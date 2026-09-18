"""資産一覧出力の本体（設計書 6章・確定仕様 Q5〜Q52）。

- 起点から全階層のフォルダを 1 フォルダ 1 行（Q29=C）で 11 列集計
- 各行は「直下」と「配下（再帰）」の両統計を持つ（Q29-1）
- 除外は部分木枝刈り（Q29-6）・ディレクトリリンクはスキップ（Q29-7・Q45=A）
- 読取エラーは統計空欄＋備考集約で継続・exit 2（Q17=A・Q36=A・Q29-16）
- 合計行は独立計算（直下系合計・Q20=A'・Q29-10）
- 出力は .tmp 逐次書き込み＋完了時 os.replace（Q47=A）
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from mytools_common.scan import is_excluded, is_hidden

from .config import Config

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_PARTIAL = 2

ROOT_LABEL = "(ルート)"
NOTE_ERROR = "読取エラー"
NOTE_LINK = "リンクスキップ"
WARN_ROW_LIMIT = 1_000_000      # 行数上限なし・超過は WARN（Q29-8）
DRY_RUN_TOP_N = 10              # dry-run のサイズ上位表示件数（Q35=A）

COLUMNS = [
    "保管フォルダ", "フォルダ名", "深さ",
    "ファイル数(直下)", "サイズ(直下)byte", "サイズ(直下)表示",
    "ファイル数(配下)", "サイズ(配下)byte", "サイズ(配下)表示",
    "最新更新日時(配下最大)", "備考",
]

DETAIL_COLUMNS = ["相対パス", "サイズ", "更新日時", "SHA-256", "備考"]


def human_size(num: Optional[int]) -> str:
    """human readable サイズ（例 `1.2 GB`・Q39=A）。None/0 は `0 B`。"""
    if not num:
        return "0 B"
    n = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_mtime(ts: Optional[float]) -> str:
    """ローカル時刻 `YYYY-MM-DD HH:MM:SS`（Q38=A）。"""
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class Row:
    """11 列の 1 行（フォルダ集約・Q29=C）。None は統計取得不能（空欄出力）。"""
    rel_comps: Tuple[str, ...]
    storage: str                     # 列1 保管フォルダ（相対パス or (ルート)）
    name: str                        # 列2 フォルダ名
    depth: int                       # 列3 深さ
    files_d: Optional[int] = None    # 列4 ファイル数(直下)
    size_d: Optional[int] = None     # 列5 サイズ(直下)byte
    files_r: Optional[int] = None    # 列7 ファイル数(配下)
    size_r: Optional[int] = None     # 列8 サイズ(配下)byte
    mtime_r: Optional[float] = None  # 列10 最新更新日時(配下最大)
    notes: List[str] = field(default_factory=list)  # 列11 備考

    @property
    def files_d_str(self) -> str:
        return "" if self.files_d is None else str(self.files_d)

    @property
    def size_d_str(self) -> str:
        return "" if self.size_d is None else str(self.size_d)

    @property
    def size_d_disp(self) -> str:
        return "" if self.size_d is None else human_size(self.size_d)

    @property
    def files_r_str(self) -> str:
        return "" if self.files_r is None else str(self.files_r)

    @property
    def size_r_str(self) -> str:
        return "" if self.size_r is None else str(self.size_r)

    @property
    def size_r_disp(self) -> str:
        return "" if self.size_r is None else human_size(self.size_r)

    @property
    def mtime_r_str(self) -> str:
        return "" if self.mtime_r is None else format_mtime(self.mtime_r)

    @property
    def notes_str(self) -> str:
        return "; ".join(self.notes)

    def cells(self) -> List[str]:
        return [self.storage, self.name, str(self.depth),
                self.files_d_str, self.size_d_str, self.size_d_disp,
                self.files_r_str, self.size_r_str, self.size_r_disp,
                self.mtime_r_str, self.notes_str]


@dataclass
class DetailRow:
    """詳細一覧の 1 行（6.7・Q27=A）。"""
    rel_path: str
    size: int = 0
    mtime: Optional[float] = None
    sha256: Optional[str] = None     # --with-hash 時のみ
    notes: str = ""

    def cells(self, with_hash: bool) -> List[str]:
        cells = [self.rel_path, str(self.size) if self.size is not None else "",
                 format_mtime(self.mtime)]
        if with_hash:
            cells.append(self.sha256 or "")
        cells.append(self.notes)
        return cells


@dataclass
class SubStats:
    """配下統計の集約（再帰合成用）。"""
    files: int = 0
    size: int = 0
    mtime: Optional[float] = None
    errors: int = 0
    link_skips: int = 0

    @classmethod
    def merge(cls, *parts: "SubStats") -> "SubStats":
        s = cls()
        for p in parts:
            s.files += p.files
            s.size += p.size
            if p.mtime is not None:
                s.mtime = p.mtime if s.mtime is None else max(s.mtime, p.mtime)
            s.errors += p.errors
            s.link_skips += p.link_skips
        return s


def _rel_key(comps: Tuple[str, ...]):
    """相対パスのコンポーネント比較（大小文字無視・pre-order・Q29-3/Q50=A）。"""
    return tuple(c.lower() for c in comps)


def sort_rows(rows: List[Row], sort_key: str, order: str) -> None:
    """ソート（Q14=A・Q29-12・Q50=A）。

    - 第2キー＝相対パス昇順（安定ソートで担保）
    - 空値（統計なし）は asc/desc とも末尾
    """
    rows.sort(key=lambda r: _rel_key(r.rel_comps))  # 既定順（第2キー）
    if sort_key == "name":
        # rel_path はユニークのため reverse ソートで同値衝突なし
        rows.sort(key=lambda r: _rel_key(r.rel_comps), reverse=(order == "desc"))
        return
    # size/mtime/files は配下基準（Q29-12）。desc は -x を使用し、
    # 空値は末尾固定・第2キー（相対パス昇順）は維持（stable sort）。

    def primary(r: Row):
        if sort_key == "size":
            return None if r.size_r is None else -r.size_r
        if sort_key == "mtime":
            return None if r.mtime_r is None else -r.mtime_r
        if sort_key == "files":
            return None if r.files_r is None else -r.files_r
        return _rel_key(r.rel_comps)

    rows.sort(key=lambda r: (1, 0) if primary(r) is None else (0, primary(r)))


# ---------- 走査 ----------

MAX_SCAN_DEPTH = 500            # 実用上の再帰安全上限（仕様上は深さ非固定）


@dataclass
class ScanState:
    """走査中の共有状態（行リスト・進捗・合算統計）。"""
    rows: List[Row] = field(default_factory=list)
    detail_rows: Optional[List[DetailRow]] = None   # --detail 時のみ
    visited: set = field(default_factory=set)       # 循環防止（Q45=A）
    scanned_files: int = 0                          # 走査済みファイル数（Q46=A）
    total_errors: int = 0
    total_link_skips: int = 0


def _excluded(name: str, cfg: Config) -> bool:
    return is_excluded(name, exclude_names=cfg.exclude_names,
                       exclude_pattern=cfg.exclude_pattern, include_os_system=True)


def _rel_disp(rel_comps: Tuple[str, ...]) -> str:
    return "\\".join(rel_comps) if rel_comps else ROOT_LABEL


def _read_direct(dir_path: Path, rel_comps: Tuple[str, ...], cfg: Config,
                 state: ScanState, cb: Callable) -> Tuple[Optional[SubStats],
                                                          List, int, int]:
    """dir_path の直下統計を 1 段走査する。戻り値: (direct|None, 子フォルダ候補,
    読取エラー数, リンクスキップ数)。None は scandir 失敗（読取エラー）。

    隠し属性の「フォルダ」枝刈りは呼び出し側で行う（部分木枝刈り・Q29-6）。
    """
    direct = SubStats()
    errors = 0
    link_skips = 0
    child_dirs: List = []
    try:
        entries = list(os.scandir(dir_path))
    except OSError:
        return None, [], 1, 0
    for ent in sorted(entries, key=lambda e: e.name.lower()):
        name = ent.name
        if _excluded(name, cfg):
            continue
        try:
            is_link = ent.is_symlink()
            is_dir = ent.is_dir(follow_symlinks=False)
        except OSError:
            errors += 1
            continue
        if is_link and is_dir:
            link_skips += 1          # ディレクトリリンクは非追跡（Q29-7）
            continue
        if is_dir:
            child_dirs.append((Path(ent.path), name))
            continue
        try:
            st = ent.stat(follow_symlinks=False)
        except OSError:
            errors += 1
            if state.detail_rows is not None:
                state.detail_rows.append(DetailRow(
                    rel_path="\\".join((*rel_comps, name)), notes=f"{NOTE_ERROR}1件"))
            continue
        if is_hidden(Path(ent.path)):
            continue
        direct.files += 1
        direct.size += st.st_size
        direct.mtime = st.st_mtime if direct.mtime is None else max(
            direct.mtime, st.st_mtime)
        state.scanned_files += 1
        cb(state.scanned_files, 0, f"走査中: {_rel_disp((*rel_comps, name))}")
        if state.detail_rows is not None:
            state.detail_rows.append(DetailRow(
                rel_path="\\".join((*rel_comps, name)),
                size=st.st_size, mtime=st.st_mtime))
    return direct, child_dirs, errors, link_skips


def _make_row(dir_path: Path, rel_comps: Tuple[str, ...], direct: Optional[SubStats],
              subtree: Optional[SubStats], notes: List[str]) -> Row:
    return Row(rel_comps=rel_comps,
               storage=_rel_disp(rel_comps),
               name=dir_path.name,
               depth=len(rel_comps),
               files_d=direct.files if direct else None,
               size_d=direct.size if direct else None,
               files_r=subtree.files if subtree else None,
               size_r=subtree.size if subtree else None,
               mtime_r=subtree.mtime if subtree else None,
               notes=notes)


def _notes_of(errors: int, link_skips: int) -> List[str]:
    notes: List[str] = []
    if errors:
        notes.append(f"{NOTE_ERROR}{errors}件")
    if link_skips:
        notes.append(f"{NOTE_LINK}{link_skips}件")
    return notes


def _scan_children(child_dirs: List, rel_comps: Tuple[str, ...], cfg: Config,
                   state: ScanState, cb: Callable, parent_parts: List) -> None:
    """子フォルダを走査して parent_parts に配下統計を追加する。"""
    child_dirs.sort(key=lambda t: t[1].lower())
    for child_path, child_name in child_dirs:
        child_comps = (*rel_comps, child_name)
        if is_hidden(child_path):
            continue            # 隠しフォルダは部分木ごと枝刈り（Q31=A）
        if cfg.recursive:
            parent_parts.append(_scan_dir(child_path, child_comps, cfg, state, cb))
        else:
            # --no-recursive: 起点直下のみ（Q29-9）・子は直下統計のみ
            cdirect, _, cerr, clink = _read_direct(child_path, child_comps, cfg, state, cb)
            if cdirect is None:
                state.rows.append(_make_row(
                    child_path, child_comps, None, None, _notes_of(cerr, clink)))
                state.total_errors += cerr
                parent_parts.append(SubStats(errors=cerr))
            else:
                state.rows.append(_make_row(
                    child_path, child_comps, cdirect, cdirect, _notes_of(cerr, clink)))
                state.total_errors += cerr
                state.total_link_skips += clink
                parent_parts.append(cdirect)


def _scan_dir(dir_path: Path, rel_comps: Tuple[str, ...], cfg: Config,
              state: ScanState, cb: Callable) -> SubStats:
    """dir_path 自身を 1 行として作成し、部分木の配下統計を返す（Q29=C）。"""
    try:
        state.visited.add(os.path.realpath(dir_path))
    except OSError:
        state.visited.add(str(dir_path))
    direct, child_dirs, errors, link_skips = _read_direct(
        dir_path, rel_comps, cfg, state, cb)

    if direct is None:
        # 読取エラー: 統計空欄・部分木は走査不能（行のみ出力・Q29-16）
        state.rows.append(_make_row(dir_path, rel_comps, None, None,
                                    _notes_of(errors, link_skips)))
        state.total_errors += errors
        state.total_link_skips += link_skips
        return SubStats(errors=errors)

    parts = [direct]
    if len(rel_comps) < MAX_SCAN_DEPTH:
        _scan_children(child_dirs, rel_comps, cfg, state, cb, parts)

    subtree = SubStats.merge(*parts)
    state.rows.append(_make_row(dir_path, rel_comps, direct, subtree,
                                _notes_of(errors, link_skips)))
    state.total_errors += errors
    state.total_link_skips += link_skips
    return subtree


def scan_tree(cfg: Config, cb: Callable) -> ScanState:
    """起点から全階層を走査し、`(ルート)` 行を含む全行を作る（Q28=A・Q29=C）。"""
    state = ScanState(detail_rows=[] if cfg.detail else None)
    root = cfg.input_dir
    try:
        state.visited.add(os.path.realpath(root))
    except OSError:
        state.visited.add(str(root))
    direct, child_dirs, errors, link_skips = _read_direct(root, (), cfg, state, cb)

    if direct is None:
        # 起点が読めない: `(ルート)` 行のみ（空欄）で exit 2 相当
        state.rows.append(_make_row(root, (), None, None, _notes_of(errors, link_skips)))
        state.total_errors += errors
        state.total_link_skips += link_skips
        return state

    parts: List[SubStats] = [direct]
    _scan_children(child_dirs, (), cfg, state, cb, parts)
    subtree = SubStats.merge(*parts)
    state.total_errors += errors
    state.total_link_skips += link_skips
    state.rows.insert(0, _make_row(root, (), direct, subtree, _notes_of(errors, link_skips)))
    return state


# ---------- 合計行 ----------

def compute_total(rows: List[Row]) -> Row:
    """合計行（末尾1行・独立計算・Q20=A'・Q29-10）。

    列4/5 は全行の直下系合計（=ユニーク総数）・列7〜9 は二重計上回避で空欄・
    列10 は全体の最新更新日時・列11 は `フォルダ数 N`（`(ルート)` 除く）。
    """
    files_total = 0
    size_total = 0
    mtime_max: Optional[float] = None
    folder_count = 0
    for r in rows:
        # ファイル総数・総サイズは `(ルート)` の直下も含む（ユニーク・Q29-10）
        if r.files_d is not None:
            files_total += r.files_d
        if r.size_d is not None:
            size_total += r.size_d
        if r.mtime_r is not None:
            mtime_max = r.mtime_r if mtime_max is None else max(mtime_max, r.mtime_r)
        if r.storage != ROOT_LABEL:
            folder_count += 1
    return Row(rel_comps=(), storage="合計", name="", depth=0,
               files_d=files_total, size_d=size_total, mtime_r=mtime_max,
               notes=[f"フォルダ数 {folder_count}"])


# ---------- 詳細一覧（--with-hash） ----------

def fill_sha256(detail_rows: List[DetailRow], cfg: Config,
                cb: Callable) -> None:
    """--with-hash 時に SHA-256 を逐次計算する（Q8=A・件数表示）。"""
    import hashlib
    total = len(detail_rows)
    for i, d in enumerate(detail_rows, start=1):
        if d.notes:                 # 読取エラー行は計算対象外
            continue
        path = cfg.input_dir.joinpath(*d.rel_path.split("\\"))
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            d.sha256 = h.hexdigest()
        except OSError:
            d.sha256 = None
            d.notes = f"{NOTE_ERROR}1件" if not d.notes else d.notes
        cb(i, total, f"ハッシュ: {i}/{total}")


# ---------- 実行エントリ ----------

def _log_summary(logger, rows: List[Row], state: ScanState) -> None:
    files_total = sum(r.files_d or 0 for r in rows if r.storage != ROOT_LABEL)
    size_total = sum(r.size_d or 0 for r in rows if r.storage != ROOT_LABEL)
    logger.info("summary: フォルダ=%s ファイル=%s 総サイズ=%s 読取エラー=%s "
                "リンクスキップ=%s",
                len(rows) - 1, files_total, human_size(size_total),
                state.total_errors, state.total_link_skips)
    if state.total_errors:
        logger.warning("読取エラーがあるため配下の統計は取得できた範囲の集計です")


def _dry_run_log(logger, rows: List[Row]) -> None:
    logger.info("DRY-RUN: ファイル出力を行いません（Q35=A）")
    ranked = sorted((r for r in rows if r.size_r is not None and r.storage != ROOT_LABEL),
                    key=lambda r: r.size_r, reverse=True)
    for r in ranked[:DRY_RUN_TOP_N]:
        logger.info("  上位: %s （配下 %s）", r.storage, human_size(r.size_r))


def run(cfg: Config, logger,
        progress_callback: Optional[Callable[[int, int, str], None]] = None) -> int:
    """資産一覧出力を実行する。戻り値は終了コード（0/1/2/130）。"""
    cb = progress_callback or (lambda cur, total, msg: None)
    logger.info("asset-tool 開始: 入力=%s", cfg.input_dir)
    try:
        state = scan_tree(cfg, cb)
    except RecursionError as exc:
        logger.error("階層が深すぎるため走査を中止しました: %s", exc)
        return EXIT_FATAL

    sort_rows(state.rows, cfg.sort, cfg.order)
    total_row = compute_total(state.rows)
    _log_summary(logger, state.rows, state)

    if cfg.dry_run:
        _dry_run_log(logger, state.rows)
        return EXIT_PARTIAL if state.total_errors else EXIT_OK

    if len(state.rows) > WARN_ROW_LIMIT:
        logger.warning("行数が %s 行を超えました（性能低下の可能性）", WARN_ROW_LIMIT)

    from . import writers
    try:
        out_path = writers.write_aggregate(cfg, state.rows, total_row, logger)
        detail_path = None
        if cfg.detail and state.detail_rows is not None:
            if cfg.with_hash:
                fill_sha256(state.detail_rows, cfg, cb)
            detail_path = writers.write_detail(cfg, state.detail_rows, logger)
    except KeyboardInterrupt:
        logger.warning("中断されました (Ctrl+C)")
        writers.cleanup_tmp(cfg)
        raise
    except OSError as exc:
        logger.error("出力書き込みエラー: %s", exc)
        return EXIT_FATAL

    logger.info("出力: %s", out_path)
    if detail_path:
        logger.info("詳細出力: %s", detail_path)

    return EXIT_PARTIAL if state.total_errors else EXIT_OK
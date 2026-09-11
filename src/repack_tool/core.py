"""Core: 全体オーケストレーション（設計書 5.1）。CLI/GUI双方から呼ばれる。"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .checker import check_archive
from .classifier import classify
from .config import Config
from .extractor import Extractor
from .passwords import PasswordList
from .paths import long_path, resolve_no_follow
from .progress import ProgressLogger
from .repacker import (archive_stem, create_group_zip, create_zip,
                       folder_zip_name, group_zip_name, unique_path)
from .scanner import ArchiveItem, archive_kind, is_within, scan


@dataclass
class RepackResult:
    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    success_zips: List[Path] = field(default_factory=list)
    skips: List[tuple] = field(default_factory=list)      # (name, reason, detail)
    failures: List[tuple] = field(default_factory=list)   # (name, reason, detail)


class RepackError(Exception):
    """致命的エラー（終了コード1相当）。"""


def run(config: Config, logger: ProgressLogger,
        progress_callback: Optional[Callable[[int, int, str], None]] = None) -> int:
    """実行。終了コード 0/2/1 を返す（130はcli側で処理）。"""
    result = RepackResult()

    # ---- 入出力検証 ----
    input_dir = resolve_no_follow(config.input_dir)
    if not input_dir.is_dir():
        logger.error("入力フォルダが存在しません: %s", input_dir)
        return 1
    output_dir = resolve_no_follow(config.output_dir)
    if is_within(output_dir, input_dir) and not config.allow_output_inside_input:
        logger.error(
            "出力フォルダが入力フォルダ配下です(Q40): %s\n"
            "別の出力先を指定するか --allow-output-inside-input で明示許可してください。",
            output_dir)
        return 1
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("出力フォルダを作成できません: %s (%s)", output_dir, exc)
        return 1

    # ---- 辞書 ----
    try:
        pwlist = PasswordList.from_file(config.password_list, config.encoding,
                                        config.max_passwords)
        if pwlist.truncated:
            logger.warning("パスワード辞書が上限 %s 件で切り詰められました", config.max_passwords)
    except Exception as exc:  # noqa: BLE001
        logger.error("パスワード辞書の読込に失敗: %s", exc)
        return 1

    # ---- 探索 ----
    items = scan(input_dir, output_dir, config)
    result.total = len(items)
    logger.set_total(len(items))
    if config.dry_run:
        logger.info("DRY-RUN: 解凍・書込は行いません")
        for it in items:
            logger.info("  対象: %s (%s)", it.path, it.kind)
        logger.info("summary: total=%s (dry-run)", len(items))
        return 0

    extractor = Extractor(config, logger)
    used_names: set = set()

    for idx, it in enumerate(items, 1):
        try:
            _process_item(it, config, logger, extractor, pwlist, output_dir,
                          input_dir, result, used_names)
        except Exception as exc:  # noqa: BLE001
            logger.error("予期しないエラー: %s (%s)", it.path, exc)
            result.failed += 1
            result.failures.append((it.path.name, "unexpected", str(exc)))
        finally:
            if progress_callback is not None:
                progress_callback(idx, result.total, f"{it.path.name} 処理完了")
            logger.update(1)

    _summary(logger, result)
    return 2 if (result.skipped > 0 or result.failed > 0) else 0


def _process_item(it: ArchiveItem, config: Config, logger: ProgressLogger,
                  extractor: Extractor, pwlist: PasswordList,
                  output_dir: Path, input_dir: Path, result: RepackResult,
                  used_names: set) -> None:
    """アーカイブ1件の処理: 検証→解凍→入れ子展開→分類→zip化→後片付け。"""
    name = it.path.name
    if it.missing_parts:
        result.skipped += 1
        result.skips.append((name, "missing-part", "分割巻が揃っていません"))
        logger.warning("%s -> skip (reason=missing-part)", name)
        return
    if it.split_volume and not it.split_leader:
        result.skipped += 1
        result.skips.append((name, "split-part", "従属巻のため対象外"))
        logger.warning("%s -> skip (reason=split-part)", name)
        return

    # 事前整合性チェック（lib系のみ。7z/rarは解凍時に判定）
    if it.kind in ("zip", "tar_gz", "tgz", "tar_bz2", "tbz2", "tar_xz", "txz",
                   "gz", "bz2", "xz"):
        ok, _ = check_archive(it.path, it.kind)
        if not ok:
            skip_fail(result, logger, name, "corrupt", "事前整合性チェック失敗")
            return

    # ---- 一時解凍 ----
    tmp = Path(tempfile.mkdtemp(prefix="repack_"))
    try:
        ok, reason, tried = extractor.extract(it.path, it.kind, long_path(tmp),
                                              list(pwlist))
        if not ok:
            # 分割先頭巻が解凍できないのは欠巻の可能性が高い（Q33）
            if it.split_leader and it.split_volume and reason == "corrupt":
                reason = "missing-part"
            skip_fail(result, logger, name, reason, f"tried={tried}")
            return

        # ---- 入れ子展開（Q38/Q49） ----
        if config.nested_depth > 0:
            _expand_nested(tmp, 1, config, logger, extractor, pwlist)

        # ---- 分類 ----
        cr = classify(tmp, config, logger)
        if cr.is_empty:
            skip_fail(result, logger, name, "empty", "解凍結果が空")
            return

        # ---- 出力先（ミラー） ----
        out_dir = _output_target(it, config, output_dir, input_dir)

        created: List[Path] = []
        had_skip = False
        for d in cr.dirs:
            if not _has_content(d, config):
                logger.info("%s -> skip: empty-folder %s", name, d.name)
                result.skipped += 1
                result.skips.append((name, "empty-folder", d.name))
                had_skip = True
                continue
            zpath = unique_path(out_dir, folder_zip_name(d.name), used_names)
            if create_zip(d, zpath, config, logger):
                created.append(zpath)
            else:
                result.failed += 1
                result.failures.append((name, "write-failed", str(zpath)))

        if cr.files:
            zpath = unique_path(out_dir, group_zip_name(it.path), used_names)
            if create_group_zip(cr.files, zpath, config, logger):
                created.append(zpath)
            else:
                result.failed += 1
                result.failures.append((name, "write-failed", str(zpath)))

        if created:
            result.success += 1
            result.success_zips.extend(created)
            logger.info("%s -> extract ok -> zip: %s",
                        name, ", ".join(p.name for p in created))
        elif not had_skip:
            skip_fail(result, logger, name, "empty", "作成可能なzipなし")
    finally:
        if config.keep_temp:
            logger.info("一時フォルダを保持: %s", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    return 2 if (result.skipped > 0 or result.failed > 0) else 0
def skip_fail(result: RepackResult, logger: ProgressLogger, name: str,
              reason: str, detail: str) -> None:
    result.skipped += 1
    result.skips.append((name, reason, detail))
    logger.warning("%s -> skip (reason=%s, %s)", name, reason, detail)


def _expand_nested(root: Path, depth: int, config: Config, logger: ProgressLogger,
                   extractor: Extractor, pwlist: PasswordList) -> None:
    """解凍結果の中に圧縮があれば再帰展開（Q38）。深さ上限は config.nested_depth。"""
    if depth > config.nested_depth:
        logger.warning("入れ子の深さ上限(%s)を超過したため展開を中止", config.nested_depth)
        return
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        kind = archive_kind(p)
        if kind is None:
            continue
        if ".repack_tmp" in p.name:
            continue
        tmp2 = p.parent / (p.name + ".repack_tmp")
        try:
            ok, reason, _ = extractor.extract(p, kind, long_path(tmp2), list(pwlist))
        except Exception:  # noqa: BLE001
            ok = False
            reason = "corrupt"
        if not ok:
            shutil.rmtree(tmp2, ignore_errors=True)
            logger.warning("入れ子解凍失敗: %s (reason=%s) ファイルのまま残します",
                           p.name, reason)
            continue
        try:
            p.unlink()
            _merge_dir(tmp2, p.parent)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)
        # リストが変わったので再帰的に再スキャン
        _expand_nested(root, depth + 1, config, logger, extractor, pwlist)
        return


def _merge_dir(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _merge_dir(item, target)
        else:
            if target.exists():
                target = dst / (item.stem + "_dup" + item.suffix)
            shutil.move(str(item), str(target))


def _output_target(it: ArchiveItem, config: Config, output_dir: Path,
                   input_dir: Path) -> Path:
    if config.flat:
        return output_dir
    rel = it.path.relative_to(input_dir)
    parent = rel.parent
    stem = archive_stem(it.path)
    return output_dir / parent / stem


def _has_content(d: Path, config: Config) -> bool:
    for p in d.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and \
           p.name.lower() not in {n.lower() for n in config.exclude_names}:
            return True
    return False


def _summary(logger: ProgressLogger, result: RepackResult) -> None:
    logger.info("summary: total=%s success=%s skip=%s fail=%s",
                result.total, result.success, result.skipped, result.failed)
    if result.success_zips:
        logger.info("作成zip一覧:")
        for p in result.success_zips:
            logger.info("  %s", p)
    if result.skips:
        logger.info("スキップ一覧:")
        for name, reason, detail in result.skips:
            logger.info("  %s (reason=%s, %s)", name, reason, detail)
    if result.failures:
        logger.info("失敗一覧:")
        for name, reason, detail in result.failures:
            logger.info("  %s (reason=%s, %s)", name, reason, detail)
"""再圧縮（設計書 7章）。命名・ミラー出力・連番衝突回避・zip作成・読戻し検証。"""
from __future__ import annotations

import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional, Set

from .config import Config
from .paths import sanitize_name
from .progress import ProgressLogger


def archive_stem(path: Path) -> str:
    """アーカイブの基底名。foo.tar.gz -> foo / foo.7z -> foo / foo.7z.001 -> foo。"""
    name = path.name
    # 分割巻: .7z.001 / .part1.rar / .z01 の数字部を除去
    import re as _re
    m = _re.search(r"\.(7z\.\d{3,}|part\d{1,3}r?\.rar|z\d{2})$", name.lower())
    if m:
        name = name[: m.start(1)]
    low = name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz",
                   ".7z", ".zip", ".rar", ".gz", ".bz2", ".xz"):
        if low.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def folder_zip_name(folder_name: str) -> str:
    """フォルダ名 -> <sanitize>.zip（Q7）。"""
    return sanitize_name(folder_name) + ".zip"


def group_zip_name(archive: Path) -> str:
    """ファイル群zip名: <基底名>_files.zip（Q36提案）。"""
    return sanitize_name(archive_stem(archive)) + "_files.zip"


def unique_path(target_dir: Path, desired: str, used: Set[str]) -> Path:
    """同名があれば _001, _002... を付けて別名保存（Q11/Q41）。used は同一実行内の衝突回避用。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    base = desired
    if desired.lower().endswith(".zip"):
        base = desired[:-4]
    candidate = target_dir / f"{base}.zip"
    n = 1
    key = str(candidate).lower()
    while candidate.exists() or key in used:
        candidate = target_dir / f"{base}_{n:03d}.zip"
        key = str(candidate).lower()
        n += 1
    used.add(key)
    return candidate


def _should_include(rel: Path, config: Config) -> bool:
    """zip化時に含めるファイルか（隠し・ドット・OSゴミ・除外パターンは除く）。"""
    name = rel.name
    if name.startswith("."):
        return False
    if name.lower() in {n.lower() for n in config.exclude_names}:
        return False
    if config.exclude_pattern:
        try:
            if re.search(config.exclude_pattern, name):
                return False
        except re.error:
            pass
    return True


def _dt_from_mtime(mtime: float) -> tuple:
    """1980以前は1980-01-01に丸める（Q27: 日時は保持しない）。"""
    t = time.localtime(mtime)
    if t.tm_year < 1980:
        return (1980, 1, 1, 0, 0, 0)
    return (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)


def _write_entry(zf: zipfile.ZipFile, path: Path, arcname: str) -> None:
    """ファイルを1エントリとして書く。ZipInfo.from_file は1980以前で例外となるため自作。"""
    st = path.stat()
    zi = zipfile.ZipInfo(arcname, _dt_from_mtime(st.st_mtime))
    zi.file_size = st.st_size
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.flag_bits |= 0x800  # UTF-8 ファイル名フラグ（Q30）
    with path.open("rb") as src, zf.open(zi, "w") as dst:
        shutil.copyfileobj(src, dst)


def create_zip(source: Path, zip_path: Path, config: Config,
               logger: ProgressLogger, arc_root: Optional[Path] = None) -> bool:
    """source 配下のファイルを zip 化する。arc_root 未指定なら source がアーカイブ内ルート。"""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    root = arc_root or source
    try:
        with zipfile.ZipFile(zip_path, "w",
                             compression=zipfile.ZIP_DEFLATED,
                             compresslevel=config.compression_level,
                             allowZip64=config.zip64) as zf:
            for p in sorted(source.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(root)
                if not _should_include(rel, config):
                    continue
                _write_entry(zf, p, rel.as_posix())
        # 読戻し検証（5.5）
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
        if bad is not None:
            logger.warning("zip検証失敗: %s (bad=%s)", zip_path, bad)
            zip_path.unlink(missing_ok=True)
            return False
        return True
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        logger.error("zip作成失敗: %s (%s)", zip_path, exc)
        zip_path.unlink(missing_ok=True)
        return False


def create_group_zip(files: Iterable[Path], zip_path: Path, config: Config,
                     logger: ProgressLogger) -> bool:
    """トップレベル直下ファイル群を1つのzipにまとめる（Q16）。"""
    file_list = [f for f in files if f.is_file()]
    if not file_list:
        return False
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "w",
                             compression=zipfile.ZIP_DEFLATED,
                             compresslevel=config.compression_level,
                             allowZip64=config.zip64) as zf:
            for f in file_list:
                if _should_include(Path(f.name), config):
                    _write_entry(zf, f, sanitize_name(f.name))
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
        if bad is not None:
            logger.warning("zip検証失敗: %s (bad=%s)", zip_path, bad)
            zip_path.unlink(missing_ok=True)
            return False
        return True
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        logger.error("zip作成失敗: %s (%s)", zip_path, exc)
        zip_path.unlink(missing_ok=True)
        return False
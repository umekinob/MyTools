"""Scanner: 再帰探索・対象拡張子判定・分割巻検出（設計書 5.2/5.3）。"""
from __future__ import annotations

import re
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from .config import ARCHIVE_SUFFIXES, SPLIT_RE, Config
from .paths import resolve_no_follow


SUFFIX_KINDS = {
    ".tar.gz": {"tar_gz"}, ".tar.bz2": {"tar_bz2"}, ".tar.xz": {"tar_xz"},
    ".tgz": {"tgz"}, ".tbz2": {"tbz2"}, ".txz": {"txz"},
    ".7z": {"7z"}, ".zip": {"zip"}, ".rar": {"rar"},
    ".gz": {"gz", "tar_gz"}, ".bz2": {"bz2", "tar_bz2"},
    ".xz": {"xz", "tar_xz"},
}


def _kinds_allowed(include_exts) -> set:
    kinds = set()
    for s in include_exts:
        kinds |= SUFFIX_KINDS.get(s.lower(), set())
    return kinds


@dataclass
class ArchiveItem:
    """処理対象アーカイブ1件。分割巻は先頭巻のみを保持。"""
    path: Path
    kind: str            # 7z / zip / rar / tar_gz / tgz / tar_bz2 / tar_xz / gz / bz2 / xz
    split_leader: bool   # 分割の先頭巻か
    split_volume: bool   # 分割の従属巻か（処理対象外）
    missing_parts: bool  # 分割の欠巻があるか


def archive_kind(path: Path) -> Optional[str]:
    """拡張子から種別を返す。対象外はNone。複合拡張子・分割巻を先に判定。"""
    name = path.name.lower()
    # 分割巻（先頭・従属とも種別判定する）
    if re.search(r"\.7z\.\d{3,}$", name):
        return "7z"
    if re.search(r"\.part\d{1,3}\.rar$|\.part\d{1,3}r\.rar$", name):
        return "rar"
    if re.search(r"\.z\d{2}$", name):
        return "zip"
    for suffix, kind in (
            (".tar.gz", "tar_gz"), (".tar.bz2", "tar_bz2"), (".tar.xz", "tar_xz"),
            (".tgz", "tgz"), (".tbz2", "tbz2"), (".txz", "txz"),
            (".7z", "7z"), (".zip", "zip"), (".rar", "rar"),
            (".gz", "gz"), (".bz2", "bz2"), (".xz", "xz")):
        if name.endswith(suffix):
            return kind
    return None


def _split_info(path: Path, kind: str) -> tuple:
    """(is_leader, is_volume, missing) を返す。分割でない場合は (True, False, False)。"""
    name = path.name.lower()
    if kind == "7z":
        m = re.search(SPLIT_RE["7z"], name)
        if m:
            num = int(m.group(0).split(".")[-1])
            return (num == 1, True, False)
    elif kind == "rar":
        m = re.search(SPLIT_RE["rar"], name)
        if m:
            part = m.group(1)
            num = int(re.search(r"\d+", part).group())
            return (num == 1, True, False)
    elif kind == "zip":
        # .z01 等は従属巻扱い（本体 .zip がリーダー）
        if re.search(SPLIT_RE["zip"], name):
            return (False, True, False)
    return (True, False, False)


def _missing_parts(path: Path, kind: str) -> bool:
    """分割の欠巻チェック（Q9/Q33）。先頭巻の隣に期待連番が全て揃っているか。"""
    if kind == "7z" and re.search(SPLIT_RE["7z"], path.name.lower()):
        base = path.name[: path.name.rfind(".")]  # 例: a.7z.001 -> a.7z
        num = int(path.suffix[1:])
        for i in range(2, num + 1):
            if not (path.parent / f"{base}.{i:03d}").exists():
                return True
        return False
    if kind == "rar" and re.search(SPLIT_RE["rar"], path.name.lower()):
        m = re.search(SPLIT_RE["rar"], path.name.lower())
        part = m.group(1)
        num = int(re.search(r"\d+", part).group())
        base = path.name[: path.name.lower().rfind(".part")]
        for i in range(1, num + 1):
            if not (path.parent / f"{base}.part{i:02d}.rar").exists() and \
               not (path.parent / f"{base}.part{i}.rar").exists():
                return True
        return False
    if kind == "zip" and re.search(SPLIT_RE["zip"], path.name.lower()):
        return False
    return False


def scan(input_dir: Path, output_dir: Path, config: Config) -> List[ArchiveItem]:
    """入力ルートを探索し処理対象一覧を返す（相対パス昇順・決定的）。"""
    root = resolve_no_follow(input_dir)
    out = resolve_no_follow(output_dir)
    # 出力が入力配下 or 同一ならスキャン除外（Q40）
    exclude_out = is_within(out, root)

    items: List[ArchiveItem] = []
    for p in sorted(root.rglob("*") if config.recursive else root.glob("*")):
        if not p.is_file():
            continue
        rp = resolve_no_follow(p)
        if exclude_out and _is_within(rp, out):
            continue
        kind = archive_kind(p)
        if kind is None:
            continue
        if kind not in _kinds_allowed(config.include_exts):
            continue
        leader, volume, _ = _split_info(p, kind)
        if volume and not leader:
            continue  # 従属巻はスキップ
        missing = _missing_parts(p, kind)
        items.append(ArchiveItem(path=p, kind=kind, split_leader=leader,
                                 split_volume=volume, missing_parts=missing))

    items.sort(key=lambda it: str(it.path.relative_to(root)).lower())
    return items


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
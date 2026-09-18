"""パス補助（repack_tool/paths.py から複写・Q30=A/Q1=B）。ドリフトは差分検知テストで検知する。"""
from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

# Windowsで長いパス(260文字超)を扱うためのprefix。
_LONG_PREFIX = "\\\\?\\"
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

IS_WINDOWS = sys.platform.startswith("win")


def long_path(path: Path) -> Path:
    """Windows向けに \\\\?\\ を付与したPathを返す（存在しない/未正規化でも可）。"""
    if not IS_WINDOWS:
        return path
    s = str(path)
    if s.startswith(_LONG_PREFIX):
        return Path(s)
    abs_s = str(Path.cwd() / path) if not Path(path).is_absolute() else s
    # 絶対パスへ統一（相対パスはcwd結合）
    norm = re.sub(r"[/\\]+", "\\\\", abs_s)
    if norm.endswith("\\") and len(norm) > 3:
        norm = norm[:-1]
    return Path(_LONG_PREFIX + norm)


def sanitize_name(name: str) -> str:
    """OS非対応文字・空白制御文字を '_' に置換。"""
    cleaned = _ILLEGAL_CHARS.sub("_", name)
    cleaned = cleaned.strip().strip(".")
    cleaned = cleaned.replace("..", "_")
    if cleaned in ("", "."):
        cleaned = "unnamed"
    return cleaned


def is_safe_entry(entry_rel: str) -> bool:
    """Zip Slip対策: アーカイブ内エントリ名が危険か判定。"""
    p = PurePosixPath(entry_rel.replace("\\", "/"))
    if p.is_absolute():
        return False
    for part in p.parts:
        if part == "..":
            return False
    return not (p.drive or p.root)


def resolve_no_follow(path: Path) -> Path:
    """シンボリックリンクを辿らず絶対パス解決（存在しない場合は連結）。"""
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError):
        return Path(path.absolute())
"""走査・除外述語（設計書 9.2・Q30/Q31/Q32）。

repack の `classifier._is_excluded` と判定ロジックを共通化するための複写先。
repack 側は現行実装を維持し、asset が本モジュールを参照する（一方向）。
一致性は `tests/test_scan_parity.py` で検証する（OSシステム項目は asset 固有の許容差）。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional

# OSシステム項目（asset 固有の追加除外・Q31=A）
OS_SYSTEM_NAMES = frozenset({
    "$recycle.bin", "system volume information",
    "hiberfil.sys", "pagefile.sys", "swapfile.sys",
})


def is_excluded(name: str, exclude_names: Optional[Iterable[str]] = None,
                exclude_pattern: Optional[str] = None,
                include_os_system: bool = True) -> bool:
    """除外判定（repack classifier._is_excluded 相当＋OSシステム項目）。

    - exclude_names: 除外名リスト（大小文字無視）
    - exclude_pattern: 正規表現（名前部分一致）
    - ドット始まり名は除外
    - include_os_system=True で $RECYCLE.BIN 等も除外（Q31=A）
    """
    lower = name.lower()
    if include_os_system and lower in OS_SYSTEM_NAMES:
        return True
    if exclude_names and lower in {n.lower() for n in exclude_names}:
        return True
    if name.startswith("."):
        return True
    if exclude_pattern:
        try:
            if re.search(exclude_pattern, name):
                return True
        except re.error:
            pass
    return False


def is_hidden(path: Path) -> bool:
    """隠し属性判定（repack classifier._is_hidden 相当の複写）。"""
    if os.name == "nt":
        try:
            return bool(path.stat().st_file_attributes & 0x2)
        except (OSError, AttributeError):
            return False
    return path.name.startswith(".")
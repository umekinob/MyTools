"""トップレベル分類（設計書 6章）。OSゴミ・隠し・ドットを除外し、単一/複数/混在/ファイルのみ/空を判定。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .config import Config, SUSPICIOUS_KEYWORDS
from .progress import ProgressLogger


@dataclass
class ClassifyResult:
    dirs: List[Path] = field(default_factory=list)
    files: List[Path] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)   # 除外したエントリ名
    suspicious: List[str] = field(default_factory=list)  # 機密ワーニング対象名

    @property
    def is_empty(self) -> bool:
        return not self.dirs and not self.files


def _is_excluded(name: str, config: Config) -> bool:
    lower = name.lower()
    if lower in {n.lower() for n in config.exclude_names}:
        return True
    if name.startswith("."):
        return True  # ドットファイル（Q45）
    if config.exclude_pattern:
        try:
            if re.search(config.exclude_pattern, name):
                return True
        except re.error:
            pass
    return False


def _is_hidden(path: Path) -> bool:
    if os.name == "nt":
        try:
            return bool(path.stat().st_file_attributes & 0x2)  # FILE_ATTRIBUTE_HIDDEN
        except (OSError, AttributeError):
            return False
    return path.name.startswith(".")


def classify(top_dir: Path, config: Config, logger: ProgressLogger) -> ClassifyResult:
    """解凍直下を分類する。戻り値の dirs/files は除外後の中身。"""
    result = ClassifyResult()
    if not top_dir.is_dir():
        return result
    for entry in sorted(top_dir.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        if _is_excluded(name, config) or _is_hidden(entry):
            result.skipped.append(name)
            logger.debug("除外: %s", name)
            continue
        if any(k in name.lower() for k in SUSPICIOUS_KEYWORDS):
            result.suspicious.append(name)
            logger.warning("機密情報を含む可能性がある名前を検出: %s", name)
        if entry.is_dir():
            result.dirs.append(entry)
        else:
            result.files.append(entry)
    return result
"""asset_tool の設定（設計書 6.5・8章）。優先順: CLI > TOML > 既定。"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# asset 用除外名（repack 既定＋OS システム項目・Q31=A）
DEFAULT_EXCLUDE_NAMES = [".DS_Store", "Thumbs.db", "desktop.ini",
                         ".git", ".gitignore", ".gitattributes"]

@dataclass
class Config:
    """資産一覧出力の実行設定。"""

    input_dir: Path = Path(".")
    output_dir: Path = Path("out")

    format: str = "csv"                 # csv|html|md（Q5=A）
    sort: str = "name"                  # name|size|mtime|files（Q29-12: size等は配下基準）
    order: str = "asc"                  # asc|desc（Q50=A）
    recursive: bool = True              # ON=全階層 / OFF=起点直下のみ（Q29-9）

    with_hash: bool = False             # SHA-256（詳細一覧に追加・Q8=A）
    detail: bool = False                # ファイル単位一覧を別出力（Q26=A）

    exclude_names: List[str] = field(
        default_factory=lambda: list(DEFAULT_EXCLUDE_NAMES))
    exclude_pattern: Optional[str] = None

    log_file: Optional[Path] = None
    log_level: str = "INFO"

    dry_run: bool = False


def default_config() -> Config:
    return Config()


def from_dict(data: Dict[str, Any]) -> Config:
    """TOML の [asset] セクション相当の dict から Config を作る。未知キーは無視。"""
    known = {f.name for f in dataclasses.fields(Config)}
    cfg = Config()
    for key, value in data.items():
        if key not in known and key not in ("input", "output"):
            continue
        if key == "input":
            cfg.input_dir = Path(value) if value else cfg.input_dir
        elif key == "output":
            cfg.output_dir = Path(value) if value else cfg.output_dir
        elif key in ("log_file",):
            cfg.log_file = Path(value) if value else None
        else:
            setattr(cfg, key, value)
    return cfg
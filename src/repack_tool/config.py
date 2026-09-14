"""既定値・設定(Config)・拡張子一覧。設計書 5.2/7.4/8.2 に対応。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# 解凍対象拡張子（小文字比較）。複合拡張子を先に判定する。
ARCHIVE_SUFFIXES: List[str] = [
    ".tar.gz", ".tar.bz2", ".tar.xz",
    ".tgz", ".tbz2", ".txz",
    ".7z", ".zip", ".rar",
    ".gz", ".bz2", ".xz",
]

# 一時解凍先の既定フォルダ（Q19改修: 本プログラム配置場所配下の tmp/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMP_DIR = PROJECT_ROOT / "tmp"

# OSゴミ・隠し(ドット)ファイルは除外（Q45）
DEFAULT_EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".git",
                        ".gitignore", ".gitattributes", ".DS_Store"}
# 機密ワーニング用パターン（Q23）: 名前に含まれるとWARN
SUSPICIOUS_KEYWORDS = ("password", "passwd", "secret", "個人情報", "マイナンバー",
                       "クレジット", "認証情報", "credential")

# 分割巻の正規表現パターン（小文字比較）
SPLIT_RE = {
    "7z": r"\.7z\.\d{3,}$",
    "rar": r"\.(part\d{1,3}\.rar|part\d+r\.rar)$",
    "zip": r"\.z\d{2}$",   # .z01.. 側をスキップ用に利用
}


@dataclass
class Config:
    """ツール全体の実行設定。CLI・TOML・既定値の優先順: CLI > TOML > 既定。"""

    input_dir: Path = Path(".")
    output_dir: Path = Path("out")
    recursive: bool = True

    password_list: Optional[Path] = None
    encoding: str = "utf-8"
    max_passwords: int = 10000

    compression_level: int = 9          # 0-9（設計書: 最高圧縮既定）
    zip64: bool = True

    seven_zip_path: Optional[str] = None  # 自動検出結果の保持
    prefer_7z: bool = False             # lib優先（既定）

    dry_run: bool = False
    keep_temp: bool = False
    flat: bool = False
    allow_output_inside_input: bool = False
    temp_dir: Optional[Path] = None  # 未指定ならプログラム配置場所の tmp（Q19改修）

    log_file: Optional[Path] = None
    log_level: str = "INFO"             # DEBUG/INFO/WARNING/ERROR

    include_exts: List[str] = field(default_factory=lambda: list(ARCHIVE_SUFFIXES))
    exclude_names: List[str] = field(default_factory=lambda: sorted(DEFAULT_EXCLUDE_NAMES))
    exclude_pattern: Optional[str] = None  # 正規表現（Q23追加）

    nested_depth: int = 3               # 入れ子解凍の上限（Q49）
    max_extract_mb: int = 0             # 0 = 無制限（Q39）
    max_compression_ratio: int = 0      # 0 = OFF

    on_conflict: str = "increment"      # 連番のみ固定（Q46）


def default_config() -> Config:
    return Config()


def from_dict(data: Dict[str, Any]) -> Config:
    """TOML等で読んだdict(repackキー配下相当)からConfigを作る。未知キーは無視。"""
    known = {f for f in dataclasses.fields(Config)}
    cfg = Config()
    for key, value in data.items():
        if key not in known and key not in ("input", "output"):
            continue
        if key == "include_exts" and isinstance(value, list):
            cfg.include_exts = [str(v) for v in value]
        elif key == "exclude_names" and isinstance(value, list):
            cfg.exclude_names = [str(v) for v in value]
        elif key == "input":
            cfg.input_dir = Path(value) if value else cfg.input_dir
        elif key == "output":
            cfg.output_dir = Path(value) if value else cfg.output_dir
        elif key in ("password_list", "log_file", "seven_zip_path", "temp_dir"):
            setattr(cfg, key, Path(value) if value else None)
        else:
            setattr(cfg, key, value)
    return cfg
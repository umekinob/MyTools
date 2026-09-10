"""CLI（設計書 8章）。argparse + TOML設定のマージ（優先: CLI > TOML > 既定）。"""
from __future__ import annotations

import argparse
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import __version__
from .config import Config, default_config, from_dict
from .core import run
from .paths import resolve_no_follow
from .progress import ProgressLogger

_EXIT_FATAL = 1
_EXIT_PARTIAL = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repack-tool",
        description="圧縮ファイルを解凍し、フォルダ毎にzip再圧縮するツール。",
        epilog="終了コード: 0=全成功 / 2=一部スキップ・失敗 / 1=致命的エラー")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    p.add_argument("--input", required=True, help="入力フォルダ（必須）")
    p.add_argument("--output", required=True, help="出力フォルダ（必須）")

    p.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=None,
                   help="再帰探索（既定: ON）")
    p.add_argument("--password-list", default=None, metavar="PATH", help="パスワード辞書")
    p.add_argument("--encoding", default=None, help="辞書エンコーディング（既定: utf-8）")
    p.add_argument("--compression-level", type=int, default=None, choices=range(0, 10),
                   help="zip圧縮レベル 0-9（既定: 9=最高圧縮）")
    p.add_argument("--seven-zip-path", default=None, metavar="PATH", help="7z.exe指定")
    p.add_argument("--prefer-7z", action=argparse.BooleanOptionalAction, default=None,
                   help="7z.exeを優先（既定: lib優先）")
    p.add_argument("--dry-run", action="store_true", help="対象一覧のみ表示")
    p.add_argument("--keep-temp", action="store_true", help="一時フォルダを残す")
    p.add_argument("--flat", action="store_true", help="ミラーを作らない平坦出力")
    p.add_argument("--allow-output-inside-input", action="store_true",
                   help="出力が入力配下にあることを許可")
    p.add_argument("--nested-depth", type=int, default=None, choices=range(0, 10),
                   help="入れ子解凍の深さ上限（既定: 3）")
    p.add_argument("--max-extract-mb", type=int, default=None, help="解凍サイズ上限MB(0=無制限)")
    p.add_argument("--exclude-pattern", default=None, help="除外正規表現")
    p.add_argument("--log-file", default=None, metavar="PATH", help="ログファイル")
    p.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="ログレベル")
    p.add_argument("--config", default=None, metavar="PATH", help="TOML設定ファイル")
    return p


def _load_toml(path: Optional[str]) -> dict:
    if not path:
        return {}
    pp = Path(path)
    if not pp.is_file():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {pp}")
    with pp.open("rb") as f:
        data = tomllib.load(f)
    return data.get("repack", data)


def _merge(args: argparse.Namespace, cfg: "Config") -> "Config":
    """CLI引数（None以外）を Config へ反映。既にTOML/既定が入っている。"""
    m = {
        "input_dir": ("input", Path), "output_dir": ("output", Path),
        "recursive": ("recursive", None), "compression_level": ("compression_level", None),
        "nested_depth": ("nested_depth", None), "max_extract_mb": ("max_extract_mb", None),
        "log_level": ("log_level", None),
        "password_list": ("password_list", lambda v: Path(v) if v else None),
        "seven_zip_path": ("seven_zip_path", lambda v: Path(v) if v else None),
        "log_file": ("log_file", lambda v: Path(v) if v else None),
        "encoding": ("encoding", None), "exclude_pattern": ("exclude_pattern", None),
        "prefer_7z": ("prefer_7z", None),
    }
    for field_, (arg, conv) in m.items():
        val = getattr(args, arg, None)
        if conv and val is not None:
            val = conv(val)
        if val is not None:
            setattr(cfg, field_, val)
    for flag in ("dry_run", "keep_temp", "flat", "allow_output_inside_input"):
        val = getattr(args, flag, False)
        if val:
            setattr(cfg, flag, True)
    return cfg


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        toml_data = _load_toml(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"設定ファイル読込エラー: {exc}", file=sys.stderr)
        return _EXIT_FATAL

    cfg = default_config()
    if toml_data:
        cfg = from_dict(toml_data)
    cfg = _merge(args, cfg)

    # ログファイル既定: 出力直下 repack_YYYYMMDD-HHMMSS.log（Q44）
    if getattr(args, "log_file", None) is None and cfg.log_file is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        cfg.log_file = cfg.output_dir / f"repack_{ts}.log"

    cfg.input_dir = resolve_no_follow(cfg.input_dir)
    cfg.output_dir = resolve_no_follow(cfg.output_dir)

    logger = ProgressLogger(log_level=cfg.log_level, log_file=cfg.log_file)
    try:
        return run(cfg, logger)
    except KeyboardInterrupt:
        logger.warning("中断されました (Ctrl+C)")
        return 130


def console_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    console_main()
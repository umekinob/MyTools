"""asset_tool CLI（設計書 6.5・8章）。argparse + TOML（[asset] セクション）。

優先順: CLI > TOML > 既定。終了コード: 0=全成功 / 2=一部スキップ・失敗 /
1=致命的エラー / 130=中断。
"""
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
from mytools_common.paths import resolve_no_follow
from mytools_common.logging import ProgressLogger

_EXIT_FATAL = 1
_EXIT_PARTIAL = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="asset-tool",
        description="指定フォルダを走査し、全階層フォルダを1行として資産台帳を出力する。",
        epilog="終了コード: 0=全成功 / 2=一部スキップ・失敗 / 1=致命的エラー")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    p.add_argument("--input", required=True, help="起点フォルダ（必須）")
    p.add_argument("--output", required=True, metavar="OUT_DIR",
                   help="出力フォルダ（必須・ファイル指定不可・Q33=B）")

    p.add_argument("--format", default=None, choices=["csv", "html", "md"],
                   help="出力形式（既定: csv・Q5=A）")
    p.add_argument("--sort", default=None,
                   choices=["name", "size", "mtime", "files"],
                   help="ソートキー（size/mtime/files は配下基準・Q29-12）")
    p.add_argument("--order", default=None, choices=["asc", "desc"],
                   help="ソート順（同値時は相対パス昇順・Q50=A）")
    p.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=None,
                   help="ON=全階層 / OFF=起点直下のみ（既定: ON・Q29-9）")
    p.add_argument("--with-hash", dest="with_hash", action="store_true",
                   help="詳細一覧に SHA-256 を追加（既定: OFF・Q8=A）")
    p.add_argument("--detail", action="store_true",
                   help="ファイル単位の一覧を別出力（Q26=A）")
    p.add_argument("--exclude-pattern", default=None, help="除外正規表現（部分木枝刈り・Q29-6）")
    p.add_argument("--log-file", default=None, metavar="PATH",
                   help="ログファイル（既定: 出力フォルダ直下 asset_YYYYMMDD-HHMMSS.log）")
    p.add_argument("--log-level", default=None,
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="ログレベル")
    p.add_argument("--dry-run", action="store_true",
                   help="走査と集計のみ・ファイル出力なし（Q35=A）")
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
    return data.get("asset", data)


def _merge(args: argparse.Namespace, cfg: Config) -> Config:
    """CLI引数（None以外）を Config へ反映。"""
    if args.input:
        cfg.input_dir = Path(args.input)
    if args.output:
        cfg.output_dir = Path(args.output)
    for arg in ("format", "sort", "order", "recursive",
                "exclude_pattern", "log_level"):
        val = getattr(args, arg, None)
        if val is not None:
            setattr(cfg, arg, val)
    if getattr(args, "log_file", None):
        cfg.log_file = Path(args.log_file)
    for flag in ("with_hash", "detail", "dry_run"):
        if getattr(args, flag, False):
            setattr(cfg, flag, True)
    return cfg


def validate_output(out_dir: Path) -> Optional[str]:
    """--output はフォルダ指定のみ（Q33=B）。違反時はエラー文言を返す。"""
    if out_dir.is_file():
        return f"出力にはフォルダを指定してください（ファイルは指定できません）: {out_dir}"
    if out_dir.suffix and not out_dir.exists():
        return f"拡張子付きの指定はファイルとみなします: {out_dir}"
    return None


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

    # --output はフォルダのみ（Q33=B）
    err = validate_output(cfg.output_dir)
    if err:
        print(f"出力指定エラー: {err}", file=sys.stderr)
        return _EXIT_FATAL

    # 入力フォルダの存在確認
    if not cfg.input_dir.is_dir():
        print(f"入力フォルダが見つかりません: {cfg.input_dir}", file=sys.stderr)
        return _EXIT_FATAL

    # ログファイル既定: 出力直下 asset_YYYYMMDD-HHMMSS.log（Q44=A）
    if getattr(args, "log_file", None) is None and cfg.log_file is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        cfg.log_file = cfg.output_dir / f"asset_{ts}.log"

    cfg.input_dir = resolve_no_follow(cfg.input_dir)
    cfg.output_dir = resolve_no_follow(cfg.output_dir)

    logger = ProgressLogger(log_level=cfg.log_level, log_file=cfg.log_file,
                            logger_name="mytools.asset")
    try:
        return run(cfg, logger)
    except KeyboardInterrupt:
        logger.warning("中断されました (Ctrl+C)")
        return 130
    finally:
        logger.close_all()  # Windows のファイルロック解放（テスト・後続処理向け）


def console_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    console_main()
"""機能選択・起動用CLI（将来拡張。Q23=Aによりサブパーサは不採用）。"""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="suite_top", description="作業効率化ツール スイート")
    parser.add_argument("--version", action="version",
                        version="suite_top 0.1.0")
    parser.parse_args()
    # 機能起動はGUI（python -m suite_top）を正式手順とする
    from .gui_top import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
"""python -m suite_top のエントリ。

- 引数なし → TOP画面（GUI）を起動
- --help / --version → cli_top の argparse で処理して終了
"""
from .cli_top import main

if __name__ == "__main__":
    main()
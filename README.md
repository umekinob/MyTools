# repack-tool

圧縮ファイル（7z / zip / rar / tar系など）を解凍し、フォルダが分かれていれば
**フォルダ毎に再びzip圧縮する**処理ツール。設計書: `docs/archive-repack-tool-design.md`

## 要件

- Python 3.11 以上（標準ライブラリのみで動作）
- 7z/rar は `7-Zip`（`7z.exe`）があれば処理可能（任意。無ければ 7z/rar はスキップ）
  - 任意依存: `py7zr`, `rarfile`, `tqdm` を入れると lib 経路が拡張される

## 実行

```bash
cd c:\Dドライブ\AI_Models\MyTools
$env:PYTHONPATH = "src"
python -m repack_tool --input ./in --output ./out --recursive \
  --password-list ./passwords.txt --log-file ./logs/repack.log
```

主なオプション（詳細は `python -m repack_tool --help`）:

| オプション | 既定 | 説明 |
|------------|------|------|
| `--input/--output` | 必須 | 入力・出力フォルダ |
| `--recursive/--no-recursive` | ON | 再帰探索 |
| `--password-list` | なし | UTF-8 1行1件、`#` はコメント、上限1万行 |
| `--compression-level 0-9` | 9 | zip圧縮レベル（最高圧縮） |
| `--seven-zip-path/--prefer-7z` | 自動検出/lib優先 | 7z.exe 指定・優先切替 |
| `--dry-run/--keep-temp/--flat` | OFF | 予測のみ/一時保持/平坦出力 |
| `--allow-output-inside-input` | OFF | 出力が入力配下のとき明示許可 |
| `--nested-depth 0-9` | 3 | 入れ子解凍上限 |
| `--max-extract-mb / --max-compression-ratio` | 0=OFF | Zip爆弾警告用 |
| `--exclude-pattern REGEX` | なし | 除外正規表現 |
| `--config PATH` | なし | TOML設定（`--input/--output` はCLIが必須のため上書） |
| `--log-file / --log-level` | out配下自動名/INFO | ファイル＋コンソール出力 |

終了コード: 0=全成功 / 2=一部スキップ・失敗 / 1=致命的エラー / 130=中断

## 設定ファイル（TOML例）

```toml
[repack]
input = "./in"
output = "./out"
recursive = true
password_list = "./passwords.txt"
compression_level = 9
nested_depth = 3
log_level = "INFO"
```

CLI引数が TOML より優先されます。

## ルール概要

- 単一フォルダ→そのまま1zip、複数→フォルダ毎分割、混在→フォルダ毎＋直下ファイル群の1zip
- 出力は `out/<入力相対親>/<アーカイブ名>/` 配下にミラー（`--flat` で平坦）
- 同名は `_001/_002...` 連番で別名保存（上書き禁止）
- 空フォルダはスキップ。元圧縮は削除しない。一時フォルダは処理後削除（`--keep-temp` を除く）
- 日本語・ロングパス対応。タイムスタンプは保持しない（1980以前は1980-01-01に丸め）
- 機密らしき名前は警告のみ（`--exclude-pattern` で除外可）
- 再現性: 走査順は相対パス昇順、辞書は行順厳守、ログにパスワードは出さない

## 検証手順

```bash
# 1. サンプル21件を生成（7z.exe があれば全パターン）
python tests/make_samples.py
# 2. 本実行（辞書 secret を含む）
$env:PYTHONPATH = "src"
python -m repack_tool --input tests/data/in --output tests/data/out \
  --password-list tests/data/dict.txt
# 期待: success=17(skip: 空/PW不一致/欠巻/破損=4), fail=0, exit=2
# 3. 単体＋統合
python tests/test_scanner.py
python tests/test_passwords.py
python tests/test_paths.py
python tests/test_integration.py
```

## GUI（後付け・実装済み）

CLI/Core を import する薄ラッパー（tkinter）。GUI相当の全設定＋プログレスバー。
`run(config, logger, progress_callback)` が進捗コールバック（current/total/message）に対応済み。

```bash
$env:PYTHONPATH = "src"
python -m repack_tool.gui
```

ドラッグ＆ドロップは任意依存 `tkinterdnd2` 導入時のみ有効、無ければファイル選択ダイアログのみで動作する（Q48）。
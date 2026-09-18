# MyTools（作業効率化ツール群）

日常のファイル管理作業を自動化する Python 製デスクトップツール群（スイート）。

| 機能 | 概要 | CLI | GUI |
|---|---|---|---|
| スイートTOP | 機能一覧から各ツールを別窓起動 | `python -m suite_top` | `python -m suite_top` |
| **repack-tool** | 圧縮ファイル解凍 → フォルダ毎に zip 再圧縮 | `python -m repack_tool` | `python -m repack_tool.gui` |
| **asset-tool** | フォルダ資産の台帳を CSV/HTML/MD 出力（読み取り専用） | `python -m asset_tool` | `python -m asset_tool.gui` |

- repack 設計書: `docs/archive-repack-tool-design.md`
- スイート化設計書: `docs/work-efficiency-suite-design.md`（Q1〜Q52 確定・ブロッカー0）
- GUI マニュアル: `docs/gui_manual.html`

## 要件

- Windows 10/11 + Python 3.11 以上（標準ライブラリのみで動作）
- repack: 7z/rar は `7-Zip`（`7z.exe`）があれば処理可能（任意。無ければスキップ継続）
  - 任意依存: `py7zr`, `rarfile`, `tqdm`（repack の lib 経路拡張）
  - 任意依存: `tkinterdnd2`（GUI のドラッグ＆ドロップ）

## 実行

```powershell
cd c:\Dドライブ\AI_Models\MyTools
$env:PYTHONPATH = "src"
python -m suite_top                 # スイートTOP（各機能を別窓起動）
python -m repack_tool.gui           # repack GUI 直接起動
python -m asset_tool.gui            # asset GUI 直接起動
```

CLI の正式手順は `PYTHONPATH=src` ＋ `python -m`（`[project.scripts]` は不使用・Q25=A）。

## asset-tool（資産一覧出力）

指定フォルダを**読み取り専用**で走査し、**全階層のフォルダを 1 フォルダ 1 行**（Q29=C）で
11 列の資産台帳を出力します。

```powershell
python -m asset_tool --input D:\資産 --output D:\資産台帳 --format csv
```

主なオプション（詳細は `python -m asset_tool --help`）:

| オプション | 既定 | 説明 |
|---|---|---|
| `--input/--output` | 必須 | 起点フォルダ／出力**フォルダ**（ファイル指定は不可・Q33=B） |
| `--format` | `csv` | `csv` / `html` / `md`（Q5=A） |
| `--sort` / `--order` | `name` / `asc` | `name`・`size`・`mtime`・`files`（size等は配下基準・Q29-12） |
| `--recursive` | ON | ON=全階層 / OFF=起点直下のみ（Q29-9） |
| `--with-hash` | OFF | 詳細一覧に SHA-256 を追加（重複検出の材料・Q8=A） |
| `--detail` | OFF | ファイル単位の一覧を別出力（Q26=A） |
| `--exclude-pattern` | なし | 除外正規表現（一致フォルダは部分木枝刈り・Q29-6） |
| `--log-file / --log-level` | out配下 `asset_*.log` / INFO | ログ（Q44=A） |
| `--dry-run` | OFF | 走査と集計のみ・ファイル出力なし（Q35=A） |
| `--config` | なし | TOML設定（`[asset]` セクション） |

- 出力名: `asset_YYYYMMDD.csv`（同日は `_01` 連番・Q18=A）。CSV は UTF-8 BOM付き/CRLF（Q37=A）
- 列: 保管フォルダ／フォルダ名／深さ／ファイル数(直下)／サイズ(直下)byte／サイズ(直下)表示／
  ファイル数(配下)／サイズ(配下)byte／サイズ(配下)表示／最新更新日時(配下最大)／備考（11列・Q13=A'）
- 合計行は独立計算（直下系合計・`フォルダ数 N`・配下系は二重計上回避で空欄・Q29-10）
- 空フォルダは 0 件行・起点直下ファイルは `(ルート)` 行（Q15=A・Q28=A）
- 除外: repack 既定＋OS システム項目（`$RECYCLE.BIN` 等・隠し属性）（Q31=A）
- リンク（ジャンクション/シンボリック）は非追跡・親行備考に集約（Q29-7）
- 読取エラーは統計空欄＋備考集約で継続・終了コード 2（Q17=A・Q29-16）
- 性能目安: **10万フォルダ / CSV 10万行**を想定（100万行超で WARN・Q29-8/Q29-14）

終了コード（repack と同一体系）: 0=全成功 / 2=一部スキップ・失敗 / 1=致命的エラー / 130=中断

## repack-tool

圧縮ファイル（7z / zip / rar / tar系など）を解凍し、フォルダが分かれていれば
**フォルダ毎に再びzip圧縮する**処理ツール。

```powershell
python -m repack_tool --input ./in --output ./out --recursive `
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
| `--config PATH` | なし | TOML設定（`[repack]` セクション） |
| `--log-file / --log-level` | out配下自動名/INFO | ファイル＋コンソール出力 |

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

[asset]
format = "csv"
sort = "name"
order = "asc"
recursive = true
```

CLI引数が TOML より優先されます（優先順: CLI > TOML > 既定）。

## ルール概要（repack）

- 単一フォルダ→そのまま1zip、複数→フォルダ毎分割、混在→フォルダ毎＋直下ファイル群の1zip
- 出力は `out/<入力相対親>/<アーカイブ名>/` 配下にミラー（`--flat` で平坦）
- 同名は `_001/_002...` 連番で別名保存（上書き禁止）
- 空フォルダはスキップ。元圧縮は削除しない。一時フォルダは処理後削除（`--keep-temp` を除く）
- 日本語・ロングパス対応。タイムスタンプは保持しない（1980以前は1980-01-01に丸め）
- 機密らしき名前は警告のみ（`--exclude-pattern` で除外可）
- 再現性: 走査順は相対パス昇順、辞書は行順厳守、ログにパスワードは出さない

## 検証手順

```powershell
# 1. repack サンプル21件を生成（7z.exe があれば全パターン）
python tests/make_samples.py
# 2. repack 本実行（辞書 secret を含む）
$env:PYTHONPATH = "src"
python -m repack_tool --input tests/data/in --output tests/data/out `
  --password-list tests/data/dict.txt
# 期待: success=17(skip: 空/PW不一致/欠巻/破損=4), fail=0, exit=2
# 3. asset サンプル生成（日本語名・空フォルダ・深い階層・リンク等・Q51=A）
python tests/make_asset_samples.py
# 4. asset 本実行
python -m asset_tool --input tests/data/asset_in --output tests/data/asset_out
# 5. 単体＋統合（全部）
python tests/test_scanner.py
python tests/test_passwords.py
python tests/test_paths.py
python tests/test_names.py
python tests/test_dry_run.py
python tests/test_scan_parity.py
python tests/test_suite_top.py
python tests/test_asset_core.py
python tests/test_asset_output.py
python tests/test_asset_cli.py
python tests/test_asset_integration.py
python tests/test_integration.py
```

### 検証レポート（自動生成）

`python tests/make_report.py` でサンプル生成→E2E→全テストを一括実行し、
`result/result_yyyymmdd.html`（同日複数回は `result_yyyymmdd_01.html` の連番）に
HTMLレポートを保存します。内容: 総合PASS/FAIL、コミット情報、repack E2Eチェック詳細、
単体テスト結果（repack＋スイート＋asset）、T01〜T22対応表、実行ログ（パスワード非出力）。

## GUI

CLI/Core を import する薄ラッパー（tkinter）。`run(config, logger, progress_callback)` の
進捗コールバック（current/total/message）に対応済み。

```powershell
$env:PYTHONPATH = "src"
python -m suite_top        # スイートTOP（推奨・各機能へ別窓起動）
python -m repack_tool.gui  # repack GUI 単体起動
python -m asset_tool.gui   # asset GUI 単体起動
```

- スイートTOP は各機能を**サブプロセスで別窓起動**（TOP 終了時は子窓も終了・Q48=A）
- 走査はファイル数ベースのため asset の進捗バーは不定（indeterminate）表示（Q46=A）
- ドラッグ＆ドロップは任意依存 `tkinterdnd2` 導入時のみ有効、無ければダイアログのみで動作
- 詳細な操作手順は `docs/gui_manual.html` を参照
- TOP→子窓の起動検証: `tests/verify_suite_spawn.py`（「実GUI別窓起動の確認」参照）

### 実GUI別窓起動の確認（手動検証）

自動テストはモックによるロジック検証のため、実際に子窓が表示されるかは
次のスクリプトで確認します（実プロセスを起動し、検証後に終了します）。

```powershell
$env:PYTHONPATH = "src"
python tests/verify_suite_spawn.py
```

検証項目（結果は標準出力と `verify_result.txt`）:

1. repack ボタン → `python -m repack_tool.gui` の別窓が表示される
2. 起動中に再度押しても二重起動しない（`起動済み` の案内のみ）
3. asset ボタン → `python -m asset_tool.gui` の別窓が表示される
4. TOP の×ボタン終了（`_on_close`）で子窓も終了する（Q48=A）

確認用のモーダルダイアログ（`起動済み`・終了確認）は監視スレッドが自動処理します。
全体の上限は 120 秒で、超えた場合は `RESULT=FAIL` で終了します。

ウィンドウを表示できない環境では `RESULT=FAIL` になります。
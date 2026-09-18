# 技術コンテキスト（Tech Context）

## 実行環境
- OS: Windows 10/11（環境: win32 / VS Code / PowerShell）
- Python: 3.12.10 実測（`pyproject.toml` は `requires-python >= 3.11`）
- 作業ディレクトリ: `c:\Dドライブ\AI_Models\MyTools`
- Python 3.11 以上。**基本は標準ライブラリのみで動作**（dependencies 空）

## 依存関係
### 任意依存（optional-dependencies `full`）
- `py7zr>=0.22.0`: .7z を 7z.exe 無しで扱う場合
- `rarfile>=4.1`, `tqdm>=4.66.0`
- `tkinterdnd2`: GUI のドラッグ＆ドロップ（無ければダイアログのみで動作）
### 開発用（`test`）
- `pytest>=7.0`
### 外部ツール
- 7-Zip (`7z.exe`): 検出順は PATH → `C:\Program Files\7-Zip\7z.exe` → `--seven-zip-path`。
  無ければ 7z/rar はスキップ継続

## 主要コマンド
```powershell
# 実行（PYTHONPATH=src + python -m が正式手順）
$env:PYTHONPATH = "src"
python -m repack_tool --input ./in --output ./out --recursive `
  --password-list ./passwords.txt --log-file ./logs/repack.log
python -m repack_tool.gui

# サンプル生成 → 本実行検証（tests/data/in に 7z.exe で全パターン生成）
python tests/make_samples.py
python -m repack_tool --input tests/data/in --output tests/data/out `
  --password-list tests/data/dict.txt
# 期待値: success=17(skip 4), fail=0, exit=2

# 単体/統合テスト（tests 配下の python スクリプト直実行方式）
python tests/test_scanner.py
python tests/test_passwords.py
python tests/test_paths.py
python tests/test_integration.py
python tests/test_names.py
python tests/test_dry_run.py
python tests/test_scan_parity.py      # repack/common 除外述語の一致性（Q30=A）
python tests/test_suite_top.py        # TOP 画面・CLI エントリ・GUI import スモーク
python tests/test_asset_cli.py        # asset CLI 引数・設定・出力検証
python tests/test_asset_core.py       # asset 走査・11列集約・合計行
python tests/test_asset_output.py     # CSV/HTML/MD 出力・tmp→replace
python tests/test_asset_integration.py  # asset CLI サブプロセス E2E

# 実 GUI 別窓起動の手動検証（TOP→repack/asset の実起動・連動終了。結果 verify_result.txt）
python tests/verify_suite_spawn.py

# スイート（Phase 3/4・2026-09-18 実装済み）
python -m suite_top                   # TOP 画面（GUI）
python -m suite_top --version         # argparse 処理（GUI は起動しない）
python -m asset_tool --input tests/data/asset_in --output ./out
python tests/make_asset_samples.py    # asset 用サンプル生成（tests/data/asset_in）

# HTML レポート一括生成（サンプル→E2E→単体テスト → result/result_yyyymmdd.html）
python tests/make_report.py
```
- pytest 設定あり（`[tool.pytest.ini_options] testpaths = ["tests"]`）。
  テストスクリプトは `python tests/test_*.py` 直実行と pytest 両方の併存
- GUI マニュアルのスクリーンショット: `tests/shoot_manual.py` → `docs/img/`
- 実 GUI 別窓起動の手動検証: `tests/verify_suite_spawn.py` →
  `verify_result.txt`（実プロセス起動・`RESULT=PASS/FAIL`）。
  `messagebox` はモーダルのため監視スレッドで自動処理・全体 120 秒の watchdog 付き

## パッケージ/ビルド
- setuptools（`[build-system] requires = ["setuptools>=68"]`）
- 配布名 `mytools` / version 0.1.0（旧 `repack-tool` から変更済み・Q24=A）
- `[tool.setuptools.packages.find] where = ["src"]`
- `[project.scripts]` は存在しない・追加もしない（Q25=A）

## 技術的制約・考慮事項
- **Windows ファイルシステム固有の考慮**: ロングパス（`\\?\` 接頭辞）対応、
  隠し属性（HIDDEN）除外、`\\` やドット始まり名の扱い、タイムスタンプ 1980-01-01 丸め
- **日本語**: ファイル名文字化けの自動復元（`names.py`）、辞書は行順厳守
- **セキュリティ**: zip 爆弾警告（`--max-extract-mb`/`--max-compression-ratio`、既定 OFF）、
  機密名は警告のみ。ログにパスワード非出力。Zip64=allow
- **逐次処理**（並列化は非目的 Q31）、timeout なし（終わるまで待つ Q43）
- **.gitignore**: `tests/data/in/`, `tests/data/out*/`, `tests/data/asset_in/`,
  `tests/data/asset_out*/`, `result/`, `tmp/`, `*.log`, `shoot_result.txt`,
  `verify_result.txt`, `passwords.txt`, `dict.txt`, `*.7z*`, `*.rar` 等を除外
  （実データ・機密はコミットしない）

## 開発運用
- コミットは指示者確認後に実行。push は指示後。コミットメッセージは
  `feat:/fix:/docs: 等 + 日本語 + 絵文字` の慣行（例: `feat: ... 🚀`）
- 開発モード: PM（要件）→ Architect（設計）→ Code（実装・テスト）→ PMO（品質確認）
- 要件は設計書の Q&A トレーサビリティ（Q1〜Q52）で管理。新しい判断は設計書へ反映

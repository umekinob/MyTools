# 現在の作業コンテキスト（Active Context）

- 最終更新: 2026-09-18
- 最新コミット: `a2801b8` (HEAD -> master, origin/master)
- 本セッション: **スイート化 Phase 1〜4 を実装完了**（Phase 3 asset 本体＋Phase 4 ドキュメント/E2E）。
  指示（「コミットせずに Phase 3 と 4 を進める」）によりコミットは未実施

## 現在の焦点
スイート化実装は **Phase 1〜4 完了**（設計書10章どおり・2026-09-18）。
- **Phase 1-1 完了**: `src/suite_top/`（`__init__`/`__main__`/`gui_top.py`/`cli_top.py`）新設。
  TOP画面 `SuiteApp(tk.Tk)` は機能一覧＋「開く」＋バージョン＋ヘルプ。
  repack GUI は Q1=B を守るため**サブプロセス（`python -m repack_tool.gui`）別窓起動**とした。
  同一機能は起動済みなら再起動しない。TOP終了時に子窓を terminate（Q48=A）。
  asset は Phase 3 で `asset_tool.gui` 起動へ接続済み（「準備中」ダイアログは解消）。
  `pyproject.toml` の name を `mytools` へ変更（Q24=A）。
  `python -m suite_top` は `cli_top.main()` 経由（`--help`/`--version` は argparse 処理、
  引数なしで GUI 起動）。**GUI 直呼びだと `--help` が GUI 起動でブロックする**回帰を
  `test_cli_help_exits_without_gui` で防止。
- **Phase 1-2 完了**: `src/mytools_common/`（`__init__`/`logging.py`/`paths.py`/`scan.py`）新設。
  - `logging.py`: repack `progress.py` の複写。logger名引数化（既定 `mytools.repack`・Q43=A）、
    初期化時に当該loggerの既存ハンドラ全除去
  - `paths.py`: repack `paths.py` の複写
  - `scan.py`: 除外述語 `is_excluded(..., include_os_system)`＋`is_hidden`。
    OSシステム項目（`$RECYCLE.BIN`等・Q31=A）は `include_os_system=True` 時のみ
- **Phase 2-1 完了**: `src/asset_tool/`（`__init__`/`__main__`/`config.py`/`cli.py`/`core.py`）新設。
  CLI は 6.5 オプション表どおり（`--input/--output/--format/--sort/--order/
  --recursive|--no-recursive/--with-hash/--detail/--exclude-pattern/--log-file/--log-level/
  --dry-run/--config`）。TOML は `[asset]` セクション（Q33=B）。
  `--output` はフォルダ検証 `validate_output()`（ファイル・拡張子付きは exit 1）。
  ログ既定 `asset_YYYYMMDD-HHMMSS.log`（出力フォルダ直下・Q44=A）。
  ロガー名 `mytools.asset`。`core.run()` は Phase 3 で実装済み（スタブ解消）。
  **main は finally で `logger.close_all()`**（Windows のログファイルロック解放）。
- **Phase 2-2 完了**: 旧エントリ `python -m repack_tool --version`（repack-tool 0.1.0）と
  `--help`（exit 0）を確認。既存テスト全緑で互換維持を担保
- **Phase 3 完了（2026-09-18）**: asset 機能本体を実装。
  - `core.py`: `os.scandir` 反復＋明示スタックで全階層走査（`RecursionError` 回避）。
    除外は部分木枝刈り、ディレクトリリンクはスキップ集約、読取エラーは統計 None
    （空欄）＋備考集約で継続し exit 2。11 列 `Row`／`compute_total`（直下系合計＋
    `フォルダ数 N`・配下系は空欄）／`(ルート)` 疑似行（Q28=A）／ソート Q50=A
  - `writers.py`: CSV（UTF-8 BOM・CRLF・11列）／HTML（CSS 埋込）／MD（GFM）＋詳細一覧
    （5列・`--with-hash` で SHA-256）。`.tmp` 逐次書き込み＋完了時 `os.replace`（Q47=A）
  - `gui.py`: `AssetApp(tk.Tk)`（repack 流儀・queue+thread・indeterminate 進捗 Q46=A）
  - `suite_top/gui_top.py`: asset ボタンを実起動へ接続
- **Phase 4 完了（2026-09-18）**: `docs/gui_manual.html` 章9（スイートTOP）・章10（asset）追補＋
  目次/ヘッダ更新／`docs/img/10_suite_top.png`・`11_asset_startup.png`・
  `12_asset_configured.png` を `tests/shoot_manual.py` の `shoot_suite()` で生成／
  `README.md` 全面更新（スイート表・asset 節・検証手順に `test_names`/`test_dry_run` 追記）／
  `tests/make_asset_samples.py`（Q51=A）・`tests/test_asset_*.py` 追加／
  `.gitignore` に asset サンプル出力と `shoot_result.txt` を追加／
  `tests/make_report.py` の対象に asset/suite テストを追加
- **テスト**: 最終的に **12 ファイル全て exit=0**。新設は
  `tests/test_suite_top.py`（6件）・`tests/test_scan_parity.py`（5件）・
  `tests/test_asset_cli.py`（12件）・`tests/test_asset_core.py`・
  `tests/test_asset_output.py`・`tests/test_asset_integration.py`（CLI E2E・tempfile）
- **Phase 4 追加**: 実 GUI の別窓起動を検証する手動スクリプト
  `tests/verify_suite_spawn.py` を追加（pytest 対象外）。実行結果は **RESULT=PASS**
  （`verify_result.txt` は `.gitignore` 済み）

## 次に行う作業（スイート化 Phase 1〜4 完了後）
1. **実装分のコミット**（指示確認後。分割案: TOP画面／共通基盤／asset CLI／asset 本体／
   ドキュメント・E2E）
2. 拡張候補（設計書12章）: `--no-empty`・`--rollup`・重複検出（ハッシュ活用）・
   GUI の TOML 対応
3. 読取エラーの実環境再現（`icacls` 等でのアクセス拒否）は未実施（例外注入テストは実装済み）

### 完了済み（2026-09-18 最終）
- [x] 実 GUI 別窓起動の検証: `tests/verify_suite_spawn.py` で **実プロセス検証 RESULT=PASS**
      （repack/asset の別窓表示・二重起動なし・`_on_close` で子窓連動終了）
- [x] `tests/make_report.py` によるレポート生成: `result/result_20260918.html` **overall=PASS**

## 未検証事項・確認が必要な点
- **一時展開先の記載差異**: 設計書は「OS標準temp（Q19）」だが、コミット `d120508`
  で「プログラムの tmp フォルダ」に変更した経緯。tmp 生成は repack の core 側にある
  （paths.py には無い）。asset の出力（`.tmp`＋`os.replace`）は本仕様どおり実装
- `.clinerules` が git 上で削除扱い（` D .clinerules`）のまま。要指示者判断
- `memory-bank/` 未追跡・`docs/img/run_00..09.png` の追跡範囲は要指示者判断

## 実 GUI 検証の知見（tests/verify_suite_spawn.py）
- `messagebox` はモーダルでブロックするため、**同一スレッドからは閉じられない**。
  監視スレッド（`start_dialog_watcher`）から `WM_CLOSE`／`WM_COMMAND IDOK` を送る
- 全体に watchdog（120 秒）を設け、ハング時も `RESULT=FAIL` を残して終了する

## 重要なパターン・方針（決定済み）
- 実行手順は `PYTHONPATH=src` ＋ `python -m`（`[project.scripts]` は作らない Q25=A）
- repack 側のオプション名・既定値・エントリは一切変更しない（Q11=A・Q1=B）
- 共通部品は「複写」であり移動ではない（差分検知テストでドリフト防止 Q30=A）
- TOP→機能起動は**サブプロセス方式**（GuiApp 無変更の制約上の採用。Q48の窓管理は
  「起動済みなら再起動しない＋TOP終了時に terminate」で近似）
- asset CLI のログハンドラは finally で close_all（Windows ロック対策）
- GUI 起動を伴うエントリの `__main__.py` は必ず cli_* の argparse を経由させる
  （`--help` が GUI を起動してブロックしないため）
- コミットは確認後のみ、push は指示後、秘密情報はコミット禁止

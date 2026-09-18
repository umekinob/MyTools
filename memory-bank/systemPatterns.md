# システムパターン（System Patterns）

## 現行アーキテクチャ（実装済み: repack-tool）

```text
python -m repack_tool  →  cli.console_main (argparse + TOMLマージ)
python -m repack_tool.gui  →  GuiApp(tk.Tk) (queue + thread)
        └── core.run(cfg, logger, progress_callback)
              ├─ Scanner   再帰探索・分割判定
              ├─ Checker   分割/破損の事前チェック
              ├─ Extractor 整合性検査+解凍
              ├─ Classifier トップレベル分類（単一/複数/混在/ファイルのみ）
              └─ Repacker  フォルダ毎zip化・ミラー出力
                    ├─ Python libs (py7zr/zipfile/tarfile/gzip/bz2/lzma)
                    └─ 7z.exe fallback (rar保険)

エンジン検出順: PATH → C:\Program Files\7-Zip\7z.exe → --seven-zip-path
```

### モジュール構成（src/repack_tool/）
| ファイル | 責務 |
|---|---|
| `cli.py` | argparse・TOML マージ・run() 呼び出し |
| `gui.py` | tkinter GUI。queue+thread で run() 実行、進捗バー+ログ |
| `core.py` | `run(config, logger, progress_callback)` 本体（逐次） |
| `config.py` | 設定データクラス・TOML 読み込み |
| `scanner.py` | アーカイブ走査・分割判定 |
| `checker.py` | 分割巻揃い/破損チェック |
| `extractor.py` | 解凍（lib 優先・7z.exe fallback） |
| `classifier.py` | トップレベル分類・除外判定 `_is_excluded` |
| `repacker.py` | zip 化・ミラー出力・連番衝突回避 |
| `passwords.py` | 辞書読込（UTF-8、行順厳守、#コメント、上限1万行） |
| `paths.py` | パス解決・ロングパス・日本語対応 |
| `progress.py` | ProgressLogger（console+file・進捗コールバック） |
| `names.py` | 日本語ファイル名の文字化け自動復元 |

### 確立された設計パターン
- **Core/CLI/GUI 分離**: GUI・CLI は薄ラッパー。ロジックは core に集約
- **進捗コールバック契約**: `(current, total, message)` ＋ `set_total`/`update`。
  GUI の `_GuiHandler` と互換。GUI 側は queue で受けて描画（スレッド分離）
- **スキップ継続**: 1 件失敗でも止めず次へ。終了コード 0/1/2/130 で判別
- **命名規約**: `out/<相対親>/<アーカイブ名>/<フォルダ名>.zip`。
  同名は `_001/_002…` 連番（上書き禁止・on-conflict は連番のみ固定 Q46）
- **再現性**: 走査順＝相対パス昇順、辞書＝行順厳守、ログにパスワード非出力
- **実行は `PYTHONPATH=src` ＋ `python -m`**（console_scripts 非使用）

## スイート化 アーキテクチャ（実装済み）
```text
python -m suite_top        → TOP画面 (SuiteApp(tk.Tk))
  ├─ [解凍→再圧縮] → サブプロセス `python -m repack_tool.gui` を別窓起動
  │                   （GuiApp は Tk を所有するため無変更・Q1=B）
  └─ [資産一覧出力] → サブプロセス `python -m asset_tool.gui` を別窓起動

CLI は機能ごとに独立エントリ（サブパーサ方式・互換シムは不採用 Q23=A）:
  python -m repack_tool ...   現行のまま変更なし（Q11=A）
  python -m asset_tool  ...   新規（--input/--output フォルダ/--format/--sort 等）
```

### 追加モジュール構成
| パッケージ | ファイル | 責務 |
|---|---|---|
| `suite_top/` | `__main__.py` | `cli_top.main()` 経由（`--help`/`--version` は GUI 非起動） |
| | `cli_top.py` | argparse（引数なしで GUI 起動） |
| | `gui_top.py` | `SuiteApp(tk.Tk)`・機能一覧＋「開く」＋ヘルプ。子プロセス管理（`_procs`） |
| `mytools_common/` | `logging.py` | ProgressLogger（logger 名引数化・初期化時既存ハンドラ除去 Q43=A） |
| | `paths.py` | repack paths の複写 |
| | `scan.py` | 除外述語 `is_excluded`／`is_hidden`（OS システム項目 Q31=A） |
| `asset_tool/` | `config.py` | `[asset]` TOML＋既定値・`validate_output()`（Q33=B） |
| | `cli.py` | argparse・ログ設定・`finally: logger.close_all()` |
| | `core.py` | 走査・11列集約・ソート・合計行・終了コード（Q22〜Q52） |
| | `writers.py` | CSV/HTML/MD＋詳細一覧＋`.tmp`→`os.replace`（Q47=A） |
| | `gui.py` | `AssetApp(tk.Tk)`（repack 流儀・queue+thread） |

### asset の実装パターン（core）
- 走査は `os.scandir` の**反復＋明示スタック**（再帰に依存せず深い階層で
  `RecursionError` を起こさない）。`RecursionError` 捕捉時は exit 1
- 除外は**部分木枝刈り**（除外フォルダ配下を走査しない・Q29-6）
- ディレクトリリンクは巡回スキップ＋`リンクスキップ` 備考（Q29-7・Q45=A）
- 読取エラーは該当行の統計を `None`（空欄）にし備考へ集約、全体は継続して exit 2
  （Q17=A・Q36=A）。配下統計が部分集計である旨を WARN ログへ出す
- 合計行は `compute_total` で独立計算（直下系のみ合計＋`フォルダ数 N`・
  配下系は二重計上回避のため空欄・Q29-10）
- `(ルート)` 疑似行（深さ0）が起点直下ファイルの受け皿（Q28=A）
- 安定ソート（`name`/`size`/`mtime`/`files`・Q50=A）
- 形式（CSV/HTML/MD）は行セット・ソート順が完全一致（Q29-11）

- GUI 運用: 機能ごとに窓 1 つ。TOP は起動済み機能を再起動せず、終了時に子窓を
  `terminate`（Q48=A の近似。実装はサブプロセス方式）

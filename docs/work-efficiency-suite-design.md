# 作業効率化ツール スイート化改修案（検討結果反映版）

作成日: 2026-09-14 / 更新日: 2026-09-14（Q1〜Q22 壁打ち結果を反映・全問確定）

本書は現行の「解凍→フォルダ毎zip再圧縮（repack-tool）」を
**作業効率化ツール群の1機能**と位置づけ、TOP画面から各機能へ遷移する
構成へ改修するための提案書である。
**実装は本書承認後に開始する。コード変更は本タスクでは行わない。**

---

## 1. 背景と目的

### 1.1 現状

- `src/repack_tool/` に CLI（`cli.py`）・GUI（`gui.py`）・Core（`core.py` 他）が一体で実装。
- エントリは `python -m repack_tool`（CLI）と `python -m repack_tool.gui`（GUI）。
- `pyproject.toml` の配布名も `repack-tool` 単機能が前提。

### 1.2 目的

- 本機能を壊さずに**機能追加に強いスイート構成**へ移行する。
- 第2機能「デジタル保有資産一覧出力」（指定フォルダを読み取り、サブフォルダ単位の保管ファイル＝主にzipを一覧出力）を同じ土台に載せる。
- GUIは **TOP画面 → 各機能画面** の遷移モデルに統一する。

### 1.3 非目的（今回やらないこと）

- repack機能自体の仕様変更（分類・命名・終了コード等は現行維持）。
- Web化・常駐化・DB導入。出力はファイル（CSV/HTML等）に留める。
- インストーラ化・自動更新（必要なら別案件）。

---

## 2. 用語定義

| 用語 | 意味 |
|---|---|
| スイート / Suite | 作業効率化ツール全体。TOP＋複数機能の総称 |
| 機能 / Feature | repack・資産一覧などの単位。CLIサブコマンド＋GUI画面を1セットとする |
| シェル / Shell | TOP画面・機能選択・共通設定・バージョン表示を担う枠 |
| 共通基盤 / Common | ログ・進捗・スレッド実行・ファイル選択・設定読込など横断部品 |

---

## 3. 全体像（After）

```text
起動（GUI）: python -m suite_top           → TOP画面（Q2/Q3/Q4確定）
  ├─ [解凍→再圧縮] → 既存 repack GUI を別窓で起動（現行 gui.py そのまま）
  └─ [資産一覧出力] → asset GUI を別窓で起動（新規）

起動（CLI） : python -m repack_tool ...    → 現行のまま維持（Q11=A）
              python -m asset_tool ...     → 資産一覧出力（新規）
              python -m suite_top ...      → 機能選択・起動用（将来拡張）
```

### 3.1 GUI遷移イメージ

```text
┌─────────────────────────────┐
│ 作業効率化ツール TOP         │
│  ・解凍→フォルダ毎zip [開く] │
│  ・資産一覧出力      [開く]  │
│  ・バージョン/ヘルプ        │
└──────────────┬──────────────┘
               │ Toplevelで開く（TOPは残す）
     ┌─────────┴─────────┐
     ▼                   ▼
┌───────────┐     ┌────────────┐
│ repack画面 │     │ asset画面  │
│ 実行/中止 │     │ 実行/中止  │
│ 進捗+ログ │     │ 進捗+ログ  │
└───────────┘     └────────────┘
```

- TOPは常駐し、各機能画面は `Toplevel` で開く（Q4=A: TOPは選択・起動のみ、既存GUIを別窓で開き現行操作感を維持）。
- 現行 `GuiApp(tk.Tk)` は変更せず、`suite_top/gui_top.py` の新規 `SuiteApp(tk.Tk)` から起動する。

### 3.2 CLI構成イメージ

```text
python -m repack_tool --input IN --output OUT [現行オプション...]（変更なし・Q11=A）
python -m asset_tool  --input IN --output OUT.csv [--recursive] [--format csv|html] ...
```

- `argparse` サブパーサ方式。`repack` 側の既存オプション名は一切変えない。
- 旧 `python -m repack_tool` は薄い互換シムとして残し、新 `repack` に委譲する。

---

## 4. 現行構成と変更方針

### 4.1 現行ファイル構成（要点）

```text
src/repack_tool/
  __init__.py  __main__.py   # python -m repack_tool → cli.console_main
  cli.py       # argparse単体、TOMLマージ、run()呼び出し
  gui.py       # GuiApp(tk.Tk)、queue+threadでrun()実行、進捗バー+ログ
  core.py      # run(cfg, logger, progress_callback)
  config.py checker.py extractor.py classifier.py repacker.py
  paths.py passwords.py progress.py names.py
```

### 4.2 改修方針：段階移行（Big Bangにしない）

1. **Phase 0**: 本書承認＋資産一覧の出力仕様だけ先に固める。
2. **Phase 1**: 共通基盤の切り出し（`common/`）＋ `mytools` シェル追加。repack本体は移動のみ。
3. **Phase 2**: TOP画面＋機能画面化（GUI）、サブコマンド化（CLI）。旧エントリは互換シム化。
4. **Phase 3**: 資産一覧機能の新規実装。
5. **Phase 4**: テスト・ドキュメント・リリース整理。

---

## 5. 提案する新ディレクトリ構成【確定: Q1=B・Q3=C】

- Q1回答Bにより、`mytools` パッケージ化は行わず、`src/repack_tool` ＋ `src/asset_tool` の並列＋TOP新設とする（移行工数最小）。
- Q3回答Cにより、TOP専用 `src/suite_top/` と部品専用 `src/common/` に分離する。

```text
src/
  repack_tool/                    # 現行のまま維持（Q1=B: 移設しない）
    __init__.py  __main__.py
    cli.py gui.py core.py config.py ...
  asset_tool/                     # 新規（第2機能・Q1=B）
    __init__.py __main__.py cli.py gui.py core.py config.py
  suite_top/                      # TOP専用（Q3=C: 新規）
    __init__.py __main__.py       # python -m suite_top → TOP画面
    gui_top.py                    # SuiteApp（TOP画面・Q4=A: 選択・起動のみ）
    cli_top.py                    # 機能選択・振り分け用CLI（将来拡張）
  common/                         # 部品専用（Q3=C: 新規）
    logging.py                    # ProgressLogger 移設先候補
    paths.py                      # パス解決・ロングパス
```

### 5.1 移行ルール【確定: Q1=B・Q11=A】

- `src/repack_tool/` は移動せず現行維持（Q1=B）。importパス変更なし。
- `src/asset_tool/`・`src/suite_top/`・`src/common/` を新規追加する。
- 旧エントリ `python -m repack_tool` は維持し、互換シム化は行わない（Q11=A）。
- `pyproject.toml` の `repack-tool` スクリプト登録は現行維持し、`asset-tool` を追加登録する。

---

## 6. 第2機能：デジタル保有資産一覧出力【確定: Q5=A・Q6=B・Q7=C・Q8=A・Q9=A・Q13=A・Q14=A・Q15=A・Q16=A・Q17=A・Q18=A・Q19=A・Q20=A・Q21=A・Q22=A】

- Q5回答A：出力形式は既定CSV＋任意HTML/Markdown。
- Q6回答B：1行の粒度はフォルダ集約1行（フォルダ数把握向き・詳細は別出力）。
- Q7回答C：収集対象は全ファイル（拡張子不問・汎用資産台帳）。
- Q8回答A：ハッシュは任意・既定OFF。
- Q9回答A：既存 `result_yyyymmdd` 系とは独立（`asset_YYYYMMDD` 形式・既存に影響なし）。
- Q13回答A：列はフォルダ名＋ファイル数＋合計サイズ＋最新更新日＋備考（最小集約）。
- Q14回答A：ソートはフォルダ名昇順を既定とし、後から変更可能にする。
- Q15回答A：空フォルダは件数0行として出力する。
- Q16回答A：除外条件はrepackと共通（OSゴミ・ドット＋正規表現）。
- Q17回答A：読取エラーは備考欄に記録して継続＋終了コード2（repack踏襲）。
- Q18回答A：出力名は `asset_YYYYMMDD`＋同日は`_01`連番（result系と同一則）。
- Q19回答A：集約単位は起点直下のサブフォルダ単位。
- Q20回答A：合計行あり（フォルダ数・ファイル総数・総サイズ）。
- Q21回答A：集計範囲は直下単位・中身は再帰集計。
- Q22回答A：実行ログは必要（repack踏襲：ヘッダ＋件数要約）。

> 元の要望は「主にzip」だったが、Q7回答Cにより全ファイルを対象とする汎用資産台帳に拡張する。
> Q19＋Q21の組み合わせ：起点直下の各サブフォルダを1行とし、その配下は再帰的に集計する（直下ファイルのみに限定しない）。

---

> ユーザー要望：「指定フォルダを読み取り、サブフォルダ単位で保管しているファイル（主にzip）を一覧出力」。
> 以下は**叩き台仕様**。Phase 0で確定させる。

### 6.1 機能概要【確定: Q5/Q6/Q7/Q9/Q13/Q15/Q19/Q20/Q21】

- 入力：起点フォルダ（例：`D:\資産`）。サブフォルダ直下を1単位とする。
- 収集：単位フォルダ配下の全ファイル（Q7=C）を走査。
- 出力：単位フォルダごとにフォルダ集約1行（Q6=B）でまとめ、CSV既定（Q5=A）または HTML/Markdown で出力（`asset_YYYYMMDD` 形式・Q9=A）。

### 6.2 出力項目【確定: Q6/Q13/Q15/Q20】

| 列 | 内容 | 備考 |
|---|---|---|
| 保管フォルダ | 起点直下サブフォルダ名（相対パス・Q19=A） | 一覧の主キー・ソート既定は昇順（Q14=A） |
| ファイル数 | 集約対象フォルダ配下のファイル件数（再帰集計・Q21=A、除外適用後・Q16=A） | 空フォルダは0（Q15=A） |
| 合計サイズ | バイト＋human readable | 合計行にも出力（Q20=A） |
| 最新更新日時 | 配下ファイルのmtime最大値（空フォルダは空欄） | ソート切替用（Q14=A） |
| 備考 | 読み取りエラー等（Q17=A） | エラー時は記録して継続 |

### 6.3 動作仕様【確定: Q8/Q14/Q16/Q17/Q18/Q20/Q22】

- 再帰有無・除外パターン・ログファイル・終了コード（0/2/1）・dry-run を repack と共通化。
- 除外条件はrepackと共通（Q16=A：OSゴミ・ドット＋正規表現）。
- 読取エラーは備考欄に記録して継続し、終了コード2に寄与する（Q17=A）。
- 出力名は `asset_YYYYMMDD`＋同日は`_01`連番（Q18=A・result系と同一則）。
- 末尾に合計行を出力する（Q20=A：フォルダ数・ファイル総数・総サイズ）。
- 実行ログはrepack踏襲で出力する（Q22=A：ヘッダ＋件数要約。ログ名は `asset_YYYYMMDD-HHMMSS.log` 想定）。
- ソートは `--sort name|size|mtime`＋`--order asc|desc` で切替え可能とし、既定はフォルダ名昇順（Q14=A）。
- ハッシュ計算は任意・既定OFF（Q8=A）。有効時はストリーミング計算、件数表示＋プログレスバー。
- 日本語・ロングパス対応は共通基盤に委譲。

### 6.4 未確定事項 → 確定結果（Phase 0 壁打ち Q5〜Q9・Q13〜Q22）

1. 出力形式 → **CSV既定＋HTML/Markdown任意**（Q5=A）。
2. 1行の粒度 → **フォルダ集約1行**（Q6=B）。
3. 収集対象 → **全ファイル**（Q7=C）。
4. ハッシュ → **任意・既定OFF**（Q8=A）。
5. `result_yyyymmdd` 系との関係 → **独立**（Q9=A）。
6. 列定義 → **フォルダ名＋ファイル数＋合計サイズ＋最新更新日＋備考**（Q13=A）。
7. ソート順 → **フォルダ名昇順を既定とし、後から変更可能**（Q14=A）。
8. 空フォルダ → **件数0行として出力**（Q15=A）。
9. 除外条件 → **repackと共通**（Q16=A）。
10. 読取エラー → **備考欄に記録して継続＋終了コード2**（Q17=A）。
11. 出力ファイル名 → **`asset_YYYYMMDD`＋同日は`_01`連番**（Q18=A）。
12. 集約単位 → **起点直下のサブフォルダ単位**（Q19=A）。
13. 合計行 → **あり**（Q20=A）。
14. 集計範囲 → **直下単位・中身は再帰集計**（Q21=A）。
15. 実行ログ → **必要（repack踏襲）**（Q22=A）。

### 6.5 asset CLIオプション案（Q14/Q8確定に基づく）

```text
python -m asset_tool --input IN --output OUT.csv [--recursive]
  [--format csv|html|md] [--sort name|size|mtime] [--order asc|desc]
  [--with-hash] [--exclude-pattern REGEX] [--log-file PATH] [--dry-run]
```

- `--format`：既定 `csv`（Q5=A）。
- `--sort/--order`：既定 `name/asc`（Q14=A）。
- `--with-hash`：指定時のみSHA-256列を追加（Q8=A）。
- `--recursive`：Q19=A＋Q21=Aのもとでは集計範囲の再帰有無には影響しない。将来の集計方式切替用に予約。
- 出力先が日付形式の場合は `asset_YYYYMMDD`＋連番則（Q18=A）を適用。

---

## 7. GUI設計

### 7.1 TOP画面（`suite_top/gui_top.py`・新規）【確定: Q4=A】

- タイトル：「作業効率化ツール」。機能ボタンを縦に配置（Q4=A: TOPは選択・起動のみ）。

- タイトル：「作業効率化ツール」。機能ボタンを縦に配置。
- 各機能の概要1行＋「開く」ボタン。バージョン表示・ヘルプ導線。
- 機能画面は `Toplevel` で開き、TOPを閉じたら全画面終了とする。

### 7.2 機能画面の共通化（`common/`＋各機能側・Q1=Bのため切り出し最小限）

既存 `repack_tool/gui.py` は変更しない。新規 `asset_tool/gui.py` は実行パネル等の流儀を踏襲する。

現行 `gui.py` の汎用部分を切り出す：

- `RunPanel`：実行／中止ボタン＋`ttk.Progressbar`。
- `LogView`：Text＋クリアボタン（ログファイルは消さない現行仕様を継承）。
- `run_in_thread()`：`queue + threading.Thread + after(100ms) pump` の定型化。
- ファイル／フォルダ選択行ヘルパー、DnD（tkinterdnd2任意）対応。

repack画面・asset画面は共通部品の上に「入力欄とオプション」だけを載せる。

### 7.3 同時実行ポリシー【確定: Q10=A】

- Q10回答A：**機能ごとに最大1ジョブ**（実行中はボタンdisable）。機能間の同時実行は許可する。
- 中止ボタンは現行どおり「即時killしない」注意表示を継承し、将来キャンセルフラグ対応とする。

---

## 8. CLI設計

- `suite_top/cli_top.py`：機能選択・起動用（将来拡張。Q1=Bのためサブパーサ方式は採用しない）。
- `repack_tool/cli.py`：現行のまま変更なし（Q11=A）。
- `asset_tool/cli.py`：`--input/--output/--recursive/--format/--with-hash/--log-file` 等（6章確定後に固定）。
- TOMLは機能ごとに独立セクション方式（後方互換のため既存 `[repack]` の読み方は変えない）。

---

## 9. 共通基盤の切り出し計画

| 候補 | 現行場所 | 方針 |
|---|---|---|
| 進捗・ログ | `repack_tool/progress.py` | `common/logging.py` へ複写し、repack側は現行維持（Q1=B） |
| パス解決・ロングパス | `repack_tool/paths.py` | `common/paths.py` へ複写し、repack側は現行維持（Q1=B） |
| 辞書読込 | `repack_tool/passwords.py` | repack専用のまま残す（assetは使わない） |
| ファイル名復元 | `repack_tool/names.py` | 当面repack専用、安定後に共通化検討 |
| 走査・除外 | `repack_tool/scanner.py` 相当 | assetと要件が近いため `common/scan.py` 新設を検討 |

---

## 10. 移行手順（実装フェーズ詳細）

- [ ] **Phase 0（継続中→完了見込み）**: asset詳細詰め Q13〜Q22 確定済み。残りは実装承認のみ。
- [ ] **Phase 1-1**: `src/suite_top/` 雛形＋TOP画面（選択・起動のみ）作成（Q4=A）。既存repack GUIは変更せず別窓で起動。
- [ ] **Phase 1-2**: 共通部品を `src/common/` へ複写（repack側は現行維持・Q1=B）。既存テストを全緑にする。
- [ ] **Phase 2-1**: `src/asset_tool/` のCLI雛形作成（Q5〜Q9確定仕様に基づく）。
- [ ] **Phase 2-2**: 旧エントリの動作確認（変更なし・Q11=A）。
- [ ] **Phase 3**: asset機能の実装（core/cli/gui＋テスト）。
- [ ] **Phase 4**: `docs/gui_manual.html` 追補（TOP＋asset）、`README` 更新、E2E追加、リリース。

各Phase完了ごとにコミットし、pushは指示後に行う（現行運用ルール）。

---

## 11. テスト計画

- 回帰：既存テスト（names/dry_run/scanner/passwords/paths/integration）を全緑維持。旧エントリ経路のスモークテストを追加。
- 新規：TOP起動・画面遷移のGUIスモーク、assetのCSV/HTML出力テスト（日本語名・空フォルダ・権限エラー時も継続）。
- 受入：`python -m repack_tool` が現行動作と同一（変更なし・Q11=A）、`python -m asset_tool` が6章仕様どおり。

---

## 12. リスクと対策

| リスク | 対策 |
|---|---|
| importパス変更による外部スクリプト破損 | Q1=B・Q11=Aによりrepack側のimport変更なし。asset/suite_top/commonは新規追加のみ |
| GUI共通化でrepack操作感が変わる | 見た目・文言は現行踏襲、共通化は内部のみ |
| asset仕様の膨張 | Q5〜Q9で固定済み。追加要望はPhase 4以降へ |
| テスト用一時資産の混入 | `.gitignore` の `tmp/result/tests/data` 系除外を維持 |

---

## 13. 承認のお願い（次アクション）【Q1〜Q22確定・実装承認待ち】

確定済み（Planモード壁打ち結果）：

1. 構成案（5章）→ **B方式**（Q1=B: `src/repack_tool`＋`src/asset_tool`並列＋TOP新設）。
2. TOP置き場所 → **C**（Q3=C: `src/suite_top/`＋`src/common/`に分離）。
3. TOP遷移方式 → **A**（Q4=A: 選択・起動のみ＋既存GUIを別窓で開く）。
4. 資産一覧5点 → **Q5=A・Q6=B・Q7=C・Q8=A・Q9=A**（6.4参照）。
5. GUI同時実行 → **A**（Q10=A: 機能ごとに最大1ジョブ・機能間同時可）。
6. 旧エントリ互換 → **維持**（Q11=A: 変更なし）。
7. 進め方 → **B**（Q12=B: asset詳細を先に詰める・Phase 0継続）。
8. asset詳細 → **Q13=A・Q14=A・Q15=A・Q16=A・Q17=A・Q18=A・Q19=A・Q20=A・Q21=A・Q22=A**（6.1〜6.5参照）。

残タスクなし。承認時は「**スイート化の実装に進んで**」と返信してください（Actモード）。

---

## 付録: Q&Aトレーサビリティ（Planモード壁打ち Q1〜Q12）

| No | 質問 | 回答 | 反映先 |
|---|---|---|---|
| Q1 | スイート構成案 | **B**: `src/repack_tool`＋`src/asset_tool`並列＋TOP新設 | 5章・5.1・8章・10章 |
| Q2 | TOP画面の置き場所 | **C**: `common_top`系（→Q3で具体化） | 5章（Q3=Cに統合） |
| Q3 | common_topの中身・命名 | **C**: `src/suite_top/`＋`src/common/`に分離 | 5章・7.1・9章・10章 |
| Q4 | TOP→機能画面の遷移方式 | **A**: TOPは選択・起動のみ＋既存GUIを別窓 | 3章・7.1 |
| Q5 | 資産一覧の出力形式 | **A**: 既定CSV＋任意HTML/Markdown | 6章・6.4 |
| Q6 | 資産一覧の行粒度 | **B**: フォルダ集約1行 | 6章・6.4 |
| Q7 | 資産一覧の収集対象 | **C**: 全ファイル | 6章・6.4 |
| Q8 | ハッシュ必須化 | **A**: 任意・既定OFF | 6章・6.4 |
| Q9 | result系レポートとの関係 | **A**: 独立（`asset_YYYYMMDD`） | 6章・6.4 |
| Q10 | GUI同時実行ポリシー | **A**: 機能ごと最大1ジョブ・機能間同時可 | 7.3 |
| Q11 | 旧エントリ互換維持 | **A**: 維持（変更なし） | 3章・5.1・8章・10章・11章 |
| Q12 | ブラッシュアップ後の進め方 | **B**: asset仕様の詳細を先に詰める | 10章・13章 |
| Q13 | フォルダ集約1行の列定義 | **A**: フォルダ名＋ファイル数＋合計サイズ＋最新更新日＋備考 | 6章・6.2・6.4 |
| Q14 | 一覧のソート順 | **A**: フォルダ名昇順を既定とし、後から変更可能 | 6章・6.2・6.3・6.4・6.5 |
| Q15 | 空フォルダの扱い | **A**: 件数0行として出力 | 6章・6.2・6.4 |
| Q16 | 除外条件 | **A**: repackと共通 | 6章・6.2・6.3・6.4 |
| Q17 | 読取エラーの扱い | **A**: 備考欄に記録して継続＋終了コード2 | 6章・6.2・6.3・6.4 |
| Q18 | 出力ファイル名の規則 | **A**: `asset_YYYYMMDD`＋同日は`_01`連番 | 6章・6.3・6.4 |
| Q19 | 集約単位 | **A**: 起点直下のサブフォルダ単位 | 6章・6.2・6.4 |
| Q20 | 合計行 | **A**: 合計行あり | 6章・6.2・6.3・6.4 |
| Q21 | 集計範囲 | **A**: 直下単位・中身は再帰集計 | 6章・6.1・6.2・6.4 |
| Q22 | asset実行ログ | **A**: 必要（repack踏襲） | 6章・6.3・6.4 |

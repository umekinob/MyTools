# 圧縮ファイル解凍→フォルダ毎Zip再圧縮ツール 設計書

- 文書名: archive-repack-tool-design.md
- 作成日: 2026-09-10
- 対象: MyTools (`c:\Dドライブ\AI_Models\MyTools`)
- ステータス: 設計確定版（実装前）/ 要承認
- 経緯: PM（Q1〜Q37壁打ち）→仕様漏れ確認（Q38〜Q52追記）→ Architect（本書）→ Code（次工程）
- 環境: Python 3.12.10 / Windows / VS Code

## 1. 概要・目的・スコープ

### 1.1 目的
あるフォルダの圧縮ファイル（例: 7z）を解凍し、フォルダが分かれていればフォルダ毎にzip圧縮し直す処理を自動化する。

```text
入力: input/photo-pack.7z (解凍すると FolderA/ + FolderB/)
出力: output/.../FolderA.zip, FolderB.zip
```

### 1.2 IN（対象内）
- 指定フォルダの再帰探索→解凍→分類→フォルダ毎zip化
- CLI先行、GUIは後付けラッパー（CLI相当＋進捗バー）
- コンソール＋ファイルにログ・進捗
- 専用出力フォルダに集約、入力階層ミラー再現
- パスワード辞書の自動試行、分割・破損の事前チェック
- 日本語・ロングパス対応、逐次処理

### 1.3 OUT（対象外）
- 出力zipの暗号化（無暗号: Q22）
- 並列処理（逐次: Q31）
- 日時・属性保持（しない: Q27）
- 元圧縮の削除（残す: Q24）
- 空フォルダのzip化（スキップ: Q28）

## 2. 用語・前提

| 用語 | 定義 |
|------|------|
| アーカイブ | 処理対象の圧縮1件（例 `a.7z`） |
| 入力ルート | `--input` 起点フォルダ |
| 出力ルート | `--output` 専用出力フォルダ |
| ミラー出力 | 入力相対パスを出力配下に再現（Q17） |
| トップレベル | 一時解凍直下の集合 |
| ファイル群zip | 混在・ファイルのみ時に直下ファイルをまとめたzip |
| 作業一時 | OS標準tempの一時域。処理後削除（Q19/Q37） |
| スキップ継続 | 1件失敗でも止めず次へ（Q20） |

前提: Win10/11 + Python3.12、`docs/`存在確認済み、実装はこれから。

## 3. 要件トレーサビリティ（Q1〜Q52）

| No | 項目 | 確定 | 反映先 |
|----|------|------|--------|
| Q1 | 操作形式 | 両対応（CLI先行＋GUI後付け） | 4,8,9章 |
| Q2/Q32 | 形式 | 7z/zip/rar/tar.gz・tgz＋tar.bz2・tar.xz・gz・bz2・xz | 5章 |
| Q3 | 指定 | 再帰探索（既定ON） | 5,8章 |
| Q4 | 判定 | 単一→内部のフォルダ群をzip化、複数→直下フォルダ毎分割 | 6章 |
| Q5/Q12/Q29 | ログ | 結果＋進捗、コンソール＋ファイル | 11章 |
| Q6 | 出力先 | 専用出力フォルダ | 7章 |
| Q7 | zip名 | フォルダ名→zip名 | 7章 |
| Q8/Q21 | PW | 辞書自動試行、形式は設計提案 | 10章 |
| Q9/Q33 | 分割破損 | 事前チェック、全巻揃い条件 | 5.3章 |
| Q10/Q37 | 一時 | 中間・一時は処理後削除 | 5.6章 |
| Q11 | 衝突 | 連番で別名保存 | 7.3章 |
| Q13 | 言語 | Python | 4章 |
| Q14 | エンジン | lib優先・無ければ7z.exe | 4.2章 |
| Q15/Q34/Q35 | 検証 | 本格検証、パターンは設計提案 | 14章 |
| Q16/Q36 | 混在 | ファイル群1zip、名は設計提案 | 6.3,7.2章 |
| Q17 | 構造 | ミラー | 7章 |
| Q18 | 圧縮 | 最高圧縮既定（切替可） | 7.4章 |
| Q19 | 一時場所 | OS標準temp | 5.6章 |
| Q20 | 失敗時 | スキップ継続 | 12章 |
| Q22 | 出力暗号 | しない | 7章 |
| Q23 | 機密 | 設計提案 | 13章 |
| Q24 | 元圧縮 | 残す | 5.6章 |
| Q25 | CLI | フル機能 | 8章 |
| Q26 | GUI | CLI相当＋バー | 9章 |
| Q27 | 日時 | 保持しない | 7.4章 |
| Q28 | 空 | スキップ | 6.5章 |
| Q30 | 長パス | 日本語・長パス対応 | 13章 |
| Q31 | 並列 | 逐次 | 4.3章 |
| Q38 | 入れ子 | 再帰的に解凍して展開（上限あり） | 5.7, 6.4, 12章 |
| Q39 | 巨大ZIP64 | 処理対象（zip64=allow、Zip爆弾警告はOFF既定） | 5.7, 8章 |
| Q40 | 入出力同一・包含 | 出力をScanner除外、`--allow-output-inside-input` | 5.6, 8, 13章 |
| Q41 | 同名アーカイブ内Dir | 連番保存（Q11ルール流用） | 7.3章 |
| Q42 | 空き不足・権限 | WARN＋処理継続 | 5.6, 12章 |
| Q43 | タイムアウト | 設けない（終わるまで待つ） | 12章 |
| Q44 | ログ件数 | ヘッダ実行実＋件数要約 | 11章 |
| Q45 | 隠し・ドット | 除外対象に追加 | 6, 13章 |
| Q46 | on-conflict | 連番のみ固定（上書き・スキップ無し） | 7.3章 |
| Q47 | 設定ファイル | TOML対応 | 8.3, 13章 |
| Q48 | GUI入力 | ダイアログ＋D&D対応 | 9章 |
| Q49 | 入れ子上限 | 既定3階層・切替可 | 5.7, 8, 12章 |
| Q50 | 文字化け検証 | 検証して採用・警告継続 | 13, 14章 |
| Q51 | サマリ詳細 | 成功・失敗双方一覧 | 11章 |
| Q52 | サマリ内一覧 | 成功zip一覧＋スキップ理由一覧を分けて出力 | 11章 |

## 4. 全体アーキテクチャ

```text
CLI(repack-cli, フルオプション)
  └─ Core Service(逐次) ─ Log/Progress(console+file)
       ├─ Scanner(再帰探索・分割判定)
       ├─ Extractor(整合性+解凍)
       └─ Repacker(分類+zip化・ミラー出力)
            ├─ Python libs(py7zr/zipfile/tarfile)
            └─ 7z.exe fallback(rar保険用)
将来: GUI Wrapper(CLI/Core呼び出し＋進捗バー)
```

### 4.2 エンジン選定（Q14）
| 形式 | 優先lib | fallback | 備考 |
|------|---------|----------|------|
| .7z | py7zr | 7z x | 辞書は両経路で試行 |
| .zip | zipfile | 7z x/t | 破損は7z tで再判定 |
| .rar | rarfile | 7z x(主経路) | py単体制限のため7z委譲必須 |
| .tar.gz/.tgz/.tar.bz2/.tar.xz | tarfile | 7z x | |
| .gz/.bz2/.xz単体 | gzip/bz2/lzma | 7z x | 単一→ファイルのみ扱い |

- 検出順: PATH→`C:\Program Files\7-Zip\7z.exe`→`--seven-zip-path`
- 依存案: `py7zr>=0.22.0, rarfile>=4.1, tqdm>=4.66.0`
- rarは7z.exe無しでは原則スキップ＋明示ログ

### 4.3 処理方式
- 逐次処理のみ（Q31）。1件単位: 検証→一時解凍→分類→zip化→検証→後片付け

## 5. 処理フロー

### 5.1 メインフロー

1. 引数解決＋入出力チェック
2. Scanner: 再帰走査→一覧（相対パス昇順）
3. 件毎に逐次: 分割判定→整合性→temp解凍→辞書順試行→分類→zip化→読戻し検証→temp削除→結果ログ
4. サマリ表示＋ログ
5. 終了コード: 0=全成功、2=一部スキップ/失敗、1=致命的、130=中断

### 5.2 Scanner
- 対象(小文字化): `.7z,.zip,.rar,.tar.gz,.tgz,.tar.bz2,.tar.xz,.gz,.bz2,.xz`
- 複合拡張子を先判定。出力配下・tempは除外。再帰OFFは直下のみ。

### 5.3 分割・整合性（Q9/Q33）
- `*.7z.001`のみ対象、他巻は`split-part`でスキップ
- `*.part01.rar/part1`のみ対象、`*.z01+*.zip`は`.zip`のみ対象
- 連番欠け→`missing-part`でスキップ継続
- lib: ヘッダ/PW要否の事前判定、7z: `7z t`。破損→`corrupt`スキップ

### 5.4 解凍
- 試行順: 無PW→辞書行順。辞書無＋要PW→`password-required`、全滅→`password-mismatch`
- Zip Slip対策: `../`・絶対パスは無害化/警告スキップ。symlinkは展開しない。
- 再帰解凍: 展開物中の圧縮は Q38 に従い再帰（5.7/6.4参照）

### 5.5 再圧縮共通
- `ZIP_DEFLATED level=9`既定、日時不保持、UTF-8名、空は作らず、出力後testzip読戻し

### 5.6 後片付け・入出力関係（Q10/Q24/Q37/Q40/Q42）
- tempはtry-finallyで必ず削除。`--keep-temp`のみ残置
- 中間はtemp内に閉じる。元圧縮は削除しない。
- 入力=出力 or 包含関係（Q40）: 既定はエラー回避のため全シンボリックチェックの上で、出力を入力の下に置く場合はScannerの除外リストに出力を必ず含める（再帰ループ防止）。`--allow-output-inside-input` で明示許可
- 出力側エラー（Q42）: 空き不足・権限なしはWARN表示しつつ処理継続（スキップ対象のアーカイブのみ記録）。致命的な引数エラーのみ即時終了

### 5.7 入れ子・隠しファイル（Q38/Q45/Q49）
- 入れ子圧縮: 再帰的に解凍して展開する（Q38）
- 深さ上限: 既定3階層、`--nested-depth 0-9` で切替（Q49）。超過分・自己参照は `nested-limit` スキップ
- 隠しファイル・ドットファイル（`.git`、`.gitignore`、ドット始まり）は除外対象に追加（Q45）
- 巨大ファイル・ZIP64（Q39）: 処理対象とし zip64=allow を明示。空き不足は警告で継続（Q42）
- 巨大解凍時のZip爆弾: `--max-extract-mb`（既定0=無制限）・`--max-compression-ratio` で警告（既定OFF）

## 6. 分類ロジック（Q4/Q16中核）

直下を`dirs/files`とし、`Thumbs.db/.DS_Store/desktop.ini`/隠し・ドット（.git等）は除外。残0は空。

| ケース | 条件 | 動作 |
|--------|------|------|
| A単一 | dirs=1,files=0 | 6.1の単一フォルダ降下ルールへ |
| B複数 | dirs>=2 | フォルダ毎＋直下ファイルあれば群zip追加 |
| C混在 | dirs>=1,files>=1 | Bと同様 |
| Dファイルのみ | dirs=0,files>=1 | 群zip1つ |
| E空 | 0,0 | スキップ(empty) |

### 6.1 単一フォルダ降下（パターン2/3/4/2'）

単一トップレベルの場合、**直下にフォルダがある間は1階層ずつ降下**し、フォルダ群に当たった階層を処理対象とする（深さ上限: `--nested-depth`既定3）。

- 例: `ああ/01,02,03` → `ああ`を降下 → `01.zip, 02.zip, 03.zip`
- 例: `ああ/ああ/01,02,03` → 2回降下 → `01.zip, 02.zip, 03.zip`
- 直下が**ファイルのみ**の単一フォルダ → 降下せず従来の1zip（`Top.zip`）
- 直下が**ファイル群のみ**（folderなし） → 従来の1zip

### 6.2 単一フォルダ降下時のファイル群・アーカイブ

降下した階層に直下ファイルがある場合:
- **アーカイブ**（zip等）→ 解凍せずそのまま出力へ保持（コピー）。中身は展開しない
- **それ以外のファイル** → `フォルダ直下.zip` に群zip化（パターン2'）

- 深い階層は再分割しない。例`Top/Sub1/Sub2`→`Top.zip`のみ（Sub層は対象外）
- 空フォルダは`skip: empty-folder`をログ

### 6.3 ファイル群zip
- Q16確定で1つにまとめる。Q36提案名は7.2で定義。

### 6.4 ネスト・無限ループ（Q38/Q49）
- 入れ子圧縮は再帰的に解凍・展開して分類化する（Q38）
- 深さ上限`--nested-depth`（既定3）。超過・自己参照は`nested-limit`としてスキップ継続（Q49）
- 巨大・ZIP64（Q39）: 処理対象。`zip64=allow`を明示、`--max-extract-mb`/`--max-compression-ratio`でZip爆弾警告（既定OFF）
- 再帰後にフォルダが分かれた場合も6章の分類ルール（単一降下→フォルダ毎／複数→フォルダ毎）を適用
- 単一フォルダ降下時は入れ子展開をスキップ（アーカイブは保持のため）

## 7. 命名・出力規則

### 7.1 基本（Q7）
- フォルダ由来`<フォルダ名>.zip`。単一時も同ルール（元名引継なし）

### 7.2 群zip名（Q36提案）
- 推奨: `<アーカイブ基底名>_files.zip`（例`photo-pack.7z`→`photo-pack_files.zip`）
- 代替`loose_files.zip`は設定切替可。既定は推奨案（追跡・衝突回避のため）

### 7.3 出力先・ミラー・衝突（Q6/Q17/Q11/Q41）
- 既定`out/<rel-parent>/<archive-stem>/`配下にミラー作成
- 例: `in/sub/b.rar`→`out/sub/b/DirX.zip, b_files.zip`
- 同名→`_001,_002`連番で別名保存。上書き禁止（Q46: 上書き・スキップは対応しない）。出力無暗号。`--flat`で平坦化可。
- 異なるアーカイブ同士で同名フォルダ（`a.7z`の`Dir`＋`b.7z`の`Dir`→同`Dir.zip`）も上記連番ルールを流用し両方保存（Q41）

### 7.4 圧縮（Q18/Q27）
- 既定level9、`--compression-level 0-9`で切替。日時・属性不保持。

## 8. CLI仕様（Q25フル機能）

```bash
python -m repack_tool --input ./in --output ./out --recursive --password-list ./dict.txt --log-file ./logs/repack.log
```

| 項 | 既定 | 説明 |
|----|------|------|
| --input必須 | - | 入力フォルダ |
| --output必須 | - | 出力フォルダ（無ければ作成） |
| --recursive/--no-recursive | ON | 再帰有無 |
| --password-list | なし | 辞書（10章） |
| --encoding | utf-8 | 辞書読込 |
| --compression-level 0-9 | 9 | 最高圧縮既定 |
| --on-conflict | increment | 連番（将来overwrite/skip余地） |
| --include-exts | 既定一覧 | 上書き可 |
| --exclude-names | OSゴミ等 | 除外パターン |
| --seven-zip-path | 自動検出 | 明示指定 |
| --prefer-7z/--no-prefer-7z | lib優先 | 切替可 |
| --dry-run | OFF | 作成予定zipを算出・表示（書込なし／8.4） |
| --keep-temp | OFF | デバッグ残置 |
| --flat | OFF | 平坦出力 |
| --log-file | out内自動名 | ファイル先 |
| --log-level | INFO | DEBUG/INFO/WARNING/ERROR |
| --nested-depth 0-9 | 3 | 入れ子解凍上限（Q49） |
| --max-extract-mb | 0=無制限 | 解凍サイズ上限（Q39-Zip爆弾対策） |
| --max-compression-ratio | 0=OFF | 圧縮率上限（Q39） |
| --exclude-pattern | なし | 正規表現で除外（Q23） |
| --config PATH | なし | 設定ファイル読込（Q47） |
| --allow-output-inside-input | OFF | 出力が入力配下を許可（Q40） |

終了コード: 0全成功/2一部スキップ/1致命的/130中断。

### 8.3 設定ファイル（Q47）
- 形式: `TOML`（Python3.11+標準）。
- 例:
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
- CLI引数（`--config`と個別オプション両方ある場合）は、CLI引数が優先
- 既定は `repack.toml` をカレントに探す（無ければCLI引数のみで動作）

### 8.4 dry-run仕様（実処理との一致保証）

- `--dry-run` は「予測のみ」ではなく、**実処理と同一の処理経路**で作成予定zipを算出する（方針B完全実施）。
- 解凍・単一フォルダ降下・入れ子解凍・分類・命名・衝突回避は本実行と同じロジックを通し、
  **出力フォルダへの書き込み（zip作成・コピー・フォルダ作成）のみを行わない**。
- 解凍は一時領域（既定 `tmp/`、`--temp-dir` で変更可）で実施し、処理後に削除する（`--keep-temp` を除く）。
- ログには `DRY-RUN <アーカイブ名> -> <出力先からの相対パス>` と要約行 `予定zip:` を出力する。
- このため **dry-runの予測は本実行の出力と一致する**（単一フォルダ降下／入れ子解凍／空フォルダskip／
  降下時のアーカイブ保持／直下ファイル群の「フォルダ直下.zip」を含む）。
- アーカイブ内のファイル名一覧から軽量推定する旧方式（方針B初期実装）は、降下・入れ子・空判定を
  反映できず本実行と乖離するため**廃止**した。

## 9. GUI仕様（後付け・Q26/Q48）

- CLI/Coreをimportする薄ラッパー（既定案tkinter）
- 入力/出力/辞書選択＋再帰・7z優先・keep・dry-run＋圧縮/ログレベル＋実行/中止＋バー＋ログビュー
- 入力指定: フォルダ選択ダイアログに加えて、ファイル/フォルダのドラッグ＆ドロップ対応も組み込む（Q48）
- Coreは`on_progress(current/total,message)`コールバックを呼ぶ設計
- CLI完成後の別マイルストーン

## 10. パスワード辞書（Q8/Q21提案）

- UTF-8(BOM可)、1行1PW、空行・前後空白無視、`#`行はコメント、上限1万行で警告
- `--password-list`未指定＋要PW→`password-required`でスキップ
- 行順厳守・シャッフルなし。成功PW・行番号もログに出さない
- 例: `passwords.txt`に`password123`等を列挙。ログ・例外にPWを出さない

## 11. ログ・進捗（Q5/Q12/Q29/Q44/Q51/Q52）

- コンソールtqdm＋ファイル`--log-file`（既定`<output>/repack_YYYYMMDD-HHMMSS.log`）、UTF-8
- 例: `scan: found 12`／`[1/12] a.7z -> extract ok -> multi(2dirs+3files) -> A.zip,B.zip,a_files.zip`
- skip例: `broken.zip -> skip(reason=corrupt)`／`secret.rar -> skip(password-mismatch,tried=120)`
- サマリ必須（Q51/Q52）: total/success/skip/fail＋出力先＋
  - 成功一覧（作成zipのフルパス）＋スキップ・失敗一覧（理由別）を必ず双方出力（検証・リカバリ用）
  - 件数進捗のみ（%内訳なし）
- ログファイル名（Q44）: `repack_YYYYMMDD-HHMMSS.log` に日時入りで上書きしない。ヘッダに実行日時・ツールバージョン・オプションを記録、件数（total/success/skip/fail）を要約末尾に記録

## 12. エラー処理（Q20/Q43/Q49）

| 事象 | reason | 終了寄与 |
|------|--------|----------|
| 欠巻/破損/PW要/PW不一致/空/書込失敗 | missing-part/corrupt/password-required/password-mismatch/empty/write-failed | 2（継続） |
| 入れ子上限超過・自己参照 | nested-limit | 2（継続） |
| 入力不存在・出力不可 | - | 1（即時） |
| Ctrl+C | interrupted | 130（一時削除） |

- アーカイブ単位try-except、traceはDEBUGのみ、tempはfinally削除
- タイムアウト: 設けない（Q43。終わるまで待つ）。進行中の最長を進捗ログに記録し続行

## 13. 横断配慮（Q30/Q40/Q45/Q47/Q50）

- 日本語・長パス（Q30）: pathlib統一、utf-8、`\\?\`付与、zip UTF-8旗、cp437検証
- セキュリティ（Q23提案）: 既定はWARNのみ（`password/個人情報/マイナンバー/secret`含名）、`--exclude-pattern`で除外可、中身・PWは非出力
- Zip Slip/絶対パス/symlink対策、一時権限はtempfile既定、空き容量は警告のみ
- 入出力関係（Q40）: 出力が入力配下のときScanner除外対象に含め無限ループ防止（5.6参照）
- 隠し・ドットファイル（Q45）: `.git`/`.gitignore`/ドット始まりは除外（6章参照）
- 設定ファイル（Q47）: `TOML` 対応（8.3章 `--config` 参照）
- 文字化け検証（Q50）: 解凍後・zip化時にcp437等のエンコードを検証し、データ化けが検出された場合は `encoding-unsupported` でスキップせず警告＋処理は継続（エントリ名は正規化して保存）
- 空白・特殊文字・OS非対応文字: サニタイズ関数で `<>:"/\|?*` を置換・除去して保存

## 14. テスト計画（本格・Q15/Q34/Q35提案）

| ID | パターン | 期待 |
|----|----------|------|
| T01 | 単一Top/ | Top.zip |
| T02 | A/,B/ | A.zip,B.zip |
| T03 | A/+2file | A.zip＋<base>_files.zip |
| T04 | fileのみ3 | <base>_files.zip |
| T05 | 空のみ | emptyスキップ |
| T06 | 日本語・空白 | 化けなし |
| T07 | 要PW一致 | 成功・非ログ |
| T08 | 要PW不一致 | mismatchスキップ |
| T09 | 分割揃い | 先頭巻成功 |
| T10 | 分割欠け | missing-part |
| T11 | 破損 | corrupt |
| T12 | tar系各1 | 正常化 |
| T13 | 同名存在 | _001連番 |
| T14 | sub階層 | ミラー再現 |
| T15 | Slip含有 | 無害化WARN |
| T16 | 入れ子zip→zip | 内部展開されフォルダ分類（Q38） |
| T17 | 隠し・ドット | 除外される（Q45） |
| T18 | 出力と入力が同一 | 無限ループ無し（Q40） |
| T19 | 同名アーカイブ内Dir | 連番保存（Q41） |
| T20 | 日本語・長パス | 正常zip化・再読出（Q30/Q50） |
| T21 | 巨大ダミー | 警告＋継続（Q39/Q42） |
| T22 | 設定ファイル | TOML反映確認（Q47） |

- pytestで分類・命名・分割・連番を単体化、実解凍は7z有無で分岐
- 手順: make_samples→dry-run→本実行→7-Zip目視→checklist記録（将来`verification-checklist.md`）

## 15. 構成案

```text
MyTools/docs/archive-repack-tool-design.md
src/repack_tool/__init__ __main__(CLI入口) cli/scanner/checker/extractor/classifier/repacker/passwords/progress/paths/config.py
tests/test_classifier test_naming test_scanner make_samples.py
requirements.txt pyproject.toml README.md
```

## 16. 実装ステップ

1. 雛形＋`--help`骨格 2. scanner/checker/passwords/paths＋単体 3. extractor/classifier/repacker＋T01-05疎通 4. ログ/終了/dry-run/keep-temp 5. T01-22＋設定ファイルTOML 6. PMOレビュー→README 7. GUI別フェーズ
- コミットは確認後のみ。秘密コミット禁止（.clinerules準拠）

## 17. リスク・未決

- 最高圧縮は低速受容・切替可／rarは7z依存／逐次で確実性／日時不保持／群名`<base>_files.zip`は異議あれば変更可／機密WARN＋除外／辞書上限1万／入れ子上限3は拡張可能／4GB超・ZIP64はライブラリに依存

## 18. 承認チェック

- [ ] 6章分類でよいか [ ] 7.2群名でよいか [ ] 7.3ミラー＋sub＋Q41連番でよいか [ ] 10章辞書でよいか [ ] 13章機密WARN＋除外でよいか [ ] 8章オプション（Q38/Q39/Q40/Q45/Q47/Q49含む）でよいか [ ] 承認後実装へ進んでよいか

## 付録A. help案

```text
usage: python -m repack_tool --input IN --output OUT [options]
--recursive/--no-recursive --password-list PATH --compression-level 0-9(9)
--seven-zip-path PATH --prefer-7z --dry-run --keep-temp --flat --log-file PATH --log-level INFO
--nested-depth 0-9(3) --max-extract-mb N --max-compression-ratio N
--exclude-pattern REGEX --config PATH --allow-output-inside-input
```

## 付録B. Q&A要約

Q1両対応/Q2主要/Q3再帰/Q4単一1複数分割/Q5等両出力/Q6専用/Q7名/Q8辞書/Q9事前/Q10削除/Q11連番/Q13Python/Q14両対応/Q15本格/Q16群1/Q17ミラー/Q18最高/Q19temp/Q20継続/Q21提案/Q22無暗号/Q23提案/Q24残す/Q25フル/Q26全＋バー/Q27不保持/Q28空外/Q30対応/Q31逐次/Q32拡張gz系迄/Q33全巻/Q34本格/Q35提案/Q36提案/Q37削除。
Q38再帰展開/Q39処理対象+/Q40入出力関係ガード/Q41連番/Q42警告継続/Q43タイムアウトなし/Q44件数ログ/Q45隠し除外/Q46連番のみ/Q47設定ファイル/Q48D&D/Q49上限3/Q50検証採用。



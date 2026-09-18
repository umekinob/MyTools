# プロジェクト概要（Project Brief）

- プロジェクト名: MyTools（作業効率化ツール群）
- 場所: `c:\Dドライブ\AI_Models\MyTools`
- リポジトリ: https://github.com/umekinob/MyTools.git（branch: master）
- メモリーバンク初期化日: 2026-09-17
- 環境: Windows 10/11 + Python 3.12.10 + VS Code

## 存在目的
日常のファイル管理作業を自動化する Python 製デスクトップツール群。
最初の機能として「圧縮ファイル解凍 → フォルダ毎 zip 再圧縮ツール（repack-tool）」を実装済み。
第2機能「デジタル保有資産一覧出力（asset）」を同一土台に載せるスイート化を実装済み
（Phase 1〜4・2026-09-18。コミットは未実施）。

## 現在のスコープ（実装済み）
- **repack-tool**: 7z/zip/rar/tar系などを解凍し、トップレベル構造に応じて
  フォルダ毎に zip 再圧縮するツール。
  - CLI: `python -m repack_tool`（フルオプション）
  - GUI: `python -m repack_tool.gui`（tkinter・進捗バー付き）
  - パスワード辞書自動試行・分割/破損事前チェック・入れ子解凍・ミラー出力
  - 設計書: `docs/archive-repack-tool-design.md`（Q1〜Q52 確定済み）
- **スイート化（Phase 1〜4 完了・2026-09-18）**: TOP 画面（`suite_top`）から
  各機能画面へ遷移する構成＋第2機能 asset-tool。
  設計書: `docs/work-efficiency-suite-design.md`（2026-09-16 ブロッカー0 到達）。
  - `asset_tool`: 指定フォルダを読み取り専用で走査し全階層フォルダを 1 行 1 フォルダで
    CSV/HTML/MD 出力（CLI `python -m asset_tool` / GUI `python -m asset_tool.gui`）
  - `mytools_common`: ログ・パス・走査除外の共通部品（複写方式・Q30=A）
  - `suite_top`: TOP 画面。各機能はサブプロセスで別窓起動（repack は無変更）
  - `pyproject.toml` の配布名を `mytools` へ変更済み（Q24=A）
  - コミットは未実施（指示により Phase 3/4 を先行実装）

## スコープ外（明確にやらないこと）
- repack 機能自体の仕様変更（分類・命名・終了コード等は現行維持）
- Web化・常駐化・DB導入・インストーラ化・自動更新
- asset の更新系操作（削除/移動/リネーム）
- asset の将来拡張（`--no-empty`・`--rollup`・重複検出本体）は設計書12章に保留
- 出力 zip の暗号化・並列処理・日時属性保持・元圧縮の削除

## 運用ルール
- コミットは必ず指示者の確認を経てから実行（push は指示後）
- 機密情報（パスワード辞書・API キー等）はコミットしない（.gitignore で運用中）
- 開発は PM → Architect → Code → PMO のモード自動切替で進行

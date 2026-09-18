"""asset 用テストデータ生成（設計書 11章・Q51=A）。

網羅: 日本語名・空フォルダ・深い階層・起点直下ファイル・シンボリックリンク・
同名タイトル・長パス。
使い方: python tests/make_asset_samples.py
（tests/data/asset_in に生成。.gitignore 運用対象のためコミットしない）
"""
from __future__ import annotations

from pathlib import Path

DEEP_LEVELS = 20


def build_samples(root: Path) -> dict:
    """root 配下にサンプルを構築し、作成情報を返す。"""
    root.mkdir(parents=True, exist_ok=True)
    info: dict = {}

    # 1. 起点直下ファイル（(ルート) 行の受け皿・Q28=A）
    (root / "起点直下.txt").write_text("ルート直下ファイル", encoding="utf-8")

    # 2. 設計書の想定構造（6.1）
    p = root / "あ-お" / "あ" / "ああ-あと" / "タイトル"
    p.mkdir(parents=True)
    (p / "タイトル.zip").write_bytes(b"sample zip content")

    # 3. 空フォルダ（0件行・Q15=A）
    (root / "あ-お" / "い" / "空フォルダ").mkdir(parents=True)

    # 4. 深い階層
    deep = root
    for i in range(DEEP_LEVELS):
        deep = deep / f"深さ{i:02d}"
    deep.mkdir(parents=True)
    (deep / "深いファイル.txt").write_text("deep", encoding="utf-8")
    info["deep_path"] = deep

    # 5. 同名タイトル（別パス・重複確認材料）
    for parent in ("X分類", "Y分類"):
        t = root / parent / "同名タイトル"
        t.mkdir(parents=True)
        (t / "同じ.zip").write_bytes(b"dup content")

    # 6. シンボリックリンク（権限がある場合のみ・Q45=A）
    try:
        (root / "リンクA").symlink_to(root / "あ-お", target_is_directory=True)
        info["link_created"] = True
    except OSError:
        info["link_created"] = False

    # 7. 長パス（フォルダ名80文字）
    long_name = "長" * 80
    (root / long_name).mkdir()
    (root / long_name / "ファイル.txt").write_text("long", encoding="utf-8")
    info["long_dir"] = long_name

    return info


def main() -> None:
    root = Path(__file__).resolve().parent / "data" / "asset_in"
    info = build_samples(root)
    print(f"作成: {root}")
    print(f"リンク作成: {info.get('link_created')}")


if __name__ == "__main__":
    main()
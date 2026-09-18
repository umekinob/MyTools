"""asset_tool E2E テスト（Phase 4・CLI サブプロセス実行）。

make_asset_samples.build_samples でサンプルを構築し、
`python -m asset_tool` を CLI として実行して成果物を検証する。
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = TESTS_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(TESTS_DIR))

from make_asset_samples import build_samples  # noqa: E402


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(SRC_DIR)}
    return subprocess.run([sys.executable, "-m", "asset_tool", *args],
                          capture_output=True, text=True, timeout=120, env=env,
                          encoding="utf-8", errors="replace")


class TestAssetE2E(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.in_dir = self.root / "資産"
        self.out = self.root / "out"
        self.out.mkdir()
        build_samples(self.in_dir)

    def tearDown(self):
        self._td.cleanup()

    def test_cli_csv_end_to_end(self):
        """CLI 実行 → 終了コード0・CSV（BOM/CRLF/11列/合計行）。"""
        r = run_cli("--input", str(self.in_dir), "--output", str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        files = list(self.out.glob("asset_*.csv"))
        self.assertEqual(len(files), 1)
        data = files[0].read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        lines = [l for l in data.decode("utf-8-sig").split("\r\n") if l]
        # ヘッダ11列
        self.assertEqual(len(lines[0].split(",")), 11)
        body = lines[1:-1]
        first = body[0].split(",")
        self.assertEqual(first[0], "(ルート)")
        self.assertEqual(first[2], "0")            # 深さ0
        # 合計行（列1=合計・列11=フォルダ数）
        total_cells = lines[-1].split(",")
        self.assertEqual(total_cells[0], "合計")
        self.assertTrue(total_cells[10].startswith("フォルダ数 "))
        # 想定フォルダ行数: あ-お,あ,ああ-あと,タイトル,い,空フォルダ (6)
        # + X分類,同名タイトル,Y分類,同名タイトル (4) + 深さ00..19 (20) + 長名 (1) = 31
        self.assertEqual(len(body) - 1, 31)
        # リンクはスキップ（行なし）
        self.assertNotIn("リンクA", data.decode("utf-8-sig"))

    def test_cli_html_and_md(self):
        """HTML/MD 形式も同一行セットで出力できる（Q29-11）。"""
        for fmt in ("html", "md"):
            with self.subTest(fmt=fmt):
                r = run_cli("--input", str(self.in_dir), "--output", str(self.out),
                            "--format", fmt)
                self.assertEqual(r.returncode, 0, r.stderr)
                found = list(self.out.glob(f"asset_*.{fmt}"))
                self.assertEqual(len(found), 1)

    def test_cli_dry_run_no_files(self):
        """dry-run は台帳を出力しない（Q35=A）。"""
        r = run_cli("--input", str(self.in_dir), "--output", str(self.out),
                    "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertEqual([p for p in self.out.glob("asset_*")
                          if not p.name.endswith(".log")], [])

    def test_cli_detail_with_hash(self):
        """--detail --with-hash で詳細一覧＋SHA-256（6.7）。"""
        r = run_cli("--input", str(self.in_dir), "--output", str(self.out),
                    "--detail", "--with-hash")
        self.assertEqual(r.returncode, 0)
        detail = next(iter(self.out.glob("asset_*_detail*.csv")))
        text = detail.read_text(encoding="utf-8-sig")
        self.assertIn("SHA-256", text)
        # 同名タイトルの同じ.zip が2行（重複検出の材料・Q26=A）
        self.assertEqual(text.count("同じ.zip"), 2)

    def test_cli_no_recursive(self):
        """--no-recursive は起点直下のみ（Q29-9）。"""
        r = run_cli("--input", str(self.in_dir), "--output", str(self.out),
                    "--no-recursive")
        self.assertEqual(r.returncode, 0)
        files = list(self.out.glob("asset_*.csv"))
        text = files[0].read_text(encoding="utf-8-sig")
        self.assertIn("あ-お", text)
        self.assertNotIn("あ-お\\あ", text)

    def test_cli_bad_output_rejected(self):
        """--output にファイル/拡張子付きは exit 1（Q33=B）。"""
        r = run_cli("--input", str(self.in_dir), "--output", "not_a_dir.csv")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
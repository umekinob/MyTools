"""asset_tool writers（CSV/HTML/MD・連番命名・tmp/replace・detail）のテスト（Phase 3）。"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import asset_tool.core as core
import asset_tool.writers as wr
from asset_tool.config import Config
from asset_tool.writers import next_output_path, write_aggregate, write_detail

from test_asset_core import _Logger, make_cfg


def sample_rows():
    """2行＋合計行のサンプル。"""
    r1 = core.Row(("タイトルA",), "タイトルA", "タイトルA", 1,
                  files_d=2, size_d=300, files_r=2, size_r=300,
                  mtime_r=1700000000.0)
    r2 = core.Row(("B", "タイトルA"), "B\\タイトルA", "タイトルA", 2,
                  files_d=0, size_d=0, files_r=3, size_r=1500,
                  mtime_r=1700000500.0)
    rows = [r1, r2]
    core.sort_rows(rows, "name", "asc")
    return rows, core.compute_total(rows)


class TestOutputFiles(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.out = Path(self._td.name) / "out"
        self.out.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_csv_bom_crlf_and_total(self):
        cfg = make_cfg(Path(self._td.name), self.out, format="csv")
        rows, total = sample_rows()
        p = write_aggregate(cfg, rows, total, _Logger())
        data = p.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))     # UTF-8 BOM（Q37=A）
        self.assertIn(b"\r\n", data)                          # CRLF
        lines = [l for l in data.decode("utf-8-sig").split("\r\n") if l]
        self.assertEqual(len(lines[0].split(",")), 11)        # 11列
        self.assertEqual(lines[0].split(",")[0], "保管フォルダ")
        self.assertTrue(lines[-1].startswith("合計"))         # 末尾1行（Q41=A）

    def test_sequential_naming(self):
        """同日は _01 連番（Q18=A）。"""
        cfg = make_cfg(Path(self._td.name), self.out)
        rows, total = sample_rows()
        p1 = write_aggregate(cfg, rows, total, _Logger())
        p2 = write_aggregate(cfg, rows, total, _Logger())
        self.assertNotEqual(p1, p2)
        self.assertRegex(p2.name, r"asset_\d{8}_01\.csv")

    def test_html_self_contained(self):
        cfg = make_cfg(Path(self._td.name), self.out, format="html")
        rows, total = sample_rows()
        p = write_aggregate(cfg, rows, total, _Logger())
        text = p.read_text(encoding="utf-8-sig")
        self.assertIn("<style>", text)
        self.assertIn("Meiryo", text)
        self.assertIn('class="total"', text)
        self.assertNotIn("<script", text)    # ソートJSなし（Q42=A）

    def test_md_gfm(self):
        cfg = make_cfg(Path(self._td.name), self.out, format="md")
        rows, total = sample_rows()
        p = write_aggregate(cfg, rows, total, _Logger())
        text = p.read_text(encoding="utf-8-sig")
        self.assertIn("| 保管フォルダ |", text)
        self.assertIn("|---|", text)
        self.assertIn("| 合計 |", text)

    def test_interrupt_leaves_no_final_file(self):
        """書き込み中断は最終名も tmp も残さない（Q47=A）。"""
        cfg = make_cfg(Path(self._td.name), self.out)
        rows, total = sample_rows()
        with mock.patch.object(core.Row, "cells", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                wr.write_aggregate(cfg, rows, total, _Logger())
        self.assertEqual(list(self.out.glob("asset_*.csv")), [])   # 最終名なし
        self.assertEqual(list(self.out.glob("*.tmp")), [])         # tmp も掃除


class TestDetail(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name) / "in"
        (self.root / "サブ").mkdir(parents=True)
        content = b"hello asset"
        (self.root / "サブ" / "f.bin").write_bytes(content)
        self.expected_sha = hashlib.sha256(content).hexdigest()
        self.out = Path(self._td.name) / "out"
        self.out.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_detail_csv_with_hash(self):
        """--with-hash で SHA-256 列が追加される（Q8=A・6.7）。"""
        cfg = make_cfg(self.root, self.out, detail=True, with_hash=True)
        core.run(cfg, _Logger())
        p = next(iter(self.out.glob("asset_*_detail*.csv")))
        text = p.read_text(encoding="utf-8-sig")
        self.assertIn("SHA-256", text)
        self.assertIn(self.expected_sha, text)

    def test_detail_csv_without_hash(self):
        cfg = make_cfg(self.root, self.out, detail=True)
        core.run(cfg, _Logger())
        p = next(iter(self.out.glob("asset_*_detail*.csv")))
        text = p.read_text(encoding="utf-8-sig")
        self.assertNotIn("SHA-256", text)

    def test_next_output_path(self):
        """連番ユニット（asset_YYYYMMDD[_detail]）。"""
        with tempfile.TemporaryDirectory() as td:
            base = next_output_path(Path(td), "20260918", ".csv", infix="_detail")
            self.assertEqual(base.name, "asset_20260918_detail.csv")
            base.write_text("x", encoding="utf-8")
            second = next_output_path(Path(td), "20260918", ".csv", infix="_detail")
            self.assertEqual(second.name, "asset_20260918_detail_01.csv")


if __name__ == "__main__":
    unittest.main(verbosity=2)
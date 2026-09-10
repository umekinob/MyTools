"""単体テスト: PasswordList（設計書 10章）。行順・コメント・上限・BOM。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repack_tool.passwords import PasswordList


class TestPasswordList(unittest.TestCase):
    def _write(self, content: bytes) -> Path:
        f = Path(tempfile.mkdtemp()) / "dict.txt"
        if isinstance(content, str):
            content = content.encode("utf-8")
        f.write_bytes(content)
        return f

    def test_basic(self):
        f = self._write("# コメント\n\npw1\npw2 \n")
        pl = PasswordList.from_file(f)
        # 前後空白は除去される（設計書10章）
        self.assertEqual(list(pl), ["pw1", "pw2"])

    def test_bom(self):
        f = self._write("﻿pw1\n".encode("utf-8"))
        pl = PasswordList.from_file(f)
        self.assertEqual(list(pl), ["pw1"])

    def test_none(self):
        pl = PasswordList.from_file(None)
        self.assertEqual(len(pl), 0)

    def test_missing(self):
        with self.assertRaises(Exception):
            PasswordList.from_file(Path(tempfile.mkdtemp()) / "nope.txt")

    def test_truncate(self):
        f = self._write("\n".join(f"p{i}" for i in range(200)).encode())
        pl = PasswordList.from_file(f, max_passwords=50)
        self.assertEqual(len(pl), 50)
        self.assertTrue(pl.truncated)
        self.assertEqual(pl.passwords[0], "p0")


if __name__ == "__main__":
    unittest.main()
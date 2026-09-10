"""単体テスト: scanner/archive_kind・分割巻検出（設計書 5.2/5.3・T09/T10）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repack_tool.scanner import archive_kind


class TestArchiveKind(unittest.TestCase):
    def test_compound_ext(self):
        self.assertEqual(archive_kind(Path("a.tar.gz")), "tar_gz")
        self.assertEqual(archive_kind(Path("a.tgz")), "tgz")
        self.assertEqual(archive_kind(Path("a.tar.bz2")), "tar_bz2")
        self.assertEqual(archive_kind(Path("a.tar.xz")), "tar_xz")
        self.assertEqual(archive_kind(Path("A.7Z")), "7z")
        self.assertEqual(archive_kind(Path("a.ZIP")), "zip")
        self.assertEqual(archive_kind(Path("a.rar")), "rar")
        self.assertEqual(archive_kind(Path("a.gz")), "gz")
        self.assertEqual(archive_kind(Path("a.bz2")), "bz2")
        self.assertEqual(archive_kind(Path("a.xz")), "xz")

    def test_split(self):
        self.assertEqual(archive_kind(Path("a.7z.001")), "7z")
        self.assertEqual(archive_kind(Path("a.part1.rar")), "rar")
        self.assertEqual(archive_kind(Path("a.part01.rar")), "rar")
        self.assertEqual(archive_kind(Path("a.z01")), "zip")

    def test_other(self):
        self.assertIsNone(archive_kind(Path("a.txt")))
        self.assertIsNone(archive_kind(Path("a.exe")))


if __name__ == "__main__":
    unittest.main()
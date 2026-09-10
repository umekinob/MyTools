"""単体テスト: paths（設計書 13章）。サニタイズ・Zip Slip判定。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repack_tool.paths import is_safe_entry, sanitize_name


class TestPaths(unittest.TestCase):
    def test_is_safe(self):
        self.assertTrue(is_safe_entry("a/b.txt"))
        self.assertTrue(is_safe_entry("日本語.txt"))
        self.assertFalse(is_safe_entry("../evil.txt"))
        self.assertFalse(is_safe_entry("/abs.txt"))
        self.assertFalse(is_safe_entry("..\\evil.txt"))

    def test_sanitize(self):
        self.assertEqual(sanitize_name("a:b?c"), "a_b_c")
        self.assertEqual(sanitize_name(".."), "unnamed")


if __name__ == "__main__":
    unittest.main()
"""除外判定の差分検知テスト（設計書 9.2・Q30=A）。

repack 側 `classifier._is_excluded` と `mytools_common.scan.is_excluded` の
判定一致を検証し、複写方式のドリフトを防ぐ。
asset 固有の OS システム項目（Q31=A）は許容差として明示する。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mytools_common import scan
from repack_tool.classifier import _is_excluded as repack_is_excluded
from repack_tool.config import Config


class TestScanParity(unittest.TestCase):
    def _repack(self, name: str) -> bool:
        cfg = Config(input_dir=Path("."), output_dir=Path("."))
        return repack_is_excluded(name, cfg)

    def _common(self, name: str) -> bool:
        cfg = Config(input_dir=Path("."), output_dir=Path("."))
        return scan.is_excluded(
            name, exclude_names=cfg.exclude_names,
            exclude_pattern=cfg.exclude_pattern, include_os_system=False)

    def test_parity_basic_names(self):
        names = ["普通のフォルダ", "AppData", "Thumbs.db", "desktop.ini",
                 "__pycache__", "node_modules", ".git", ".hidden", "直下.txt"]
        for n in names:
            with self.subTest(name=n):
                self.assertEqual(self._repack(n), self._common(n))

    def test_parity_dot_and_pattern(self):
        for n in [".git", ".DS_Store", "sample~", "temp_除外"]:
            with self.subTest(name=n):
                self.assertEqual(self._repack(n), self._common(n))

    def test_pattern_arg_parity(self):
        cfg = Config(input_dir=Path("."), output_dir=Path("."),
                     exclude_pattern=r"(?i)draft|beta")
        for n in ["draft_report", "beta_x", "final_report"]:
            with self.subTest(name=n):
                self.assertEqual(repack_is_excluded(n, cfg),
                                 scan.is_excluded(n, exclude_names=cfg.exclude_names,
                                                  exclude_pattern=cfg.exclude_pattern,
                                                  include_os_system=False))

    def test_os_system_items_only_in_asset(self):
        """OS システム項目は asset のみ除外（許容差・Q31=A）。"""
        self.assertTrue(scan.is_excluded("$RECYCLE.BIN", include_os_system=True))
        self.assertFalse(self._repack("$RECYCLE.BIN"))

    def test_hidden_detection(self):
        """隠し属性判定が例外なく動作する（Windows: 実属性、他: ドット規則）。"""
        from repack_tool.classifier import _is_hidden as repack_is_hidden
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "normal"
            p.mkdir()
            self.assertFalse(scan.is_hidden(p))
            self.assertFalse(repack_is_hidden(p))


if __name__ == "__main__":
    unittest.main(verbosity=2)
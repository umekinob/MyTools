# -*- coding: utf-8 -*-
"""dry-run（軽量）のテスト。解凍せず作成予定zip一覧が表示されることを検証する。"""
from __future__ import annotations

import logging
import tempfile
import unittest
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repack_tool.config import Config
from repack_tool.core import run
from repack_tool.progress import ProgressLogger


class TestDryRun(unittest.TestCase):
    """dry-run時に作成予定zip一覧が出力されることを検証。"""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="repack_dry_run_test_")
        self.in_dir = Path(self.tmpdir) / "in"
        self.out_dir = Path(self.tmpdir) / "out"
        self.in_dir.mkdir()
        self.out_dir.mkdir()
        # テスト用zip作成（フォルダ1つ）
        self._make_test_zip()

    def _make_test_zip(self) -> None:
        zip_path = self.in_dir / "test_single.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("TopFolder/file1.txt", "hello")
            zf.writestr("TopFolder/file2.txt", "world")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dry_run_lists_zip(self) -> None:
        """dry-run時に作成予定zip一覧がログに出力されること。"""
        cfg = Config(input_dir=self.in_dir, output_dir=self.out_dir,
                     dry_run=True)
        logger = ProgressLogger()
        # ログをキャプチャ
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        logs: list = []
        handler.emit = lambda record: logs.append(record.getMessage())
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.DEBUG)

        rc = run(cfg, logger)

        self.assertEqual(rc, 0)
        # 実際のzipは作成されない
        self.assertEqual(list(self.out_dir.rglob("*.zip")), [])
        # ログに作成予定zipが含まれる
        joined = "\n".join(logs)
        self.assertIn("DRY-RUN", joined)
        self.assertIn("test_single.zip", joined)
        self.assertIn("TopFolder.zip", joined)

    def test_dry_run_no_actual_files(self) -> None:
        """dry-run時に実際のファイルが作成されないこと。"""
        cfg = Config(input_dir=self.in_dir, output_dir=self.out_dir,
                     dry_run=True)
        logger = ProgressLogger()
        rc = run(cfg, logger)
        self.assertEqual(rc, 0)
        # 出力ディレクトリは空
        self.assertEqual(list(self.out_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
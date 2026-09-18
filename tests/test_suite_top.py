"""suite_top のスモークテスト（GUI非表示でロジックを検証）。"""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import suite_top.gui_top as gt


class TestSuiteTop(unittest.TestCase):
    def test_manual_path_exists(self):
        """ヘルプ用マニュアルパスが docs 配下を指すこと。"""
        self.assertEqual(gt._DOCS_MANUAL.name, "gui_manual.html")
        self.assertEqual(gt._DOCS_MANUAL.parent.name, "docs")

    def test_open_asset_spawns_process(self):
        """asset は Phase 3 実装済みのためサブプロセスで起動する。"""
        app = gt.SuiteApp()
        try:
            fake = mock.Mock()
            fake.poll.return_value = None
            app._children["asset"] = fake
            with mock.patch("suite_top.gui_top.messagebox") as mb, \
                 mock.patch("suite_top.gui_top.subprocess.Popen") as popen:
                app._open_feature("asset")
            # 既に起動済み→Popenは呼ばれない・警告ダイアログ
            popen.assert_not_called()
            mb.showinfo.assert_called_once()

            # 未起動なら asset_tool.gui を起動する
            app._children["asset"] = None
            with mock.patch("suite_top.gui_top.messagebox"), \
                 mock.patch("suite_top.gui_top.subprocess.Popen") as popen2:
                app._open_feature("asset")
            popen2.assert_called_once()
            args = popen2.call_args[0][0]
            self.assertIn("-m", args)
            self.assertIn("asset_tool.gui", args)
        finally:
            app.destroy()

    def test_open_repack_spawns_process(self):
        """repack はサブプロセスで別窓起動する。"""
        app = gt.SuiteApp()
        try:
            fake = mock.Mock()
            fake.poll.return_value = None
            app._children["repack"] = fake
            with mock.patch("suite_top.gui_top.messagebox") as mb, \
                 mock.patch("suite_top.gui_top.subprocess.Popen") as popen:
                app._open_feature("repack")
            # 既に起動済み→Popenは呼ばれない・警告ダイアログ
            popen.assert_not_called()
            mb.showinfo.assert_called_once()
        finally:
            app.destroy()


class TestGuiModulesImportable(unittest.TestCase):
    """GUI モジュールの構文・import 破損を検知する（回帰防止）。"""

    def test_gui_modules_importable(self):
        import importlib
        for name in ("suite_top.gui_top", "asset_tool.gui", "repack_tool.gui"):
            with self.subTest(module=name):
                importlib.import_module(name)


class TestSuiteCliEntry(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        return subprocess.run([sys.executable, "-m", "suite_top", *args],
                              capture_output=True, text=True, timeout=30, env=env,
                              encoding="utf-8", errors="replace")

    def test_cli_help_exits_without_gui(self):
        """--help は argparse で終了し、GUI を起動しない（回帰防止）。"""
        r = self._run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("suite_top", r.stdout)

    def test_cli_version(self):
        r = self._run("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("suite_top", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
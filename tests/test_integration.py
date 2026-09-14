"""統合テスト: サンプル21件の期待結果検証（設計書 14章 T01〜T19）。"""
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repack_tool.core import run
from repack_tool.config import Config
from repack_tool.progress import ProgressLogger


class TestIntegration(unittest.TestCase):
    def test_end_to_end(self):
        data = Path(__file__).resolve().parent / "data"
        if not (data / "in").exists():
            self.skipTest("tests/data/in がありません (make_samples.py を先行実行)")

        dest = Path(tempfile.mkdtemp()) / "out"
        cfg = Config(input_dir=data / "in", output_dir=dest,
                     password_list=data / "dict.txt", log_file=None,
                     compression_level=1)
        import logging as _logging
        _logging.getLogger("repack_tool").handlers.clear()
        logger = ProgressLogger(log_level="INFO", log_file=None, use_tty=False)
        code = run(cfg, logger)
        logger.close_all()
        _logging.getLogger("repack_tool").handlers.clear()

        # total=26, success>=22, 一部スキップのため 2 を期待
        self.assertEqual(code, 2)
        expected = [
            dest / "T01_single" / "Top.zip",
            dest / "T02_multi" / "A.zip",
            dest / "T02_multi" / "B.zip",
            dest / "T03_mixed" / "T03_mixed_files.zip",
            dest / "T04_files" / "T04_files_files.zip",
            dest / "T06_jp" / "フォルダ 名前.zip",
            dest / "T07_pw" / "SecretDir.zip",
            dest / "T09_split" / "SecretDir.zip",
            dest / "T12a" / "DirA.zip",
            dest / "T14_sub" / "a" / "Top.zip",
            dest / "T15_slip" / "T15_slip_files.zip",
            dest / "T16_nested" / "Inner.zip",
            dest / "T17_dot" / "T17_dot_files.zip",
            dest / "T23_legacy_jp" / "日本語フォルダ.zip",
            # T24〜T27: 単一フォルダ降下（パターン2〜4）
            dest / "T24_p2" / "S1.zip",
            dest / "T24_p2" / "S2.zip",
            dest / "T24_p2" / "S3.zip",
            dest / "T25_p3" / "S1.zip",
            dest / "T25_p3" / "S2.zip",
            dest / "T25_p3" / "arch.zip",
            dest / "T26_p4" / "S1.zip",
            dest / "T26_p4" / "S2.zip",
            dest / "T26_p4" / "S3.zip",
            dest / "T27_p2p" / "S1.zip",
            dest / "T27_p2p" / "S2.zip",
            dest / "T27_p2p" / "フォルダ直下.zip",
        ]
        for p in expected:
            self.assertTrue(p.is_file(), f"欠落: {p}")
        # 内容バリデーション
        with zipfile.ZipFile(dest / "T03_mixed" / "T03_mixed_files.zip") as zf:
            self.assertEqual(sorted(zf.namelist()), ["f1.txt", "f2.jpg"])
        with zipfile.ZipFile(dest / "T06_jp" / "フォルダ 名前.zip") as zf:
            self.assertIn("日本語ファイル.txt", zf.namelist())
        # T25: arch.zip は解凍されず元のまま保持されること
        with zipfile.ZipFile(dest / "T25_p3" / "arch.zip") as zf:
            self.assertEqual(sorted(zf.namelist()), ["ArchData/data.txt"])
        # T27: 直下ファイル群は「フォルダ直下.zip」にまとまること
        with zipfile.ZipFile(dest / "T27_p2p" / "フォルダ直下.zip") as zf:
            self.assertEqual(zf.namelist(), ["top.txt"])
        # T17: 隠し・ドット除外 → visible のみ
        with zipfile.ZipFile(dest / "T17_dot" / "T17_dot_files.zip") as zf:
            self.assertEqual(zf.namelist(), ["visible.txt"])
        # T23: 旧式日本語ZIPの文字化け復元 → 日本語名が復元されていること
        with zipfile.ZipFile(dest / "T23_legacy_jp" / "日本語フォルダ.zip") as zf:
            names = zf.namelist()
            self.assertIn("日本語ファイル.txt", names, f"復元された名前が含まれるべき: {names}")
        # T05(空)/T08(PW)/T11(破損) は存在しないこと
        for bad in ["T05_empty", "T08_pw_bad", "T11_corrupt", "T10_split_missing"]:
            self.assertEqual(list((dest / bad).rglob("*.zip")), [],
                             f"存在してはいけない出力: {bad}")
        shutil.rmtree(dest.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
# -*- coding: utf-8 -*-
"""dry-run（プラン）のテスト。

dry-run時に：
- 実際のファイルが作成されない
- 作成予定zip一覧がログに出力される
- 作成予定zip一覧が実処理結果と一致する（パターン1-4, 2'）
ことを検証する。
"""
from __future__ import annotations

import io
import logging
import shutil
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
        self.tmpdir = tempfile.mkdtemp(prefix="rdr_")
        self.in_dir = Path(self.tmpdir) / "in"
        self.out_dir = Path(self.tmpdir) / "out"
        self.in_dir.mkdir()
        self.out_dir.mkdir()
        with zipfile.ZipFile(self.in_dir / "test_single.zip", "w") as zf:
            zf.writestr("TopFolder/f1.txt", "hello")
            zf.writestr("TopFolder/f2.txt", "world")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---- ヘルパー ----
    def _capture(self, i: Path, o: Path) -> list:
        cfg = Config(input_dir=i, output_dir=o, dry_run=True)
        lg = ProgressLogger(log_level="DEBUG", log_file=None, use_tty=False)
        l: list = []
        h = logging.StreamHandler(); h.setLevel(logging.DEBUG)
        h.emit = lambda r: l.append(r.getMessage())
        lg.logger.addHandler(h)
        rc = run(cfg, lg)
        lg.logger.removeHandler(h); lg.close_all()
        self.assertEqual(rc, 0, f"dry-run failed: {l}")
        return l

    def _parse(self, logs: list) -> list:
        """ログからdry-run予定zipの「出力先からの相対パス(posix)」を抽出（ソート）。要約行のみ数える。

        要約行「DRY-RUN xxx -> 予定zip: a/b.zip, c.zip」に記録される
        出力先相対パスをそのまま比較単位とする（_collect と同じ）。
        """
        out: list = []
        for line in logs:
            m = line.strip()
            if "-> 予定zip:" in m:
                out.extend(p.strip().replace("\\", "/")
                           for p in m.split("-> 予定zip:", 1)[1].split(",")
                           if p.strip())
        return sorted(out)

    def _collect(self, i: Path, o: Path) -> list:
        """実処理を実行し、出力dirからの相対パス(posix、ソート)を返す。

        dry-run要約ログは「出力先からの相対パス」で記録するため、
        比較単位を相対パスに揃える。
        """
        cfg = Config(input_dir=i, output_dir=o, log_file=None, compression_level=1)
        lg = ProgressLogger(log_level="INFO", log_file=None, use_tty=False)
        rc = run(cfg, lg); lg.close_all()
        self.assertEqual(rc, 0)
        return sorted(p.relative_to(o).as_posix() for p in o.rglob("*.zip"))

    # ---- 既存 dry-run 基本テスト ----
    def test_dry_run_lists_zip(self) -> None:
        """dry-run時に作成予定zip一覧がログに出力されること。"""
        l = self._capture(self.in_dir, self.out_dir)
        self.assertEqual(list(self.out_dir.rglob("*.zip")), [])
        j = "\n".join(l).replace("\\", "/")
        self.assertIn("DRY-RUN", j)
        self.assertIn("test_single.zip", j)
        self.assertIn("test_single/TopFolder.zip", j)

    def test_dry_run_no_actual_files(self) -> None:
        """dry-run時に実際のファイルが作成されないこと。"""
        self._capture(self.in_dir, self.out_dir)
        self.assertEqual(list(self.out_dir.iterdir()), [])

    # ---- dry-run と実処理の一致検証 ----
    def _check(self, make) -> None:
        """dry-run予測と実処理結果が一致することを検証。"""
        ti = Path(tempfile.mkdtemp(prefix="drin_"))
        tr = Path(tempfile.mkdtemp(prefix="dre_"))
        td = Path(tempfile.mkdtemp(prefix="drd_"))
        ro, do = tr / "out", td / "out"
        try:
            make(ti / "src.zip")
            real = self._collect(ti, ro)
            logs = self._capture(ti, do)
            dry = self._parse(logs)
            self.assertEqual(real, dry, f"\nreal={real}\ndry={dry}\nlogs={logs}")
        finally:
            shutil.rmtree(ti, ignore_errors=True)
            shutil.rmtree(tr, ignore_errors=True)
            shutil.rmtree(td, ignore_errors=True)

        
    def test_p1(self) -> None:
        """パターン1: トップ直下に複数フォルダ -> フォルダ毎zip"""
        def m(z):
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("01/a.png", "a")
                zf.writestr("02/b.png", "b")
        self._check(m)

    def test_p2(self) -> None:
        """パターン2: 単一トップフォルダ -> 内部フォルダ毎zip"""
        def m(z):
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("D1/S1/a.txt", "a")
                zf.writestr("D1/S2/b.txt", "b")
        self._check(m)

    def test_p3(self) -> None:
        """パターン3: 単一トップフォルダ + 内部アーカイブ保持"""
        def m(z):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("ArchData/data.txt", "arch")
            inner = buf.getvalue()
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("D1/S1/a.txt", "a")
                zf.writestr("D1/S2/b.txt", "b")
                zf.writestr("D1/arch.zip", inner)
        self._check(m)

    def test_p4(self) -> None:
        """パターン4: 2重トップフォルダ -> 内部フォルダ毎zip"""
        def m(z):
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("D1/D2/S1/a.txt", "a")
                zf.writestr("D1/D2/S2/b.txt", "b")
        self._check(m)

    def test_p2p(self) -> None:
        """パターン2': 単一トップフォルダ + 直下ファイル群"""
        def m(z):
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("D1/S1/a.txt", "a")
                zf.writestr("D1/S2/b.txt", "b")
                zf.writestr("D1/top.txt", "top")
        self._check(m)


if __name__ == "__main__":
    unittest.main()

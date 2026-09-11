"""文字化け復元の単体テスト（スパイク検証用）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repack_tool.names import normalize_tree, recover_fs_name, recover_name


def make_legacy_zip(path: Path, names: list) -> None:
    """UTF-8フラグなし・cp932名の旧式ZIPを作成する。

    zipfile は非ASCII名に UTF-8 フラグを自動付与するため、
    ここでは struct でローカルヘッダ+中央ディレクトリを手組みし、
    filename フィールドに cp932 バイト列を格納する。
    """
    import struct
    import zlib

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    entries = []  # (raw_name, data, local_offset, crc)
    blob = bytearray()
    for name in names:
        raw = name.encode("cp932")
        data = b"" if name.endswith("/") else b"dummy-content"
        comp = zlib.compressobj(9, zlib.DEFLATED, -15)
        comp_data = comp.compress(data) + comp.flush()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        local_off = len(blob)
        # local file header: flag=0x000 (UTF-8フラグなし), method=8(deflate, dirは0)
        method = 0 if name.endswith("/") else 8
        blob += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0x0000, method,
                            0x2821, 0x5454, crc, len(comp_data), len(data),
                            len(raw), 0)
        blob += raw
        if method == 8:
            blob += comp_data
        # data descriptor は使わない（flag bit3 なし）
        entries.append((raw, crc, len(comp_data), len(data), local_off, method))
    cd_start = len(blob)
    cd_size = 0
    for raw, crc, csize, usize, local_off, method in entries:
        is_dir = raw.endswith(b"/")
        ext_attr = (0o40755 << 16) if is_dir else (0o600 << 16)
        n = len(blob)
        blob += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0x0000,
                            method, 0x2821, 0x5454, crc, csize, usize,
                            len(raw), 0, 0, 0, 0, ext_attr, local_off)
        blob += raw
        cd_size = len(blob) - cd_start
    cd_end = len(blob)
    blob += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries),
                        cd_size, cd_start, 0)
    path.write_bytes(bytes(blob))


class TestRecoverName(unittest.TestCase):
    def test_cp932_legacy_dir(self):
        garbled = "日本語テスト".encode("cp932").decode("cp437")
        got, conf = recover_name(garbled, strict=False)
        self.assertEqual(got, "日本語テスト")
        self.assertGreater(conf, 0)

    def test_utf8_normal_untouched(self):
        got, conf = recover_name("日本語フォルダ", strict=False)
        self.assertEqual(got, "日本語フォルダ")
        self.assertEqual(conf, 0.0)

    def test_ascii_untouched(self):
        got, conf = recover_name("PlainDir123", strict=False)
        self.assertEqual(got, "PlainDir123")
        self.assertEqual(conf, 0.0)

    def test_western_cp437_not_broken(self):
        # 純粋な西欧cp437名（日本語復号できても日本語率が低ければ維持）
        got, conf = recover_name("caf\u00e9", strict=True)
        self.assertEqual(got, "caf\u00e9")
        self.assertEqual(conf, 0.0)

    def test_normalize_tree_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            garbled = "日本語テスト".encode("cp932").decode("cp437")
            (root / garbled).mkdir()
            (root / garbled / "a.txt").write_text("x", encoding="utf-8")
            n = normalize_tree(root, logger=None)
            self.assertEqual(n, 1)
            self.assertTrue((root / "日本語テスト").is_dir())

    def test_normalize_tree_surrogate(self):
        # tar由来の化け名の復元（純粋関数レベルで検証）。
        # Windowsではサロゲート単体を含むファイル名を実ディスクに作れないため、
        # mkdirは行わず recover_fs_name の復元結果のみ確認する。
        raw = "日本語テスト".encode("cp932")
        bad = raw.decode("utf-8", "surrogateescape")
        self.assertTrue(any(0xDC80 <= ord(c) <= 0xDCFF for c in bad))
        got, conf = recover_fs_name(bad)
        self.assertEqual(got, "日本語テスト")
        self.assertGreater(conf, 0)

    def test_legacy_zip_e2e_extract(self):
        from repack_tool.config import Config
        from repack_tool.extractor import Extractor
        from repack_tool.progress import ProgressLogger
        import logging

        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)
            zpath = td_p / "legacy.zip"
            make_legacy_zip(zpath, ["日本語フォルダ/", "日本語フォルダ/日本語ファイル.txt"])
            dest = td_p / "out"
            dest.mkdir()
            cfg = Config(input_dir=td_p, output_dir=td_p / "o2")
            logger = ProgressLogger(logging.getLogger("test"))
            ex = Extractor.__new__(Extractor)
            ex.config = cfg
            ex.logger = logger
            from repack_tool.extractor import SevenZip
            ex.seven = SevenZip.__new__(SevenZip)
            ex.seven.is_available = False
            ex.seven.exe = None
            ok, reason, _ = ex.extract(zpath, "zip", dest, [])
            self.assertTrue(ok, reason)
            self.assertTrue((dest / "日本語フォルダ").is_dir())
            self.assertTrue((dest / "日本語フォルダ" / "日本語ファイル.txt").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)

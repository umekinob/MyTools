"""整合性チェック（設計書 5.3/9章）。軽量な構造チェック＋7z.exe の `7z t`。"""
from __future__ import annotations

import bz2
import gzip
import lzma
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from .config import Config


def check_archive(path: Path, kind: str, password: Optional[str] = None,
                  seven_zip: Optional["SevenZip"] = None,
                  prefer_7z: bool = False) -> Tuple[bool, bool]:
    """(ok, needs_password) を返す。needs_password は暗号化要否の事前判定。"""
    if kind == "zip":
        return _check_zip(path)
    if kind in ("tar_gz", "tgz", "tar_bz2", "tbz2", "tar_xz", "txz"):
        return _check_tar(path, kind)
    if kind in ("gz", "bz2", "xz"):
        return _check_single(path, kind)
    # 7z / rar は 7z.exe に委譲（libでの事前チェックは不安定）
    if seven_zip is not None:
        ok = seven_zip.test(path, password)
        return (ok, False)
    return (False, False)


def _check_zip(path: Path) -> Tuple[bool, bool]:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if not infos:
                return (True, False)
            encrypted = any((i.flag_bits & 0x1) for i in infos)
            # 中央ディレクトリが読める＝構造OK。データ検証は解凍時に実施
            return (True, encrypted)
    except (zipfile.BadZipFile, OSError, ValueError):
        return (False, False)


def _check_tar(path: Path, kind: str) -> Tuple[bool, bool]:
    mode = {"tar_gz": "r:gz", "tgz": "r:gz", "tar_bz2": "r:bz2",
            "tbz2": "r:bz2", "tar_xz": "r:xz", "txz": "r:xz"}[kind]
    try:
        with tarfile.open(path, mode) as tf:
            for _ in tf:  # 先頭メンバを読むことでヘッダ破損を検出
                break
        return (True, False)
    except (tarfile.TarError, OSError, EOFError, lzma.LZMAError):
        return (False, False)


def _check_single(path: Path, kind: str) -> Tuple[bool, bool]:
    opener = {"gz": gzip.open, "bz2": bz2.open, "xz": lzma.open}[kind]
    try:
        with opener(path, "rb") as f:
            f.read(1)
        return (True, False)
    except (OSError, EOFError, lzma.LZMAError, gzip.BadGzipFile):
        return (False, False)
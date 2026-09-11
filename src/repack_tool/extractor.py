"""7z.exe ラッパーと解凍エンジン（設計書 4.2/5.4）。lib優先・無ければ7z.exe。"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config
from .names import normalize_tree, recover_name
from .paths import is_safe_entry, long_path
from .progress import ProgressLogger


def _pw_reason(passwords: List[str]) -> str:
    return "password-required" if not passwords else "password-mismatch"

_DEFAULT_7Z_PATHS = [
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
]


class SevenZip:
    """7z.exe の存在解決と test/extract 実行。無ければ is_available=False。"""

    def __init__(self, explicit: Optional[str] = None):
        self.exe: Optional[Path] = None
        if explicit:
            p = Path(explicit)
            if p.is_file():
                self.exe = p
        else:
            self.exe = self._discover()
        self.is_available = self.exe is not None

    @staticmethod
    def _discover() -> Optional[Path]:
        w = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
        if w:
            return Path(w)
        for p in _DEFAULT_7Z_PATHS:
            if p.is_file():
                return p
        return None

    def _run(self, args: List[str]) -> subprocess.CompletedProcess:
        cmd = [str(self.exe), *args]
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test(self, archive: Path, password: Optional[str] = None) -> bool:
        if not self.is_available:
            return False
        args = ["t", "-y"]
        if password is not None:
            args.append(f"-p{password}")
        args.append(str(long_path(archive)))
        try:
            return self._run(args).returncode == 0
        except OSError:
            return False

    def extract(self, archive: Path, dest: Path, password: Optional[str] = None) -> bool:
        if not self.is_available:
            return False
        dest.mkdir(parents=True, exist_ok=True)
        args = ["x", "-y", f"-o{str(long_path(dest))}"]
        if password is not None:
            args.append(f"-p{password}")
        args.append(str(long_path(archive)))
        try:
            return self._run(args).returncode == 0
        except OSError:
            return False


def _try_lib_extract(archive: Path, kind: str, dest: Path, password: Optional[str],
                     logger: Optional["ProgressLogger"] = None) -> Tuple[bool, str]:
    """Python標準libでの解凍を試みる。(成功, エラー種別) を返す。"""
    try:
        if kind == "zip":
            for pw_b in _password_bytes(password):
                try:
                    _extract_zip_safe(archive, dest, pw_b, logger)
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc).lower()
                    if "password" in msg or "encrypted" in msg or isinstance(exc, RuntimeError):
                        continue  # 次の符号化候補へ（日本語PWのutf-8/cp932両対応）
                    raise
                normalize_tree(dest, logger)
                return (True, "")
            return (False, "password")
        if kind in ("tar_gz", "tgz", "tar_bz2", "tbz2", "tar_xz", "txz"):
            import tarfile
            mode = {"tar_gz": "r:gz", "tgz": "r:gz", "tar_bz2": "r:bz2",
                    "tbz2": "r:bz2", "tar_xz": "r:xz", "txz": "r:xz"}[kind]
            with tarfile.open(archive, mode) as tf:
                tf.extractall(dest, filter="data")
            normalize_tree(dest, logger)
            return (True, "")
        if kind in ("gz", "bz2", "xz"):
            return _extract_single(archive, kind, dest)
    except Exception as exc:  # noqa: BLE001 - 種別判定して継続
        msg = str(exc).lower()
        if "password" in msg or "encrypted" in msg or "bad password" in msg:
            return (False, "password")
        return (False, "corrupt")
    return (False, "unsupported")


def _password_bytes(password: Optional[str]) -> list:
    """試行するPWバイト列。日本語PWの符号化不一致に備え utf-8→cp932 の順で試す。"""
    if password is None:
        return [None]
    out: list = []
    for enc in ("utf-8", "cp932"):
        try:
            b = password.encode(enc)
        except (UnicodeEncodeError, LookupError):
            continue
        if b not in out:
            out.append(b)
    return out or [None]


def _utf8_flag(info) -> bool:
    return bool(info.flag_bits & 0x800)


def _extract_zip_safe(archive: Path, dest: Path, pw: Optional[bytes],
                      logger: Optional["ProgressLogger"] = None) -> None:
    """ZIPをエントリ単位で安全展開。UTF-8フラグなし名は文字化け復元して書く。"""
    import zipfile
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            raw_name = info.filename
            # 安全チェック（展開前）
            if not is_safe_entry(raw_name) and not raw_name.endswith("/"):
                if logger is not None:
                    logger.warning("Zip Slip/危険パス検出(スキップ): %s", raw_name)
                continue
            name = raw_name
            if not _utf8_flag(info):
                fixed, _conf = recover_name(raw_name, strict=False)
                if fixed != raw_name:
                    name = fixed
                    if logger is not None:
                        logger.warning("文字化け名を復元(zip): %s -> %s", raw_name, fixed)
            # 安全チェック（復元後）
            if not is_safe_entry(name) and not name.endswith("/"):
                if logger is not None:
                    logger.warning("Zip Slip/危険パス検出(スキップ): %s", name)
                continue
            target = (dest / Path(*name.replace("\\", "/").split("/"))).resolve() \
                if name not in ("", "/") else dest
            try:
                target.relative_to(dest.resolve())
            except ValueError:
                if logger is not None:
                    logger.warning("Zip Slip/危険パス検出(スキップ): %s", name)
                continue
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, pwd=pw) as src, open(long_path(target), "wb") as dst:
                shutil.copyfileobj(src, dst)


def _extract_single(archive: Path, kind: str, dest: Path) -> Tuple[bool, str]:
    import bz2
    import gzip
    import lzma
    opener = {"gz": gzip.open, "bz2": bz2.open, "xz": lzma.open}[kind]
    out_name = _single_out_name(archive)
    out_path = dest / out_name
    try:
        with opener(archive, "rb") as src, open(out_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return (True, "")
    except Exception:
        return (False, "corrupt")


def _single_out_name(archive: Path) -> str:
    """foo.gz -> foo / foo.tar.gz は tar系で処理済み。"""
    name = archive.name
    for suffix in (".gz", ".bz2", ".xz"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name + ".out"
def _try_7z_extract(seven: SevenZip, archive: Path, dest: Path,
                    password: Optional[str],
                    logger: Optional["ProgressLogger"] = None) -> bool:
    if not seven.is_available:
        return False
    ok = seven.extract(archive, dest, password)
    if ok:
        # 7z/rar経路（外部プロセス）でも化け名があれば正規化
        normalize_tree(dest, logger)
    return ok


class Extractor:
    """解凍エンジン。lib優先（既定）→ 7z.exeフォールバック。パスワードは辞書順に試行。"""

    def __init__(self, config: Config, logger: ProgressLogger):
        self.config = config
        self.logger = logger
        self.seven = SevenZip(config.seven_zip_path)
        if not self.seven.is_available:
            self.logger.warning("7z.exe が見つかりません。7z/rar はスキップされます")

    def extract(self, archive: Path, kind: str, dest: Path,
                passwords: List[str]) -> Tuple[bool, str, int]:
        """(成功, reason, 試行PW数) を返す。reason: ok/password-required/password-mismatch/corrupt/unsupported"""
        candidates: List[Optional[str]] = [None] + list(passwords)
        if self.config.prefer_7z and self.seven.is_available:
            for pw in candidates:
                if _try_7z_extract(self.seven, archive, dest, pw, self.logger):
                    return (True, "ok", candidates.index(pw))
            return (False, _pw_reason(passwords), len(candidates))
        # lib優先
        for pw in candidates:
            ok, err = _try_lib_extract(archive, kind, dest, pw, self.logger)
            if ok:
                return (True, "ok", candidates.index(pw))
            if err == "password":
                continue  # 次の候補へ
            # 破損等: 7z.exeで再試行（フォールバック）
            if self.seven.is_available and _try_7z_extract(self.seven, archive, dest, pw, self.logger):
                return (True, "ok", candidates.index(pw))
            return (False, "corrupt", candidates.index(pw) + 1)
        return (False, _pw_reason(passwords), len(candidates))
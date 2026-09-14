"""検証用サンプル生成（設計書 14章: T01〜T22）。python tests/make_samples.py で作成。"""
from __future__ import annotations

import bz2
import gzip
import lzma
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

DATA_ROOT = Path(__file__).parent / "data"
IN = DATA_ROOT / "in"
OUT = DATA_ROOT / "out"

SEVEN_ZIP_CANDIDATES = [
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
]


def find_7z() -> Path | None:
    w = shutil.which("7z") or shutil.which("7za")
    if w:
        return Path(w)
    for c in SEVEN_ZIP_CANDIDATES:
        if c.is_file():
            return c
    return None


def _write_zip(zip_path: Path, entries: dict, compress=True) -> None:
    """entries: {arcname: bytes or None(空フォルダ)}"""
    with zipfile.ZipFile(zip_path, "w",
                         compression=zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED) as zf:
        for name, content in entries.items():
            if content is None:
                zi = zipfile.ZipInfo(name.rstrip("/") + "/")
                zf.writestr(zi, b"")
            else:
                zf.writestr(name, content)


def _write_tar(tar_path: Path, mode: str, entries: dict) -> None:
    with tarfile.open(tar_path, mode) as tf:
        for name, content in entries.items():
            if content is None:
                ti = tarfile.TarInfo(name + "/")
                tf.addfile(ti)
            else:
                data = content.encode("utf-8")
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                tf.addfile(ti, _ByteStream(data))


class _ByteStream:
    def __init__(self, data: bytes):
        self.data = data

    def __len__(self):
        return len(self.data)

    def read(self, n=-1):
        if n is None or n < 0:
            n = len(self.data)
        out = self.data[:n]
        self.data = self.data[n:]
        return out


def _run_7z(seven: Path, args) -> bool:
    try:
        r = subprocess.run([str(seven), *args], capture_output=True)
        return r.returncode == 0
    except OSError:
        return False


def _write_legacy_jp_zip(zip_path: Path, entries: dict) -> None:
    """旧式日本語ZIPを作成する（cp932名＋UTF-8フラグなし）。

    ``ZipFile.open`` で書き込むことで、DEFLATE 圧縮と UTF-8 フラグオフを確実に反映する。
    """
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in entries.items():
            # cp932 バイト列を復元してファイル名にする
            raw = name.encode("cp932")
            arcname = raw.decode("cp932")
            zinfo = zipfile.ZipInfo(filename=arcname)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            # UTF-8 フラグを明示的にオフ（旧式互換）
            zinfo.flag_bits &= ~0x800
            # writestr は data が str の場合に内部で UTF-8 エンコードするため、
            # バイト列に変換してから open で書き込む（DEFLATE 圧縮を確実に適用）
            bdata = data.encode("utf-8") if isinstance(data, str) else data
            with zf.open(zinfo, "w") as f:
                f.write(bdata)


def main(clean: bool = True) -> dict:
    keep = DATA_ROOT / ".gitkeep"
    keep_bytes = keep.read_bytes() if keep.exists() else None
    if clean and DATA_ROOT.exists():
        shutil.rmtree(DATA_ROOT)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    if keep_bytes is not None:
        keep.write_bytes(keep_bytes)
    IN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    seven = find_7z()
    results = {}

    # パスワード辞書（T07用。T08は辞書外のパスワードで暗号化済み → mismatch）
    (DATA_ROOT / "dict.txt").write_text(
        "# テスト用パスワード辞書（ダミー。実パスワードを置かないこと）\nsecret\n",
        encoding="utf-8")

    # T01: 単一フォルダ
    _write_zip(IN / "T01_single.zip",
               {"Top/note.txt": "hello"})
    # T02: 複数フォルダ
    _write_zip(IN / "T02_multi.zip",
               {"A/a.txt": "a", "B/b.txt": "b"})
    # T03: 混在（フォルダ＋ファイル）
    _write_zip(IN / "T03_mixed.zip",
               {"A/a.txt": "a", "f1.txt": "f1", "f2.jpg": "f2"})
    # T04: ファイルのみ
    _write_zip(IN / "T04_files.zip",
               {"x.txt": "x", "y.png": "y", "z.md": "z"})
    # T05: 空フォルダのみ
    _write_zip(IN / "T05_empty.zip", {"EmptyDir/": None})
    # T06: 日本語・空白
    _write_zip(IN / "T06_jp.zip",
               {"フォルダ 名前/日本語ファイル.txt": "日本語コンテンツ",
                "スペース ファイル.txt": "space"})
    # T07/T08: パスワード付きzip（ZipCrypto）
    pw_src = IN / "_pw_src"
    (pw_src / "SecretDir").mkdir(parents=True, exist_ok=True)
    (pw_src / "SecretDir" / "s.txt").write_text("s3cret", encoding="utf-8")
    if seven is not None:
        _run_7z(seven, ["a", "-tzip", "-mem=ZipCrypto", "-psecret",
                        str(IN / "T07_pw.zip"), str(pw_src / "SecretDir")])
        # T08: 異なるパスワードで暗号化（辞書に無い → mismatch）
        _run_7z(seven, ["a", "-tzip", "-mem=ZipCrypto", "-pwrongpass",
                        str(IN / "T08_pw_bad.zip"), str(pw_src / "SecretDir")])
        # T09/T10: 分割7z（揃っている / 欠巻）収まるよう400KBのダミーを用意
        big = pw_src / "SecretDir" / "big.bin"
        big.write_bytes(os.urandom(400 * 1024))
        for name in ("T09_split", "T10_split_missing"):
            for old in IN.glob(f"{name}.7z.*"):
                old.unlink()
            _run_7z(seven, ["a", "-v100k", str(IN / f"{name}.7z"), str(pw_src / "SecretDir")])
        # T10: 先頭巻のみ残し欠けを作る
        for f in IN.glob("T10_split_missing.7z.*"):
            if f.name != "T10_split_missing.7z.001":
                f.unlink()
    shutil.rmtree(pw_src, ignore_errors=True)

    # T11 破損zip
    zip_path = IN / "T11_corrupt.zip"
    _write_zip(zip_path, {"d/d.txt": "data" * 100})
    data = zip_path.read_bytes()
    zip_path.write_bytes(data[: len(data) // 2])

    # T12 tar系
    _write_tar(IN / "T12a.tar.gz", "w:gz", {"DirA/a.txt": "ta"})
    _write_tar(IN / "T12b.tar.bz2", "w:bz2", {"DirB/b.txt": "tb"})
    _write_tar(IN / "T12c.tar.xz", "w:xz", {"DirC/c.txt": "tc"})
    _write_tar(IN / "T12d.tgz", "w:gz", {"DirD/d.txt": "td"})

    # T15 Zip Slip
    _write_zip(IN / "T15_slip.zip", {"../evil.txt": "evil", "ok.txt": "ok"})

    # T16 入れ子
    inner_tmp = IN / "inner_tmp"
    inner_tmp.mkdir(exist_ok=True)
    _write_zip(inner_tmp / "inner.zip", {"Inner/inner.txt": "nested"})
    _write_zip(IN / "T16_nested.zip", {"inner.zip": (inner_tmp / "inner.zip").read_bytes(),
                                        "f.txt": "outer"})
    shutil.rmtree(inner_tmp, ignore_errors=True)

    # T17 隠し・ドット
    _write_zip(IN / "T17_dot.zip",
               {".hidden": "h", ".git/config": "g", "visible.txt": "v"})

    # T19 同名Dir（T13用の先勝ちは実行側で out に Dir.zip を事前配置）
    _write_zip(IN / "T13_conflict.zip", {"Dir/d1.txt": "c1"})
    _write_zip(IN / "T19_same.zip", {"Dir/d2.txt": "c2"})

    # T14 再帰（サブフォルダ）
    sub = IN / "T14_sub"
    sub.mkdir(exist_ok=True)
    _write_zip(sub / "a.zip", {"Top/t.txt": "t"})

    # T23: 旧式日本語ZIP（cp932名＋UTF-8フラグなし → 文字化け復元の検証）
    _write_legacy_jp_zip(IN / "T23_legacy_jp.zip",
                         {"日本語フォルダ/日本語ファイル.txt": "復元される内容",
                          "資料/メモ.txt": "メモ内容"})

    # T24: 単一トップフォルダ → 内部複数フォルダ（パターン2）
    #      期待: S1.zip, S2.zip, S3.zip
    _write_zip(IN / "T24_p2.zip",
               {"D1/S1/a.txt": "a", "D1/S2/b.txt": "b", "D1/S3/c.txt": "c"})

    # T25: 単一トップフォルダ → 内部複数フォルダ＋アーカイブ保持（パターン3）
    #      期待: S1.zip, S2.zip, arch.zip(保持コピー)
    arch_tmp = IN / "_arch_tmp"
    arch_tmp.mkdir(exist_ok=True)
    _write_zip(arch_tmp / "arch.zip", {"ArchData/data.txt": "arch"})
    _write_zip(IN / "T25_p3.zip",
               {"D1/S1/a.txt": "a", "D1/S2/b.txt": "b",
                "D1/arch.zip": (arch_tmp / "arch.zip").read_bytes()})
    shutil.rmtree(arch_tmp, ignore_errors=True)

    # T26: 単一トップフォルダが2重 → 内部複数フォルダ（パターン4）
    #      期待: S1.zip, S2.zip, S3.zip
    _write_zip(IN / "T26_p4.zip",
               {"D1/D2/S1/a.txt": "a", "D1/D2/S2/b.txt": "b",
                "D1/D2/S3/c.txt": "c"})

    # T27: 単一トップフォルダ → 内部複数フォルダ＋直下ファイル群（パターン2'）
    #      期待: S1.zip, S2.zip, フォルダ直下.zip
    _write_zip(IN / "T27_p2p.zip",
               {"D1/S1/a.txt": "a", "D1/S2/b.txt": "b", "D1/top.txt": "top"})

    results["seven_zip"] = str(seven) if seven else None
    return results


if __name__ == "__main__":
    r = main()
    print(f"サンプル生成完了: {DATA_ROOT}")
    print(f"7z.exe: {r.get('seven_zip') or '利用不可（T07-T10生成スキップ）'}")
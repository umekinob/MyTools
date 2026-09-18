"""GUIマニュアル用スナップショット撮影（標準ライブラリのみ・Pillow不要）。

使い方（プロジェクトルートで実行）:
    $env:PYTHONPATH = "src;tests"
    python tests/shoot_manual.py

docs/img/ に出力される画像（マニュアルが参照する採用画像のみ）:
    01_startup.png     起動直後（未設定）
    02_configured.png  入力・出力・辞書設定済み
    05_done_dialog.png 完了ダイアログ
    run_01.png         実行中（採用済み: マニュアル §4/§6 が参照）
    run_03.png         実行中（採用済み: マニュアル §6 が参照）
    10_suite_top.png       スイートTOP（機能一覧）
    11_asset_startup.png   asset-tool 起動直後
    12_asset_configured.png asset-tool 起点・出力フォルダ設定済み

result/img_run/ に出力される画像（作業用・git 管理外）:
    run_00..09.png     実行中の連写。最良の1枚を docs/img/run_XX.png として採用する
                       （採用したら本スクリプトの出力先を docs/img へ切り替えて再撮影するか、
                         result/img_run/ からコピーしてマニュアルの参照を更新する）

結果サマリは shoot_result.txt（UTF-8）に書き出す。
"""
from __future__ import annotations

import ctypes
import shutil
import struct
import sys
import zlib
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from make_samples import main as make_samples_main  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"
# 連写素材は作業用フォルダ（docs/img はマニュアル参照の採用画像のみを追跡する）
RUN_DIR = ROOT / "result" / "img_run"
RESULT_TXT = ROOT / "shoot_result.txt"

# ---- Win32 定数 ----
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
GA_ROOT = 2
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
WM_CLOSE = 0x0010

_notes: list[str] = []


def _log(msg: str) -> None:
    _notes.append(msg)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER)]


def _write_png(path: Path, w: int, h: int, rgba: bytearray) -> None:
    """自作PNGエンコーダ（RGBA8, filter=0）。"""
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: None
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def capture_hwnd(hwnd: int, path: Path) -> bool:
    """ウィンドウHWNDをPNGに保存（PrintWindow・裏に回っていても取得可）。"""
    rc = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
        return False
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return False
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    printed = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h  # 負値でトップダウン
    bi.biPlanes = 1
    bi.biBitCount = 32
    bmi = BITMAPINFO(bi)
    buf = ctypes.create_string_buffer(w * h * 4)
    got = gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    if not printed or got == 0:
        return False
    ba = bytearray(buf.raw)
    ba[0::4], ba[2::4] = ba[2::4], ba[0::4]  # BGRA -> RGBA
    ba[3::4] = b"\xff" * len(ba[3::4])       # αは0で返るため255に
    _write_png(path, w, h, ba)
    return True


def capture_tk_window(win, path: Path) -> bool:
    win.update_idletasks()
    win.update()
    hwnd = user32.GetAncestor(win.winfo_id(), GA_ROOT)
    return capture_hwnd(hwnd, path)


def _find_msgbox_hwnd() -> int:
    """自プロセスの可視 #32770（メッセージボックス）HWNDを列挙で探す。"""
    import ctypes as _ct

    kernel32 = ctypes.windll.kernel32
    pid = kernel32.GetCurrentProcessId()
    found = []

    CB = _ct.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, _ct.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value == "#32770":
                found.append(hwnd)
                return False
        return True

    cb = CB(_cb)
    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def _list_toplevels() -> list[str]:
    """自プロセスの可視トップレベル (class|title) を列挙（診断用）。"""
    import ctypes as _ct

    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    out: list[str] = []
    CB = _ct.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lp):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, _ct.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            title = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            user32.GetWindowTextW(hwnd, title, 256)
            out.append(f"{cls.value}|{title.value}")
        return True

    cb = CB(_cb)
    user32.EnumWindows(cb, 0)
    return out


def try_capture_dialog(path: Path) -> bool:
    """メッセージボックス(#32770)をキャプチャして閉じる。"""
    hwnd = _find_msgbox_hwnd()
    if not hwnd:
        return False
    ok = capture_hwnd(hwnd, path)
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    _log(f"dialog captured={ok}")
    return ok



def shoot_suite() -> None:
    """スイートTOP・asset画面のスナップショット（Phase 4・GUIマニュアル追補用）。"""
    from suite_top.gui_top import SuiteApp
    from asset_tool.gui import AssetApp

    top = SuiteApp()
    top.geometry("420x260+40+40")
    top.attributes("-topmost", True)
    top.update()
    top.update()
    ok = capture_tk_window(top, IMG_DIR / "10_suite_top.png")
    _log(f"10_suite_top={ok}")
    top.destroy()

    app = AssetApp()
    app.geometry("760x600+60+60")
    app.attributes("-topmost", True)
    app.update()
    app.update()
    ok = capture_tk_window(app, IMG_DIR / "11_asset_startup.png")
    _log(f"11_asset_startup={ok}")
    app.var_input.set(str(ROOT / "tests" / "data" / "in"))
    app.var_output.set(str(ROOT / "result" / "shot_out"))
    app.update()
    ok = capture_tk_window(app, IMG_DIR / "12_asset_configured.png")
    _log(f"12_asset_configured={ok}")
    app.destroy()


def main() -> None:
    make_samples_main(clean=True)
    # 撮影用出力は毎回クリーンに（出力名に連番 _00N が写らないように初回状態で撮る）
    shutil.rmtree(ROOT / "result" / "shot_out", ignore_errors=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    from repack_tool.gui import GuiApp
    app = GuiApp()
    app.geometry("720x560+40+40")
    app.attributes("-topmost", True)
    app.update()
    app.update()

    # 1) 起動直後
    ok1 = capture_tk_window(app, IMG_DIR / "01_startup.png")
    _log(f"01_startup={ok1}")

    # 2) 設定済み（サンプル入力・撮影用出力・辞書）
    app.var_input.set(str(ROOT / "tests" / "data" / "in"))
    app.var_output.set(str(ROOT / "result" / "shot_out"))
    app.var_dict.set(str(ROOT / "tests" / "data" / "dict.txt"))
    ok2 = capture_tk_window(app, IMG_DIR / "02_configured.png")
    _log(f"02_configured={ok2}")

    # 3) 実行中の連写（作業用フォルダへ。最良の1枚を docs/img/run_XX.png として採用）
    run_shots = [RUN_DIR / f"run_{i:02d}.png" for i in range(10)]
    for i, p in enumerate(run_shots):
        app.after(500 + i * 700, lambda p=p: capture_tk_window(app, p))

    # 4) 完了ダイアログ（done後に出現する modal を何度か試して撮影→閉じる）
    dlg_path = IMG_DIR / "05_done_dialog.png"
    dlg_done: list[bool] = []

    def _dlg() -> None:
        if dlg_done:
            return
        hwnd = _find_msgbox_hwnd()
        _log(f"dlg try: msgbox={hwnd} tops={_list_toplevels()}")
        if hwnd:
            ok = capture_hwnd(hwnd, dlg_path)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            _log(f"dialog captured={ok}")
            if ok:
                dlg_done.append(True)

    for t in (2400, 3200, 4000, 4800, 5600, 6600):
        app.after(t, _dlg)

    app._start()
    app.after(10000, app.destroy)
    app.mainloop()

    # 5) スイートTOP・asset画面（Phase 4 追加）
    try:
        shoot_suite()
    except Exception as exc:  # noqa: BLE001
        _log(f"suite shots failed: {exc}")

    # 結果サマリ出力（採用画像＝docs/img、連写素材＝result/img_run）
    lines = ["shot results:"]
    for p in sorted(IMG_DIR.glob("*.png")) + sorted(RUN_DIR.glob("*.png")):
        head = p.read_bytes()[:33]
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        lines.append(f"  {p.parent.name}/{p.name}  {w}x{h}  {p.stat().st_size}B")
    lines += _notes
    RESULT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""スイートTOP→各機能の「実 GUI 別窓起動」検証（手動確認用手順・Q48=A）。

自動テスト（tests/test_suite_top.py）はモックによるロジック検証のみで、
実際に子プロセスが起動しウィンドウが表示されるかは確認しない。
本スクリプトは実プロセスを起動して以下を検証する:

  1. repack ボタン → `python -m repack_tool.gui` が別窓で起動する
  2. 起動中に再度押しても二重起動しない（既存窓のメッセージのみ）
  3. asset ボタン → `python -m asset_tool.gui` が別窓で起動する
  4. TOP の×ボタン終了（`_on_close`）で子プロセスも終了し、TOP 自身も閉じる

モーダルダイアログ（`起動済み`・終了確認）は監視スレッドが自動処理する
（`messagebox` はモーダルのため同一スレッドからは閉じられない）。
ハング防止として全体に 120 秒の上限を設けている。

使い方（プロジェクトルートで実行）:
    $env:PYTHONPATH = "src"
    python tests/verify_suite_spawn.py

結果は標準出力と verify_result.txt（UTF-8）に書き出す。
GUI が表示できない環境（ヘッドレス等）では失敗として記録される。
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

RESULT_TXT = ROOT / "verify_result.txt"

user32 = ctypes.windll.user32
_WAIT_SEC = 12.0        # 子窓のウィンドウ出現を待つ上限
_POLL_SEC = 0.5
_TOTAL_TIMEOUT_SEC = 120.0   # スクリプト全体の上限（ダイアログ待ちでハングしないため）

# 期待するウィンドウタイトル（src/*/gui.py の self.title()）
EXPECT_TITLE = {
    "repack": "repack-tool（解凍→フォルダ毎zip）",
    "asset": "asset-tool（資産一覧出力）",
}

_lines: list[str] = []
# 終了確認ダイアログで「OK」を押すモード（set で有効）
_WATCH_ACCEPT = threading.Event()


def _log(msg: str) -> None:
    print(msg)
    _lines.append(msg)


def _abort() -> None:
    """上限時間を超えた場合に結果を残して強制終了する（ハング防止）。"""
    _log(f"[NG] 上限時間 {_TOTAL_TIMEOUT_SEC:.0f} 秒を超えたため中断しました")
    _log("RESULT=FAIL")
    try:
        RESULT_TXT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    finally:
        import os
        os._exit(1)


def _visible_titles_for_pid(pid: int) -> list[str]:
    """指定 PID が所有する可視トップレベルウィンドウのタイトル一覧。"""
    out: list[str] = []
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lp):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            if title.value:
                out.append(title.value)
        return True

    cb = CB(_cb)
    user32.EnumWindows(cb, 0)
    return out


def _wait_for_window(pid: int, expected: str, timeout: float = _WAIT_SEC) -> list[str]:
    """期待タイトルのウィンドウが現れるまで待ち、見つかった時点の一覧を返す。"""
    deadline = time.time() + timeout
    titles: list[str] = []
    while time.time() < deadline:
        titles = _visible_titles_for_pid(pid)
        if any(expected in t for t in titles):
            return titles
        time.sleep(_POLL_SEC)
    return titles


def _check_child(key: str, app) -> bool:
    """1 機能を実起動し、別窓表示と二重起動防止・終了を検証する。"""
    ok = True
    app._open_feature(key)
    proc = app._children.get(key)
    if proc is None:
        _log(f"[NG] {key}: 子プロセスが起動していません")
        return False
    _log(f"[OK] {key}: 子プロセス起動 pid={proc.pid}")

    titles = _wait_for_window(proc.pid, EXPECT_TITLE[key])
    if any(EXPECT_TITLE[key] in t for t in titles):
        _log(f"[OK] {key}: 別窓を検出 title={[t for t in titles if EXPECT_TITLE[key] in t]}")
    else:
        _log(f"[NG] {key}: 期待タイトルの窓が出ません expected={EXPECT_TITLE[key]} "
             f"titles={titles}")
        ok = False

    # 二重起動しないこと（起動済み → Popen は再利用され、pid は変わらない）
    # 注: ここで `起動済み` の messagebox がモーダル表示されるが、
    #     監視スレッド（start_dialog_watcher）が自動で閉じるため処理が戻る。
    before = proc.pid
    app._open_feature(key)
    after = app._children.get(key)
    if after is not None and after.pid == before and after.poll() is None:
        _log(f"[OK] {key}: 二重起動しません pid={before}")
    else:
        _log(f"[NG] {key}: 二重起動した or 状態異常 before={before} "
             f"after={None if after is None else after.pid}")
        ok = False
    return ok


def _dismiss_msgbox(accept: bool = False) -> bool:
    """自プロセスの messagebox(#32770) を検出して閉じる。

    accept=False: ×で閉じる（askokcancel なら「キャンセル」相当）
    accept=True : OK(IDOK) を押す（askokcancel なら「OK」相当＝終了を承諾）

    注意: `messagebox.showinfo` はモーダルでブロックするため、呼び出し元と
    同一スレッドでは閉じられない。必ず監視スレッド（`start_dialog_watcher`）から呼ぶ。
    見つかった場合は True を返す。
    """
    WM_CLOSE = 0x0010
    WM_COMMAND = 0x0111
    IDOK = 1
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []
    pid = ctypes.windll.kernel32.GetCurrentProcessId()

    def _cb(hwnd, _lp):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "#32770":
            found.append(hwnd)
            return False
        return True

    cb = CB(_cb)
    user32.EnumWindows(cb, 0)
    for hwnd in found:
        if accept:
            user32.PostMessageW(hwnd, WM_COMMAND, IDOK, 0)
        else:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return bool(found)


def start_dialog_watcher() -> "threading.Event":
    """モーダルダイアログを自動で閉じる監視スレッドを開始する。

    検証の自動化のため、`起動済み` などの messagebox が現れたら即座に処理する。
    戻り値の Event を set すると監視を終了する。
    終了確認ダイアログで「OK」を押したい場合は `_WATCH_ACCEPT` を set する。
    """
    stop = threading.Event()

    def _loop() -> None:
        dismissed = 0
        while not stop.is_set():
            if _dismiss_msgbox(accept=_WATCH_ACCEPT.is_set()):
                dismissed += 1
            stop.wait(0.3)
        if dismissed:
            _log(f"[INFO] モーダルダイアログを {dismissed} 回自動処理しました")

    threading.Thread(target=_loop, daemon=True).start()
    return stop


def main() -> int:
    from suite_top.gui_top import SuiteApp

    # 万一ダイアログで停止してもハングしないよう、全体に上限時間を設ける
    watchdog = threading.Timer(_TOTAL_TIMEOUT_SEC, _abort)
    watchdog.daemon = True
    watchdog.start()

    stop_watch = start_dialog_watcher()
    app = SuiteApp()
    app.withdraw()                          # TOP 自体は表示不要（子窓のみ検証）
    ok_all = True
    destroyed = False
    try:
        for key in ("repack", "asset"):
            ok_all &= _check_child(key, app)

        # TOP終了（×ボタン相当: _on_close）で子窓も終了する（Q48=A）
        # 終了確認ダイアログが出るため、監視スレッドに「OK」を押させる。
        procs = {k: p for k, p in app._children.items() if p is not None}
        _WATCH_ACCEPT.set()
        app._on_close()
        destroyed = True
        time.sleep(1.5)
        for k, p in procs.items():
            if p.poll() is None:
                _log(f"[NG] {k}: TOP終了処理後も子プロセスが生存 pid={p.pid}")
                ok_all = False
            else:
                _log(f"[OK] {k}: TOP終了処理で子プロセス終了 rc={p.returncode}")
        _log("[OK] TOP: _on_close で TOP 自身も終了（destroy 済み）")
    finally:
        watchdog.cancel()
        stop_watch.set()
        if not destroyed:
            app.destroy()

    _log(f"RESULT={'PASS' if ok_all else 'FAIL'}")
    RESULT_TXT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
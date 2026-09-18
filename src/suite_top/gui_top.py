"""TOP画面（設計書 7.1・Q4=A: 選択・起動のみ）。

既存 repack GUI（GuiApp(tk.Tk)）は変更しないため（Q1=B）、
機能ごとにサブプロセス（`python -m repack_tool.gui`）で別窓起動する。
同一機能の窓は同時に1つだけとし、既に起動済みの場合は再起動しない（Q48=A）。
TOPを閉じたときは起動した子窓も終了する（Q48=A）。
"""
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, Optional

from repack_tool import __version__ as REPACK_VERSION

_SRC_DIR = Path(__file__).resolve().parent.parent
_DOCS_MANUAL = _SRC_DIR.parent / "docs" / "gui_manual.html"


class SuiteApp(tk.Tk):
    """機能選択・起動のみを担うTOP画面。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("作業効率化ツール TOP")
        self.geometry("420x260")
        self._children: Dict[str, Optional[subprocess.Popen]] = {}

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="作業効率化ツール",
                  font=("", 14, "bold")).pack(anchor=tk.W, pady=(0, 8))

        # ---- 機能一覧（概要1行＋「開く」ボタン）----
        features = [
            ("repack", "解凍→フォルダ毎zip",
             "圧縮ファイルを解凍しフォルダ毎にzip再圧縮"),
            ("asset", "資産一覧出力",
             "フォルダ資産の台帳をCSV/HTML/MD出力"),
        ]
        for key, label, desc in features:
            row = ttk.Frame(frm)
            row.pack(fill=tk.X, pady=4)
            info = ttk.Frame(row)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(info, text=label, font=("", 10, "bold")).pack(anchor=tk.W)
            ttk.Label(info, text=desc).pack(anchor=tk.W)
            ttk.Button(row, text="開く",
                       command=lambda k=key: self._open_feature(k)).pack(side=tk.RIGHT)

        # ---- バージョン / ヘルプ ----
        foot = ttk.Frame(frm)
        foot.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(foot, text="ヘルプ", command=self._open_help).pack(side=tk.LEFT)
        ttk.Label(foot, text=f"version {REPACK_VERSION}").pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 機能起動 ----
    def _open_feature(self, key: str) -> None:
        proc = self._children.get(key)
        if proc is not None and proc.poll() is None:
            messagebox.showinfo("起動済み", "この機能の窓は既に開いています")
            return
        module = {"repack": "repack_tool.gui", "asset": "asset_tool.gui"}[key]
        cmd = [sys.executable, "-m", module]
        env_extra = {"PYTHONPATH": str(_SRC_DIR)}
        try:
            self._children[key] = subprocess.Popen(cmd, env={
                **__import__("os").environ, **env_extra})
        except OSError as exc:
            messagebox.showerror("起動エラー", f"機能の起動に失敗しました: {exc}")

    def _open_help(self) -> None:
        """ヘルプ（GUIマニュアル）を既定ブラウザで開く（Q49=A）。"""
        import webbrowser
        if _DOCS_MANUAL.exists():
            webbrowser.open(_DOCS_MANUAL.as_uri())
        else:
            messagebox.showwarning("未検出", f"マニュアルが見つかりません:\n{_DOCS_MANUAL}")

    # ---- 終了処理（Q48=A: TOP終了時は子窓も終了）----
    def _on_close(self) -> None:
        running = [k for k, p in self._children.items()
                   if p is not None and p.poll() is None]
        if running:
            ok = messagebox.askokcancel(
                "終了確認", "機能の窓が開いています。TOPを終了すると一緒に閉じます。よろしいですか？")
            if not ok:
                return
        self._terminate_children()
        self.destroy()

    def _terminate_children(self) -> None:
        for proc in self._children.values():
            if proc is not None and proc.poll() is None:
                proc.terminate()
        self._children.clear()


def main() -> None:
    app = SuiteApp()
    app.mainloop()


if __name__ == "__main__":
    main()
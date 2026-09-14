"""GUIラッパー（設計書 9章）。CLI/Coreをimportする薄いラッパー（tkinter＋ドラッグ&ドロップ対応想定）。
使い方: python -m repack_tool.gui
Windows の素の tkinter には DnD が無いため、任意依存 `tkinterdnd2` があれば
有効化し、無ければファイル選択ダイアログのみで動作する（Q48）。
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repack_tool.config import Config
from repack_tool.core import run
from repack_tool.progress import ProgressLogger


class GuiApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("repack-tool（解凍→フォルダ毎zip）")
        self.geometry("720x560")
        self._running = False
        self._queue: "queue.Queue[tuple]" = queue.Queue()

        # ---- 入力・出力 ----
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.X)
        self.var_input = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_dict = tk.StringVar()
        self.var_temp = tk.StringVar()
        self._row(frm, 0, "入力フォルダ", self.var_input, self._pick_input)
        self._row(frm, 1, "出力フォルダ", self.var_output, self._pick_output)
        self._row(frm, 2, "辞書(任意)", self.var_dict, self._pick_dict)
        self._row(frm, 3, "一時フォルダ(任意)", self.var_temp, self._pick_temp)
        ttk.Label(frm, text="※ 入力へドラッグ&ドロップ可（tkinterdnd2導入時）").grid(
            row=4, column=0, columnspan=3, sticky=tk.W)

        # ---- オプション ----
        opt = ttk.LabelFrame(self, text="オプション", padding=8)
        opt.pack(fill=tk.X, padx=8)
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_prefer7z = tk.BooleanVar(value=False)
        self.var_flat = tk.BooleanVar(value=False)
        self.var_dryrun = tk.BooleanVar(value=False)
        self.var_keeptemp = tk.BooleanVar(value=False)
        self.var_level = tk.IntVar(value=9)
        self.var_loglevel = tk.StringVar(value="INFO")
        ttk.Checkbutton(opt, text="再帰探索", variable=self.var_recursive).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(opt, text="7z優先", variable=self.var_prefer7z).grid(row=0, column=1, sticky=tk.W)
        ttk.Checkbutton(opt, text="平坦出力", variable=self.var_flat).grid(row=0, column=2, sticky=tk.W)
        ttk.Checkbutton(opt, text="DRY-RUN", variable=self.var_dryrun).grid(row=1, column=0, sticky=tk.W)
        ttk.Checkbutton(opt, text="一時保持", variable=self.var_keeptemp).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(opt, text="圧縮レベル").grid(row=1, column=2, sticky=tk.E)
        ttk.Spinbox(opt, from_=0, to=9, textvariable=self.var_level, width=4).grid(row=1, column=3)
        ttk.Label(opt, text="ログレベル").grid(row=0, column=2, sticky=tk.E)
        ttk.Combobox(opt, textvariable=self.var_loglevel,
                     values=["DEBUG", "INFO", "WARNING", "ERROR"],
                     state="readonly", width=8).grid(row=0, column=3)

        # ---- 実行 ----
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill=tk.X)
        self.btn_run = ttk.Button(bar, text="実行", command=self._start)
        self.btn_run.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(bar, text="中止", command=self._stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=8)
        self.progress = ttk.Progressbar(bar, orient="horizontal", mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # ---- ログビュー ----
        log_frame = ttk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.log = tk.Text(log_frame, height=16, state=tk.DISABLED)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btn_clear = ttk.Button(log_frame, text="ログクリア", command=self._clear_log)
        btn_clear.pack(side=tk.RIGHT, anchor=tk.N, padx=(8, 0))

        self._enable_dnd()
        self.after(100, self._pump)
    def _row(self, parent, r, label, var, cmd):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=var, width=60).grid(row=r, column=1, sticky=tk.EW)
        ttk.Button(parent, text="参照", command=cmd).grid(row=r, column=2)
        parent.columnconfigure(1, weight=1)

    def _pick_input(self):
        d = filedialog.askdirectory()
        if d:
            self.var_input.set(d)

    def _pick_output(self):
        d = filedialog.askdirectory()
        if d:
            self.var_output.set(d)

    def _pick_dict(self):
        f = filedialog.askopenfilename(filetypes=[("text", "*.txt"), ("all", "*.*")])
        if f:
            self.var_dict.set(f)

    def _pick_temp(self):
        initial = self.var_temp.get() or str(Path.home())
        d = filedialog.askdirectory(
            title="一時フォルダを選択（無指定なら本プログラムの tmp/）",
            initialdir=initial)
        if d:
            self.var_temp.set(d)

    def _enable_dnd(self):
        # tkinterdnd2 があれば入力欄へのDnDを有効化
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore
        except Exception:
            return

        def _drop(event):
            paths = self.tk.splitlist(event.data)
            if paths:
                p = Path(paths[0])
                self.var_input.set(str(p if p.is_dir() else p.parent))

        try:
            self.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.dnd_bind("<<Drop>>", _drop)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        """GUIのログテキストをクリア（ログファイルはそのまま）。"""
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _pump(self):
        try:
            while True:
                kind, *rest = self._queue.get_nowait()
                if kind == "progress":
                    cur, total, msg = rest
                    self.progress.configure(maximum=max(total, 1), value=cur)
                    self._append_log(f"[{cur}/{total}] {msg}")
                elif kind == "log":
                    self._append_log(rest[0])
                elif kind == "done":
                    code = rest[0]
                    self._running = False
                    self.btn_run.configure(state=tk.NORMAL)
                    self.btn_stop.configure(state=tk.DISABLED)
                    self._append_log(f"終了コード: {code}")
                    messagebox.showinfo("完了", f"終了コード: {code}")
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _start(self):
        if self._running:
            return
        if not self.var_input.get() or not self.var_output.get():
            messagebox.showwarning("入力不足", "入力・出力フォルダを指定してください")
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path(self.var_output.get())
        cfg = Config(
            input_dir=Path(self.var_input.get()),
            output_dir=out,
            password_list=Path(self.var_dict.get()) if self.var_dict.get() else None,
            recursive=self.var_recursive.get(),
            prefer_7z=self.var_prefer7z.get(),
            flat=self.var_flat.get(),
            dry_run=self.var_dryrun.get(),
            keep_temp=self.var_keeptemp.get(),
            compression_level=int(self.var_level.get()),
            log_level=self.var_loglevel.get(),
            temp_dir=Path(self.var_temp.get()) if self.var_temp.get() else None,
            log_file=out / f"repack_{ts}.log",
        )
        self._running = True
        self.btn_run.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.progress.configure(value=0)

        def _worker():
            q: "queue.Queue[tuple]" = self._queue

            class _GuiHandler:
                def info(self, m, *a):
                    q.put(("log", m % a if a else m))

                def warning(self, m, *a):
                    q.put(("log", "[WARN] " + (m % a if a else m)))

                def error(self, m, *a):
                    q.put(("log", "[ERROR] " + (m % a if a else m)))

                def debug(self, m, *a):
                    pass

                def set_total(self, t):
                    q.put(("log", f"scan: 対象 {t} 件"))

                def update(self, n=1, message=""):
                    pass

            def _cb(cur, total, msg):
                q.put(("progress", cur, total, msg))

            try:
                code = run(cfg, _GuiHandler(), progress_callback=_cb)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                q.put(("log", f"[ERROR] 予期しないエラー: {exc}"))
                code = 1
            q.put(("done", code))

        threading.Thread(target=_worker, daemon=True).start()

    def _stop(self):
        # 逐次処理のため即時中断は行わず、注意のみ表示（将来: キャンセルフラグ対応）
        messagebox.showinfo("中止", "現在のファイル処理が終わるまでお待ちください")


def main() -> None:
    app = GuiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
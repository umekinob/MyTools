"""asset_tool GUI ラッパー（repack gui.py 流儀踏襲・設計書 7.2/7.3）。

使い方: python -m asset_tool.gui
- queue + thread で core.run() を実行し、進捗バー＋ログへ表示
- 走査はファイル数ベースで total が事前不明のため（Q46=A）、
  total=0 の間は進捗バーを indeterminate 表示に切り替える
- 中止ボタンは現行流儀どおり「即時killしない」注意表示を継承する
"""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asset_tool.config import Config
from asset_tool.core import run


class AssetApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("asset-tool（資産一覧出力）")
        self.geometry("760x600")
        self._running = False
        self._queue: "queue.Queue[tuple]" = queue.Queue()

        # ---- 入力・出力 ----
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.X)
        self.var_input = tk.StringVar()
        self.var_output = tk.StringVar()
        self._row(frm, 0, "起点フォルダ", self.var_input, self._pick_input)
        self._row(frm, 1, "出力フォルダ", self.var_output, self._pick_output)
        ttk.Label(frm, text="※ 読み取り専用・既存データは変更しません").grid(
            row=2, column=0, columnspan=3, sticky=tk.W)

        # ---- オプション ----
        opt = ttk.LabelFrame(self, text="オプション", padding=8)
        opt.pack(fill=tk.X, padx=8)
        self.var_format = tk.StringVar(value="csv")
        self.var_sort = tk.StringVar(value="name")
        self.var_order = tk.StringVar(value="asc")
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_hash = tk.BooleanVar(value=False)
        self.var_detail = tk.BooleanVar(value=False)
        self.var_dryrun = tk.BooleanVar(value=False)
        self.var_pattern = tk.StringVar()
        self.var_loglevel = tk.StringVar(value="INFO")
        ttk.Label(opt, text="形式").grid(row=0, column=0, sticky=tk.E)
        ttk.Combobox(opt, textvariable=self.var_format, state="readonly",
                     values=["csv", "html", "md"], width=6).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(opt, text="ソート").grid(row=0, column=2, sticky=tk.E)
        ttk.Combobox(opt, textvariable=self.var_sort, state="readonly",
                     values=["name", "size", "mtime", "files"], width=6).grid(row=0, column=3, sticky=tk.W)
        ttk.Label(opt, text="順序").grid(row=0, column=4, sticky=tk.E)
        ttk.Combobox(opt, textvariable=self.var_order, state="readonly",
                     values=["asc", "desc"], width=6).grid(row=0, column=5, sticky=tk.W)
        ttk.Checkbutton(opt, text="全階層", variable=self.var_recursive).grid(row=1, column=0, sticky=tk.W)
        ttk.Checkbutton(opt, text="SHA-256", variable=self.var_hash).grid(row=1, column=1, sticky=tk.W)
        ttk.Checkbutton(opt, text="詳細一覧", variable=self.var_detail).grid(row=1, column=2, sticky=tk.W)
        ttk.Checkbutton(opt, text="DRY-RUN", variable=self.var_dryrun).grid(row=1, column=3, sticky=tk.W)
        ttk.Label(opt, text="除外正規表現").grid(row=1, column=4, sticky=tk.E)
        ttk.Entry(opt, textvariable=self.var_pattern, width=16).grid(row=1, column=5, sticky=tk.W)
        ttk.Label(opt, text="ログレベル").grid(row=2, column=4, sticky=tk.E)
        ttk.Combobox(opt, textvariable=self.var_loglevel, state="readonly",
                     values=["DEBUG", "INFO", "WARNING", "ERROR"], width=6).grid(row=2, column=5, sticky=tk.W)

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
        logf = ttk.LabelFrame(self, text="ログ", padding=4)
        logf.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.log = tk.Text(logf, height=10, state=tk.DISABLED)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(logf, command=self.log.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scroll.set)
        clearf = ttk.Frame(self, padding=(8, 0))
        clearf.pack(fill=tk.X)
        ttk.Button(clearf, text="ログクリア", command=self._clear_log).pack(side=tk.RIGHT)

        self.after(100, self._pump)

    def _row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.E)
        ttk.Entry(parent, textvariable=var, width=52).grid(
            row=row, column=1, sticky=tk.W + tk.E, padx=4)
        ttk.Button(parent, text="参照", command=command).grid(row=row, column=2)
        parent.columnconfigure(1, weight=1)

    def _pick_input(self):
        p = filedialog.askdirectory()
        if p:
            self.var_input.set(p)

    def _pick_output(self):
        p = filedialog.askdirectory()
        if p:
            self.var_output.set(p)

    def _append_log(self, msg):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _pump(self):
        try:
            while True:
                kind, *rest = self._queue.get_nowait()
                if kind == "progress":
                    cur, total, msg = rest
                    if total == 0:
                        self.progress.configure(mode="indeterminate")
                        self.progress.start(10)
                    else:
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress.configure(maximum=max(total, 1), value=cur)
                    self._append_log(f"[{cur}] {msg}")
                elif kind == "log":
                    self._append_log(rest[0])
                elif kind == "done":
                    code = rest[0]
                    self._running = False
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
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
            messagebox.showwarning("入力不足", "起点・出力フォルダを指定してください")
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path(self.var_output.get())
        cfg = Config(
            input_dir=Path(self.var_input.get()),
            output_dir=out,
            format=self.var_format.get(),
            sort=self.var_sort.get(),
            order=self.var_order.get(),
            recursive=self.var_recursive.get(),
            with_hash=self.var_hash.get(),
            detail=self.var_detail.get(),
            exclude_pattern=self.var_pattern.get() or None,
            log_level=self.var_loglevel.get(),
            dry_run=self.var_dryrun.get(),
            log_file=out / f"asset_{ts}.log",
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
        # 逐次処理のため即時中断は行わず、注意のみ表示（Q47=A: 出力は完了時のみ）
        messagebox.showinfo("中止", "現在の走査が終わるまでお待ちください（"
                                    "完了時のみ出力が書かれます）")


def main() -> None:
    app = AssetApp()
    app.mainloop()


if __name__ == "__main__":
    main()
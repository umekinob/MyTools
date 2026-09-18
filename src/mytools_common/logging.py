"""ログ・進捗（mytools_common 版・Q43=A/Q44=A）。

repack_tool/progress.py の複写。相違点:
- logger名を引数化（既定 "mytools.repack"）
- 初期化時に当該logger名の既存ハンドラを全て除去（同一ログファイルの二重
  オープン・機能間混線を防止）
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
          "WARNING": logging.WARNING, "ERROR": logging.ERROR}

try:
    sys.stdout.reconfigure(errors="backslashreplace")
except Exception:
    pass
try:
    sys.stderr.reconfigure(errors="backslashreplace")
except Exception:
    pass


class ProgressLogger:
    """コンソールとファイルの双方へ出力する薄いログラッパー。連番進捗も管理。"""

    def __init__(self, log_level: str = "INFO",
                 log_file: Optional[Path] = None,
                 progress_callback: Optional[Callable[[int, int, str], None]] = None,
                 use_tty: bool = True,
                 logger_name: str = "mytools.repack"):
        self.logger = logging.getLogger(logger_name)
        # 既存ハンドラを全て除去（Q43=A: 実行単位クリア）
        for h in self.logger.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            self.logger.removeHandler(h)
        lvl = LEVELS.get(str(log_level).upper(), logging.INFO)
        self.logger.setLevel(lvl)
        self.logger.propagate = False
        self._callback = progress_callback
        self._use_tty = use_tty

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        ch.setLevel(lvl)
        self.logger.addHandler(ch)
        if log_file is not None:
            try:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(log_file, encoding="utf-8")
                fh.setFormatter(fmt)
                fh.setLevel(lvl)
                self.logger.addHandler(fh)
                self.file_enabled = True
            except OSError as exc:
                self.logger.warning("ログファイルを開けません(%s)。ファイル出力は無効", exc)
                self.file_enabled = False
        else:
            self.file_enabled = False

        self.current = 0
        self.total = 0
        self._start_time: float = 0.0
        self._item_times: list = []
        self._bar = None

    def debug(self, msg: str, *args) -> None:
        self.logger.debug(msg, *args)

    def info(self, msg: str, *args) -> None:
        self.logger.info(msg, *args)

    def warning(self, msg: str, *args) -> None:
        self.logger.warning(msg, *args)

    def error(self, msg: str, *args) -> None:
        self.logger.error(msg, *args)

    def set_total(self, total: int) -> None:
        self.total = total
        self.current = 0
        self._start_time = time.time()
        self._item_times = []
        self.info("scan: 対象 %s 件", total)
        try:
            from tqdm import tqdm  # 任意依存
            self._bar = tqdm(total=total, desc="progress", unit="file", ncols=80)
        except Exception:
            self._bar = None

    def update(self, n: int = 1, message: str = "") -> None:
        self.current += n
        now = time.time()
        if self.current > 0 and self.total > 0:
            elapsed = now - self._start_time
            avg_time = elapsed / self.current
            self._item_times.append(avg_time)
            if len(self._item_times) > 5:
                self._item_times.pop(0)
            moving_avg = sum(self._item_times) / len(self._item_times)
            remaining = max(0, moving_avg * (self.total - self.current))
            pct = self.current * 100 // self.total
            eta_str = self._format_time(remaining)
            elapsed_str = self._format_time(elapsed)
            self.info("[%s/%s] %s%% 経過%s 残り%s %s",
                      self.current, self.total, pct, elapsed_str, eta_str, message)
        # total が事前不明な処理（asset の走査等・Q46=A）でも
        # コールバック契約 (current, total, message) を守る（total=0 は不定）。
        if self._callback is not None:
            self._callback(self.current, self.total, message or "")
        if self._bar is not None:
            self._bar.update(n)

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m}m{s}s"
        else:
            h, rem = divmod(int(seconds), 3600)
            m, s = divmod(rem, 60)
            return f"{h}h{m}m{s}s"

    def close(self) -> None:
        if self._bar is not None:
            self._bar.close()

    def close_all(self) -> None:
        """全ハンドラを閉じて除去（テスト用）。"""
        for h in self.logger.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            self.logger.removeHandler(h)
"""ログ・進捗（設計書 11章）。コンソール＋ファイル双方に出力し、GUIからはコールバックで受け取る。"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
          "WARNING": logging.WARNING, "ERROR": logging.ERROR}

# 化け名（cp437由来の非cp932文字等）をログ出力してもクラッシュしないよう、
# コンソールのエラー処理を backslashreplace に緩和する（ファイル出力はUTF-8のまま）。
try:
    sys.stdout.reconfigure(errors="backslashreplace")
except Exception:
    pass
try:
    sys.stderr.reconfigure(errors="backslashreplace")
except Exception:
    pass


class ProgressLogger:
    """コンソールとファイルの双方へ出力する薄いログラッパー。連番進捗も管理。

    注意：logging はファイル毎に logger を保持します（重複オープン防止）。
    loggingモジュールはユニークなハンドラをキャッシュし、複回目の init では
    open append の想定どおりログが追記されます。
    """

    def __init__(self, log_level: str = "INFO",
                 log_file: Optional[Path] = None,
                 progress_callback: Optional[Callable[[int, int, str], None]] = None,
                 use_tty: bool = True):
        self.logger = logging.getLogger("repack_tool")
        lvl = LEVELS.get(str(log_level).upper(), logging.INFO)
        self.logger.setLevel(lvl)
        self.logger.propagate = False
        self._callback = progress_callback
        self._use_tty = use_tty

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
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
        self._item_times: list = []  # 各アイテムの処理時間履歴（移動平均用）
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
            self._bar = tqdm(total=total, desc="repack", unit="file", ncols=80)
        except Exception:
            self._bar = None

    def update(self, n: int = 1, message: str = "") -> None:
        self.current += n
        now = time.time()
        # 1件あたりの平均処理時間を計算（移動平均、直近5件）
        if self.current > 0:
            elapsed = now - self._start_time
            avg_time = elapsed / self.current
            self._item_times.append(avg_time)
            if len(self._item_times) > 5:
                self._item_times.pop(0)
            # 移動平均で残り時間を推定
            moving_avg = sum(self._item_times) / len(self._item_times)
            remaining = max(0, moving_avg * (self.total - self.current))
            pct = self.current * 100 // self.total if self.total > 0 else 0
            eta_str = self._format_time(remaining)
            elapsed_str = self._format_time(elapsed)
            self.info("[%s/%s] %s%% 経過%s 残り%s %s",
                      self.current, self.total, pct, elapsed_str, eta_str, message)
        if self._callback is not None and self.total:
            self._callback(self.current, self.total, message or "")
        if self._bar is not None:
            self._bar.update(n)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """秒数を読みやすい形式に変換（12s / 1m30s / 2h15m）。"""
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
        """ファイルハンドラを全て閉じる（テスト用）。"""
        for h in self.logger.handlers[:]:
            if isinstance(h, logging.FileHandler):
                try:
                    h.close()
                except Exception:
                    pass
                self.logger.removeHandler(h)
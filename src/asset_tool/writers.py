"""asset_tool の出力（設計書 6.6・6.7・Q18/Q33/Q37〜Q42/Q47）。

- CSV: UTF-8 BOM付き / CRLF / ヘッダあり / QUOTE_MINIMAL（Q37=A）
- HTML: CSS埋め込み自己完結（Q42=A）／MD: GFMテーブル
- 3形式とも同一の行セット・同一ソート（Q29-11）
- ファイル名 `asset_YYYYMMDD`＋同日 `_01` 連番（Q18=A）
- .tmp 逐次書き込み＋完了時 os.replace（Q47=A）
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .core import COLUMNS, DETAIL_COLUMNS, ROOT_LABEL, Row, DetailRow

EXIT_FATAL = 1


def next_output_path(out_dir: Path, date_str: str, suffix: str,
                     infix: str = "") -> Path:
    """`asset_YYYYMMDD[_NN]` 形式で未使用パスを返す（Q18=A）。"""
    base = f"asset_{date_str}{infix}"
    candidate = out_dir / f"{base}{suffix}"
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = out_dir / f"{base}_{i:02d}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _atomic_writer(path: Path):
    """.tmp への書き込みコンテキスト。完了時に os.replace で最終名へ（Q47=A）。"""
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    class _W:
        def __enter__(self):
            self._fh = open(tmp_path, "w", encoding="utf-8-sig", newline="")
            return self._fh

        def __exit__(self, exc_type, exc, tb):
            self._fh.close()
            if exc_type is None:
                os.replace(tmp_path, path)
            else:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False

    return _W(), tmp_path


def cleanup_tmp(cfg) -> None:
    """中断時に最終名のファイルを残さないため、tmp を掃除する（Q47=A）。"""
    try:
        for p in cfg.output_dir.glob("asset_*.tmp"):
            p.unlink(missing_ok=True)
    except OSError:
        pass


# ---------- 集約一覧 ----------

def write_aggregate(cfg, rows: List[Row], total_row: Row, logger) -> Path:
    date_str = datetime.now().strftime("%Y%m%d")
    ext = {"csv": ".csv", "html": ".html", "md": ".md"}[cfg.format]
    path = next_output_path(cfg.output_dir, date_str, ext)
    if cfg.format == "csv":
        _write_csv(path, rows, total_row)
    elif cfg.format == "html":
        _write_html(path, rows, total_row)
    else:
        _write_md(path, rows, total_row)
    return path


def _iter_lines(rows: List[Row], total_row: Row):
    for r in rows:
        yield r.cells()
    yield total_row.cells()


def _write_csv(path: Path, rows: List[Row], total_row: Row) -> None:
    writer_ctx, _ = _atomic_writer(path)
    with writer_ctx as f:
        w = csv.writer(f, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(COLUMNS)
        for cells in _iter_lines(rows, total_row):
            w.writerow(cells)


def _esc_html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _write_html(path: Path, rows: List[Row], total_row: Row) -> None:
    writer_ctx, _ = _atomic_writer(path)
    with writer_ctx as f:
        f.write("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n")
        f.write("<meta charset=\"utf-8\">\n")
        f.write("<title>資産一覧</title>\n<style>\n")
        f.write("body{font-family:'Meiryo','Yu Gothic',sans-serif;margin:16px;}\n")
        f.write("table{border-collapse:collapse;font-size:13px;}\n")
        f.write("th,td{border:1px solid #999;padding:2px 8px;white-space:nowrap;}\n")
        f.write("th{background:#e8eef7;}\n")
        f.write("tr.total td{background:#f2f2f2;font-weight:bold;}\n")
        f.write("</style>\n</head>\n<body>\n")
        f.write(f"<h1>資産一覧</h1>\n<table>\n<tr>")
        f.write("".join(f"<th>{_esc_html(c)}</th>" for c in COLUMNS))
        f.write("</tr>\n")
        for r in rows:
            f.write("<tr>" + "".join(f"<td>{_esc_html(c)}</td>"
                                     for c in r.cells()) + "</tr>\n")
        f.write("<tr class=\"total\">" + "".join(f"<td>{_esc_html(c)}</td>"
                                                 for c in total_row.cells()) + "</tr>\n")
        f.write("</table>\n</body>\n</html>\n")


def _esc_md(s: str) -> str:
    return s.replace("|", "\\|")


def _write_md(path: Path, rows: List[Row], total_row: Row) -> None:
    writer_ctx, _ = _atomic_writer(path)
    with writer_ctx as f:
        f.write("# 資産一覧\n\n")
        f.write("| " + " | ".join(_esc_md(c) for c in COLUMNS) + " |\n")
        f.write("|" + "|".join(["---"] * len(COLUMNS)) + "|\n")
        for cells in _iter_lines(rows, total_row):
            f.write("| " + " | ".join(_esc_md(c) for c in cells) + " |\n")


# ---------- 詳細一覧（--detail） ----------

def write_detail(cfg, detail_rows: List[DetailRow], logger) -> Path:
    date_str = datetime.now().strftime("%Y%m%d")
    path = next_output_path(cfg.output_dir, date_str, ".csv", infix="_detail")
    columns = list(DETAIL_COLUMNS) if cfg.with_hash else \
        [c for c in DETAIL_COLUMNS if c != "SHA-256"]
    writer_ctx, _ = _atomic_writer(path)
    with writer_ctx as f:
        w = csv.writer(f, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(columns)
        for d in detail_rows:
            w.writerow(d.cells(with_hash=cfg.with_hash))
    return path
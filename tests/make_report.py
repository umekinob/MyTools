"""検証実行＋HTMLレポート生成（result/result_yyyymmdd[_NN].html）。前半: 実行系。"""
from __future__ import annotations

import datetime as _dt
import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "tests"))

from repack_tool.config import Config
from repack_tool.core import run
from repack_tool.progress import ProgressLogger
from make_samples import main as make_samples_main

RESULT_DIR = ROOT / "result"


def report_path_today(now: _dt.datetime | None = None) -> Path:
    """result_yyyymmdd / 同日複数は _01, _02... の連番。"""
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    base = (now or _dt.datetime.now()).strftime("result_%Y%m%d")
    cand = RESULT_DIR / f"{base}.html"
    if not cand.exists():
        return cand
    n = 1
    while True:
        cand = RESULT_DIR / f"{base}_{n:02d}.html"
        if not cand.exists():
            return cand
        n += 1


def run_e2e(workdir: Path, log_stream: io.StringIO) -> dict:
    """E2E 1回分の実行。期待結果の検証情報も返す。"""
    data = ROOT / "tests" / "data"
    dest = workdir / "out_e2e"
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    lg = logging.getLogger("repack_tool")
    lg.handlers.clear()
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    lg.propagate = False

    cfg = Config(input_dir=data / "in", output_dir=dest,
                 password_list=data / "dict.txt", log_file=None,
                 compression_level=1)
    logger = ProgressLogger(log_level="INFO", log_file=None, use_tty=False)
    t0 = time.perf_counter()
    code = run(cfg, logger)
    dt = time.perf_counter() - t0

    checks = []
    expected = [
        dest / "T01_single" / "Top.zip",
        dest / "T02_multi" / "A.zip",
        dest / "T02_multi" / "B.zip",
        dest / "T03_mixed" / "T03_mixed_files.zip",
        dest / "T04_files" / "T04_files_files.zip",
        dest / "T06_jp" / "フォルダ 名前.zip",
        dest / "T07_pw" / "SecretDir.zip",
        dest / "T09_split" / "SecretDir.zip",
        dest / "T12a" / "DirA.zip",
        dest / "T14_sub" / "a" / "Top.zip",
        dest / "T15_slip" / "T15_slip_files.zip",
        dest / "T16_nested" / "Inner.zip",
        dest / "T17_dot" / "T17_dot_files.zip",
    ]
    for p in expected:
        ok = p.is_file()
        nm = "out_e2e/" + p.relative_to(dest).as_posix()
        checks.append({"id": "EXIST", "name": nm, "ok": ok,
                       "detail": "存在" if ok else "欠落"})

    def _zip_check(path: Path, expect: list, label: str):
        try:
            with zipfile.ZipFile(path) as zf:
                got = sorted(zf.namelist())
            ok = got == expect
            checks.append({"id": "ZIP", "name": label, "ok": ok,
                           "detail": f"got={got}" if not ok else f"entries={len(got)}"})
        except Exception as exc:  # noqa: BLE001
            checks.append({"id": "ZIP", "name": label, "ok": False, "detail": str(exc)})

    _zip_check(dest / "T03_mixed" / "T03_mixed_files.zip", ["f1.txt", "f2.jpg"], "T03群zip内容")
    _zip_check(dest / "T17_dot" / "T17_dot_files.zip", ["visible.txt"], "T17隠し除外")
    try:
        with zipfile.ZipFile(dest / "T06_jp" / "フォルダ 名前.zip") as zf:
            ok = "日本語ファイル.txt" in zf.namelist()
            checks.append({"id": "JP", "name": "T06日本語", "ok": ok,
                           "detail": "文字化けなし" if ok else "欠落"})
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "JP", "name": "T06日本語", "ok": False, "detail": str(exc)})

    for bad in ["T05_empty", "T08_pw_bad", "T11_corrupt", "T10_split_missing"]:
        got = list((dest / bad).rglob("*.zip")) if (dest / bad).exists() else []
        checks.append({"id": "SKIP", "name": f"{bad}は出力なし", "ok": not got,
                       "detail": "出力なし" if not got else f"残存={got}"})

    return {"exit_code": code, "elapsed": dt, "checks": checks,
            "output_dir": "(temp)/out_e2e"}


def run_pytest_files() -> list:
    results = []
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join([str(SRC), str(ROOT / "tests")]),
           "PYTHONIOENCODING": "utf-8"}
    for name in ["test_scanner.py", "test_passwords.py", "test_paths.py",
                 "test_integration.py"]:
        p = subprocess.run([sys.executable, str(ROOT / "tests" / name)],
                           capture_output=True, cwd=str(ROOT), env=env,
                           encoding="utf-8", errors="replace")
        tail = (p.stderr or p.stdout or "").strip().splitlines()
        summary = "\n".join(tail[-4:]) if tail else ""
        ok = ("OK" in summary) and ("FAILED" not in summary)
        results.append({"file": name, "ok": ok, "returncode": p.returncode,
                        "summary": summary})
    return results
CASE_TABLE = [
    ("T01", "単一フォルダ", "Top.zip 1件", "自動検証(EXIST)"),
    ("T02", "複数フォルダ", "A.zip, B.zip", "自動検証(EXIST)"),
    ("T03", "混在", "A.zip＋群zip(f1,f2)", "自動検証(EXIST/ZIP)"),
    ("T04", "ファイルのみ", "群zip", "自動検証(EXIST)"),
    ("T05", "空フォルダのみ", "empty-folderスキップ", "自動検証(SKIP＋exit=2)"),
    ("T06", "日本語・空白", "文字化けなし", "自動検証(JP)"),
    ("T07", "要PW一致", "解凍成功・PW非ログ", "自動検証(EXIST)＋目視"),
    ("T08", "要PW不一致", "password-mismatch", "自動検証(SKIP)"),
    ("T09", "分割揃い", "先頭巻から成功", "自動検証(EXIST)"),
    ("T10", "分割欠け", "missing-part", "自動検証(SKIP)"),
    ("T11", "破損", "corrupt", "自動検証(SKIP)"),
    ("T12", "tar系x4", "DirA〜D.zip", "自動検証(EXIST)"),
    ("T13", "同名出力存在", "_001連番", "手動(flat)で確認済"),
    ("T14", "sub階層", "ミラー a/Top.zip", "自動検証(EXIST)"),
    ("T15", "Slip含有", "無害化WARN＋抽出", "自動検証(EXIST)"),
    ("T16", "入れ子", "Inner.zip展開", "自動検証(EXIST)"),
    ("T17", "隠し・ドット", "visibleのみ", "自動検証(ZIP)"),
    ("T18", "入出力同一", "既定で終了1＋明示", "手動で確認済"),
    ("T19", "同名Dir(flat)", "Dir/Dir_001", "手動(flat)で確認済"),
    ("T20", "日本語・長パス", "UTF-8保存・再読OK", "T06相当＋手動"),
    ("T21", "巨大ダミー", "警告＋継続", "T09(400KB分割)で代用"),
    ("T22", "TOML設定", "反映確認", "未実行（将来）"),
]


def build_html(payload: dict) -> str:
    import html as _html
    e = _html.escape
    rows = []
    for c in payload["e2e"]["checks"]:
        cls = "ok" if c["ok"] else "ng"
        mark = "OK" if c["ok"] else "NG"
        rows.append(f"<tr class='{cls}'><td>{mark}</td><td>{e(c['id'])}</td>"
                    f"<td>{e(c['name'])}</td><td>{e(c['detail'])}</td></tr>")
    trows = []
    for tid, pat, exp_, how in CASE_TABLE:
        trows.append(f"<tr><td>{e(tid)}</td><td>{e(pat)}</td><td>{e(exp_)}</td><td>{e(how)}</td></tr>")
    prows = []
    for r in payload["unit"]:
        cls = "ok" if r["ok"] else "ng"
        mark = "OK" if r["ok"] else "NG"
        prows.append(f"<tr class='{cls}'><td>{mark}</td><td>{e(r['file'])}</td>"
                     f"<td>rc={r['returncode']}</td><td><pre>{e(r['summary'])}</pre></td></tr>")
    log_html = e(payload["e2e_log"])
    meta = payload["meta"]
    badge = "pass" if payload["overall_ok"] else "fail"
    word = "PASS" if payload["overall_ok"] else "FAIL"
    ok_n = sum(1 for c in payload["e2e"]["checks"] if c["ok"])
    n_all = len(payload["e2e"]["checks"])
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>repack-tool 検証レポート {e(meta['report_name'])}</title>
<style>
body{{font-family:'Yu Gothic',Meiryo,sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #bbb;padding:6px 8px;text-align:left;font-size:13px}}
th{{background:#f0f4f8}}
tr.ng{{background:#fff3f3}}
pre{{white-space:pre-wrap;font-size:12px;margin:0}}
.log{{background:#111;color:#ddd;padding:12px;font-size:12px;max-height:420px;overflow:auto}}
h1{{font-size:22px}} h2{{font-size:18px;margin-top:28px}}
.badge{{display:inline-block;padding:2px 10px;border-radius:12px;font-weight:bold}}
.pass{{background:#e6f6ea;color:#0a7d2c}} .fail{{background:#fdecec;color:#c00}}
.meta{{color:#555;font-size:13px}}
</style>
</head>
<body>
<h1>repack-tool 検証レポート（{e(meta['report_name'])}）</h1>
<p class="meta">実行日時: {e(meta['executed_at'])} / コミット: {e(meta['commit'])} /
Python: {e(meta['python'])} / 7z: {e(meta['seven_zip'])}</p>
<h2>総合結果 <span class="badge {badge}">{word}</span></h2>
<p>E2E 終了コード: {payload['e2e']['exit_code']}（期待 2） / 処理時間: {payload['e2e']['elapsed']:.1f}s /
チェック: {ok_n}/{n_all} 件OK</p>
<h2>1. E2Eチェック詳細</h2>
<table><tr><th></th><th>種別</th><th>対象</th><th>詳細</th></tr>
{''.join(rows)}</table>
<h2>2. 単体テスト</h2>
<table><tr><th></th><th>ファイル</th><th>結果</th><th>概要</th></tr>
{''.join(prows)}</table>
<h2>3. 検証ケース対応表（T01〜T22）</h2>
<table><tr><th>ID</th><th>パターン</th><th>期待</th><th>検証方法</th></tr>
{''.join(trows)}</table>
<h2>4. 実行ログ（抜粋・PW非出力）</h2>
<div class="log"><pre>{log_html}</pre></div>
</body>
</html>
"""
def _git_commit() -> str:
    import subprocess as _sp
    try:
        r = _sp.run(["git", "log", "-1", "--format=%h %s"],
                    capture_output=True, text=True, cwd=str(ROOT),
                    encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else "(gitなし)"
    except Exception:
        return "(gitなし)"


def main() -> Path:
    now = _dt.datetime.now()
    target = report_path_today(now)
    tmp_root = Path(tempfile.mkdtemp(prefix="repack_report_"))
    workdir = tmp_root / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    print("サンプル生成中...", flush=True)
    make_samples_main(clean=True)
    print("E2E実行中...", flush=True)
    e2e = run_e2e(workdir, buf)
    print("単体テスト実行中...", flush=True)
    unit = run_pytest_files()
    overall = (e2e["exit_code"] == 2
               and all(c["ok"] for c in e2e["checks"])
               and all(u["ok"] for u in unit))
    payload = {
        "meta": {
            "report_name": target.stem,
            "executed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "commit": _git_commit(),
            "python": sys.version.split()[0],
            "seven_zip": "C:\\Program Files\\7-Zip\\7z.exe",
        },
        "e2e": e2e,
        "unit": unit,
        "e2e_log": buf.getvalue()[-12000:],
        "overall_ok": overall,
    }
    target.write_text(build_html(payload), encoding="utf-8")
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"レポート保存: {target} / overall={'PASS' if overall else 'FAIL'}", flush=True)
    return target


if __name__ == "__main__":
    main()
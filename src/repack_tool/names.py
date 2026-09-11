"""ファイル名文字化けの検出・復元（ZIP/7z/rar/tar共通）。

背景:
- ZIPは UTF-8フラグ(0x800)なしのエントリ名を旧仕様どおり cp437 として読む。
  日本語ツールが Shift_JIS(cp932)名をフラグなしで格納した旧式ZIPは、
  `zipfile` では化けた名前として復号される（主犯パターン)。
- 7z/rar は 7z.exe が展開するため展開処理自体に介入できない。
  よって「展開後に中間フォルダの名前を正規化する」統一レイヤ方式とし、
  展開経路(lib/7z.exe)を問わず全形式に効かせる。

復元方式:
- 化け文字列を cp437 バイトに戻し、候補 [utf-8, cp932, euc-jp] で厳密復号、
  日本語含有率・置換文字・制御文字でスコア化する。
- 確信が持てない場合は元の名前を維持する（誤復元防止）。
- tar由来の surrogateescape 名は os.fsencode で生バイトに戻してから判定する。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

# 復号候補の優先順（厳密復号で試す）
_CANDIDATE_ENCODINGS = ("utf-8", "cp932", "euc-jp")


def _is_jp_char(ch: str) -> bool:
    o = ord(ch)
    return (
        0x3040 <= o <= 0x309F  # ひらがな
        or 0x30A0 <= o <= 0x30FF  # カタカナ
        or 0x4E00 <= o <= 0x9FFF  # CJK統合漢字
        or 0x3400 <= o <= 0x4DBF  # CJK拡張A
        or 0xFF61 <= o <= 0xFF9F  # 半角カタカナ
        or 0x3000 <= o <= 0x303F  # CJK記号・句読点
    )


def _score_candidate(text: str) -> float:
    """候補文字列のスコア。高いほど日本語として自然。"""
    if not text:
        return -1000.0
    if "\ufffd" in text:
        return -1000.0
    ctrl = sum(1 for c in text if ord(c) < 32 or ord(c) == 127)
    if ctrl:
        return -100.0 * ctrl
    jp = sum(1 for c in text if _is_jp_char(c))
    if jp == 0:
        return -1.0
    ratio = jp / max(len(text), 1)
    return jp * 10.0 + ratio * 10.0


def _pick_best(raw: bytes) -> Tuple[Optional[str], float]:
    best: Optional[str] = None
    best_score = float("-inf")
    for enc in _CANDIDATE_ENCODINGS:
        try:
            cand = raw.decode(enc, errors="strict")
        except Exception:
            continue
        score = _score_candidate(cand)
        if score > best_score:
            best_score = score
            best = cand
    return best, best_score


def _is_ascii_only(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def recover_name(display: str, strict: bool = False) -> Tuple[str, float]:
    """化け表示名からの復元を試みる。(復元名, 信頼度)を返す。

    strict=False: ZIPフラグなし等「化け確定度が高い」場合の寛容モード。
    strict=True:  7z/rar展開後など provenance 不明な場合の厳格モード。
    復元できない/すべきでない場合は (display, 0.0) を返す。
    """
    if not display or _is_ascii_only(display):
        return display, 0.0
    try:
        raw = display.encode("cp437")
    except (UnicodeEncodeError, ValueError):
        # cp437に無い文字を含む=既に正しいUTF-8日本語等のため対象外
        return display, 0.0
    best, score = _pick_best(raw)
    if best is None or best == display:
        return display, 0.0
    jp = sum(1 for c in best if _is_jp_char(c))
    ratio = jp / max(len(best), 1)
    if strict:
        ok = (jp >= 2 and ratio >= 0.4) or (jp == 1 and len(best) <= 2 and ratio >= 0.5)
    else:
        ok = jp >= 1 and ratio >= 0.3 and score > 0
    if not ok:
        return display, 0.0
    return best, ratio


def recover_fs_name(name: str, strict: bool = False) -> Tuple[str, float]:
    """surrogateescape を含み得るファイルシステム名からの復元。"""
    if not name:
        return name, 0.0
    has_surrogate = any(0xDC80 <= ord(c) <= 0xDCFF for c in name)
    if has_surrogate:
        # surrogateescape を正しく生バイトに戻す
        raw = bytearray()
        for c in name:
            o = ord(c)
            if 0xDC80 <= o <= 0xDCFF:
                raw.append(o - 0xDC00)
            elif o < 128:
                raw.append(o)
            else:
                raw.extend(c.encode("utf-8"))
        if not raw:
            return name, 0.0
        best, score = _pick_best(bytes(raw))
        if best is None or best == name:
            return name, 0.0
        jp = sum(1 for c in best if _is_jp_char(c))
        ratio = jp / max(len(best), 1)
        if jp >= 1 and ratio >= 0.3 and score > 0:
            return best, ratio
        return name, 0.0
    return recover_name(name, strict=strict)


def normalize_tree(root: Path, logger: Optional[object] = None) -> int:
    """展開済みツリー内の化け名をボトムアップでリネームする。戻り値は復元件数。

    - root自体は改名しない。ファイル＋フォルダ双方が対象。
    - 厳格モードで誤復元を抑止。衝突時は _dupN を付与。
    - パスワードや内容はログに出さない（名前のみ）。
    """
    if not root.is_dir():
        return 0
    # 深い順（ボトムアップ）で処理
    paths = sorted(root.rglob("*"), key=lambda p: (len(p.parts), str(p)), reverse=True)
    fixed = 0
    for p in paths:
        try:
            new_name, _conf = recover_fs_name(p.name, strict=True)
        except Exception:
            continue
        if new_name == p.name:
            continue
        if "/" in new_name or "\\" in new_name or new_name in ("", ".", ".."):
            continue
        target = p.parent / new_name
        if target.exists():
            stem = target.stem
            suffix = target.suffix if target.is_file() else ""
            base = target.parent / stem if target.is_file() else target
            n = 1
            while True:
                cand = target.parent / f"{stem}_dup{n}{suffix}" if target.is_file() \
                    else Path(str(base) + f"_dup{n}")
                if not cand.exists():
                    target = cand
                    break
                n += 1
                if n > 999:
                    target = None  # type: ignore[assignment]
                    break
            if target is None:
                continue
        try:
            p.rename(target)
            fixed += 1
            if logger is not None:
                try:
                    logger.warning("文字化け名を復元: %s -> %s", p.name, target.name)  # type: ignore[attr-defined]
                except Exception:
                    pass
        except OSError:
            continue
    return fixed

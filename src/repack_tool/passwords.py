"""パスワード辞書読み込み（設計書 10章）。ログには内容を出さない。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


class PasswordListError(Exception):
    pass


@dataclass
class PasswordList:
    passwords: List[str] = field(default_factory=list)
    source: Optional[Path] = None
    truncated: bool = False

    @classmethod
    def from_file(cls, path: Optional[Path], encoding: str = "utf-8",
                  max_passwords: int = 10000) -> "PasswordList":
        if path is None:
            return cls()
        p = Path(path)
        if not p.is_file():
            raise PasswordListError(f"password-list が見つかりません: {p}")
        try:
            raw = p.read_bytes()
        except OSError as exc:
            raise PasswordListError(f"password-list を読めません: {exc}") from exc
        # BOM対応
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode(encoding, errors="replace")
        pws: List[str] = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            pws.append(s)
            if len(pws) >= max_passwords:
                return cls(passwords=pws[:max_passwords], source=p, truncated=True)
        return cls(passwords=pws, source=p)

    def __len__(self) -> int:
        return len(self.passwords)

    def __iter__(self):
        return iter(self.passwords)
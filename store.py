"""حفظ المحادثات ودمج التصديرات الجديدة في نفس الجدول (بدون تكرار)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from core import Message

VERSION = 1


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return s[:60] or "chat"


@dataclass
class Workspace:
    name: str
    messages: dict = field(default_factory=dict)   # key -> {"t","s","x","o"}
    ai: dict = field(default_factory=dict)         # key -> نتيجة الذكاء الاصطناعي أو None
    meta: dict = field(default_factory=dict)       # imports, trusted, ...

    # ───── الدمج ─────
    def merge(self, msgs: list[Message], source: str = "") -> tuple[int, int]:
        """بيضيف الرسائل الجديدة بس. بيرجّع (جديد, كانت موجودة)."""
        added = existing = 0
        for m in msgs:
            if m.key in self.messages:
                existing += 1
                continue
            self.messages[m.key] = {"t": m.when.isoformat(timespec="minutes"), "s": m.sender, "x": m.text, "o": m.idx}
            added += 1
        log = self.meta.setdefault("imports", [])
        log.append({"file": source, "added": added, "existing": existing, "at": datetime.now().isoformat(timespec="minutes")})
        del log[:-20]
        return added, existing

    def sorted_messages(self) -> list[Message]:
        rows = sorted(self.messages.items(), key=lambda kv: (kv[1]["t"], kv[1]["o"], kv[0]))
        return [Message(i, datetime.fromisoformat(v["t"]), v["s"], v["x"], k) for i, (k, v) in enumerate(rows)]

    def __len__(self) -> int:
        return len(self.messages)

    # ───── التخزين ─────
    def to_json(self) -> str:
        return json.dumps({"app": "classmate", "version": VERSION, "name": self.name, "messages": self.messages,
                           "ai": self.ai, "meta": self.meta}, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Workspace":
        d = json.loads(raw)
        if d.get("app") != "classmate" or not isinstance(d.get("messages"), dict):
            raise ValueError("الملف مش نسخة احتياطية من ClassMate.")
        return cls(d.get("name", "chat"), d["messages"], d.get("ai", {}), d.get("meta", {}))

    def absorb(self, other: "Workspace") -> tuple[int, int]:
        """دمج نسخة احتياطية في المحادثة الحالية (الرسائل + نتايج الذكاء الاصطناعي)."""
        added = existing = 0
        for k, v in other.messages.items():
            if k in self.messages:
                existing += 1
            else:
                self.messages[k] = v
                added += 1
        for k, v in other.ai.items():
            self.ai.setdefault(k, v)
        return added, existing


def is_backup(raw: str) -> bool:
    head = raw[:200].lstrip()
    return head.startswith("{") and '"app"' in raw[:400] and "classmate" in raw[:400]


# ───── ملفات محلية (للتشغيل على جهازك) ─────

def _path(data_dir: str, name: str) -> str:
    return os.path.join(data_dir, slugify(name) + ".json")


def list_spaces(data_dir: str) -> list[str]:
    if not os.path.isdir(data_dir):
        return []
    out = []
    for f in sorted(os.listdir(data_dir)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(data_dir, f), encoding="utf-8") as fh:
                    out.append(json.load(fh).get("name") or f[:-5])
            except Exception:
                continue
    return out


def load_space(data_dir: str, name: str) -> Workspace | None:
    p = _path(data_dir, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return Workspace.from_json(fh.read())


def save_space(data_dir: str, ws: Workspace) -> None:
    os.makedirs(data_dir, exist_ok=True)
    p = _path(data_dir, ws.name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(ws.to_json())
    os.replace(tmp, p)  # كتابة آمنة: لو الجهاز فصل نص الكتابة مانخسرش الملف القديم


def delete_space(data_dir: str, name: str) -> None:
    p = _path(data_dir, name)
    if os.path.exists(p):
        os.remove(p)

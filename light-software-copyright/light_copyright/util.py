"""基础工具：结构化读写、哈希、日期、显示宽度。"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import yaml


def load_structured(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


def dump_yaml(path: Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def dump_json(path: Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in
            p.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def today() -> str:
    return date.today().isoformat()


def add_days(iso: str, days: int) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return (date(y, m, d) + timedelta(days=days)).isoformat()


def display_width(text: str) -> int:
    """显示列宽：全角/宽字符计 2 列，其余 1 列（折行口径）。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def wrap_line(text: str, columns: int) -> list:
    """按显示列宽折行；不改任何字符内容，只切分（HC-1：不改写源码）。"""
    if display_width(text) <= columns:
        return [text]
    out, cur, cur_w = [], "", 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if cur and cur_w + w > columns:
            out.append(cur)
            cur, cur_w = "", 0
        cur += ch
        cur_w += w
    if cur:
        out.append(cur)
    return out

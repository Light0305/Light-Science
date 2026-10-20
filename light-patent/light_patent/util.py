"""通用小工具：结构化文件读写、哈希、日期运算、文本清洗。

日期运算只用标准库；月份加减按日历月（月末钳制），供台账期限
机械计算（优先权 12 个月窗、答复期、年费周年）。
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

import yaml


def today() -> str:
    return date.today().isoformat()


def parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def add_months(d: date, months: int) -> date:
    """日历月加减：目标月不存在当日时钳到月末。"""
    total = (d.year * 12 + (d.month - 1)) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_between(start: date, end: date) -> float:
    """两日期相差的月数（按天折算到 30.4375 天/月，审计口径用）。"""
    return (end - start).days / 30.4375


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slugify(text: str, fallback: str = "case") -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", (text or "").strip()).strip("-").lower()
    return slug or fallback


def load_structured(path):
    path = Path(path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if path.suffix == ".json":
        return json.loads(text)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return text


def dump_yaml(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def dump_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def append_jsonl(path, rows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def read_text(path) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

"""通用小工具：YAML/JSON 读写、规范化哈希、时间戳、ID 生成。

口径与 Light-Idea / Light-Design / Light-Experiment / Light-Analysis /
Light-Write 对齐：
- 规范化 JSON（sort_keys + 紧凑分隔符）是全包哈希计算的唯一序列化口径，
  校验器重算哈希时用同一口径，序列化口径漂移即哈希全灭——不许另起炉灶。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

import yaml


def slugify(title: str, max_len: int = 40, fallback: str = "figures") -> str:
    """把题名转成文件系统安全的短名；全非 ASCII 时退化为 fallback。"""
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or fallback


def today() -> str:
    return date.today().isoformat()


def utcnow() -> str:
    """事件与时间线用的 UTC 时间戳（秒精度，ISO 格式，可排序可解析）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(obj) -> str:
    """哈希计算的唯一序列化口径：键排序、紧凑分隔、非 ASCII 直出。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def component_hash(obj) -> str:
    """结构化对象的规范化哈希（快照哈希/内容哈希的唯一算法）。"""
    return sha256_text(canonical_json(obj))


def load_structured(path):
    """按后缀读 YAML / JSON / JSONL，返回 Python 对象（JSONL 返回 list）。"""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        return json.loads(text)
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return yaml.safe_load(text)


def dump_yaml(path, obj) -> None:
    Path(path).write_text(
        yaml.safe_dump(obj, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def dump_json(path, obj) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

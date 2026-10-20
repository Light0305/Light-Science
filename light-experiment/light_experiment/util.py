"""通用小工具：YAML/JSON 读写、规范化哈希、时间戳、ID 生成。

口径与 light-idea / light-design 对齐：
- exec_id / design_id 均为 slug + '_' + sha256(题名)[:6] 形态；
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


def slugify(title: str, max_len: int = 40, fallback: str = "execution") -> str:
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


def component_hash(obj) -> str:
    """任意结构化成分的哈希 = sha256(规范化 JSON)。"""
    return sha256_text(canonical_json(obj))


def read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def read_jsonl(path: Path) -> list[dict]:
    """读 JSONL（逐行 JSON）。坏行抛 ValueError 并点名行号。"""
    out: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name} 第 {i} 行不是合法 JSON：{e}") from e
    return out


def load_structured(path: Path) -> dict:
    """按后缀读 JSON / YAML 结构化文件（run 规格、交接件等）。"""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in (".yaml", ".yml"):
        return read_yaml(path)
    raise ValueError(f"文件格式不支持：{path.name}（须为 .json / .yaml / .yml）")

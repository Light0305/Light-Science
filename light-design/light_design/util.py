"""通用小工具：YAML 读写、题名 slug、design_id 生成。

design_id 规则（与 Light-Idea 的 idea_id 口径一致）：
    <slug>_<hash6>
- slug：题名 ASCII 化、连字符连接、截断 40 字符（全非 ASCII 时退化为 'design'）；
- hash6：sha256(规范化题名) 的前 6 位。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from pathlib import Path

import yaml


def slugify(title: str, max_len: int = 40) -> str:
    """把题名转成文件系统安全的短名；全非 ASCII 时退化为 'design'。"""
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "design"


def make_design_id(title: str) -> str:
    """由题名生成 design_id：slug + '_' + sha256(题名)[:6]。"""
    norm = (title or "").strip().lower()
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return f"{slugify(title)}_{digest[:6]}"


def today() -> str:
    return date.today().isoformat()


def read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

"""通用小工具：YAML/JSON 读写、JSONL 计数、嵌套字段深搜、时间戳。

口径与姊妹包对齐。总控只读上游登记文件：解析失败一律返回 None 并由
调用方点名，不猜、不修、不回写。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import yaml


def today() -> str:
    return date.today().isoformat()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_yaml(path):
    """读 YAML 为 dict；文件不存在、解析失败或顶层非 dict 返回 None。"""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def dump_yaml(path, data) -> None:
    Path(path).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def load_json(path):
    """读 JSON；不存在或解析失败返回 None。"""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def count_jsonl(path) -> int:
    """数 JSONL 非空行数；文件不存在返回 0。"""
    path = Path(path)
    if not path.is_file():
        return 0
    n = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def deep_find(data, key):
    """在嵌套 dict/list 里深搜第一个 key 对应的值；找不到返回 None。

    上游登记头里 review_status 等门标记的嵌套位置逐包不同（Idea 在
    查新区、Design 在 freeze.review、Write 在 intake/review 区），
    总控按字段名深搜，不假设路径。
    """
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            hit = deep_find(v, key)
            if hit is not None:
                return hit
    elif isinstance(data, list):
        for v in data:
            hit = deep_find(v, key)
            if hit is not None:
                return hit
    return None


def deep_find_all(data, key) -> list:
    """深搜全部同名字段值（去重保序）。"""
    out: list = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key and v not in out:
                    out.append(v)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return out

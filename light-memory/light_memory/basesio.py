"""Obsidian Bases（.base）著述与离线求值（工具层 T1，§5.1）。

.base 是核心功能的视图定义文件（纯 YAML：filters / formulas /
properties / summaries / views），本体不存数据行——故本模块
整文件著述不涉 frontmatter 行级保真问题（那是笔记的纪律）。

离线求值只支持 filters 的子集：hasProperty / hasTag / inFolder /
属性等值与比较、and/or/not 组合。公式字段不离线算（结果点名
列入 skipped_formulas）；求值结果恒标注 offline-eval，与应用
内 base:query 的结果可能有差——定位是体检/预览，不冒充应用
渲染。不认识的过滤表达式逐项点名报错，不静默当真/当假。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import vaultio
from .util import sha256_text

VIEW_TYPES = ("table", "cards", "list", "map")

_LEAF_RES = [
    ("hasProperty",
     re.compile(r'^file\.hasProperty\(\s*"([^"]+)"\s*\)$')),
    ("hasTag", re.compile(r'^file\.hasTag\(\s*"([^"]+)"\s*\)$')),
    ("inFolder",
     re.compile(r'^file\.inFolder\(\s*"([^"]*)"\s*\)$')),
    ("compare", re.compile(
        r'^(file\.name|file\.basename|file\.folder|file\.ext|'
        r'[A-Za-z0-9_.\-]+)\s*(==|!=|>=|<=|>|<)\s*(.+)$')),
]


class BaseError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 著述

def validate_base(spec) -> list:
    gaps = []
    if not isinstance(spec, dict):
        return [".base 顶层须为映射"]
    if "filters" not in spec:
        gaps.append(".base 缺 filters 段")
    views = spec.get("views")
    if not isinstance(views, list) or not views:
        gaps.append(".base 缺 views 或为空")
    else:
        for view in views:
            if not isinstance(view, dict):
                gaps.append("views 条目须为映射")
                continue
            if view.get("type") not in VIEW_TYPES:
                gaps.append(f"视图类型非法：{view.get('type')}"
                            f"（只许 {'/'.join(VIEW_TYPES)}）")
            if not view.get("name"):
                gaps.append("视图缺 name")
    for seg in ("formulas", "properties", "summaries"):
        if seg in spec and not isinstance(spec[seg], dict):
            gaps.append(f".base 的 {seg} 段须为映射")
    return gaps


def write_base(path, spec: dict) -> dict:
    gaps = validate_base(spec)
    if gaps:
        raise BaseError(gaps)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)
    p.write_text(text, encoding="utf-8")
    return {"path": str(p), "sha256": sha256_text(text),
            "views": [v.get("name") for v in spec.get("views") or []]}


def read_base(path) -> dict:
    p = Path(path)
    if not p.exists():
        raise BaseError([f".base 不存在：{p}"])
    try:
        spec = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BaseError([f".base YAML 解析失败：{p}（{exc}）"])
    gaps = validate_base(spec)
    if gaps:
        raise BaseError(gaps)
    return spec


# ---------------------------------------------------------------- 离线求值

def _note_record(vault: Path, rel: str) -> dict:
    text = (vault / rel).read_text(encoding="utf-8")
    fm = vaultio.fm_parse(text)
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    folder = str(Path(rel).parent)
    return {
        "rel": rel, "fm": fm,
        "file.name": Path(rel).name, "file.basename": Path(rel).stem,
        "file.folder": "" if folder == "." else folder,
        "file.ext": "md", "tags": [str(t) for t in tags],
    }


def _literal(raw: str):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _compare(actual, op: str, expected) -> bool:
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and \
            not isinstance(expected, bool):
        try:
            actual = float(actual)
        except (TypeError, ValueError):
            return False
    else:
        actual = str(actual)
        expected = str(expected)
    return {"==": actual == expected, "!=": actual != expected,
            ">": actual > expected, ">=": actual >= expected,
            "<": actual < expected, "<=": actual <= expected}[op]


def _eval_leaf(expr: str, record: dict, unsupported: list) -> bool:
    expr = expr.strip()
    for name, rx in _LEAF_RES:
        m = rx.match(expr)
        if not m:
            continue
        if name == "hasProperty":
            return record["fm"].get(m.group(1)) is not None
        if name == "hasTag":
            tag = m.group(1)
            return any(t == tag or t.startswith(tag + "/")
                       for t in record["tags"])
        if name == "inFolder":
            folder = m.group(1).strip("/")
            if not folder:
                return record["file.folder"] == ""
            cur = record["file.folder"]
            return cur == folder or cur.startswith(folder + "/")
        key, op, raw = m.group(1), m.group(2), m.group(3)
        if key.startswith("file.") and key not in (
                "file.name", "file.basename", "file.folder",
                "file.ext"):
            unsupported.append(expr)
            return False
        actual = record.get(key) if key.startswith("file.") \
            else record["fm"].get(key)
        return _compare(actual, op, _literal(raw))
    unsupported.append(expr)
    return False


def _eval_filter(node, record: dict, unsupported: list) -> bool:
    if isinstance(node, str):
        return _eval_leaf(node, record, unsupported)
    if isinstance(node, list):
        return all(_eval_filter(x, record, unsupported)
                   for x in node)
    if isinstance(node, dict):
        if "and" in node:
            return all(_eval_filter(x, record, unsupported)
                       for x in node["and"] or [])
        if "or" in node:
            return any(_eval_filter(x, record, unsupported)
                       for x in node["or"] or [])
        if "not" in node:
            return not _eval_filter(node["not"], record, unsupported)
    unsupported.append(str(node))
    return False


def eval_base(vault, base_rel: str) -> dict:
    """离线求值：按 filters 子集算命中笔记集，标注 offline-eval。

    含不认识的表达式即整体点名报错（不给半对的结果冒充全对）。
    """
    vault = Path(vault)
    spec = read_base(vault / base_rel)
    filters = spec.get("filters")
    matched, unsupported = [], []
    for rel in vaultio.list_notes(vault):
        record = _note_record(vault, rel)
        if filters is None or _eval_filter(filters, record,
                                           unsupported):
            matched.append(rel)
    if unsupported:
        raise BaseError(
            [f"离线求值不支持的过滤表达式：{e}"
             for e in sorted(set(unsupported))] +
            ["离线求值只支持 hasProperty/hasTag/inFolder/属性比较"
             "与 and-or-not 组合；公式字段不离线算"])
    return {
        "base": base_rel, "label": "offline-eval",
        "note": "离线求值（filters 子集）结果，与应用内 base:query "
                "渲染可能有差；公式字段不离线算",
        "matched": matched, "count": len(matched),
        "views": [v.get("name") for v in spec.get("views") or []],
        "skipped_formulas": sorted(
            (spec.get("formulas") or {}).keys()),
    }

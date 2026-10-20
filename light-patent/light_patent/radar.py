"""P7 政策雷达 lite（Q7）：条目登记 + 简报生成。

信源分层：A 级（官方原文）可支撑撰写口径；B 级（律所解读、
地方预审口径等）只作线索，不得单独改口径。雷达只出简报，不
自动修改 SKILL 或任何包文件——改口径是旁路动作，须另行点名。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import PatentError
from .util import dump_yaml, load_structured, today

_RADAR_FILE = Path(__file__).with_name("radar_entries.yaml")


def load_entries() -> list:
    data = load_structured(_RADAR_FILE)
    if data and data.get("entries"):
        return data["entries"]
    return [dict(e) for e in schema.POLICY_RADAR_SEED]


def save_entries(entries) -> None:
    dump_yaml(_RADAR_FILE, {"kind": "light-patent/policy-radar",
                            "entries": entries})


def seed_if_missing() -> list:
    if not _RADAR_FILE.exists():
        entries = [dict(e) for e in schema.POLICY_RADAR_SEED]
        save_entries(entries)
        return entries
    return load_entries()


def add_entry(payload: dict) -> dict:
    entries = seed_if_missing()
    gaps = []
    if payload.get("source_grade") not in schema.POLICY_SOURCE_GRADES:
        gaps.append("信源等级须为 A（官方原文）或 B（转述线索）")
    for field in ("entry_id", "title", "source", "effective", "summary",
                  "impact_disclosure", "impact_drafting"):
        if not payload.get(field):
            gaps.append(f"政策条目缺字段 {field}")
    if any(e["entry_id"] == payload.get("entry_id") for e in entries):
        gaps.append(f"条目 {payload.get('entry_id')} 已登记（雷达只增不改，"
                    "更正请新增条目并在 summary 注明取代关系）")
    if gaps:
        raise PatentError(gaps)
    entries.append(dict(payload))
    save_entries(entries)
    return payload


def render_brief(entries=None) -> str:
    entries = entries if entries is not None else load_entries()
    lines = [
        "# 专利政策雷达简报（lite）",
        "",
        f"生成日期：{today()}。信源分层：A 级官方原文可支撑口径；"
        "B 级只作线索、不得单独改口径。本简报不自动修改任何技能"
        "文件；口径变更须另行点名走修订。",
        "",
    ]
    for e in sorted(entries, key=lambda x: x.get("effective") or ""):
        lines += [
            f"## {e['entry_id']} {e['title']}",
            f"- 信源：{e['source']}（{e['source_grade']} 级）",
            f"- 施行：{e['effective']}",
            f"- 要点：{e['summary']}",
            f"- 对交底写法的影响：{e['impact_disclosure']}",
            f"- 对申请文件写法的影响：{e['impact_drafting']}",
            "",
        ]
    return "\n".join(lines)

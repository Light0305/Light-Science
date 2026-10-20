"""补课采纳的账本类机制（deep-read-D-supplement）：

- D-W13 草稿标记纪律：sections 内标记分工注册表扫描——[claim:]/[num:]/[@key]/
  [rev:]/[fig:] 为 Light 行内标记；[todo-fact:] 只许事实/来源问题（开放计数 =
  证据就绪度指标）、[note-edit:] 编辑意见、[directive:] 必改指令、
  [superseded:] 冻结替换留痕。未注册的方括号标记 → 纯度违规。
- D-W02 术语账：terminology.yaml 锁定后，已见变体出现在正文 = 违规（只报不改）。
- D-W01 正文分配纪律：body_allocation.yaml——主张位置图（每处出现标功能）、
  结果功能八分类与目的地、删除日志、字数增量；enforced=true 时位置图须
  覆盖正文全部主张出现处。
"""

from __future__ import annotations

import re

from . import schema
from .project import section_files

MARKER_RE = re.compile(r"\[([a-z][a-z0-9-]*):([^\]]*)\]")
CITE_RE = re.compile(r"\[@([^\]]+)\]")


def scan_markers(pkg) -> dict:
    """草稿标记扫描：计数、未注册标记、开放指令/事实问题清单。"""
    sections = section_files(pkg["root"])
    counts: dict[str, int] = {}
    unknown: list[dict] = []
    open_directives: list[dict] = []
    open_fact_todos: list[dict] = []
    claim_occurrences: dict[str, list[str]] = {}
    for fname, text in sorted(sections.items()):
        for m in MARKER_RE.finditer(text):
            kind, body = m.group(1), m.group(2)
            counts[kind] = counts.get(kind, 0) + 1
            if kind not in schema.DRAFT_MARKERS:
                unknown.append({"section": fname, "marker": m.group(0)})
            if kind == "directive":
                open_directives.append({"section": fname, "text": body.strip()})
            if kind == "todo-fact":
                open_fact_todos.append({"section": fname, "text": body.strip()})
            if kind == "claim":
                claim_occurrences.setdefault(body.strip(), []).append(fname)
    return {
        "counts": counts,
        "unknown": unknown,
        "open_directives": open_directives,
        "open_fact_todos": open_fact_todos,
        "evidence_readiness_open": len(open_fact_todos),
        "claim_occurrences": claim_occurrences,
    }


def terminology_check(pkg) -> list[dict]:
    """术语账校验（D-W02）：返回 issue 列表（level/code/message/where）。"""
    issues = []

    def err(code, msg, where=None):
        issues.append({"level": "error", "code": code, "message": msg,
                       "where": where})

    def warn(code, msg, where=None):
        issues.append({"level": "warning", "code": code, "message": msg,
                       "where": where})

    term = pkg.get("terminology") or {}
    terms = term.get("terms") or []
    sections = section_files(pkg["root"])
    for i, t in enumerate(terms):
        where = f"terminology[{i}]"
        if not t.get("canonical"):
            err("terms.no_canonical", "术语账条目缺 canonical form", where)
            continue
        if not t.get("first_use_full"):
            warn("terms.no_full_form",
                 f"术语 {t['canonical']!r} 缺首现全称：首现处须给全称或标旗问作者",
                 where)
        if t.get("coined"):
            err("terms.coined",
                f"术语 {t['canonical']!r} 被标为自创：不许自创术语入稿", where)
    if term.get("locked"):
        for t in terms:
            for variant in t.get("variants") or []:
                if not variant:
                    continue
                for fname, text in sorted(sections.items()):
                    if variant in text:
                        err("terms.variant_in_text",
                            f"术语账已锁定：变体 {variant!r} 仍出现在 {fname}"
                            f"（canonical={t.get('canonical')!r}）；改名 = 全稿"
                            "替换 + 账本更新，本校验只报不改",
                            f"terminology:{t.get('canonical')}")
    return issues


def allocation_check(pkg) -> list[dict]:
    """正文分配纪律校验（D-W01）：位置图/功能分类/删除日志的机械核对。"""
    issues = []

    def err(code, msg, where=None):
        issues.append({"level": "error", "code": code, "message": msg,
                       "where": where})

    def warn(code, msg, where=None):
        issues.append({"level": "warning", "code": code, "message": msg,
                       "where": where})

    alloc = pkg.get("allocation") or {}
    locations = alloc.get("locations") or []
    claim_ids = {c.get("claim_id")
                 for c in (pkg["claims"] or {}).get("claims") or []}
    section_ids = {s.get("section_id")
                   for s in (pkg["manuscript"] or {}).get("sections") or []}
    seen: dict[tuple, int] = {}
    for i, loc in enumerate(locations):
        where = f"allocation.locations[{i}]"
        if loc.get("claim_id") not in claim_ids:
            err("allocation.unknown_claim",
                f"位置图条目指向未登记主张 {loc.get('claim_id')!r}", where)
        if loc.get("section") not in section_ids:
            err("allocation.unknown_section",
                f"位置图条目指向未登记节 {loc.get('section')!r}", where)
        if loc.get("role") not in schema.LOCATION_ROLES:
            err("allocation.role_vocab",
                f"位置图功能 {loc.get('role')!r} 不在 {schema.LOCATION_ROLES}",
                where)
        key = (loc.get("claim_id"), loc.get("section"))
        seen[key] = seen.get(key, 0) + 1
    for (cid, sec), n in seen.items():
        roles = [l.get("role") for l in locations
                 if l.get("claim_id") == cid and l.get("section") == sec]
        if roles.count("demonstrate") > 1:
            err("allocation.duplicate_demonstrate",
                f"主张 {cid} 在节 {sec} 被标 demonstrate {roles.count('demonstrate')} 次"
                "：同一主张同一节只许一处论证位（主张重复审计）",
                f"allocation:{cid}")
    for i, r in enumerate(alloc.get("results") or []):
        where = f"allocation.results[{i}]"
        if r.get("function") not in schema.RESULT_FUNCTIONS:
            err("allocation.function_vocab",
                f"结果功能 {r.get('function')!r} 不在八分类 {schema.RESULT_FUNCTIONS}",
                where)
        if r.get("destination") not in schema.DESTINATIONS:
            err("allocation.destination_vocab",
                f"结果目的地 {r.get('destination')!r} 不在 {schema.DESTINATIONS}",
                where)
        if r.get("function") == "core_discovery" and \
                r.get("destination") == "supplementary":
            err("allocation.core_in_si",
                "结论改变型证据（core_discovery）不许埋进补充材料"
                "（main-text-discipline 非协商例外）", where)
    for i, d in enumerate(alloc.get("deletion_log") or []):
        if not d.get("what") or not d.get("reason"):
            err("allocation.deletion_log_incomplete",
                "删除日志条目须含 what 与 reason（可审计压缩记录）",
                f"allocation.deletion_log[{i}]")
    if alloc.get("enforced"):
        occ = scan_markers(pkg)["claim_occurrences"]
        mapped = {(l.get("claim_id"), l.get("section")) for l in locations}
        section_file_to_id = {
            s.get("file"): s.get("section_id")
            for s in (pkg["manuscript"] or {}).get("sections") or []}
        for cid, files in sorted(occ.items()):
            for fname in files:
                sid = section_file_to_id.get(fname)
                if (cid, sid) not in mapped:
                    err("allocation.unmapped_occurrence",
                        f"正文主张出现处未入位置图：{cid} @ {sid or fname}"
                        "（enforced 模式下每处出现须标功能）",
                        f"allocation:{cid}")
    else:
        if locations:
            warn("allocation.not_enforced",
                 "位置图已建但 enforced=false：覆盖性未机械核对")
    return issues

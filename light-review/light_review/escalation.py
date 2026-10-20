"""席位侧证据升格三查（v1.1，REV-D10）：concern 入共识账前的独立机械门。

v1 的欠账：concern 的证据指针「存在」只靠规程自觉，双指针准入顶着，
没有独立机械门。本模块在 consensus 落盘口逐条验三查，结果逐条落账
（consensus.yaml 的 escalation_checks 块），任一查判 fail 即拒入账：

1. 指针实位：结构化指针逐个解析到承接快照的实物（登记行/文件/发现），
   指名不存在对象 = 虚设（fabricated），拒。自由文本指针（自然语言
   复合形态）机械不可解析，落 not_checkable 如实登记，不冒充已验，
   也不误杀——虚设的定义钉在「指名结构化对象而对象不存在」。
2. 逐字支撑：concern 带 support_snippet 时，片段必须在证据指针所指
   原文中逐字命中（原文 = 源文件文本或登记行的结构化转储）；对不上
   （mismatch）拒。未带片段落 not_provided 如实登记。
3. 强度不越档：computed severity 为 critical 时，证据中必须有
   confirmed_error 级（非 flag_only）法医发现指针托底——critical 是
   最强档，只许由已确认错误级证据支撑，其余证据封顶 major（与
   GRIM 旗标不定罪、佐证不抬级的既有纪律同构）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .project import fold_findings, load_package
from .util import load_structured

_ID_STOP = re.compile(r"[#/\s；;，,（(]")
_LINE_ID = re.compile(r"\bR-[A-Z0-9][A-Z0-9-]*\b")
_INPUTS_FORM = re.compile(r"^(analysis|manuscript|figure)\s+(inputs/\S+)$")


# ---------------------------------------------------------------- 上下文

def load_context(root, pkg=None) -> dict:
    """从承接快照装解析上下文（只读上游登记物，不产生任何判断）。"""
    root = Path(root)
    pkg = pkg or load_package(root)
    review = pkg["review"] or {}
    intake = review.get("intake") or {}
    ctx = {
        "claims": {}, "conclusions": {}, "figures": {}, "numbers": {},
        "lock": {}, "sections": {}, "delivery": {}, "verdict_lines": set(),
        "findings": {}, "summaries": {}, "pkg_dirs": {},
        "verdicts_text": "", "has_intake": bool(intake),
    }
    for f in fold_findings(pkg["findings"] or []):
        ctx["findings"][f["finding_id"]] = f
    for e in (pkg["summaries"] or {}).get("entries") or []:
        if e.get("stat_id"):
            ctx["summaries"][e["stat_id"]] = e

    def _rows(base, name, key):
        if base is None:
            return []
        data = load_structured(Path(base) / name) or {}
        return data.get(key) or []

    mp = (intake.get("manuscript") or {}).get("package_path")
    ap = (intake.get("analysis") or {}).get("package_path")
    fp = (intake.get("figure") or {}).get("package_path")
    if mp:
        ctx["pkg_dirs"]["manuscript"] = Path(mp)
        for c in _rows(mp, "claims_register.yaml", "claims"):
            ctx["claims"][c.get("claim_id")] = c
        for n in _rows(mp, "numbers_ledger.yaml", "numbers"):
            ctx["numbers"][n.get("num_id")] = n
        for f in _rows(mp, "figures_manifest.yaml", "figures"):
            ctx["figures"][f.get("figure_id")] = f
        lock = load_structured(Path(mp) / "references.lock.json") or {}
        for e in lock.get("entries") or []:
            ctx["lock"][e.get("key")] = e
        sdir = Path(mp) / "sections"
        if sdir.is_dir():
            for p in sorted(sdir.glob("*.md")):
                ctx["sections"][p.name] = p.read_text(encoding="utf-8")
    if ap:
        ctx["pkg_dirs"]["analysis"] = Path(ap)
        conclusions = load_structured(Path(ap) / "conclusions.yaml") or {}
        grades = {s.get("claim_id"): s
                  for s in conclusions.get("strength") or []}
        for c in conclusions.get("claims_verdict") or []:
            row = dict(c)
            if c.get("claim_id") in grades:
                row["_strength"] = grades[c["claim_id"]]
            ctx["conclusions"][c.get("claim_id")] = row
        vpath = Path(ap) / "verdicts.jsonl"
        if vpath.exists():
            ctx["verdicts_text"] = vpath.read_text(encoding="utf-8")
            for line in ctx["verdicts_text"].splitlines():
                try:
                    import json
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("registry_line_id"):
                    ctx["verdict_lines"].add(row["registry_line_id"])
    if fp:
        ctx["pkg_dirs"]["figure"] = Path(fp)
        delivery = load_structured(Path(fp) / "delivery.yaml") or {}
        for f in delivery.get("figures") or []:
            ctx["delivery"][f.get("fig_id")] = f
    return ctx


def _dump(obj) -> str:
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------- 单指针解析

def _segment(segment: str, ctx) -> dict:
    """解析一个指针段：{result, detail, text, evidence_class}。

    result：resolved（实位命中）/ fabricated（指名结构化对象而不存在）
    / not_checkable（自由文本，机械不可解析）。
    """
    s = segment.strip()
    if not s:
        return {"result": "not_checkable", "detail": "空指针段",
                "text": None, "evidence_class": None}

    def _ident(rest: str) -> str:
        m = _ID_STOP.search(rest)
        return rest[:m.start()] if m else rest

    for prefix, table, label in (
            ("claims_register:", "claims", "主张登记行"),
            ("conclusions:", "conclusions", "结论行"),
            ("figures_manifest:", "figures", "图登记行"),
            ("numbers_ledger:", "numbers", "数字登记行"),
            ("references.lock:", "lock", "引用 lock 条目"),
            ("delivery:", "delivery", "图包交付行")):
        if s.startswith(prefix):
            ident = _ident(s[len(prefix):])
            obj = ctx[table].get(ident)
            if obj is None:
                return {"result": "fabricated",
                        "detail": f"{label} {ident} 不存在（指针虚设）",
                        "text": None, "evidence_class": None}
            return {"result": "resolved",
                    "detail": f"{label} {ident} 实位命中",
                    "text": _dump(obj), "evidence_class": table}
    if s.startswith("findings:"):
        ident = _ident(s[len("findings:"):])
        f = ctx["findings"].get(ident)
        if f is None:
            return {"result": "fabricated",
                    "detail": f"法医发现 {ident} 不存在（指针虚设）",
                    "text": None, "evidence_class": None}
        cls = ("confirmed_error" if f.get("category") == "confirmed_error"
               and not f.get("flag_only") else "finding")
        return {"result": "resolved",
                "detail": f"法医发现 {ident} 实位命中"
                          f"（category={f.get('category')}，"
                          f"flag_only={f.get('flag_only')}）",
                "text": _dump(f), "evidence_class": cls}
    if s.startswith("summaries:"):
        ident = _ident(s[len("summaries:"):])
        e = ctx["summaries"].get(ident)
        if e is None:
            return {"result": "fabricated",
                    "detail": f"GRIM 登记量 {ident} 不存在（指针虚设）",
                    "text": None, "evidence_class": None}
        return {"result": "resolved",
                "detail": f"GRIM 登记量 {ident} 实位命中",
                "text": _dump(e), "evidence_class": "summaries"}
    if s.startswith("verdicts.jsonl"):
        tokens = _LINE_ID.findall(s)
        if not ctx["verdicts_text"]:
            return {"result": "not_checkable",
                    "detail": "承接快照无 verdicts.jsonl 可解析",
                    "text": None, "evidence_class": None}
        missing = [t for t in tokens if t not in ctx["verdict_lines"]]
        if missing:
            return {"result": "fabricated",
                    "detail": f"verdicts 登记行不存在：{missing}（指针虚设）",
                    "text": None, "evidence_class": None}
        return {"result": "resolved",
                "detail": f"verdicts 登记行 {tokens or '（文件）'} 实位命中",
                "text": ctx["verdicts_text"],
                "evidence_class": "verdicts"}
    if s.startswith("sections/") or s.startswith("sections:"):
        name = s.split("/", 1)[1] if "/" in s else s.split(":", 1)[1]
        name = name.strip()
        if name in ctx["sections"]:
            return {"result": "resolved",
                    "detail": f"章节文件 {name} 实位命中",
                    "text": ctx["sections"][name],
                    "evidence_class": "sections"}
        # 路径形态指针不判虚设：文件布局随包而变（演示 inputs 目录
        # 即在包同级），未命中只落未定位、如实登记，不误杀。
        return {"result": "not_checkable",
                "detail": f"章节文件 {name} 未在承接稿件中定位到"
                          "（路径形态指针，落未验不判虚设）",
                "text": None, "evidence_class": None}
    m = _INPUTS_FORM.match(s)
    if m:
        base = ctx["pkg_dirs"].get(m.group(1))
        rel = m.group(2)
        if base is not None:
            for cand in (base / rel, base.parent / rel):
                if cand.exists():
                    return {"result": "resolved",
                            "detail": f"上游文件 {rel} 实位命中",
                            "text": cand.read_text(encoding="utf-8"),
                            "evidence_class": "file"}
        return {"result": "not_checkable",
                "detail": f"上游文件 {rel} 未在承接包内定位到（自由路径形态）",
                "text": None, "evidence_class": None}
    return {"result": "not_checkable",
            "detail": "自由文本指针，机械不可解析（如实登记，不冒充已验）",
            "text": None, "evidence_class": None}


def resolve_pointer(pointer, ctx) -> dict:
    """解析一个（可复合）指针：任一段虚设即虚设；有命中即已解析。"""
    if not (pointer or "").strip():
        return {"result": "absent", "detail": "未登记该指针",
                "texts": [], "evidence_classes": []}
    parts = [_segment(seg, ctx) for seg in str(pointer).split(" + ")]
    results = [p["result"] for p in parts]
    if "fabricated" in results:
        result = "fabricated"
    elif "resolved" in results:
        result = "resolved"
    else:
        result = "not_checkable"
    return {
        "result": result,
        "detail": "；".join(p["detail"] for p in parts),
        "texts": [p["text"] for p in parts if p.get("text")],
        "evidence_classes": [p["evidence_class"] for p in parts
                             if p.get("evidence_class")],
    }


# ---------------------------------------------------------------- 三查

def check_concern(raw: dict, computed_severity, ctx) -> tuple[dict, list]:
    """对一条 concern 跑升格三查，返回 (escalation_checks, fail 理由列表)。

    escalation_checks 逐条落账：{pointer_resolution, verbatim_support,
    severity_cap, verdict}，每查带 result 与 detail。
    """
    pointers = raw.get("pointers") or {}
    claim_r = resolve_pointer(pointers.get("claim_pointer"), ctx)
    evid_r = resolve_pointer(pointers.get("evidence_pointer"), ctx)
    fails = []

    # 查一：指针实位
    pres_parts = []
    pres_result = "absent"
    for label, r in (("claim_pointer", claim_r), ("evidence_pointer", evid_r)):
        pres_parts.append(f"{label}：{r['detail']}")
        if r["result"] == "fabricated":
            fails.append(f"指针虚设——{label}：{r['detail']}")
    if "fabricated" in (claim_r["result"], evid_r["result"]):
        pres_result = "fabricated"
    elif "resolved" in (claim_r["result"], evid_r["result"]):
        pres_result = "resolved"
    elif "not_checkable" in (claim_r["result"], evid_r["result"]):
        pres_result = "not_checkable"
    pointer_resolution = {"result": pres_result,
                          "detail": "；".join(pres_parts)}

    # 查二：逐字支撑（片段对证据指针所指原文逐字命中）
    snippet = raw.get("support_snippet") \
        or pointers.get("support_snippet")
    if not (snippet or "").strip():
        verbatim = {"result": "not_provided",
                    "detail": "未带逐字支撑片段（如实登记，未验）"}
    elif not evid_r["texts"]:
        verbatim = {"result": "not_checkable",
                    "detail": "带了逐字片段，但证据指针无可解析原文可比对"}
    elif any(snippet in t for t in evid_r["texts"]):
        verbatim = {"result": "matched",
                    "detail": "逐字片段在证据原文中命中"}
    else:
        verbatim = {"result": "mismatch",
                    "detail": "逐字片段在证据指针所指原文中无命中（对不上）"}
        fails.append("逐字支撑对不上——support_snippet 在证据原文中无命中")

    # 查三：强度不越档（critical 须 confirmed_error 级证据托底）
    if computed_severity != "critical":
        cap = {"result": "within_cap",
               "detail": f"severity={computed_severity} 非 critical，"
                         "封顶不触发（critical 只许 confirmed_error 级"
                         "证据托底，其余封顶 major）"}
    else:
        classes = claim_r["evidence_classes"] + evid_r["evidence_classes"]
        if "confirmed_error" in classes:
            cap = {"result": "within_cap",
                   "detail": "critical 由 confirmed_error 级（非 flag_only）"
                             "法医发现指针托底，未越档"}
        else:
            cap = {"result": "over_cap",
                   "detail": "severity=critical 但证据中无 confirmed_error 级"
                             "（非 flag_only）发现指针：强度越过证据档"}
            fails.append("强度越档——critical 无 confirmed_error 级证据托底")

    if fails:
        verdict = "fail"
    elif "not_checkable" in (pres_result, verbatim["result"]) \
            or verbatim["result"] == "not_provided" \
            or pres_result == "absent":
        verdict = "partial"
    else:
        verdict = "pass"
    checks = {"pointer_resolution": pointer_resolution,
              "verbatim_support": verbatim,
              "severity_cap": cap,
              "verdict": verdict}
    return checks, fails

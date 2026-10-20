"""风险门（草案 §四两级门 + 拍板 E3 分级硬度）。

硬度口径（E3，写死不许临场放宽）：
- hard_exclude（预警命中 / 已停刊被剔除 / scope 明显不符 /
  用户排除项）：命中即出局，用户确认也**不许放行**；
- quasi_hard（掠夺·劫持社区名单命中 / 域名不一致）：默认排除，
  仅当用户书面知情确认记录字段齐全（确认人、确认文本、日期）
  才可放行，放行与命中理由永久留痕；
- soft_warn：保留推荐，证据卡必须显形；
- clear：无任何命中。

数据源纪律（JS-02）：风险核查只用合法开放源——本地可注入的
名单文件（如 stop-predatory 风格 CSV）+ 预警/停刊的联网核查
登记；核查记录本身必须带 source 与 checked_at，查不到要落
hit=null + 状态说明，不许把「没查」登记成「没命中」。
被排除条目进 excluded[] 只增不改（本模块只 append，校验器
核对其形态；任何其他代码路径不许删改 excluded 条目）。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from . import schema
from .gates import GateError, advance_to, require_selection
from .project import find_candidate, save_selection
from .util import normalize_name, today

OVERRIDE_REQUIRED_FIELDS = ["confirmed_by", "confirmation_text", "date"]


def evaluate_level(checks: list[dict]) -> str:
    """由核查记录集算风险等级（只看 hit is True 的条目）。"""
    hits = {c.get("condition") for c in checks or [] if c.get("hit") is True}
    if hits & set(schema.HARD_CONDITIONS):
        return "hard_exclude"
    if hits & set(schema.QUASI_HARD_CONDITIONS):
        return "quasi_hard"
    if hits & set(schema.SOFT_CONDITIONS):
        return "soft_warn"
    return "clear"


def valid_override(override) -> tuple[bool, list[str]]:
    """准硬门放行记录校验：字段齐 + 文本非空才有效。"""
    if not isinstance(override, dict):
        return False, ["放行记录不是对象"]
    gaps = [f"放行记录缺字段 {f}" for f in OVERRIDE_REQUIRED_FIELDS
            if override.get(f) in (None, "")]
    return (not gaps), gaps


def load_name_list(path) -> list[dict]:
    """读本地可注入名单文件（stop-predatory 风格 CSV）。

    形态：name,issn,condition,source,version —— condition 须在
    风险条件词表内（一级/准硬名单皆可）；返回归一化条目列表。
    """
    text = Path(path).read_text(encoding="utf-8")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        rows.append({
            "name": (row.get("name") or "").strip(),
            "name_key": normalize_name(row.get("name") or ""),
            "issn": (row.get("issn") or "").strip() or None,
            "condition": (row.get("condition") or "").strip(),
            "source": (row.get("source") or "").strip(),
            "version": (row.get("version") or "").strip(),
        })
    return rows


def checks_from_name_list(candidates: list[dict], name_list: list[dict],
                          checked_at: str) -> dict:
    """名单 × 候选池匹配，生成逐刊核查记录（未命中也落 hit=False）。

    返回 {candidate_id: [check, ...]}。名单文件给出的条件为命中
    依据；名单来源与版本逐条落字（可注入 = 可换源 + 可审计）。
    """
    out: dict[str, list[dict]] = {}
    for cand in candidates:
        rows = []
        name_key = normalize_name(cand.get("name") or "")
        issns = {cand.get("issn"), cand.get("eissn")} - {None}
        for item in name_list:
            hit = (item["name_key"] == name_key
                   or (item["issn"] and item["issn"] in issns))
            rows.append({
                "condition": item["condition"],
                "hit": bool(hit),
                "source": item["source"] or "local_name_list",
                "source_ref": f"name_list v{item['version'] or '未标版本'}",
                "checked_at": checked_at,
                "note": "名单命中" if hit else None,
            })
        out[cand.get("candidate_id")] = rows
    return out


def apply_gate(root, checks_by_candidate: dict,
               overrides: dict | None = None,
               today_str: str | None = None) -> dict:
    """执行风险门：算级、处置排除、跃迁 gated。

    checks_by_candidate: {candidate_id 或刊名: [check, ...]}；
    overrides: {candidate_id 或刊名: 放行记录}（仅对 quasi_hard
    有效；对 hard_exclude 给放行记录 = 报错，E3 写死）。
    任一候选缺核查记录 → 整批拒绝（不许部分过门）。
    """
    root = Path(root)
    selection = require_selection(root)
    if selection.get("status") not in ("verified", "gated"):
        raise GateError([f"状态 {selection.get('status')} 不许过风险门"
                         "（须先 verified）"])
    overrides = overrides or {}
    today_str = today_str or today()
    gaps: list[str] = []
    plan = []
    for cand in list(selection.get("candidates") or []):
        checks = (checks_by_candidate.get(cand.get("candidate_id"))
                  or checks_by_candidate.get(cand.get("name")))
        if checks is None:
            gaps.append(f"候选 {cand.get('name')} 缺风险核查记录"
                        "（名单核查未完成不许宣称安全，JS-02）")
            continue
        for check in checks:
            if check.get("condition") not in schema.RISK_CONDITIONS:
                gaps.append(f"候选 {cand.get('name')} 风险条件 "
                            f"{check.get('condition')!r} 不在词表")
            if check.get("hit") is True and not check.get("source"):
                gaps.append(f"候选 {cand.get('name')} 命中记录 "
                            f"{check.get('condition')} 缺来源（无源不许落命中）")
        level = evaluate_level(checks)
        override = (overrides.get(cand.get("candidate_id"))
                    or overrides.get(cand.get("name")))
        if level == "hard_exclude" and override is not None:
            gaps.append(f"候选 {cand.get('name')} 为硬排除"
                        "（预警/停刊/scope/用户排除），用户确认不许放行（E3）")
        if level == "quasi_hard" and override is not None:
            ok, ogaps = valid_override(override)
            if not ok:
                gaps.extend(f"候选 {cand.get('name')}：" + g for g in ogaps)
        plan.append((cand, checks, level, override))
    if gaps:
        raise GateError(gaps)

    excluded_now = []
    levels = {}
    for cand, checks, level, override in plan:
        levels[cand.get("name")] = level
        cand["risk"] = {"level": level, "checks": checks,
                        "override": override,
                        "evaluated_at": today_str}
        must_exclude = level == "hard_exclude" or (
            level == "quasi_hard" and override is None)
        if must_exclude:
            cand["tier"] = "excluded"
            reasons = [f"{c['condition']}（来源：{c.get('source')}，"
                       f"{c.get('source_ref') or '无版本标注'}）"
                       for c in checks if c.get("hit") is True]
            selection.setdefault("excluded", []).append({
                "candidate_id": cand.get("candidate_id"),
                "name": cand.get("name"),
                "level": level,
                "reasons": reasons,
                "candidate_snapshot": cand,
                "at": today_str,
                "by": "light-journal-select gate",
            })
            selection["candidates"].remove(cand)
            excluded_now.append(cand.get("name"))
    save_selection(root, selection)
    advanced = None
    if selection.get("status") == "verified":
        advance_to(root, "gated", by="light-journal-select gate")
        advanced = "gated"
    return {"excluded": excluded_now,
            "remaining": [c["name"] for c in selection.get("candidates") or []],
            "levels": levels,
            "status": advanced or selection.get("status")}

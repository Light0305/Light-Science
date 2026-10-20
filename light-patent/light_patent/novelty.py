"""P2 检索查新：两轮召回登记、候选池、D1 锁定与三态门。

纪律：失败分型三态严格分开（LP-06）——渠道失败不是「无现有
技术」，检索成功 0 条也不是；池空记未评估。著录未核验条目只
许进池待复核，不许作决定性依据（不得锁 D1，LP-01/LP-05）。
区别特征 Fk 全案统一编号，是 P3 撰写与 P5 答复共用的同一份
证据账。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .intake import require_audited
from .project import (
    PatentError, case_path, load_case, load_yaml_or, save_case, set_status,
)
from .util import append_jsonl, dump_yaml, read_jsonl, today


def register_search(root, payload: dict) -> dict:
    """登记一轮检索。payload: {round, channel_id, query, outcome,
    results: [pool entries]}。outcome 属失败分型词表。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    gaps = []
    if payload.get("round") not in schema.SEARCH_ROUNDS:
        gaps.append(f"检索轮次 {payload.get('round')!r} 不在两轮词表内"
                    "（means_phrases / classification_neighborhood）")
    if payload.get("outcome") not in schema.SEARCH_OUTCOMES:
        gaps.append(f"检索结果分型 {payload.get('outcome')!r} 不在词表内"
                    "（LP-06 三态 + 未评估）")
    known_channels = {c["channel_id"] for c in schema.CHANNELS}
    if payload.get("channel_id") not in known_channels:
        gaps.append(f"渠道 {payload.get('channel_id')!r} 不在渠道登记表内")
    if gaps:
        raise PatentError(gaps)
    row = {
        "at": today(),
        "round": payload["round"],
        "channel_id": payload["channel_id"],
        "query": payload.get("query") or "",
        "outcome": payload["outcome"],
        "hits": len(payload.get("results") or []),
        "note": payload.get("note") or "",
    }
    append_jsonl(case_path(root, "search_log"), [row])
    pool = load_yaml_or(root, "pool",
                        {"kind": "light-patent/prior-art-pool",
                         "case_id": case["case_id"], "entries": []})
    seen = {e["pub_number"] for e in pool["entries"]}
    for e in payload.get("results") or []:
        if e.get("pub_number") in seen:
            continue
        pool["entries"].append({
            "pub_number": e.get("pub_number") or "",
            "title": e.get("title") or "",
            "applicant": e.get("applicant") or "",
            "pub_date": e.get("pub_date") or "",
            "url": e.get("url") or "",
            "verified": bool(e.get("verified")),
            "evidence_level": e.get("evidence_level") or "abstract",
            "relevance": e.get("relevance"),
            "source_channel": payload["channel_id"],
            "found_in_round": payload["round"],
        })
        seen.add(e.get("pub_number"))
    dump_yaml(case_path(root, "pool"), pool)
    return {"round": row["round"], "outcome": row["outcome"],
            "pool_size": len(pool["entries"])}


def lock_d1(root, payload: dict) -> dict:
    """锁定 D1 并产区别特征表。payload: {pub_number, rationale,
    evidence_level, feature_comparison: [{feature_ref, claim_feature,
    in_d1, note}], gate, gate_reasons}。"""
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    pool = load_yaml_or(root, "pool", {"entries": []})
    entry = next((e for e in pool["entries"]
                  if e["pub_number"] == payload.get("pub_number")), None)
    gaps = []
    if entry is None:
        gaps.append(f"D1 候选 {payload.get('pub_number')!r} 不在候选池内"
                    "（禁止假 D1，LP-05）")
    elif not entry.get("verified"):
        gaps.append(f"D1 候选 {entry['pub_number']} 著录未核验：待复核"
                    "条目不得作决定性依据（LP-01），先核验再锁定")
    if not (payload.get("rationale") or "").strip():
        gaps.append("缺 D1 选定理由（LP-05：锁定必须写理由）")
    if payload.get("evidence_level") not in schema.EVIDENCE_LEVELS:
        gaps.append("缺证据级别（abstract / full_text）：摘要级判断不得"
                    "表述为全文结论（LP-05）")
    if payload.get("gate") not in schema.NOVELTY_GATES:
        gaps.append(f"查新门结论 {payload.get('gate')!r} 不在三态词表内")
    comparison = payload.get("feature_comparison") or []
    if not comparison:
        gaps.append("缺逐特征比对表：无区别特征表不许锁 D1")
    if gaps:
        raise PatentError(gaps)
    distinguishing = []
    n = 0
    for row in comparison:
        if not row.get("in_d1"):
            n += 1
            distinguishing.append({
                "fk": f"F{n}",
                "feature_ref": row.get("feature_ref") or "",
                "claim_feature": row.get("claim_feature") or "",
                "contribution": row.get("contribution") or "",
                "note": row.get("note") or "",
            })
    d1 = {
        "kind": "light-patent/d1-lock",
        "case_id": case["case_id"],
        "locked_at": today(),
        "d1": entry["pub_number"],
        "rationale": payload["rationale"],
        "evidence_level": payload["evidence_level"],
        "feature_comparison": comparison,
        "distinguishing_features": distinguishing,
        "gate": payload["gate"],
        "gate_reasons": payload.get("gate_reasons") or [],
        "disclaimers": [schema.DRAFT_DISCLAIMER, schema.SCREENING_DISCLAIMER],
    }
    dump_yaml(case_path(root, "d1"), d1)
    if payload["gate"] == "fail":
        case["degraded"] = {
            "gate_id": "novelty_gate_fail_degraded",
            "detail": "查新三态门为「不过」：仍可成文，但创造性论述"
                      "降级、交付显式标注 D1 未被区别特征充分拉开",
            "fix_pointer": "收窄独权至区别特征组合后重跑查新门",
        }
    save_case(root, case)
    if case["status"] in ("audited", "mined"):
        set_status(root, case, "searched", "light-patent novelty")
    return {"d1": d1["d1"], "distinguishing": len(distinguishing),
            "gate": d1["gate"]}


def search_summary(root) -> dict:
    rows = read_jsonl(case_path(root, "search_log"))
    pool = load_yaml_or(root, "pool", {"entries": []})
    return {
        "rounds": rows,
        "pool_size": len(pool.get("entries") or []),
        "failures": [r for r in rows if r["outcome"] == "channel_failure"],
        "zero_result_rounds": [r for r in rows
                               if r["outcome"] == "zero_results"],
    }

"""案件包全量校验：跨文件一致性与纪律总检。

逐项点名 errors/warnings；STALE（检查后改稿）在此点名。校验
不替代 P4 检查器：P4 管文本与结构，本模块管全包账目自洽。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import case_path, load_case, load_yaml_or
from .util import read_jsonl, read_text, sha256_text

_SENSITIVE_KEYS = ("id_card", "id_number", "身份证", "passport_no",
                   "bank_account", "phone", "mobile", "email")


def _walk_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{prefix}{k}"
            yield from _walk_keys(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{prefix}{i}.")


def validate_package(root) -> dict:
    root = Path(root)
    errors, warnings = [], []
    case = load_case(root)

    # V-01 基本词表
    if case.get("status") not in schema.CASE_STATES:
        errors.append(f"案件状态 {case.get('status')!r} 不在状态词表内")
    if case.get("patent_type") not in schema.PATENT_TYPES_V1:
        errors.append("patent_type 超出 v1 范围（只做发明）")
    # V-02 发明人自然人（84 号令 4.1.2）
    for inv in (case.get("parties") or {}).get("inventors") or []:
        name = inv.get("name") if isinstance(inv, dict) else inv
        if name and any(t in str(name) for t in ("课题组", "公司", "大学",
                                                "研究院", "人工智能", "AI")):
            if "人工智能" in str(name) or "课题组" in str(name):
                errors.append(f"发明人 {name!r} 疑似单位/集体/AI 名称："
                              "发明人应当是自然人（84 号令 4.1.2）")
    # V-03 敏感字段名（LP-12：身份信息不落本包）
    for key in _walk_keys(case.get("parties") or {}):
        leaf = key.rsplit(".", 1)[-1].lower()
        if leaf in _SENSITIVE_KEYS:
            errors.append(f"当事人数据出现敏感字段 {key}：身份证件号等"
                          "身份信息不落本包文件（LP-12）")

    audit = load_yaml_or(root, "audit", None)
    status = case.get("status")
    order = schema.STATE_ORDER.get(status, 0)
    # V-04 阶段账：推进过审计段必须有审计件且结论非阻断
    if order >= schema.STATE_ORDER["audited"]:
        if not audit:
            errors.append("状态已过 audited 但无公开审计件")
        elif audit.get("conclusion") == "blocked_prior_disclosure" \
                and order > schema.STATE_ORDER["audited"]:
            errors.append("审计结论 blocked 却已推进过 audited 段（LP-09）")
    # V-05 查新账：searched 之后须有 D1
    d1 = load_yaml_or(root, "d1", None)
    if order >= schema.STATE_ORDER["searched"] and not d1:
        errors.append("状态已过 searched 但无 D1 锁定件")
    if d1 and d1.get("gate") == "fail" and not case.get("degraded"):
        errors.append("查新门 fail 但案件未落 degraded 降级点名")

    # V-06 权要账：支持四值已在登记时拦；此处核对支持映射与权要一致
    claims = load_yaml_or(root, "claims", None)
    support = load_yaml_or(root, "support_map", {"rows": []})
    if claims:
        n_features = sum(len(c.get("features") or [])
                         for c in claims.get("claims") or [])
        if len(support.get("rows") or []) != n_features:
            errors.append("支持映射行数与权要特征数不一致（支持账漂移）")
    # V-07 STALE：检查报告哈希 vs 当前工件
    report = load_yaml_or(root, "check_report", None)
    if report:
        for key, h in (report.get("artifact_hashes") or {}).items():
            p = case_path(root, key)
            if p.exists() and sha256_text(read_text(p)) != h:
                errors.append(f"检查后工件已改动（{key}）：检查报告 STALE，须重跑 check")
        if report.get("delivery_grade") == "deliverable_draft" \
                and report.get("errors"):
            errors.append("交付等级与检查结论矛盾：有 ERROR 却标可交付草案")
    # V-08 答复账：第 33 条出处（登记时已拦，此处兜底全量复核）
    for a in read_jsonl(case_path(root, "oa_amendments")):
        if not a.get("basis_pointer") or not a.get("basis_quote"):
            errors.append(f"修改 {a.get('amendment_id')} 缺第 33 条出处指针/摘录")
    # V-09 检索日志分型词表兜底
    for row in read_jsonl(case_path(root, "search_log")):
        if row.get("outcome") not in schema.SEARCH_OUTCOMES:
            errors.append(f"检索日志分型越界：{row.get('outcome')!r}")
    # V-10 摘要字数兜底
    abstract = read_text(case_path(root, "abstract_md"))
    body = re.sub(r"^#.*$", "", abstract, flags=re.M).strip()
    if body and len(body) > schema.ABSTRACT_MAX_CHARS:
        errors.append(f"摘要 {len(body)} 字超 300 字上限")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "status": status,
        "case_id": case.get("case_id"),
    }

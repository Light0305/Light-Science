"""校验器：选刊包全部纪律的确定性核查（只出判定，不改文件）。

fail-closed（与姊妹包同口径）：error = 纪律被破；warning = 须落字
说明的风险。校验器的绿灯只表示「未发现自动可判的失败」，不表示
某刊安全或适合——不存在「绝对安全」的表述（JS-02）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import FILES, load_selection
from .util import load_structured, sha256_file
from .verify import (
    Report, check_oa_license_block, check_policy_checks,
    check_scope_checks, check_verification_block,
)


def validate_selection(selection: dict) -> Report:
    rep = Report()
    if not isinstance(selection, dict):
        rep.error("package.not_object", "selection.yaml 须为对象")
        return rep
    status = selection.get("status")
    if status not in schema.STATES:
        rep.error("selection.status",
                  f"status {status!r} 不在状态机词表 {schema.STATES}")
    history = [h.get("state") for h in selection.get("status_history") or []]
    order = [schema.STATES.index(s) for s in history if s in schema.STATES]
    if order != sorted(order) or (history and history[-1] != status):
        rep.error("selection.history",
                  "status_history 与状态机顺序或当前状态不一致")
    manuscript = selection.get("manuscript") or {}
    if manuscript.get("language") not in schema.LANGUAGES:
        rep.error("manuscript.language",
                  f"稿件语言 {manuscript.get('language')!r} 必填且须 ∈ "
                  f"{schema.LANGUAGES}")
    if manuscript.get("type") not in schema.MANUSCRIPT_TYPES:
        rep.error("manuscript.type",
                  f"稿件类型 {manuscript.get('type')!r} 不在词表")

    fingerprint = selection.get("fingerprint")
    queries = selection.get("queries") or []
    if fingerprint is not None:
        for field in schema.FINGERPRINT_FIELDS:
            if fingerprint.get(field) in (None, ""):
                rep.error("fingerprint.field",
                          f"指纹缺字段 {field}（指纹七区必填）",
                          where="fingerprint")
        if fingerprint.get("contribution_type") not in \
                schema.CONTRIBUTION_TYPES:
            rep.error("fingerprint.contribution_type",
                      "贡献类型不在词表", where="fingerprint")
        if fingerprint.get("methods_role") not in schema.METHODS_ROLES:
            rep.error("fingerprint.methods_role",
                      "方法角色不在词表（方法不许冒充领域，JS-04 指纹纪律）",
                      where="fingerprint")
        if not (2 <= len(queries) <= 3):
            rep.error("fingerprint.queries",
                      f"判别性检索式须 2–3 条，实为 {len(queries)} 条",
                      where="queries")
    elif status != "draft":
        rep.error("fingerprint.missing", "已离开 draft 但指纹未落盘")

    cons = selection.get("constraints") or {}
    for key in schema.CONSTRAINT_KEYS:
        if key not in cons:
            rep.error("constraints.key_missing",
                      f"约束键 {key} 缺失（缺项不许静默默认，键必须在场，"
                      "值可为未设）", where="constraints")
        elif cons.get(key) is None:
            rep.warning("constraints.unset",
                        f"约束 {key} 未设（报告将如实渲染「未设」）",
                        where="constraints")

    for run in selection.get("precedent_runs") or []:
        if run.get("status") == "succeeded" and not run.get("evidence_file"):
            rep.error("precedent.evidence_missing",
                      f"先例查询 #{run.get('query_index')} 标 succeeded "
                      "但无原始响应留痕文件", where="precedent_runs")
        if run.get("status") not in ("succeeded", "failed"):
            rep.error("precedent.run_status",
                      f"先例查询状态 {run.get('status')!r} 不在词表"
                      "（失败必须如实落 failed）", where="precedent_runs")

    for row in selection.get("source_type_exclusions") or []:
        for field in ("name", "source_type", "reason", "queried_at"):
            if row.get(field) in (None, ""):
                rep.error("source_type_exclusion.field",
                          f"来源类型排除附记缺字段 {field}（JS-D03 "
                          "附记必须自足：留痕不静默）",
                          where="source_type_exclusions")
        if row.get("source_type") == schema.JOURNAL_SOURCE_TYPE:
            rep.error("source_type_exclusion.is_journal",
                      "来源类型排除附记里混入 journal 型来源"
                      "（过滤口径被破，JS-D03）",
                      where="source_type_exclusions")
    for cand in selection.get("candidates") or []:
        _check_candidate(cand, rep)
    for row in selection.get("excluded") or []:
        for field in ("candidate_id", "name", "level", "reasons", "at"):
            if row.get(field) in (None, "", []):
                rep.error("excluded.field",
                          f"排除留痕缺字段 {field}（excluded 只增不改，"
                          "条目必须自足）", where="excluded")
        if row.get("level") not in ("hard_exclude", "quasi_hard"):
            rep.error("excluded.level",
                      f"排除条目 level {row.get('level')!r} 非排除级",
                      where="excluded")
    _check_decision_handoff(selection, rep)
    return rep


def _check_decision_handoff(selection: dict, rep: Report) -> None:
    """定刊与交接登记的纪律（Phase 2）：定刊不许落在被排除刊、
    准硬门未放行刊上；状态与登记块必须互相对齐。"""
    from .decide import DECISION_FIELDS
    from .gate import valid_override
    from .project import find_candidate

    status = selection.get("status")
    decision = selection.get("decision")
    if decision is not None:
        for field in DECISION_FIELDS:
            if decision.get(field) in (None, ""):
                rep.error("decision.field",
                          f"定刊记录缺字段 {field}（定刊四项缺一不可）",
                          where="decision")
        cid = decision.get("candidate_id")
        for row in selection.get("excluded") or []:
            if row.get("candidate_id") == cid:
                rep.error("decision.on_excluded",
                          f"定刊落在已被风险门排除的刊 "
                          f"{row.get('name')}（{row.get('level')}），"
                          "不许定刊（E3）", where="decision")
        cand = find_candidate(selection, cid or "")
        if cand is not None:
            risk = cand.get("risk") or {}
            if risk.get("level") == "hard_exclude":
                rep.error("decision.on_hard_excluded",
                          "定刊候选风险级 hard_exclude，不许定刊（E3）",
                          where="decision")
            elif risk.get("level") == "quasi_hard":
                ok, _ = valid_override(risk.get("override"))
                if not ok:
                    rep.error("decision.quasi_hard_unreleased",
                              "定刊候选为准硬门命中且无有效放行记录"
                              "（E3）", where="decision")
    elif status in ("decided", "handed_off"):
        rep.error("decision.missing",
                  f"状态已是 {status} 但 decision 未回填", where="decision")
    handoff = selection.get("handoff")
    if status == "handed_off" and not handoff:
        rep.error("handoff.missing",
                  "状态 handed_off 但交接登记块缺失", where="handoff")
    if selection.get("policy_checks") is not None:
        check_policy_checks(selection["policy_checks"], rep,
                            where="policy_checks")
    if handoff is not None:
        for field in ("journal", "candidate_id", "target_dir",
                      "check_record", "download_manifest", "record_id",
                      "at"):
            if handoff.get(field) in (None, ""):
                rep.error("handoff.field",
                          f"交接登记缺字段 {field}", where="handoff")
        if handoff.get("policy_gaps"):
            rep.warning("handoff.policy_gaps",
                        "政策必查项未全覆盖："
                        + "、".join(handoff["policy_gaps"])
                        + "（JS-13：定刊交接前应逐刊核读并点名带回，"
                        "缺项已在 handoff.md 显形，投稿前须补核）",
                        where="handoff")


def _check_candidate(cand: dict, rep: Report) -> None:
    cid = cand.get("candidate_id")
    where = f"candidates.{cid}"
    if cand.get("source") not in schema.CANDIDATE_SOURCES:
        rep.error("candidate.source",
                  f"候选来源 {cand.get('source')!r} 不在词表", where=where)
    stats = cand.get("precedent")
    if stats is not None:
        for field in ("similar_works_n", "queries_covered", "window",
                      "queried_at", "precedents"):
            if stats.get(field) is None:
                rep.error("candidate.precedent_field",
                          f"先例统计缺字段 {field}（统计块必须自足留痕）",
                          where=where)
        if len(stats.get("precedents") or []) > \
                schema.MAX_PRECEDENTS_PER_JOURNAL:
            rep.error("candidate.precedents_too_many",
                      "每刊先例样例超过上限", where=where)
        if stats.get("rate_per_10k") is not None and \
                not stats.get("journal_volume_window"):
            rep.error("candidate.rate_without_volume",
                      "有归一化率却无发文量分母（归一化不许无源）",
                      where=where)
    backfill = cand.get("homepage_backfill")
    if backfill is not None:
        if backfill.get("status") not in ("filled", "unconfirmed"):
            rep.error("candidate.backfill_status",
                      f"官网回填状态 {backfill.get('status')!r} 不在"
                      "词表（filled/unconfirmed，JS-D02）", where=where)
        if backfill.get("status") == "filled":
            if not backfill.get("value") or \
                    not backfill.get("evidence_url"):
                rep.error("candidate.backfill_filled_no_trace",
                          "回填标 filled 却缺取值或证据 URL"
                          "（回填必须带源留痕，JS-D02）", where=where)
            if cand.get("homepage_url") != backfill.get("value"):
                rep.error("candidate.backfill_mismatch",
                          "回填取值与 candidate.homepage_url 不一致",
                          where=where)
    if cand.get("verification") is not None:
        check_verification_block(cand, rep)
    if cand.get("scope_checks") is not None:
        check_scope_checks(cand["scope_checks"], rep,
                           where=f"{where}.scope_checks")
    if cand.get("oa_license") is not None:
        check_oa_license_block(cand["oa_license"], rep,
                               where=f"{where}.oa_license")
    if cand.get("policy_checks") is not None:
        check_policy_checks(cand["policy_checks"], rep,
                            where=f"{where}.policy_checks")
    apc_entry = ((cand.get("verification") or {}).get("metrics")
                 or {}).get("apc")
    if isinstance(apc_entry, dict) and \
            apc_entry.get("status") == "verified" and \
            isinstance(apc_entry.get("value"), dict) and \
            apc_entry["value"].get("charge_timing") is None:
        rep.warning("candidate.apc_timing_undisclosed",
                    f"候选 {cand.get('name')} 费用组收费时点未披露："
                    "费用不透明是资格证据，风险门宜落 apc_opaque "
                    "核查（JS-12 与 §6.3 软警告口径衔接）", where=where)
    risk = cand.get("risk")
    if risk is not None:
        if risk.get("level") not in schema.RISK_LEVELS:
            rep.error("candidate.risk_level",
                      f"风险等级 {risk.get('level')!r} 不在词表", where=where)
        for check in risk.get("checks") or []:
            if check.get("condition") not in schema.RISK_CONDITIONS:
                rep.error("candidate.risk_condition",
                          f"风险条件 {check.get('condition')!r} 不在词表",
                          where=where)
            if check.get("hit") is True and not check.get("source"):
                rep.error("candidate.risk_hit_no_source",
                          "命中记录缺来源（无源不许落命中）", where=where)
            if check.get("hit") is True and \
                    check.get("origin") == "name_list" and \
                    not check.get("list_version") and \
                    not check.get("list_year"):
                rep.error("candidate.risk_hit_no_list_version",
                          "名单命中缺名单版本与年份：名单逐年更新，"
                          "命中必须带名单名 + 版本/年份 + 查询日期"
                          "（JS-08）", where=where)
        if risk.get("level") == "quasi_hard" and cand.get("tier") not in (
                None, "excluded"):
            from .gate import valid_override
            ok, _ = valid_override(risk.get("override"))
            if not ok:
                rep.error("candidate.quasi_hard_tiered",
                          "准硬门命中候选无有效放行记录却被分档（E3）",
                          where=where)
    if cand.get("tier") is not None and \
            cand.get("tier") not in schema.TIERS:
        rep.error("candidate.tier",
                  f"档位 {cand.get('tier')!r} 不在词表", where=where)
    if cand.get("provisional") and cand.get("tier") in ("challenge", "target"):
        rep.error("candidate.provisional_tier",
                  "暂定候选至多落 safety（JS-04）", where=where)


def validate_package(root) -> dict:
    root = Path(root)
    selection = load_selection(root)
    if selection is None:
        rep = Report()
        rep.error("package.missing", "选刊包不存在（selection.yaml 缺失）")
    else:
        rep = validate_selection(selection)
        if selection.get("handoff"):
            _check_handoff_files(root, selection, rep)
    return {"ok": rep.ok,
            "errors": rep.errors,
            "warnings": rep.warnings,
            "issues": rep.issues}


def _check_handoff_files(root: Path, selection: dict, rep: Report) -> None:
    """交接物文件层回验：记录在场、语言一致、manifest 哈希诚实。

    downloaded 条目必须有哈希且与入库文件实测一致；pending
    条目带哈希 = 把没下载说成下载了，直接 error。
    """
    record_path = root / FILES["check_record"]
    manifest_path = root / FILES["manifest"]
    if not record_path.exists():
        rep.error("handoff.record_file_missing",
                  f"交接登记在册但核查记录缺失：{FILES['check_record']}",
                  where="handoff")
    else:
        record = load_structured(record_path)
        journal_language = (record.get("A") or {}).get("journal_language")
        manuscript_language = (selection.get("manuscript") or {}).get(
            "language")
        if journal_language != manuscript_language:
            rep.error("handoff.language_mismatch",
                      f"核查记录语言 {journal_language!r} 与稿件语言 "
                      f"{manuscript_language!r} 不一致（一篇稿一个语言）",
                      where="handoff")
    if not manifest_path.exists():
        rep.error("handoff.manifest_file_missing",
                  f"交接登记在册但下载清单缺失：{FILES['manifest']}",
                  where="handoff")
        return
    manifest = load_structured(manifest_path)
    for entry in manifest.get("entries") or []:
        where = f"manifest.{entry.get('entry_id')}"
        if entry.get("status") == "downloaded":
            if not entry.get("sha256"):
                rep.error("manifest.downloaded_no_hash",
                          "已下载条目缺 SHA-256（下载留痕必须可验）",
                          where=where)
                continue
            stored = root / (entry.get("stored_path") or "")
            if not stored.is_file():
                rep.error("manifest.stored_file_missing",
                          f"已下载条目的入库文件不存在："
                          f"{entry.get('stored_path')}", where=where)
            elif sha256_file(stored) != entry.get("sha256"):
                rep.error("manifest.hash_mismatch",
                          "入库文件实测哈希与 manifest 登记不符"
                          "（文件被换或登记造假）", where=where)
        elif entry.get("status") == "pending_download":
            if entry.get("sha256"):
                rep.error("manifest.pending_with_hash",
                          "待下载条目带 SHA-256：未下载不许冒充已下载",
                          where=where)
        else:
            rep.error("manifest.entry_status",
                      f"下载条目状态 {entry.get('status')!r} 不在词表",
                      where=where)

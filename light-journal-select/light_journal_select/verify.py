"""逐刊核验登记与核验纪律校验（JS-01 / JS-02 / JS-03 / E4）。

工具只登记与校验、不代查：核验值由执行者联网现查后经 verify
命令落盘；校验器执行三条铁律——
1. 指标零记忆（JS-01）：verified 的值必须带「来源 URL + 指标
   年份/版本 + 查询日期」三元组，裸数值（条目不是完整对象、
   或缺任一元）直接报错；
2. 未确认如实（JS-02）：status=unconfirmed 的条目 value 必须为
   None，且须带 source_status 四态说明「为什么未确认」；
3. 众包三标注（E4）：审稿周期 provenance=crowd 时 basis /
   sample_size / queried_at 缺一报错；样本量未知写「未披露」。
来源冲突（JS-03）：条目带 conflicts 时必须有 conflict_resolution
（官方优先的取舍落字），不许静默取一。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .gates import GateError, advance_to, require_selection
from .project import find_candidate, save_selection
from .util import today


def _issue(level, code, message, where=None):
    return {"level": level, "code": code, "message": message, "where": where}


class Report:
    """与 light-write validate.Report 同构的判定收集器。"""

    def __init__(self):
        self.issues = []

    def error(self, code, message, where=None):
        self.issues.append(_issue("error", code, message, where))

    def warning(self, code, message, where=None):
        self.issues.append(_issue("warning", code, message, where))

    @property
    def errors(self):
        return [i for i in self.issues if i["level"] == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i["level"] == "warning"]

    @property
    def ok(self):
        return not self.errors


def check_metric_entry(key, entry, rep: Report, where: str) -> None:
    """单条指标的核验纪律（validate 与 verify 登记共用此口径）。"""
    if not isinstance(entry, dict):
        rep.error("metric.bare_value",
                  f"指标 {key} 是裸数值 {entry!r}：指标零记忆（JS-01），"
                  "每值必须落 {value, source_url, source_year, "
                  "queried_at, status} 完整条目",
                  where=where)
        return
    status = entry.get("status")
    if status not in schema.VERIFICATION_STATUSES:
        rep.error("metric.status",
                  f"指标 {key} status {status!r} 不在 "
                  f"{schema.VERIFICATION_STATUSES}", where=where)
        return
    if status == "verified":
        if entry.get("value") is None:
            rep.error("metric.verified_no_value",
                      f"指标 {key} 标 verified 但 value 为空", where=where)
        for field in ("source_url", "source_year", "queried_at"):
            if entry.get(field) in (None, ""):
                rep.error("metric.missing_provenance",
                          f"指标 {key} 缺三元组字段 {field}"
                          "（JS-01：来源+年份+查询日期缺一不许落 verified）",
                          where=where)
    else:  # unconfirmed
        if entry.get("value") is not None:
            rep.error("metric.unconfirmed_with_value",
                      f"指标 {key} 标 unconfirmed 却带 value"
                      "（未确认不许带数，更不许参与分档，JS-02）",
                      where=where)
        if entry.get("source_status") not in schema.SOURCE_STATUSES:
            rep.error("metric.unconfirmed_no_reason",
                      f"指标 {key} 未确认但缺 source_status 四态说明"
                      "（attempted/partial/skipped，JS-02）",
                      where=where)
    prov = entry.get("provenance")
    if prov is not None and prov not in schema.METRIC_PROVENANCES:
        rep.error("metric.provenance",
                  f"指标 {key} provenance {prov!r} 不在词表", where=where)
    if key == "apc" and status == "verified":
        check_apc_value(entry, rep, where)
    if key == "acceptance_rate" and status == "verified" and \
            prov != "official":
        rep.error("metric.acceptance_rate_source",
                  "录用率 verified 只许期刊官方公布口径"
                  "（provenance=official）：未官方公布一律未确认，"
                  "不许以个案经验/众包/倒推冒充该刊录用率（JS-10）",
                  where=where)
    if key == "indexing" and status == "verified" and \
            prov == "aggregator":
        rep.warning("metric.indexing_not_primary",
                    "收录状态以聚合源落 verified：声称须在源头核验"
                    "（MJL / Scopus Sources / DOAJ 登记页），聚合源"
                    "只作回退与线索（JS-09）", where=where)
    if key == "review_cycle" and entry.get("derived") is True:
        if not entry.get("derivation"):
            rep.error("metric.derived_no_method",
                      "派生审稿周期缺 derivation 方法落字：倒推估计"
                      "必须标注「派生」与方法，且不许与官方统计"
                      "同列同权（JS-10）", where=where)
    if key == "review_cycle" and prov == "crowd":
        ann = entry.get("annotations") or {}
        for field in schema.REVIEW_CYCLE_CROWD_ANNOTATIONS:
            if ann.get(field) in (None, ""):
                rep.error("metric.crowd_annotation",
                          f"众包审稿周期缺三标注字段 {field}"
                          "（E4：众包口径+样本量+查询日期缺一不可；"
                          "样本量未知写「未披露」）",
                          where=where)
    if key == "quartile_jcr" and status == "verified" and \
            entry.get("value") not in schema.JCR_QUARTILES:
        rep.error("metric.jcr_value",
                  f"JCR 分区值 {entry.get('value')!r} 不在 "
                  f"{schema.JCR_QUARTILES}", where=where)
    if key == "quartile_cas" and status == "verified" and \
            entry.get("value") not in schema.CAS_ZONES:
        rep.error("metric.cas_value",
                  f"中科院分区值 {entry.get('value')!r} 不在 "
                  f"{schema.CAS_ZONES}", where=where)
    conflicts = entry.get("conflicts") or []
    if conflicts and not entry.get("conflict_resolution"):
        rep.error("metric.conflict_unresolved",
                  f"指标 {key} 有来源冲突未落取舍（JS-03：官方优先，"
                  "冲突本身与取舍必须落字）", where=where)


def check_apc_value(entry: dict, rep: Report, where: str) -> None:
    """APC 费用组形态（JS-12）：verified 的 value 应为结构化
    费用组对象；旧标量兼容读取但给迁移警告（构建单判断 J2）。"""
    value = entry.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        rep.warning("metric.apc_legacy_scalar",
                    "APC 仍为标量值：v1.1 起应登记为结构化费用组"
                    "（标价/币种/收费时点/附加费/减免/协议覆盖，"
                    "JS-12）；本次按标价兼容读取", where=where)
        return
    if not isinstance(value, dict):
        rep.error("metric.apc_shape",
                  f"APC 值 {value!r} 既非标量也非费用组对象（JS-12）",
                  where=where)
        return
    for field in value:
        if field not in schema.APC_FEE_FIELDS:
            rep.error("metric.apc_unknown_field",
                      f"费用组未知字段 {field!r}（词表见 "
                      "schema.APC_FEE_FIELDS）", where=where)
    price = value.get("list_price")
    if price is not None:
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            rep.error("metric.apc_price",
                      f"费用组 list_price {price!r} 须为数值",
                      where=where)
        elif price > 0 and not value.get("currency"):
            rep.error("metric.apc_currency",
                      "费用组有标价却缺 currency：全成本口径须带"
                      "币种（JS-12）", where=where)
    timing = value.get("charge_timing")
    if timing is not None and timing not in schema.APC_CHARGE_TIMINGS:
        rep.error("metric.apc_timing",
                  f"收费时点 {timing!r} 不在 {schema.APC_CHARGE_TIMINGS}"
                  "（未披露写 None，不许臆造）", where=where)
    extra = value.get("extra_fees")
    if extra is not None:
        if not isinstance(extra, list) or any(
                not isinstance(f, dict) or not f.get("name")
                for f in extra):
            rep.error("metric.apc_extra_fees",
                      "附加费清单须为 [{name, amount, currency}] "
                      "列表，与主费用分开登记（JS-12）", where=where)
    waiver = value.get("waiver_available")
    if waiver is not None and not isinstance(waiver, bool):
        rep.error("metric.apc_waiver",
                  "减免有无 waiver_available 须为布尔或 None（未知）",
                  where=where)
    coverage = value.get("agreement_coverage")
    if coverage is not None and \
            coverage not in schema.APC_AGREEMENT_COVERAGE:
        rep.error("metric.apc_coverage",
                  f"协议覆盖状态 {coverage!r} 不在 "
                  f"{schema.APC_AGREEMENT_COVERAGE}（未知写 unknown，"
                  "不许把标价当实付，JS-12）", where=where)


def check_scope_checks(block, rep: Report, where: str) -> None:
    """scope 核验三项（JS-06）：逐项与指标同口径——verified 须
    带来源 URL 与查询日期；unconfirmed 须带四态说明。"""
    if not isinstance(block, dict):
        rep.error("scope_checks.shape", "scope_checks 须为对象",
                  where=where)
        return
    for item, entry in block.items():
        if item not in schema.SCOPE_CHECK_ITEMS:
            rep.error("scope_checks.unknown_item",
                      f"未知 scope 核验项 {item!r}（三项见 "
                      "schema.SCOPE_CHECK_ITEMS）", where=where)
            continue
        if not isinstance(entry, dict):
            rep.error("scope_checks.bare",
                      f"scope 核验项 {item} 不是完整条目对象",
                      where=where)
            continue
        status = entry.get("status")
        if status not in schema.VERIFICATION_STATUSES:
            rep.error("scope_checks.status",
                      f"scope 核验项 {item} status {status!r} 不在词表",
                      where=where)
            continue
        if status == "verified":
            for field in ("source_url", "queried_at"):
                if entry.get(field) in (None, ""):
                    rep.error("scope_checks.missing_provenance",
                              f"scope 核验项 {item} 标 verified 却缺 "
                              f"{field}（JS-01 三元组口径）", where=where)
        elif entry.get("source_status") not in schema.SOURCE_STATUSES:
            rep.error("scope_checks.unconfirmed_no_reason",
                      f"scope 核验项 {item} 未确认但缺 source_status "
                      "四态说明（JS-02）", where=where)


def check_oa_license_block(block, rep: Report, where: str) -> None:
    """许可组（JS-12）：OA 模型与许可层字段 + 来源三元组。"""
    if not isinstance(block, dict):
        rep.error("oa_license.shape", "oa_license 须为对象", where=where)
        return
    model = block.get("oa_model")
    if model is not None and model not in schema.OA_MODELS:
        rep.error("oa_license.model",
                  f"OA 模型 {model!r} 不在 {schema.OA_MODELS}",
                  where=where)
    lic = block.get("license_type")
    if lic is not None and lic not in schema.LICENSE_TYPES:
        rep.error("oa_license.license_type",
                  f"许可类型 {lic!r} 不在词表（以该刊官网/DOAJ "
                  "登记页核读为准，JS-12）", where=where)
    retained = block.get("author_rights_retained")
    if retained is not None and not isinstance(retained, bool):
        rep.error("oa_license.rights",
                  "作者保留权利 author_rights_retained 须为布尔或 "
                  "None（未知）", where=where)
    for field in ("source_url", "queried_at"):
        if block.get(field) in (None, ""):
            rep.error("oa_license.missing_provenance",
                      f"许可组缺 {field}：许可事实同样带源落字"
                      "（JS-01 口径）", where=where)


def check_policy_checks(items, rep: Report, where: str) -> None:
    """政策逐刊核读条目（JS-13）：topic 词表 + 状态词表 +
    来源与访问日期三元组；not_applicable 须落理由。"""
    if not isinstance(items, list):
        rep.error("policy_checks.shape", "policy_checks 须为条目列表",
                  where=where)
        return
    for item in items:
        if not isinstance(item, dict):
            rep.error("policy_checks.bare", "政策核读条目须为对象",
                      where=where)
            continue
        topic = item.get("topic")
        if topic not in schema.POLICY_TOPICS:
            rep.error("policy_checks.topic",
                      f"政策主题 {topic!r} 不在 {schema.POLICY_TOPICS}",
                      where=where)
        status = item.get("status")
        if status not in schema.POLICY_CHECK_STATUSES:
            rep.error("policy_checks.status",
                      f"政策条目状态 {status!r} 不在 "
                      f"{schema.POLICY_CHECK_STATUSES}", where=where)
            continue
        if status == "not_applicable":
            if not item.get("note"):
                rep.error("policy_checks.na_no_note",
                          f"政策主题 {topic} 标 not_applicable 却无"
                          "理由落字（不适用也要说清为什么）",
                          where=where)
            continue
        for field in ("source_url", "accessed_at"):
            if item.get(field) in (None, ""):
                rep.error("policy_checks.missing_provenance",
                          f"政策条目 {topic} 缺 {field}：政策是活"
                          "文本，核读必须带出处页面与访问日期"
                          "（JS-13）", where=where)
        if not item.get("finding"):
            rep.error("policy_checks.no_finding",
                      f"政策条目 {topic} 缺 finding：与本稿情形"
                      "相关的政策条款须点名带回，不许只落「已查」",
                      where=where)


def check_verification_block(cand: dict, rep: Report) -> None:
    block = cand.get("verification")
    where = f"candidates.{cand.get('candidate_id')}.verification"
    if block is None:
        rep.error("verification.missing",
                  f"候选 {cand.get('name')} 无核验块", where=where)
        return
    if block.get("source_status") not in schema.SOURCE_STATUSES:
        rep.error("verification.source_status",
                  f"候选 {cand.get('name')} 核验块 source_status "
                  f"{block.get('source_status')!r} 不在四态词表（JS-02）",
                  where=where)
    for key, entry in (block.get("metrics") or {}).items():
        if key not in schema.METRIC_KEYS:
            rep.error("metric.unknown_key",
                      f"未知指标键 {key!r}（词表见 schema.METRIC_KEYS）",
                      where=where)
            continue
        check_metric_entry(key, entry, rep, where=f"{where}.metrics.{key}")


def apply_verification(root, records: list, today_str: str | None = None) -> dict:
    """登记逐刊核验结果。records 形态：

    [{candidate: <id 或刊名>, source_status: <四态>,
      metrics: {指标键: 条目},
      scope_checks: {三项核验条目}（可选，JS-06）,
      oa_license: {许可组}（可选，JS-12）,
      policies: [政策核读条目]（可选，JS-13）}]

    纪律不过（Report 有 error）整批拒绝、不落盘。
    """
    root = Path(root)
    selection = require_selection(root)
    if selection.get("status") not in ("candidates_ready", "verified"):
        raise GateError([f"状态 {selection.get('status')} 不许登记核验"
                         "（须先 candidates_ready）"])
    rep = Report()
    staged = []
    for rec in records or []:
        cand = find_candidate(selection, rec.get("candidate") or "")
        if cand is None:
            rep.error("verification.unknown_candidate",
                      f"核验记录指向不存在的候选 {rec.get('candidate')!r}")
            continue
        block = {"checked_at": today_str or today(),
                 "source_status": rec.get("source_status"),
                 "metrics": rec.get("metrics") or {}}
        probe = dict(cand)
        probe["verification"] = block
        check_verification_block(probe, rep)
        extra = {}
        where = f"candidates.{cand.get('candidate_id')}"
        if rec.get("scope_checks") is not None:
            check_scope_checks(rec["scope_checks"], rep,
                               where=f"{where}.scope_checks")
            extra["scope_checks"] = rec["scope_checks"]
        if rec.get("oa_license") is not None:
            check_oa_license_block(rec["oa_license"], rep,
                                   where=f"{where}.oa_license")
            extra["oa_license"] = rec["oa_license"]
        if rec.get("policies") is not None:
            check_policy_checks(rec["policies"], rep,
                                where=f"{where}.policy_checks")
            extra["policy_checks"] = rec["policies"]
        staged.append((cand, block, extra))
    if rep.errors:
        raise GateError([f"{i['code']}: {i['message']}" for i in rep.errors])
    for cand, block, extra in staged:
        cand["verification"] = block
        cand.update(extra)
    save_selection(root, selection)
    advanced = None
    if selection.get("status") == "candidates_ready" and all(
            c.get("verification") is not None
            for c in selection.get("candidates") or []):
        advance_to(root, "verified", by="light-journal-select verify")
        advanced = "verified"
    return {"verified_candidates": [c["name"] for c, _, _ in staged],
            "status": advanced or selection.get("status"),
            "warnings": [i["message"] for i in rep.warnings]}

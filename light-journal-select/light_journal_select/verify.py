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
      metrics: {指标键: 条目}}]

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
        staged.append((cand, block))
    if rep.errors:
        raise GateError([f"{i['code']}: {i['message']}" for i in rep.errors])
    for cand, block in staged:
        cand["verification"] = block
    save_selection(root, selection)
    advanced = None
    if selection.get("status") == "candidates_ready" and all(
            c.get("verification") is not None
            for c in selection.get("candidates") or []):
        advance_to(root, "verified", by="light-journal-select verify")
        advanced = "verified"
    return {"verified_candidates": [c["name"] for c, _ in staged],
            "status": advanced or selection.get("status"),
            "warnings": [i["message"] for i in rep.warnings]}

"""成稿复核子流程（Phase 2）：与 Idea/Design/Analysis 同构的跨模型硬门。

分工：复核只判**边界情形**，不重开已冻结的口径——
  1. 措辞贴合边界：出现在正文且强度档 ≤ suggestive 或 writable_form
     被降格（downgraded / limitations_only）的主张，其稿内表述是否
     与上游判定贴合；
  2. 审计门四的相关性待核条目（门一 relevance_pending）。
复核包自包含：成稿口径宪法 + 审计总判定 + 主张摘要表 + 边界主张全字段
+ 回填 JSON 形态。收据 RV-<sha256[:10]>；同族自审判拒；执行者不许
自判自赦；REVIEW_UNAVAILABLE 显式落字拦 submission_ready（gates 接通）。
收据绑复核包哈希，复核包绑稿件哈希——稿改后旧收据 STALE，须重备包重审。
"""

from __future__ import annotations

import json
from pathlib import Path

from .audit import load_audit_report
from .project import (
    load_package, manuscript_hash, save_manuscript, section_files,
)
from .util import component_hash, sha256_file, today
from .validate import CLAIM_MARK_RE

CONSTITUTION = """## 成稿口径宪法（复核者须知，判据不重开）

- 引用只许来自 Light-Literature verified 集快照（references.lock）；
  数字只许来自 Analysis 溯源表；正文措辞强度永不超过 Analysis 强度档。
- writable_form 与 wording_ceiling 由上游状态 × 强度档规则表机械导出，
  不许临场升格；untested 主张只许 limitations_only / omit。
- 审计四门（引用两段核对 / 数字对账 / 强度措辞 / 落点映射）的判定
  形态与容差层已冻结，复核不重开门规则本身，只判边界情形的落字属实性。
- 引用语境处置 REPLACE / REMOVE 永须人类批准；相关性存疑只标记不定制。
- 验收合同 contested 的稿件不许 submission_ready，复核不得推翻。
- 复核结论形态：逐边界主张 agree / disagree + 一句理由；有 disagree 的
  回填不被接受——须先改稿或改登记后重新备包复核。
"""

_PACKET_NAME = "review_packet.md"


class ReviewError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def boundary_claims(pkg) -> list:
    """挑边界主张：正文在场且（低档 或 被降格 或 相关性待核牵连）。"""
    files = section_files(pkg["root"])
    in_text = set()
    for text in files.values():
        in_text.update(CLAIM_MARK_RE.findall(text))
    report = load_audit_report(pkg["root"])
    relevance_pending = set()
    if report:
        for g in report.get("gates") or []:
            if g.get("gate") == "citations":
                relevance_pending = set(
                    (g.get("details") or {}).get("relevance_pending") or [])
    picked = []
    for row in (pkg["claims"] or {}).get("claims") or []:
        cid = row.get("claim_id")
        reasons = []
        if cid in in_text and row.get("strength_grade") in (
                "suggestive", "insufficient"):
            reasons.append("低强度档主张在正文在场：措辞贴合待核")
        if cid in in_text and row.get("writable_form") in (
                "downgraded", "limitations_only"):
            reasons.append("被降格形态主张在正文在场：降格落字待核")
        if reasons:
            picked.append({"claim_id": cid, "reasons": reasons, "row": row})
    return picked, sorted(relevance_pending)


def prepare_review(root) -> dict:
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise ReviewError(["稿件包不存在（先 init）"])
    picked, relevance_pending = boundary_claims(pkg)
    report = load_audit_report(root)
    out = [f"# 成稿复核包 — {manuscript.get('manuscript_id')}", "",
           f"- 生成日期：{today()}",
           f"- 稿件语言：{manuscript.get('language')}",
           f"- 稿件哈希：`{manuscript_hash(root)}`",
           f"- 审计总判定：{report.get('overall') if report else '未审计'}",
           f"- 执行者：{(manuscript.get('executor') or {}).get('name')}"
           f"（家族 {(manuscript.get('executor') or {}).get('family')}）",
           "", CONSTITUTION, "", "## 主张摘要", "",
           "| 主张 | 上游状态 | 强度档 | 可写形态 | 措辞上限 |",
           "|---|---|---|---|---|"]
    for row in (pkg["claims"] or {}).get("claims") or []:
        out.append(
            f"| {row.get('claim_id')} | {row.get('upstream_status')} | "
            f"{row.get('strength_grade')} | {row.get('writable_form')} | "
            f"{(row.get('wording_ceiling') or {}).get('ceiling_label')} |")
    out += ["", f"## 边界主张（共 {len(picked)} 条，逐条全字段）", ""]
    for item in picked:
        out.append(f"### {item['claim_id']}")
        out.append("")
        out.append("入选理由：" + "；".join(item["reasons"]))
        out.append("")
        out.append("```json")
        out.append(json.dumps(item["row"], ensure_ascii=False, indent=2))
        out.append("```")
        out.append("")
    if relevance_pending:
        out += ["## 相关性待核条目（门一标记，复核时一并看）", "",
                ", ".join(relevance_pending), ""]
    out += ["## 回填形态（review import --from-json 的 JSON schema）", "",
            "```json",
            json.dumps({
                "reviewer": "<复核者名>",
                "family": "<模型家族，须与执行者不同族>",
                "decisions": [{"claim_id": "<边界主张 id>",
                               "agree": True,
                               "comment": "<一句理由>"}],
                "notes": "<可选总评>",
            }, ensure_ascii=False, indent=2),
            "```", ""]
    packet_path = root / _PACKET_NAME
    packet_path.write_text("\n".join(out), encoding="utf-8")
    info = {"packet": _PACKET_NAME,
            "packet_hash": sha256_file(packet_path),
            "manuscript_hash": manuscript_hash(root),
            "prepared_at": today(),
            "scope_claim_ids": [i["claim_id"] for i in picked]}
    manuscript["review_packet"] = info
    save_manuscript(root, manuscript)
    return info


def _check_reviewer(manuscript, reviewer, family):
    executor = manuscript.get("executor") or {}
    if executor.get("family") and family and family == executor["family"]:
        raise ReviewError([
            f"同族复核被拒：复核家族 {family} 与稿件执行者同族"
            "（跨模型硬门：复核者须异家族）"])
    if executor.get("name") and reviewer and reviewer == executor["name"]:
        raise ReviewError(["复核者与稿件执行者为同一人：写者不许自判自赦"])


def _receipt(payload) -> str:
    return "RV-" + component_hash(payload)[:10]


def record_review(root, reviewer, family, outcome="agree", notes=None) -> dict:
    """落复核收据（直接记录一场已完成的异家族复核）。"""
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise ReviewError(["稿件包不存在（先 init）"])
    packet = manuscript.get("review_packet")
    if not packet:
        raise ReviewError(["复核包未生成：先 review prepare"])
    if packet.get("manuscript_hash") != manuscript_hash(root):
        raise ReviewError(["稿件已在备包后变动：复核包 STALE，须重新 prepare"])
    if not reviewer or not family:
        raise ReviewError(["record 须给 --reviewer 与 --family"
                           "（复核者身份与家族是收据的一部分）"])
    _check_reviewer(manuscript, reviewer, family)
    if outcome not in ("agree", "agree_with_notes"):
        raise ReviewError([
            f"复核结论 {outcome!r} 不落收据：有异议须先改稿/改登记后"
            "重新复核，不许带异议放行"])
    receipt = _receipt({"packet_hash": packet.get("packet_hash"),
                        "reviewer": reviewer, "family": family,
                        "outcome": outcome,
                        "scope": packet.get("scope_claim_ids")})
    review = {"reviewer": reviewer, "family": family,
              "review_status": "approved", "receipt_id": receipt,
              "outcome": outcome, "notes": notes,
              "scope_claim_ids": packet.get("scope_claim_ids"),
              "packet_hash": packet.get("packet_hash"),
              "manuscript_hash": packet.get("manuscript_hash"),
              "recorded_at": today(), "via": "record"}
    manuscript["review"] = review
    save_manuscript(root, manuscript)
    return review


def record_unavailable(root, reason=None) -> dict:
    """REVIEW_UNAVAILABLE 显式通道：落字拦 submission_ready，不许假装审过。"""
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise ReviewError(["稿件包不存在（先 init）"])
    review = {"reviewer": None, "family": None,
              "review_status": "REVIEW_UNAVAILABLE", "receipt_id": None,
              "reason": reason or "本环境无异家族复核者可用",
              "recorded_at": today(), "via": "unavailable"}
    manuscript["review"] = review
    save_manuscript(root, manuscript)
    return review


_IMPORT_KEYS = {"reviewer", "family", "decisions", "notes"}
_DECISION_KEYS = {"claim_id", "agree", "comment"}


def import_review(root, json_path) -> dict:
    """外部判定回填：校验 schema 后落收据（收据哈希锚定回填文件本身）。"""
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise ReviewError(["稿件包不存在（先 init）"])
    packet = manuscript.get("review_packet")
    if not packet:
        raise ReviewError(["复核包未生成：先 review prepare"])
    if packet.get("manuscript_hash") != manuscript_hash(root):
        raise ReviewError(["稿件已在备包后变动：复核包 STALE，须重新 prepare"])
    json_path = Path(json_path)
    if not json_path.exists():
        raise ReviewError([f"回填文件不存在：{json_path}"])
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ReviewError([f"回填文件不是合法 JSON：{e}"])
    gaps = []
    bad = set(data) - _IMPORT_KEYS
    if bad:
        gaps.append(f"回填含未知字段 {sorted(bad)}（schema 外字段拒收）")
    if not data.get("reviewer") or not data.get("family"):
        gaps.append("回填缺 reviewer / family（复核者身份必填）")
    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        gaps.append("回填 decisions 须为列表（逐边界主张给 agree 与理由）")
        decisions = []
    scope = set(packet.get("scope_claim_ids") or [])
    seen = set()
    for d in decisions:
        if not isinstance(d, dict) or set(d) - _DECISION_KEYS:
            gaps.append(f"decision 形态不合 schema：{d!r}")
            continue
        cid = d.get("claim_id")
        if scope and cid not in scope:
            gaps.append(f"decision 引用复核范围外主张 {cid}")
        if not isinstance(d.get("agree"), bool):
            gaps.append(f"decision {cid} 的 agree 须为布尔值")
        if cid in seen:
            gaps.append(f"decision 对主张 {cid} 重复")
        seen.add(cid)
    missing = scope - seen
    if missing:
        gaps.append(f"边界主张未逐条回填：缺 {sorted(missing)}")
    if gaps:
        raise ReviewError(gaps)
    _check_reviewer(manuscript, data["reviewer"], data["family"])
    disagreed = [d["claim_id"] for d in decisions if not d["agree"]]
    if disagreed:
        raise ReviewError([
            f"复核对 {disagreed} 有异议（disagree）：回填不被接受，"
            "须先按异议改稿/改登记后重新 prepare + 复核"])
    receipt = _receipt({"file_hash": sha256_file(json_path),
                        "reviewer": data["reviewer"],
                        "family": data["family"]})
    review = {"reviewer": data["reviewer"], "family": data["family"],
              "review_status": "approved", "receipt_id": receipt,
              "outcome": "agree", "notes": data.get("notes"),
              "scope_claim_ids": sorted(seen),
              "packet_hash": packet.get("packet_hash"),
              "manuscript_hash": packet.get("manuscript_hash"),
              "recorded_at": today(), "via": "import",
              "source_file": str(json_path)}
    manuscript["review"] = review
    save_manuscript(root, manuscript)
    return review

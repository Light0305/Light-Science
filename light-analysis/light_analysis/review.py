"""判定复核子流程（Phase 2，拍板③：与 Idea/Design 同构、分工收窄）。

异家族复核只判三类边界情形与强度合成，不重开冻结判据本身：
  1. judge 落 undetermined 的行（材料/门缺口是否属实）；
  2. 四象限边缘行（significant_but_equivalent：「存在但 <SESOI」落字）；
  3. 强度合成有争议行（方向份额 <1 或档位 ≤ suggestive 的方向性行）。
复核包自包含：口径宪法 + 全部判定摘要 + 边界行全字段 + 回填 JSON 形态。
收据 RV-<sha256[:10]>；同族自审判拒；REVIEW_UNAVAILABLE 显式落字
拦 delivered（gates 已接通）；执行者永不代判。
"""

from __future__ import annotations

import json
from pathlib import Path

from .project import current_verdicts, load_package, save_analysis
from .util import component_hash, sha256_file, today

CONSTITUTION = """## 判定口径宪法（复核者须知，判据不重开）

- 判定口径只认 Design 冻结登记行：方向、γ=登记值、SESOI 登记快照值；
  分析期新立的标准一律无效。
- positive 双门：规格集联合推断（中位效应同向 + 方向份额 ≥0.5 +
  Stouffer 合并 p 达族 α）与 Type S/M 校准（D 只许冻结 SESOI，
  Type M ≤ 登记阈值）缺一不可。
- null 只许由 TOST 挣来（bounds = 登记 SESOI，90% CI 全落界内）；
  「不显著」不等于 null；判不了落 undetermined 是一等终态。
- 作废 run 支撑行与 fundamental 失败行只许 untested（未检验 ≠ 不成立）。
- 强度 4 档由合成式机械给出（证据上限 × 稳健档 × Type S/M），
  复核只判合成是否合式、边界落字是否属实，不改判据、不改档位定义。
- 复核结论形态：逐边界行 agree / disagree + 一句理由；有 disagree 的
  回填不被接受——须先改判（supersedes 新行）后重新复核。
"""

_PACKET_NAME = "review_packet.md"


class ReviewError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def boundary_lines(pkg) -> list:
    """挑边界情形行：undetermined（judge 落的）/ 象限边缘 / 强度有争议。"""
    rows = current_verdicts(pkg["verdicts"] or [])
    picked = []
    for lid, row in rows.items():
        reasons = []
        if row.get("verdict") == "undetermined" \
                and row.get("decided_by") != "intake-audit":
            reasons.append("judge 落 undetermined：门缺口属实性待核")
        if row.get("quadrant") == "significant_but_equivalent":
            reasons.append("四象限边缘：存在但幅度 <SESOI 的落字待核")
        if row.get("verdict") in ("positive", "negative", "null") and (
                (row.get("joint") or {}).get("direction_share", 1.0) < 1.0
                or row.get("strength_grade") in ("suggestive", "insufficient")):
            reasons.append("强度合成有争议：规格方向份额未全票或档位偏低")
        if reasons:
            picked.append({"registry_line_id": lid, "reasons": reasons,
                           "row": row})
    return picked


def prepare_review(root) -> dict:
    """生成自包含复核包 review_packet.md，并把包指针登记进 analysis。"""
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise ReviewError(["分析包不存在（先 init）"])
    if not pkg["verdicts"]:
        raise ReviewError(["尚无判定行：先 judge 再备复核包"])
    picked = boundary_lines(pkg)
    current = current_verdicts(pkg["verdicts"] or [])
    params = ((analysis.get("spec") or {}).get("judge_params") or {})

    out = [f"# 判定复核包 — {analysis.get('analysis_id')}", "",
           f"- 生成日期：{today()}",
           f"- 执行包：{(analysis.get('execution_ref') or {}).get('execution_id')}",
           f"- Design content_hash：`{(analysis.get('design_ref') or {}).get('content_hash')}`",
           f"- 判定参数：γ={params.get('gamma')}、Type M 阈值={params.get('type_m_max')}",
           f"- 分析执行者：{(analysis.get('analyst') or {}).get('name')}"
           f"（家族 {(analysis.get('analyst') or {}).get('family')}）",
           "", CONSTITUTION, "", "## 全部判定摘要", "",
           "| 登记行 | 判定 | 象限 | 强度 | 方向份额 | Type M |",
           "|---|---|---|---|---|---|"]
    for lid in (analysis.get("registry_snapshot") or {}).get("line_ids") or []:
        row = current.get(lid)
        if row is None:
            continue
        out.append(
            f"| {lid} | {row.get('verdict')} | {row.get('quadrant') or ''} | "
            f"{row.get('strength_grade') or ''} | "
            f"{(row.get('joint') or {}).get('direction_share', '')} | "
            f"{(row.get('type_sm') or {}).get('type_m', '')} |")
    out += ["", f"## 边界情形行（共 {len(picked)} 行，逐行全字段）", ""]
    for item in picked:
        out.append(f"### {item['registry_line_id']}")
        out.append("")
        out.append("入选理由：" + "；".join(item["reasons"]))
        out.append("")
        out.append("```json")
        out.append(json.dumps(item["row"], ensure_ascii=False, indent=2))
        out.append("```")
        out.append("")
    out += ["## 回填形态（review import --from-json 的 JSON schema）", "",
            "```json",
            json.dumps({
                "reviewer": "<复核者名>",
                "family": "<模型家族，须与分析执行者不同族>",
                "decisions": [{"registry_line_id": "<边界行 id>",
                               "agree": True,
                               "comment": "<一句理由>"}],
                "notes": "<可选总评>",
            }, ensure_ascii=False, indent=2),
            "```", ""]
    packet_path = root / _PACKET_NAME
    packet_path.write_text("\n".join(out), encoding="utf-8")
    info = {"packet": _PACKET_NAME,
            "packet_hash": sha256_file(packet_path),
            "prepared_at": today(),
            "scope_line_ids": [i["registry_line_id"] for i in picked]}
    analysis["review_packet"] = info
    save_analysis(root, analysis)
    return info


def _check_reviewer(analysis, reviewer, family):
    analyst = analysis.get("analyst") or {}
    if analyst.get("family") and family and family == analyst["family"]:
        raise ReviewError([
            f"同族复核被拒：复核家族 {family} 与分析执行者同族"
            "（跨模型硬门：复核者须异家族）"])
    if analyst.get("name") and reviewer and reviewer == analyst["name"]:
        raise ReviewError(["复核者与分析执行者为同一人：写者不许自判自赦"])


def _receipt(payload) -> str:
    return "RV-" + component_hash(payload)[:10]


def record_review(root, reviewer, family, outcome="agree", notes=None) -> dict:
    """落复核收据（直接记录一场已完成的异家族复核）。"""
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise ReviewError(["分析包不存在（先 init）"])
    packet = analysis.get("review_packet")
    if not packet:
        raise ReviewError(["复核包未生成：先 review prepare"])
    if not reviewer or not family:
        raise ReviewError(["record 须给 --reviewer 与 --family"
                           "（复核者身份与家族是收据的一部分）"])
    _check_reviewer(analysis, reviewer, family)
    if outcome not in ("agree", "agree_with_notes"):
        raise ReviewError([
            f"复核结论 {outcome!r} 不落收据：有异议须先改判（supersedes）"
            "后重新复核，不许带异议放行"])
    receipt = _receipt({"packet_hash": packet.get("packet_hash"),
                        "reviewer": reviewer, "family": family,
                        "outcome": outcome,
                        "scope": packet.get("scope_line_ids")})
    review = {"reviewer": reviewer, "family": family,
              "review_status": "approved", "receipt_id": receipt,
              "outcome": outcome, "notes": notes,
              "scope_line_ids": packet.get("scope_line_ids"),
              "recorded_at": today(), "via": "record"}
    analysis["review"] = review
    save_analysis(root, analysis)
    return review


def record_unavailable(root, reason=None) -> dict:
    """REVIEW_UNAVAILABLE 显式通道：落字拦 delivered，不许假装复核过。"""
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise ReviewError(["分析包不存在（先 init）"])
    review = {"reviewer": None, "family": None,
              "review_status": "REVIEW_UNAVAILABLE", "receipt_id": None,
              "reason": reason or "本环境无异家族复核者可用",
              "recorded_at": today(), "via": "unavailable"}
    analysis["review"] = review
    save_analysis(root, analysis)
    return review


_IMPORT_KEYS = {"reviewer", "family", "decisions", "notes"}
_DECISION_KEYS = {"registry_line_id", "agree", "comment"}


def import_review(root, json_path) -> dict:
    """外部判定回填：校验 schema 后落收据（收据哈希锚定回填文件本身）。"""
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise ReviewError(["分析包不存在（先 init）"])
    packet = analysis.get("review_packet")
    if not packet:
        raise ReviewError(["复核包未生成：先 review prepare"])
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
    if not isinstance(decisions, list) or not decisions:
        gaps.append("回填 decisions 为空：须逐边界行给 agree 与理由")
        decisions = []
    scope = set(packet.get("scope_line_ids") or [])
    seen = set()
    for d in decisions:
        if not isinstance(d, dict) or set(d) - _DECISION_KEYS:
            gaps.append(f"decision 形态不合 schema：{d!r}")
            continue
        lid = d.get("registry_line_id")
        if scope and lid not in scope:
            gaps.append(f"decision 引用复核范围外登记行 {lid}")
        if not isinstance(d.get("agree"), bool):
            gaps.append(f"decision {lid} 的 agree 须为布尔值")
        if lid in seen:
            gaps.append(f"decision 对登记行 {lid} 重复")
        seen.add(lid)
    missing = scope - seen
    if missing:
        gaps.append(f"边界行未逐行回填：缺 {sorted(missing)}")
    if gaps:
        raise ReviewError(gaps)
    _check_reviewer(analysis, data["reviewer"], data["family"])
    disagreed = [d["registry_line_id"] for d in decisions if not d["agree"]]
    if disagreed:
        raise ReviewError([
            f"复核对 {disagreed} 有异议（disagree）：回填不被接受，"
            "须先按异议改判（verdicts supersedes 新行）后重新 prepare + 复核"])
    receipt = _receipt({"file_hash": sha256_file(json_path),
                        "reviewer": data["reviewer"],
                        "family": data["family"]})
    review = {"reviewer": data["reviewer"], "family": data["family"],
              "review_status": "approved", "receipt_id": receipt,
              "outcome": "agree", "notes": data.get("notes"),
              "scope_line_ids": sorted(seen),
              "recorded_at": today(), "via": "import",
              "source_file": str(json_path)}
    analysis["review"] = review
    save_analysis(root, analysis)
    return review

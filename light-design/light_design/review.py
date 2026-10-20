"""定版评审子流程（D6 补完，二期）。

一期 frozen 门只验 freeze.review 的结构与异家族，评审记录靠手写 yaml。
二期把评审做成正式子流程（与 light-idea 查新复核包同构）：

  review prepare  生成自包含评审包 review/<design_id>/：
                  - review_packet.md   设计书全文渲染 + Stage 1 五条评审
                    标准 + 结果可见性声明 + 评审者须知（异家族要求、
                    自评不作数）+ 外部判定 JSON 回填格式说明；
                  - review_checklist.yaml 五条逐项结构（评审者填写用）。
  review record   落盘评审记录 → freeze.review + review_record.json：
                  - 同家族（或同模型）评审直接拒收（约束 13：自评不作数）；
                  - 五条缺项 / 无注 / 决议与逐项矛盾，逐条点名拒绝；
                  - --review-unavailable 显式降级通道（拍板 ①）：落盘
                    review_status=REVIEW_UNAVAILABLE，frozen 门硬拦，
                    只许停、不许定版，恢复后补评审。

评审包自包含：把 review_packet.md 全文交给另一个模型家族的模型（或
人工专家）即可独立评审，不需要访问本项目；判定回来后按包内「回填」
一节的 JSON 格式落盘即可。

增量评审（v1.1 DES-D02）：冻结后命门 amendment 的评审走本模块的
--amendment 子流程，产物落在 review/<design_id>/amendments/amd-<n>/：
只审变更项及其影响面（字段依赖映射见 schema.FIELD_DEPENDENCY_MAP），
不重开全量定版评审。分流两轨（C-补04）：category=prewritten_branch
（定版预写偏离分支）走轻评审——只核触发条件成立与按预写执行两项；
category=unforeseen（未预见变更）走全评审——只核依赖映射圈定的
Stage 1 条目子集。评审落盘前 amendment 保持 pending_review，
export 被拦（export.py）；REVIEW_UNAVAILABLE 显式落字可解除待审，
但导出件须注明未完成。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .project import render_design_md
from .schema import (
    REVIEW_DECISIONS,
    STAGE1_ITEMS,
    VISIBILITY_LEVELS,
    _nonempty_str,
    amendment_impact_areas,
)
from .util import read_yaml, write_yaml

REVIEW_DIRNAME = "review"

# Stage 1 五条评审标准（Chambers 2013 / Nosek 转述，LEARNING §7）：
# 每条 = (标题, 判定标准说明)；packet 与 checklist 共用此表。
STAGE1_CRITERIA: dict[str, tuple[str, str]] = {
    "question_quality": (
        "问题/假设的质量与重要性",
        "研究问题是否明确、重要且可证伪；主张 ≤2 条且每条都说清了"
        "「什么证据能让强审稿人信服」（minimum_convincing_evidence）。",
    ),
    "theoretical_basis": (
        "假设的逻辑与理论依据",
        "假设是否有逻辑/机制依据（不是「试试看」）；anti_claims 是否登记了"
        "要排除的竞争解释，且排除路径在设计内真实存在。",
    ),
    "methodological_soundness": (
        "方法学健全可行且能回答问题（含功效）",
        "变量三组齐全、取值全枚举、重复层级声明与 n 的口径一致；"
        "功效核算（SESOI + 敏感性范围 + 推导）给得起所声称的结论，"
        "给不起时声称是否已下调为探索性。",
    ),
    "analysis_predetermined": (
        "分析在见数据前已确定到可对账",
        "判读三向（positive/negative/null 的 meaning + action）在见结果前"
        "写死；主指标唯一点名且带惯例出处；调参对等条款已声明；"
        "登记头的结果可见性声明与实际进度相符。",
    ),
    "competing_explanations": (
        "设计能区分竞争性解释（强推断）",
        "status_quo 一等对照在场且处理组对照先行（depends_on）；消融矩阵"
        "逐条写明 what_it_tests 与 expected_if_component_matters；"
        "效度四分法逐类三态登记、无整类缺失。",
    ),
}

_VISIBILITY_GLOSS = {
    "no_runs_yet": "尚无任何运行",
    "pilot_run_unseen": "判别实验已跑但结果未看",
    "pilot_seen": "判别实验结果已看、主实验未跑",
    "main_partial_seen": "主实验部分结果已看",
    "results_seen": "结果已看过 — 只许探索性，不许确认性定版",
}


class ReviewError(Exception):
    """评审子流程失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def review_dir(root: Path, design_id: str) -> Path:
    return root / REVIEW_DIRNAME / design_id


def make_review_id(design_id: str, date: str, reviewer_model: str | None,
                   decision: str | None) -> str:
    """评审收据 id：RV-<sha256(design_id|日期|评审模型|决议)[:10]>
    （与 light-idea 的 verdict_id 口径同构）。"""
    raw = f"{design_id}|{date}|{reviewer_model or 'REVIEW_UNAVAILABLE'}|{decision or ''}"
    return "RV-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


# ---------- prepare ----------

def prepare_review(root: Path, design: dict, *, date: str) -> dict:
    """生成自包含评审包。返回 {dir, packet, checklist} 路径 dict。
    已 frozen 的设计不许再 prepare（评审对象是冻结前版本）。"""
    if design.get("status") == "frozen":
        raise ReviewError(["设计已 frozen：定版评审须在冻结前完成；"
                           "冻结后修订走 amendment + 增量评审，不重开全量评审包"])
    d = review_dir(root, design["design_id"])
    d.mkdir(parents=True, exist_ok=True)
    reg = design.get("registration") or {}
    designer = reg.get("designer") or {}

    checklist = {
        "design_id": design["design_id"],
        "title": design.get("title"),
        "prepared": date,
        "designer": {"model": designer.get("model"),
                     "family": designer.get("family")},
        "visibility": reg.get("visibility"),
        "reviewer": {"model": None, "family": None},
        "decision": None,
        "items": {
            it: {"criterion": STAGE1_CRITERIA[it][0], "verdict": None, "note": ""}
            for it in STAGE1_ITEMS
        },
        "instructions": (
            "逐项填 verdict（pass/fail）与 note（判定依据，必填）；"
            "decision 填 pass/reject；reviewer 填判定模型与家族，"
            "family 必须与 designer.family 不同，同族自审会被拒收。"),
    }
    checklist_path = d / "review_checklist.yaml"
    write_yaml(checklist_path, checklist)

    packet_path = d / "review_packet.md"
    packet_path.write_text(_render_packet(design, date), encoding="utf-8")
    return {"dir": d, "packet": packet_path, "checklist": checklist_path}


def _render_packet(design: dict, date: str) -> str:
    reg = design.get("registration") or {}
    designer = reg.get("designer") or {}
    vis = reg.get("visibility")
    L: list[str] = []
    L.append(f"# 定版评审包 — {design.get('title')}")
    L.append("")
    L.append(f"> 用途：light-design 设计书 `{design['design_id']}`"
             f"（承接 idea `{design.get('idea_id')}`）的定版（frozen）评审。")
    L.append("> 本包自包含：把全文交给**另一个模型家族**的模型（或人工专家）"
             "即可独立评审，不需要访问本项目。评审回来后按文末「回填」"
             "一节落盘。")
    L.append(f"> 生成日期：{date}｜设计级别：{design.get('tier')}"
             f"｜当前状态：{design.get('status')}")
    L.append("")
    L.append("## 评审者须知（逐条执行）")
    L.append("")
    L.append(f"1. **异家族要求**：本设计书的设计生成者是 "
             f"`{designer.get('model')}`（家族 `{designer.get('family')}`）。"
             "评审者的模型家族**必须与此不同**，否则记录会被校验器拒收"
             "（同族自审不作定版依据）。")
    L.append("2. **自评不作数**：评审者不得是设计生成者本人/同家族模型；"
             "评审记录会落盘评审者身份与家族，供冻结门核验。")
    L.append("3. **逐项判定**：按下面 Stage 1 五条逐项给 verdict"
             "（pass / fail）并写 note（依据，具体到设计书的哪个字段/哪条"
             "运行）；不许只给整体印象。五条缺一不可。")
    L.append("4. **决议**：decision ∈ pass / reject。五条有任一 fail 时"
             "decision 不许 pass（落盘时会因决议与逐项矛盾被拒）。")
    L.append("5. **只审设计、不改设计**：评审者不许替设计者补字段；"
             "发现缺口写进 note，决议 reject，由设计者回 draft 修订。")
    L.append("")
    L.append("## Stage 1 五条评审标准")
    L.append("")
    for i, it in enumerate(STAGE1_ITEMS, 1):
        title, criterion = STAGE1_CRITERIA[it]
        L.append(f"{i}. **{it}（{title}）**：{criterion}")
    L.append("")
    L.append("## 结果可见性声明（登记头，评审须核对与实际进度相符）")
    L.append("")
    L.append(f"- 声明档位：**{vis}**（{_VISIBILITY_GLOSS.get(vis or '', '未声明')}）")
    L.append("- 五档含义：" + "；".join(
        f"{k} = {v}" for k, v in _VISIBILITY_GLOSS.items()))
    assets = reg.get("existing_assets") or []
    L.append(f"- 定版时已有资产：{assets if assets else '（无）'}")
    L.append(f"- 软件环境：{reg.get('software_env') or '（未登记）'}")
    if vis == VISIBILITY_LEVELS[-1]:
        L.append("- ⚠️ 第 5 档（results_seen）：本设计只许探索性声称，"
                 "评审须确认无确认性主张残留。")
    L.append("")
    L.append("## 设计书全文（被评审对象）")
    L.append("")
    L.append(render_design_md(design))
    L.append("")
    L.append("## 回填（评审完成后）")
    L.append("")
    L.append("把判定整理成 JSON（字段名写死，落盘时逐项校验）：")
    L.append("")
    L.append("```json")
    L.append(json.dumps({
        "reviewer_model": "<判定模型名>",
        "reviewer_family": "<判定模型家族，须与设计者家族不同>",
        "decision": "pass",
        "items": {
            it: {"verdict": "pass", "note": "<逐项依据>"}
            for it in STAGE1_ITEMS
        },
    }, ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("落盘命令（二选一）：")
    L.append("")
    L.append("```bash")
    L.append(f"light-design review record <project> {design['design_id']} "
             "--from-json verdict.json")
    L.append(f"# 或：填写 review/{design['design_id']}/review_checklist.yaml 后")
    L.append(f"light-design review record <project> {design['design_id']} "
             "--reviewer-model <模型> --reviewer-family <家族> --decision pass")
    L.append("```")
    L.append("")
    L.append("落盘后设计者依次执行 `advance --to reviewed`、"
             "`advance --to frozen` 完成定版；若跨模型评审不可得，"
             "用 `review record --review-unavailable` 显式落降级记录"
             "（冻结门会硬拦，恢复后补评审，不许伪造收据）。")
    L.append("")
    return "\n".join(L)


# ---------- record ----------

def _designer_family(design: dict) -> tuple[str | None, str | None]:
    designer = (design.get("registration") or {}).get("designer") or {}
    m, f = designer.get("model"), designer.get("family")
    return (str(m) if _nonempty_str(m) else None,
            str(f) if _nonempty_str(f) else None)


def _same_family(design: dict, reviewer_model: str,
                 reviewer_family: str) -> str | None:
    """同族/同模型自审判定：命中返回人读原因，否则 None。"""
    dmodel, dfamily = _designer_family(design)
    if dfamily and reviewer_family.strip().lower() == dfamily.strip().lower():
        return (f"评审者与设计者同模型家族（{reviewer_family}）："
                "同族自审不作定版依据（约束 13），须异家族复核后落盘")
    if dmodel and reviewer_model.strip() == dmodel.strip():
        return (f"评审者与设计生成者是同一模型（{reviewer_model}）："
                "自评不作定版依据，须换异家族模型评审")
    return None


def normalize_items(raw) -> tuple[dict, list[str]]:
    """把外部判定里的 items 规范成 {item: {status, note}}。
    接受 {item: {verdict|status, note}} 或 {item: "pass"} 两种写法。"""
    errs: list[str] = []
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out, ["items 缺失或不是映射（Stage 1 五条须逐项判定）"]
    for it in STAGE1_ITEMS:
        v = raw.get(it)
        if v is None:
            errs.append(f"评审五条缺项：{it} 未判定（五条逐项必填，缺一不可）")
            continue
        if isinstance(v, str):
            verdict, note = v, ""
        elif isinstance(v, dict):
            verdict = v.get("verdict", v.get("status"))
            note = v.get("note") or ""
        else:
            errs.append(f"items.{it} 形态非法：{type(v).__name__}")
            continue
        if verdict not in ("pass", "fail"):
            errs.append(f"items.{it}.verdict 非法：{verdict!r}（须为 pass/fail）")
            continue
        if not _nonempty_str(note):
            errs.append(f"items.{it}.note 为空（逐项判定须写依据，"
                        "不许只给结论）")
            continue
        out[it] = {"status": verdict, "note": str(note)}
    return out, errs


def record_review(root: Path, design: dict, data: dict, *, date: str,
                  source: str = "json") -> dict:
    """落盘一份评审记录：写入 design.freeze.review 并存根
    review/<design_id>/review_record.json。成功返回记录 dict；
    失败抛 ReviewError（逐条点名）。design 的保存由调用方负责。"""
    if design.get("status") == "frozen":
        raise ReviewError(["设计已 frozen：评审记录不许事后改写；"
                           "冻结后修订走 amendment 通道"])
    reviewer_model = str(data.get("reviewer_model") or "").strip()
    reviewer_family = str(data.get("reviewer_family") or "").strip()
    decision = data.get("decision")
    errs: list[str] = []
    if not reviewer_model:
        errs.append("reviewer_model 为空（评审者身份必须落盘）")
    if not reviewer_family:
        errs.append("reviewer_family 为空（异家族核验须有家族登记）")
    if reviewer_model and reviewer_family:
        same = _same_family(design, reviewer_model, reviewer_family)
        if same:
            errs.append(same)
    items, item_errs = normalize_items(data.get("items"))
    errs.extend(item_errs)
    if decision not in REVIEW_DECISIONS:
        errs.append(f"decision 非法：{decision!r}（须为 {REVIEW_DECISIONS} 之一）")
    elif decision == "pass" and items and \
            any(v["status"] != "pass" for v in items.values()):
        failed = [k for k, v in items.items() if v["status"] != "pass"]
        errs.append(f"决议与逐项矛盾：decision=pass 但 {failed} 未 pass"
                    "（决议须与逐项判定一致，不许「差不多」式放行）")
    if errs:
        raise ReviewError(errs)

    record = {
        "reviewer": reviewer_model,
        "family": reviewer_family,
        "date": date,
        "items": items,
        "decision": decision,
        "review_status": "ok",
        "review_id": make_review_id(design["design_id"], date,
                                    reviewer_model, decision),
        "source": source,
    }
    design.setdefault("freeze", {})["review"] = record
    _write_record_stub(root, design["design_id"], record)
    return record


def record_review_unavailable(root: Path, design: dict, *, date: str,
                              note: str = "") -> dict:
    """显式降级通道（拍板 ①）：跨模型评审不可得时落盘
    review_status=REVIEW_UNAVAILABLE。frozen 门会据此硬拦——只许停、
    不许定版；恢复后用 record_review 覆盖本记录再推进。"""
    if design.get("status") == "frozen":
        raise ReviewError(["设计已 frozen：不许事后改写评审记录"])
    record = {
        "reviewer": None,
        "family": None,
        "date": date,
        "items": {},
        "decision": None,
        "review_status": "REVIEW_UNAVAILABLE",
        "review_id": make_review_id(design["design_id"], date, None, None),
        "source": "review-unavailable",
        "note": note or "跨模型评审不可得（本环境无异家族模型）：显式降级，"
                        "不定版、不停工，恢复后补评审",
    }
    design.setdefault("freeze", {})["review"] = record
    _write_record_stub(root, design["design_id"], record)
    return record


def _write_record_stub(root: Path, design_id: str, record: dict) -> Path:
    d = review_dir(root, design_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "review_record.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load_checklist_items(path: Path) -> dict:
    """读评审者填好的 review_checklist.yaml，取 reviewer/decision/items
    组装成 record_review 的 data（命令行参数可覆盖 reviewer/decision）。"""
    data = read_yaml(path)
    reviewer = data.get("reviewer") or {}
    return {
        "reviewer_model": reviewer.get("model"),
        "reviewer_family": reviewer.get("family"),
        "decision": data.get("decision"),
        "items": data.get("items") or {},
    }


# ---------- amendment 增量评审（DES-D02） ----------

AMENDMENTS_DIRNAME = "amendments"

# 轻评审两项（C-补04 预写分支轨）：(标题, 判定标准)
LIGHT_REVIEW_ITEMS = ("trigger_verified", "fallback_as_predeclared")
LIGHT_CRITERIA: dict[str, tuple[str, str]] = {
    "trigger_verified": (
        "触发条件成立",
        "预写分支声明的触发条件在本次变更时点确实成立，且有证据随"
        "评审材料给出；不许事后追认一个当时并不成立的触发。",
    ),
    "fallback_as_predeclared": (
        "按预写执行",
        "变更内容与分支预写的备援方法/取值一致，未借分支之名夹带"
        "预写之外的改动；超出预写影响面的部分不属本轨，须另行登记。",
    ),
}


def amendment_review_dir(root: Path, design_id: str, amd_index: int) -> Path:
    return review_dir(root, design_id) / AMENDMENTS_DIRNAME / f"amd-{amd_index}"


def _get_amendment(design: dict, amd_index: int) -> dict:
    """按 1 起序号取 amendment；越界/非 frozen 抛 ReviewError。"""
    if design.get("status") != "frozen":
        raise ReviewError([f"设计未 frozen（status={design.get('status')}）："
                           "增量评审只针对冻结后命门 amendment"])
    amds = (design.get("freeze") or {}).get("amendments") or []
    if not (1 <= amd_index <= len(amds)):
        raise ReviewError([f"amendment 序号越界：#{amd_index}"
                           f"（现有 {len(amds)} 条）"])
    return amds[amd_index - 1]


def _amendment_track(amd: dict) -> str:
    rev = amd.get("review") or {}
    if rev.get("track") in ("light", "full"):
        return rev["track"]
    return "light" if amd.get("category") == "prewritten_branch" else "full"


def _affected_entities(design: dict, amd: dict) -> dict:
    """按字段依赖映射生成受影响登记行/主张清单（增量评审包的影响面）。"""
    stage1: list[str] = []
    reg_scope, claim_scope = "none", "none"
    for f in amd.get("fields") or []:
        areas = amendment_impact_areas(str(f))
        for it in areas["stage1_items"]:
            if it not in stage1:
                stage1.append(it)
        if areas["registry_scope"] == "all":
            reg_scope = "all"
        if areas["claims_scope"] == "all":
            claim_scope = "all"
        elif areas["claims_scope"] == "named" and claim_scope == "none":
            claim_scope = "named"
    stage1 = [it for it in STAGE1_ITEMS if it in stage1]
    rows: list[str] = []
    if reg_scope == "all":
        rows = [r.get("run_id") for r in
                (design.get("handoff") or {}).get("expected_registry") or []
                if isinstance(r, dict) and r.get("run_id")]
    claim_ids = [c.get("id") for c in
                 (design.get("claims") or {}).get("primary_claims") or []
                 if isinstance(c, dict) and c.get("id")]
    claims: list[str] = []
    if claim_scope == "all":
        claims = claim_ids
    elif claim_scope == "named":
        named: set[str] = set()
        for f in amd.get("fields") or []:
            m = re.match(r"claims\.primary_claims\[(\d+)\]", str(f))
            if m:
                idx = int(m.group(1))
                pcs = (design.get("claims") or {}).get("primary_claims") or []
                if idx < len(pcs) and isinstance(pcs[idx], dict):
                    named.add(pcs[idx].get("id"))
        # SESOI 的 estimand_ref 点名的主张同受影响
        ref = ((design.get("evaluation") or {}).get("sesoi") or {}) \
            .get("estimand_ref")
        if isinstance(ref, str):
            m = re.search(r"\[([^\]]+)\]", ref)
            if m and m.group(1) in claim_ids:
                named.add(m.group(1))
        claims = [c for c in claim_ids if c in named]
    return {"stage1_items": stage1, "registry_rows": rows, "claims": claims}


def prepare_amendment_review(root: Path, design: dict, amd_index: int, *,
                             date: str) -> dict:
    """生成增量评审包 review/<design_id>/amendments/amd-<n>/。
    只对命门 amendment 开包；非命门点名拒绝（不触发增量评审）。
    成功返回 {dir, packet, checklist, track, items_required}，
    并把 items_required/track 落进 amendment 的 review 子记录。"""
    amd = _get_amendment(design, amd_index)
    fields = amd.get("fields") or []
    if not amd.get("critical"):
        raise ReviewError([
            f"amendment #{amd_index}（{fields}）非命门字段修订："
            "不触发增量评审（DES-D02：增量评审只审命门 amendment 的"
            "变更项及其影响面），其 review.status=not_required"])
    rev = amd.get("review") or {}
    status = rev.get("status", "pending_review")
    if status in ("passed", "rejected"):
        raise ReviewError([
            f"amendment #{amd_index} 增量评审已落盘（status={status}）："
            "不许重开；决议为 reject 时须以补偿 amendment 回退变更"])
    if status not in ("pending_review", "unavailable_noted"):
        raise ReviewError([f"amendment #{amd_index} 评审状态异常：{status!r}"])
    track = _amendment_track(amd)
    impact = _affected_entities(design, amd)
    items_required = list(LIGHT_REVIEW_ITEMS) if track == "light" \
        else impact["stage1_items"]

    d = amendment_review_dir(root, design["design_id"], amd_index)
    d.mkdir(parents=True, exist_ok=True)
    reg = design.get("registration") or {}
    designer = reg.get("designer") or {}
    criteria = LIGHT_CRITERIA if track == "light" else STAGE1_CRITERIA
    checklist = {
        "design_id": design["design_id"],
        "amendment_index": amd_index,
        "fields": fields,
        "category": amd.get("category"),
        "track": track,
        "prepared": date,
        "designer": {"model": designer.get("model"),
                     "family": designer.get("family")},
        "reviewer": {"model": None, "family": None},
        "decision": None,
        "items": {
            it: {"criterion": criteria[it][0], "verdict": None, "note": ""}
            for it in items_required
        },
        "instructions": (
            "增量评审：只审本 amendment 的变更项及其影响面。逐项填 "
            "verdict（pass/fail）与 note（依据必填）；decision 填 "
            "pass/reject；reviewer.family 必须与 designer.family 不同，"
            "同族自审会被拒收。"),
    }
    checklist_path = d / "amendment_review_checklist.yaml"
    write_yaml(checklist_path, checklist)
    packet_path = d / "amendment_review_packet.md"
    packet_path.write_text(
        _render_amendment_packet(design, amd, amd_index, track,
                                 items_required, impact, date),
        encoding="utf-8")
    amd["review"] = {
        "status": "pending_review",
        "track": track,
        "items_required": items_required,
        "prepared": date,
        "packet": str(packet_path.relative_to(root))
        if packet_path.is_relative_to(root) else str(packet_path),
    }
    return {"dir": d, "packet": packet_path, "checklist": checklist_path,
            "track": track, "items_required": items_required}


def _render_amendment_packet(design: dict, amd: dict, amd_index: int,
                             track: str, items_required: list[str],
                             impact: dict, date: str) -> str:
    fr = design.get("freeze") or {}
    frev = fr.get("review") or {}
    reg = design.get("registration") or {}
    designer = reg.get("designer") or {}
    criteria = LIGHT_CRITERIA if track == "light" else STAGE1_CRITERIA
    track_gloss = (
        "轻评审（light）：本 amendment 声明为定版预写偏离分支的执行，"
        "只核触发条件成立与按预写执行两项。"
        if track == "light" else
        "全评审（full）：本 amendment 为未预见变更，只核字段依赖映射"
        "圈定的 Stage 1 条目子集，不重开未受影响的条目。")
    L: list[str] = []
    L.append(f"# 增量评审包 — {design.get('title')}（amendment #{amd_index}）")
    L.append("")
    L.append(f"> 用途：frozen 设计书 `{design['design_id']}` 的命门 "
             f"amendment #{amd_index} 增量评审（DES-D02）。本包自包含："
             "交给**另一个模型家族**的模型（或人工专家）即可独立评审。")
    L.append(f"> 生成日期：{date}｜轨道：{track}｜类别："
             f"{amd.get('category')}")
    L.append(f"> {track_gloss}")
    L.append("")
    L.append("## 变更内容（变更项本身）")
    L.append("")
    L.append(f"- 变更字段：{amd.get('fields')}")
    L.append(f"- 理由：{amd.get('reason')}")
    L.append(f"- 改时结果可见性（results_seen）：{amd.get('results_seen')}")
    L.append(f"- 用户签：{amd.get('user_signed')}｜落盘日期：{amd.get('date')}"
             f"｜变更后哈希：`{amd.get('new_hash')}`")
    if amd.get("category") == "prewritten_branch":
        branch = next(
            (b for b in (design.get("plan") or {}).get("deviation_branches")
             or [] if isinstance(b, dict)
             and b.get("id") == amd.get("branch_ref")), None)
        L.append(f"- 预写分支：{amd.get('branch_ref')}｜分支声明："
                 f"{json.dumps(branch, ensure_ascii=False, default=str)}")
    changes = amd.get("changes")
    if isinstance(changes, list) and changes:
        L.append("")
        L.append("| 字段 | 变更前 | 变更后 |")
        L.append("|---|---|---|")
        for ch in changes:
            if isinstance(ch, dict):
                L.append(
                    f"| {ch.get('field')} | "
                    f"{json.dumps(ch.get('before'), ensure_ascii=False, default=str)} | "
                    f"{json.dumps(ch.get('after'), ensure_ascii=False, default=str)} |")
    else:
        L.append("- 前后值：本 amendment 落盘于前后值记录机制之前，"
                 "变更前值未登记（以 amendment 链上一哈希版本为准）。")
    L.append("")
    L.append("## 影响面（字段依赖映射生成，只审这些）")
    L.append("")
    L.append(f"- 受影响登记行（expected_registry）："
             f"{impact['registry_rows'] or '（无）'}")
    L.append(f"- 受影响主张：{impact['claims'] or '（无）'}")
    L.append("- 须核条目：" + "、".join(
        f"{it}（{criteria[it][0]}）" for it in items_required))
    L.append("")
    L.append("## 原冻结评审收据（指针，不重开）")
    L.append("")
    L.append(f"- review_id：{frev.get('review_id') or '（无）'}｜评审者："
             f"{frev.get('reviewer')} / {frev.get('family')}｜日期："
             f"{frev.get('date')}｜决议：{frev.get('decision')}")
    L.append(f"- 冻结于 {fr.get('frozen_at')}，原始冻结哈希 "
             f"`{fr.get('content_hash')}`；本设计书的设计生成者是 "
             f"`{designer.get('model')}`（家族 `{designer.get('family')}`），"
             "评审者家族必须与此不同，同族自审会被拒收。")
    L.append("")
    L.append("## 评审标准（逐项判定，note 必填）")
    L.append("")
    for i, it in enumerate(items_required, 1):
        title, criterion = criteria[it]
        L.append(f"{i}. **{it}（{title}）**：{criterion}")
    L.append("")
    L.append("## 回填（评审完成后）")
    L.append("")
    L.append("把判定整理成 JSON（字段名写死，落盘时逐项校验）：")
    L.append("")
    L.append("```json")
    L.append(json.dumps({
        "reviewer_model": "<判定模型名>",
        "reviewer_family": "<判定模型家族，须与设计者家族不同>",
        "decision": "pass",
        "items": {it: {"verdict": "pass", "note": "<逐项依据>"}
                  for it in items_required},
    }, ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("```bash")
    L.append(f"light-design review record <project> {design['design_id']} "
             f"--amendment {amd_index} --from-json verdict.json")
    L.append("```")
    L.append("")
    L.append("落盘 pass 后 export 解拦；决议 reject 时变更不许沿用，"
             "须以补偿 amendment 回退（只追加纪律）。跨模型评审不可得时"
             "用 `review record --amendment "
             f"{amd_index} --review-unavailable` 显式落字（导出件会注明"
             "增量评审未完成，不许伪造收据）。")
    L.append("")
    return "\n".join(L)


def _normalize_required_items(raw, required: list[str]) -> tuple[dict, list[str]]:
    """把外部判定里的 items 按给定必填集规范成 {item: {status, note}}。"""
    errs: list[str] = []
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out, ["items 缺失或不是映射（增量评审须逐项判定）"]
    for it in required:
        v = raw.get(it)
        if v is None:
            errs.append(f"增量评审缺项：{it} 未判定（圈定条目逐项必填）")
            continue
        if isinstance(v, str):
            verdict, note = v, ""
        elif isinstance(v, dict):
            verdict = v.get("verdict", v.get("status"))
            note = v.get("note") or ""
        else:
            errs.append(f"items.{it} 形态非法：{type(v).__name__}")
            continue
        if verdict not in ("pass", "fail"):
            errs.append(f"items.{it}.verdict 非法：{verdict!r}（须为 pass/fail）")
            continue
        if not _nonempty_str(note):
            errs.append(f"items.{it}.note 为空（逐项判定须写依据）")
            continue
        out[it] = {"status": verdict, "note": str(note)}
    return out, errs


def record_amendment_review(root: Path, design: dict, amd_index: int,
                            data: dict, *, date: str,
                            source: str = "json") -> dict:
    """落盘一份增量评审记录：写入 amendment 的 review 子记录并存根
    amendment_review_record.json。design 的保存由调用方负责。"""
    amd = _get_amendment(design, amd_index)
    if not amd.get("critical"):
        raise ReviewError([f"amendment #{amd_index} 非命门字段修订："
                           "不触发增量评审，无待审记录可落"])
    rev = amd.get("review") or {}
    required = rev.get("items_required")
    if not isinstance(required, list) or not required:
        raise ReviewError([f"amendment #{amd_index} 尚未生成增量评审包："
                           "先跑 review prepare --amendment "
                           f"{amd_index}（评审范围以包内圈定条目为准）"])
    if rev.get("status") not in ("pending_review", "unavailable_noted"):
        raise ReviewError([f"amendment #{amd_index} 评审状态为 "
                           f"{rev.get('status')!r}，不许重复落盘/改写"])
    reviewer_model = str(data.get("reviewer_model") or "").strip()
    reviewer_family = str(data.get("reviewer_family") or "").strip()
    decision = data.get("decision")
    errs: list[str] = []
    if not reviewer_model:
        errs.append("reviewer_model 为空（评审者身份必须落盘）")
    if not reviewer_family:
        errs.append("reviewer_family 为空（异家族核验须有家族登记）")
    if reviewer_model and reviewer_family:
        same = _same_family(design, reviewer_model, reviewer_family)
        if same:
            errs.append(same)
    items, item_errs = _normalize_required_items(data.get("items"), required)
    errs.extend(item_errs)
    if decision not in REVIEW_DECISIONS:
        errs.append(f"decision 非法：{decision!r}（须为 {REVIEW_DECISIONS} 之一）")
    elif decision == "pass" and items and \
            any(v["status"] != "pass" for v in items.values()):
        failed = [k for k, v in items.items() if v["status"] != "pass"]
        errs.append(f"决议与逐项矛盾：decision=pass 但 {failed} 未 pass")
    if errs:
        raise ReviewError(errs)

    record = {
        "status": "passed" if decision == "pass" else "rejected",
        "track": rev.get("track") or _amendment_track(amd),
        "items_required": required,
        "reviewer": reviewer_model,
        "family": reviewer_family,
        "date": date,
        "items": items,
        "decision": decision,
        "review_id": make_review_id(
            f"{design['design_id']}#amd{amd_index}", date,
            reviewer_model, decision),
        "source": source,
    }
    amd["review"] = record
    _write_amendment_stub(root, design["design_id"], amd_index, record)
    return record


def record_amendment_review_unavailable(root: Path, design: dict,
                                        amd_index: int, *, date: str,
                                        note: str = "") -> dict:
    """增量评审降级通道（DES-D02）：跨模型评审不可得时显式落字
    unavailable_noted，解除待审拦截；导出件会注明该 amendment 的
    增量评审未完成。恢复后可重新 prepare 并 record 覆盖本记录。"""
    amd = _get_amendment(design, amd_index)
    if not amd.get("critical"):
        raise ReviewError([f"amendment #{amd_index} 非命门字段修订："
                           "不触发增量评审，无待审状态可落字"])
    rev = amd.get("review") or {}
    if rev.get("status") not in ("pending_review", "unavailable_noted", None):
        raise ReviewError([f"amendment #{amd_index} 评审状态为 "
                           f"{rev.get('status')!r}，不许改写为降级记录"])
    record = {
        "status": "unavailable_noted",
        "track": rev.get("track") or _amendment_track(amd),
        "items_required": rev.get("items_required"),
        "prepared": rev.get("prepared"),
        "reviewer": None,
        "family": None,
        "date": date,
        "items": {},
        "decision": None,
        "review_id": make_review_id(
            f"{design['design_id']}#amd{amd_index}", date, None, None),
        "source": "review-unavailable",
        "note": note or "跨模型增量评审不可得：显式落字，解除待审拦截；"
                        "导出件注明未完成，恢复后补评审",
    }
    amd["review"] = record
    _write_amendment_stub(root, design["design_id"], amd_index, record)
    return record


def _write_amendment_stub(root: Path, design_id: str, amd_index: int,
                          record: dict) -> Path:
    d = amendment_review_dir(root, design_id, amd_index)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "amendment_review_record.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path

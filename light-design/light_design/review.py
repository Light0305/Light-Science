"""定版评审子流程（D6 补完，二期）。

一期 frozen 门只验 freeze.review 的结构与异家族，评审记录靠手写 yaml。
二期把评审做成正式子流程（与 Light-Idea 查新复核包同构）：

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
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .project import render_design_md
from .schema import (
    REVIEW_DECISIONS,
    STAGE1_ITEMS,
    VISIBILITY_LEVELS,
    _nonempty_str,
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
    （与 Light-Idea 的 verdict_id 口径同构）。"""
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
    L.append(f"> 用途：Light-Design 设计书 `{design['design_id']}`"
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

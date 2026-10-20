"""状态机：intake → contracted → produced → audited → delivered。

逐图同构推进，包状态 = 逐图状态的机械汇总（草案 §二）。

门面（Phase 2）：
- intake→contracted：全门实现——承接快照齐全且哈希对齐、目标刊图形
  合同已登记、AI 政策快照在有效期内（schematic 线）、每图合同五点齐、
  数据图后端已按解析顺序决定并落盘、方法图配色确认门已过。
- contracted→produced：产物齐备深门——数据图（脚本/源数据/预览齐备、
  源级预检全过、账实相符）、方法图（提示词产物、参考图入包登记且
  验收落字、重绘 manifest 落字且构建对账无差、provenance 行齐、
  逐标签核对完成）。
- produced→audited：§1.7 审计门按线全跑且绑定当前产物哈希（FRESH），
  阻断门无 FIX、无 NOT_AUDITABLE，REVIEW 门逐门有处置理由落字。
- audited→delivered：delivery.yaml 在场且为现行版、编号已冻结、
  逐图交付行哈希/图注哈希与现状一致、交付前账行逐行复验全过、
  审计 FRESH（delivery.delivered_gaps）。
门不过 → 停在当前段并逐项点名，不许整体放行。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .audit import audit_status, record_path
from .produce import precheck_script, script_path, source_data_path
from .project import (
    effective_backend, load_package, provenance_row, save_head,
)
from .prompt import prompt_path
from .redraw import load_manifest, validate_manifest, vsdx_relpath
from .reference import reference_relpath
from .style import bundle_current
from .util import load_structured, sha256_file, today
from .validate import policy_snapshot_expired, validate_package

NEXT_STATE = schema.NEXT_STATE


class GateError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _contracted_gaps(pkg) -> list:
    """intake→contracted 入口门（草案 §二）：全过才许 advance。"""
    gaps = []
    head = pkg["head"]
    report = validate_package(pkg["root"])
    for e in report["errors"]:
        gaps.append(f"[{e['code']}] {e['message']}")

    if not head.get("intake"):
        gaps.append("承接快照为空：先跑 intake（--manifest 或 --standalone）")
    figures = head.get("figures") or []
    if not figures:
        gaps.append("逐图状态表为空：无图不开合同")
    if not (pkg["journal_contract"] or {}).get("registered"):
        gaps.append("目标刊图形合同未登记：intake 时以 --journal-contract "
                    "登记（或补齐 journal_contract.yaml 并置 registered=true）")

    backend_reg = pkg["backend"] or {}
    if backend_reg.get("backend") is None and not backend_reg.get("overrides"):
        gaps.append("数据图后端未决定：按解析顺序五级决定并落盘 backend.json"
                    "（约束 2 / 拍板 D2）")
    for row in figures:
        if row.get("line") != "data":
            continue
        effective, _ = effective_backend(backend_reg, row["fig_id"])
        if effective is None:
            gaps.append(f"数据图 {row['fig_id']} 的后端无解析结果"
                        "（包级默认与逐图覆写均未登记）")

    schematic_ids = [r["fig_id"] for r in figures
                     if r.get("line") == "schematic"]
    if schematic_ids:
        target = head.get("target_journal") or {}
        snapshot = target.get("ai_policy_snapshot")
        if snapshot is None:
            gaps.append("方法图线缺 AI 政策快照：intake 时以 --ai-policy "
                        "登记目标刊政策快照（约束 8：逐刊核对）")
        elif policy_snapshot_expired(snapshot):
            gaps.append("AI 政策快照已过期：按目标刊当期政策原文重新核对"
                        "并重新登记（约束 8：过期自动失效）")
        for fig_id in schematic_ids:
            contract = pkg["contracts"].get(fig_id) or {}
            palette_conf = contract.get("palette_confirmation") or {}
            if not palette_conf.get("confirmed_by") \
                    or not palette_conf.get("confirmed_at"):
                gaps.append(f"方法图 {fig_id} 未过配色确认门："
                            "palette_confirmation 须落确认人 + 时点"
                            "（约束 7：角色色板未定不许出提示词）")
            policy = contract.get("policy_check") or {}
            if not policy.get("policy_snapshot_ref"):
                gaps.append(f"方法图 {fig_id} 的 policy_check 未指向 "
                            "AI 政策快照（policy_snapshot_ref）")
    return gaps


def _produced_gaps(pkg) -> list:
    """contracted→produced 入口门（草案 §二 produced 行）：产物齐备性。

    数据图：脚本 + 源数据 + 预览齐备、源级预检全过、provenance
    哈希与实物相符（账实相符）。方法图：提示词产物落盘、参考图入包
    登记且验收落字、重绘 manifest 落字且成品反抽对账无未登记差集、
    provenance 账行齐、逐标签核对完成才许过。
    """
    gaps = []
    root = pkg["root"]
    report = validate_package(root)
    for e in report["errors"]:
        gaps.append(f"[{e['code']}] {e['message']}")
    bundle, bundle_problem = bundle_current(root)
    has_data = any(r.get("line") == "data"
                   for r in pkg["head"].get("figures") or [])
    if has_data and bundle_problem:
        gaps.append(bundle_problem)

    for row in pkg["head"].get("figures") or []:
        fig_id = row["fig_id"]
        entry = provenance_row(pkg["provenance"], fig_id) or {}
        if row.get("line") == "data":
            path = script_path(root, fig_id)
            if not path.exists():
                gaps.append(f"数据图 {fig_id} 缺绘图脚本 "
                            f"data/scripts/{fig_id}.py")
            elif bundle is not None and not bundle_problem:
                _header, pre_gaps = precheck_script(root, fig_id, bundle)
                gaps.extend(pre_gaps)
            if bundle is not None and entry.get("style_build_hash") \
                    and entry["style_build_hash"] \
                    != bundle["style_build_hash"]:
                gaps.append(f"数据图 {fig_id} 账面 style_build_hash 与"
                            "当前编译 bundle 不一致：重跑 produce 回填")
            contract = pkg["contracts"].get(fig_id)
            data_path = source_data_path(root, contract)
            if data_path is None:
                gaps.append(f"数据图 {fig_id} 合同未登记源数据路径")
            elif not data_path.exists():
                gaps.append(f"数据图 {fig_id} 源数据不存在：{data_path}")
            preview = root / "data" / "previews" / f"{fig_id}.png"
            if not preview.exists():
                gaps.append(f"数据图 {fig_id} 缺预览渲染 "
                            f"data/previews/{fig_id}.png（跑 produce 生成）")
            if path.exists() and entry.get("script_hash") \
                    != sha256_file(path):
                gaps.append(f"数据图 {fig_id} 账面脚本哈希与实物不符"
                            "（账实相符：脚本变更后重跑 produce 回填）")
            if data_path is not None and data_path.exists() \
                    and entry.get("source_data_hash") \
                    != sha256_file(data_path):
                gaps.append(f"数据图 {fig_id} 账面源数据哈希与实物不符")
        else:
            if not prompt_path(root, fig_id).exists():
                gaps.append(f"方法图 {fig_id} 缺提示词产物 "
                            f"schematic/prompts/{fig_id}.md（跑 prompt build）")
            ref_rel = reference_relpath(root, fig_id)
            if ref_rel is None:
                gaps.append(f"方法图 {fig_id} 参考图未入包登记"
                            "（跑 reference add）")
            elif entry.get("reference_image_hash") \
                    != sha256_file(root / ref_rel):
                gaps.append(f"方法图 {fig_id} 账面参考图哈希与包内"
                            "文件不符（账实相符）")
            acceptance = entry.get("reference_acceptance") or {}
            if acceptance.get("done") is not True:
                gaps.append(f"方法图 {fig_id} 参考图验收未落字"
                            "（约束 9：三项清单经 reference accept 落字）")
            manifest = load_manifest(root, fig_id)
            if manifest is None:
                gaps.append(f"方法图 {fig_id} 缺重绘 manifest"
                            "（redraw install 登记，单一真相源）")
            else:
                gaps.extend(validate_manifest(manifest, root=root))
                if manifest.get("status") not in ("built", "verified"):
                    gaps.append(f"方法图 {fig_id} 重绘 manifest 状态为 "
                                f"{manifest.get('status')}：须先 redraw "
                                "build 构建成品")
                reconciliation = manifest.get("reconciliation") or {}
                if reconciliation.get("ok") is not True:
                    gaps.append(f"方法图 {fig_id} 重绘反抽对账未过"
                                "（redraw extract 须无未登记差集）")
            vsdx = root / vsdx_relpath(fig_id)
            redraw_source = entry.get("redraw_source") or {}
            if not vsdx.exists():
                gaps.append(f"方法图 {fig_id} 成品 .vsdx 不存在"
                            "（redraw build 构建）")
            elif redraw_source.get("hash") != sha256_file(vsdx):
                gaps.append(f"方法图 {fig_id} 账面重绘源哈希与成品"
                            "不符（账实相符）")
            if not entry.get("prompt_version"):
                gaps.append(f"方法图 {fig_id} 账面缺 prompt_version")
            if not entry.get("generation_model"):
                gaps.append(f"方法图 {fig_id} 账面缺生成模型登记 "
                            "（reference add --model-name 回填）")
            label = entry.get("label_check") or {}
            if label.get("done") is not True:
                gaps.append(f"方法图 {fig_id} 逐标签核对未完成落字"
                            "（约束 9：重绘成品逐标签核对，"
                            "provenance set label_check 回填）")
    return gaps


def _audited_gaps(pkg) -> list:
    """produced→audited 入口门（草案 §二 audited 行）：审计门按线
    全跑且绑定当前交付物哈希——无 FIX、无 NOT_AUDITABLE、
    REVIEW_REQUIRED 逐门有处置理由落字。"""
    gaps = []
    root = pkg["root"]
    report = validate_package(root)
    for e in report["errors"]:
        gaps.append(f"[{e['code']}] {e['message']}")
    status = audit_status(root)["figures"]
    for row in pkg["head"].get("figures") or []:
        fig_id = row["fig_id"]
        state = (status.get(fig_id) or {}).get("state")
        if state == "NO_ARTIFACT":
            gaps.append(f"图 {fig_id} 无最终产物文件：先完成生产再审计")
            continue
        if state == "MISSING":
            gaps.append(f"图 {fig_id} 未审计：跑 audit run")
            continue
        if state == "STALE":
            gaps.append(f"图 {fig_id} 审计已 STALE（产物在审计后变更）："
                        "重跑 audit run（约束 13：改动必重跑）")
            continue
        record = load_structured(record_path(root, fig_id))
        dispositions = record.get("review_dispositions") or {}
        for name, gate in (record.get("gates") or {}).items():
            if not gate.get("applicable"):
                continue
            verdict = gate.get("verdict")
            if verdict == "FIX_BEFORE_DELIVERY":
                fails = [f["message"] for f in gate.get("findings") or []
                         if f["level"] == "fail"]
                gaps.append(f"图 {fig_id} 审计门 {name} 为 "
                            "FIX_BEFORE_DELIVERY：" + "；".join(fails))
            elif verdict == "NOT_AUDITABLE":
                fails = [f["message"] for f in gate.get("findings") or []
                         if f["level"] == "fail"]
                gaps.append(f"图 {fig_id} 审计门 {name} 为 "
                            "NOT_AUDITABLE（不许声称通过）："
                            + "；".join(fails))
            elif verdict == "REVIEW_REQUIRED" \
                    and not dispositions.get(name):
                gaps.append(f"图 {fig_id} 审计门 {name} 为 "
                            "REVIEW_REQUIRED 且无处置理由落字："
                            "audit note 逐门落处置后才许过门")
    return gaps


def advance(root) -> dict:
    root = Path(root)
    pkg = load_package(root)
    head = pkg["head"]
    if head is None:
        raise GateError(["图包不存在（先 init）"])
    current = head.get("status")
    if current not in NEXT_STATE:
        return {"advanced": False, "from": current, "to": None,
                "gaps": [f"状态 {current} 已是终态或不在状态机词表内"]}
    target = NEXT_STATE[current]
    if target == "contracted":
        gaps = _contracted_gaps(pkg)
    elif target == "produced":
        gaps = _produced_gaps(pkg)
    elif target == "audited":
        gaps = _audited_gaps(pkg)
    elif target == "delivered":
        from .delivery import delivered_gaps
        gaps = delivered_gaps(pkg)
    else:
        gaps = [f"未知目标状态 {target}"]
    result = {"advanced": False, "from": current, "to": target, "gaps": gaps}
    if gaps:
        return result
    head["status"] = target
    head.setdefault("status_history", []).append(
        {"state": target, "at": today(), "by": "light-figure advance"})
    backend_reg = pkg["backend"] or {}
    for row in head.get("figures") or []:
        row["stage"] = target
        if target == "audited":
            row["audit_final"] = "pass"
        if target == "delivered":
            row["delivery_status"] = "delivered"
        if row.get("line") == "data":
            effective, _ = effective_backend(backend_reg, row["fig_id"])
            row["backend"] = effective
    save_head(root, head)
    result["advanced"] = True
    return result


def status_summary(root) -> dict:
    """状态摘要（report 与排障共用）：包状态 + 逐图行 + 校验计数。"""
    root = Path(root)
    pkg = load_package(root)
    head = pkg["head"]
    if head is None:
        raise GateError(["图包不存在（先 init）"])
    report = validate_package(root)
    return {
        "package_id": head.get("package_id"),
        "title": head.get("title"),
        "status": head.get("status"),
        "figures": [
            {"fig_id": r.get("fig_id"), "line": r.get("line"),
             "stage": r.get("stage"), "backend": r.get("backend"),
             "audit_final": r.get("audit_final"),
             "delivery_status": r.get("delivery_status")}
            for r in head.get("figures") or []
        ],
        "validate": {"ok": report["ok"],
                     "error_count": report["error_count"],
                     "warning_count": report["warning_count"]},
    }

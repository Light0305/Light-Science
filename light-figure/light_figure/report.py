"""FIGURE_REPORT.md 生成/刷新（手工区保留，同 Light-Design 体例）。

报告是图包的唯一权威汇总文档：包状态 / 逐图状态表 / 后端解析 /
期刊合同与容差 / provenance 账面 / 校验结论。手工区（MANUAL 标记
之间）逐字保留，刷新不覆盖。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import FILES, effective_backend, load_package
from .util import today
from .validate import validate_package

MANUAL_START = "<!-- MANUAL:START -->"
MANUAL_END = "<!-- MANUAL:END -->"


def _extract_manual(text: str) -> str:
    """取旧报告里的手工区内容（标记之间）；无标记时为空。"""
    if MANUAL_START in text and MANUAL_END in text:
        inner = text.split(MANUAL_START, 1)[1].split(MANUAL_END, 1)[0]
        return inner.strip("\n")
    return ""


def build_report(root, *, date: str | None = None) -> dict:
    """生成/刷新图包根目录的 FIGURE_REPORT.md，返回汇总 dict。"""
    root = Path(root)
    date = date or today()
    pkg = load_package(root)
    head = pkg["head"] or {}
    report_path = root / FILES["report"]
    old = report_path.read_text(encoding="utf-8") \
        if report_path.exists() else ""
    manual = _extract_manual(old)

    validation = validate_package(root)
    figures = head.get("figures") or []
    backend_reg = pkg["backend"] or {}
    journal = pkg["journal_contract"] or {}
    provenance_entries = {
        e.get("fig_id"): e
        for e in (pkg["provenance"] or {}).get("entries") or []
    }

    L: list[str] = []
    L.append(f"# FIGURE_REPORT — {head.get('title', root.name)}")
    L.append("")
    L.append(f"> 本图包唯一权威汇总（report 命令生成/刷新于 {date}）："
             "包状态 / 逐图状态 / 后端与期刊合同 / provenance 账面 / 校验结论。"
             "手工区在文末标记之间，刷新不覆盖。")
    L.append("")
    L.append("## 总览")
    L.append("")
    L.append(f"- 包 ID：`{head.get('package_id')}`")
    L.append(f"- 包状态：{head.get('status')}")
    intake = head.get("intake") or {}
    if intake:
        L.append(f"- 承接：{intake.get('source_kind')} @ "
                 f"{intake.get('intake_at')}（源哈希 "
                 f"`{str(intake.get('source_hash'))[:12]}…`）")
    else:
        L.append("- 承接：（未 intake）")
    target = head.get("target_journal") or {}
    if target:
        snap = target.get("ai_policy_snapshot") or {}
        L.append(f"- 目标期刊：模板记录 {target.get('template_record_id')}｜"
                 f"AI 政策快照 verified_at={snap.get('verified_at')}")
    data_n = sum(1 for r in figures if r.get("line") == "data")
    schem_n = sum(1 for r in figures if r.get("line") == "schematic")
    L.append(f"- 图总数：{len(figures)}（数据图 {data_n} / 方法图 {schem_n}）")
    L.append(f"- 校验：{'通过' if validation['ok'] else '未通过'}"
             f"（error {validation['error_count']} / "
             f"warning {validation['warning_count']}）")
    L.append("")
    L.append("## 逐图状态")
    L.append("")
    if not figures:
        L.append("（暂无图）")
    else:
        L.append("| fig_id | 线别 | 段 | 后端 | 审计终态 | 交付 |")
        L.append("|---|---|---|---|---|---|")
        for row in figures:
            effective, _ = effective_backend(backend_reg, row["fig_id"])
            backend = row.get("backend") or effective or "—"
            L.append(f"| {row.get('fig_id')} | {row.get('line')} "
                     f"| {row.get('stage')} | {backend} "
                     f"| {row.get('audit_final')} "
                     f"| {row.get('delivery_status')} |")
    L.append("")
    L.append("## 期刊合同与容差")
    L.append("")
    L.append(f"- 登记状态：{'已登记' if journal.get('registered') else '未登记（骨架缺省）'}"
             f"｜期刊：{journal.get('journal')}｜版本：{journal.get('version')}"
             f"｜核查日期：{journal.get('checked_at')}")
    tolerances = journal.get("tolerances") or {}
    if tolerances:
        L.append("- 容差参数：" + "；".join(
            f"{k}={tolerances[k]}" for k in sorted(tolerances)))
    exemptions = journal.get("tolerance_exemptions") or []
    L.append(f"- 容差豁免登记：{len(exemptions)} 项"
             + ("（" + "；".join(
                 f"{e.get('param')}={e.get('value')}：{e.get('reason')}"
                 for e in exemptions) + "）" if exemptions else ""))
    L.append("")
    L.append("## provenance 账面")
    L.append("")
    if not figures:
        L.append("（暂无账行）")
    for row in figures:
        entry = provenance_entries.get(row["fig_id"]) or {}
        if row.get("line") == "schematic":
            redraw = entry.get("redraw_source") or {}
            label = entry.get("label_check") or {}
            L.append(
                f"- `{row['fig_id']}`（方法图）：提示词版本 "
                f"{entry.get('prompt_version')}｜参考图哈希 "
                f"{'有' if entry.get('reference_image_hash') else '无'}｜"
                f"重绘源 {'有' if redraw.get('path') else '无'}｜"
                f"逐标签核对 {'已完成' if label.get('done') else '未完成'}")
        else:
            L.append(
                f"- `{row['fig_id']}`（数据图）：后端 "
                f"{entry.get('backend')}｜脚本哈希 "
                f"{'有' if entry.get('script_hash') else '无'}｜"
                f"源数据哈希 {'有' if entry.get('source_data_hash') else '无'}")
    L.append("")
    L.append("## 校验问题（error 全文）")
    L.append("")
    if not validation["errors"]:
        L.append("（无 error）")
    for e in validation["errors"]:
        L.append(f"- [{e['code']}] {e['message']}")
    L.append("")
    L.append("## 手工区（人工维护，report 刷新不覆盖）")
    L.append("")
    L.append(MANUAL_START)
    if manual:
        L.append(manual)
    L.append(MANUAL_END)
    L.append("")
    report_path.write_text("\n".join(L), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "date": date,
        "status": head.get("status"),
        "figures": len(figures),
        "validate_ok": validation["ok"],
        "error_count": validation["error_count"],
        "warning_count": validation["warning_count"],
    }

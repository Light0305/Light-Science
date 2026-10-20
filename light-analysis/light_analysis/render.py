"""渲染：audit.md（承接可判性清单）与 ANALYSIS_REPORT.md（判定总表）。

渲染只是视图：数字一律从结构化文件机械汇总，不许在渲染层加工口径。
"""

from __future__ import annotations

from .project import current_verdicts

_JUDGE_LABEL = {
    "judgeable": "可判",
    "untested_candidate": "未检验候选（预登记 untested）",
    "undetermined_candidate": "不可判候选（预登记 undetermined）",
    "material_fail": "材料不合格（拦截）",
}


def render_audit(audit: dict) -> str:
    s = audit.get("summary") or {}
    out = [
        f"# A0 承接与可判性校验 — {audit.get('analysis_id')}",
        "",
        f"- 校验日期：{audit.get('checked_at')}",
        f"- 执行包：{audit.get('execution_id')}（execution_card 哈希 "
        f"`{str(audit.get('execution_card_hash'))[:16]}…`）",
        f"- Design content_hash：`{str(audit.get('design_content_hash'))[:16]}…`",
        f"- 登记行集哈希：`{str(audit.get('registry_hash'))[:16]}…`",
        f"- 哈希对齐：{audit.get('hash_alignment')}",
        "",
        f"共 {s.get('total', 0)} 行：可判 {s.get('judgeable', 0)}、"
        f"untested 候选 {s.get('untested_candidate', 0)}、"
        f"undetermined 候选 {s.get('undetermined_candidate', 0)}、"
        f"null 精度预警 {s.get('null_precision_warnings', 0)}。",
        "",
        "| 登记行 | 角色 | 可判性 | 有效 n / 登记 n | 理由 |",
        "|---|---|---|---|---|",
    ]
    for line in audit.get("lines") or []:
        reasons = "；".join(line.get("reasons") or []) or "—"
        out.append(
            f"| {line.get('registry_line_id')} | {line.get('role') or '—'} | "
            f"{_JUDGE_LABEL.get(line.get('judgeability'), line.get('judgeability'))} | "
            f"{line.get('n_effective')} / {line.get('n_registered')} | {reasons} |")
    if audit.get("failures"):
        out += ["", "## 失败项", ""]
        out += [f"- {f}" for f in audit["failures"]]
    out.append("")
    return "\n".join(out)


def render_report(pkg: dict) -> str:
    analysis = pkg.get("analysis") or {}
    counts = analysis.get("counts") or {}
    current = current_verdicts(pkg.get("verdicts") or [])
    snap_lines = {
        l["registry_line_id"]: l
        for l in (analysis.get("registry_snapshot") or {}).get("lines") or []
    }
    out = [
        f"# {analysis.get('analysis_id')} 分析报告",
        "",
        f"- 状态：{analysis.get('status')}",
        f"- 执行包：{(analysis.get('execution_ref') or {}).get('execution_id')}",
        f"- Design：{(analysis.get('design_ref') or {}).get('design_id')} "
        f"(content_hash `{(analysis.get('design_ref') or {}).get('content_hash') or ''}`)",
        "",
        "## 判定分布（机械汇总）",
        "",
        "| positive | negative | null | undetermined | untested | 登记行总数 |",
        "|---|---|---|---|---|---|",
        f"| {counts.get('positive', 0)} | {counts.get('negative', 0)} | "
        f"{counts.get('null', 0)} | {counts.get('undetermined', 0)} | "
        f"{counts.get('untested', 0)} | {counts.get('total_lines', 0)} |",
        "",
        "## 逐行判定",
        "",
        "| 登记行 | 判定 | 象限 | 强度 | 依据规格 | 备注 |",
        "|---|---|---|---|---|---|",
    ]
    line_ids = (analysis.get("registry_snapshot") or {}).get("line_ids") or list(current)
    for lid in line_ids:
        row = current.get(lid)
        if row is None:
            judge = (snap_lines.get(lid) or {}).get("judgeability", "")
            out.append(f"| {lid} | （未判定） | | | | 承接可判性：{judge} |")
        else:
            out.append(
                f"| {lid} | {row.get('verdict')} | {row.get('quadrant') or ''} | "
                f"{row.get('strength_grade') or ''} | {row.get('basis_spec_id') or ''} | "
                f"{row.get('note') or ''} |")
    out.append("")
    return "\n".join(out)

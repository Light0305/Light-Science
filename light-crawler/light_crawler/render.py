"""CRAWL_REPORT.md：工作区人读摘要视图（只读渲染，不落状态）。"""

from __future__ import annotations

from pathlib import Path

from . import precheck as precheck_mod
from . import project, schema, storage


def render_report(root) -> str:
    header = project.load_header(root)
    lines = [f"# 采集工作区报告（{header.get('project')}）", ""]
    lines.append(f"- 工作区状态：{header.get('status')}"
                 f"（熔断目标：{header.get('circuit_broken_targets') or '无'}）")
    prov = storage.read_provenance(root)
    lines.append(f"- provenance 总账：{len(prov)} 条"
                 f"（抓取 {sum(1 for r in prov if r.get('kind') == 'fetch')}、"
                 f"人工导入 {sum(1 for r in prov if r.get('kind') == 'manual_import')}）")
    lines += ["", "## 目标", "",
              "| 目标 | 通道 | 用途 | 预检 | 熔断 |",
              "|---|---|---|---|---|"]
    for reg in project.list_targets(root):
        cur = precheck_mod.current_precheck(root, reg["target_id"])
        state = project.load_state(root, reg["target_id"])
        lines.append(
            f"| {reg['target_id']} | {reg['channel']} | {reg['purpose_kind']} "
            f"| {cur['status']} | {'是' if state.get('circuit_broken') else '否'} |")
    refusals = [e for e in project.read_events(root)
                if e["type"] in schema.REFUSAL_EVENT_TYPES]
    lines += ["", f"## 拒绝留痕（共 {len(refusals)} 条）", ""]
    if refusals:
        for e in refusals[-20:]:
            lines.append(f"- [{e['at']}] {e['type']} "
                         f"目标 {e.get('target_id') or '-'}：{e.get('detail')}")
    else:
        lines.append("（暂无拒绝记录）")
    lines.append("")
    return "\n".join(lines)


def write_report(root) -> Path:
    dest = Path(root) / "CRAWL_REPORT.md"
    dest.write_text(render_report(root), encoding="utf-8")
    return dest

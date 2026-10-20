"""事前 stale 清单视图（EXP-D02）。

偏离作废是事后机制（跑完对账、登记后算闭包）；开工前缺一个回答：
「以当前代码/数据/参数，本批已登记 run 哪些还有效、哪些已 stale、
补跑只需跑哪几条。」本模块以现行哈希链对登记集做状态查询（dvc
deps 哈希比对式），输出三态清单 current / stale / voided：

- voided：run 已带作废标记（voided_by 在场）——既成事实，直接引用；
- stale：出生证明逐维与「现行参照」不符（触发维逐条点名），或其
  上游条目已 stale（brief 依赖图传递闭包，维 upstream——与
  deviation 闭包同一算法、同一口径）；
- current：比对维度全合，或尚无出生证明（planned，开跑时按现行
  规格定型）。

现行参照两路（均为机械比对，不靠自述；构建单判断 J1）：
(a) 设计链：重读 design_ref.export_dir 的 design_card.json，取现行
    哈希（amendment 链尾，口径同 intake），与 run 承接区钉住的
    content_hash 比对（维 design）；交接目录已不可读时该维记
    「未比对」并在报告注明，不伪造结论。
(b) 调用方声明的现行状态 spec（--spec）：按条目键给
    {design_run_id: spec} 或全包一份 spec；按出生证明逐维比对
    （code/config/data_version/environment 走出生证明成分哈希，
    params 走 params_hash）。声明未覆盖的维不下结论、报告注明。

只读纪律：本模块不写 events、不动 run.yaml / execution.yaml；
产物只有两份报告（机读 stale_report.json + 人读 STALE_REPORT.md）。
作废仍走 deviation 闭包流程——stale 只是事前视图，不是处置。
"""

from __future__ import annotations

import json
from pathlib import Path

from .deviations import compute_closure
from .project import current_design_hash, exec_dir, load_package
from .schema import birth_components, compute_params_hash, run_voided_by
from .util import today

# spec 成分键 → (报告维名, 出生证明成分键)；params 单独走 params_hash
_SPEC_COMPONENT_DIMS = (
    ("code_snapshot", "code", "code_snapshot"),
    ("config", "config", "config"),
    ("data_version", "data", "data_version"),
    ("environment", "env", "environment"),
)

_DIM_LABELS = {
    "design": "设计版本",
    "code": "代码快照",
    "params": "参数",
    "config": "配置全文",
    "data": "数据版本",
    "env": "环境声明",
    "upstream": "上游条目",
}


def _spec_for(current_spec: dict | None, design_run_id: str) -> dict | None:
    """从现行状态声明里取某条目的 spec：顶层含成分键 → 全包一份；
    否则按条目键取 {design_run_id: spec}；都没有 → None（该条目
    无声明参照，(b) 路不比对）。"""
    if not current_spec:
        return None
    if any(k in current_spec for k in
           ("config", "params", "code_snapshot", "data_version", "environment")):
        return current_spec
    sub = current_spec.get(design_run_id)
    return sub if isinstance(sub, dict) else None


def _current_design(execution: dict) -> tuple[str | None, str]:
    """(a) 路：重读交接件取设计现行哈希。返回 (哈希或 None, 注记)。"""
    export_dir = (execution.get("design_ref") or {}).get("export_dir") or ""
    card_path = Path(export_dir) / "design_card.json" if export_dir else None
    if card_path is None or not card_path.exists():
        return None, (f"交接目录 {export_dir or '(未登记)'} 已不可读，"
                      "design 维未比对（不伪造结论）")
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"design_card.json 重读失败（{e}），design 维未比对"
    cur = current_design_hash(card)
    if not cur:
        return None, "交接件无现行哈希（freeze.content_hash 缺失），design 维未比对"
    return cur, f"交接件现行哈希 {cur[:12]}…（amendment 链尾口径）"


def _compare_run(run: dict, spec: dict | None, design_now: str | None) -> list[dict]:
    """逐维比对单个 run 的出生证明 vs 现行参照，返回不符维清单
    [{dimension, detail, run_anchor, current_anchor}]。"""
    dims: list[dict] = []
    ident = run.get("identity") or {}
    intake_hash = ((run.get("intake") or {}).get("design_ref") or {}).get("content_hash")
    if design_now and intake_hash and intake_hash != design_now:
        dims.append({
            "dimension": "design",
            "detail": "run 承接的设计哈希与交接件现行哈希不一致"
                      "（设计已 amendment 前进，本 run 按旧冻结版出生）",
            "run_anchor": intake_hash[:12], "current_anchor": design_now[:12]})
    if spec is None:
        return dims
    bc = (ident.get("birth_certificate") or {}).get("components") or {}
    if not bc:
        return dims  # 未开跑：无出生证明，开跑时按现行规格定型
    pseudo = {
        "config": spec.get("config"),
        "code_snapshot": spec.get("code_snapshot") or {},
        "data_version": spec.get("data_version"),
        "environment": spec.get("environment"),
    }
    current_components = birth_components(pseudo)
    for spec_key, dim, comp_key in _SPEC_COMPONENT_DIMS:
        if spec_key not in spec:
            continue  # 声明未覆盖的维不下结论
        if bc.get(comp_key) != current_components.get(comp_key):
            dims.append({
                "dimension": dim,
                "detail": f"出生证明 {_DIM_LABELS[dim]} 成分与现行声明不一致",
                "run_anchor": (bc.get(comp_key) or "")[:12],
                "current_anchor": (current_components.get(comp_key) or "")[:12]})
    if "params" in spec:
        cur_params = compute_params_hash(spec.get("params"))
        if ident.get("params_hash") and ident["params_hash"] != cur_params:
            dims.append({
                "dimension": "params",
                "detail": "params_hash 与现行声明的参数集不一致",
                "run_anchor": ident["params_hash"][:12],
                "current_anchor": cur_params[:12]})
    return dims


def _advice(dims: list[dict], stale_upstream: list[str]) -> str:
    parts: list[str] = []
    names = {d["dimension"] for d in dims}
    if "design" in names:
        parts.append("设计已变更：回 intake 以新批次承接现行冻结版后重跑本条目")
    direct = [d for d in dims if d["dimension"] not in ("design", "upstream")]
    if direct:
        labels = "、".join(_DIM_LABELS[d["dimension"]] for d in direct)
        parts.append(f"以现行{labels}新开 attempt 补跑本条目"
                     "（run-new --retry-of 留血缘，改参数=新 run 不许原地改）")
    if stale_upstream:
        parts.append(f"上游条目 {'、'.join(stale_upstream)} 已 stale："
                     "待上游补跑后凭新产物重跑本条目")
    return "；".join(parts)


def compute_stale_report(root: Path, exec_id: str, *,
                         current_spec: dict | None = None,
                         spec_source: str = "",
                         date: str | None = None) -> dict:
    """组装 stale 三态清单（纯查询，不落盘、不改包状态）。"""
    date = date or today()
    pkg = load_package(root, exec_id)
    execution = pkg["execution"]
    runs = pkg["runs"]
    design_now, design_note = _current_design(execution)

    entries: dict[str, dict] = {}
    direct_stale_entries: set[str] = set()
    for rid in sorted(runs):
        run = runs[rid]
        spec = _spec_for(current_spec, run.get("design_run_id"))
        dims = _compare_run(run, spec, design_now)
        voided = run_voided_by(run)
        entries[rid] = {
            "run_id": rid,
            "design_run_id": run.get("design_run_id"),
            "run_status": run.get("status"),
            "state": "voided" if voided else ("stale" if dims else "current"),
            "stale_dimensions": dims,
            "voided_by": voided,
            "stale_upstream": [],
            "advice": "",
            "note": "" if (run.get("identity") or {}).get("birth_certificate")
                    else "未开跑（无出生证明）：开跑时按现行规格定型",
        }
        if dims and not voided:
            direct_stale_entries.add(run.get("design_run_id"))

    # 下游传递闭包：与 deviation 闭包同一算法（compute_closure 以
    # 直接 stale 条目的任一 run 为上下文、dimension=None 展开到全部
    # 下游条目），保证 stale 集与偏离闭包口径一致、可对照。
    upstream_map: dict[str, list[str]] = {}
    for entry_id in sorted(direct_stale_entries):
        rep = next(r for r in sorted(runs)
                   if runs[r].get("design_run_id") == entry_id)
        for rid in compute_closure(pkg, run_id=rep, dimension=None):
            if rid == rep:
                continue
            src_entry = runs[rid].get("design_run_id")
            if src_entry == entry_id:
                continue  # 同条目其他 attempt：由其自身比对结论说话
            if entries[rid]["state"] == "current":
                entries[rid]["state"] = "stale"
                entries[rid]["stale_dimensions"].append({
                    "dimension": "upstream",
                    "detail": f"上游条目 {entry_id} 已 stale，其产物被本条目消费",
                    "run_anchor": "", "current_anchor": ""})
            if entries[rid]["state"] == "stale":
                upstream_map.setdefault(rid, []).append(entry_id)
    for rid, entry in entries.items():
        entry["stale_upstream"] = sorted(set(upstream_map.get(rid, [])))
        if entry["state"] == "stale":
            entry["advice"] = _advice(entry["stale_dimensions"],
                                       entry["stale_upstream"])
        elif entry["state"] == "voided":
            entry["advice"] = ("已作废（偏离闭包处置的既成事实）：补跑走替代 run，"
                               "stale 视图不重复处置")

    compared = {"design"} if design_now else set()
    if current_spec:
        for spec_key, dim, _ in _SPEC_COMPONENT_DIMS:
            if any(spec_key in (_spec_for(current_spec, r.get("design_run_id")) or {})
                   for r in runs.values()):
                compared.add(dim)
        if any("params" in (_spec_for(current_spec, r.get("design_run_id")) or {})
               for r in runs.values()):
            compared.add("params")
    all_dims = {"design", "code", "params", "config", "data", "env"}
    uncompared = sorted(all_dims - compared)
    summary = {"current": 0, "stale": 0, "voided": 0}
    for e in entries.values():
        summary[e["state"]] += 1
    return {
        "exec_id": exec_id,
        "generated_at": date,
        "design_current_hash": design_now,
        "design_note": design_note,
        "spec_source": spec_source or None,
        "compared_dimensions": sorted(compared),
        "uncompared_dimensions": uncompared,
        "runs": [entries[r] for r in sorted(entries)],
        "summary": summary,
    }


def render_stale_markdown(report: dict) -> str:
    """人读版 STALE_REPORT.md：三态总表 + stale 逐条触发维与补跑建议。"""
    s = report["summary"]
    lines = [
        f"# stale 预检清单 — {report['exec_id']}", "",
        f"> 生成于 {report['generated_at']}。只读视图：本报告不改变任何 "
        "run 状态；作废仍走 deviation 闭包流程，stale 只是开工前预检。",
        f"> 设计链：{report['design_note']}",
        f"> 已比对维度：{'、'.join(report['compared_dimensions']) or '（无）'}"
        f"；未比对维度：{'、'.join(report['uncompared_dimensions']) or '（无）'}"
        "（声明未覆盖的维不下结论）。", "",
        f"三态汇总：current {s['current']} · stale {s['stale']} · "
        f"voided {s['voided']}", "",
        "| run_id | 条目 | run 状态 | stale 判定 | 触发维 |",
        "|---|---|---|---|---|",
    ]
    for e in report["runs"]:
        dims = "、".join(d["dimension"] for d in e["stale_dimensions"]) or "—"
        lines.append(f"| {e['run_id']} | {e['design_run_id']} | "
                     f"{e['run_status']} | {e['state']} | {dims} |")
    stale = [e for e in report["runs"] if e["state"] == "stale"]
    if stale:
        lines += ["", "## stale 逐条（触发维与补跑建议）", ""]
        for e in stale:
            lines.append(f"### {e['run_id']}（条目 {e['design_run_id']}）")
            for d in e["stale_dimensions"]:
                anchor = (f"（出生锚 {d['run_anchor']}… ≠ 现行 "
                          f"{d['current_anchor']}…）"
                          if d.get("run_anchor") else "")
                lines.append(f"- {_DIM_LABELS.get(d['dimension'], d['dimension'])}"
                             f"：{d['detail']}{anchor}")
            lines.append(f"- 补跑建议：{e['advice']}")
            lines.append("")
    voided = [e for e in report["runs"] if e["state"] == "voided"]
    if voided:
        lines += ["## voided（既成事实，偏离闭包已处置）", ""]
        for e in voided:
            lines.append(f"- {e['run_id']}：作废于 {'、'.join(e['voided_by'])}")
        lines.append("")
    return "\n".join(lines)


def write_stale_reports(root: Path, exec_id: str, report: dict, *,
                        out_json: Path | None = None,
                        out_md: Path | None = None) -> tuple[Path, Path]:
    """落盘两份报告（默认 exec 包目录内 stale_report.json +
    STALE_REPORT.md）。这是 stale 命令唯一的写动作，且只写报告
    文件本身——不触碰包状态文件。"""
    d = exec_dir(root, exec_id)
    out_json = out_json or (d / "stale_report.json")
    out_md = out_md or (d / "STALE_REPORT.md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    out_md.write_text(render_stale_markdown(report), encoding="utf-8")
    return out_json, out_md

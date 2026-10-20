"""分析包的落盘结构：init 建骨架、load/save 读写文件群。

一个分析包 = 一个目录（权威源是结构化文件群，MD 是渲染）：
    analysis.yaml / verdicts.jsonl / spec_ledger.yaml / spec_results.jsonl
    conclusions.yaml / exploratory/exploratory.yaml
    audit.json + audit.md（intake 落盘）/ ANALYSIS_REPORT.md（渲染）
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import dump_jsonl, dump_yaml, load_structured, read_jsonl

FILES = {
    "analysis": "analysis.yaml",
    "verdicts": "verdicts.jsonl",
    "spec_ledger": "spec_ledger.yaml",
    "spec_results": "spec_results.jsonl",
    "conclusions": "conclusions.yaml",
    "exploratory": "exploratory/exploratory.yaml",
    "audit": "audit.json",
}


def pkg_path(root, name: str) -> Path:
    return Path(root) / name


def init_package(root, title: str = "") -> Path:
    """在 root 处建分析包骨架；analysis_id 取目录名。已存在关键文件则拒绝覆盖。"""
    root = Path(root)
    if (root / FILES["analysis"]).exists():
        raise FileExistsError(f"分析包已存在：{root / FILES['analysis']}")
    (root / "exploratory").mkdir(parents=True, exist_ok=True)
    analysis_id = root.name
    dump_yaml(root / FILES["analysis"],
              schema.new_analysis(analysis_id, title=title or analysis_id))
    dump_jsonl(root / FILES["verdicts"], [])
    dump_yaml(root / FILES["spec_ledger"], schema.new_spec_ledger())
    dump_jsonl(root / FILES["spec_results"], [])
    dump_yaml(root / FILES["conclusions"], schema.new_conclusions())
    dump_yaml(root / FILES["exploratory"], schema.new_exploratory())
    (root / "ANALYSIS_REPORT.md").write_text(
        f"# {analysis_id} 分析报告\n\n（尚未渲染：intake 后由 render 生成。）\n",
        encoding="utf-8")
    return root


def load_package(root) -> dict:
    """读整个分析包为 dict；缺文件记 None（校验器负责点名，不在这里抛）。"""
    root = Path(root)
    pkg = {"root": root}
    for key, name in FILES.items():
        p = root / name
        if not p.exists():
            pkg[key] = None
        elif name.endswith(".jsonl"):
            pkg[key] = read_jsonl(p)
        else:
            pkg[key] = load_structured(p)
    return pkg


def save_analysis(root, analysis: dict) -> None:
    dump_yaml(Path(root) / FILES["analysis"], analysis)


def save_ledger(root, ledger: dict) -> None:
    dump_yaml(Path(root) / FILES["spec_ledger"], ledger)


def save_conclusions(root, conclusions: dict) -> None:
    dump_yaml(Path(root) / FILES["conclusions"], conclusions)


def save_verdicts(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["verdicts"], rows)


def save_spec_results(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["spec_results"], rows)


def refresh_counts(analysis: dict, verdict_rows) -> dict:
    """汇总区计数由工具从现行判定行机械汇总，不许手填（草案 §2.1）。

    现行行 = 每条登记行在 verdicts.jsonl 中的最后一行（改判走 supersedes 链）。
    """
    current = {}
    for row in verdict_rows or []:
        current[row.get("registry_line_id")] = row
    counts = schema.empty_counts()
    for row in current.values():
        if row.get("verdict") in counts:
            counts[row["verdict"]] += 1
    snap = (analysis.get("registry_snapshot") or {}).get("line_ids") or []
    counts["total_lines"] = len(snap) if snap else len(current)
    analysis["counts"] = counts
    return counts


def current_verdicts(verdict_rows) -> dict:
    """登记行 id → 现行判定行（文件序最后一行）。"""
    current = {}
    for row in verdict_rows or []:
        current[row.get("registry_line_id")] = row
    return current


def assign_row_refs(rows):
    """按行内出现序回填 row_ref（<line>#v<n>）与 supersedes 链，供校验器核链。"""
    seen: dict[str, int] = {}
    last_ref: dict[str, str] = {}
    for row in rows:
        line = row.get("registry_line_id")
        seen[line] = seen.get(line, 0) + 1
        ref = f"{line}#v{seen[line]}"
        row["row_ref"] = ref
        if seen[line] > 1 and not row.get("supersedes"):
            row["supersedes"] = last_ref[line]
        last_ref[line] = ref
    return rows

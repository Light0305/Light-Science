"""Light-Journal-Select CLI：init / fingerprint / precedent /
add-candidate / verify / gate / report / validate / status /
decide / handoff。

所有命令输出 JSON；纪律错误逐项点名（gaps），不给整体式含糊失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import schema
from .decide import apply_decide
from .gate import apply_gate, checks_from_name_list, load_name_list
from .gates import GateError, require_selection
from .handoff import run_handoff
from .precedent import run_precedent
from .project import (
    find_candidate, init_package, new_candidate, save_selection,
)
from .report import run_report
from .util import load_structured, today
from .validate import validate_package
from .verify import apply_verification


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _apply_fingerprint(root, payload: dict) -> dict:
    selection = require_selection(root)
    if selection.get("status") != "draft":
        raise GateError([f"状态 {selection.get('status')} 不许再落指纹"
                         "（指纹只在 draft 段登记，后续修改走新一轮选刊）"])
    manuscript = payload.get("manuscript") or {}
    for field in ("abstract", "keywords"):
        if manuscript.get(field):
            selection["manuscript"][field] = manuscript[field]
    if manuscript.get("source_ref"):
        selection["manuscript"]["source_ref"] = manuscript["source_ref"]
    fingerprint = payload.get("fingerprint") or {}
    missing = [f for f in schema.FINGERPRINT_FIELDS
               if fingerprint.get(f) in (None, "")]
    if missing:
        raise GateError([f"指纹缺字段：{', '.join(missing)}"])
    selection["fingerprint"] = fingerprint
    queries = payload.get("queries") or []
    if not (2 <= len(queries) <= 3):
        raise GateError([f"判别性检索式须 2–3 条，实为 {len(queries)} 条"])
    selection["queries"] = queries
    constraints = payload.get("constraints") or {}
    for key, value in constraints.items():
        if key not in schema.CONSTRAINT_KEYS:
            raise GateError([f"未知约束键 {key!r}"])
        selection["constraints"][key] = value
    selection["constraints_confirmed"] = bool(
        payload.get("constraints_confirmed"))
    save_selection(root, selection)
    return {"selection_id": selection["selection_id"],
            "queries": queries,
            "constraints_confirmed": selection["constraints_confirmed"],
            "status": selection["status"]}


def _add_candidate(root, name, source, detail=None) -> dict:
    selection = require_selection(root)
    if selection.get("status") not in ("draft", "candidates_ready"):
        raise GateError([f"状态 {selection.get('status')} 不许新增候选"])
    if find_candidate(selection, name) is not None:
        raise GateError([f"候选 {name} 已在池中"])
    cand = new_candidate(name, source)
    cand["source_detail"] = detail
    selection.setdefault("candidates", []).append(cand)
    save_selection(root, selection)
    return {"candidate_id": cand["candidate_id"], "name": name,
            "source": source, "status": selection["status"]}


def _status(root) -> dict:
    selection = require_selection(root)
    tiers = {}
    for cand in selection.get("candidates") or []:
        if cand.get("tier"):
            tiers[cand["tier"]] = tiers.get(cand["tier"], 0) + 1
    return {"selection_id": selection.get("selection_id"),
            "status": selection.get("status"),
            "candidates": len(selection.get("candidates") or []),
            "excluded": len(selection.get("excluded") or []),
            "tiers": tiers,
            "decision": selection.get("decision"),
            "status_history": selection.get("status_history")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-journal-select", description="Light-Journal-Select 选刊包工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="新建选刊包骨架")
    p.add_argument("root")
    p.add_argument("--title", required=True)
    p.add_argument("--language", required=True, choices=schema.LANGUAGES,
                   help="稿件语言（按投稿方向定，影响候选池与目录核验）")
    p.add_argument("--type", default="research",
                   choices=schema.MANUSCRIPT_TYPES)

    p = sub.add_parser("fingerprint", help="落稿件指纹+检索式+约束")
    p.add_argument("root")
    p.add_argument("--file", required=True,
                   help="指纹 JSON：{manuscript, fingerprint, queries, constraints}")

    p = sub.add_parser("precedent", help="先例路：OpenAlex 实时统计入池")
    p.add_argument("root")

    p = sub.add_parser("add-candidate", help="检索补充/finder 带回候选登记")
    p.add_argument("root")
    p.add_argument("--name", required=True)
    p.add_argument("--source", required=True,
                   choices=["search", "finder_manual"])
    p.add_argument("--detail", default=None)

    p = sub.add_parser("verify", help="登记逐刊核验结果（纪律校验后落盘）")
    p.add_argument("root")
    p.add_argument("--file", required=True,
                   help="核验 JSON：[{candidate, source_status, metrics}]")

    p = sub.add_parser("gate", help="风险门：名单文件+附加核查记录")
    p.add_argument("root")
    p.add_argument("--name-list", default=None,
                   help="本地名单 CSV（stop-predatory 风格，可注入）")
    p.add_argument("--checks", default=None,
                   help="附加核查 JSON：{candidate: [check, ...]}")
    p.add_argument("--override", default=None,
                   help="准硬门放行 JSON：{candidate: 放行记录}")

    p = sub.add_parser("report", help="分档并渲染 SELECTION_REPORT.md")
    p.add_argument("root")

    p = sub.add_parser("validate", help="全量纪律校验")
    p.add_argument("root")

    p = sub.add_parser("status", help="状态摘要")
    p.add_argument("root")

    p = sub.add_parser("decide", help="定刊回填（gated → decided）")
    p.add_argument("root")
    p.add_argument("--candidate", required=True,
                   help="候选 candidate_id 或刊名（须在已过门池内）")
    p.add_argument("--by", default=None, help="定刊人（必填，处理器点名）")
    p.add_argument("--reason", default=None, help="定刊理由（必填）")
    p.add_argument("--date", default=None, help="定刊日期（缺省今日）")

    p = sub.add_parser("handoff",
                       help="定刊交接：journal/target/ + check-record 自检")
    p.add_argument("root")
    p.add_argument("--fields", default=None,
                   help="指南字段 JSON（B–I 组 + A 组版本字段，"
                        "读官网作者指南后填写）")
    p.add_argument("--files", default=None,
                   help="下载登记 JSON：[{kind, filename, source_url, "
                        "local_path?}]，无 local_path 或文件不存在 = "
                        "pending_download")
    p.add_argument("--write-root", default=None,
                   help="Light-Write 包路径：给出则以子进程调其 "
                        "check_template_record 做外部自检")
    p.add_argument("--guideline-version", default=None,
                   help="指南版本子目录名（缺省用交接日期）")
    p.add_argument("--date", default=None, help="交接日期（缺省今日）")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            sel = init_package(args.root, args.title, args.language,
                               manuscript_type=args.type)
            _print({"selection_id": sel["selection_id"],
                    "status": sel["status"], "language": args.language})
        elif args.cmd == "fingerprint":
            _print(_apply_fingerprint(args.root, load_structured(args.file)))
        elif args.cmd == "precedent":
            _print(run_precedent(args.root))
        elif args.cmd == "add-candidate":
            _print(_add_candidate(args.root, args.name, args.source,
                                  detail=args.detail))
        elif args.cmd == "verify":
            _print(apply_verification(args.root, load_structured(args.file)))
        elif args.cmd == "gate":
            selection = require_selection(args.root)
            checks: dict = {}
            if args.name_list:
                name_list = load_name_list(args.name_list)
                checks = checks_from_name_list(
                    selection.get("candidates") or [], name_list, today())
            if args.checks:
                for key, rows in (load_structured(args.checks) or {}).items():
                    cand = find_candidate(selection, key)
                    cid = cand["candidate_id"] if cand else key
                    checks.setdefault(cid, []).extend(rows)
            overrides = load_structured(args.override) if args.override else {}
            resolved = {}
            for key, ov in (overrides or {}).items():
                cand = find_candidate(selection, key)
                resolved[cand["candidate_id"] if cand else key] = ov
            _print(apply_gate(args.root, checks, overrides=resolved))
        elif args.cmd == "report":
            _print(run_report(args.root))
        elif args.cmd == "validate":
            report = validate_package(args.root)
            _print(report)
            return 0 if report["ok"] else 1
        elif args.cmd == "status":
            _print(_status(args.root))
        elif args.cmd == "decide":
            _print(apply_decide(args.root, args.candidate,
                                decided_by=args.by, reason=args.reason,
                                date_str=args.date))
        elif args.cmd == "handoff":
            fields = load_structured(args.fields) if args.fields else None
            file_specs = load_structured(args.files) if args.files else None
            _print(run_handoff(args.root, fields=fields,
                               file_specs=file_specs,
                               write_root=args.write_root,
                               guideline_version=args.guideline_version,
                               today_str=args.date))
    except (GateError, FileExistsError) as e:
        gaps = getattr(e, "gaps", None) or [str(e)]
        _print({"ok": False, "gaps": gaps})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

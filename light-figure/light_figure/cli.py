"""light-figure CLI：init / intake / validate / advance / report /
style build / produce / prompt build / reference add|accept /
redraw init|install|build|extract / audit run|audit-status|audit note /
provenance set|show / deliver。

所有命令输出 JSON；纪律错误逐项点名（gaps），不给整体式含糊失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import AuditError, run_audit, audit_status, \
    set_review_disposition
from .delivery import DeliveryError, generate_delivery, register_unfreeze
from .gates import GateError, advance, status_summary
from .intake import IntakeError, run_intake
from .produce import ProduceError, produce_data_figure
from .project import init_package, load_package, provenance_row
from .prompt import PromptError, build_prompt
from .provenance import ProvenanceError, provenance_history, \
    update_provenance_row
from .redraw import RedrawError, build_vsdx, extract_and_reconcile, \
    init_manifest, install_manifest
from .reference import ReferenceError, ACCEPTANCE_CHECKS, \
    accept_reference, register_reference
from .report import build_report
from .style import StyleError, build_style
from .validate import validate_package

_ERRORS = (IntakeError, GateError, FileExistsError, StyleError,
           ProduceError, PromptError, ReferenceError, RedrawError,
           AuditError, ProvenanceError, DeliveryError)


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-figure", description="light-figure 图包工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="新建图包骨架")
    p.add_argument("root")
    p.add_argument("--title", required=True)

    p = sub.add_parser("intake", help="承接 Write 图表清单或独立立项清单")
    p.add_argument("root")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--manifest", default=None,
                     help="Write figures_manifest.yaml 路径")
    src.add_argument("--standalone", default=None,
                     help="独立立项清单（YAML/JSON：{figures: [{fig_id, kind}]}）")
    p.add_argument("--journal-contract", default=None,
                   help="期刊图形合同登记文件（YAML/JSON），登记时先过数值校验")
    p.add_argument("--template-record-id", default=None,
                   help="目标刊模板记录 id（姊妹仓登记）")
    p.add_argument("--ai-policy", default=None,
                   help="目标刊 AI 政策快照文件（YAML/JSON）")
    p.add_argument("--by", default=None)

    p = sub.add_parser("validate", help="全量校验")
    p.add_argument("root")

    p = sub.add_parser("advance", help="状态机推进一段（逐项点名缺口）")
    p.add_argument("root")

    p = sub.add_parser("status", help="状态摘要")
    p.add_argument("root")

    p = sub.add_parser("report", help="刷新 FIGURE_REPORT.md（手工区保留）")
    p.add_argument("root")

    p = sub.add_parser("style", help="样式编译（期刊合同+色板登记→bundle）")
    style_sub = p.add_subparsers(dest="style_cmd", required=True)
    sp = style_sub.add_parser("build", help="编译并落盘 bundle/mplstyle/theme.R")
    sp.add_argument("root")

    p = sub.add_parser("produce", help="数据图生产（脚本→PDF+预览+量测+账）")
    p.add_argument("root")
    p.add_argument("fig_id")
    p.add_argument("--by", default=None)

    p = sub.add_parser("prompt", help="方法图提示词产物")
    prompt_sub = p.add_subparsers(dest="prompt_cmd", required=True)
    sp = prompt_sub.add_parser("build", help="生成/改版六段提示词产物")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--by", default=None)

    p = sub.add_parser("reference", help="参考图入包登记与验收")
    ref_sub = p.add_subparsers(dest="reference_cmd", required=True)
    sp = ref_sub.add_parser("add", help="参考图入包 + provenance 登记")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--image", required=True)
    sp.add_argument("--model-name", default=None)
    sp.add_argument("--model-version", default=None)
    sp.add_argument("--by", default=None)
    sp = ref_sub.add_parser("accept", help="参考图验收落字（约束 9 三项清单）")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--by", required=True)
    for check in ACCEPTANCE_CHECKS:
        sp.add_argument(f"--{check.replace('_', '-')}", action="store_true",
                        help=f"验收项 {check} 已逐项核对")

    p = sub.add_parser("redraw", help="Visio 重绘 manifest 与文件级构建")
    redraw_sub = p.add_subparsers(dest="redraw_cmd", required=True)
    sp = redraw_sub.add_parser("init", help="生成 manifest 骨架（标定待补）")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp = redraw_sub.add_parser("install", help="登记 manifest（全量契约校验）")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--manifest", required=True)
    sp = redraw_sub.add_parser("build", help="文件级从零构建 .vsdx")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--by", default=None)
    sp = redraw_sub.add_parser("extract", help="成品反抽清单并与 manifest 对账")
    sp.add_argument("root")
    sp.add_argument("fig_id")

    p = sub.add_parser("audit", help="审计引擎（七门）")
    audit_sub = p.add_subparsers(dest="audit_cmd", required=True)
    sp = audit_sub.add_parser("run", help="按线全跑审计门并落 audit/ 产物")
    sp.add_argument("root")
    sp.add_argument("--fig", default=None)
    sp = audit_sub.add_parser("note", help="给 REVIEW 门落处置理由")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--gate", required=True)
    sp.add_argument("--reason", required=True)

    p = sub.add_parser("audit-status", help="逐图审计新鲜度（FRESH/STALE）")
    p.add_argument("root")

    p = sub.add_parser("deliver", help="生成 exports/delivery.yaml"
                                       "（交付前账行复验 + 编号冻结）"
                                       "，或登记解冻")
    p.add_argument("root")
    p.add_argument("--by", default=None)
    p.add_argument("--unfreeze", action="store_true",
                   help="登记解冻（冻结后改图的前置登记，须 --reason）")
    p.add_argument("--reason", default=None,
                   help="解冻理由（留痕，--unfreeze 时必填）")

    p = sub.add_parser("provenance", help="一本账更新（append-only）与查看")
    prov_sub = p.add_subparsers(dest="provenance_cmd", required=True)
    sp = prov_sub.add_parser("set", help="更新账行字段（旧行哈希入 history）")
    sp.add_argument("root")
    sp.add_argument("fig_id")
    sp.add_argument("--set", action="append", required=True,
                    metavar="KEY=VALUE",
                    help="可重复；VALUE 按 JSON 解析，失败则按字符串")
    sp.add_argument("--by", default=None)
    sp = prov_sub.add_parser("show", help="查看账行与更新 history")
    sp.add_argument("root")
    sp.add_argument("fig_id", nargs="?", default=None)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            head = init_package(args.root, args.title)
            _print({"package_id": head["package_id"],
                    "status": head["status"]})
        elif args.cmd == "intake":
            _print(run_intake(
                args.root, manifest=args.manifest,
                standalone=args.standalone,
                journal_contract_file=args.journal_contract,
                template_record_id=args.template_record_id,
                ai_policy_file=args.ai_policy, by=args.by))
        elif args.cmd == "validate":
            report = validate_package(args.root)
            _print(report)
            return 0 if report["ok"] else 1
        elif args.cmd == "advance":
            result = advance(args.root)
            _print(result)
            return 0 if result["advanced"] else 1
        elif args.cmd == "status":
            _print(status_summary(args.root))
        elif args.cmd == "report":
            _print(build_report(args.root))
        elif args.cmd == "style":
            bundle = build_style(args.root)
            _print({"style_build_hash": bundle["style_build_hash"],
                    "journal": bundle.get("journal"),
                    "artifacts": ["data/styles/bundle.json",
                                  "data/styles/light.mplstyle",
                                  "data/styles/theme.R"]})
        elif args.cmd == "produce":
            _print(produce_data_figure(args.root, args.fig_id,
                                       by=args.by))
        elif args.cmd == "prompt":
            _print(build_prompt(args.root, args.fig_id, by=args.by))
        elif args.cmd == "reference":
            if args.reference_cmd == "add":
                _print(register_reference(
                    args.root, args.fig_id, args.image,
                    model_name=args.model_name,
                    model_version=args.model_version, by=args.by))
            else:
                checks = {c: bool(getattr(args, c))
                          for c in ACCEPTANCE_CHECKS}
                _print(accept_reference(args.root, args.fig_id,
                                        by=args.by, checks=checks))
        elif args.cmd == "redraw":
            if args.redraw_cmd == "init":
                manifest = init_manifest(args.root, args.fig_id)
                _print({"fig_id": args.fig_id,
                        "manifest": f"schematic/redraw/{args.fig_id}"
                                    ".manifest.json",
                        "status": manifest["status"]})
            elif args.redraw_cmd == "install":
                manifest = install_manifest(args.root, args.fig_id,
                                            args.manifest)
                _print({"fig_id": args.fig_id,
                        "status": manifest["status"],
                        "shapes": len(manifest.get("shapes") or [])})
            elif args.redraw_cmd == "build":
                _print(build_vsdx(args.root, args.fig_id, by=args.by))
            else:
                _print(extract_and_reconcile(args.root, args.fig_id))
        elif args.cmd == "audit":
            if args.audit_cmd == "run":
                _print(run_audit(args.root, fig_id=args.fig))
            else:
                _print(set_review_disposition(
                    args.root, args.fig_id, args.gate, args.reason))
        elif args.cmd == "audit-status":
            _print(audit_status(args.root))
        elif args.cmd == "deliver":
            if args.unfreeze:
                _print(register_unfreeze(args.root, args.reason,
                                         by=args.by))
            else:
                _print(generate_delivery(args.root, by=args.by))
        elif args.cmd == "provenance":
            if args.provenance_cmd == "set":
                updates = {}
                for item in args.set:
                    key, _, raw = item.partition("=")
                    updates[key.strip()] = _parse_value(raw)
                row = update_provenance_row(args.root, args.fig_id,
                                            updates, by=args.by)
                _print(row)
            else:
                pkg = load_package(Path(args.root))
                if args.fig_id:
                    _print({
                        "row": provenance_row(pkg["provenance"],
                                              args.fig_id),
                        "history": provenance_history(args.root,
                                                      args.fig_id),
                    })
                else:
                    _print(pkg["provenance"])
    except _ERRORS as e:
        gaps = getattr(e, "gaps", None) or [str(e)]
        _print({"ok": False, "gaps": gaps})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

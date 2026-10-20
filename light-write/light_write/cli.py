"""light-write CLI：init / intake / register-template / freeze-contract /
validate / advance / status / audit / disclose / review / revision /
figures / reverify-claim。

所有命令输出 JSON；纪律错误逐项点名（gaps），不给整体式含糊失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import schema
from .audit import AuditError, audit_status, reverify_claim, run_audit
from .disclose import DiscloseError, disclosures_status, generate_disclosures
from .figures import (
    FigureError, add_figure, check_figures, freeze_numbering, mark_delivered,
    set_caption, sync_intext_refs,
)
from .gates import GateError, advance, freeze_contract, status_summary
from .intake import (
    ContributionError, IntakeError, confirm_contribution, run_intake,
)
from .project import init_package
from .review import (
    ReviewError, import_review, prepare_review, record_review,
    record_unavailable,
)
from .revision import (
    RevisionError, add_comment, add_response, bind_revision, check_revision,
)
from .template_reg import TemplateError, register_template
from .util import load_structured
from .validate import validate_package


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="light-write", description="light-write 稿件包工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="新建稿件包骨架")
    p.add_argument("root")
    p.add_argument("--title", required=True)
    p.add_argument("--language", required=True, choices=schema.LANGUAGES,
                   help="稿件语言（按目标期刊定，一篇稿一个语言）")

    p = sub.add_parser("intake", help="承接 conclusion_card + verified 集")
    p.add_argument("root")
    p.add_argument("--conclusion-card", required=True)
    p.add_argument("--literature", required=True,
                   help="Literature verified 条目导出（候选池 JSONL / JSON 列表）")
    p.add_argument("--by", default=None)

    p = sub.add_parser("confirm-contribution",
                       help="用户签认主导贡献陈述，落回执（WRT-D04）")
    p.add_argument("root")
    p.add_argument("--by", required=True, help="签认人（用户本人）")
    p.add_argument("--statement", default=None,
                   help="签认文本（缺省取承接草案原文）")
    p.add_argument("--drift-note", default=None,
                   help="签认文本与草案不一致时必填：点名差异")

    p = sub.add_parser("register-template", help="登记目标刊模板核查记录")
    p.add_argument("root")
    p.add_argument("--record", required=True)

    p = sub.add_parser("freeze-contract", help="冻结验收合同")
    p.add_argument("root")

    p = sub.add_parser("validate", help="全量校验")
    p.add_argument("root")

    p = sub.add_parser("advance", help="状态机推进一段（逐项点名缺口）")
    p.add_argument("root")

    p = sub.add_parser("status", help="状态摘要")
    p.add_argument("root")

    p = sub.add_parser("audit", help="审计四门（产物落 audit/，绑稿件哈希）")
    p.add_argument("root")
    p.add_argument("--online-records", default=None,
                   help="在线权威记录 JSON：{entry_id: {exists, title, "
                        "authors, year, venue, doi, doi_resolves, ...}}；"
                        "缺省为离线（门一 honest-unverified）")
    p.add_argument("--relevance", default=None,
                   help="相关性判定 JSON：{entry_id: {verdict, disposition,"
                        " note, human_approved}}")
    p.add_argument("--support", default=None,
                   help="支撑五级判定 YAML/JSON（D-W07/W12）："
                        "{assessments: [{entry_id, claim_id, level, "
                        "verbatim_quote, rejection_reason}]}；缺省读 "
                        "audit/support_assessments.yaml")

    p = sub.add_parser("audit-status", help="审计产物状态（STALE 检出）")
    p.add_argument("root")

    p = sub.add_parser("tone", help="程式化核查（WRT-D01，advisory 只报不改）")
    p.add_argument("root")

    p = sub.add_parser("disclose", help="按刊生成 AI 披露并落锚")
    p.add_argument("root")

    p = sub.add_parser("disclose-status", help="披露齐备与新鲜度")
    p.add_argument("root")

    p = sub.add_parser("reverify-claim", help="主张改词后重验贴合度落字")
    p.add_argument("root")
    p.add_argument("--claim", required=True)
    p.add_argument("--by", default=None)

    p = sub.add_parser("review", help="跨模型复核子流程")
    review_sub = p.add_subparsers(dest="review_cmd", required=True)
    rp = review_sub.add_parser("prepare", help="生成自包含复核包")
    rp.add_argument("root")
    rp = review_sub.add_parser("record", help="落复核收据")
    rp.add_argument("root")
    rp.add_argument("--reviewer", required=True)
    rp.add_argument("--family", required=True)
    rp.add_argument("--outcome", default="agree")
    rp.add_argument("--notes", default=None)
    rp = review_sub.add_parser("import", help="外部判定回填")
    rp.add_argument("root")
    rp.add_argument("--from-json", required=True)
    rp = review_sub.add_parser("unavailable", help="落 REVIEW_UNAVAILABLE")
    rp.add_argument("root")
    rp.add_argument("--reason", default=None)

    p = sub.add_parser("revision", help="W7 返修子包")
    rev_sub = p.add_subparsers(dest="revision_cmd", required=True)
    rp = rev_sub.add_parser("add-comment", help="登记审稿意见")
    rp.add_argument("root")
    rp.add_argument("--reviewer", required=True)
    rp.add_argument("--text", required=True)
    rp.add_argument("--category", default="major",
                    choices=schema.REVISION_CATEGORIES)
    rp.add_argument("--claims", default="")
    rp.add_argument("--sections", default="")
    rp = rev_sub.add_parser("respond", help="登记逐条回复")
    rp.add_argument("root")
    rp.add_argument("--comment", required=True)
    rp.add_argument("--decision", required=True,
                    choices=schema.REVISION_DECISIONS)
    rp.add_argument("--rationale", required=True)
    rp.add_argument("--anchors", default="",
                    help="改动锚点，逗号分隔 file:marker 对")
    rp = rev_sub.add_parser("check", help="双向对账 + STALE 检出")
    rp.add_argument("root")
    rp = rev_sub.add_parser("bind", help="resubmit 检查并生成回复信")
    rp.add_argument("root")

    p = sub.add_parser("terms", help="术语账校验（D-W02）")
    p.add_argument("root")

    p = sub.add_parser("allocation", help="正文分配纪律校验（D-W01）")
    p.add_argument("root")

    p = sub.add_parser("checklist", help="投稿检查清单工具")
    cl_sub = p.add_subparsers(dest="checklist_cmd", required=True)
    cp = cl_sub.add_parser("add-stats", help="加入统计报告审计底线条目（D-W14）")
    cp.add_argument("root")

    p = sub.add_parser("figures", help="图表回填对账与编号冻结")
    fig_sub = p.add_subparsers(dest="figures_cmd", required=True)
    fp = fig_sub.add_parser("add", help="登记图表")
    fp.add_argument("root")
    fp.add_argument("--id", required=True)
    fp.add_argument("--kind", default="figure", choices=schema.FIGURE_KINDS)
    fp = fig_sub.add_parser("sync", help="从正文回填 intext_refs")
    fp.add_argument("root")
    fp = fig_sub.add_parser("caption", help="登记图注（落哈希）")
    fp.add_argument("root")
    fp.add_argument("--id", required=True)
    fp.add_argument("--text", required=True)
    fp = fig_sub.add_parser("delivered", help="标记交付/回填")
    fp.add_argument("root")
    fp.add_argument("--id", required=True)
    fp.add_argument("--source-ref", required=True)
    fp.add_argument("--source-hash", required=True)
    fp.add_argument("--backfill", action="store_true")
    fp = fig_sub.add_parser("check", help="三方对账（只判不改）")
    fp.add_argument("root")
    fp = fig_sub.add_parser("freeze", help="编号冻结（--renumber 全量重编）")
    fp.add_argument("root")
    fp.add_argument("--renumber", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            ms = init_package(args.root, args.title, args.language)
            _print({"manuscript_id": ms["manuscript_id"], "status": ms["status"],
                    "language": ms["language"]})
        elif args.cmd == "intake":
            _print(run_intake(args.root, args.conclusion_card,
                              args.literature, by=args.by))
        elif args.cmd == "confirm-contribution":
            _print(confirm_contribution(
                args.root, args.by, statement=args.statement,
                drift_note=args.drift_note))
        elif args.cmd == "register-template":
            _print(register_template(args.root, args.record))
        elif args.cmd == "freeze-contract":
            _print(freeze_contract(args.root))
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
        elif args.cmd == "audit":
            online = load_structured(args.online_records) \
                if args.online_records else None
            relevance = load_structured(args.relevance) \
                if args.relevance else None
            support = None
            if getattr(args, "support", None):
                data = load_structured(args.support) or {}
                support = {}
                for row in data.get("assessments") or []:
                    support[row.get("entry_id") or row.get("key")] = row
            report = run_audit(args.root, online_records=online,
                               relevance=relevance, support=support)
            _print(report)
            return 0 if report["overall"] == "pass" else 1
        elif args.cmd == "audit-status":
            _print(audit_status(args.root))
        elif args.cmd == "tone":
            from .tone import ToneError, run_tone_check
            try:
                tone_report = run_tone_check(args.root)
            except ToneError as e:
                _print({"ok": False, "gaps": e.gaps})
                return 1
            _print({"advisory": True, "blocking": False,
                    "findings": tone_report["counts"]["total"],
                    "by_rule": tone_report["counts"]["by_rule"],
                    "report_file": "audit/tone_report.json"})
        elif args.cmd == "disclose":
            _print(generate_disclosures(args.root))
        elif args.cmd == "disclose-status":
            _print(disclosures_status(args.root))
        elif args.cmd == "reverify-claim":
            _print(reverify_claim(args.root, args.claim, by=args.by))
        elif args.cmd == "review":
            if args.review_cmd == "prepare":
                _print(prepare_review(args.root))
            elif args.review_cmd == "record":
                _print(record_review(args.root, args.reviewer, args.family,
                                     outcome=args.outcome, notes=args.notes))
            elif args.review_cmd == "import":
                _print(import_review(args.root, args.from_json))
            elif args.review_cmd == "unavailable":
                _print(record_unavailable(args.root, reason=args.reason))
        elif args.cmd == "revision":
            if args.revision_cmd == "add-comment":
                _print(add_comment(
                    args.root, args.reviewer, args.text,
                    category=args.category,
                    claim_ids=[s for s in args.claims.split(",") if s],
                    section_ids=[s for s in args.sections.split(",") if s]))
            elif args.revision_cmd == "respond":
                anchors = []
                for pair in (args.anchors.split(",") if args.anchors else []):
                    f, _, marker = pair.partition(":")
                    anchors.append({"file": f.strip(),
                                    "marker": marker.strip()})
                _print(add_response(args.root, args.comment, args.decision,
                                    args.rationale, change_anchors=anchors))
            elif args.revision_cmd == "check":
                result = check_revision(args.root)
                _print(result)
                return 0 if result["ok"] else 1
            elif args.revision_cmd == "bind":
                _print(bind_revision(args.root))
        elif args.cmd == "terms":
            from .ledger import terminology_check
            from .project import load_package as _lp
            issues = terminology_check(_lp(Path(args.root)))
            _print({"ok": not any(i["level"] == "error" for i in issues),
                    "issues": issues})
            return 0 if not any(i["level"] == "error" for i in issues) else 1
        elif args.cmd == "allocation":
            from .ledger import allocation_check
            from .project import load_package as _lp
            issues = allocation_check(_lp(Path(args.root)))
            _print({"ok": not any(i["level"] == "error" for i in issues),
                    "issues": issues})
            return 0 if not any(i["level"] == "error" for i in issues) else 1
        elif args.cmd == "checklist":
            from .project import load_package as _lp, save_checklist
            pkg = _lp(Path(args.root))
            items = (pkg["checklist"] or {}).get("items") or []
            have = {i.get("item_id") for i in items}
            added = []
            for spec in schema.STATS_REPORTING_CHECKLIST:
                if spec["item_id"] in have:
                    continue
                items.append({
                    "item_id": spec["item_id"], "tier": "baseline",
                    "requirement": spec["requirement"],
                    "anchor": {"kind": "section", "section": spec["section"],
                               "marker": "AUTHOR_INPUT_NEEDED"},
                    "stage": "initial", "applicability": "required",
                    "status": "open",
                    "source": "light-write D-W14 (nature-statistics)"})
                added.append(spec["item_id"])
            save_checklist(args.root, {"items": items})
            _print({"added": added, "total_items": len(items)})
        elif args.cmd == "figures":
            if args.figures_cmd == "add":
                _print(add_figure(args.root, args.id, kind=args.kind))
            elif args.figures_cmd == "sync":
                _print(sync_intext_refs(args.root))
            elif args.figures_cmd == "caption":
                _print(set_caption(args.root, args.id, args.text))
            elif args.figures_cmd == "delivered":
                _print(mark_delivered(args.root, args.id, args.source_ref,
                                      args.source_hash,
                                      backfill=args.backfill))
            elif args.figures_cmd == "check":
                result = check_figures(args.root)
                _print(result)
                return 0 if result["ok"] else 1
            elif args.figures_cmd == "freeze":
                _print(freeze_numbering(args.root, renumber=args.renumber))
    except (IntakeError, ContributionError, TemplateError, GateError,
            FileExistsError, AuditError, DiscloseError, ReviewError,
            RevisionError, FigureError) as e:
        gaps = getattr(e, "gaps", None) or [str(e)]
        _print({"ok": False, "gaps": gaps})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""light-patent CLI：init / audit / sources / scan-code / mine /
disclosure / channels / query / search / d1 / claims / text /
numerals / gaps / strip / check / redteam / oa / amend /
meeting / file / priority / worth-it / radar / validate / status。

所有命令输出 JSON；纪律错误逐项点名（gaps），不给整体式失败。
payload 类命令从 --payload 指向的 JSON/YAML 文件读入。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import (channels, check, draft, execsearch, intake, ledger,
               novelty, oa, radar, render)
from .project import PatentError, init_package, load_case
from .util import load_structured
from .validate import validate_package


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _payload(args) -> dict:
    if not args.payload:
        raise PatentError(["缺 --payload 文件"])
    data = load_structured(args.payload)
    if not isinstance(data, dict):
        raise PatentError(["payload 须为对象（JSON/YAML 文件）"])
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="light-patent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("root")
    p.add_argument("--title", required=True)
    p.add_argument("--ai-related", action="store_true")

    p = sub.add_parser("audit"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("sources"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("scan-code"); p.add_argument("root"); p.add_argument("--repo", required=True)
    p = sub.add_parser("mine"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("disclosure"); p.add_argument("root"); p.add_argument("--from", dest="src", required=True)

    p = sub.add_parser("channels"); p.add_argument("root", nargs="?")
    p = sub.add_parser("channel-enable"); p.add_argument("root")
    p.add_argument("--channel", required=True); p.add_argument("--payload")
    p = sub.add_parser("query"); p.add_argument("root"); p.add_argument("--payload")

    p = sub.add_parser("search"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("search-exec"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("d1"); p.add_argument("root"); p.add_argument("--payload")

    p = sub.add_parser("claims"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("text"); p.add_argument("root")
    p.add_argument("--kind", choices=["specification", "abstract"], required=True)
    p.add_argument("--from", dest="src", required=True)
    p = sub.add_parser("numerals"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("gaps"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("strip"); p.add_argument("root")
    p = sub.add_parser("render-docx"); p.add_argument("root")

    p = sub.add_parser("check"); p.add_argument("root")
    p = sub.add_parser("redteam"); p.add_argument("root"); p.add_argument("--payload")

    p = sub.add_parser("oa"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("amend"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("meeting"); p.add_argument("root")

    p = sub.add_parser("file"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("priority"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("worth-it"); p.add_argument("root"); p.add_argument("--payload")
    p = sub.add_parser("deadlines"); p.add_argument("root")

    p = sub.add_parser("radar"); p.add_argument("--add", dest="payload")
    p = sub.add_parser("validate"); p.add_argument("root")
    p = sub.add_parser("status"); p.add_argument("root")

    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except PatentError as exc:
        _print({"ok": False, "gaps": exc.gaps})
        return 2


def _dispatch(args) -> int:
    cmd = args.cmd
    if cmd == "init":
        case = init_package(args.root, args.title,
                            ai_related=args.ai_related)
        _print({"ok": True, "case_id": case["case_id"], "status": case["status"]})
    elif cmd == "audit":
        _print(intake.run_audit(args.root, _payload(args)))
    elif cmd == "sources":
        _print(intake.register_sources(args.root, _payload(args)))
    elif cmd == "scan-code":
        _print(intake.scan_code(args.root, args.repo))
    elif cmd == "mine":
        _print(intake.register_candidates(args.root, _payload(args)))
    elif cmd == "disclosure":
        _print(intake.write_disclosure(args.root, args.src))
    elif cmd == "channels":
        _print({"channels": channels.channel_registry(),
                "enabled": channels.load_channel_state(args.root) if args.root else {}})
    elif cmd == "channel-enable":
        _print(channels.enable_channel(args.root, args.channel,
                                       _payload(args) if args.payload else {}))
    elif cmd == "query":
        case = load_case(args.root)
        payload = _payload(args)
        _print({"query": channels.build_query(
            case, ipc_codes=payload.get("ipc_codes"),
            means_phrases=payload.get("means_phrases"))})
    elif cmd == "search":
        _print(novelty.register_search(args.root, _payload(args)))
    elif cmd == "search-exec":
        _print(execsearch.execute_search(args.root, _payload(args)))
    elif cmd == "d1":
        _print(novelty.lock_d1(args.root, _payload(args)))
    elif cmd == "claims":
        _print(draft.register_claims(args.root, _payload(args)))
    elif cmd == "text":
        _print(draft.register_text(args.root, args.kind, args.src))
    elif cmd == "numerals":
        _print(draft.register_numerals(args.root, _payload(args)))
    elif cmd == "gaps":
        _print(draft.register_gaps(args.root, _payload(args)))
    elif cmd == "strip":
        _print(draft.strip_filing(args.root))
    elif cmd == "render-docx":
        _print(render.render_docx(args.root))
    elif cmd == "check":
        _print(check.run_check(args.root))
    elif cmd == "redteam":
        _print(check.register_redteam(args.root, _payload(args)))
    elif cmd == "oa":
        _print(oa.register_office_action(args.root, _payload(args)))
    elif cmd == "amend":
        _print(oa.register_amendment(args.root, _payload(args)))
    elif cmd == "meeting":
        _print(oa.export_meeting_questions(args.root))
    elif cmd == "file":
        _print(ledger.register_filing(args.root, _payload(args)))
    elif cmd == "priority":
        _print(ledger.register_priority(args.root, _payload(args)))
    elif cmd == "worth-it":
        _print(ledger.set_worth_it(args.root, _payload(args)))
    elif cmd == "deadlines":
        _print({"deadlines": ledger.refresh_deadlines(args.root)})
    elif cmd == "radar":
        if args.payload:
            data = load_structured(args.payload)
            _print(radar.add_entry(data))
        else:
            radar.seed_if_missing()
            print(radar.render_brief())
    elif cmd == "validate":
        result = validate_package(args.root)
        _print(result)
        return 0 if result["ok"] else 1
    elif cmd == "status":
        case = load_case(args.root)
        _print({
            "case_id": case["case_id"], "title": case["title"],
            "status": case["status"], "blocked": case.get("blocked"),
            "degraded": case.get("degraded"),
            "deadlines": ledger.load_ledger(args.root).get("deadlines"),
            "disclaimers": case.get("disclaimers"),
        })
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""light-crawler CLI。

命令面（规程见 SKILL.md）：
  init        建工作区（项目根 data-sources/ 口径，拒绝覆盖）
  register    登记/更新目标（--file 登记 YAML；先过校验再落盘）
  targets     列目标（通道/用途/预检状态/熔断一行一个）
  precheck    跑合规预检（目标级检查 + 项目锁 + 拒绝留痕）
  confirm     高危通道预检的人工确认（--by 具名，S4）
  gate-check  对外预检门接口的命令行形态（--json；供其他包调用）
  fetch       guard 全过才执行的采集 run（无任何绕过旗标）
  import      人工导出后登记导入（S2 正当替代；--note/--by 必填）
  unblock     熔断恢复（--by 具名 + --reason）
  refusals    拒绝留痕清单（可查询，含原因与规则出处）
  events      事件账（可按目标过滤）
  status      工作区状态一行摘要
  validate    登记自洽 + provenance 哈希重算校验
  render      渲染 CRAWL_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import fetch as fetch_mod
from . import precheck as precheck_mod
from . import project, render, schema
from .util import load_yaml
from .validate import validate_workspace


def _fail(exc) -> int:
    if isinstance(exc, project.WorkspaceError):
        for p in exc.problems:
            print(f"错误：{p}")
    elif isinstance(exc, fetch_mod.Refusal):
        for r in exc.reasons:
            print(f"拒绝：{r}")
    else:
        print(f"错误：{exc}")
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="light-crawler")
    parser.add_argument("--root", default=".",
                        help="工作区目录（项目根 data-sources/）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("--project", required=True)
    p = sub.add_parser("register")
    p.add_argument("--file", required=True); p.add_argument("--update", action="store_true")
    sub.add_parser("targets")
    p = sub.add_parser("precheck"); p.add_argument("--target", required=True)
    p = sub.add_parser("confirm")
    p.add_argument("--target", required=True); p.add_argument("--by", required=True)
    p.add_argument("--note", default="")
    p = sub.add_parser("gate-check")
    p.add_argument("--target", required=True); p.add_argument("--json", action="store_true")
    p = sub.add_parser("fetch")
    p.add_argument("--target", required=True)
    p.add_argument("--url", action="append", default=[])
    p.add_argument("--refetch-seen", action="store_true",
                   help="重取已见指纹（只影响增量跳过，不绕任何合规门）")
    p = sub.add_parser("import")
    p.add_argument("--target", required=True); p.add_argument("--file", required=True)
    p.add_argument("--note", required=True); p.add_argument("--by", required=True)
    p = sub.add_parser("unblock")
    p.add_argument("--target", required=True); p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    sub.add_parser("refusals")
    p = sub.add_parser("events"); p.add_argument("--target", default=None)
    sub.add_parser("status")
    sub.add_parser("validate")
    sub.add_parser("render")

    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.cmd == "init":
            header = project.init_workspace(root, args.project)
            print(f"工作区已建：{root}（workspace_id {header['workspace_id']}）")
        elif args.cmd == "register":
            reg = load_yaml(args.file)
            if reg is None:
                print(f"错误：登记文件不可解析：{args.file}")
                return 2
            project.load_header(root)
            project.register_target(root, reg, update=args.update)
            print(f"目标已登记：{reg['target_id']}（{reg['channel']}）")
        elif args.cmd == "targets":
            for reg in project.list_targets(root):
                cur = precheck_mod.current_precheck(root, reg["target_id"])
                state = project.load_state(root, reg["target_id"])
                print(f"{reg['target_id']}\t{reg['channel']}\t"
                      f"{reg['purpose_kind']}\t预检 {cur['status']}"
                      f"\t熔断 {'是' if state.get('circuit_broken') else '否'}")
        elif args.cmd == "precheck":
            rec = precheck_mod.run_precheck(root, args.target)
            print(f"预检 {rec['precheck_id']}：{rec['status']}"
                  f"（ready_to_fetch={rec['ready_to_fetch']}）")
            for r in rec["blocked_reasons"]:
                print(f"  blocked：{r}")
            for m in rec["missing"]:
                print(f"  缺项：{m}")
            rate = rec["checks"]["rate"]
            print(f"  有效间隔：{rate['effective_interval_sec']}s"
                  f"（裁决输入 {rate['inputs']}，定版并发 "
                  f"{schema.REQUIRED_CONCURRENCY}）")
            if rec["status"] == "pending_confirmation":
                print("  高危通道：须具名 confirm 后才生效（S4）")
            if rec["status"] == "blocked":
                return 2
        elif args.cmd == "confirm":
            row = precheck_mod.confirm_precheck(
                root, args.target, args.by, args.note)
            print(f"已确认：{row['precheck_id']}（{args.by}）")
        elif args.cmd == "gate-check":
            verdict = fetch_mod.gate_check(root, args.target)
            if args.json:
                print(json.dumps(verdict, ensure_ascii=False, indent=1))
            else:
                print(f"{verdict['target_id']}：ready={verdict['ready']}"
                      f"（{verdict['status']}）")
                for r in verdict["reasons"]:
                    print(f"  {r}")
            return 0 if verdict["ready"] else 2
        elif args.cmd == "fetch":
            rec = fetch_mod.fetch_run(
                root, args.target, urls=args.url or None,
                refetch_seen=args.refetch_seen)
            print(f"run {rec['run_id']}：{rec['status']}（请求 "
                  f"{rec['requested']}、落盘 {rec['stored']}、未变更 "
                  f"{rec['not_modified']}、重复 {rec['duplicates']}）")
            for e in rec["errors"]:
                print(f"  {e}")
            if rec["refused"]:
                return 2
        elif args.cmd == "import":
            prov = fetch_mod.import_file(
                root, args.target, args.file, args.note, args.by)
            print(f"已导入：{prov['prov_id']}（sha256 {prov['sha256'][:12]}…）")
        elif args.cmd == "unblock":
            fetch_mod.unblock_target(root, args.target, args.by, args.reason)
            print(f"已解除熔断：{args.target}（{args.by}）")
        elif args.cmd == "refusals":
            rows = [e for e in project.read_events(root)
                    if e["type"] in schema.REFUSAL_EVENT_TYPES]
            for e in rows:
                print(f"[{e['at']}] {e['type']}\t{e.get('target_id') or '-'}\t"
                      f"{e.get('detail')}")
            print(f"共 {len(rows)} 条拒绝留痕")
        elif args.cmd == "events":
            rows = project.read_events(root)
            if args.target:
                rows = [e for e in rows if e.get("target_id") == args.target]
            for e in rows:
                print(f"[{e['at']}] {e['type']}\t{e.get('target_id') or '-'}\t"
                      f"{e.get('detail')}")
        elif args.cmd == "status":
            header = project.load_header(root)
            print(f"status: {header.get('status')}（项目 "
                  f"{header.get('project')}，目标 "
                  f"{len(project.list_targets(root))} 个，熔断 "
                  f"{header.get('circuit_broken_targets') or '无'}）")
        elif args.cmd == "validate":
            problems = validate_workspace(root)
            if problems:
                for p_ in problems:
                    print(f"错误：{p_}")
                return 2
            print("validate: ok（登记自洽、provenance 哈希全对）")
        elif args.cmd == "render":
            dest = render.write_report(root)
            print(f"报告已渲染：{dest}")
    except (project.WorkspaceError, fetch_mod.Refusal) as exc:
        return _fail(exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())

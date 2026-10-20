"""light-leader CLI：init / status / route / registry 四个子命令。

纪律：status、route、registry 全只读（不写项目任何文件）；init 只在
空位建骨架、拒绝覆盖。输出中文、缺失逐项点名；失败 exit 1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import registry as registry_mod
from . import route as route_mod
from . import scan as scan_mod
from . import scaffold
from .layout import PIPELINE, STAGES


def _fail(msg: str) -> int:
    print(f"失败：{msg}")
    return 1


def cmd_init(args) -> int:
    root = Path(args.path)
    name = args.name or root.resolve().name
    try:
        head = scaffold.init_project(root, name, title=args.title or "",
                                     goal=args.goal or "")
    except FileExistsError as exc:
        return _fail(str(exc))
    print(f"项目骨架已生成：{root}（登记头 {head.name}，项目名 {name}）")
    print("阶段目录：" + "、".join(
        STAGES[s]["dir"] for s in PIPELINE + ("memory",))
        + "、journal/target")
    print("下一步：在各阶段目录内用对应技能的命令建包；"
          "随时 `light-leader status .` 看全项目状态。")
    return 0


def _print_stage(sid: str, ss: dict) -> None:
    spec = STAGES[sid]
    label = f"{sid}（light-{sid}）" if sid != "journal-select" else \
        "journal-select（light-journal-select，write 前置扩展位）"
    if not ss["found"]:
        print(f"[{label}] 未发现登记头（{spec['carrier']}）")
        return
    if sid == "literature":
        for it in ss["items"]:
            counts = "、".join(f"{k}x{v}" for k, v in
                               it["status_counts"].items()) or "无篇目"
            ev = it.get("evidence_rows")
            print(f"[{label}] {it['path']}：篇目 {it['papers']}（{counts}），"
                  f"证据行 {ev if ev is not None else '未发现证据表'}")
            if it.get("error"):
                print(f"    注：{it['error']}")
        return
    if sid == "memory":
        for it in ss["items"]:
            c = it["counts"]
            print(f"[{label}] {it['path']}：对象 {c['objects']}、事件 "
                  f"{c['events']}、事实 {c['facts']}、关系 {c['relations']}；"
                  f"registry-view.json {'已导出' if it['registry_view'] else '未导出'}")
        return
    for it in ss["items"]:
        st = it["status"] if it["status"] is not None else "（缺失）"
        term = "（终态）" if it["status"] in spec["terminal"] else ""
        print(f"[{label}] {it['path']}：status={st}{term}")
        if it.get("error"):
            print(f"    注：{it['error']}")
        for g in it.get("gates", []):
            print(f"    硬门标记：{g['field']} = {g['value']}")
        if it.get("blocked_reason"):
            print(f"    blocked 原因：{it['blocked_reason']}")


def cmd_status(args) -> int:
    root = Path(args.path)
    if not root.is_dir():
        return _fail(f"项目目录不存在：{root}")
    report = scan_mod.scan_project(root)
    head = scaffold.load_project_head(root)
    title = (head or {}).get("title") or root.resolve().name
    print(f"项目状态：{title}（{root}）")
    if head is None:
        print("注：无 project.yaml 登记头，按文件扫描报告（不影响只读扫描）")
    for sid in PIPELINE + ("memory",):
        _print_stage(sid, report["stages"][sid])
    return 0


def cmd_route(args) -> int:
    root = Path(args.path)
    if not root.is_dir():
        return _fail(f"项目目录不存在：{root}")
    result = route_mod.route(scan_mod.scan_project(root))
    if result["gates"]:
        print("[硬门] 以下阶段被复核硬门拦住：")
        for g in result["gates"]:
            print(f"- {g['stage']}：{g['gate']}（登记头证据："
                  + "；".join(g["evidence"]) + "）")
            print(f"  {g['fix']}")
    if result["next"]:
        n = result["next"]
        print(f"[下一步] {n['action']} —— {n['reason']}")
    for note in result["notes"]:
        print(f"[提示] {note}")
    if result["done"]:
        print("[收官] 流水线各阶段均已达终态：稿件可投稿；其后若收到"
              "真实审稿意见，返修走 light-write 的 W7（不归 light-review）；"
              "全程产物由 light-memory 持续收编。")
    return 0


def cmd_registry(args) -> int:
    root = Path(args.path)
    if not root.is_dir():
        return _fail(f"项目目录不存在：{root}")
    try:
        path, view = registry_mod.load_view(root)
    except registry_mod.RegistryError as exc:
        return _fail(str(exc))
    print(f"来源：{path}")
    print(registry_mod.render_view(view))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-leader",
        description="light-leader：Light-Science 总控（薄编排：骨架/状态/路由/注册视图）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="生成标准项目骨架")
    p.add_argument("path")
    p.add_argument("--name", default="")
    p.add_argument("--title", default="")
    p.add_argument("--goal", default="")
    p.set_defaults(fn=cmd_init)

    for name, fn, help_ in (
            ("status", cmd_status, "只读扫描逐阶段状态"),
            ("route", cmd_route, "按规则表给下一步建议与硬门点名"),
            ("registry", cmd_registry, "渲染对象注册统一视图")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("path")
        p.set_defaults(fn=fn)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

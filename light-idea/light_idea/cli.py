"""light-idea CLI（一期 + 二期 + 三期）。

命令：
  init     建项目骨架（idea-stage/ + cards/ + novelty/ + 索引）
  new      建一张 draft 想法卡（idea.yaml + card.md）
  validate 校验一张卡的结构合法性（逐条报错，exit 1 表示不合法）
  advance  按状态机验门推进状态（不过门逐条报错，不许静默放行）
  dedup    离线去重：疑似重复对 + 去重率报告（只报告，不删卡）
  list     列出项目内全部想法卡与状态
  novelty prepare  facet 查新取证：逐面构式 → 四源实查 → 证据包落盘
  novelty verdict  判定落卡：跨模型判定 + 逐面举证写入查新证据区
  chain    演进链取材：按种子 DOI 拉引文邻居落盘成链素材（三期）
  duel     两两对决记录：结果追加进双方卡 aux.pairwise_record（三期）
  rank     对决汇总：胜率矩阵 + Elo 风格参考分（辅助信号，三期）
  export   交接三件套：定版卡 → exports/<idea_id>/（三期）
  report   项目级报告：生成/刷新 IDEA_REPORT.md（三期）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import chain as chain_mod
from . import dedup as dedup_mod
from . import duel as duel_mod
from . import export as export_mod
from . import novelty as novelty_mod
from .gates import GateError, advance as gate_advance
from .project import (
    init_project,
    list_cards,
    load_card,
    new_card,
    refresh_index,
    save_card,
)
from .schema import ALL_STATES, OPERATORS, VERDICTS, validate_card
from .util import today


def _fail(msg: str) -> int:
    print(f"错误：{msg}", file=sys.stderr)
    return 1


def cmd_init(args) -> int:
    root = Path(args.dir)
    try:
        init_project(root, args.direction)
    except FileExistsError as e:
        return _fail(str(e))
    print(f"项目已建：{root}（方向：{args.direction}）")
    return 0


def cmd_new(args) -> int:
    root = Path(args.project)
    try:
        card = new_card(root, args.title, args.one_liner, args.operator,
                        provenance_note=args.provenance)
    except FileExistsError as e:
        return _fail(str(e))
    print(f"已建想法卡：{card['idea_id']}（status=draft）")
    print("提示：空卡只是骨架，补齐 facets/body/provenance 后 validate 才会通过。")
    return 0


def cmd_validate(args) -> int:
    root = Path(args.project)
    try:
        card = load_card(root, args.idea_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    errors = validate_card(card)
    if errors:
        print(f"{args.idea_id} 结构不合法（{len(errors)} 条）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"{args.idea_id} 结构合法（status={card.get('status')}）")
    return 0


def cmd_advance(args) -> int:
    root = Path(args.project)
    try:
        card = load_card(root, args.idea_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        gate_advance(card, args.to, by=args.by, date=today(), note=args.note or "")
    except GateError as e:
        print(f"推进被拦：{args.idea_id} → {args.to}（{len(e.errors)} 条未过门）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    save_card(root, card)
    refresh_index(root)
    print(f"已推进：{args.idea_id} → {args.to}")
    return 0


def cmd_dedup(args) -> int:
    root = Path(args.project)
    cards = list_cards(root)
    if len(cards) < 2:
        print(f"卡数 {len(cards)} < 2，无需去重。")
        return 0
    pairs = dedup_mod.find_pairs(cards, threshold=args.threshold)
    report = dedup_mod.dedup_report(cards, pairs, args.threshold)
    print(f"去重报告（阈值 {args.threshold}，字符 n-gram TF-IDF，离线）：")
    print(f"  生成总数：{report['total_generated']}")
    print(f"  疑似重复对：{report['suspected_pairs']}")
    for p in pairs:
        print(f"    - {p['a']} × {p['b']}：{p['similarity']}")
    print(f"  重复簇：{len(report['clusters'])} 个 {report['clusters']}")
    print(f"  若裁决全部成立：冗余 {report['redundant_if_all_confirmed']} 张，"
          f"存活 {report['survivors_if_all_confirmed']} 张，"
          f"去重率 {report['dedup_rate_if_all_confirmed']}")
    if report["empty_text_cards"]:
        print(f"  ⚠️ 空文本卡（生成事故，请点名处理）：{report['empty_text_cards']}")
    print("  注：去重只报告、供人工裁决，不自动删卡。")
    if not args.no_write:
        best = dedup_mod.most_similar_map(cards, pairs)
        for c in cards:
            info = best.get(c["idea_id"])
            c["dedup"] = {
                "checked": True,
                "max_similarity": info["max_similarity"] if info else 0.0,
                "most_similar_to": info["most_similar_to"] if info else None,
                "adjudication": (c.get("dedup") or {}).get("adjudication"),
            }
            c["updated"] = today()
            save_card(root, c)
        print("  已回写各卡 dedup 字段（checked=true）。裁决请在卡上改 adjudication。")
    out = root / "idea-stage" / "dedup_report.md"
    lines = [f"# 去重报告（{today()}）", "",
             f"- 生成总数：{report['total_generated']}",
             f"- 阈值：{report['threshold']}",
             f"- 疑似重复对：{report['suspected_pairs']}",
             f"- 重复簇：{report['clusters']}",
             f"- 若裁决全部成立：存活 {report['survivors_if_all_confirmed']}，"
             f"去重率 {report['dedup_rate_if_all_confirmed']}", "",
             "## 疑似重复对（按相似度降序）", ""]
    for p in pairs:
        lines.append(f"- {p['a']} × {p['b']}：{p['similarity']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  报告已落盘：{out}")
    return 0


def cmd_novelty_prepare(args) -> int:
    root = Path(args.project)
    try:
        card = load_card(root, args.idea_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        summary = novelty_mod.prepare(
            root, card, per_query=args.per_query,
            interleave_sleep=args.sleep)
    except novelty_mod.NoveltyError as e:
        print(f"查新取证失败：{args.idea_id}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    save_card(root, card)
    refresh_index(root)
    st = summary["source_status"]
    print(f"查新证据包已落盘：novelty/{args.idea_id}/"
          f"（evidence.jsonl / queries.json / pool_report.md）")
    print(f"  查询式：{summary['query_count']} 条（逐面短语式+关键词式 + 整想法召回）")
    print(f"  证据池：{summary['pool_size']} 条（原始命中 {summary['raw_source_hits']}，去重后）")
    for source in novelty_mod.SOURCES:
        s = st[source]
        state = "可用" if s["ok"] else "不可用"
        print(f"  - {novelty_mod.SOURCE_LABELS[source]}：{state}"
              f"（命中 {s['hits']}，失败 {len(s['errors'])} 条）")
    if summary["blind_spots"]:
        print("  已知盲区（已写入卡的 search_scope 与 pool_report.md）：")
        for spot in summary["blind_spots"]:
            print(f"    · {spot}")
    if not summary["any_source_ok"]:
        print("错误：四源全部不可用，证据池为空——本次查新未成立，"
              "不许在此基础上落判定。", file=sys.stderr)
        return 1
    print("  下一步：把证据包交给另一模型家族判定，再用 novelty verdict 落卡。")
    return 0


def cmd_novelty_verdict(args) -> int:
    root = Path(args.project)
    try:
        card = load_card(root, args.idea_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    data: dict = {
        "verdict": args.verdict,
        "judge_model": args.judge_model,
        "judge_family": args.judge_family,
        "executor_model": args.executor_model,
        "executor_family": args.executor_family,
        "caution_reason": args.caution_reason or "",
        "review_unavailable": bool(args.review_unavailable),
        "closest_works": [],
        "named_paper": None,
    }
    if args.closest_file:
        try:
            payload = json.loads(
                Path(args.closest_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return _fail(f"closest 文件不可读/不是合法 JSON：{e}")
        if isinstance(payload, list):
            data["closest_works"] = payload
        elif isinstance(payload, dict):
            data["closest_works"] = payload.get("closest_works") or []
            data["named_paper"] = payload.get("named_paper")
        else:
            return _fail("closest 文件须为 JSON 对象（含 closest_works / "
                         "named_paper）或 closest_works 列表")
    try:
        record = novelty_mod.apply_verdict(root, card, data)
    except novelty_mod.NoveltyError as e:
        print(f"判定被拒：{args.idea_id}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    save_card(root, card)
    refresh_index(root)
    print(f"判定已落卡：{args.idea_id} → {record['verdict']}"
          f"（verdict_id {record['receipt']['verdict_id']}，"
          f"review_status {record['review_status']}）")
    print(f"  最接近工作 {len(record['closest_works'])} 条（均已核对在证据池中）")
    if record["review_status"] == "REVIEW_UNAVAILABLE":
        print("  ⚠️ 降级通道：本次无跨模型判定收据，卡可继续流转，"
              "但定版门会拦截——恢复后须补跨模型判定。")
    if record["verdict"] == "ABANDON":
        named = record.get("named_paper") or {}
        print("  ⚠️ ABANDON 不许留在主线：请转 killed 并点名在先论文——")
        print("     在卡的 kill 记录中填写：source=novelty_named_paper、"
              "failure_class（二分类）、reason（撞车说明），且")
        print(f"     named_paper 须带 paper_id/doi（本次点名："
              f"{named.get('title') or named.get('doi') or named.get('paper_id')}），"
              f"然后运行 advance --to killed。")
    else:
        print(f"  下一步：advance {args.idea_id} --to novelty_checked 过查新门。")
    return 0


def cmd_chain(args) -> int:
    root = Path(args.project)
    if not (root / "project.yaml").exists():
        return _fail(f"项目不存在：{root}（先用 init 建项目）")
    try:
        summary = chain_mod.fetch_chain(
            root, args.seed_doi, chain_id=args.chain_id,
            per_direction=args.per_direction)
    except chain_mod.ChainError as e:
        print(f"链素材抓取失败（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    refresh_index(root)
    print(f"链素材已落盘：chains/{summary['chain_id']}/"
          f"（seed.json / neighbors.jsonl / chain_report.md）")
    print(f"  本跳种子：{summary['seed_doi']}，新增邻居 "
          f"{summary['new_neighbors']} 条"
          f"（参考文献 {summary['counts']['references']}、"
          f"施引 {summary['counts']['cited_by']}），"
          f"盘上共 {summary['total_neighbors_on_disk']} 条")
    for source in chain_mod.SOURCES:
        s = summary["source_status"][source]
        state = (f"可用（邻居 {s['neighbors']}）" if s["ok"]
                 else f"失败（{s['error']}）")
        print(f"  - {chain_mod.SOURCE_LABELS[source]}：{state}")
    print("  下一步（智能体规程，不由工具代劳）：按 SKILL 第 9 节从邻居里"
          "逐跳选 3–5 个节点抽四元组建链，再在链尾/断点处生成候选并落卡；"
          "继续生长用同一 chain_id 对选定节点 DOI 再跑 chain。")
    return 0


def cmd_duel(args) -> int:
    root = Path(args.project)
    try:
        card_a = load_card(root, args.a)
        card_b = load_card(root, args.b)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        record = duel_mod.record_duel(
            card_a, card_b, args.winner, by=args.by, note=args.note or "")
    except duel_mod.DuelError as e:
        print(f"对决记录被拒（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    save_card(root, card_a)
    save_card(root, card_b)
    refresh_index(root)
    outcome = ("平局" if record["winner"] == "draw"
               else f"胜者 {record['winner']}")
    print(f"对决已记录：{record['a']} × {record['b']} → {outcome}"
          f"（已写入双方卡 aux.pairwise_record，属辅助信号："
          f"暂定，未经执行验证，不作淘汰依据）")
    return 0


def cmd_rank(args) -> int:
    root = Path(args.project)
    cards = list_cards(root)
    rank = duel_mod.rank_project(root, cards)
    if not rank["matches"]:
        print("暂无对决记录：先用 duel 落对决，再汇总。")
        return 0
    print(f"对决汇总（{len(rank['matches'])} 场；相对判断只定先后不定生死）：")
    print("  胜率矩阵（行 对 列：胜/负/平）：")
    ids = [s["idea_id"] for s in rank["standings"]]
    for a in ids:
        cells = []
        for b in ids:
            if a == b:
                cells.append("—")
            else:
                cell = rank["matrix"].get(a, {}).get(b)
                cells.append(
                    f"{cell['win']}/{cell['loss']}/{cell['draw']}"
                    if cell else "·")
        print(f"    {a}：{'  '.join(cells)}")
    print("  Elo 风格参考分（辅助字段，暂定，未经执行验证）：")
    for s in rank["standings"]:
        print(f"    {s['idea_id']}：{s['elo']}（胜 {s['win']} 负 {s['loss']} "
              f"平 {s['draw']}，胜率 {s['win_rate']}）")
    for cyc in rank["cycles"]:
        print(f"  ⚠️ 循环胜负：{'、'.join(cyc)} 之间对决分不开"
              f"（循环胜负），Elo 在这些卡之间只作并列参考。")
    print("  注：分数不作淘汰依据——淘汰只凭查新 ABANDON / 试点 "
          "negative / 客观不可行三类证据。")
    if not args.no_write:
        by_id = {c["idea_id"]: c for c in cards}
        for s in rank["standings"]:
            card = by_id[s["idea_id"]]
            card.setdefault("aux", {})["elo"] = s["elo"]
            card["updated"] = today()
            save_card(root, card)
        print("  已回写各卡 aux.elo（参考分，暂定）。")
    return 0


def cmd_export(args) -> int:
    root = Path(args.project)
    try:
        card = load_card(root, args.idea_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        result = export_mod.export_card(root, card)
    except export_mod.ExportError as e:
        print(f"导出被拒：{args.idea_id}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}" if not err.startswith("  ·") else f"  {err}")
        return 1
    refresh_index(root)
    print(f"交接三件套已产出：exports/{args.idea_id}/"
          f"（定版级别 {result['finalization_level']}）")
    print(f"  - design_handoff.md：{result['design_handoff']}")
    print(f"  - idea_card.json：{result['idea_card_json']}")
    print(f"  - memory_export.jsonl：{result['memory_export']}"
          f"（方向层条目，供 light-memory 日后收编）")
    return 0


def cmd_report(args) -> int:
    root = Path(args.project)
    if not (root / "project.yaml").exists():
        return _fail(f"项目不存在：{root}（先用 init 建项目）")
    summary = export_mod.build_report(root)
    counts = summary["status_counts"]
    print(f"IDEA_REPORT.md 已刷新：{summary['report_path']}")
    print(f"  全池 {summary['total']} 张："
          + ("、".join(f"{s} × {n}" for s, n in counts.items()) or "（空）"))
    print(f"  定版 {len(summary['finalized'])} 张、killed "
          f"{len(summary['killed'])} 张、对决 {summary['duel_matches']} 场")
    if summary["dedup"]:
        d = summary["dedup"]
        print(f"  去重：疑似对 {d['suspected_pairs']}、"
              f"若裁决全成立去重率 {d['dedup_rate_if_all_confirmed']}")
    for cyc in summary["cycles"]:
        print(f"  ⚠️ 循环胜负：{'、'.join(cyc)} 分不开（已在报告中标注）")
    return 0


def cmd_list(args) -> int:
    root = Path(args.project)
    cards = list_cards(root)
    if not cards:
        print("（暂无想法卡）")
        return 0
    for c in cards:
        print(f"{c['idea_id']}\t{c.get('status')}\t{c.get('operator')}\t{c.get('title')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="light-idea", description="light-idea 想法卡系统（v1.0）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="建项目骨架")
    p.add_argument("dir", help="项目目录")
    p.add_argument("--direction", required=True, help="研究方向名")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("new", help="建一张 draft 想法卡")
    p.add_argument("project", help="项目目录")
    p.add_argument("--title", required=True)
    p.add_argument("--one-liner", required=True, dest="one_liner")
    p.add_argument("--operator", default="manual", choices=OPERATORS)
    p.add_argument("--provenance", default=None, help="生成出处说明（或后续在卡上填 chain_id 等）")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("validate", help="校验想法卡结构")
    p.add_argument("project")
    p.add_argument("idea_id")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("advance", help="验门推进状态")
    p.add_argument("project")
    p.add_argument("idea_id")
    p.add_argument("--to", required=True, choices=ALL_STATES, dest="to")
    p.add_argument("--by", default="light-idea advance", help="推进者（模型/人）")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("dedup", help="离线去重报告")
    p.add_argument("project")
    p.add_argument("--threshold", type=float, default=dedup_mod.DEFAULT_THRESHOLD)
    p.add_argument("--no-write", action="store_true", help="不回写 dedup 字段")
    p.set_defaults(func=cmd_dedup)

    p = sub.add_parser("list", help="列出全部想法卡")
    p.add_argument("project")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("novelty", help="facet 查新子流程（二期）")
    nsub = p.add_subparsers(dest="novelty_cmd", required=True)

    np_ = nsub.add_parser("prepare", help="查新取证：构式→四源实查→证据包落盘")
    np_.add_argument("project")
    np_.add_argument("idea_id")
    np_.add_argument("--per-query", type=int, default=novelty_mod.DEFAULT_PER_QUERY,
                     help="每条查询式每源取回条数（默认 10）")
    np_.add_argument("--sleep", type=float, default=0.0,
                     help="每次请求后的间隔秒数（源限流时调大，如 0.3）")
    np_.set_defaults(func=cmd_novelty_prepare)

    nv = nsub.add_parser("verdict", help="判定落卡（跨模型 + 逐面举证）")
    nv.add_argument("project")
    nv.add_argument("idea_id")
    nv.add_argument("--verdict", required=True, choices=list(VERDICTS))
    nv.add_argument("--judge-model", default=None, help="判定者模型名")
    nv.add_argument("--judge-family", default=None,
                    help="判定者模型家族（缺省由模型名推断）")
    nv.add_argument("--executor-model", default=None, help="执行者模型名")
    nv.add_argument("--executor-family", default=None,
                    help="执行者模型家族（缺省由模型名推断）")
    nv.add_argument("--caution-reason", default=None,
                    help="PROCEED_WITH_CAUTION 必填：delta 薄在哪")
    nv.add_argument("--closest-file", default=None,
                    help="JSON 文件：{closest_works: [...], named_paper: {...}}"
                         "（closest_works 每条须带 collided_facets 与 delta）")
    nv.add_argument("--review-unavailable", action="store_true",
                    help="显式降级：外部判定确实不可得（落 REVIEW_UNAVAILABLE，"
                         "卡可流转但不许定版）")
    nv.set_defaults(func=cmd_novelty_verdict)

    p = sub.add_parser("chain", help="演进链取材：种子 DOI 的引文邻居落盘成链素材（三期）")
    p.add_argument("project")
    p.add_argument("--seed-doi", required=True, dest="seed_doi",
                   help="本跳展开的种子/节点 DOI")
    p.add_argument("--chain-id", default=None, dest="chain_id",
                   help="链 ID（缺省由根种子 DOI 生成；生长时指回既有链，"
                        "--seed-doi 给被展开的节点 DOI）")
    p.add_argument("--per-direction", type=int,
                   default=chain_mod.DEFAULT_PER_DIRECTION, dest="per_direction",
                   help="每方向每源取回条数（默认 25）")
    p.set_defaults(func=cmd_chain)

    p = sub.add_parser("duel", help="两两对决记录（写入双方卡 aux.pairwise_record）")
    p.add_argument("project")
    p.add_argument("--a", required=True, help="对决卡 A 的 idea_id")
    p.add_argument("--b", required=True, help="对决卡 B 的 idea_id")
    p.add_argument("--winner", required=True,
                   help="胜者 idea_id，或 draw")
    p.add_argument("--by", default="light-idea duel",
                   help="判定者（模型/人；规程要求与生成者不同模型家族）")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_duel)

    p = sub.add_parser("rank", help="对决汇总：胜率矩阵 + Elo 参考分（辅助信号）")
    p.add_argument("project")
    p.add_argument("--no-write", action="store_true",
                   help="不回写 aux.elo")
    p.set_defaults(func=cmd_rank)

    p = sub.add_parser("export", help="交接三件套（只对定版卡；未定版拒绝并说明缺口）")
    p.add_argument("project")
    p.add_argument("idea_id")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("report", help="生成/刷新 IDEA_REPORT.md")
    p.add_argument("project")
    p.set_defaults(func=cmd_report)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

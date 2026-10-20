"""命令行入口：python -m light_literature <命令> ...

命令：init / ingest / triage / parse（产品解析，Doc2X 轨，收费，
先估算页数并确认额度）/ verify / export-content-list /
translate-scaffold / notes / evidence add|correct / glossary add /
find / verify-identity / screen（screen check 做校验）/ matrix /
metadata-backfill（元数据回填）/ claim-locate / claim-check（主张核查）/
ask（问语料）
（参数见各子命令 --help）。

产品解析只有双轨：Doc2X 轨（parse）与模型直读轨（无代码，由执行
agent 按 SKILL.md §5 直接读 PDF 撰写四件套）。开发期的本地文本层
抽取 / 对照打分工具属于研究存档，不在本产品发布中。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ask as ask_mod
from . import claimcheck as claimcheck_mod
from . import contentlist as contentlist_mod
from . import evidence as evidence_mod
from . import find as find_mod
from . import glossary as glossary_mod
from . import metadata as metadata_mod
from . import notes as notes_mod
from . import parse as parse_mod
from . import project as project_mod
from . import translate as translate_mod
from . import triage as triage_mod
from . import verify as verify_mod


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _resolve_paper(arg: str) -> tuple[Path, str]:
    """translate-scaffold / notes 收 <paper_dir> 路径：校验并反推
    (project_dir, paper_id)。paper_dir 须形如 <project>/Literature/<paper_id>。"""
    pdir = Path(arg)
    if not (pdir / "paper.yaml").exists():
        raise FileNotFoundError(f"不是有效的论文目录（缺 paper.yaml）：{pdir}")
    return pdir.parent.parent, pdir.name


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="light-literature",
        description="light-literature：论文四件套生产线（v1.0）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="创建项目级 Literature 结构")
    p_init.add_argument("project_dir")

    p_ing = sub.add_parser("ingest", help="单篇 PDF 入库")
    p_ing.add_argument("project_dir")
    p_ing.add_argument("pdf")
    p_ing.add_argument("--doi", default=None)
    p_ing.add_argument("--title", default=None)
    p_ing.add_argument("--source-version", default="preprint",
                       choices=["version_of_record", "preprint", "abstract_only"])
    p_ing.add_argument("--source", default=None, help="来源说明（如 arXiv:1706.03762）")
    p_ing.add_argument("--backfill-online", action="store_true",
                       help="入库回填时联网查 Crossref（默认只跑本地源）")

    p_meta = sub.add_parser(
        "metadata-backfill",
        help="元数据回填（LIT-D03）：逐字段标来源/核实状态写入 paper.yaml")
    p_meta.add_argument("paper_dir", help="单篇论文目录（含 paper.yaml）")
    p_meta.add_argument("--online", action="store_true",
                        help="联网查 Crossref 按 DOI 回填（默认只跑本地源）")
    p_meta.add_argument("--confirm", action="store_true",
                        help="用户已逐字核对原文首页：已填字段标 verified")

    p_cloc = sub.add_parser(
        "claim-locate",
        help="主张证据定位（LIT-D04）：在已入库语料块级定位候选锚点，"
             "无命中如实回 not_mentioned")
    p_cloc.add_argument("project_dir")
    p_cloc.add_argument("--claim", required=True)
    p_cloc.add_argument("--paper", default=None,
                        help="只在指定论文内定位（默认全语料）")
    p_cloc.add_argument("--top", type=int, default=10)

    p_cchk = sub.add_parser(
        "claim-check",
        help="主张支持核查（LIT-D04）：三值判定经机械校验后追加 "
             "claim_support.jsonl（只增）")
    p_cchk.add_argument("project_dir")
    p_cchk.add_argument("--paper", required=True)
    p_cchk.add_argument("--claim", required=True)
    p_cchk.add_argument("--verdict", required=True,
                        choices=list(claimcheck_mod.VERDICTS))
    p_cchk.add_argument("--anchors", default=None,
                        help="逗号分隔的证据锚点（如 S001,S002）")
    p_cchk.add_argument("--note", default=None)

    p_ask = sub.add_parser(
        "ask", help="问语料（LIT-D01）：块级检索 + 引用白名单 + "
                    "证据不足固定拒答，产物落 问答记录/")
    p_ask.add_argument("project_dir")
    p_ask.add_argument("--question", required=True)
    p_ask.add_argument("--answer", default=None,
                       help="依据命中块写出的答案（须同时给 --cite）")
    p_ask.add_argument("--cite", action="append", default=None,
                       help="引用锚点：paper_id#S001 或裸锚点，可多次")
    p_ask.add_argument("--max-citations", type=int,
                       default=ask_mod.DEFAULT_MAX_CITATIONS)

    for name, helptext in (("triage", "逐页分诊"),
                           ("verify", "锚点校验 + 图注配对 + 译文对齐校验"),
                           ("export-content-list",
                            "导出 content_list.json（MinerU Content List V1 对齐）")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("project_dir")
        p.add_argument("paper_id")

    for name, helptext in (("translate-scaffold", "生成 原文_中文翻译.md 脚手架（块级同 ID 对齐）"),
                           ("notes", "生成 阅读笔记.md（速读检查点 + 精读 16 节骨架）")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("paper_dir", help="单篇论文目录（含 paper.yaml）")

    p_ev = sub.add_parser("evidence", help="证据行：只增追加 / 纠错追加")
    ev_sub = p_ev.add_subparsers(dest="ev_cmd", required=True)
    p_ev_add = ev_sub.add_parser("add", help="向 证据表.jsonl 追加一条证据行")
    p_ev_add.add_argument("project_dir")
    p_ev_add.add_argument("--paper", required=True)
    p_ev_add.add_argument("--finding", required=True)
    p_ev_add.add_argument("--page", required=True, type=int)
    p_ev_add.add_argument("--statistic", default=None)
    p_ev_add.add_argument("--quote", default=None, help="直接引文，上限一句")
    p_ev_add.add_argument("--supports-claim", default=None)
    p_ev_add.add_argument("--claim-strength", default=None,
                          choices=list(evidence_mod.CLAIM_STRENGTHS))
    p_ev_add.add_argument("--limitations", default=None, help="仅作者自述局限")
    p_ev_add.add_argument("--note-anchor", default=None)
    p_ev_corr = ev_sub.add_parser("correct", help="追加纠错行（带 corrects，原行不动）")
    p_ev_corr.add_argument("project_dir")
    p_ev_corr.add_argument("--corrects", required=True, help="被纠错的 evidence_id")
    p_ev_corr.add_argument("--finding", default=None)
    p_ev_corr.add_argument("--page", default=None, type=int)
    p_ev_corr.add_argument("--statistic", default=None)
    p_ev_corr.add_argument("--quote", default=None)
    p_ev_corr.add_argument("--supports-claim", default=None)
    p_ev_corr.add_argument("--claim-strength", default=None,
                           choices=list(evidence_mod.CLAIM_STRENGTHS))
    p_ev_corr.add_argument("--limitations", default=None)
    p_ev_corr.add_argument("--note-anchor", default=None)

    p_gl = sub.add_parser("glossary", help="术语账本维护")
    gl_sub = p_gl.add_subparsers(dest="gl_cmd", required=True)
    p_gl_add = gl_sub.add_parser("add", help="向 术语账本.md 追加术语（重复拒绝）")
    p_gl_add.add_argument("project_dir")
    p_gl_add.add_argument("--term", required=True)
    p_gl_add.add_argument("--zh", required=True)
    p_gl_add.add_argument("--note", default=None)

    p_find = sub.add_parser(
        "find", help="Find 线：多源检索 + 三层去重对账，产出候选池与检索报告")
    p_find.add_argument("project_dir")
    p_find.add_argument("--query", action="append", required=True,
                        help="查询式，可多次给出（多视角检索）")
    p_find.add_argument("--sources", default=None,
                        help="逗号分隔的源列表，默认全部："
                             + ",".join(find_mod.DEFAULT_SOURCES))
    p_find.add_argument("--per-source", type=int, default=10,
                        help="每源每查询返回上限")
    p_find.add_argument("--mailto", default=None,
                        help="礼貌池邮箱（写入 User-Agent 与源参数）")

    p_vi = sub.add_parser(
        "verify-identity",
        help="Find 线：候选池逐条身份核实 + 独立撤稿检查（只打标不删条）")
    p_vi.add_argument("project_dir")
    p_vi.add_argument("--limit", type=int, default=None,
                      help="只核实前 N 条（默认全部）")
    p_vi.add_argument("--mailto", default=None)

    p_screen = sub.add_parser(
        "screen", help="Find 线：生成 粗筛表.csv（判定先行，人工填）")
    p_screen.add_argument("project_dir")
    p_screen_check = sub.add_parser(
        "screen-check", help="Find 线：校验粗筛表（撤稿硬规则等）")
    p_screen_check.add_argument("project_dir")

    p_matrix = sub.add_parser(
        "matrix", help="Find 线：生成 研究证据矩阵.md（成稿层硬规则在此执行）")
    p_matrix.add_argument("project_dir")

    p_parse = sub.add_parser(
        "parse", help="产品解析（Doc2X 轨）：整篇送 Doc2X 并锚点化为 "
                      "source_map.json + 原文.md（按页收费，先估算并确认额度）；"
                      "Doc2X 未配置/失败时置 awaiting_model_direct 走模型直读轨，"
                      "不回退本地抽取")
    p_parse.add_argument("paper_dir", help="单篇论文目录（含 paper.yaml）")
    p_parse.add_argument("--backend", default="doc2x",
                         help="解析后端（产品路径只有 doc2x；local 是研究/对照"
                              "工具，不在产品发布中）")


    # `screen check <project_dir>` 语法糖：argparse 无法在同一命令下同时
    # 容纳位置参数与子命令，这里把 check 改写为独立命令 screen-check。
    if argv and argv[0] == "screen" and len(argv) > 1 and argv[1] == "check":
        argv = ["screen-check", *argv[2:]]

    args = parser.parse_args(argv)

    try:
        if args.cmd == "init":
            lit = project_mod.init_project(Path(args.project_dir))
            _print({"literature_dir": str(lit)})
            return 0
        if args.cmd == "ingest":
            info = project_mod.ingest(
                Path(args.project_dir), Path(args.pdf), doi=args.doi,
                title=args.title, source_version=args.source_version,
                source=args.source, backfill_online=args.backfill_online)
            _print(info)
            return 0
        if args.cmd == "metadata-backfill":
            project_dir, paper_id = _resolve_paper(args.paper_dir)
            _print(metadata_mod.backfill_metadata(
                project_dir, paper_id, online=args.online,
                confirm=args.confirm))
            return 0
        if args.cmd == "claim-locate":
            _print(claimcheck_mod.locate_claim(
                Path(args.project_dir), args.claim, paper_id=args.paper,
                top=args.top))
            return 0
        if args.cmd == "claim-check":
            anchors = ([a.strip() for a in args.anchors.split(",")
                        if a.strip()] if args.anchors else [])
            _print(claimcheck_mod.record_claim_check(
                Path(args.project_dir), args.paper, args.claim,
                args.verdict, anchors=anchors, note=args.note))
            return 0
        if args.cmd == "ask":
            _print(ask_mod.ask(
                Path(args.project_dir), args.question, answer=args.answer,
                citations=args.cite, max_citations=args.max_citations))
            return 0
        if args.cmd == "triage":
            _print(triage_mod.triage(Path(args.project_dir), args.paper_id))
            return 0
        if args.cmd == "verify":
            report = verify_mod.verify(Path(args.project_dir), args.paper_id)
            _print(report)
            return 0 if report["ok"] else 1
        if args.cmd == "export-content-list":
            _print(contentlist_mod.export_content_list(
                Path(args.project_dir), args.paper_id))
            return 0
        if args.cmd == "translate-scaffold":
            project_dir, paper_id = _resolve_paper(args.paper_dir)
            _print(translate_mod.translate_scaffold(project_dir, paper_id))
            return 0
        if args.cmd == "notes":
            project_dir, paper_id = _resolve_paper(args.paper_dir)
            _print(notes_mod.generate_notes(project_dir, paper_id))
            return 0
        if args.cmd == "evidence" and args.ev_cmd == "add":
            row = evidence_mod.add_evidence(
                Path(args.project_dir), args.paper, args.finding, args.page,
                statistic=args.statistic, quote=args.quote,
                supports_claim=args.supports_claim,
                claim_strength=args.claim_strength,
                limitations=args.limitations, note_anchor=args.note_anchor)
            _print(row)
            return 0
        if args.cmd == "evidence" and args.ev_cmd == "correct":
            row = evidence_mod.correct_evidence(
                Path(args.project_dir), args.corrects, finding=args.finding,
                page=args.page, statistic=args.statistic, quote=args.quote,
                supports_claim=args.supports_claim,
                claim_strength=args.claim_strength,
                limitations=args.limitations, note_anchor=args.note_anchor)
            _print(row)
            return 0
        if args.cmd == "glossary" and args.gl_cmd == "add":
            _print(glossary_mod.add_term(
                Path(args.project_dir), args.term, args.zh, note=args.note))
            return 0
        if args.cmd == "find":
            sources = (tuple(s.strip() for s in args.sources.split(",")
                             if s.strip())
                       if args.sources else find_mod.DEFAULT_SOURCES)
            _print(find_mod.find(
                Path(args.project_dir), args.query, sources=sources,
                per_source=args.per_source, mailto=args.mailto))
            return 0
        if args.cmd == "verify-identity":
            _print(find_mod.verify_identity(
                Path(args.project_dir), limit=args.limit,
                mailto=args.mailto))
            return 0
        if args.cmd == "screen":
            _print(find_mod.generate_screen(Path(args.project_dir)))
            return 0
        if args.cmd == "screen-check":
            report = find_mod.check_screen(Path(args.project_dir))
            _print(report)
            return 0 if report["ok"] else 1
        if args.cmd == "matrix":
            _print(find_mod.generate_matrix(Path(args.project_dir)))
            return 0
        if args.cmd == "parse":
            _resolve_paper(args.paper_dir)  # 校验目录合法性
            _print(parse_mod.parse(Path(args.paper_dir),
                                   backend=args.backend))
            return 0
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        # RuntimeError 含 Doc2X 的 Doc2XError / EngineUnavailableError：
        # 消息已在适配器内脱敏，可直接呈现（含 uid 供续查，勿盲目重跑）
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())

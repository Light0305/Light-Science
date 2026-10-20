"""light-software-copyright CLI：SC0-SC7 全链命令。

纪律：每个命令先验状态与前置，缺项逐项点名、失败 exit 1；确认类动作
只登记用户回执（绑内容哈希），工具不代用户确认、不代签署。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import case as case_mod
from . import release, render, schema, select as select_mod, snapshot
from .case import CaseError
from .util import dump_json, load_structured, sha256_text


def _fail(msg: str) -> int:
    print(f"失败：{msg}")
    return 1


def _root(args) -> Path:
    return Path(args.case)


def cmd_init(args) -> int:
    root = Path(args.path)
    try:
        head = case_mod.init_case(root, title=args.title or "")
    except CaseError as exc:
        return _fail(str(exc))
    print(f"案件已建：{root}（登记头 copyright.yaml，状态 {head['status']}）")
    print("下一步：备好 facts 文件后 set-facts 导入登记事实。")
    return 0


def cmd_set_facts(args) -> int:
    root = _root(args)
    try:
        case = case_mod.load_case(root)
        if case["status"] not in ("draft", "correcting"):
            raise CaseError([f"当前状态 {case['status']} 不许改事实"
                             "（改事实须在 draft，或补正回路 correcting）"])
        facts = load_structured(Path(args.from_file)) or {}
        gaps = case_mod.validate_facts(facts)
        if gaps:
            raise CaseError(gaps)
        case_mod.save_facts(root, facts)
        case_mod.log_tool_use(root, "user", "set-facts", "facts",
                              f"来源 {args.from_file}")
    except CaseError as exc:
        return _fail(str(exc))
    for w in case_mod.facts_warnings(facts):
        print(f"警告（不拦）：{w}")
    print("登记事实已导入（尚未确认）。下一步：confirm-facts 由用户确认。")
    return 0


def cmd_confirm_facts(args) -> int:
    root = _root(args)
    try:
        facts = case_mod.load_facts(root)
        gaps = case_mod.validate_facts(facts)
        if gaps:
            raise CaseError(gaps)
        fp = case_mod.facts_fingerprint(facts)
        case_mod.record_confirmation(root, "facts", "facts", fp,
                                     note=args.note or "")
        case = case_mod.load_case(root)
        case_mod.set_status(root, case, "facts_confirmed")
    except CaseError as exc:
        return _fail(str(exc))
    print("登记事实已确认（回执绑指纹，事实再改即失效）。下一步：freeze。")
    return 0


def cmd_freeze(args) -> int:
    root = _root(args)
    try:
        case = case_mod.load_case(root)
        if case["status"] != "facts_confirmed":
            raise CaseError([f"当前状态 {case['status']}，freeze 须在 "
                             "facts_confirmed 后"])
        snap = snapshot.freeze(root, args.source)
        case_mod.set_status(root, case, "frozen")
    except CaseError as exc:
        return _fail(str(exc))
    print(f"源码已冻结：{snap['file_count']} 个文件，"
          f"源程序量 {snap['total_lines']} 行"
          f"（非空 {snap['nonempty_lines']} 行）。"
          "下一步：select 扫描选材。")
    return 0


def cmd_verify(args) -> int:
    root = _root(args)
    try:
        gaps = snapshot.verify_snapshot(root)
    except CaseError as exc:
        return _fail(str(exc))
    if gaps:
        for g in gaps:
            print(f"漂移：{g}")
        return _fail(f"快照校验未过（{len(gaps)} 项）")
    print("快照校验通过：冻结源码无漂移。")
    return 0


def cmd_select(args) -> int:
    root = _root(args)
    try:
        if case_mod.status_of(root) != "frozen":
            raise CaseError(["select 须在 frozen 后"])
        sel = select_mod.scan_candidates(root)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"选材扫描完成：入选 {len(sel['included'])}，"
          f"排除 {len(sel['exclusions'])}（逐条理由见 selection.json）。")
    for e in sel["exclusions"]:
        print(f"  排除 {e['path']}：{'；'.join(e['reasons'])}")
    print("下一步：核对后 confirm-selection；排除有异议用 appeal 逐个申诉。")
    return 0


def cmd_appeal(args) -> int:
    root = _root(args)
    try:
        select_mod.appeal(root, args.path, args.reason)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"申诉已登记：{args.path} 移入入选（理由留痕）。")
    return 0


def cmd_confirm_selection(args) -> int:
    root = _root(args)
    try:
        sel = select_mod.load_selection(root)
        fp = select_mod.selection_fingerprint(sel)
        case_mod.record_confirmation(root, "selection", "selection", fp)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"选材已确认（入选 {len(sel['included'])} / "
          f"排除 {len(sel['exclusions'])}）。下一步：render-code + draft-doc。")
    return 0


def _require_selection_confirmed(root):
    sel = select_mod.load_selection(root)
    if not case_mod.confirmation_valid(
            root, "selection", "selection",
            select_mod.selection_fingerprint(sel)):
        raise CaseError(["选材未确认（先 confirm-selection）"])
    return sel


def cmd_render_code(args) -> int:
    root = _root(args)
    try:
        if case_mod.status_of(root) not in ("frozen", "materials_ready"):
            raise CaseError(["render-code 须在 frozen 后"])
        _require_selection_confirmed(root)
        facts = case_mod.load_facts(root)
        man = render.render_code_material(root, facts)
        dump_json(root / render.MATERIALS_DIR / "code-manifest.json", man)
        meas = render.measure_code_material(root, man)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"源程序鉴别材料已渲染：{man['constructed_pages']} 页"
          f"（实测 {meas['measured_pages']} 页，每页 "
          f"{schema.CODE_LINES_PER_PAGE} 行，末页除外）。")
    if man["omitted"]:
        print(f"前后各 30 页口径：中段省略 {man['omitted']['omitted_pages']}"
              f" 页（第 {man['omitted']['omitted_from_page']}-"
              f"{man['omitted']['omitted_to_page']} 页）已登记。")
    return 0


def cmd_draft_doc(args) -> int:
    root = _root(args)
    try:
        if case_mod.status_of(root) != "frozen":
            raise CaseError(["draft-doc 须在 frozen 后"])
        _require_selection_confirmed(root)
        facts = case_mod.load_facts(root)
        man = render.draft_doc_segments(root, facts)
        case = case_mod.load_case(root)
        case_mod.set_status(root, case, "materials_ready")
    except CaseError as exc:
        return _fail(str(exc))
    print(f"文档草稿已生成：{man['doc_type']}，共 "
          f"{len(man['segments'])} 段（draft/segments/）。"
          "下一步：逐段审阅，confirm-segment 逐段确认（可先 revise-segment 改写）。")
    return 0


def cmd_revise_segment(args) -> int:
    root = _root(args)
    try:
        man = render.load_segments(root)
        seg = next((s for s in man["segments"]
                    if s["seg_id"] == args.seg), None)
        if seg is None:
            raise CaseError([f"段 {args.seg} 不存在"])
        text = Path(args.from_file).read_text(encoding="utf-8")
        (root / seg["file"]).write_text(text, encoding="utf-8")
        seg["sha256"] = sha256_text(text)
        dump_json(root / render.DRAFT_DIR / "segments-manifest.json", man)
        case_mod.log_tool_use(root, "user", "revise-segment",
                              f"segment:{args.seg}", "用户改写，旧确认失效")
    except CaseError as exc:
        return _fail(str(exc))
    print(f"段 {args.seg} 已改写（新哈希已登记，此前确认失效，须重新确认）。")
    return 0


def cmd_confirm_segment(args) -> int:
    root = _root(args)
    try:
        if case_mod.status_of(root) not in ("materials_ready", "confirmed"):
            raise CaseError(["confirm-segment 须在 materials_ready 后"])
        man = render.load_segments(root)
        seg = next((s for s in man["segments"]
                    if s["seg_id"] == args.seg), None)
        if seg is None:
            raise CaseError([f"段 {args.seg} 不存在"])
        text = render.segment_text(root, seg)
        if sha256_text(text) != seg["sha256"]:
            raise CaseError([f"段 {args.seg} 内容与清单哈希不符"
                             "（生成后被外部改动，先 revise-segment 登记）"])
        case_mod.record_confirmation(root, "segment", args.seg,
                                     seg["sha256"], note=args.note or "")
        pending = [s["seg_id"] for s in man["segments"]
                   if not case_mod.confirmation_valid(
                       root, "segment", s["seg_id"], s["sha256"])]
        if not pending and case_mod.status_of(root) == "materials_ready":
            case = case_mod.load_case(root)
            case_mod.set_status(root, case, "confirmed")
    except CaseError as exc:
        return _fail(str(exc))
    if pending:
        print(f"段 {args.seg} 已确认。未确认段：{'、'.join(pending)}。")
    else:
        print(f"段 {args.seg} 已确认。全部段落确认完毕，状态 confirmed。"
              "下一步：render-doc。")
    return 0


def cmd_render_doc(args) -> int:
    root = _root(args)
    try:
        if case_mod.status_of(root) != "confirmed":
            raise CaseError(["render-doc 须在全部段落确认（confirmed）后"])
        facts = case_mod.load_facts(root)
        man = render.render_doc_material(root, facts)
        dump_json(root / render.MATERIALS_DIR / "doc-manifest.json", man)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"文档鉴别材料已渲染：{man['doc_type']} {man['constructed_pages']}"
          f" 页（{man.get('docx', '无 DOCX')}）。下一步：declaration + check。")
    return 0


def cmd_import_shot(args) -> int:
    root = _root(args)
    try:
        row = release.import_screenshot(root, args.file, args.caption)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"截图已导入：{row['file']}（哈希 {row['sha256'][:12]}，仅导入整理）。")
    return 0


def cmd_declaration(args) -> int:
    root = _root(args)
    try:
        if args.action == "record":
            meta = release.record_declaration_text(root, args.file,
                                                   args.origin)
            print(f"声明原文已登记：{meta['chars']} 字，"
                  f"哈希 {meta['sha256'][:12]}，来源 {meta['origin']}。"
                  "下一步：用户本人逐字核对后 declaration verify。")
            return 0
        # verify：用户本人核对回执（本包不签署，只登记）
        text_p = release.declaration_text_path(root)
        if not text_p.exists():
            raise CaseError(["尚无声明原文落案（先 declaration record）"])
        from .util import sha256_file
        note = args.attest
        if args.claims_no_tool_drafting:
            note = "claims_no_tool_drafting；" + note
        case_mod.record_confirmation(root, "declaration", "current_text",
                                     sha256_file(text_p), note=note)
    except CaseError as exc:
        return _fail(str(exc))
    gaps = release.declaration_gate(root)
    if gaps:
        for g in gaps:
            print(f"未过：{g}")
        return _fail("declaration 门未全过")
    print("declaration 门通过：原文在案 + 逐字核对回执有效 + 留痕无矛盾。")
    return 0


def cmd_check(args) -> int:
    root = _root(args)
    try:
        res = release.run_release_checks(root)
    except CaseError as exc:
        return _fail(str(exc))
    for w in res["warnings"]:
        print(f"警告（不拦）：{w}")
    if not res["ok"]:
        for g in res["gaps"]:
            print(f"未过：{g}")
        return _fail(f"发布门禁未过（{len(res['gaps'])} 项）")
    try:
        case = case_mod.load_case(root)
        if case["status"] == "confirmed":
            case_mod.set_status(root, case, "release_checked")
    except CaseError as exc:
        return _fail(str(exc))
    print("发布门禁全过。下一步：package 产出资料包与递交清单。")
    return 0


def cmd_package(args) -> int:
    root = _root(args)
    try:
        if case_mod.status_of(root) not in ("release_checked", "correcting"):
            raise CaseError(["package 须在 check 全过（release_checked）后，"
                             "或补正回路 correcting 中"])
        out = release.build_package(root)
        case = case_mod.load_case(root)
        if case["status"] == "release_checked":
            case_mod.set_status(root, case, "packaged")
        else:  # correcting 补正后重新打包，correction 留痕保留，状态回 packaged
            case["status"] = "packaged"
            case["updated_at"] = case_mod.today()
            case_mod.save_case(root, case)
    except CaseError as exc:
        return _fail(str(exc))
    print(f"资料包已产出：{out['package_dir']}")
    for f in out["files"]:
        print(f"  - {f}")
    print("v1 到此为止：递交（官网填报/签章）由用户本人按递交清单完成。")
    return 0


def cmd_correct(args) -> int:
    root = _root(args)
    try:
        case = case_mod.load_case(root)
        if case["status"] != "packaged":
            raise CaseError(["correct 须在 packaged 后（收到补正通知时）"])
        from .util import add_days
        case["correction"] = {
            "notice_date": args.notice_date,
            "deadline": add_days(args.notice_date, schema.CORRECTION_DAYS),
            "items": [s.strip() for s in args.items.split("；") if s.strip()],
        }
        case["status"] = "correcting"
        case["updated_at"] = case_mod.today()
        case_mod.save_case(root, case)
        case_mod.log_tool_use(root, "user", "correction", "case",
                              f"补正 {len(case['correction']['items'])} 项，"
                              f"期限 {case['correction']['deadline']}")
    except CaseError as exc:
        return _fail(str(exc))
    print(f"已进入补正回路：期限 {case['correction']['deadline']}"
          f"（通知后 {schema.CORRECTION_DAYS} 日，登记办法第二十二条）。"
          "修正后重新 check + package。")
    return 0


def cmd_status(args) -> int:
    root = _root(args)
    try:
        case = case_mod.load_case(root)
        facts = case_mod.load_facts(root)
    except CaseError as exc:
        return _fail(str(exc))
    sw = facts.get("software") or {}
    print(f"状态：{case['status']}")
    print(f"软件：{sw.get('full_name', '（事实未导入）')} "
          f"{sw.get('version', '')}（{sw.get('kind', '')}）")
    if case.get("correction"):
        c = case["correction"]
        print(f"补正：通知 {c['notice_date']}，期限 {c['deadline']}，"
              f"{len(c['items'])} 项")
    print(f"规则快照：{case.get('rules_snapshot_date')}"
          "（动态字段递交当日复核，HC-7）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="light-copyright",
        description="light-software-copyright：中国软著登记材料")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="建案")
    p.add_argument("path")
    p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_init)

    def case_args(name, help_text):
        q = sub.add_parser(name, help=help_text)
        q.add_argument("case")
        return q

    p = case_args("set-facts", "导入登记事实（用户备好的 yaml/json）")
    p.add_argument("--from", dest="from_file", required=True)
    p.set_defaults(fn=cmd_set_facts)

    p = case_args("confirm-facts", "用户确认登记事实（绑指纹）")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_confirm_facts)

    p = case_args("freeze", "SC0 冻结源码快照")
    p.add_argument("--source", required=True)
    p.set_defaults(fn=cmd_freeze)

    p = case_args("verify", "校验冻结快照无漂移")
    p.set_defaults(fn=cmd_verify)

    p = case_args("select", "SC3 选材扫描（候选 + 排除留痕）")
    p.set_defaults(fn=cmd_select)

    p = case_args("appeal", "排除项申诉改判（须给归属理由）")
    p.add_argument("--path", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_appeal)

    p = case_args("confirm-selection", "用户确认选材")
    p.set_defaults(fn=cmd_confirm_selection)

    p = case_args("render-code", "SC4 渲染源程序鉴别材料")
    p.set_defaults(fn=cmd_render_code)

    p = case_args("draft-doc", "SC5 生成文档草稿段")
    p.set_defaults(fn=cmd_draft_doc)

    p = case_args("revise-segment", "用户改写草稿段（旧确认失效）")
    p.add_argument("--seg", required=True)
    p.add_argument("--from", dest="from_file", required=True)
    p.set_defaults(fn=cmd_revise_segment)

    p = case_args("confirm-segment", "用户逐段确认草稿段")
    p.add_argument("--seg", required=True)
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_confirm_segment)

    p = case_args("render-doc", "渲染文档鉴别材料（确认后）")
    p.set_defaults(fn=cmd_render_doc)

    p = case_args("import-shot", "Q6 导入用户截图（仅整理）")
    p.add_argument("--file", required=True)
    p.add_argument("--caption", required=True)
    p.set_defaults(fn=cmd_import_shot)

    p = case_args("declaration", "当期声明原文登记与逐字核对门")
    p.add_argument("action", choices=("record", "verify"))
    p.add_argument("--file", default="")
    p.add_argument("--origin", default="")
    p.add_argument("--attest", default="本人已逐字核对当期声明原文，"
                                       "工具使用记录与本人声明一致")
    p.add_argument("--claims-no-tool-drafting", action="store_true",
                   help="仅当事实如此时用：回执声称未用工具起草"
                        "（与留痕矛盾将被门阻断）")
    p.set_defaults(fn=cmd_declaration)

    p = case_args("check", "SC7 发布门禁全检")
    p.set_defaults(fn=cmd_check)

    p = case_args("package", "产出正式资料包 + 逐字段递交清单")
    p.set_defaults(fn=cmd_package)

    p = case_args("correct", "登记补正通知，进入 30 日回路")
    p.add_argument("--notice-date", required=True)
    p.add_argument("--items", required=True,
                   help="补正事项，以中文分号分隔")
    p.set_defaults(fn=cmd_correct)

    p = case_args("status", "查看案件状态")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

"""light-memory CLI（Phase 1 + Phase 2）。

  init            建记忆项目骨架（memory.yaml 登记头 + 四账 + 目录群）
  ingest          M0 承接：按水位线收编一个上游包的导出物（九包 + 选刊 + 新三包适配器）
  verdict         M3 判定落账：模型提名的五值判定由代码执行（取代链
                  区间算术 / 争议登记 / 合并查表），逐条回报结果
  dispute-resolve 争议裁决：具名裁决人 + 结论 + 理由，事实按结论执行
  facts           查事实：默认列 current；--as-of 做双时间回溯
  index           索引层：rebuild 从真相全量重建 / status 对账三态
  registry        对象注册：export 刷新 registry-view.json 只读导出
  validate        校验记忆项目（四账一致 + 双时间 + 链无环 + 索引对账
                  + 硬约束自检），逐条点名
  status          看登记头：计数、水位线、索引状态、Phase 2 待办
  candidate       Phase 2 候选通道：propose / list / accept / reject
                  （判断性提炼只产候选，人工 accept 才生效，MM-13c）
  distill-export  Phase 2 蒸馏导出：已生效语料按 Review 覆盖层格式
                  产出（只供最新冻结版）
  distill-import  Phase 2 蒸馏回流收编：Review 双存条目走候选门入账
  recall          Phase 2 检索回供：三路召回 + RRF + 渐进披露
  recipe          Phase 2 配方：list 看五配方 / set 改权重留痕
  project-obsidian Phase 2 Obsidian 投影：精选笔记单向生成入 vault
  readback        Phase 2 标注回读：视图标注区新增内容收为候选
  profile         Phase 2 画像视图：build 再生两文件 / check 自检
  stance          Phase 2 立场视图：（项目，对象）键控现场组装
  bench           Phase 2 评测：build-world 造迷你世界 / run 跑题集
                  出分项报表（只报数不判线，通过线待用户定版）
  promote         Phase 2 晋升通道：propose / confirm / withdraw /
                  list（候选 → 确认 → 复制入全局层，撤回对账）
  vault           工具层 T1/T3 Obsidian 控制层：probe（三面探测）/
                  list / read / create / append / patch / delete /
                  fm / links / backlinks / unresolved / orphans /
                  rename / search / canvas / base / daily / lint
                  （只操作 vault 视图文件，不新开入账路径；活面
                  适配器 livecli/restapi/uri 为可选增强、默认主路
                  仍是文件层）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import basesio as basesio_mod
from . import bench as bench_mod
from . import candidates as cand_mod
from . import canvasio as canvasio_mod
from . import linkgraph as linkgraph_mod
from . import obsidian as obsidian_mod
from . import vaultio as vaultio_mod
from . import profile as profile_mod
from . import promote as promote_mod
from . import retrieve as retrieve_mod
from .index import IndexError_, build_index, index_status
from .intake import IntakeError, ingest
from .project import drop_phase2_pending, init_package, load_package
from .registry import export_registry_view
from .supersede import VerdictError, apply_nominations, facts_as_of, \
    resolve_dispute
from .util import load_structured, sha256_file, utcnow
from .validate import validate_package


def _fail(msg: str) -> int:
    print(f"错误：{msg}", file=sys.stderr)
    return 1


def _gaps_fail(exc) -> int:
    print("被拦（逐项缺口）：", file=sys.stderr)
    for g in exc.gaps:
        print(f"  · {g}", file=sys.stderr)
    return 1


def _load_or_fail(root):
    pkg = load_package(root)
    if pkg.get("memory") is None:
        return None
    return pkg


def cmd_init(args) -> int:
    try:
        root = init_package(args.path, project_id=args.project,
                            title=args.title)
    except FileExistsError as exc:
        return _fail(str(exc))
    print(f"记忆项目已建：{root}")
    print("  登记头 memory.yaml + 四账（objects/events/facts/relations）"
          "+ disputes/promotions 账 + notes/candidates/profile/obsidian/"
          ".index 目录")
    print("  Phase 2 待办已登记在 memory.yaml 的 phase2_pending")
    return 0


def cmd_ingest(args) -> int:
    try:
        report = ingest(args.path, args.package, args.source)
    except IntakeError as exc:
        return _gaps_fail(exc)
    if report["status"] == "unchanged":
        print(f"[{report['package']}] 快照未变，跳过收编"
              f"（哈希 {report['snapshot_hash'][:12]}…）")
        return 0
    c = report["counts"]
    print(f"[{report['package']}] 收编完成：对象登记 {c['objects']}、"
          f"新事件 {c['events']}、新事实 {c['facts']}、新关系 "
          f"{c['relations']}、前向引用补解 {c['forward_refs_resolved']}")
    if report["previous_hash"]:
        print(f"  快照漂移：{report['previous_hash'][:12]}… → "
              f"{report['snapshot_hash'][:12]}…（已按新快照收编）")
    for g in report["gaps"]:
        print(f"  · 缺口：{g}")
    return 0


def cmd_verdict(args) -> int:
    data = load_structured(args.file)
    nominations = data if isinstance(data, list) \
        else data.get("nominations") or []
    if not nominations:
        return _fail(f"提名文件无 nominations：{args.file}")
    try:
        outcomes = apply_nominations(args.path, nominations)
    except VerdictError as exc:
        return _gaps_fail(exc)
    for o in outcomes:
        line = f"[{o['verdict']}] {o['result']}"
        if o.get("fact_id"):
            line += f"（事实 {o['fact_id']}）"
        if o.get("invalidated"):
            line += f"，失效 {o['invalidated']}"
        if o.get("stale_marked"):
            line += f"，派生标 stale {len(o['stale_marked'])} 条"
        if o.get("dispute_id"):
            line += f"，争议 {o['dispute_id']}"
        print("  " + line)
    return 0


def cmd_dispute_resolve(args) -> int:
    try:
        result = resolve_dispute(args.path, args.dispute_id, args.outcome,
                                 adjudicator=args.by,
                                 rationale=args.reason or "")
    except VerdictError as exc:
        return _gaps_fail(exc)
    print(f"争议 {result['dispute_id']} 已裁决：{result['outcome']}"
          f"（裁决人 {args.by}）")
    if result["stale_marked"]:
        print(f"  派生标 stale：{result['stale_marked']}")
    return 0


def cmd_facts(args) -> int:
    pkg = _load_or_fail(args.path)
    if pkg is None:
        return _fail(f"记忆项目不存在或缺登记头：{args.path}")
    facts = pkg.get("facts") or []
    if args.as_of:
        try:
            rows = facts_as_of(facts, args.as_of, known_at=args.known_at)
        except VerdictError as exc:
            return _gaps_fail(exc)
        print(f"as-of {args.as_of} 有效事实 {len(rows)} 条：")
    else:
        rows = [f for f in facts if f.get("status") == "current"]
        print(f"当前有效事实 {len(rows)} 条（全账 {len(facts)} 条）：")
    for f in rows:
        stale = " [stale]" if f.get("stale") else ""
        print(f"  {f.get('fact_id')} [{f.get('fact_type')}] "
              f"{f.get('statement')}{stale}")
        print(f"      对象 {f.get('object_id')}，有效 "
              f"{f.get('valid_at')} → {f.get('invalid_at') or '…'}，"
              f"状态 {f.get('status')}")
    return 0


def cmd_index(args) -> int:
    if args.action == "rebuild":
        try:
            state = build_index(args.path)
        except IndexError_ as exc:
            return _gaps_fail(exc)
        emb = state["embedder"]
        print(f"索引已从真相全量重建：块 {state['counts']['chunks']} "
              f"（事实 {state['counts']['fact_chunks']}、笔记 "
              f"{state['counts']['note_chunks']}），后端 {state['backend']}")
        print(f"  有效嵌入：{emb['effective']}（模型 {emb['model']}，"
              f"维度 {emb['dim']}）——{emb['note']}")
        return 0
    status = index_status(args.path)
    print(f"索引状态：{status['status']}")
    if status["changed"]:
        print("  变化文件：" + "、".join(status["changed"]))
    if status.get("embedder"):
        print(f"  嵌入：{status['embedder'].get('effective')} / "
              f"{status['embedder'].get('model')}，构建于 "
              f"{status.get('built_at')}")
    return 0


def cmd_registry(args) -> int:
    pkg = _load_or_fail(args.path)
    if pkg is None:
        return _fail(f"记忆项目不存在或缺登记头：{args.path}")
    view = export_registry_view(args.path, pkg)
    print(f"registry-view.json 已刷新：对象 "
          f"{sum(view['counts'].values())} 个（按类型 "
          f"{view['counts']}）")
    return 0


def cmd_validate(args) -> int:
    errs = validate_package(args.path)
    if errs:
        print(f"校验未过（{len(errs)} 条）：", file=sys.stderr)
        for e in errs:
            print(f"  · {e}", file=sys.stderr)
        return 1
    print("校验通过：四账一致、双时间合法、取代链无环、索引对账一致、"
          "硬约束自检无违规")
    # 视图层体检（MM2-03e）：只报不自动改，不进错误列表、不改退出码。
    if (Path(args.path) / obsidian_mod.VAULT_DIR).exists():
        findings = obsidian_mod.view_lint(args.path)
        print(f"视图层体检（只报不改）：{len(findings)} 条")
        for f in findings:
            where = f"（{f['note']}）" if f.get("note") else ""
            print(f"  · [{f['category']}] {f['detail']}{where}")
    return 0


def cmd_status(args) -> int:
    pkg = _load_or_fail(args.path)
    if pkg is None:
        return _fail(f"记忆项目不存在或缺登记头：{args.path}")
    memory = pkg["memory"]
    print(f"记忆项目 {memory.get('memory_id')}"
          f"（项目 {memory.get('project', {}).get('id')}，范围 "
          f"{memory.get('project', {}).get('scope')}）")
    print(f"  计数：{memory.get('counts')}")
    wm = memory.get("watermarks") or {}
    if wm:
        print("  水位线：")
        for name, w in sorted(wm.items()):
            print(f"    {name}：适配器 {w.get('adapter_version')}，"
                  f"收编于 {w.get('ingested_at')}，快照 "
                  f"{(w.get('snapshot_hash') or '')[:12]}…")
    else:
        print("  水位线：尚无收编")
    idx = memory.get("index") or {}
    live = index_status(args.path)
    print(f"  索引：登记 {idx.get('status')} / 实况 {live['status']}"
          f"（有效嵌入 {idx.get('embedder_effective')}）")
    pending = memory.get("phase2_pending") or []
    if pending:
        print(f"  Phase 2 待办 {len(pending)} 件（见 SKILL.md §8）")
    return 0


def _drop_pending(root, prefix: str) -> None:
    pkg = load_package(root)
    if pkg.get("memory") is not None:
        drop_phase2_pending(root, pkg["memory"], prefix)


# ---------------------------------------------------------------- Phase 2

def cmd_candidate(args) -> int:
    try:
        if args.action == "propose":
            content = load_structured(args.file)
            row = cand_mod.propose(
                args.path, args.kind or "fact", content,
                nominator=args.nominator, confidence=args.confidence,
                basis=[b for b in (args.basis or "").split(",") if b],
                rationale=args.rationale or "")
            print(f"候选已提名：{row['candidate_id']}（{row['kind']}，"
                  f"状态 pending；未 accept 不入账）")
        elif args.action == "list":
            rows = cand_mod.list_candidates(
                args.path, status=args.status, kind=args.kind)
            print(f"候选 {len(rows)} 条：")
            for r in rows:
                print(f"  {r['candidate_id']} [{r['kind']}] "
                      f"{r['status']}（提名 {r.get('nominator')}，"
                      f"源 {r.get('origin')}）")
        elif args.action == "accept":
            row = cand_mod.accept(args.path, args.id, by=args.by,
                                  note=args.note or "")
            print(f"候选 {row['candidate_id']} 已生效"
                  f"（result_ref：{row.get('result_ref')}）")
        else:  # reject
            row = cand_mod.reject(args.path, args.id, by=args.by,
                                  note=args.note or "")
            print(f"候选 {row['candidate_id']} 已驳回（留痕不删）")
    except cand_mod.CandidateError as exc:
        return _gaps_fail(exc)
    _drop_pending(args.path, "candidates:")
    return 0


def cmd_epilogue(args) -> int:
    from . import epilogue as epilogue_mod
    from .util import dump_json
    try:
        if args.action == "scan":
            scan = epilogue_mod.scan_transcript(args.file)
            if args.out:
                dump_json(args.out, scan)
            print(f"会话切段完成：{len(scan['segments'])} 段"
                  f"（会话哈希 {scan['transcript']['sha256'][:16]}）"
                  + (f"，清单 → {args.out}" if args.out else ""))
            for s in scan["segments"]:
                print(f"  {s['seg_id']} [{s['speaker']}] "
                      f"{s['excerpt']}")
        else:  # apply
            if not args.path:
                return _fail("epilogue apply 须给记忆项目路径")
            res = epilogue_mod.apply_epilogue(
                args.path, args.scan, args.file,
                nominator=args.nominator or "epilogue")
            print(f"epilogue 提名完成：候选 {len(res['created'])} 条"
                  "（只产候选，未 accept 不入账）")
            for cid in res["created"]:
                print(f"  {cid}")
            for g in res["gaps"]:
                print(f"  · 缺口：{g}")
    except epilogue_mod.EpilogueError as exc:
        return _gaps_fail(exc)
    return 0


def cmd_distill_export(args) -> int:
    try:
        res = cand_mod.distill_export(args.path, out=args.out)
    except cand_mod.CandidateError as exc:
        return _gaps_fail(exc)
    print(f"蒸馏导出完成：{res['count']} 条（最新冻结版）→ {res['path']}")
    _drop_pending(args.path, "candidates:")
    return 0


def cmd_distill_import(args) -> int:
    try:
        rows = cand_mod.distill_import(args.path, args.file,
                                       nominator=args.nominator)
    except cand_mod.CandidateError as exc:
        return _gaps_fail(exc)
    print(f"回流条目已收为候选 {len(rows)} 条（走候选门，未直入语料）：")
    for r in rows:
        print(f"  {r['candidate_id']}（rule "
              f"{(r['content'].get('entry') or {}).get('rule_id')}）")
    _drop_pending(args.path, "candidates:")
    return 0


def cmd_recall(args) -> int:
    try:
        result = retrieve_mod.recall(
            args.path, args.query, recipe=args.recipe,
            as_of=args.as_of, depth=args.depth,
            extra_roots=args.also or [])
    except retrieve_mod.RetrieveError as exc:
        return _gaps_fail(exc)
    if not result.get("ok"):
        return _fail(result.get("detail") or "回供失败")
    print(f"回供：配方 {result['recipe']}，作用域 "
          f"{'、'.join(result['scope_roots'])}，命中 "
          f"{result['count']} 条（上限 "
          f"{result['caps']['max_items']}）")
    for d in result["degraded"]:
        print(f"  · 降级：{d}")
    for i, item in enumerate(result["items"], 1):
        flags = []
        if item["disputed"]:
            flags.append("未裁决争议")
        if item["stale"]:
            flags.append("stale")
        if item["validity"] == "as_of":
            flags.append("as-of 当时有效")
        print(f"  {i}. [{item['project']}] {item['source_id']} "
              f"分 {item['score']}（路：{'/'.join(item['routes'])}）"
              + (f" [{'，'.join(flags)}]" if flags else ""))
        if args.depth >= 1 and item.get("text"):
            print(f"     {item['text'][:200]}")
        if args.depth >= 2 and item.get("drill"):
            d = item["drill"]
            print(f"     出处：{d['source_package']} / "
                  f"{d['source_artifact']} / 锚 {d['source_anchor']}")
    _drop_pending(args.path, "retrieval:")
    return 0


def cmd_recipe(args) -> int:
    pkg = _load_or_fail(args.path)
    if pkg is None:
        return _fail(f"记忆项目不存在或缺登记头：{args.path}")
    if args.action == "list":
        for r in retrieve_mod.list_recipes(pkg["memory"]):
            print(f"  {r['name']}：权重 {r['weights']}，作用域 "
                  f"{r['scope']}，跳数 {r['hops']}——{r.get('note')}")
        caps = retrieve_mod.get_caps(pkg["memory"])
        print(f"  回供封顶：{caps}")
        return 0
    patch: dict = {}
    if args.weights:
        weights = {}
        for pair in args.weights.split(","):
            k, _, v = pair.partition("=")
            weights[k.strip()] = float(v)
        patch["weights"] = weights
    if args.hops is not None:
        patch["hops"] = args.hops
    if args.include_dormant is not None:
        patch["include_dormant"] = args.include_dormant == "true"
    if not patch:
        return _fail("recipe set 须至少给一项改动（--weights/--hops/"
                     "--include-dormant）")
    try:
        eff = retrieve_mod.set_recipe(args.path, args.name, patch,
                                      by=args.by)
    except retrieve_mod.RetrieveError as exc:
        return _gaps_fail(exc)
    print(f"配方 {args.name} 已更新并留痕：权重 {eff['weights']}，"
          f"跳数 {eff['hops']}")
    _drop_pending(args.path, "retrieval:")
    return 0


def cmd_project_obsidian(args) -> int:
    try:
        report = obsidian_mod.project_obsidian(args.path,
                                               full=args.full)
    except obsidian_mod.ObsidianError as exc:
        return _gaps_fail(exc)
    print(f"投影完成：入选对象 {report['selected']}，写 "
          f"{len(report['written'])}、未变跳过 "
          f"{len(report['unchanged'])}、脱选留置 "
          f"{len(report['orphaned'])} → {report['vault']}")
    for name in report["orphaned"]:
        print(f"  · 脱选笔记留置（不删，待人工处置）：{name}")
    _drop_pending(args.path, "obsidian:")
    return 0


def cmd_readback(args) -> int:
    try:
        report = obsidian_mod.readback(args.path)
    except (obsidian_mod.ObsidianError, cand_mod.CandidateError) as exc:
        return _gaps_fail(exc)
    print(f"标注回读：新增候选 {report['count']} 条、未变 "
          f"{report['unchanged']} 处（标注只产候选，未 accept 不入账）")
    for cid in report["created"]:
        print(f"  · {cid}")
    _drop_pending(args.path, "obsidian:")
    return 0


# ---------------------------------------------------------------- vault 控制层（T1）

def _emit(args, payload, lines) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in lines:
            print(line)
    return 0


def _register_artifact(vault, rel: str, sha: str) -> None:
    """把控制层产物登记进 .projection.json 的 vault_artifacts 段
    （与投影 notes 分开记，不扰动投影的 orphan 口径）。"""
    manifest = vault / obsidian_mod.MANIFEST_FILE
    if not manifest.exists():
        return
    data = load_structured(manifest) or {}
    artifacts = data.setdefault("vault_artifacts", {})
    artifacts[rel] = {"sha256": sha, "origin": "vault-control",
                      "registered_at": utcnow()}
    from .util import dump_json
    dump_json(manifest, data)


def _typed_value(args):
    raw = args.value
    kind = args.type
    if kind == "null":
        return None
    if kind == "number":
        try:
            return int(raw)
        except ValueError:
            return float(raw)
    if kind == "bool":
        if raw not in ("true", "false"):
            raise vaultio_mod.VaultError(
                [f"--type bool 只许 true/false：{raw}"])
        return raw == "true"
    if kind == "list":
        return [item.strip() for item in raw.split(",") if item.strip()]
    return raw


def cmd_vault(args) -> int:
    vault = vaultio_mod.resolve_vault(args.path)
    act = args.vaction
    try:
        if act == "probe":
            payload = vaultio_mod.probe_vault(vault)
            lines = [
                f"vault：{payload['vault']}（存在 {payload['exists']}，"
                f"笔记 {payload['notes']}）",
                "文件层：可用（默认主路）",
                f"obsidian_live_verified："
                f"{payload['obsidian_live_verified']}"]
            for name, surf in payload["live_surfaces"].items():
                detail = surf.get("reason") or surf.get("scope") or ""
                lines.append(
                    f"活面 {name}：{surf.get('status')}"
                    f"{('（' + detail + '）') if detail else ''}"
                    "（增强面，未验实机）")
            return _emit(args, payload, lines)
        if act == "list":
            notes = vaultio_mod.list_notes(vault)
            return _emit(args, {"notes": notes},
                         [f"笔记 {len(notes)} 篇："] +
                         [f"  {n}" for n in notes])
        if act == "read":
            text = vaultio_mod.read_note(vault, args.note)
            if args.json:
                return _emit(args, {"path": args.note, "text": text},
                             [])
            print(text, end="")
            return 0
        if act == "create":
            content = args.content or ""
            if args.content_file:
                content = Path(args.content_file).read_text(
                    encoding="utf-8")
            fm = json.loads(args.fm_json) if args.fm_json else None
            r = vaultio_mod.create_note(
                vault, args.note, content=content, frontmatter=fm,
                template=args.template, overwrite=args.overwrite)
            return _emit(args, r, [f"已建笔记：{r['path']}"])
        if act == "append":
            addition = args.text or ""
            if args.content_file:
                addition = Path(args.content_file).read_text(
                    encoding="utf-8")
            r = vaultio_mod.append_note(vault, args.note, addition)
            return _emit(args, r, [f"已追加：{r['path']}"])
        if act == "patch":
            body = args.text or ""
            if args.content_file:
                body = Path(args.content_file).read_text(
                    encoding="utf-8")
            r = vaultio_mod.patch_section(vault, args.note,
                                          args.heading, body,
                                          mode=args.mode)
            return _emit(args, r, [
                f"已补丁段落 {r['heading']}（{r['mode']}）：{r['path']}"])
        if act == "delete":
            r = vaultio_mod.delete_note(vault, args.note)
            return _emit(args, r, [
                f"已移入 .trash：{r['path']} → {r['trashed_to']}"])
        if act == "fm":
            if args.fm_action == "get":
                text = vaultio_mod.read_note(vault, args.note)
                found, value = vaultio_mod.fm_get(text, args.key)
                payload = {"path": args.note, "key": args.key,
                           "found": found, "value": value}
                return _emit(args, payload, [
                    f"{args.key}：{value}" if found
                    else f"键不存在：{args.key}"])
            r = vaultio_mod.fm_set_note(vault, args.note, args.key,
                                        _typed_value(args))
            return _emit(args, r, [
                f"已行级补丁 {args.key}：{r['path']}"])
        if act == "links":
            g = linkgraph_mod.build_graph(vault)
            if args.note:
                targets = g["outlinks"].get(args.note, [])
                return _emit(args, {"note": args.note,
                                    "outlinks": targets},
                             [f"{args.note} 出边 {len(targets)}："] +
                             [f"  → {t}" for t in targets])
            lines = [f"图谱：笔记 {len(g['notes'])}、边 "
                     f"{len(g['edges'])}、未解 "
                     f"{len(g['unresolved'])}、孤儿 "
                     f"{len(g['orphans'])}"]
            return _emit(args, g, lines)
        if act == "backlinks":
            g = linkgraph_mod.build_graph(vault)
            sources = g["backlinks"].get(args.note, [])
            return _emit(args, {"note": args.note,
                                "backlinks": sources},
                         [f"{args.note} 入边 {len(sources)}："] +
                         [f"  ← {s}" for s in sources])
        if act == "unresolved":
            g = linkgraph_mod.build_graph(vault)
            rows = g["unresolved"]
            return _emit(args, {"unresolved": rows},
                         [f"未解链接 {len(rows)} 条："] +
                         [f"  {r['from']}:{r['line']} → "
                          f"{r['target_raw']}（{r['reason']}）"
                          for r in rows])
        if act == "orphans":
            g = linkgraph_mod.build_graph(vault)
            rows = g["orphans"]
            return _emit(args, {"orphans": rows},
                         [f"孤儿笔记 {len(rows)} 篇："] +
                         [f"  {r}" for r in rows])
        if act == "rename":
            plan = linkgraph_mod.rename_note(
                vault, args.from_rel, args.to_rel, apply=args.apply)
            lines = [f"改名 {args.from_rel} → {args.to_rel}"
                     f"（{'已落字' if plan['applied'] else 'dry-run'}）：",
                     f"  笔记改链 {len(plan['note_changes'])} 个文件、"
                     f"canvas {len(plan['canvas_changes'])}、"
                     f"base {len(plan['base_changes'])}"]
            for c in plan["note_changes"]:
                for rep in c["replacements"]:
                    lines.append(f"  {c['file']}:{rep['line']} "
                                 f"{rep['old']} → {rep['new']}")
            if plan["applied"]:
                lines.append(f"  落字后新增未解："
                             f"{plan['new_unresolved'] or '无'}")
            return _emit(args, plan, lines)
        if act == "search":
            r = vaultio_mod.search_vault(vault, args.query,
                                         field=args.field)
            return _emit(args, r,
                         [f"命中 {r['count']} 条"
                          f"（截断 {r['truncated']}）："] +
                         [f"  {h['path']}"
                          f"{(':' + str(h['line'])) if h['line'] else ''}"
                          f" {h['text']}" for h in r["hits"]])
        if act == "canvas":
            g = linkgraph_mod.build_graph(vault)
            nodes = [{"type": "file", "file": rel}
                     for rel in g["notes"]]
            edges, seen = [], set()
            for e in g["edges"]:
                if e["to"] is None:
                    continue
                label = e["field"] if e["kind"] == "inline_field" \
                    else None
                key = (e["from"], e["to"], label)
                if key in seen:
                    continue
                seen.add(key)
                edges.append({"from_key": ("file", e["from"]),
                              "to_key": ("file", e["to"]),
                              "label": label})
            out_path = vault / args.out
            r = canvasio_mod.build_canvas_file(out_path, nodes, edges)
            _register_artifact(vault, args.out,
                               sha256_file(out_path))
            return _emit(args, r, [
                f"canvas 已生成/更新：{args.out}（节点 {r['nodes']}、"
                f"边 {r['edges']}；保坐标沿用 {r['nodes_kept']}、"
                f"新增 {r['nodes_added']}、删除 {r['nodes_removed']}）"])
        if act == "base":
            if args.base_action == "build":
                spec = load_structured(args.spec_from)
                out_path = vault / args.out
                r = basesio_mod.write_base(out_path, spec)
                _register_artifact(vault, args.out, r["sha256"])
                return _emit(args, r, [
                    f".base 已生成：{args.out}（视图 {r['views']}）"])
            r = basesio_mod.eval_base(vault, args.file)
            return _emit(args, r, [
                f"离线求值（{r['label']}）：命中 {r['count']} 篇"] +
                [f"  {m}" for m in r["matched"]] +
                ([f"  公式字段不离线算：{r['skipped_formulas']}"]
                 if r["skipped_formulas"] else []))
        if act == "daily":
            on = date.fromisoformat(args.date) if args.date else None
            r = vaultio_mod.daily_note(vault, on=on)
            return _emit(args, r, [
                f"日记：{r['path']}（新建 {r['created']}，格式 "
                f"{r['format']}，配置来源 {r['config_source']}）"])
        if act == "lint":
            findings = []
            pkg = load_package(args.path)
            if pkg.get("memory") is not None and \
                    (Path(args.path) / obsidian_mod.VAULT_DIR).exists():
                findings += obsidian_mod.view_lint(args.path)
            if vault.exists():
                g = linkgraph_mod.build_graph(vault)
                for u in g["unresolved"]:
                    findings.append({
                        "category": "vault_unresolved",
                        "note": u["from"],
                        "detail": f"未解链接 {u['target_raw']}"
                                  f"（{u['reason']}）"})
            return _emit(args, {"findings": findings},
                         [f"vault 体检（只报不改）：{len(findings)} 条"]
                         + [f"  · [{f['category']}] {f['detail']}"
                            f"（{f['note']}）" if f.get("note") else
                            f"  · [{f['category']}] {f['detail']}"
                            for f in findings])
    except (vaultio_mod.VaultError, linkgraph_mod.LinkGraphError,
            canvasio_mod.CanvasError, basesio_mod.BaseError) as exc:
        return _gaps_fail(exc)
    return _fail(f"未知 vault 动作：{act}")


def cmd_profile(args) -> int:
    if args.action == "build":
        try:
            res = profile_mod.build_profile(args.path)
        except profile_mod.ProfileError as exc:
            return _gaps_fail(exc)
        print(f"画像已再生：{res['static']} / {res['dynamic']}"
              f"（决策 {res['decisions']}、方法 {res['methods']}、"
              f"近期事件 {res['recent_events']}；只装处置与指针）")
        _drop_pending(args.path, "profile:")
        return 0
    errs = profile_mod.check_profile(args.path)
    if errs:
        print(f"画像自检未过（{len(errs)} 条）：", file=sys.stderr)
        for e in errs:
            print(f"  · {e}", file=sys.stderr)
        return 1
    print("画像自检通过：每条内容行均带可回指指针")
    return 0


def cmd_stance(args) -> int:
    pkg = _load_or_fail(args.path)
    if pkg is None:
        return _fail(f"记忆项目不存在或缺登记头：{args.path}")
    label = (pkg["memory"].get("project") or {}).get("id") or args.path
    roots = [(label, args.path)]
    for extra in args.also or []:
        epkg = load_package(extra)
        if epkg.get("memory") is None:
            return _fail(f"记忆项目不存在或缺登记头：{extra}")
        roots.append(((epkg["memory"].get("project") or {}).get("id")
                      or extra, extra))
    try:
        view = profile_mod.stance_view(roots, args.object)
    except profile_mod.ProfileError as exc:
        return _gaps_fail(exc)
    print(profile_mod.render_stance(view), end="")
    return 0


def cmd_bench(args) -> int:
    if args.action == "build-world":
        roots = bench_mod.build_mini_world(args.dir)
        print("迷你世界已构造：" +
              "、".join(f"{k}={v}" for k, v in roots.items()))
        return 0
    try:
        report = bench_mod.run_bench(args.set, args.world,
                                     out=args.out)
    except bench_mod.BenchError as exc:
        return _gaps_fail(exc)
    print(f"评测报表（只报数不判线，通过线：{report['pass_line']}）：")
    for cat, c in sorted(report["categories"].items()):
        print(f"  {cat}：{c['correct']}/{c['total']}（率 {c['rate']}）")
    print(f"  合计：{report['overall']['correct']}/"
          f"{report['overall']['total']}")
    if args.out:
        print(f"  报表已存：{args.out}")
    if args.path:
        _drop_pending(args.path, "eval:")
    return 0


def cmd_promote(args) -> int:
    try:
        if args.action == "propose":
            row = promote_mod.propose(args.path, args.source,
                                      args.fact_id, by=args.by,
                                      reason=args.reason or "")
            print(f"晋升候选已提名：{row['candidate_id']}"
                  "（pending；confirm 后才复制入全局层）")
        elif args.action == "confirm":
            rec = promote_mod.confirm(args.path, args.id, by=args.by)
            print(f"晋升生效：{rec['promotion_id']}，副本 "
                  f"{rec['global_fact_id']} 已入全局层"
                  "（原件留在项目层）")
        elif args.action == "withdraw":
            rec = promote_mod.withdraw(args.path, args.promotion_id,
                                       by=args.by,
                                       reason=args.reason or "")
            print(f"晋升已撤回：{rec['promotion_id']}"
                  "（全局副本对账删除，晋升账留痕，项目原件不动）")
        else:  # list
            rows = promote_mod.list_promotions(args.path)
            print(f"晋升账 {len(rows)} 行：")
            for r in rows:
                print(f"  {r['promotion_id']} [{r['action']}] "
                      f"{r.get('source_fact_id')}（{r.get('by')}，"
                      f"{r.get('at')}）")
    except (promote_mod.PromoteError, cand_mod.CandidateError) as exc:
        return _gaps_fail(exc)
    _drop_pending(args.path, "promote:")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-memory",
        description="light-memory：独立研究记忆（Phase 1 + Phase 2）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="建记忆项目骨架")
    p.add_argument("path")
    p.add_argument("--project", default="")
    p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("ingest", help="M0 承接：收编一个上游包的导出物")
    p.add_argument("path")
    p.add_argument("--package", required=True)
    p.add_argument("--source", required=True)
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("verdict", help="M3 判定落账（提名文件 JSON）")
    p.add_argument("path")
    p.add_argument("--file", required=True)
    p.set_defaults(fn=cmd_verdict)

    p = sub.add_parser("dispute-resolve", help="争议裁决（具名+结论+理由）")
    p.add_argument("path")
    p.add_argument("--dispute-id", required=True)
    p.add_argument("--outcome", required=True,
                   choices=["challenger_wins", "incumbent_wins",
                            "both_stand"])
    p.add_argument("--by", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_dispute_resolve)

    p = sub.add_parser("facts", help="查事实（默认 current；--as-of 回溯）")
    p.add_argument("path")
    p.add_argument("--as-of", default=None)
    p.add_argument("--known-at", default=None)
    p.set_defaults(fn=cmd_facts)

    p = sub.add_parser("index", help="索引层：rebuild / status")
    p.add_argument("path")
    p.add_argument("action", choices=["rebuild", "status"])
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser("registry", help="对象注册导出")
    p.add_argument("path")
    p.add_argument("action", choices=["export"])
    p.set_defaults(fn=cmd_registry)

    p = sub.add_parser("validate", help="校验记忆项目")
    p.add_argument("path")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("status", help="看登记头与水位线")
    p.add_argument("path")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("candidate",
                       help="Phase 2 候选通道（判断性提炼只产候选）")
    p.add_argument("path")
    p.add_argument("action",
                   choices=["propose", "list", "accept", "reject"])
    # --kind 默认 None：list 时不带 --kind 须列全部 kind（MM2-09，
    # 默认值 fact 会把 annotation 等候选静默吞掉）；propose 未给时
    # 在 cmd_candidate 内回落 fact（提名须有确定类型）。
    p.add_argument("--kind", default=None)
    p.add_argument("--file", default=None)
    p.add_argument("--nominator", default="")
    p.add_argument("--confidence", type=float, default=None)
    p.add_argument("--basis", default="")
    p.add_argument("--rationale", default="")
    p.add_argument("--status", default=None)
    p.add_argument("--id", default=None)
    p.add_argument("--by", default="")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_candidate)

    p = sub.add_parser("epilogue",
                       help="会话沉淀规程（MM2-01）：scan 切段 / "
                            "apply 提名候选（只产候选）")
    p.add_argument("path", nargs="?", default=None,
                   help="记忆项目路径（apply 必填；scan 不用）")
    p.add_argument("action", choices=["scan", "apply"])
    p.add_argument("--file", required=True,
                   help="scan：会话记录文件；apply：提名文件")
    p.add_argument("--scan", default=None,
                   help="apply：scan 产出的切段清单")
    p.add_argument("--out", default=None, help="scan 清单输出路径")
    p.add_argument("--nominator", default="epilogue")
    p.set_defaults(fn=cmd_epilogue)

    p = sub.add_parser("distill-export",
                       help="Phase 2 蒸馏导出（Review 覆盖层格式）")
    p.add_argument("path")
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_distill_export)

    p = sub.add_parser("distill-import",
                       help="Phase 2 蒸馏回流收编（走候选门）")
    p.add_argument("path")
    p.add_argument("--file", required=True)
    p.add_argument("--nominator", required=True)
    p.set_defaults(fn=cmd_distill_import)

    p = sub.add_parser("recall", help="Phase 2 检索回供（三路 + 披露）")
    p.add_argument("path")
    p.add_argument("query")
    p.add_argument("--recipe", default="default")
    p.add_argument("--as-of", default=None)
    p.add_argument("--depth", type=int, default=0, choices=[0, 1, 2])
    p.add_argument("--also", action="append", default=[])
    p.set_defaults(fn=cmd_recall)

    p = sub.add_parser("recipe", help="Phase 2 配方查看/改权重留痕")
    p.add_argument("path")
    p.add_argument("action", choices=["list", "set"])
    p.add_argument("--name", default=None)
    p.add_argument("--weights", default=None)
    p.add_argument("--hops", type=int, default=None)
    p.add_argument("--include-dormant", default=None,
                   choices=["true", "false"])
    p.add_argument("--by", default="")
    p.set_defaults(fn=cmd_recipe)

    p = sub.add_parser("project-obsidian",
                       help="Phase 2 Obsidian 单向投影")
    p.add_argument("path")
    p.add_argument("--full", action="store_true")
    p.set_defaults(fn=cmd_project_obsidian)

    p = sub.add_parser("readback", help="Phase 2 视图标注回读为候选")
    p.add_argument("path")
    p.set_defaults(fn=cmd_readback)

    p = sub.add_parser("profile", help="Phase 2 画像视图再生/自检")
    p.add_argument("path")
    p.add_argument("action", choices=["build", "check"])
    p.set_defaults(fn=cmd_profile)

    p = sub.add_parser("stance",
                       help="Phase 2 立场视图（项目，对象）键控组装")
    p.add_argument("path")
    p.add_argument("--object", required=True)
    p.add_argument("--also", action="append", default=[])
    p.set_defaults(fn=cmd_stance)

    p = sub.add_parser("bench", help="Phase 2 评测集运行器")
    p.add_argument("action", choices=["build-world", "run"])
    p.add_argument("dir", nargs="?", default=None)
    p.add_argument("--world", default=None)
    p.add_argument("--set", default="mini")
    p.add_argument("--out", default=None)
    p.add_argument("--path", default=None,
                   help="run 时顺带摘除该包的 eval 待办登记")
    p.set_defaults(fn=cmd_bench)

    pv = sub.add_parser(
        "vault",
        help="Obsidian 控制层（T1 文件层 vaultio/linkgraph/"
             "canvasio/basesio；T3 活面适配器 livecli/restapi/"
             "uri，probe 三面探测）")
    pv.add_argument("path", help="记忆项目根或 vault 目录")
    vsub = pv.add_subparsers(dest="vaction", required=True)

    def _leaf(name, help_text):
        leaf = vsub.add_parser(name, help=help_text)
        leaf.add_argument("--json", action="store_true")
        return leaf

    _leaf("probe", "探测：文件层可用性 + 活面三面状态与 live 登记")
    _leaf("list", "列 vault 内笔记")
    p = _leaf("read", "读笔记全文")
    p.add_argument("--note", required=True)
    p = _leaf("create", "建笔记（可带模板/ frontmatter）")
    p.add_argument("--note", required=True)
    p.add_argument("--content", default="")
    p.add_argument("--content-file", default=None)
    p.add_argument("--template", default=None)
    p.add_argument("--fm-json", default=None,
                   help="frontmatter 初值（JSON 对象）")
    p.add_argument("--overwrite", action="store_true")
    p = _leaf("append", "追加内容（投影笔记进标注区）")
    p.add_argument("--note", required=True)
    p.add_argument("--text", default="")
    p.add_argument("--content-file", default=None)
    p = _leaf("patch", "按标题路径补丁段落")
    p.add_argument("--note", required=True)
    p.add_argument("--heading", required=True)
    p.add_argument("--text", default="")
    p.add_argument("--content-file", default=None)
    p.add_argument("--mode", default="replace",
                   choices=["replace", "append"])
    p = _leaf("delete", "留痕删除（移入 .trash）")
    p.add_argument("--note", required=True)
    pfm = vsub.add_parser("fm", help="frontmatter 行级补丁")
    fsub = pfm.add_subparsers(dest="fm_action", required=True)
    p = fsub.add_parser("get", help="读 frontmatter 键")
    p.add_argument("--note", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--json", action="store_true")
    p = fsub.add_parser("set", help="行级设置 frontmatter 键")
    p.add_argument("--note", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--value", default="")
    p.add_argument("--type", default="string",
                   choices=["string", "number", "bool", "date",
                            "list", "null"])
    p.add_argument("--json", action="store_true")
    p = _leaf("links", "出边（或全图谱概览）")
    p.add_argument("--note", default=None)
    p = _leaf("backlinks", "入边")
    p.add_argument("--note", required=True)
    _leaf("unresolved", "未解链接清单")
    _leaf("orphans", "孤儿笔记清单")
    p = _leaf("rename", "改名重写（默认 dry-run，--apply 落字）")
    p.add_argument("--from", dest="from_rel", required=True)
    p.add_argument("--to", dest="to_rel", required=True)
    p.add_argument("--apply", action="store_true")
    p = _leaf("search", "全文/字段检索")
    p.add_argument("query")
    p.add_argument("--field", default=None)
    pcan = vsub.add_parser("canvas", help="JSON Canvas 著述")
    csub = pcan.add_subparsers(dest="canvas_action", required=True)
    p = csub.add_parser("build", help="由链接图谱生成/保坐标更新")
    p.add_argument("--out", required=True)
    p.add_argument("--json", action="store_true")
    pbase = vsub.add_parser("base", help="Bases 著述与离线求值")
    bsub = pbase.add_subparsers(dest="base_action", required=True)
    p = bsub.add_parser("build", help="按视图定义文件生成 .base")
    p.add_argument("--from", dest="spec_from", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--json", action="store_true")
    p = bsub.add_parser("eval", help="离线求值（filters 子集）")
    p.add_argument("--file", required=True)
    p.add_argument("--json", action="store_true")
    p = _leaf("daily", "按 daily-notes 配置定位/建当日笔记")
    p.add_argument("--date", default=None)
    _leaf("lint", "体检：view_lint + 图谱未解（只报不改）")
    pv.set_defaults(fn=cmd_vault)

    p = sub.add_parser("promote", help="Phase 2 跨项目晋升通道")
    p.add_argument("path", help="全局层记忆包路径")
    p.add_argument("action",
                   choices=["propose", "confirm", "withdraw", "list"])
    p.add_argument("--from", dest="source", default=None)
    p.add_argument("--fact-id", default=None)
    p.add_argument("--id", default=None)
    p.add_argument("--promotion-id", default=None)
    p.add_argument("--by", default="")
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_promote)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

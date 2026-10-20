"""校验器：四账一致性 + 双时间合法性 + 取代链无环 + 索引对账 + 硬约束自检。

逐条点名返回错误列表（空 = 通过）。检查面：
1. 文件群齐备与登记头形态；
2. 溯源五字段完整（MM-02）：事件/事实/关系/争议逐条；
3. 指针完整性：事实→对象、关系端点、取代指针双向对称；
4. 双时间合法性（MM-09）：invalid_at 不早于 valid_at 等；
5. 取代链无环（沿 superseded_by 走不到自己）；
6. 争议账与事实状态双向一致（MM-15）；
7. 关系类型在词表内、生成方式与类型表相符（MM-25）；
8. 索引与真相哈希对账（MM-05）：台账在册而真相已变 → 点名文件；
9. 硬约束自检（MM-03）：真相目录出现数据库文件即报错——数据库只许
   住在 .index 里当影子；判定事件的 verdict 必须在五值词表内。
"""

from __future__ import annotations

from pathlib import Path

from . import project as project_mod, schema
from .index import index_status

DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")


def _prov_errors(kind: str, ident, prov) -> list:
    gaps = schema.provenance_gaps(prov)
    if not gaps:
        return []
    return [f"{kind} {ident}：溯源缺 {'、'.join(gaps)}（MM-02）"]


def validate_package(root) -> list:
    root = Path(root)
    errs: list = []
    pkg = project_mod.load_package(root)
    memory = pkg.get("memory")

    # ---- 1. 文件群与登记头 ---------------------------------------------
    for key, name in project_mod.FILES.items():
        if key == "registry_view":
            continue  # 导出件，可随时重建，不作齐备要求
        if pkg.get(key) is None:
            errs.append(f"文件群缺失：{name}")
    if memory is None:
        return errs
    if memory.get("kind") != "light-memory/project":
        errs.append("登记头 kind 不是 light-memory/project")

    objects = pkg.get("objects") or []
    events = pkg.get("events") or []
    facts = pkg.get("facts") or []
    relations = pkg.get("relations") or []
    disputes = pkg.get("disputes") or []

    # ---- 3a. 对象：ID 唯一 + 派生一致 -----------------------------------
    object_ids = set()
    for o in objects:
        oid = o.get("object_id")
        if oid in object_ids:
            errs.append(f"对象 ID 重复：{oid}")
        object_ids.add(oid)
        expect = schema.derive_object_id(o.get("object_type"),
                                         o.get("upstream_id"))
        if oid != expect:
            errs.append(f"对象 {oid}：ID 与派生口径不符（应为 {expect}）")
        if o.get("status") not in schema.OBJECT_STATUSES:
            errs.append(f"对象 {oid}：状态不在词表内：{o.get('status')}")

    facts_by_id = {f.get("fact_id"): f for f in facts}

    # ---- 2/3b/4. 事实：溯源、指针、双时间 -------------------------------
    for f in facts:
        fid = f.get("fact_id")
        provs = f.get("provenance") or []
        if not provs:
            errs.append(f"事实 {fid}：无溯源记录（MM-02）")
        for prov in provs:
            errs += _prov_errors("事实", fid, prov)
        if f.get("object_id") not in object_ids:
            errs.append(f"事实 {fid}：指向不存在的对象 "
                        f"{f.get('object_id')}")
        if f.get("status") not in schema.FACT_STATUSES:
            errs.append(f"事实 {fid}：状态不在词表内：{f.get('status')}")
        errs += schema.check_interval(f)
        if f.get("status") == "superseded":
            succ = f.get("superseded_by")
            if not succ:
                errs.append(f"事实 {fid}：已取代但 superseded_by 为空")
            elif succ not in facts_by_id:
                errs.append(f"事实 {fid}：superseded_by 指向不存在的 "
                            f"事实 {succ}")
            else:
                srow = facts_by_id[succ]
                points_back = srow.get("supersedes") == fid or \
                    fid in (srow.get("derived_from") or []) or \
                    fid in ((srow.get("extra") or {})
                            .get("merged_from") or [])
                if not points_back:
                    errs.append(f"事实 {fid}：取代指针不对称——{succ} "
                                "未回指本事实")
        for src in f.get("derived_from") or []:
            if src not in facts_by_id:
                errs.append(f"事实 {fid}：derived_from 指向不存在的 "
                            f"事实 {src}")

    # ---- 5. 取代链无环 ---------------------------------------------------
    for f in facts:
        seen = set()
        cur = f.get("fact_id")
        while cur:
            if cur in seen:
                errs.append(f"取代链成环：从 {f.get('fact_id')} 出发"
                            f"回到 {cur}")
                break
            seen.add(cur)
            row = facts_by_id.get(cur)
            cur = row.get("superseded_by") if row else None

    # ---- 6. 争议双向一致 --------------------------------------------------
    open_dispute_facts = set()
    for d in disputes:
        errs += _prov_errors("争议", d.get("dispute_id"),
                             d.get("provenance"))
        for fid in d.get("fact_ids") or []:
            if fid not in facts_by_id:
                errs.append(f"争议 {d.get('dispute_id')}：指向不存在的"
                            f"事实 {fid}")
            elif d.get("status") == "open":
                open_dispute_facts.add(fid)
    for fid in open_dispute_facts:
        if facts_by_id[fid].get("status") != "disputed":
            errs.append(f"事实 {fid}：在 open 争议中但状态不是 disputed")
    for f in facts:
        if f.get("status") == "disputed" and \
                f.get("fact_id") not in open_dispute_facts:
            errs.append(f"事实 {f.get('fact_id')}：状态 disputed 但无 "
                        "open 争议账对应")

    # ---- 2/7. 关系：溯源、词表、端点 --------------------------------------
    for r in relations:
        rid = r.get("relation_id")
        errs += _prov_errors("关系", rid, r.get("provenance"))
        spec = schema.RELATION_TYPES.get(r.get("type"))
        if spec is None:
            errs.append(f"关系 {rid}：类型不在词表内：{r.get('type')}")
            continue
        if r.get("generation") != spec["generation"]:
            errs.append(f"关系 {rid}：生成方式 {r.get('generation')} 与"
                        f"类型表不符（应为 {spec['generation']}）")
        if r.get("status") == "resolved":
            for end in ("from_id", "to_id"):
                if r.get(end) not in object_ids and \
                        r.get(end) not in facts_by_id:
                    errs.append(f"关系 {rid}：{end} 指向不存在的端点 "
                                f"{r.get(end)}")
        elif r.get("status") == "unresolved" and not r.get("target_name"):
            errs.append(f"关系 {rid}：unresolved 但未保留目标原文标识"
                        "（MM-26）")

    # ---- 2/9. 事件：溯源 + 判定词表 ----------------------------------------
    for e in events:
        errs += _prov_errors("事件", e.get("event_id"),
                             e.get("provenance"))
        if e.get("type") == "verdict":
            v = (e.get("payload") or {}).get("verdict")
            if v is not None and v not in schema.VERDICTS:
                errs.append(f"事件 {e.get('event_id')}：verdict 不在"
                            f"五值词表内：{v}")

    # ---- 8. 索引对账 --------------------------------------------------------
    status = index_status(root)
    if status["status"] == "stale":
        errs.append("索引与真相不一致（stale），变化文件："
                    + "、".join(status["changed"])
                    + "；运行 index rebuild 重建")
    # 索引整删是合法操作（MM-03）：台账缺失不算错误，登记头摘要与
    # 实况的出入由 status 命令呈现，不在此报错。

    # ---- 9. 硬约束自检：真相目录不许有数据库文件 ----------------------------
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] == ".index":
            continue
        if p.suffix in DB_SUFFIXES:
            errs.append(f"真相目录出现数据库文件：{rel}（数据库只许住在"
                        ".index 里当影子索引，MM-03）")
    return errs

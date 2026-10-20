"""词表与工厂：判定五值、关系类型表、合并算子表、条目工厂、ID 派生。

纪律锚点（LEARNING.md）：
- MM-01：Memory 不另建 ID 体系，内部稳定 ID 由「对象类型 + 上游 ID」
  确定性派生，同一对象跨次收编自动合并。
- MM-02：溯源五字段是条目出生的必填项（来源包/来源产物/来源锚点/
  来源版本/收编时间），缺一不许进长期层。
- MM-14：沉淀判定只许五值词表；合并算子按条目类型预声明，写入路径
  只查表，不许在写入现场发明操作。
- MM-25：关系类型表带端点签名与生成方式，命门四类（启发/否定/修订/
  折返）自建。
"""

from __future__ import annotations

from .util import component_hash, parse_time, today, utcnow

# ---------------------------------------------------------------- 词表

#: 沉淀判定五值（MM-14）。delete 不在词表内（MM-30：物理删除退出词表）。
VERDICTS = ("store", "skip", "supersede", "merge", "dispute")

#: 事实状态机：current → superseded / disputed（裁决后回 current 或转
#: superseded）。跃迁只许由沉淀命令与裁决命令执行并落事件。
FACT_STATUSES = ("current", "superseded", "disputed")

#: 对象状态：referenced = 只被指针引用、尚未收编本体的前向登记（MM-26）。
OBJECT_STATUSES = ("active", "superseded", "archived", "referenced")

#: 关系状态：unresolved = 前向引用（目标未出现，保留目标原文标识）。
RELATION_STATUSES = ("resolved", "unresolved", "superseded")

#: 上游包登记名（收编适配器与水位线的键）。
UPSTREAM_PACKAGES = ("literature", "idea", "design", "experiment",
                     "analysis", "write", "figure", "journal-select",
                     "review")

# ---------------------------------------------------------------- 算子表

#: 合并算子表（按事实类型预声明，MM-14）：写入路径只查表。
#: supersede_only —— 结论类不许 merge 稀释口径，只许新版取代；
#: immutable      —— 决策类不许就地改写，变更只能走 supersede；
#: merge_union    —— 教训类可合并，时间跨度与出处取并集；
#: patch          —— 方法类可经 merge 更新派生描述（必落演化事件）；
#: free           —— 其余类型按判定词表正常处理。
MERGE_OPERATORS = {
    "conclusion": "supersede_only",
    "conclusion_verdict": "supersede_only",
    "design_claim": "supersede_only",
    "decision": "immutable",
    "lesson": "merge_union",
    "method": "patch",
    "journal_fact": "merge_union",
    "evidence": "merge_union",
    "direction": "merge_union",
    "figure_provenance": "merge_union",
    "failure_record": "merge_union",
    "review_concern": "merge_union",
    "generic": "free",
}

#: 允许 merge 判定的事实类型（算子为 merge_union / patch / free 者）。
MERGEABLE_OPERATORS = ("merge_union", "patch", "free")


def merge_operator(fact_type: str) -> str:
    return MERGE_OPERATORS.get(fact_type or "generic", "free")


# ---------------------------------------------------------------- 关系表

#: 关系类型表 v1（MM-25）：每类登记方向、端点签名、生成方式、默认权重。
#: 端点签名 None 表示任意类型端点；from/to 为允许的对象/条目类型集合。
#: 强关系只许机械生成；弱关系（inspires）走候选 + 判定两段式。
RELATION_TYPES = {
    "supersedes": {
        "direction": "directed", "generation": "mechanical",
        "endpoints": None, "weight": 1.0,
        "note": "修订/取代（强）：新版对旧版的取代，只由上游事件与取代链机械生成",
    },
    "refutes": {
        "direction": "directed", "generation": "mechanical",
        "endpoints": None, "weight": 1.0,
        "note": "否定（强）：如撤稿事件对关联结论的否定边",
    },
    "supports": {
        "direction": "directed", "generation": "mechanical",
        "endpoints": None, "weight": 0.8,
        "note": "证实（强）：证据对主张的支持",
    },
    "depends-on": {
        "direction": "directed", "generation": "mechanical",
        "endpoints": None, "weight": 0.8,
        "note": "依赖（强）：结论包对执行包/设计包的承接依赖",
    },
    "derived-from": {
        "direction": "directed", "generation": "mechanical",
        "endpoints": None, "weight": 0.6,
        "note": "出处包含（强）：派生条目回指其源头",
    },
    "same-object-as": {
        "direction": "undirected", "generation": "mechanical",
        "endpoints": None, "weight": 0.6,
        "note": "跨项目同源（中）：同一上游对象在不同项目的登记映射",
    },
    "backtracks-to": {
        "direction": "directed", "generation": "mechanical",
        "endpoints": None, "weight": 0.7,
        "note": "折返（中）：死胡同/返工路线连回其种子与定版产物",
    },
    "inspires": {
        "direction": "directed", "generation": "judged",
        "endpoints": None, "weight": 0.4,
        "note": "启发（弱）：只许候选 + 判定两段式生成，落账带判定标记",
    },
}

#: 否定与折返边的传播权重下限受保护（MM-20：不许被来源计数压过）。
PROTECTED_RELATION_FLOOR = {"refutes": 0.7, "backtracks-to": 0.7}


# ---------------------------------------------------------------- ID 派生

def derive_object_id(object_type: str, upstream_id: str) -> str:
    """对象 Memory ID：由对象类型 + 上游 ID 确定性派生（MM-01）。"""
    return f"{object_type}:{upstream_id}"


def derive_fact_id(object_id: str, statement: str, valid_at,
                   source_package: str) -> str:
    """事实 ID：由对象 + 陈述 + 生效时间 + 来源包派生，保证收编幂等。"""
    digest = component_hash({
        "object_id": object_id, "statement": statement,
        "valid_at": str(valid_at) if valid_at is not None else None,
        "source_package": source_package,
    })
    return f"fact_{digest[:12]}"


def derive_relation_id(rel_type: str, from_id: str, to_id: str) -> str:
    digest = component_hash({"type": rel_type, "from": from_id, "to": to_id})
    return f"rel_{digest[:12]}"


# ---------------------------------------------------------------- 溯源

PROVENANCE_FIELDS = ("source_package", "source_artifact", "source_anchor",
                     "source_version", "ingested_at")


def make_provenance(source_package: str, source_artifact: str,
                    source_anchor, source_version, *, at: str = None) -> dict:
    """溯源五字段（MM-02）：条目出生必填，缺一不许进长期层。"""
    return {
        "source_package": source_package,
        "source_artifact": source_artifact,
        "source_anchor": source_anchor,
        "source_version": source_version,
        "ingested_at": at or utcnow(),
    }


def provenance_gaps(prov) -> list:
    """检查一条溯源记录缺哪几项（空串/None 均算缺）。"""
    if not isinstance(prov, dict):
        return list(PROVENANCE_FIELDS)
    return [f for f in PROVENANCE_FIELDS
            if prov.get(f) is None or prov.get(f) == ""]


# ---------------------------------------------------------------- 工厂

def new_memory(memory_id: str, project_id: str = "", title: str = "",
               scope: str = "project") -> dict:
    """登记头 memory.yaml（权威）：项目、隔离、嵌入登记、水位线、索引摘要。"""
    now = utcnow()
    return {
        "kind": "light-memory/project",
        "version": "0.1",
        "memory_id": memory_id,
        "project": {"id": project_id or memory_id, "title": title,
                    "scope": scope},
        "created_at": now,
        "updated_at": now,
        # 嵌入提供者登记（拍板 2）：未登记时索引用确定性测试嵌入并标注。
        "embedder": {"provider": None, "model": None, "dim": None},
        "settle": {
            "triggers": {"count_threshold": 20, "idle_days": 7,
                         "warmup": [1, 2, 4, 8]},
            "recipes": ["default", "paraphrase", "failure-lookup",
                        "as-of", "cross-project"],
        },
        "watermarks": {},
        "adapters": {},
        "index": {"status": "absent", "embedder_effective": None,
                  "model": None, "built_at": None,
                  "truth_manifest_hash": None},
        "counts": {"objects": 0, "events": 0, "facts": 0,
                   "relations": 0, "disputes_open": 0},
        # Phase 2 接口登记位（本期只留接口，见 SKILL.md §8）。
        "phase2_pending": [
            "candidates: 判断性提炼候选通道与 accept 生效门（MM-13c）",
            "retrieval: 检索三路融合与渐进披露三级（MM-19 至 MM-23）",
            "obsidian: Obsidian 视图投影生成与标注回读（MM-27 至 MM-29）",
            "profile: 画像视图再生与项目立场视图（MM-31）",
            "eval: 自建评测集运行器与配置报表（MM-32）",
            "promote: 跨项目晋升通道与撤回对账（拍板 6）",
        ],
    }


def new_object(object_type: str, upstream_id: str, provenance: dict, *,
               project: str = "", title: str = "", status: str = "active",
               current_version=None, at: str = None) -> dict:
    now = at or utcnow()
    return {
        "object_id": derive_object_id(object_type, upstream_id),
        "object_type": object_type,
        "upstream_id": upstream_id,
        "project": project,
        "title": title,
        "status": status,
        "current_version": current_version,
        "aliases": [],
        "source_package": provenance.get("source_package"),
        "source_version": provenance.get("source_version"),
        "registered_at": now,
        "updated_at": now,
    }


def new_event(seq: int, event_type: str, summary: str, provenance: dict, *,
              object_id=None, payload=None, at: str = None) -> dict:
    return {
        "event_id": f"EV-{seq:06d}",
        "seq": seq,
        "ts": at or utcnow(),
        "type": event_type,
        "summary": summary,
        "object_id": object_id,
        "payload": payload or {},
        "provenance": provenance,
    }


def new_fact(statement: str, fact_type: str, object_id: str,
             provenance, *, valid_at=None, invalid_at=None,
             reference_time=None, derived_from=None, extra=None,
             status: str = "current", at: str = None) -> dict:
    """事实条目：双时间四字段 + 溯源列表 + 取代指针 + 强度记账（MM-09）。"""
    if isinstance(provenance, dict):
        provenance = [provenance]
    now = at or utcnow()
    return {
        "fact_id": derive_fact_id(
            object_id, statement, valid_at,
            (provenance[0] or {}).get("source_package") if provenance
            else ""),
        "statement": statement,
        "fact_type": fact_type or "generic",
        "object_id": object_id,
        "valid_at": valid_at,
        "invalid_at": invalid_at,
        "created_at": now,
        "expired_at": None,
        "reference_time": reference_time,
        "provenance": provenance,
        "status": status,
        "superseded_by": None,
        "supersedes": None,
        "derived_from": list(derived_from or []),
        "stale": False,
        "stale_reason": None,
        # 强度记账（MM-30）：只作排序与休眠分层信号，永不驱动物理删除。
        "strength": {"calls": 0, "last_called_at": None, "dormant": False},
        "extra": extra or {},
    }


def new_relation(rel_type: str, from_id: str, to_id: str, provenance: dict,
                 *, generation: str = None, weight=None, sources: int = 1,
                 status: str = "resolved", target_name=None,
                 valid_at=None, at: str = None) -> dict:
    spec = RELATION_TYPES[rel_type]
    if generation is None:
        generation = spec["generation"]
    if weight is None:
        weight = spec["weight"]
    floor = PROTECTED_RELATION_FLOOR.get(rel_type)
    if floor is not None and weight < floor:
        weight = floor
    return {
        "relation_id": derive_relation_id(rel_type, from_id,
                                          to_id or target_name or ""),
        "type": rel_type,
        "from_id": from_id,
        "to_id": to_id,
        "target_name": target_name,
        "weight": weight,
        "sources": sources,
        "generation": generation,
        "status": status,
        "valid_at": valid_at,
        "invalid_at": None,
        "stale_endpoint": None,
        "provenance": provenance,
        "created_at": at or utcnow(),
    }


def new_dispute(dispute_id: str, object_id: str, slot: str, fact_ids,
                provenance: dict, *, nominated_by: str = "",
                rationale: str = "", at: str = None) -> dict:
    """争议账条目（MM-15）：只登记不裁决，事实本体一字不动。"""
    return {
        "dispute_id": dispute_id,
        "object_id": object_id,
        "slot": slot,
        "fact_ids": list(fact_ids),
        "nominated_by": nominated_by,
        "rationale": rationale,
        "status": "open",
        "resolution": None,
        "created_at": at or utcnow(),
        "provenance": provenance,
    }


def check_interval(fact: dict) -> list:
    """双时间合法性：invalid_at 不得早于 valid_at；expired 不得早于 created。"""
    errs = []
    valid = parse_time(fact.get("valid_at"))
    invalid = parse_time(fact.get("invalid_at"))
    if valid is not None and invalid is not None and invalid < valid:
        errs.append(f"事实 {fact.get('fact_id')}：invalid_at 早于 valid_at")
    created = parse_time(fact.get("created_at"))
    expired = parse_time(fact.get("expired_at"))
    if created is not None and expired is not None and expired < created:
        errs.append(f"事实 {fact.get('fact_id')}：expired_at 早于 created_at")
    return errs


def intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    """半开区间 [start, end) 是否重叠（MM-10 区间算术的唯一实现）。

    end 为 None 表示开区间（至今有效）。边界相接（a_end == b_start）
    不算重叠——两个事实可以在不同时段同真。
    """
    from datetime import datetime, timezone
    inf = datetime.max.replace(tzinfo=timezone.utc)
    a_s, b_s = parse_time(a_start), parse_time(b_start)
    a_e = parse_time(a_end) or inf
    b_e = parse_time(b_end) or inf
    if a_s is None or b_s is None:
        return False
    return a_s < b_e and b_s < a_e

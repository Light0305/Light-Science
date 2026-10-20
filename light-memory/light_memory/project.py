"""记忆项目的文件群落盘：init 建骨架、load/save 读写四账与登记头。

一个记忆项目 = 一个目录（项目内 <项目>/memory/，或用户级记忆根）：

    memory.yaml        登记头（权威）：项目标识、隔离范围、嵌入提供者
                       登记、水位线、索引状态摘要、机械计数
    objects.jsonl      对象注册（只增）：消费上游既有 ID（MM-01）
    events.jsonl       事件层（只增）：一切状态跃迁在此落痕
    facts.jsonl        事实层（现行状态文件）：双时间 + 取代指针；每次
                       变更由沉淀/裁决命令执行并同步落一条事件
    relations.jsonl    关系层（现行状态文件）：八类关系 + 前向引用
    disputes.jsonl     争议账：只登记不裁决（MM-15）
    promotions.jsonl   晋升账（Phase 2 通道，本期只建空账）
    registry-view.json 对象注册统一视图的只读导出（总控预留消费方）
    notes/             笔记层（Phase 2 沉淀模板产出，本期建目录）
    candidates/        判断性提炼候选区（Phase 2，本期建目录）
    profile/           画像视图（Phase 2，本期建目录）
    obsidian/          Obsidian 投影视图（Phase 2，本期建目录）
    .index/            索引层（唯一可整删目录）：FTS5 + 向量 + 同步台账

铁律（MM-03）：.index 之外任何文件丢失都算数据事故，不许以「重建」
话术掩盖；.index 之内不许出现真相的唯一副本。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import dump_jsonl, dump_yaml, load_structured, read_jsonl, utcnow

FILES = {
    "memory": "memory.yaml",
    "objects": "objects.jsonl",
    "events": "events.jsonl",
    "facts": "facts.jsonl",
    "relations": "relations.jsonl",
    "disputes": "disputes.jsonl",
    "promotions": "promotions.jsonl",
    "registry_view": "registry-view.json",
}

DIRS = ("notes", "candidates", "profile", "obsidian", ".index")

#: 真相文件清单（索引台账与校验对账的范围；memory.yaml 是登记头、
#: 由各命令维护，不入索引清单以免自引用漂移）。
TRUTH_FILES = ("objects.jsonl", "events.jsonl", "facts.jsonl",
               "relations.jsonl", "disputes.jsonl", "promotions.jsonl")


def pkg_path(root, name: str) -> Path:
    return Path(root) / name


def init_package(root, project_id: str = "", title: str = "",
                 scope: str = "project") -> Path:
    """在 root 处建记忆项目骨架；memory_id 取目录名。已存在则拒绝覆盖。"""
    root = Path(root)
    if (root / FILES["memory"]).exists():
        raise FileExistsError(f"记忆项目已存在：{root / FILES['memory']}")
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    memory_id = root.name
    dump_yaml(root / FILES["memory"],
              schema.new_memory(memory_id, project_id=project_id,
                                title=title, scope=scope))
    for key in ("objects", "events", "facts", "relations", "disputes",
                "promotions"):
        dump_jsonl(root / FILES[key], [])
    return root


def load_package(root) -> dict:
    """读整个记忆项目为 dict；缺文件记 None（校验器负责点名）。"""
    root = Path(root)
    pkg = {"root": root}
    for key, name in FILES.items():
        p = root / name
        if not p.exists():
            pkg[key] = None
        elif name.endswith(".jsonl"):
            pkg[key] = read_jsonl(p)
        elif name.endswith(".json"):
            pkg[key] = load_structured(p)
        else:
            pkg[key] = load_structured(p)
    return pkg


def save_memory(root, memory: dict) -> None:
    memory["updated_at"] = utcnow()
    dump_yaml(Path(root) / FILES["memory"], memory)


def save_objects(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["objects"], rows)


def save_events(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["events"], rows)


def save_facts(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["facts"], rows)


def save_relations(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["relations"], rows)


def save_disputes(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["disputes"], rows)


def refresh_counts(memory: dict, pkg: dict) -> dict:
    """汇总计数由工具机械汇总，不许手填。"""
    disputes = pkg.get("disputes") or []
    memory["counts"] = {
        "objects": len(pkg.get("objects") or []),
        "events": len(pkg.get("events") or []),
        "facts": len(pkg.get("facts") or []),
        "relations": len(pkg.get("relations") or []),
        "disputes_open": sum(1 for d in disputes
                             if d.get("status") == "open"),
    }
    return memory["counts"]


def save_promotions(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["promotions"], rows)


def drop_phase2_pending(root, memory: dict, prefix: str) -> list:
    """Phase 2 落地一件摘除一件：按条目前缀从 pending 登记摘除。

    由 Phase 2 命令在成功执行后调用（登记头是唯一权威，待办状态
    随落地事实走，不靠文档口头宣布）。
    """
    pending = memory.get("phase2_pending") or []
    kept = [p for p in pending if not p.startswith(prefix)]
    if len(kept) != len(pending):
        memory["phase2_pending"] = kept
        save_memory(root, memory)
    return kept


def next_seq(events) -> int:
    return (max((e.get("seq") or 0 for e in events), default=0) + 1)


def append_events(root, pkg: dict, new_rows) -> list:
    """给事件账追加行（自动续 seq 与 event_id），返回落盘后的全账。"""
    events = list(pkg.get("events") or [])
    seq = next_seq(events)
    for row in new_rows:
        row["seq"] = seq
        row["event_id"] = f"EV-{seq:06d}"
        events.append(row)
        seq += 1
    save_events(root, events)
    pkg["events"] = events
    return events

"""候选通道（M3 判断性提炼段，MM-13c）+ Review 蒸馏双向接口。

纪律锚点（LEARNING.md / REDESIGN-DRAFT.md）：
- MM-13 三段制：捕获与确定性提炼全自动（走一期 intake），判断性提炼
  （教训归纳、结论性合并、技能/模式蒸馏）只产候选——候选存放在
  candidates/ 区，人工 accept 是独立生效动作，reject 留痕不删。
  通道分工在代码层分开：本模块是判断性提炼的唯一入口，它的 accept
  才许触碰事实层（经一期判定落账）；intake 不读候选区。
- 蒸馏双向接口（草案 §5.1）：内容 schema 八字段定版；distill-export
  按 Review 覆盖层格式产出、只供最新冻结版（每 rule_id 只出最新
  version）；Review 侧回流的双存条目走候选门收编，不直入语料库。

候选账 candidates/candidates.jsonl 是现行状态文件（命令重写），
已生效的蒸馏语料另存 candidates/distill-corpus.jsonl（只增）。
"""

from __future__ import annotations

import copy
from pathlib import Path

from . import project as project_mod, schema
from . import supersede
from .util import component_hash, dump_json, dump_jsonl, load_structured, \
    read_jsonl, utcnow

CANDIDATES_FILE = "candidates.jsonl"
CORPUS_FILE = "distill-corpus.jsonl"
EXPORT_FILE = "distill-export.json"

#: 判断性提炼候选的封闭类型表。确定性提炼不在此列——它走 intake，
#: 不许借候选通道绕行（通道分工的代码层分界）。
CANDIDATE_KINDS = ("fact", "distill_rule", "annotation", "promotion")

CANDIDATE_STATUSES = ("pending", "accepted", "rejected")

#: 蒸馏条目内容 schema 八字段（草案 §5.1 定版，与 Review 条目卡对齐）。
DISTILL_FIELDS = ("rule_id", "statement_faithful", "statement_normalized",
                  "source_class", "explicit_or_inferred", "provenance_ptr",
                  "scope", "distilled_at", "version")

DISTILL_SOURCE_CLASSES = ("对象显式", "对象推导", "历史校准", "通用质量")

#: fact 类候选 accept 后果中视为执行失败的结果（候选保持 pending）。
FACT_ACCEPT_FAILURES = ("rejected_unknown_verdict",
                        "rejected_incomplete_fact",
                        "rejected_target_missing", "rejected_same_fact",
                        "blocked_no_timestamps", "operator_forbidden",
                        "cycle_rejected")


class CandidateError(Exception):
    """候选操作被拒。gaps 为逐条人读原因。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 账本 IO

def ledger_path(root) -> Path:
    return Path(root) / "candidates" / CANDIDATES_FILE


def corpus_path(root) -> Path:
    return Path(root) / "candidates" / CORPUS_FILE


def load_candidates(root) -> list:
    return read_jsonl(ledger_path(root))


def save_candidates(root, rows) -> None:
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    dump_jsonl(p, rows)


def load_corpus(root) -> list:
    return read_jsonl(corpus_path(root))


def _save_corpus(root, rows) -> None:
    p = corpus_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    dump_jsonl(p, rows)


def _candidate_id(kind: str, content: dict, nominator: str) -> str:
    digest = component_hash({"kind": kind, "content": content,
                             "nominator": nominator})
    return f"cand_{digest[:12]}"


def _prov(root_pkg, candidate_id: str, anchor) -> dict:
    return schema.make_provenance(
        "light-memory", "candidates", anchor or candidate_id,
        component_hash({"candidate": candidate_id}))


def _log_event(root, pkg, event_type: str, summary: str, prov: dict,
               payload: dict) -> None:
    row = schema.new_event(0, event_type, summary, prov, payload=payload)
    project_mod.append_events(root, pkg, [row])


# ---------------------------------------------------------------- 提名

def distill_entry_gaps(entry) -> list:
    """蒸馏条目八字段校验（提名与回流收编共用同一把尺）。"""
    if not isinstance(entry, dict):
        return ["蒸馏条目不是对象"]
    gaps = [f"蒸馏条目缺字段：{f}" for f in DISTILL_FIELDS
            if entry.get(f) is None or entry.get(f) == ""]
    eoi = entry.get("explicit_or_inferred")
    if isinstance(eoi, dict):
        if eoi.get("mode") not in ("Explicit", "Inferred"):
            gaps.append("explicit_or_inferred.mode 须为 Explicit 或 "
                        "Inferred")
        conf = eoi.get("confidence")
        if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            gaps.append("explicit_or_inferred.confidence 须为 0 至 1 "
                        "的数值")
    elif eoi is not None and eoi != "":
        gaps.append("explicit_or_inferred 须为含 mode 与 confidence "
                    "的对象")
    if entry.get("source_class") not in (None, "") and \
            entry.get("source_class") not in DISTILL_SOURCE_CLASSES:
        gaps.append(f"source_class 不在四分词表内："
                    f"{entry.get('source_class')}")
    scope = entry.get("scope")
    if isinstance(scope, dict) and scope.get("priority") is not None and \
            scope.get("priority") not in ("overlay_wins", "core_wins"):
        gaps.append("scope.priority 须为 overlay_wins 或 core_wins"
                    "（与通用核心冲突时的优先序）")
    return gaps


def propose(root, kind: str, content: dict, *, nominator: str,
            confidence=None, basis=None, rationale: str = "",
            origin: str = "local") -> dict:
    """提名一条判断性候选（只产候选，绝不直接入账）。

    幂等：同 kind + 内容 + 提名者的候选已在 pending 时返回既有行；
    已被 accept/reject 的同内容再提名视为新一轮，生成新行（带轮次）。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise CandidateError([f"记忆项目不存在或缺登记头：{root}"])
    if kind not in CANDIDATE_KINDS:
        raise CandidateError(
            [f"候选类型不在判断性词表内：{kind}（可选："
             f"{'、'.join(CANDIDATE_KINDS)}；确定性提炼走 intake，"
             "不许借候选通道）"])
    if not nominator:
        raise CandidateError(["提名者必填：候选须可归因"])
    if confidence is not None and \
            not (isinstance(confidence, (int, float))
                 and 0 <= confidence <= 1):
        raise CandidateError(["置信须为 0 至 1 的数值"])
    if not isinstance(content, dict) or not content:
        raise CandidateError(["候选内容不能为空"])
    if kind == "fact":
        nom = content.get("nomination") or {}
        if nom.get("verdict") not in schema.VERDICTS:
            raise CandidateError(
                ["fact 类候选须带 nomination.verdict（五值词表内）"])
        if nom.get("verdict") != "skip" and not \
                (nom.get("fact") or {}).get("statement"):
            raise CandidateError(
                ["fact 类候选须带 nomination.fact.statement 草稿"])
    if kind == "distill_rule":
        gaps = distill_entry_gaps(content.get("entry"))
        if gaps:
            raise CandidateError(gaps)
    if kind == "annotation" and not (content.get("text") or "").strip():
        raise CandidateError(["annotation 类候选须带标注原文 text"])

    rows = load_candidates(root)
    cid = _candidate_id(kind, content, nominator)
    for row in rows:
        if row.get("candidate_id") == cid and \
                row.get("status") == "pending":
            return row
    if any(r.get("candidate_id") == cid for r in rows):
        cid = f"{cid}-r{sum(1 for r in rows if r.get('candidate_id', '').startswith(cid)) + 1}"
    row = {
        "candidate_id": cid,
        "kind": kind,
        "status": "pending",
        "content": content,
        "basis": list(basis or []),
        "rationale": rationale,
        "nominator": nominator,
        "confidence": confidence,
        "origin": origin,
        "created_at": utcnow(),
        "decided_at": None,
        "decided_by": None,
        "decision_note": None,
        "result_ref": None,
    }
    rows.append(row)
    save_candidates(root, rows)
    _log_event(root, pkg, "candidate",
               f"候选提名 {cid}（{kind}，提名：{nominator}）",
               _prov(pkg, cid, (basis or [None])[0]),
               {"candidate_id": cid, "kind": kind, "action": "proposed",
                "origin": origin})
    return row


def list_candidates(root, *, status: str = None, kind: str = None) -> list:
    rows = load_candidates(root)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return rows


def get_candidate(root, candidate_id: str):
    for row in load_candidates(root):
        if row.get("candidate_id") == candidate_id:
            return row
    return None


# ---------------------------------------------------------------- 裁决

def set_decision(root, candidate_id: str, status: str, *, by: str,
                 note: str = "", result_ref=None) -> dict:
    """落裁决（accept/reject 的公共尾段；promote 确认亦经此落痕）。"""
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise CandidateError([f"记忆项目不存在或缺登记头：{root}"])
    rows = load_candidates(root)
    row = next((r for r in rows if r.get("candidate_id") == candidate_id),
               None)
    if row is None:
        raise CandidateError([f"候选不存在：{candidate_id}"])
    if row.get("status") != "pending":
        raise CandidateError(
            [f"候选 {candidate_id} 已裁决（{row.get('status')}），"
             "不许重复裁决"])
    if status not in ("accepted", "rejected"):
        raise CandidateError([f"未知裁决状态：{status}"])
    row["status"] = status
    row["decided_at"] = utcnow()
    row["decided_by"] = by
    row["decision_note"] = note
    if result_ref is not None:
        row["result_ref"] = result_ref
    save_candidates(root, rows)
    _log_event(root, pkg, "candidate",
               f"候选 {candidate_id} 裁决：{status}（{by}）",
               _prov(pkg, candidate_id, candidate_id),
               {"candidate_id": candidate_id, "action": status,
                "by": by, "result_ref": result_ref})
    return row


def reject(root, candidate_id: str, *, by: str, note: str = "") -> dict:
    """驳回候选：留痕不删，行保留在账内可查（MM-13c）。"""
    return set_decision(root, candidate_id, "rejected", by=by, note=note)


def accept(root, candidate_id: str, *, by: str, note: str = "") -> dict:
    """人工生效（独立动作）：按候选类型执行入账，失败则候选保持
    pending 并逐项点名，不许半生效冒充完成。

    - fact：经一期判定落账（提名归模型、执行归代码，MM-10）；
    - distill_rule：条目入已生效蒸馏语料（distill-corpus.jsonl）；
    - annotation：标注原文落一条 annotation 事件（MM-29 的判定段）；
    - promotion：须走 promote confirm（要跨包复制，本函数拒绝代办）。
    """
    root = Path(root)
    row = get_candidate(root, candidate_id)
    if row is None:
        raise CandidateError([f"候选不存在：{candidate_id}"])
    if row.get("status") != "pending":
        raise CandidateError(
            [f"候选 {candidate_id} 已裁决（{row.get('status')}），"
             "不许重复裁决"])
    kind = row.get("kind")
    content = row.get("content") or {}
    result_ref = None

    if kind == "promotion":
        raise CandidateError(
            ["promotion 类候选须走 promote confirm 执行跨包复制，"
             "不许在候选通道内直接生效"])

    if kind == "fact":
        nom = copy.deepcopy(content.get("nomination") or {})
        nom["nominator"] = row.get("nominator") or nom.get("nominator")
        if not nom.get("rationale"):
            nom["rationale"] = row.get("rationale") or ""
        outcomes = supersede.apply_nominations(root, [nom])
        outcome = outcomes[0]
        if outcome.get("result") in FACT_ACCEPT_FAILURES:
            raise CandidateError(
                [f"判定执行未生效：{outcome.get('result')}"
                 "（候选保持 pending，请修正后重试或 reject）"])
        result_ref = outcome.get("fact_id") or outcome.get("dispute_id")

    elif kind == "distill_rule":
        entry = copy.deepcopy(content.get("entry") or {})
        corpus = load_corpus(root)
        entry.setdefault("frozen_via", candidate_id)
        corpus.append(entry)
        _save_corpus(root, corpus)
        result_ref = entry.get("rule_id")

    elif kind == "annotation":
        pkg = project_mod.load_package(root)
        prov = schema.make_provenance(
            "light-memory", "candidates",
            content.get("vault_note") or candidate_id,
            component_hash(content))
        event_row = schema.new_event(
            0, "annotation",
            f"视图标注生效：{(content.get('text') or '')[:60]}",
            prov, object_id=content.get("object_id"),
            payload={"text": content.get("text"),
                     "vault_note": content.get("vault_note"),
                     "candidate_id": candidate_id})
        events = project_mod.append_events(root, pkg, [event_row])
        result_ref = events[-1].get("event_id")

    return set_decision(root, candidate_id, "accepted", by=by, note=note,
                        result_ref=result_ref)


# ---------------------------------------------------------------- 蒸馏接口

def latest_corpus(root) -> list:
    """已生效蒸馏语料的最新冻结版视图：每 rule_id 只取最大 version。"""
    best: dict[str, dict] = {}
    for entry in load_corpus(root):
        rid = entry.get("rule_id")
        if rid is None:
            continue
        cur = best.get(rid)
        if cur is None or (entry.get("version") or 0) >= \
                (cur.get("version") or 0):
            best[rid] = entry
    return [best[k] for k in sorted(best)]


def distill_export(root, out=None) -> dict:
    """按 Review 覆盖层格式导出已生效蒸馏语料（只供最新冻结版）。

    导出形态与 Review 领域门覆盖层的加载口径对齐：条目八字段平铺，
    explicit_or_inferred 拆 mode + confidence 两键、附 precedence
    （由 scope.priority 给出），Review 侧以其加载校验消费。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise CandidateError([f"记忆项目不存在或缺登记头：{root}"])
    entries = []
    for e in latest_corpus(root):
        eoi = e.get("explicit_or_inferred") or {}
        scope = e.get("scope") or {}
        entries.append({
            "rule_id": e.get("rule_id"),
            "statement_faithful": e.get("statement_faithful"),
            "statement_normalized": e.get("statement_normalized"),
            "source_class": e.get("source_class"),
            "explicit_or_inferred": eoi.get("mode"),
            "confidence": eoi.get("confidence"),
            "provenance_ptr": e.get("provenance_ptr"),
            "scope": scope,
            "precedence": scope.get("priority"),
            "distilled_at": e.get("distilled_at"),
            "version": e.get("version"),
        })
    doc = {
        "kind": "light-memory/distill-export",
        "format": "review-overlay",
        "version": "1.0",
        "memory_id": pkg["memory"].get("memory_id"),
        "exported_at": utcnow(),
        "entries": entries,
    }
    out_path = Path(out) if out else \
        Path(root) / "candidates" / EXPORT_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(out_path, doc)
    return {"path": str(out_path), "count": len(entries), "doc": doc}


def _normalize_distill_entry(entry):
    """回流条目归一化：覆盖层压平形 → 内部八字段形。

    distill-export 为 Review 加载口径把 explicit_or_inferred 压平为
    mode + confidence 两键、precedence 单列；Review 侧回流可能带
    压平形，也可能带内部八字段形——收编口同时接受两形，归一后
    再走同一把八字段尺校验。
    """
    if not isinstance(entry, dict):
        return entry
    e = copy.deepcopy(entry)
    eoi = e.get("explicit_or_inferred")
    if isinstance(eoi, str):
        e["explicit_or_inferred"] = {
            "mode": eoi, "confidence": e.get("confidence")}
    e.pop("confidence", None)
    scope = e.get("scope")
    if e.get("precedence") is not None:
        if not isinstance(scope, dict):
            scope = {}
        scope.setdefault("priority", e.pop("precedence"))
        e["scope"] = scope
    else:
        e.pop("precedence", None)
    return e


def distill_import(root, path, *, nominator: str) -> list:
    """收编 Review 侧回流的双存条目：只产候选，走候选门不直入语料。

    输入接受导出文档形态（{entries: [...]}）或裸条目列表，条目可为
    内部八字段形或覆盖层压平形（先归一化）；逐条按八字段校验，
    缺字段的整条点名拒绝，不许半收编。
    """
    root = Path(root)
    data = load_structured(path)
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries:
        raise CandidateError([f"回流文件无条目：{path}"])
    entries = [_normalize_distill_entry(e) for e in entries]
    gaps = []
    for i, e in enumerate(entries):
        gaps += [f"第 {i + 1} 条：{g}" for g in distill_entry_gaps(e)]
    if gaps:
        raise CandidateError(gaps)
    created = []
    for e in entries:
        created.append(propose(
            root, "distill_rule", {"entry": e}, nominator=nominator,
            basis=[e.get("provenance_ptr")],
            rationale="Review 侧回流双存条目收编（走候选门）",
            origin="review_return"))
    return created

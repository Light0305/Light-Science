"""领域门三层（R3/RV-16/RV-17）：通用轴地板 + 按刊事实层 + 蒸馏覆盖层。

第零层范式判定（v1.1，REV-D01）：intake 后、领域判定前在登记头落
paradigm 登记（词表 methods/empirical/benchmark/theory/humanities +
判定依据）。范式是定性权重层不是判定层——只调两处：覆盖层条目的
适用性（paradigms 字段）与席位定性权重的规程指引（SKILL 5B 第零
层）；不动法医层、不动代码计分与封顶（回归测试钉死跨范式法医
产物逐字一致）。检索式多形（REV-D08）：DG-J05 条目卡登记多形
列表，匹配走归一化文本，命中口径不变。

纪律：
- 通用轴恒加载（地板）：条目带条目卡五元数据（稳定 ID / 出处 /
  严重度 / 范围 / 执行层），来源四分标 generic_quality，不许伪装
  成按刊事实；
- 按刊事实层只读同一事实源：经 intake 指针读 Journal-Select 核查
  记录 / Write 模板记录（九组记录）原件，不复制第三份数据。事实
  时效按 H 组 verified_at + review_cycle_days（缺省 180 天，与
  Write 过期口径同构）判：过期或无核查日期 → fact_status 落
  UNVERIFIED，该层全部条目结果强制 not_applicable——过期事实不许
  驱动判定（RV-17）；
- 蒸馏覆盖层 v1 只落格式与加载校验：覆盖层文件须含来源四分标注、
  双存指针、与核心冲突优先序；条目检查只许三种确定性机械检查。
  冲突解析（overrides + precedence）在落盘时由代码完成，校验器
  重算钉死；
- 开跑前先验承接快照：上游漂移即 STALE 拒绝（与法医层同纪律）。

产物 domain_gate.jsonl：逐条 {item_id, layer, result(hit/miss/
not_applicable), evidence_pointer, fact?} + 边级覆盖自报 summary 行。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import schema
from .intake import snapshot_drift
from .project import clear_pending, load_package, save_domain_gate, save_review
from .util import load_structured, sha256_file, today

# 通用轴地板（恒加载）：IEEE 评审七轴投影 + 包内登记纪律。
# 每条 = 条目卡五元数据 + 确定性判定函数名（_UNIVERSAL_CHECKS 分发）。
UNIVERSAL_ITEMS = [
    {"item_id": "DG-U01", "axis": "Validity",
     "title": "每个主张都登记了证据指针（evidence_refs 非空）",
     "severity_if_hit": "major", "scope": "claims_register",
     "tier": "deterministic", "check": "claims_have_evidence"},
    {"item_id": "DG-U02", "axis": "Data",
     "title": "每个登记数字都有溯源（trace_ref + calc_provenance）",
     "severity_if_hit": "major", "scope": "numbers_ledger",
     "tier": "deterministic", "check": "numbers_have_provenance"},
    {"item_id": "DG-U03", "axis": "Compliance",
     "title": "引用条目的撤稿状态全部已登记（非 unknown/缺失）",
     "severity_if_hit": "major", "scope": "references.lock",
     "tier": "deterministic", "check": "retraction_states_known"},
    {"item_id": "DG-U04", "axis": "Clarity",
     "title": "每幅登记图都有图注（caption 非空）",
     "severity_if_hit": "minor", "scope": "figures_manifest",
     "tier": "deterministic", "check": "figures_have_captions"},
    {"item_id": "DG-U05", "axis": "Structure",
     "title": "章节结构齐备（方法类与结果类章节都在）",
     "severity_if_hit": "minor", "scope": "sections",
     "tier": "deterministic", "check": "section_structure"},
]

# 按刊事实层条目（自九组记录 D/C/G 组派生；记录无该字段 → 不适用）
JOURNAL_ITEMS = [
    {"item_id": "DG-J01", "field": ("D", "word_limit_total"),
     "axis": "Compliance", "title": "全文词数不超目标刊限额",
     "severity_if_hit": "major"},
    {"item_id": "DG-J02", "field": ("D", "word_limit_abstract"),
     "axis": "Compliance", "title": "摘要词数不超目标刊限额",
     "severity_if_hit": "minor"},
    {"item_id": "DG-J03", "field": ("D", "figure_limit"),
     "axis": "Compliance", "title": "图数不超目标刊限额",
     "severity_if_hit": "minor"},
    {"item_id": "DG-J04", "field": ("D", "reference_limit"),
     "axis": "Compliance", "title": "参考文献数不超目标刊限额",
     "severity_if_hit": "minor"},
    {"item_id": "DG-J05", "field": ("G", "ai_policy"),
     "axis": "Compliance", "title": "目标刊要求 AI 披露时稿件带披露声明",
     "severity_if_hit": "major",
     # 检索多形列表（v1.1 REV-D08）：单条正则对措辞形态敏感（演示
     # DG-J05 实测：披露标题 Declaration of AI Use 不在检索式内而
     # 误判 hit）。形态登记在条目卡上：标题同义形 + 大小写/标点变体
     # （匹配前归一化）+ 双语标题词表 + 正文披露句式。命中口径不变：
     # hit = 要求披露而多形检索仍未检出，须人工复核的旗标。
     "match_forms": [
         # —— 标题同义形（英）
         r"declaration of ai use",
         r"declaration on the use of ai",
         r"ai use declaration",
         r"statement on ai use",
         r"ai disclosure",
         r"disclosure of ai use",
         r"disclosure statement",
         r"declaration of generative ai",
         r"generative ai disclosure",
         r"artificial intelligence disclosure",
         r"declaration of artificial intelligence use",
         # —— 双语标题词表（中）
         r"人工智能使用声明",
         r"人工智能披露声明",
         r"生成式人工智能声明",
         r"生成式人工智能使用声明",
         r"ai 使用声明",
         r"ai使用声明",
         # —— 正文披露句式
         r"ai assisted",
         r"ai generated content",
         r"generated with the assistance of",
         r"prepared with the assistance of ai",
         r"was written with the assistance of",
         r"large language model",
         r"生成式 ai",
         r"生成式ai",
         r"生成式人工智能",
         r"大语言模型",
     ]},
    {"item_id": "DG-J06", "field": ("C", "keyword_limit"),
     "axis": "Compliance", "title": "关键词数不超目标刊限额",
     "severity_if_hit": "minor"},
]

_WORD = re.compile(r"\w+", re.UNICODE)
_TABLE_SEP = re.compile(r"^\|[-: |]+\|$")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """检索归一化（REV-D08）：小写 + 标点/空白折叠为单空格。

    大小写与标点变体（AI-Assisted / ai assisted / AI assisted:）
    归一后同形，形态覆盖靠条目卡的 match_forms 列表而非正则技巧。
    """
    return _NON_WORD.sub(" ", (text or "").lower()).strip()


def match_disclosure(text: str, forms) -> str | None:
    """多形检索：任一形态在归一化文本中命中即返回该形态（否则 None）。"""
    normalized = normalize_text(text)
    for form in forms or []:
        if re.search(form, normalized):
            return form
    return None


class DomainError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def word_count(text: str) -> int:
    """词数口径：Unicode 词元计数（确定性，全包统一）。"""
    return len(_WORD.findall(text or ""))


def _upstream(root, review) -> dict:
    intake = review["intake"]
    mp = Path(intake["manuscript"]["package_path"])
    sections = {}
    sdir = mp / "sections"
    if sdir.is_dir():
        for p in sorted(sdir.glob("*.md")):
            sections[p.name] = p.read_text(encoding="utf-8")
    manuscript = load_structured(mp / "manuscript.yaml") or {}

    def _rows(name, key):
        data = load_structured(mp / name) or {}
        return data.get(key) or []

    lock = load_structured(mp / "references.lock.json") or {}
    return {
        "claims": _rows("claims_register.yaml", "claims"),
        "numbers": _rows("numbers_ledger.yaml", "numbers"),
        "figures": _rows("figures_manifest.yaml", "figures"),
        "lock_entries": lock.get("entries") or [],
        "sections": sections,
        "manuscript": manuscript,
    }


# ---------------------------------------------------------------- 通用轴判定

def _u_claims_have_evidence(up):
    if not up["claims"]:
        return "not_applicable", "无登记主张，本条无对象"
    bad = [c.get("claim_id") for c in up["claims"]
           if not c.get("evidence_refs")]
    if bad:
        return "hit", f"主张缺证据指针：{bad}"
    return "miss", f"{len(up['claims'])} 条主张证据指针齐全"


def _u_numbers_have_provenance(up):
    if not up["numbers"]:
        return "not_applicable", "无登记数字，本条无对象"
    bad = [n.get("num_id") for n in up["numbers"]
           if not n.get("trace_ref") or not n.get("calc_provenance")]
    if bad:
        return "hit", f"数字缺溯源（trace_ref/calc_provenance）：{bad}"
    return "miss", f"{len(up['numbers'])} 个数字溯源齐全"


def _u_retraction_states_known(up):
    if not up["lock_entries"]:
        return "not_applicable", "无引用条目，本条无对象"
    bad = [e.get("key") for e in up["lock_entries"]
           if (e.get("retraction_state") or "unknown") == "unknown"]
    if bad:
        return "hit", f"撤稿状态未登记（unknown）：{bad}"
    return "miss", f"{len(up['lock_entries'])} 条引用撤稿状态已登记"


def _u_figures_have_captions(up):
    if not up["figures"]:
        return "not_applicable", "无登记图，本条无对象"
    bad = [f.get("figure_id") for f in up["figures"]
           if not (f.get("caption") or "").strip()]
    if bad:
        return "hit", f"图缺图注：{bad}"
    return "miss", f"{len(up['figures'])} 幅图图注齐全"


def _u_section_structure(up):
    names = " ".join(up["sections"].keys()).lower()
    if not up["sections"]:
        return "not_applicable", "无章节文件，本条无对象"
    has_method = any(t in names for t in ("method", "方法"))
    has_result = any(t in names for t in ("result", "结果"))
    if has_method and has_result:
        return "miss", "方法类与结果类章节都在"
    missing = [x for x, ok in (("方法类", has_method), ("结果类", has_result))
               if not ok]
    return "hit", f"章节结构缺：{'、'.join(missing)}"


_UNIVERSAL_CHECKS = {
    "claims_have_evidence": _u_claims_have_evidence,
    "numbers_have_provenance": _u_numbers_have_provenance,
    "retraction_states_known": _u_retraction_states_known,
    "figures_have_captions": _u_figures_have_captions,
    "section_structure": _u_section_structure,
}


def run_universal(up) -> list:
    rows = []
    for item in UNIVERSAL_ITEMS:
        result, detail = _UNIVERSAL_CHECKS[item["check"]](up)
        rows.append(schema.domain_check_row(
            item["item_id"], "universal", result,
            axis=item["axis"], title=item["title"],
            severity_if_hit=item["severity_if_hit"],
            evidence_pointer=f"upstream:{item['scope']}",
            detail=detail, source_kind="generic_quality"))
    return rows


# ---------------------------------------------------------------- 按刊事实层

def fact_freshness(record: dict, today_str: str | None = None) -> dict:
    """判事实时效：返回 {verified_at, fact_status, cycle_days, age_days}。

    verified_at 缺失/不可解析/超龄 → unverified（RV-17：查不到或
    过期一律 UNVERIFIED，不许拿过期事实驱动判定）。
    """
    group_h = (record or {}).get("H") or {}
    verified_at = group_h.get("verified_at")
    cycle = group_h.get("review_cycle_days") \
        or schema.FACT_FRESHNESS_DEFAULT_DAYS
    out = {"verified_at": verified_at, "cycle_days": cycle,
           "age_days": None, "fact_status": "unverified"}
    if not verified_at:
        return out
    try:
        vdate = date.fromisoformat(str(verified_at)[:10])
        tdate = date.fromisoformat(today_str) if today_str else date.today()
    except ValueError:
        return out
    age = (tdate - vdate).days
    out["age_days"] = age
    if 0 <= age <= cycle:
        out["fact_status"] = "verified"
    return out


def _journal_value(record, group, field):
    return ((record or {}).get(group) or {}).get(field)


def _j_word_limit_total(up, record):
    limit = _journal_value(record, "D", "word_limit_total")
    total = sum(word_count(t) for t in up["sections"].values())
    return ("hit" if total > limit else "miss",
            f"全文词数 {total} vs 限额 {limit}")


def _j_word_limit_abstract(up, record):
    limit = _journal_value(record, "D", "word_limit_abstract")
    text = None
    for name, t in sorted(up["sections"].items()):
        if "abstract" in name.lower() or "摘要" in name:
            text = t
            break
    if text is None and up["manuscript"].get("abstract"):
        text = str(up["manuscript"]["abstract"])
    if text is None:
        return "not_applicable", "稿件无可识别摘要（无限额可对）"
    n = word_count(text)
    return ("hit" if n > limit else "miss", f"摘要词数 {n} vs 限额 {limit}")


def _j_figure_limit(up, record):
    limit = _journal_value(record, "D", "figure_limit")
    n = len(up["figures"])
    return ("hit" if n > limit else "miss", f"图数 {n} vs 限额 {limit}")


def _j_reference_limit(up, record):
    limit = _journal_value(record, "D", "reference_limit")
    n = len(up["lock_entries"])
    return ("hit" if n > limit else "miss",
            f"参考文献 {n} 条 vs 限额 {limit}")


def _j_ai_policy(up, record):
    policy = _journal_value(record, "G", "ai_policy") or {}
    if not policy.get("disclosure_required"):
        return "not_applicable", "目标刊 AI 政策未要求披露，本条未触发"
    item = next(i for i in JOURNAL_ITEMS if i["item_id"] == "DG-J05")
    forms = item.get("match_forms") or []
    joined = "\n".join(up["sections"].values())
    hit_form = match_disclosure(joined, forms)
    if hit_form:
        return "miss", "目标刊要求 AI 披露，稿件章节中检出披露声明" \
                       f"（多形检索命中形态：{hit_form}）"
    return "hit", "目标刊要求 AI 披露（disclosure_required），" \
                  f"稿件章节经多形检索（条目卡登记 {len(forms)} 形）" \
                  "仍未检出披露声明：命中为须人工复核的旗标，非定罪"


def _j_keyword_limit(up, record):
    limit = _journal_value(record, "C", "keyword_limit")
    keywords = up["manuscript"].get("keywords")
    if not isinstance(keywords, list):
        return "not_applicable", "稿件未登记关键词清单，本条无对象"
    n = len(keywords)
    return ("hit" if n > limit else "miss", f"关键词 {n} 个 vs 限额 {limit}")


_JOURNAL_CHECKS = {
    "DG-J01": _j_word_limit_total,
    "DG-J02": _j_word_limit_abstract,
    "DG-J03": _j_figure_limit,
    "DG-J04": _j_reference_limit,
    "DG-J05": _j_ai_policy,
    "DG-J06": _j_keyword_limit,
}


def run_journal(up, record, record_pointer, freshness) -> list:
    """按刊事实层。record 为 None（未登记目标刊记录）时全条不适用并点名。"""
    rows = []
    verified = freshness["fact_status"] == "verified"
    for item in JOURNAL_ITEMS:
        group, field = item["field"]
        value = _journal_value(record, group, field)
        fact = {"field": f"{group}.{field}", "value": value,
                "verified_at": freshness["verified_at"],
                "fact_status": freshness["fact_status"],
                "cycle_days": freshness["cycle_days"],
                "record_pointer": record_pointer}
        if record is None:
            result, detail = "not_applicable", \
                "未登记目标刊核查记录：按刊事实层无源（如实登记未覆盖）"
        elif value is None:
            result, detail = "not_applicable", \
                f"目标刊记录未登记 {group}.{field}，本条未触发"
        elif not verified:
            result, detail = "not_applicable", \
                "事实 UNVERIFIED（核查日期缺失或已超复核周期）：" \
                "过期事实不许驱动判定（RV-17）"
        elif item["item_id"] != "DG-J05" \
                and not isinstance(value, (int, float)):
            result, detail = "not_applicable", \
                f"记录 {group}.{field} 非数值（{value!r}），无法机械对账"
        else:
            result, detail = _JOURNAL_CHECKS[item["item_id"]](up, record)
        rows.append(schema.domain_check_row(
            item["item_id"], "journal_fact", result,
            axis=item["axis"], title=item["title"],
            severity_if_hit=item["severity_if_hit"],
            evidence_pointer=f"{record_pointer}#{group}.{field}"
            if record_pointer else None,
            detail=detail, source_kind="explicit_object", fact=fact))
    return rows


# ---------------------------------------------------------------- 蒸馏覆盖层

def load_overlay(path) -> dict:
    """加载并校验覆盖层文件（格式纪律 RV-16：来源四分/双存/优先序）。

    v1 只落格式与加载校验，不预置任何学科内容；检查种类只许
    schema.OVERLAY_CHECK_KINDS 三种确定性机械检查。
    """
    p = Path(path)
    if not p.exists():
        raise DomainError([f"覆盖层文件不存在：{p}"])
    try:
        overlay = load_structured(p)
    except Exception as e:
        raise DomainError([f"覆盖层文件不可解析：{e}"])
    if not isinstance(overlay, dict):
        raise DomainError(["覆盖层文件须为结构化对象"])
    gaps = []
    if not overlay.get("overlay_id"):
        gaps.append("覆盖层缺 overlay_id")
    source = overlay.get("source") or {}
    if source.get("kind") not in schema.SOURCE_KINDS:
        gaps.append(f"覆盖层 source.kind {source.get('kind')!r} "
                    f"不在来源四分词表 {schema.SOURCE_KINDS}")
    if not source.get("ref"):
        gaps.append("覆盖层 source.ref 缺失（来源须可指认）")
    if not source.get("checked_at"):
        gaps.append("覆盖层 source.checked_at 缺失（来源须带核查日期，RV-16a）")
    if not (overlay.get("dual_store_pointer") or "").strip():
        gaps.append("覆盖层缺 dual_store_pointer（蒸馏双存：保真形态存档"
                    "指针必填，RV-16）")
    precedence = (overlay.get("precedence") or {}).get("on_conflict")
    if precedence not in schema.OVERLAY_PRECEDENCE:
        gaps.append(f"覆盖层 precedence.on_conflict {precedence!r} "
                    f"不在词表 {schema.OVERLAY_PRECEDENCE}"
                    "（与核心冲突的优先序必须写明，RV-16c）")
    seen = set()
    for item in overlay.get("items") or []:
        iid = item.get("item_id")
        if not iid or iid in seen:
            gaps.append(f"覆盖层条目 item_id 缺失或重复：{iid!r}")
        seen.add(iid)
        if not str(item.get("title") or item.get("statement") or "").strip():
            gaps.append(f"覆盖层条目 {iid} 缺条目陈述（title/statement）："
                        "条目卡无陈述不许加载（RV-16）")
        if item.get("source_kind") not in schema.SOURCE_KINDS:
            gaps.append(f"覆盖层条目 {iid} 的 source_kind "
                        f"{item.get('source_kind')!r} 不在来源四分词表")
        if item.get("explicit_or_inferred") not in schema.EXPLICITNESS:
            gaps.append(f"覆盖层条目 {iid} 缺 Explicit-or-Inferred 标记")
        conf = item.get("confidence")
        if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            gaps.append(f"覆盖层条目 {iid} 的 confidence 须为 0–1 数值")
        if item.get("severity_if_hit") not in schema.SEVERITIES:
            gaps.append(f"覆盖层条目 {iid} 的 severity_if_hit 不在严重度词表")
        paradigms = item.get("paradigms")
        if paradigms is not None:
            if not isinstance(paradigms, list) or not paradigms:
                gaps.append(f"覆盖层条目 {iid} 的 paradigms 须为非空列表"
                            "（范式适用性字段，REV-D01/D12 预留位）")
            else:
                bad = [p for p in paradigms if p not in schema.PARADIGMS]
                if bad:
                    gaps.append(f"覆盖层条目 {iid} 的 paradigms 含词表外"
                                f"范式 {bad}（词表 {schema.PARADIGMS}）")
        chk = item.get("check") or {}
        if chk.get("kind") not in schema.OVERLAY_CHECK_KINDS:
            gaps.append(f"覆盖层条目 {iid} 的 check.kind {chk.get('kind')!r} "
                        f"不在机械检查词表 {schema.OVERLAY_CHECK_KINDS}")
        if chk.get("kind") in ("keyword_present", "keyword_absent") \
                and not chk.get("keywords"):
            gaps.append(f"覆盖层条目 {iid} 的 check.keywords 为空")
        if chk.get("kind") == "section_present" and not chk.get("tokens"):
            gaps.append(f"覆盖层条目 {iid} 的 check.tokens 为空")
    if gaps:
        raise DomainError(gaps)
    return overlay


def _overlay_check(up, chk) -> tuple[str, str]:
    kind = chk.get("kind")
    joined = "\n".join(up["sections"].values()).lower()
    if kind == "keyword_present":
        found = [k for k in chk["keywords"] if k.lower() in joined]
        if found:
            return "miss", f"应出现的关键词已出现：{found}"
        return "hit", f"应出现的关键词一个未出现：{chk['keywords']}"
    if kind == "keyword_absent":
        found = [k for k in chk["keywords"] if k.lower() in joined]
        if found:
            return "hit", f"不应出现的关键词出现：{found}"
        return "miss", "禁用关键词均未出现"
    if kind == "section_present":
        names = " ".join(up["sections"].keys()).lower()
        found = [t for t in chk["tokens"] if t.lower() in names]
        if found:
            return "miss", f"应有章节已在：{found}"
        return "hit", f"应有章节缺失（文件名无 {chk['tokens']} 任一）"
    return "not_applicable", f"未知检查种类 {kind!r}"


def run_overlay(up, overlay, paradigm=None) -> list:
    rows = []
    for item in overlay.get("items") or []:
        applicable = item.get("paradigms")
        if applicable and paradigm is not None \
                and paradigm not in applicable:
            # 范式适用性（REV-D01 第零层唯一调节点之一）：登记范式
            # 不在条目适用集内 → 不适用，依据落字到判定行。
            result, detail = "not_applicable", \
                f"范式 {paradigm} 不在条目适用范式 {applicable} 内" \
                "（范式依据见登记头 paradigm 登记，本条按范式不适用）"
        else:
            result, detail = _overlay_check(up, item.get("check") or {})
            if applicable and paradigm is None:
                detail += "；注：条目带范式适用性而本包范式未登记，" \
                          "适用性未按范式过滤（reported 门将点名）"
        rows.append(schema.domain_check_row(
            item["item_id"], "overlay", result,
            axis=item.get("axis"), title=item.get("title"),
            severity_if_hit=item.get("severity_if_hit"),
            overrides=item.get("overrides"),
            evidence_pointer=f"overlay:{overlay.get('overlay_id')}"
                             f"#{item['item_id']}",
            detail=detail, source_kind=item.get("source_kind")))
    return rows


def resolve_overrides(rows, precedence: str) -> list:
    """冲突解析（代码完成，校验器重算）：overlay 条目以 overrides
    指向核心条目时，按 precedence 定谁 effective、谁 superseded。"""
    by_id = {r["item_id"]: r for r in rows if r.get("type") == "domain_check"}
    for row in rows:
        if row.get("type") != "domain_check" or row.get("layer") != "overlay":
            continue
        target_id = row.get("overrides")
        if not target_id or target_id not in by_id:
            continue
        target = by_id[target_id]
        if precedence == "overlay_wins":
            target["effective"] = False
            target["superseded_by"] = row["item_id"]
        else:  # core_wins
            row["effective"] = False
            row["superseded_by"] = target_id
    return rows


def summarize(rows) -> dict:
    checks = [r for r in rows if r.get("type") == "domain_check"]
    by_layer = {}
    for layer in schema.DOMAIN_LAYERS:
        sub = [r for r in checks if r.get("layer") == layer]
        by_layer[layer] = {
            "checked": len(sub),
            "hits": sum(1 for r in sub if r["result"] == "hit"),
            "not_applicable": sum(1 for r in sub
                                  if r["result"] == "not_applicable"),
        }
    return schema.domain_summary_row(
        checked=len(checks),
        hits=sum(1 for r in checks if r["result"] == "hit"),
        misses=sum(1 for r in checks if r["result"] == "miss"),
        not_applicable=sum(1 for r in checks
                           if r["result"] == "not_applicable"),
        effective_hits=sum(1 for r in checks
                            if r["result"] == "hit" and r.get("effective")),
        by_layer=by_layer)


# ---------------------------------------------------------------- 编排

def register_paradigm(review: dict, paradigm, basis, *, by=None,
                      today_str=None) -> dict:
    """范式登记（REV-D01 第零层）：词表 + 依据落字 + 不许静默改写。

    同值重复登记保留原登记（幂等）；异值拒绝——换范式等于换评审
    定性权重基线，必须开新 round，不许在同一轮里悄悄换。
    """
    gaps = []
    if paradigm not in schema.PARADIGMS:
        gaps.append(f"范式 {paradigm!r} 不在词表 {schema.PARADIGMS}")
    if not (basis or "").strip():
        gaps.append("范式登记须带判定依据（basis 落字：凭什么判为此范式）")
    existing = review.get("paradigm")
    if existing and existing.get("paradigm") != paradigm:
        gaps.append(f"范式已登记为 {existing.get('paradigm')}，不许静默"
                    f"改写为 {paradigm}（换范式开新 round）")
    if gaps:
        raise DomainError(gaps)
    if existing:
        return existing
    record = {"paradigm": paradigm, "basis": basis.strip(),
              "registered_at": today_str or today(),
              "registered_by": by or "light-review domain"}
    review["paradigm"] = record
    return record


def run_domain(root, overlay_path=None, today_str=None, paradigm=None,
               paradigm_basis=None, paradigm_by=None) -> dict:
    """跑领域门三层并落 domain_gate.jsonl + 登记头登记。

    落点（状态机不新增状态）：本命令可在 intake 后任意时点重跑；
    结果由 reported 门消费（SKILL §6/§8.1 写明落点与理由）。
    范式（第零层）：以 --paradigm/--paradigm-basis 随本命令登记
    （intake 后、领域判定前落字）；未登记时如实记 paradigm=None，
    条目带范式适用性时另记 paradigm_required（reported 门点名）。
    """
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise DomainError(["评审包不存在（先 init）"])
    if not review.get("intake"):
        raise DomainError(["承接快照未冻结（先 intake）"])
    drift = snapshot_drift(root)
    if drift:
        raise DomainError([f"承接快照漂移（STALE），拒绝在旧快照上跑领域门：{d}"
                           for d in drift])
    if paradigm is not None:
        register_paradigm(review, paradigm, paradigm_basis,
                          by=paradigm_by, today_str=today_str)
    paradigm_value = (review.get("paradigm") or {}).get("paradigm")
    up = _upstream(root, review)

    rows = run_universal(up)

    target = (review["intake"].get("target_journal") or {})
    record = None
    record_pointer = None
    freshness = {"verified_at": None, "fact_status": "unverified",
                 "cycle_days": schema.FACT_FRESHNESS_DEFAULT_DAYS,
                 "age_days": None}
    rec_ref = target.get("record")
    if rec_ref:
        record_pointer = rec_ref.get("path")
        rp = Path(record_pointer)
        if rp.exists():
            record = load_structured(rp) or {}
            freshness = fact_freshness(record, today_str)
    rows += run_journal(up, record, record_pointer, freshness)

    overlay_info = None
    precedence = None
    paradigm_required = bool((review.get("domain") or {})
                             .get("paradigm_required"))
    if overlay_path:
        overlay = load_overlay(overlay_path)
        if any((it.get("paradigms") for it in overlay.get("items") or [])):
            paradigm_required = True
        rows += run_overlay(up, overlay, paradigm=paradigm_value)
        precedence = overlay["precedence"]["on_conflict"]
        rows = resolve_overrides(rows, precedence)
        overlay_info = {
            "overlay_id": overlay.get("overlay_id"),
            "version": overlay.get("version"),
            "path": str(overlay_path),
            "sha256": sha256_file(Path(overlay_path)),
            "precedence": precedence,
            "items": len(overlay.get("items") or []),
        }

    summary = summarize(rows)
    rows = rows + [summary]
    save_domain_gate(root, rows)

    review["domain"] = {
        "ran_at": today_str or today(),
        "paradigm": paradigm_value,
        "paradigm_required": paradigm_required,
        "overlay": overlay_info,
        "fact_source": ({"record_path": record_pointer,
                         "verified_at": freshness["verified_at"],
                         "fact_status": freshness["fact_status"]}
                        if rec_ref else None),
        "summary": {k: summary[k] for k in
                    ("checked", "hits", "misses", "not_applicable",
                     "effective_hits")},
    }
    clear_pending(review, "domain_gate")
    review["updated_at"] = today_str or today()
    save_review(root, review)
    return review["domain"]

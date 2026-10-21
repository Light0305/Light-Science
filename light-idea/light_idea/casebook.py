"""查新判例集（IDEA-D04 冷启动）：已判案例的校准材料库。

设计依据：02-idea/LEARNING.md 约束 1/2 + diagnosis IDEA-D04 修复设计。
落点：<project>/novelty/cases/casebook.jsonl，只增不改，一行一例。

写死的纪律：

- **判定即沉淀**：每次判定落卡（novelty.apply_verdict 成功）自动追加
  一条判例——想法 facet 摘要 + closest 前三条 + 判定 + caution_reason；
- **脱敏口径**：判例是给未来判定者校准的材料，不是收据存根——判定者
  与执行者的模型名、verdict_id 一律不入判例（与 SKILL §8.3「判定者
  不需要执行者的内部信息」同向）；review_status 随条保留，降级
  （REVIEW_UNAVAILABLE）判例明示为暂定结论、校准权重低；
- **种子逐条标源**：冷启动种子随包发布（casebook_seeds.jsonl），每条
  origin=seed 且 source 写明出处类别（真实演示判定 / 测试夹具场景 /
  构建期构造），构造判例不许冒充真实判定；
- **种子标识符核验**：种子内 DOI 逐条经 Crossref 核验题名一致性，
  结果以 identifier_check（via/checked_at/result）随条留痕；错标
  订正保留原值于 result=corrected 的 was 字段（D1 教训：verified
  为 true 也须有标识符级核验支撑，不许只凭题名印象）；
- **只增与幂等**：追加按 case_id 去重，同一判定重复落卡不重复入集；
  历史判例不回改——判定被新收据覆盖时，新判定另成一例。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schema import FACETS, VERDICTS, _nonempty_str, _ref_ok

CASEBOOK_FILENAME = "casebook.jsonl"
MAX_CLOSEST_PER_CASE = 3  # 判例只带 closest 前三条（诊断 D04 口径）


class CasebookError(Exception):
    """判例集读写/校验失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


# ---------------------------------------------------------------------------
# 落点与 id

def casebook_dir(root: Path) -> Path:
    return root / "novelty" / "cases"


def casebook_path(root: Path) -> Path:
    return casebook_dir(root) / CASEBOOK_FILENAME


def make_case_id(idea_id: str, date: str, verdict: str) -> str:
    """判例 id：CB-<sha256(idea_id|日期|判定)[:10]>，与 verdict_id 同法。

    同一判定事件（卡、日期、结论）恒得同一 id，追加去重据此幂等。
    """
    raw = f"{idea_id}|{date}|{verdict}"
    return "CB-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------------------
# 判例构造与校验

def case_from_verdict(card: dict, record: dict) -> dict:
    """从一次已落卡的判定（apply_verdict 的 record）构造判例条目。

    只取校准所需字段：facet 短语摘要、closest 前三条、判定与薄点；
    收据与模型名不入判例（脱敏口径，见模块头）。
    """
    facets = card.get("facets") or {}
    idea_id = card.get("idea_id") or record.get("idea_id") or ""
    verdict = record.get("verdict")
    date = record.get("date") or ""
    closest = []
    for w in (record.get("closest_works") or [])[:MAX_CLOSEST_PER_CASE]:
        closest.append({
            "paper_id": w.get("paper_id"),
            "doi": w.get("doi"),
            "title": w.get("title") or "",
            "year": w.get("year"),
            "collided_facets": list(w.get("collided_facets") or []),
            "delta": w.get("delta") or "",
            "verified": bool(w.get("verified", False)),
        })
    return {
        "case_id": make_case_id(idea_id, date, verdict),
        "date": date,
        "origin": "verdict",
        "source": f"项目内真实判定（idea:{idea_id}）",
        "review_status": record.get("review_status"),
        "idea": {
            "idea_id": idea_id,
            "title": card.get("title") or "",
            "facets": {f: (facets.get(f) or {}).get("phrase") or ""
                       for f in FACETS},
        },
        "closest_works": closest,
        "verdict": verdict,
        "caution_reason": record.get("caution_reason") or "",
        "named_paper": record.get("named_paper"),
    }


def validate_case(case: dict) -> list[str]:
    """判例结构校验，返回错误列表（空 = 合法）。种子与追加共用。"""
    errs: list[str] = []
    if not isinstance(case, dict):
        return ["判例不是结构化记录"]
    if not _nonempty_str(case.get("case_id")):
        errs.append("判例缺 case_id")
    if not _nonempty_str(case.get("date")):
        errs.append("判例缺 date")
    if case.get("origin") not in ("verdict", "seed"):
        errs.append("判例 origin 非法（须为 verdict / seed）")
    if not _nonempty_str(case.get("source")):
        errs.append("判例缺 source 出处标注（逐条标源，不许无源判例）")
    idea = case.get("idea")
    if not isinstance(idea, dict) or not _nonempty_str(idea.get("title")):
        errs.append("判例 idea.title 为空")
    else:
        facets = idea.get("facets") or {}
        for f in FACETS:
            if not _nonempty_str(facets.get(f)):
                errs.append(f"判例 idea.facets.{f} 短语为空（facet 摘要必填）")
    verdict = case.get("verdict")
    if verdict not in VERDICTS:
        errs.append(f"判例 verdict 非法：{verdict!r}（须为 {VERDICTS} 之一）")
    if verdict == "PROCEED_WITH_CAUTION" \
            and not _nonempty_str(case.get("caution_reason")):
        errs.append("CAUTION 判例须带 caution_reason（薄点说明是校准材料"
                    "的核心，说不出薄点当时就该判 PROCEED）")
    closest = case.get("closest_works")
    if not isinstance(closest, list):
        errs.append("判例 closest_works 必须是列表")
        closest = []
    if len(closest) > MAX_CLOSEST_PER_CASE:
        errs.append(f"判例 closest_works 超过 {MAX_CLOSEST_PER_CASE} 条"
                    f"（判例只带最接近的前三条）")
    for i, w in enumerate(closest):
        if not isinstance(w, dict) or not _ref_ok(w):
            errs.append(f"判例 closest_works[{i}] 必须带 paper_id 或 doi")
            continue
        facets_hit = w.get("collided_facets")
        if not isinstance(facets_hit, list) or not facets_hit:
            errs.append(f"判例 closest_works[{i}] 缺 collided_facets")
        elif any(f not in FACETS for f in facets_hit):
            errs.append(f"判例 closest_works[{i}] collided_facets 含非法面")
        if not _nonempty_str(w.get("delta")):
            errs.append(f"判例 closest_works[{i}] 缺 delta（无差异点的"
                        f"撞车陈述不构成判例）")
    if verdict == "ABANDON" and not _ref_ok(case.get("named_paper") or {}):
        errs.append("ABANDON 判例必须点名在先论文（named_paper 带 "
                    "paper_id 或 doi）")
    return errs


# ---------------------------------------------------------------------------
# 读写（只增、按 case_id 幂等）

def load_cases(root: Path) -> list[dict]:
    """读回全部判例（文件不存在返回空列表，按落盘顺序 = 时间顺序）。"""
    path = casebook_path(root)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_case(root: Path, case: dict) -> bool:
    """追加一条判例；同 case_id 已在集内时不重复追加，返回 False。

    追加前先过 validate_case，非法判例拒绝入集（抛 CasebookError）。
    """
    errs = validate_case(case)
    if errs:
        raise CasebookError(errs)
    existing = {c.get("case_id") for c in load_cases(root)}
    if case["case_id"] in existing:
        return False
    d = casebook_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    with open(casebook_path(root), "a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")
    return True


def append_verdict_case(root: Path, card: dict, record: dict) -> tuple[dict, bool]:
    """判定落卡后调用：构造判例并追加。返回 (判例, 是否新追加)。"""
    case = case_from_verdict(card, record)
    appended = append_case(root, case)
    return case, appended


def recent_cases(root: Path, limit: int = 5) -> list[dict]:
    """最近 limit 条判例（判定材料包附带用，按时间正序返回）。"""
    cases = load_cases(root)
    return cases[-limit:] if limit > 0 else cases


def summarize_cases(cases: list[dict]) -> dict:
    """判例集构成统计（按判定与来源计数，供 CLI 与报告引用）。"""
    by_verdict: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    for c in cases:
        by_verdict[c.get("verdict")] = by_verdict.get(c.get("verdict"), 0) + 1
        by_origin[c.get("origin")] = by_origin.get(c.get("origin"), 0) + 1
    return {"total": len(cases), "by_verdict": by_verdict,
            "by_origin": by_origin}


# ---------------------------------------------------------------------------
# 冷启动种子（随包发布，逐条标源）

def load_seed_cases() -> list[dict]:
    """读随包种子判例并逐条校验；种子是包数据，非法即构建期错误。"""
    path = Path(__file__).with_name("casebook_seeds.jsonl")
    cases = []
    for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        case = json.loads(line)
        errs = validate_case(case)
        if errs:
            raise CasebookError(
                [f"种子判例第 {lineno} 行非法：{e}" for e in errs])
        cases.append(case)
    return cases


def seed_casebook(root: Path) -> dict:
    """把随包种子播种进项目判例集（幂等）。返回 {added, total}。"""
    added = 0
    for case in load_seed_cases():
        if append_case(root, case):
            added += 1
    return {"added": added, "total": len(load_cases(root))}


# ---------------------------------------------------------------------------
# 判定材料包摘录（SKILL §8.3：给判定者的最近 N 条判例）

def render_cases_md(cases: list[dict]) -> str:
    """把判例渲染成 Markdown 摘录，供判定材料包附带给判定者校准。"""
    L: list[str] = []
    L.append(f"## 查新判例集摘录（最近 {len(cases)} 条，先读判例再看证据包）")
    L.append("")
    L.append("> 判例是既往判定的校准材料：看判定口径（什么样的撞车给 "
             "ABANDON、delta 薄到什么程度给 CAUTION），不许把判例里的"
             "论文当作本卡的证据引用——本卡判定只许引证据包。")
    L.append("")
    for c in cases:
        idea = c.get("idea") or {}
        facets = idea.get("facets") or {}
        L.append(f"### 判例 {c.get('case_id')}｜{idea.get('title')}"
                 f" → **{c.get('verdict')}**")
        L.append(f"- 出处：{c.get('source')}（{c.get('date')}"
                 f"，review_status: {c.get('review_status')}）")
        L.append(f"- facet：purpose「{facets.get('purpose')}」"
                 f"｜mechanism「{facets.get('mechanism')}」"
                 f"｜evaluation「{facets.get('evaluation')}」")
        if c.get("caution_reason"):
            L.append(f"- CAUTION 薄点：{c['caution_reason']}")
        for w in c.get("closest_works") or []:
            ref = w.get("doi") or w.get("paper_id") or w.get("title")
            L.append(f"- closest：{ref}｜撞车面 {w.get('collided_facets')}"
                     f"｜delta：{w.get('delta')}")
        named = c.get("named_paper")
        if named:
            ref = named.get("doi") or named.get("paper_id") \
                or named.get("title")
            L.append(f"- ABANDON 点名论文：{ref}")
        L.append("")
    return "\n".join(L)

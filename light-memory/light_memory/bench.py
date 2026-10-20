"""自建评测集运行器（M2/M6 验收，MM-32）。

定位：没有现成考场——按 LongMemEval 分项协议自建科研任务集，
四类题 + 释义基线题；报表随配置版本登记（嵌入模型/配方/索引
清单哈希），无当版报表不称已验证；通过线不在本模块——构建期
首测后由用户定版，本运行器只报数不判线。

题集文件格式（JSONL，逐行一题）：
  qid / category（knowledge_update | cross_project | failure_reuse
  | refusal | paraphrase）/ query / recipe（可选，默认 default）
  / root（世界内的包键，默认 a）/ extra_roots（包键列表）
  / as_of（可选）/ expect：
    - include_statements：期望命中陈述的片段（任一进 top-5 即命中）
    - exclude_statements：不许出现的片段（出现即误答，知识更新题
      用来盯旧结论）
    - include_by_project：{陈述片段: 项目标签}（跨项目题：命中且
      分组正确才算对，混答即错）
    - refusal：true 表示记忆中无此信息，拒答判据 = top-5 内无
      有据命中——词法/关系路命中且与查询共享至少 2 个实义 token
      （单字 OR 命中共用字不算证据；向量弱命中不算证据，属无据）

随包迷你题集 mini_bench.jsonl 由一期真实冒烟数据派生（火鸡项目
迷你世界：结论两代/失败教训/同名方法跨项目/释义与拒答），
build_mini_world 构造对应世界作回归基线。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import index as index_mod
from . import project as project_mod, registry, retrieve, schema
from .supersede import apply_nominations
from .util import component_hash, dump_json, load_structured, utcnow

CATEGORIES = ("knowledge_update", "cross_project", "failure_reuse",
              "refusal", "paraphrase")
TOPK = 5

#: 迷你世界的包键 → 子目录名。
WORLD_KEYS = {"a": "proj-a", "b": "proj-b", "global": "global"}

# 迷你世界陈述（与一期 conftest 冒烟夹具同源：火鸡跟踪项目）
S_CONC_V1 = "跟踪器在 7 段视频上 MOTA 提升 5.25 个百分点"
S_CONC_V2 = "跟踪器在 7 段视频上 MOTA 提升 3.10 个百分点（复核修正版）"
S_FAIL = "数据版本交付不完整，登记对象不存在完整形态，运行失败"
S_LESSON = "教训：数据交付前须先核验版本完整性与登记对象完整形态"
S_IDEA = "零调参阈值可由视频级统计量预测"
S_METHOD_A = "阈值预测映射在顶视固定机位下稳定成立"
S_METHOD_B = "阈值预测映射在移动机位下不稳定，须人工校准后使用"

MINI_QUESTIONS = [
    {"qid": "q-upd-1", "category": "knowledge_update", "root": "a",
     "query": "跟踪器 MOTA 提升了多少个百分点",
     "expect": {"include_statements": [S_CONC_V2],
                "exclude_statements": [S_CONC_V1]}},
    {"qid": "q-fail-1", "category": "failure_reuse", "root": "a",
     "recipe": "failure-lookup",
     "query": "新项目数据交付前要核验什么",
     "expect": {"include_statements": [S_LESSON]}},
    {"qid": "q-cross-1", "category": "cross_project", "root": "a",
     "recipe": "cross-project", "extra_roots": ["b"],
     "query": "阈值预测映射的稳定性如何",
     "expect": {"include_by_project": {S_METHOD_A: "turkey-a",
                                       S_METHOD_B: "turkey-b"}}},
    {"qid": "q-ref-1", "category": "refusal", "root": "a",
     "query": "量子纠缠对火鸡情绪识别的影响",
     "expect": {"refusal": True}},
    {"qid": "q-para-1", "category": "paraphrase", "root": "a",
     "recipe": "paraphrase",
     "query": "视频统计量预测跟踪阈值的方法",
     "expect": {"include_statements": [S_IDEA]}},
    {"qid": "q-para-2", "category": "paraphrase", "root": "a",
     "recipe": "paraphrase",
     "query": "predicting tracker thresholds from video-level "
              "statistics",
     "expect": {"include_statements": [S_IDEA]}},
]


class BenchError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def mini_set_path() -> Path:
    return Path(__file__).parent / "mini_bench.jsonl"


def write_mini_set(path=None) -> Path:
    """把内置迷你题集落为 JSONL 文件（随包基线件的生成口）。"""
    path = Path(path) if path else mini_set_path()
    path.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n"
                            for q in MINI_QUESTIONS), encoding="utf-8")
    return path


def load_questions(set_path) -> list:
    if str(set_path) == "mini":
        set_path = mini_set_path()
    data = load_structured(set_path)
    if not isinstance(data, list) or not data:
        raise BenchError([f"题集为空或格式不对：{set_path}"])
    gaps = []
    for i, q in enumerate(data):
        if q.get("category") not in CATEGORIES:
            gaps.append(f"第 {i + 1} 题类别不在五类内："
                        f"{q.get('category')}")
        if not q.get("query"):
            gaps.append(f"第 {i + 1} 题缺 query")
    if gaps:
        raise BenchError(gaps)
    return data


# ---------------------------------------------------------------- 迷你世界

def _prov(package: str, artifact: str, anchor, version="mini-1") -> dict:
    return schema.make_provenance(package, artifact, anchor, version)


def _store(root, statement, ftype, oid, valid, prov, **kw):
    nom = {"verdict": "store", "nominator": "bench-world",
           "rationale": "迷你世界构造", "provenance": prov,
           "fact": {"statement": statement, "fact_type": ftype,
                    "object_id": oid, "valid_at": valid, **kw}}
    out = apply_nominations(root, [nom])[0]
    assert out["result"] == "stored", out
    return out["fact_id"]


def build_mini_world(base) -> dict:
    """构造迷你世界（proj-a / proj-b / global 三包），返回路径表。

    数据由一期真实冒烟夹具派生：结论两代（v1 被 v2 取代）、一次
    失败与其教训、同一方法对象在两项目下的不同结论。
    """
    base = Path(base)
    roots = {}
    for key, dirname in WORLD_KEYS.items():
        target = base / dirname
        if target.exists():
            shutil.rmtree(target)
        roots[key] = target

    # ---- proj-a（turkey-a） -------------------------------------------
    a = roots["a"]
    project_mod.init_package(a, project_id="turkey-a", title="火鸡项目A")
    pkg = project_mod.load_package(a)
    prov_an = _prov("analysis", "conclusion_card.json", "claims:C1")
    prov_ex = _prov("experiment", "execution_card.json", "exec-b2")
    prov_id = _prov("idea", "memory_export.jsonl", "DIR-idea-alpha")
    registry.register_object(pkg, "claim", "C1", prov_an,
                             project="turkey-a", title="主张 C1")
    registry.register_object(pkg, "run", "R-NEG-a1", prov_ex,
                             project="turkey-a", title="运行 R-NEG-a1")
    registry.register_object(pkg, "idea_card", "idea-alpha_123abc",
                             prov_id, project="turkey-a",
                             title="零调参阈值预测卡")
    registry.register_object(pkg, "method", "tracker-threshold",
                             prov_id, project="turkey-a",
                             title="阈值预测方法")
    project_mod.save_objects(a, pkg["objects"])
    v1 = _store(a, S_CONC_V1, "conclusion", "claim:C1", "2026-01-01",
                prov_an)
    out = apply_nominations(a, [{
        "verdict": "supersede", "nominator": "bench-world",
        "rationale": "复核修正", "provenance": prov_an,
        "target_fact_id": v1,
        "fact": {"statement": S_CONC_V2, "fact_type": "conclusion",
                 "object_id": "claim:C1", "valid_at": "2026-02-01"}}])[0]
    assert out["result"] == "superseded", out
    fail = _store(a, S_FAIL, "failure_record", "run:R-NEG-a1",
                  "2026-01-15", prov_ex)
    lesson = _store(a, S_LESSON, "lesson", "run:R-NEG-a1",
                    "2026-01-16", prov_ex, derived_from=[fail])
    idea_fact = _store(a, S_IDEA, "direction",
                       "idea_card:idea-alpha_123abc", "2026-01-05",
                       prov_id)
    _store(a, S_METHOD_A, "method", "method:tracker-threshold",
           "2026-01-20", prov_id)
    pkg = project_mod.load_package(a)
    rel = schema.new_relation("derived-from", lesson, fail, prov_ex)
    pkg["relations"].append(rel)
    # 跨对象边：方向层想法支撑分析结论（Obsidian 投影的 wikilink 样本）
    concl = next(f for f in pkg["facts"]
                 if f.get("statement") == S_CONC_V2)
    pkg["relations"].append(schema.new_relation(
        "supports", idea_fact, concl["fact_id"], prov_id))
    project_mod.save_relations(a, pkg["relations"])
    notes = a / "notes"
    (notes / "method.md").write_text(
        "# 阈值预测方法\n\n视频级统计量与最优跟踪阈值之间存在稳定"
        "映射，可据此零调参预测阈值。\n", encoding="utf-8")
    index_mod.build_index(a)

    # ---- proj-b（turkey-b）：同名方法、不同结论 -------------------------
    b = roots["b"]
    project_mod.init_package(b, project_id="turkey-b", title="火鸡项目B")
    pkg = project_mod.load_package(b)
    registry.register_object(pkg, "method", "tracker-threshold",
                             prov_id, project="turkey-b",
                             title="阈值预测方法")
    project_mod.save_objects(b, pkg["objects"])
    _store(b, S_METHOD_B, "method", "method:tracker-threshold",
           "2026-01-22", prov_id)
    index_mod.build_index(b)

    # ---- global：空全局层（晋升/跨项目作用域的落点） -------------------
    g = roots["global"]
    project_mod.init_package(g, project_id="global", title="全局层",
                             scope="global")
    return {k: str(v) for k, v in roots.items()}


# ---------------------------------------------------------------- 运行器

#: 拒答判据用的停用 token（共用字单字命中不算证据）。
_REFUSAL_STOPWORDS = {"的", "对", "在", "了", "是", "与", "及", "中",
                      "为", "有", "个", "其", "之", "和", "或", "把",
                      "被", "从", "向", "the", "a", "an", "of", "to"}


def _evidence_overlap(query: str, text: str) -> int:
    """查询与条目的实义 token 交集数（拒答判据的证据强度）。"""
    qtokens = {t for t in index_mod.tokenize(query)
               if t not in _REFUSAL_STOPWORDS}
    ttokens = set(index_mod.tokenize(text))
    return len(qtokens & ttokens)


def _score_item(result: dict, expect: dict, query: str = "") -> tuple:
    """逐题判分：返回 (是否正确, 明细 dict)。只报数不判线。"""
    items = (result.get("items") or [])[:TOPK]
    detail = {"hits": len(items), "old_answer": False,
              "evidence_routes": sorted({r for i in items
                                          for r in i["routes"]})}
    if expect.get("refusal"):
        evidenced = [i for i in items
                     if ("fts" in i["routes"]
                         or "relation" in i["routes"])
                     and _evidence_overlap(
                         query, i.get("match_text") or "") >= 2]
        detail["evidenced_hits"] = len(evidenced)
        return (len(evidenced) == 0), detail
    ok = True
    for sub in expect.get("include_statements") or []:
        if not any(sub in (i.get("match_text") or "") for i in items):
            ok = False
            detail.setdefault("missing", []).append(sub)
    for sub, label in (expect.get("include_by_project") or {}).items():
        if not any(sub in (i.get("match_text") or "")
                   and i.get("project") == label for i in items):
            ok = False
            detail.setdefault("missing_by_project", []).append(
                f"{sub} @ {label}")
    for sub in expect.get("exclude_statements") or []:
        if any(sub in (i.get("match_text") or "") for i in items):
            ok = False
            detail["old_answer"] = True
    return ok, detail


def run_bench(set_path, world_dir, *, out=None) -> dict:
    """对世界内的当前索引与配方跑全集，产分项报表（只报数不判线）。"""
    questions = load_questions(set_path)
    world_dir = Path(world_dir)
    roots = {}
    for key, dirname in WORLD_KEYS.items():
        p = world_dir / dirname
        if (p / "memory.yaml").exists():
            roots[key] = p
    if not roots:
        raise BenchError([f"世界目录无任何记忆包：{world_dir}"
                          "（先 bench build-world）"])
    used_recipes, embedder_info, manifests = {}, None, {}
    per_category: dict[str, dict] = {}
    for q in questions:
        root_key = q.get("root") or "a"
        if root_key not in roots:
            raise BenchError([f"题 {q.get('qid')} 指向不存在的包键："
                              f"{root_key}"])
        root = roots[root_key]
        pkg = project_mod.load_package(root)
        recipe_name = q.get("recipe") or "default"
        used_recipes[recipe_name] = retrieve.get_recipe(
            pkg["memory"], recipe_name)
        if embedder_info is None:
            embedder_info = index_mod.index_status(root).get("embedder")
        manifests[root_key] = index_mod.index_status(root)
        extra = [roots[k] for k in q.get("extra_roots") or []]
        result = retrieve.recall(
            root, q["query"], recipe=recipe_name,
            as_of=q.get("as_of"), extra_roots=extra,
            account_strength=False)
        ok, detail = _score_item(result, q.get("expect") or {},
                                 q["query"])
        cat = per_category.setdefault(
            q["category"], {"total": 0, "correct": 0, "items": []})
        cat["total"] += 1
        cat["correct"] += 1 if ok else 0
        cat["items"].append({"qid": q.get("qid"), "ok": ok,
                             "detail": detail})
    for cat in per_category.values():
        cat["rate"] = round(cat["correct"] / cat["total"], 4) \
            if cat["total"] else None
    report = {
        "kind": "light-memory/bench-report",
        "version": "1.0",
        "generated_at": utcnow(),
        "world": str(world_dir),
        "set": str(set_path),
        "config": {
            "recipes": {name: {"weights": r.get("weights"),
                               "scope": r.get("scope")}
                        for name, r in used_recipes.items()},
            "embedder": embedder_info,
            "index_built_at": {
                k: v.get("built_at") for k, v in manifests.items()},
            "config_hash": component_hash({
                "recipes": used_recipes, "embedder": embedder_info}),
        },
        "pass_line": None,
        "verdict": "not_judged",
        "note": "通过线待构建期首测后由用户定版；本报表只报数不判线"
                "（MM-32）。释义类单列；拒答判据 = top-5 内无与查询"
                "共享至少 2 个实义 token 的词法/关系有据命中。",
        "categories": per_category,
        "overall": {
            "total": sum(c["total"] for c in per_category.values()),
            "correct": sum(c["correct"]
                           for c in per_category.values()),
        },
    }
    if out:
        dump_json(out, report)
    return report

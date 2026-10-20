"""评审产物自审门（RV-13）：meta/decision 草稿交付前再过一轮法医。

五类命名可靠性测试，各有可机械判定的近似检查 + 模型判定登记位
（model_judgment 字段，本期恒为 None 待规程层回填）：

- vague_unsupported（空泛无据）：合成叙述逐行须带库存 ID 锚点或
  数字依据，无锚无数的断言行即点名；
- wrong_object（对象错位）：产物中出现的 ID 形 token 必须在冻结
  库存内（concern/发现/领域条目/检查行/汇总量/封顶/席位/约束号，
  以及承接快照登记的上游对象——结论登记行/图号——与 concern 双
  指针中正式引用的对象），指认不存在的对象即失败；
- praise_only（纯表扬）：表扬措辞出现在带 major/critical 未决
  关切的语境且同行无锚点，或通篇表扬却零引用 concern，即失败；
- mere_restatement（只是复述）：叙述行与某席冻结报告行 token
  Jaccard ≥ 0.9 且不带库存锚点，判为抄写而非综合；
- contradicts_frozen（与冻结清单矛盾）：decision 档位与登记头
  不一致、ready 与未裁决 confirmed error / critical 共识并存、
  行内 severity=/consensus= 标注与共识账不符，皆失败。

对账纪律：报告可少说（冻结 concern 未被 meta 引用只记
missing_from_meta，不判失败）、不可矛盾（未知对象与矛盾判失败）。
产物 reports/selfcheck.json；未过 → reported→adjudicated 门阻断。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import fold_findings, load_package, open_confirmed_errors
from .util import component_hash, dump_json, load_structured, read_jsonl, today

_ID_TOKEN = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|\b[A-Z]\d{2,}\b")
_SEVERITY_CLAIM = re.compile(r"severity=([a-z]+)")
_CONSENSUS_CLAIM = re.compile(r"consensus=(True|False)")
_PRAISE = ["出色", "优秀", "卓越", "杰出", "精彩",
           "excellent", "outstanding", "superb", "impressive"]
_TOKEN = re.compile(r"\w+")


class SelfcheckError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _upstream_ids(pkg) -> set:
    """承接快照登记的上游对象 ID（合法引用域的一部分）。

    meta 渲染 concern 陈述时正当引用上游对象（未检验的结论登记行、
    稿件图号等）；这些对象在承接时已随快照登记，是可引用库存的
    一部分，不许因库存只认本包 ID 而被判「凭空指认」（Phase 3
    演示实测：真实上游行号 R-NEG / 图号 F001 曾被误判库存外）。
    只读承接路径指向的登记文件；读不到返回空集，不猜测补齐。
    """
    ids: set = set()
    intake = (pkg["review"] or {}).get("intake") or {}
    try:
        ap = (intake.get("analysis") or {}).get("package_path")
        if ap:
            ap = Path(ap)
            conclusions = load_structured(ap / "conclusions.yaml") or {}
            for cv in conclusions.get("claims_verdict") or []:
                ids.add(cv.get("claim_id"))
                ids |= set((cv.get("line_verdicts") or {}).keys())
            for row in read_jsonl(ap / "verdicts.jsonl"):
                ids.add(row.get("registry_line_id"))
        mp = (intake.get("manuscript") or {}).get("package_path")
        if mp:
            manifest = load_structured(
                Path(mp) / "figures_manifest.yaml") or {}
            for fig in manifest.get("figures") or []:
                ids.add(fig.get("figure_id"))
    except Exception:
        pass
    return {i for i in ids if i}


def _pointer_tokens(pkg) -> set:
    """concern 双指针中正式引用的 ID 形 token。

    指针是 concern 的正式引用通道：其中登记的对象（回流票号、
    上游文件内编号等）属已登记引用，不是 meta 凭空指认；与
    _upstream_ids 共同界定合法引用域。未被任何指针登记、也不在
    承接结构化登记里的 token 仍判库存外（虚构 ID 不许放行）。
    """
    toks: set = set()
    for c in (pkg["consensus"] or {}).get("concerns") or []:
        for v in (c.get("pointers") or {}).values():
            if isinstance(v, str):
                toks |= set(_ID_TOKEN.findall(v))
    return toks


def _inventory(pkg) -> dict:
    """冻结库存：一切合法可引用的对象 ID 集合。"""
    concerns = {c.get("concern_id"): c
                for c in (pkg["consensus"] or {}).get("concerns") or []}
    findings = {f.get("finding_id")
                for f in fold_findings(pkg["findings"] or [])}
    domain_items = {r.get("item_id") for r in pkg["domain_gate"] or []
                    if r.get("type") == "domain_check"}
    check_ids = {r.get("check_id") for r in pkg["reconciliation"] or []
                 if r.get("type") == "check"}
    stat_ids = {r.get("stat_id") for r in pkg["compatibility"] or []}
    cap_ids = {c.get("cap_id")
               for c in (pkg["calibration"] or {}).get("caps") or []}
    seat_ids = {s.get("seat_id")
                for s in (pkg["seats"] or {}).get("seats") or []}
    rv_ids = {f"RV-{i:02d}" for i in range(1, 19)}
    known = (set(concerns) | findings | domain_items | check_ids
             | stat_ids | cap_ids | seat_ids | rv_ids
             | _upstream_ids(pkg) | _pointer_tokens(pkg))
    return {"concerns": concerns, "known": {k for k in known if k}}


def _targets(pkg) -> dict:
    """自审对象：meta 综合 + decision 或 problem_list（按登记模式）。"""
    return {"meta_review": pkg["meta_review"],
            "decision": pkg["decision_md"],
            "problem_list": pkg["problem_list"]}


def target_hash(pkg) -> str:
    """自审对象的内容哈希：meta/decision 任一改动即自审过期。"""
    t = _targets(pkg)
    return component_hash({k: t[k] for k in ("meta_review", "decision",
                                             "problem_list")})


def _narrative_lines(meta_text: str) -> list:
    """meta_review.md 的合成叙述节正文行（自审的空泛检查范围）。"""
    lines, in_section = [], False
    for ln in (meta_text or "").splitlines():
        if ln.startswith("## "):
            in_section = ln.strip() == "## 合成叙述"
            continue
        if in_section and ln.strip():
            lines.append(ln)
    return lines


def _test_vague(pkg, inv) -> dict:
    offenders = []
    for ln in _narrative_lines(pkg["meta_review"] or ""):
        ids = [t for t in _ID_TOKEN.findall(ln) if t in inv["known"]]
        if not ids and not re.search(r"\d", ln):
            offenders.append(ln.strip())
    return {"test_id": "vague_unsupported",
            "result": "fail" if offenders else "pass",
            "detail": "合成叙述逐行带库存锚点或数字依据"
                      if not offenders else
                      f"{len(offenders)} 行断言无锚点无数字依据",
            "offenders": offenders, "model_judgment": None}


def _test_wrong_object(pkg, inv) -> tuple[dict, set]:
    unknown = set()
    for text in _targets(pkg).values():
        for tok in _ID_TOKEN.findall(text or ""):
            if tok not in inv["known"]:
                unknown.add(tok)
    row = {"test_id": "wrong_object",
           "result": "fail" if unknown else "pass",
           "detail": "产物引用的对象全在冻结库存内"
                     if not unknown else
                     f"引用了库存外对象：{sorted(unknown)}",
           "offenders": sorted(unknown), "model_judgment": None}
    return row, unknown


def _test_praise(pkg, inv) -> dict:
    concerns = inv["concerns"]
    hard_open = any(c.get("severity") in ("major", "critical")
                    for c in concerns.values())
    offenders = []
    referenced = set()
    for name, text in _targets(pkg).items():
        for ln in (text or "").splitlines():
            ids = [t for t in _ID_TOKEN.findall(ln) if t in concerns]
            referenced |= set(ids)
            if any(p in ln for p in _PRAISE) and hard_open and not ids:
                offenders.append(f"{name}：{ln.strip()}")
    meta_text = pkg["meta_review"] or ""
    if any(p in meta_text for p in _PRAISE) and concerns and not referenced:
        offenders.append("meta_review 通篇表扬措辞但零引用 concern")
    return {"test_id": "praise_only",
            "result": "fail" if offenders else "pass",
            "detail": "无无锚表扬" if not offenders else
                      f"{len(offenders)} 处表扬无锚点（且有 major/critical "
                      "未决关切或零引用）",
            "offenders": offenders, "model_judgment": None}


def _tokens(text: str) -> set:
    return set(_TOKEN.findall((text or "").lower()))


def _test_restatement(pkg, inv) -> dict:
    seat_lines = []
    root = Path(pkg["root"])
    for s in (pkg["seats"] or {}).get("seats") or []:
        rp = s.get("report_path")
        if rp and (root / rp).exists():
            seat_lines += (root / rp).read_text(
                encoding="utf-8").splitlines()
    seat_token_sets = [(_tokens(ln), ln) for ln in seat_lines
                       if len(_tokens(ln)) >= 8]
    offenders = []
    for ln in _narrative_lines(pkg["meta_review"] or ""):
        toks = _tokens(ln)
        if len(toks) < 8:
            continue
        if any(t in inv["known"] for t in _ID_TOKEN.findall(ln)):
            continue     # 带锚点的引用是综合，不是抄写
        for stoks, _ in seat_token_sets:
            union = toks | stoks
            if union and len(toks & stoks) / len(union) >= 0.9:
                offenders.append(ln.strip())
                break
    return {"test_id": "mere_restatement",
            "result": "fail" if offenders else "pass",
            "detail": "叙述行无与冻结报告近重复者"
                      if not offenders else
                      f"{len(offenders)} 行与某席冻结报告近重复"
                      "（Jaccard ≥ 0.9）且无锚点",
            "offenders": offenders, "model_judgment": None}


def _test_contradiction(pkg, inv) -> dict:
    offenders = []
    review = pkg["review"] or {}
    decision = review.get("decision") or {}
    concerns = inv["concerns"]
    if decision.get("mode") == "full":
        band = decision.get("band")
        text = pkg["decision_md"] or ""
        if band and f"建议档位：{band}" not in text:
            offenders.append(
                f"decision.md 档位与登记头 decision.band={band} 不一致")
        if band == "ready":
            open_ce = open_confirmed_errors(
                fold_findings(pkg["findings"] or []))
            if open_ce:
                offenders.append(
                    "档位 ready 与未裁决 confirmed error 并存："
                    + "、".join(f["finding_id"] for f in open_ce))
            crit = [cid for cid, c in concerns.items()
                    if c.get("consensus")
                    and c.get("severity") == "critical"]
            if crit:
                offenders.append("档位 ready 与 critical 共识关切并存："
                                 + "、".join(crit))
    for name, text in _targets(pkg).items():
        for ln in (text or "").splitlines():
            for cid in _ID_TOKEN.findall(ln):
                concern = concerns.get(cid)
                if concern is None:
                    continue
                m = _SEVERITY_CLAIM.search(ln)
                if m and m.group(1) != concern.get("severity"):
                    offenders.append(
                        f"{name} 中 {cid} 标注 severity={m.group(1)}，"
                        f"共识账为 {concern.get('severity')}")
                m = _CONSENSUS_CLAIM.search(ln)
                if m and (m.group(1) == "True") != bool(
                        concern.get("consensus")):
                    offenders.append(
                        f"{name} 中 {cid} 标注 consensus={m.group(1)}，"
                        f"共识账为 {concern.get('consensus')}")
    return {"test_id": "contradicts_frozen",
            "result": "fail" if offenders else "pass",
            "detail": "与冻结清单无矛盾" if not offenders else
                      f"{len(offenders)} 处与冻结清单矛盾",
            "offenders": offenders, "model_judgment": None}


def run_selfcheck(root) -> dict:
    """跑自审门五类测试并落 reports/selfcheck.json。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise SelfcheckError(["评审包不存在（先 init）"])
    if not review.get("decision"):
        raise SelfcheckError(["meta 未跑：无 decision 登记，自审无对象"
                              "（先 meta）"])
    if pkg["meta_review"] is None:
        raise SelfcheckError(["缺 reports/meta_review.md（先 meta）"])
    inv = _inventory(pkg)
    wrong_row, unknown = _test_wrong_object(pkg, inv)
    tests = [_test_vague(pkg, inv), wrong_row, _test_praise(pkg, inv),
             _test_restatement(pkg, inv), _test_contradiction(pkg, inv)]
    meta_ids = set()
    for tok in _ID_TOKEN.findall(pkg["meta_review"] or ""):
        if tok in inv["concerns"]:
            meta_ids.add(tok)
    # 「报告可少说」的对账口径落在合成叙述本身：机械账目（共识账/
    # 分歧账）恒全量枚举，不计入叙述覆盖；叙述漏提只登记不判失败。
    narrative_ids = set()
    for tok in _ID_TOKEN.findall(
            "\n".join(_narrative_lines(pkg["meta_review"] or ""))):
        if tok in inv["concerns"]:
            narrative_ids.add(tok)
    report = {
        "kind": "light-review/selfcheck",
        "version": 1,
        "ran_at": today(),
        "target_hash": target_hash(pkg),
        "passed": all(t["result"] == "pass" for t in tests),
        "tests": tests,
        "reconciliation": {
            "frozen_concern_ids": sorted(inv["concerns"]),
            "meta_referenced_ids": sorted(meta_ids),
            "missing_from_meta": sorted(set(inv["concerns"]) - narrative_ids),
            "unknown_in_meta": sorted(unknown),
        },
    }
    out = root / "reports" / "selfcheck.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(out, report)
    return report

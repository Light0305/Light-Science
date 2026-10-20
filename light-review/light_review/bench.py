"""验证台（RV-15）：缺陷注入金标准集 + 判别力报表。

纪律：
- 金标准集是带已知缺陷的稿件片段 + 预期检出表；被测对象是
  **生产检查器本体**（checkers 四边 + grim 三件，与法医层同一
  代码），不许另写一套演示判定冒充验证；
- 报表按缺陷类分列检出率，并以干净对照例测误报率——检出率高
  但误报也高的配置同样不许背书决定建议；
- 报表以 config_hash 绑定评审配置（calibration.config_hash）：
  席位集/量表/封顶/权重任一漂移，报表即过期（assess 判不齐）。
"""

from __future__ import annotations

from pathlib import Path

from . import checkers
from .calibration import config_hash
from .grim import run_grim
from .project import clear_pending, load_package, save_review
from .util import dump_json, today

# ------------------------------------------------------------ 干净世界基线
# 与 tests/conftest 同形的最小一致世界，缺陷例 = 基线 + 单点注入。

_CLEAN_CLAIM = {
    "claim_id": "C1", "analysis_claim_ref": "C1",
    "upstream_status": "untested", "strength_grade": "insufficient",
    "line_verdicts": {"R-FIX": "undetermined", "R-ORA": "undetermined"},
    "writable_ceiling": "limitations_only",
    "writable_form": "limitations_only",
    "evidence_refs": [{"kind": "analysis_verdict_lines",
                       "refs": ["R-FIX", "R-ORA"]}],
}

_CLEAN_CONCLUSIONS = {
    "claims_verdict": [
        {"claim_id": "C1", "support": "untested",
         "line_verdicts": {"R-FIX": "undetermined",
                           "R-ORA": "undetermined"}}],
    "strength": [{"claim_id": "C1", "grade": "insufficient"}],
    "number_provenance": [
        {"value": 5.2493333, "quantity": "effect_size",
         "verdict_line": "R-ORA#v1", "registry_line_id": "R-ORA",
         "spec_id": "S001", "calc_provenance": "welch_effect_and_ci"}],
}

_CLEAN_NUMBER = {
    "num_id": "N001", "value_as_printed": "5.25",
    "trace_ref": "R-ORA#v1", "verdict_ref": "R-ORA", "spec_ref": "S001",
    "calc_provenance": "welch_effect_and_ci",
    "locations": [{"section": "03-results.md"}],
}

_CLEAN_SPEC_RESULTS = [
    {"spec_id": "S001", "registry_line_id": "R-ORA", "status": "computed",
     "effect_size": {"type": "mean_diff", "value": 5.2493333}},
]

_CLEAN_LOCK = [
    {"key": "dong2025", "entry_id": "ST001", "doi": "10.0000/demo.1",
     "entry_hash": "a" * 64, "retraction_state": "clean"},
]

_CLEAN_GRIM = {"stat_id": "GS1", "kind": "mean", "value": "3.47",
               "decimals": 2, "n": 30, "items": 1,
               "scale_type": "likert"}


def _section(printed="5.25", cite="dong2025"):
    return {"03-results.md":
            f"# Results\n\nThe oracle arm differed by [num:N001] {printed} "
            f"points [@{cite}].\n"}


def _flagged(checks) -> bool:
    return any(c.get("result") in ("error", "decision_error")
               for c in checks)


# ------------------------------------------------------------ 案例集
# 每例：case_id / defect_class（clean 为对照）/ expected_detect /
# run() → (detected, evidence)。detected 的判定口径逐例写明。

def _case_claim_overreach():
    claim = dict(_CLEAN_CLAIM, writable_form="full")
    checks, _ = checkers.check_claims_evidence([claim], _CLEAN_CONCLUSIONS)
    return _flagged(checks), "writable_form=full 越 ceiling=limitations_only"


def _case_missing_evidence():
    claim = dict(_CLEAN_CLAIM, analysis_claim_ref="C404")
    checks, _ = checkers.check_claims_evidence([claim], _CLEAN_CONCLUSIONS)
    return _flagged(checks), "主张回指不存在的结论行 C404"


def _case_number_inconsistency():
    checks, _ = checkers.check_numbers_numbers(
        [_CLEAN_NUMBER], _section(printed="5.52"),
        _CLEAN_SPEC_RESULTS, _CLEAN_CONCLUSIONS["number_provenance"])
    return _flagged(checks), "正文实印 5.52 ≠ 登记 5.25"


def _case_citation_gap():
    checks, _ = checkers.check_citations_claims(
        _section(cite="ghost2099"), _CLEAN_LOCK, [],
        {"R-FIX", "R-ORA"}, True)
    return _flagged(checks), "正文引用 [@ghost2099] 在 lock 中无条目"


def _case_grim_incompatible():
    entry = dict(_CLEAN_GRIM, value="2.33", n=7)
    rows = run_grim([entry])
    return rows[0]["result"] == "incompatible", \
        "均值 2.33（n=7, items=1）无整数解"


def _case_clean_claims():
    checks, _ = checkers.check_claims_evidence(
        [_CLEAN_CLAIM], _CLEAN_CONCLUSIONS)
    return _flagged(checks), "干净主张不应被标 error"


def _case_clean_numbers():
    checks, _ = checkers.check_numbers_numbers(
        [_CLEAN_NUMBER], _section(), _CLEAN_SPEC_RESULTS,
        _CLEAN_CONCLUSIONS["number_provenance"])
    return _flagged(checks), "干净数字不应被标 error"


def _case_clean_citations():
    checks, _ = checkers.check_citations_claims(
        _section(), _CLEAN_LOCK, [_CLEAN_CLAIM], {"R-FIX", "R-ORA"}, True)
    return _flagged(checks), "干净引用不应被标 error"


def _case_clean_grim():
    rows = run_grim([_CLEAN_GRIM])
    return rows[0]["result"] == "incompatible", "相容均值不应判败"


CASES = [
    {"case_id": "B-CLM-01", "defect_class": "claim_overreach",
     "expected_detect": True, "run": _case_claim_overreach},
    {"case_id": "B-CLM-02", "defect_class": "missing_evidence",
     "expected_detect": True, "run": _case_missing_evidence},
    {"case_id": "B-NUM-01", "defect_class": "number_inconsistency",
     "expected_detect": True, "run": _case_number_inconsistency},
    {"case_id": "B-CIT-01", "defect_class": "citation_gap",
     "expected_detect": True, "run": _case_citation_gap},
    {"case_id": "B-GRIM-01", "defect_class": "grim_incompatible",
     "expected_detect": True, "run": _case_grim_incompatible},
    {"case_id": "B-CLEAN-01", "defect_class": "clean",
     "expected_detect": False, "run": _case_clean_claims},
    {"case_id": "B-CLEAN-02", "defect_class": "clean",
     "expected_detect": False, "run": _case_clean_numbers},
    {"case_id": "B-CLEAN-03", "defect_class": "clean",
     "expected_detect": False, "run": _case_clean_citations},
    {"case_id": "B-CLEAN-04", "defect_class": "clean",
     "expected_detect": False, "run": _case_clean_grim},
]

DEFECT_CLASSES = sorted({c["defect_class"] for c in CASES
                         if c["defect_class"] != "clean"})


class BenchError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def run_bench(root) -> dict:
    """跑验证台并落 reports/bench_report.json（绑定当前配置哈希）。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise BenchError(["评审包不存在（先 init）"])
    current_hash = config_hash(root)
    if current_hash is None:
        raise BenchError(["calibration.yaml 缺失：验证台无配置可绑定"
                          "（先 calibration 初始化）"])
    results = []
    for case in CASES:
        detected, evidence = case["run"]()
        results.append({
            "case_id": case["case_id"],
            "defect_class": case["defect_class"],
            "expected_detect": case["expected_detect"],
            "detected": bool(detected),
            "passed": bool(detected) == case["expected_detect"],
            "evidence": evidence,
        })
    by_class = {}
    for cls in DEFECT_CLASSES:
        sub = [r for r in results if r["defect_class"] == cls]
        by_class[cls] = {
            "total": len(sub),
            "detected": sum(1 for r in sub if r["detected"]),
            "detection_rate": (sum(1 for r in sub if r["detected"])
                               / len(sub)) if sub else None,
        }
    clean = [r for r in results if r["defect_class"] == "clean"]
    false_positive = {
        "total": len(clean),
        "flagged": sum(1 for r in clean if r["detected"]),
        "rate": (sum(1 for r in clean if r["detected"]) / len(clean))
        if clean else None,
    }
    report = {
        "kind": "light-review/bench-report",
        "version": 1,
        "ran_at": today(),
        "config_hash": current_hash,
        "cases": results,
        "by_class": by_class,
        "false_positive": false_positive,
        "passed_all": all(r["passed"] for r in results),
    }
    out = root / "reports" / "bench_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(out, report)
    review["bench"] = {"ran_at": report["ran_at"],
                       "config_hash": current_hash,
                       "report_ref": "reports/bench_report.json",
                       "passed_all": report["passed_all"]}
    from .calibration import assess_calibration
    if assess_calibration(root)["complete"]:
        clear_pending(review, "calibration")
    review["updated_at"] = today()
    save_review(root, review)
    return report

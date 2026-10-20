"""Q10 评测集：参考答案全过、注错答案判败、用例数与分层在册。"""

import importlib.util
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_eval", EVAL_DIR / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cases_count_and_levels():
    mod = _load_runner()
    cases = mod._load_jsonl(EVAL_DIR / "cases.jsonl")
    assert len(cases) == 12
    levels = {c["dok_level"] for c in cases}
    assert levels == {"L1_information", "L2_reasoning",
                      "L3_evaluation", "L4_creation"}


def test_reference_answers_pass():
    mod = _load_runner()
    report = mod.score_answers(
        mod._load_jsonl(EVAL_DIR / "cases.jsonl"),
        mod._load_jsonl(EVAL_DIR / "reference_answers.jsonl"))
    assert report["passed"] == 12, report["rows"]


def test_wrong_answers_fail():
    mod = _load_runner()
    cases = mod._load_jsonl(EVAL_DIR / "cases.jsonl")
    answers = mod._load_jsonl(EVAL_DIR / "reference_answers.jsonl")
    answers[0] = {"case_id": "EV-01", "decision": "grace_ok",
                  "points": ["六个月内都没问题，可以走宽限照常申请"]}
    answers[4] = {"case_id": "EV-05", "decision": "reject_amendment",
                  "points": ["可以加入新特征"]}
    report = mod.score_answers(cases, answers)
    failed = {r["case_id"] for r in report["rows"] if not r["passed"]}
    assert failed == {"EV-01", "EV-05"}

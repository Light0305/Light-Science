"""评测集运行器：五类题分项报表、拒答判据、只报数不判线、
配置随报表登记、题集格式校验。"""

import pytest

from light_memory import bench


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def test_mini_bench_full_report(world):
    report = bench.run_bench("mini", world)
    cats = report["categories"]
    assert set(cats) == set(bench.CATEGORIES)
    assert cats["knowledge_update"]["correct"] == 1  # 不答旧结论
    assert cats["failure_reuse"]["correct"] == 1
    assert cats["cross_project"]["correct"] == 1  # 分组不混答
    assert cats["refusal"]["correct"] == 1  # 无据不编造
    assert cats["paraphrase"]["total"] == 2  # 释义类单列报数
    assert report["overall"]["total"] == 6


def test_report_records_config_and_no_pass_line(world):
    report = bench.run_bench("mini", world)
    assert report["pass_line"] is None  # 通过线待用户定版
    assert report["verdict"] == "not_judged"  # 只报数不判线
    assert report["config"]["config_hash"]
    assert "default" in report["config"]["recipes"]


def test_shipped_mini_set_matches_builtin_questions():
    questions = bench.load_questions("mini")
    assert len(questions) == len(bench.MINI_QUESTIONS)
    assert {q["qid"] for q in questions} == \
        {q["qid"] for q in bench.MINI_QUESTIONS}


def test_load_questions_rejects_bad_category(tmp_path):
    import json
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps({"qid": "x", "category": "瞎编类",
                             "query": "q"}) + "\n", encoding="utf-8")
    with pytest.raises(bench.BenchError):
        bench.load_questions(p)


def test_run_bench_requires_built_world(tmp_path):
    with pytest.raises(bench.BenchError):
        bench.run_bench("mini", tmp_path / "nowhere")


def test_old_answer_is_marked_in_detail(world):
    # 知识更新题的判分明细须能区分「答旧结论」这一误答形态
    report = bench.run_bench("mini", world)
    item = report["categories"]["knowledge_update"]["items"][0]
    assert item["ok"] is True
    assert item["detail"]["old_answer"] is False

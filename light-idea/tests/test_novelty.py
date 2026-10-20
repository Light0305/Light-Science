"""二期 facet 查新：构式 / 归池去重粗排 / 盲区记录 / 判定落卡纪律。

全部离线：HTTP 层由 fake_sources 的四源假响应 monkeypatch 顶替。
"""

import json
from pathlib import Path

import pytest
from conftest import full_card
from fake_sources import EPMC_DOI, S2_DOI, SHARED_DOI, make_fake

from light_idea import novelty
from light_idea.gates import advance, check_transition
from light_idea.project import init_project, load_card, save_card


# ---------- 工具 ----------

def fresh_card(status="screened"):
    """一张已达 screened、但查新区还是空白占位的卡。"""
    card = full_card(status)
    card["novelty"] = {
        "checked_at": None,
        "search_scope": {"sources": [], "pool_size": None,
                         "known_blind_spots": ""},
        "closest_works": [],
        "verdict": None,
        "caution_reason": "",
        "receipt": {"verdict_id": None, "judge_model": None,
                    "judge_family": None, "executor_model": None,
                    "executor_family": None},
        "review_status": "ok",
        "evidence_package": None,
    }
    return card


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "番茄病害")
    return root


@pytest.fixture()
def prepared(project, monkeypatch):
    """卡已落盘且 prepare 已用四源假响应跑完。返回 (root, card)。"""
    monkeypatch.setattr(novelty, "_http_get_json", make_fake())
    card = fresh_card()
    save_card(project, card)
    novelty.prepare(project, card, date="2026-10-20")
    save_card(project, card)
    return project, card


def verdict_data(**over):
    data = {
        "verdict": "PROCEED",
        "judge_model": "gpt-judge", "judge_family": "openai",
        "executor_model": "claude-exec", "executor_family": "anthropic",
        "caution_reason": "",
        "closest_works": [{
            "doi": SHARED_DOI,
            "title": "Masked autoencoders for plant phenotyping",
            "year": 2024,
            "collided_facets": ["mechanism"],
            "delta": "其预训练在温室受控图上，本想法针对田间域与小样本微调",
        }],
        "named_paper": None,
        "review_unavailable": False,
    }
    data.update(over)
    return data


# ---------- 构式 ----------

def test_build_queries_two_per_facet_plus_whole():
    queries = novelty.build_queries(fresh_card())
    by_facet = {}
    for q in queries:
        by_facet.setdefault(q["facet"], []).append(q)
    for facet in ("purpose", "mechanism", "evaluation"):
        kinds = {q["kind"] for q in by_facet[facet]}
        assert {"phrase", "keywords"} <= kinds, facet
    assert 1 <= len(by_facet["whole"]) <= 2
    assert all(q["kind"] == "whole_idea" for q in by_facet["whole"])


# ---------- prepare：归池 / 去重 / 粗排 / 落盘 / 回填 ----------

def test_prepare_pool_dedup_merge_across_sources(prepared):
    root, card = prepared
    lines = (root / "novelty" / card["idea_id"] / "evidence.jsonl") \
        .read_text(encoding="utf-8").strip().splitlines()
    pool = [json.loads(x) for x in lines]
    # Crossref 2 条 + OpenAlex 1 条（与 Crossref 同 DOI 合并）+ S2 1 + EPMC 1
    assert len(pool) == 4
    shared = [r for r in pool if r["doi"] == SHARED_DOI]
    assert len(shared) == 1
    assert set(shared[0]["sources"]) == {"crossref", "openalex"}
    # 每条证据记录字段齐全（含命中面与摘要片段）
    for rec in pool:
        for key in ("source", "title", "authors", "year", "doi",
                    "hit_facets", "similarity", "abstract_snippet"):
            assert key in rec
        assert rec["hit_facets"]
    # 粗排降序落盘
    sims = [r["similarity"] for r in pool]
    assert sims == sorted(sims, reverse=True)
    # 与题名同主题的 S2 记录应拿到正相似度（粗排信号真实在动）
    s2 = [r for r in pool if r["doi"] == S2_DOI][0]
    assert s2["similarity"] > 0
    assert s2["best_facet"] in s2["hit_facets"]


def test_prepare_backfills_search_scope(prepared):
    root, card = prepared
    saved = load_card(root, card["idea_id"])
    scope = saved["novelty"]["search_scope"]
    assert set(scope["sources"]) == set(novelty.SOURCES)
    assert scope["pool_size"] == 4
    assert saved["novelty"]["evidence_package"] == f"novelty/{card['idea_id']}/"
    report = (root / "novelty" / card["idea_id"] / "pool_report.md") \
        .read_text(encoding="utf-8")
    assert "已知盲区声明" in report
    assert "查询式" in report


def test_prepare_records_blind_spot_when_source_fails(project, monkeypatch):
    monkeypatch.setattr(
        novelty, "_http_get_json", make_fake(fail={"europepmc"}, status=429))
    card = fresh_card()
    save_card(project, card)
    summary = novelty.prepare(project, card, date="2026-10-20")
    assert summary["any_source_ok"] is True
    st = summary["source_status"]["europepmc"]
    assert st["ok"] is False and st["errors"], "失败必须如实记录"
    spots = "；".join(summary["blind_spots"])
    assert "Europe PMC" in spots and "429" in spots
    saved_scope = card["novelty"]["search_scope"]["known_blind_spots"]
    assert "Europe PMC" in saved_scope
    report = Path(summary["pool_report_path"]).read_text(encoding="utf-8")
    assert "Europe PMC" in report and "不可用" in report


def test_prepare_all_sources_fail_reports_not_ok(project, monkeypatch):
    monkeypatch.setattr(
        novelty, "_http_get_json",
        make_fake(fail=set(novelty.SOURCES), status=503))
    card = fresh_card()
    save_card(project, card)
    summary = novelty.prepare(project, card, date="2026-10-20")
    assert summary["any_source_ok"] is False
    assert summary["pool_size"] == 0
    # 证据包仍落盘（空池 + 盲区），不许假装查过
    assert Path(summary["evidence_path"]).exists()


# ---------- verdict：判定纪律正反例 ----------

def test_verdict_proceed_lands_with_receipt(prepared):
    root, card = prepared
    record = novelty.apply_verdict(root, card, verdict_data(),
                                   date="2026-10-20")
    assert record["receipt"]["verdict_id"].startswith("NV-")
    nov = card["novelty"]
    assert nov["verdict"] == "PROCEED"
    assert nov["checked_at"] == "2026-10-20"
    assert nov["review_status"] == "ok"
    assert nov["receipt"]["judge_family"] == "openai"
    assert nov["closest_works"][0]["collided_facets"] == ["mechanism"]
    assert (root / "novelty" / card["idea_id"] / "verdict.json").exists()


def test_verdict_rejects_same_family(prepared):
    root, card = prepared
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(
            judge_model="claude-judge", judge_family="anthropic",
            executor_model="claude-exec", executor_family="anthropic"))
    assert any("同属一个模型家族" in e for e in ei.value.errors)
    # 模型名同头推断同族也拒（openai/* 两侧）
    with pytest.raises(novelty.NoveltyError):
        novelty.apply_verdict(root, card, verdict_data(
            judge_model="openai/gpt-judge", judge_family=None,
            executor_model="openai/gpt-exec", executor_family=None))


def test_verdict_caution_requires_reason(prepared):
    root, card = prepared
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(
            verdict="PROCEED_WITH_CAUTION", caution_reason=""))
    assert any("caution_reason" in e for e in ei.value.errors)
    # 补上薄点说明后可落
    record = novelty.apply_verdict(root, card, verdict_data(
        verdict="PROCEED_WITH_CAUTION",
        caution_reason="mechanism 面与 MAE 植物表型工作相邻，delta 只在田间域"))
    assert record["verdict"] == "PROCEED_WITH_CAUTION"


def test_verdict_abandon_requires_named_paper_in_pool(prepared):
    root, card = prepared
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(verdict="ABANDON"))
    assert any("点名" in e for e in ei.value.errors)
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(
            verdict="ABANDON",
            named_paper={"doi": "10.9999/not-in-pool.2024",
                         "title": "Ghost paper"}))
    assert any("不在证据池" in e for e in ei.value.errors)


def test_verdict_abandon_ok_with_named_in_closest(prepared):
    root, card = prepared
    record = novelty.apply_verdict(root, card, verdict_data(
        verdict="ABANDON",
        named_paper={"doi": SHARED_DOI,
                     "title": "Masked autoencoders for plant phenotyping",
                     "year": 2024}))
    assert record["named_paper"]["doi"] == SHARED_DOI
    assert card["novelty"]["abandon_named_paper"]["doi"] == SHARED_DOI
    # 一期门：ABANDON 不许进 novelty_checked（应走 killed）
    errs = check_transition(card, "novelty_checked")
    assert any("ABANDON" in e for e in errs)


def test_verdict_rejects_closest_outside_pool_and_missing_proof(prepared):
    root, card = prepared
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(closest_works=[{
            "doi": "10.8888/elsewhere.2024", "title": "Elsewhere",
            "collided_facets": ["purpose"], "delta": "x"}]))
    assert any("不在证据池" in e for e in ei.value.errors)
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(closest_works=[{
            "doi": SHARED_DOI, "title": "x",
            "collided_facets": ["mechanism"], "delta": ""}]))
    assert any("delta" in e for e in ei.value.errors)
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(closest_works=[{
            "doi": SHARED_DOI, "title": "x",
            "collided_facets": [], "delta": "y"}]))
    assert any("collided_facets" in e for e in ei.value.errors)
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(root, card, verdict_data(closest_works=[{
            "doi": SHARED_DOI, "title": "x",
            "collided_facets": ["whole"], "delta": "y"}]))
    assert any("whole" in e for e in ei.value.errors)


def test_verdict_requires_evidence_package(project):
    card = fresh_card()
    save_card(project, card)
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.apply_verdict(project, card, verdict_data())
    assert any("证据包不存在" in e for e in ei.value.errors)


def test_review_unavailable_degrades_but_cannot_finalize(prepared):
    root, card = prepared
    record = novelty.apply_verdict(root, card, verdict_data(
        judge_model=None, judge_family=None,
        review_unavailable=True), date="2026-10-20")
    assert record["review_status"] == "REVIEW_UNAVAILABLE"
    assert card["novelty"]["receipt"]["judge_model"] is None
    # 可继续流转：查新门可过
    advance(card, "novelty_checked", by="test", date="2026-10-20")
    advance(card, "pre_mortem_passed", by="test", date="2026-10-20")
    # 但一期定版门拦截（本期不许放宽门）
    errs = check_transition(card, "finalized_executable")
    assert any("REVIEW_UNAVAILABLE" in e for e in errs)


# ---------- 全链：prepare → verdict → advance ----------

def test_full_chain_prepare_verdict_advance(prepared):
    root, card = prepared
    novelty.apply_verdict(root, card, verdict_data(), date="2026-10-20")
    save_card(root, card)
    advance(card, "novelty_checked", by="test", date="2026-10-20")
    assert card["status"] == "novelty_checked"


# ---------- CLI 层 ----------

def test_cli_prepare_and_verdict(project, monkeypatch, capsys):
    from light_idea.cli import main
    monkeypatch.setattr(novelty, "_http_get_json", make_fake())
    card = fresh_card()
    save_card(project, card)
    assert main(["novelty", "prepare", str(project), card["idea_id"]]) == 0
    closest = project / "closest.json"
    closest.write_text(json.dumps({"closest_works": [{
        "doi": SHARED_DOI,
        "title": "Masked autoencoders for plant phenotyping",
        "year": 2024, "collided_facets": ["mechanism"],
        "delta": "温室受控图 vs 田间域"}]}), encoding="utf-8")
    # 同族判定在 CLI 层同样被拒（exit 1）
    assert main(["novelty", "verdict", str(project), card["idea_id"],
                 "--verdict", "PROCEED",
                 "--judge-model", "claude-j", "--judge-family", "anthropic",
                 "--executor-model", "claude-e",
                 "--executor-family", "anthropic",
                 "--closest-file", str(closest)]) == 1
    assert main(["novelty", "verdict", str(project), card["idea_id"],
                 "--verdict", "PROCEED",
                 "--judge-model", "gpt-j", "--judge-family", "openai",
                 "--executor-model", "claude-e",
                 "--executor-family", "anthropic",
                 "--closest-file", str(closest)]) == 0
    saved = load_card(project, card["idea_id"])
    assert saved["novelty"]["verdict"] == "PROCEED"
    out = capsys.readouterr().out
    assert "判定已落卡" in out


def test_cli_prepare_all_sources_down_exits_1(project, monkeypatch):
    from light_idea.cli import main
    monkeypatch.setattr(
        novelty, "_http_get_json",
        make_fake(fail=set(novelty.SOURCES), status=503))
    card = fresh_card()
    save_card(project, card)
    assert main(["novelty", "prepare", str(project), card["idea_id"]]) == 1


def test_cli_verdict_abandon_prints_kill_path(project, monkeypatch, capsys):
    from light_idea.cli import main
    monkeypatch.setattr(novelty, "_http_get_json", make_fake())
    card = fresh_card()
    save_card(project, card)
    assert main(["novelty", "prepare", str(project), card["idea_id"]]) == 0
    closest = project / "closest.json"
    closest.write_text(json.dumps({
        "closest_works": [{
            "doi": SHARED_DOI,
            "title": "Masked autoencoders for plant phenotyping",
            "year": 2024, "collided_facets": ["mechanism", "purpose"],
            "delta": "机制与问题均已被覆盖，无剩余 delta"}],
        "named_paper": {"doi": SHARED_DOI,
                        "title": "Masked autoencoders for plant phenotyping",
                        "year": 2024}}), encoding="utf-8")
    assert main(["novelty", "verdict", str(project), card["idea_id"],
                 "--verdict", "ABANDON",
                 "--judge-model", "gpt-j", "--judge-family", "openai",
                 "--executor-model", "claude-e",
                 "--executor-family", "anthropic",
                 "--closest-file", str(closest)]) == 0
    out = capsys.readouterr().out
    assert "killed" in out and "novelty_named_paper" in out

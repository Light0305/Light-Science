"""v1.1 三必做：IDEA-D02 扩源 / IDEA-D04 判例集 / IDEA-D03 能力匹配。

全部离线：HTTP 层由 fake_sources 的七源假响应 monkeypatch 顶替。
"""

import json

import pytest
from conftest import full_card
from fake_sources import OPENAIRE_DOI, S2_DOI, SHARED_DOI, make_fake

from light_idea import casebook, novelty
from light_idea.gates import check_transition
from light_idea.project import init_project, load_card, save_card
from light_idea.schema import capability_summary, validate_card


# ---------- 工具（与 test_novelty 同口径的空白查新卡） ----------

def fresh_card(status="screened"):
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


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "番茄病害")
    return root


@pytest.fixture()
def prepared(project, monkeypatch):
    monkeypatch.setattr(novelty, "_http_get_json", make_fake())
    card = fresh_card()
    save_card(project, card)
    novelty.prepare(project, card, date="2026-10-20")
    save_card(project, card)
    return project, card


# ---------- IDEA-D02：扩源 ----------

def test_sources_expanded_to_seven():
    assert novelty.SOURCES == ("crossref", "openalex", "semanticscholar",
                               "europepmc", "dblp", "core", "openaire")
    assert set(novelty.SOURCE_LABELS) == set(novelty.SOURCES)
    assert set(novelty._SEARCHERS) == set(novelty.SOURCES)


def test_new_sources_rich_hits_merge_and_grow_pool(project, monkeypatch):
    monkeypatch.setattr(novelty, "_http_get_json",
                        make_fake(rich_new=True))
    card = fresh_card()
    save_card(project, card)
    summary = novelty.prepare(project, card, date="2026-10-20")
    # 原四源 4 条 + OpenAIRE 新增 1 条；dblp 并入 SHARED、CORE 并入 S2
    assert summary["pool_size"] == 5
    lines = (project / "novelty" / card["idea_id"] / "evidence.jsonl") \
        .read_text(encoding="utf-8").strip().splitlines()
    pool = [json.loads(x) for x in lines]
    shared = [r for r in pool if r["doi"] == SHARED_DOI][0]
    assert {"crossref", "openalex", "dblp"} <= set(shared["sources"])
    # dblp 题名尾句点已剥掉，归池题名与 Crossref 一致
    assert not shared["title"].endswith(".")
    s2 = [r for r in pool if r["doi"] == S2_DOI][0]
    assert {"semanticscholar", "core"} <= set(s2["sources"])
    oa = [r for r in pool if r["doi"] == OPENAIRE_DOI][0]
    assert oa["source"] == "openaire"
    assert oa["authors"] == ["Maria Garcia", "Ken Watanabe"]
    assert oa["year"] == 2024
    assert oa["venue"] == "Poultry Science"


def test_new_source_failure_blind_spot_and_scope(project, monkeypatch):
    monkeypatch.setattr(novelty, "_http_get_json",
                        make_fake(fail={"dblp"}, status=429))
    card = fresh_card()
    save_card(project, card)
    summary = novelty.prepare(project, card, date="2026-10-20")
    assert summary["any_source_ok"] is True
    assert summary["source_status"]["dblp"]["ok"] is False
    assert any("dblp" in s for s in summary["blind_spots"])
    scope = card["novelty"]["search_scope"]
    assert "dblp" not in scope["sources"]
    assert scope["failed_sources"] == ["dblp"]
    assert set(scope["sources"]) == set(novelty.SOURCES) - {"dblp"}


def test_core_unauthorized_blind_spot_mentions_key(project, monkeypatch):
    monkeypatch.setattr(novelty, "_http_get_json",
                        make_fake(fail={"core"}, status=401))
    card = fresh_card()
    save_card(project, card)
    summary = novelty.prepare(project, card, date="2026-10-20")
    assert any("CORE" in s and "CORE_API_KEY" in s
               for s in summary["blind_spots"])


def test_core_api_key_sent_as_header_never_logged(project, monkeypatch):
    captured = {}
    base = make_fake()

    def capturing(url, params=None, headers=None):
        if "core.ac.uk" in url:
            captured["headers"] = headers
        return base(url, params)

    monkeypatch.setattr(novelty, "_http_get_json", capturing)
    card = fresh_card()
    save_card(project, card)
    # 无 Key：不带 Authorization 头
    novelty.prepare(project, card, sources=("core",), date="2026-10-20")
    assert not captured["headers"]
    # 有 Key：以 Bearer 头注入，且 Key 不进任何落盘产物
    monkeypatch.setenv("CORE_API_KEY", "test-key-123")
    novelty.prepare(project, card, sources=("core",), date="2026-10-20")
    assert captured["headers"] == {"Authorization": "Bearer test-key-123"}
    nd = project / "novelty" / card["idea_id"]
    for name in ("pool_report.md", "queries.json", "evidence.jsonl"):
        assert "test-key-123" not in (nd / name).read_text(encoding="utf-8")


def test_non_json_response_reports_status_for_blind_spot(monkeypatch):
    """2xx 但回 HTML（如 dblp 的 Anubis 机器人校验页）：错误须带状态码，
    供盲区声明定位，不许伪装成查无命中。"""
    import urllib.request

    class FakeResp:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<html><title>Making sure you're not a bot!</title>"

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: FakeResp())
    with pytest.raises(novelty.SourceError) as ei:
        novelty._http_get_json("https://dblp.org/search/publ/api",
                               {"q": "x", "format": "json"})
    assert "HTTP 202" in str(ei.value)


def test_prepare_unknown_source_rejected(project, monkeypatch):
    monkeypatch.setattr(novelty, "_http_get_json", make_fake())
    card = fresh_card()
    save_card(project, card)
    with pytest.raises(novelty.NoveltyError) as ei:
        novelty.prepare(project, card, sources=("crossref", "bogus"))
    assert any("未知检索源" in e for e in ei.value.errors)


def test_cli_prepare_sources_subset(project, monkeypatch, capsys):
    from light_idea.cli import main
    monkeypatch.setattr(novelty, "_http_get_json",
                        make_fake(rich_new=True))
    card = fresh_card()
    save_card(project, card)
    assert main(["novelty", "prepare", str(project), card["idea_id"],
                 "--sources", "crossref,dblp"]) == 0
    saved = load_card(project, card["idea_id"])
    assert set(saved["novelty"]["search_scope"]["sources"]) == \
        {"crossref", "dblp"}
    assert main(["novelty", "prepare", str(project), card["idea_id"],
                 "--sources", "bogus"]) == 1


# ---------- IDEA-D04：判例集 ----------

def test_verdict_appends_case_without_model_names(prepared):
    root, card = prepared
    record = novelty.apply_verdict(root, card, verdict_data(),
                                   date="2026-10-20")
    assert record["casebook"]["appended"] is True
    cases = casebook.load_cases(root)
    mine = [c for c in cases if c["origin"] == "verdict"]
    assert len(mine) == 1
    case = mine[0]
    assert case["case_id"] == record["casebook"]["case_id"]
    assert case["verdict"] == "PROCEED"
    assert case["idea"]["facets"]["mechanism"]
    assert case["closest_works"][0]["doi"] == SHARED_DOI
    # 脱敏：判定者/执行者模型名与收据不入判例
    blob = json.dumps(case, ensure_ascii=False)
    assert "gpt-judge" not in blob and "claude-exec" not in blob
    assert "verdict_id" not in blob


def test_verdict_case_append_is_idempotent(prepared):
    root, card = prepared
    novelty.apply_verdict(root, card, verdict_data(), date="2026-10-20")
    record = novelty.apply_verdict(root, card, verdict_data(),
                                   date="2026-10-20")
    assert record["casebook"]["appended"] is False
    mine = [c for c in casebook.load_cases(root)
            if c["origin"] == "verdict"]
    assert len(mine) == 1


def test_seed_cases_cover_three_verdicts_and_validate():
    seeds = casebook.load_seed_cases()
    assert len(seeds) == 4
    assert {c["verdict"] for c in seeds} == {
        "PROCEED", "PROCEED_WITH_CAUTION", "ABANDON"}
    for c in seeds:
        assert casebook.validate_case(c) == []
        assert c["origin"] == "seed" and c["source"]
    abandon = [c for c in seeds if c["verdict"] == "ABANDON"][0]
    # D1 订正（快修批）：MAE 的正确 DOI 为 ...01553；原 ...01639 经
    # Crossref 核验指向另一篇论文（弱监督语义分割），订正留痕在
    # named_paper.identifier_check
    assert abandon["named_paper"]["doi"] == "10.1109/CVPR52688.2022.01553"
    chk = abandon["named_paper"]["identifier_check"]
    assert chk["result"] == "corrected"
    assert chk["was"] == "10.1109/CVPR52688.2022.01639"
    real = [c for c in seeds if "REVIEW_UNAVAILABLE" == c["review_status"]]
    assert len(real) == 1  # 演示 C1 的真实降级判定，原样标注


def test_seed_identifiers_all_checked():
    # 快修批种子标识符全量复核的钉位：每条 closest/named 的 DOI 都须
    # 带 identifier_check 留痕（Crossref 核验日期与结论）
    seeds = casebook.load_seed_cases()
    checked = 0
    for c in seeds:
        refs = list(c.get("closest_works") or [])
        if c.get("named_paper"):
            refs.append(c["named_paper"])
        for w in refs:
            if not w.get("doi"):
                continue
            chk = w.get("identifier_check") or {}
            assert chk.get("via") == "Crossref", (c["case_id"], w["doi"])
            assert chk.get("checked_at") == "2026-10-21"
            assert chk.get("result") in (
                "title_match", "corrected", "not_found_fixture")
            checked += 1
    assert checked == 7  # 4 种子共 7 处 DOI 引用（5 closest + 1 named + 1 重复引用）


def test_init_seeds_casebook_and_reseed_idempotent(project):
    cases = casebook.load_cases(project)
    assert len(cases) == 4  # init 建项已自动播种
    result = casebook.seed_casebook(project)
    assert result["added"] == 0 and result["total"] == 4


def test_validate_case_rejects_bad_cases():
    good = casebook.load_seed_cases()[0]
    bad = json.loads(json.dumps(good))
    bad["caution_reason"] = ""
    assert any("caution_reason" in e
               for e in casebook.validate_case(bad))
    bad2 = json.loads(json.dumps(good))
    bad2["closest_works"][0]["delta"] = ""
    assert any("delta" in e for e in casebook.validate_case(bad2))
    bad3 = json.loads(json.dumps(good))
    bad3["source"] = ""
    assert any("source" in e for e in casebook.validate_case(bad3))


def test_recent_cases_and_render_md(project):
    recent = casebook.recent_cases(project, 2)
    assert len(recent) == 2
    md = casebook.render_cases_md(casebook.recent_cases(project, 5))
    assert "判例集摘录" in md
    assert "不许把判例里的论文当作本卡的证据" in md
    assert "PROCEED_WITH_CAUTION" in md


def test_cli_cases_seed_and_md(project, capsys):
    from light_idea.cli import main
    assert main(["novelty", "cases", str(project), "--seed"]) == 0
    assert main(["novelty", "cases", str(project), "--md"]) == 0
    out = capsys.readouterr().out
    assert "判例集：4 条" in out
    assert "判例集摘录" in out


# ---------- IDEA-D03：能力匹配 ----------

def test_schema_capability_fit_shape_errors():
    card = full_card()
    fit = card["exec_spec"]["capability_fit"]
    assert validate_card(card) == []
    fit["gaps"][0]["disposition"] = "maybe"
    errs = validate_card(card)
    assert any("disposition 非法" in e for e in errs)
    fit["gaps"][0]["disposition"] = "have"
    fit["gaps"][0]["note"] = ""
    assert any("不许空评" in e for e in validate_card(card))
    fit["gaps"][0]["note"] = "有现成代码"
    fit["team_status"] = ""
    assert any("team_status" in e for e in validate_card(card))
    fit["team_status"] = "有管线"
    fit["required"] = []
    assert any("required 为空" in e for e in validate_card(card))


def test_finalize_gate_requires_capability_fit():
    card = full_card("pre_mortem_passed")
    del card["exec_spec"]["capability_fit"]
    errs = check_transition(card, "finalized_executable")
    assert any("capability_fit 未填" in e for e in errs)
    errs = check_transition(card, "finalized_conceptual")
    assert any("capability_fit 未填" in e for e in errs)


def test_finalize_gate_uncovered_capability_blocked():
    card = full_card("pre_mortem_passed")
    card["exec_spec"]["capability_fit"]["gaps"] = \
        card["exec_spec"]["capability_fit"]["gaps"][:1]
    errs = check_transition(card, "finalized_executable")
    assert any("未覆盖所需能力" in e for e in errs)


def test_blocking_gap_blocks_executable_not_conceptual():
    card = full_card("pre_mortem_passed")
    card["exec_spec"]["capability_fit"]["gaps"][1] = {
        "capability": "田间数据采集", "disposition": "blocking",
        "note": "合作农场退出，田间采集通道不存在且无替代"}
    errs = check_transition(card, "finalized_executable")
    assert any("构成不可行" in e for e in errs)
    card["finalization_level"] = "conceptual"
    errs = check_transition(card, "finalized_conceptual")
    assert not any("capability" in e or "能力" in e for e in errs), errs


def test_pre_mortem_requires_capability_match_item():
    card = full_card("novelty_checked")
    del card["pre_mortem"]["checklist"]["capability_match"]
    errs = check_transition(card, "pre_mortem_passed")
    assert any("capability_match" in e for e in errs)


def test_rank_standings_carry_capability_summary(project):
    from light_idea.duel import rank_project, record_duel
    a = full_card()
    b = full_card()
    b["idea_id"] = "another-idea_000bbb"
    b["exec_spec"]["capability_fit"] = None
    record_duel(a, b, a["idea_id"], by="judge-x", note="判语")
    rank = rank_project(project, [a, b])
    by_id = {s["idea_id"]: s for s in rank["standings"]}
    cap_a = by_id[a["idea_id"]]["capability"]
    assert cap_a["assessed"] is True
    assert cap_a["counts"] == {"have": 1, "fillable": 1, "blocking": 0}
    assert cap_a["worst"] == "fillable"
    assert by_id[b["idea_id"]]["capability"]["worst"] == "unassessed"


def test_capability_summary_unassessed():
    card = full_card()
    card["exec_spec"]["capability_fit"] = None
    s = capability_summary(card)
    assert s["assessed"] is False and s["worst"] == "unassessed"


def test_card_md_and_handoff_render_capability():
    from light_idea.export import _render_handoff
    from light_idea.project import render_card_md
    card = full_card("finalized_conceptual")
    card["finalization_level"] = "conceptual"
    md = render_card_md(card)
    assert "能力匹配区" in md and "可短期补" in md
    handoff = _render_handoff(card, "2026-10-21")
    assert "能力匹配" in handoff and "队伍现状" in handoff

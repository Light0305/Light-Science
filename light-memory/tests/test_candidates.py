"""候选通道：判断性提炼只产候选、accept 才生效、reject 留痕；
蒸馏双向接口（八字段校验、导出只供最新冻结版、回流走候选门）。"""

import pytest

from light_memory import candidates as cand
from light_memory import project as project_mod


def _fact_content(statement="候选教训：先备份再迁移", valid="2026-03-01",
                  verdict="store"):
    return {"nomination": {
        "verdict": verdict,
        "fact": {"statement": statement, "fact_type": "lesson",
                 "object_id": "run:R-NEG-a1", "valid_at": valid}}}


def _entry(version=1, rule_id="DG-X01"):
    return {"rule_id": rule_id,
            "statement_faithful": "审稿人原话：样本量须交代",
            "statement_normalized": "投稿前核查样本量交代",
            "source_class": "历史校准",
            "explicit_or_inferred": {"mode": "Inferred",
                                      "confidence": 0.7},
            "provenance_ptr": "review-pkg/concern RV-C001",
            "scope": {"journals": ["SAT"], "priority": "overlay_wins"},
            "distilled_at": "2026-10-20", "version": version}


def _facts(root):
    return project_mod.load_package(root)["facts"]


# ---------------------------------------------------------------- 通道

def test_propose_does_not_enter_facts_until_accept(mem_root):
    before = len(_facts(mem_root))
    row = cand.propose(mem_root, "fact", _fact_content(),
                       nominator="tester", confidence=0.8)
    assert row["status"] == "pending"
    assert len(_facts(mem_root)) == before  # 未 accept 不入账
    done = cand.accept(mem_root, row["candidate_id"], by="user")
    assert done["status"] == "accepted"
    assert done["result_ref"]
    facts = _facts(mem_root)
    assert len(facts) == before + 1
    assert any(f["fact_id"] == done["result_ref"] for f in facts)


def test_reject_leaves_trace_without_fact(mem_root):
    row = cand.propose(mem_root, "fact", _fact_content(),
                       nominator="tester")
    cand.reject(mem_root, row["candidate_id"], by="user", note="不成立")
    kept = cand.get_candidate(mem_root, row["candidate_id"])
    assert kept["status"] == "rejected"
    assert kept["decided_by"] == "user"
    assert _facts(mem_root) == []
    with pytest.raises(cand.CandidateError):
        cand.accept(mem_root, row["candidate_id"], by="user")


def test_propose_rejects_non_judgmental_kind(mem_root):
    # 确定性提炼走 intake，不许借候选通道（通道分工的代码层分界）
    with pytest.raises(cand.CandidateError):
        cand.propose(mem_root, "intake", {"x": 1}, nominator="t")
    with pytest.raises(cand.CandidateError):
        cand.propose(mem_root, "fact", {"nomination": {"verdict": "x"}},
                     nominator="t")


def test_accept_execution_failure_keeps_candidate_pending(mem_root):
    # supersede 缺时间戳 → 一期判定 blocked_no_timestamps：
    # accept 不许半生效，候选保持 pending 并点名
    content = {"nomination": {
        "verdict": "supersede", "target_fact_id": "fact_missing",
        "fact": {"statement": "新口径", "fact_type": "conclusion",
                 "object_id": "claim:C1", "valid_at": None}}}
    row = cand.propose(mem_root, "fact", content, nominator="t")
    with pytest.raises(cand.CandidateError):
        cand.accept(mem_root, row["candidate_id"], by="user")
    assert cand.get_candidate(
        mem_root, row["candidate_id"])["status"] == "pending"


def test_annotation_candidate_accept_lands_event_only(mem_root):
    row = cand.propose(
        mem_root, "annotation",
        {"text": "投稿时带限定语", "vault_note": "claim-c1.md",
         "object_id": "claim:C1"},
        nominator="obsidian-readback", origin="annotation_readback")
    events = project_mod.load_package(mem_root)["events"]
    assert not any(e["type"] == "annotation" for e in events)
    cand.accept(mem_root, row["candidate_id"], by="user")
    events = project_mod.load_package(mem_root)["events"]
    assert any(e["type"] == "annotation" for e in events)
    assert _facts(mem_root) == []  # 标注不冒充事实


# ---------------------------------------------------------------- 蒸馏

def test_distill_entry_eight_fields_enforced(mem_root):
    bad = _entry()
    del bad["provenance_ptr"]
    with pytest.raises(cand.CandidateError):
        cand.propose(mem_root, "distill_rule", {"entry": bad},
                     nominator="d")
    bad2 = _entry()
    bad2["source_class"] = "瞎编的类别"
    with pytest.raises(cand.CandidateError):
        cand.propose(mem_root, "distill_rule", {"entry": bad2},
                     nominator="d")


def test_distill_export_only_latest_frozen_version(mem_root):
    for v in (1, 2):
        row = cand.propose(mem_root, "distill_rule",
                           {"entry": _entry(version=v)}, nominator="d")
        cand.accept(mem_root, row["candidate_id"], by="user")
    out = cand.distill_export(mem_root)
    assert out["count"] == 1
    entry = out["doc"]["entries"][0]
    assert entry["version"] == 2
    # 覆盖层压平形：mode/confidence 拆键、precedence 单列
    assert entry["explicit_or_inferred"] == "Inferred"
    assert entry["confidence"] == 0.7
    assert entry["precedence"] == "overlay_wins"
    assert out["doc"]["format"] == "review-overlay"


def test_distill_export_empty_before_any_accept(mem_root):
    row = cand.propose(mem_root, "distill_rule", {"entry": _entry()},
                       nominator="d")
    assert cand.distill_export(mem_root)["count"] == 0
    assert row["status"] == "pending"


def test_distill_import_goes_through_candidate_gate(mem_root, tmp_path):
    src = cand.propose(mem_root, "distill_rule", {"entry": _entry()},
                       nominator="d")
    cand.accept(mem_root, src["candidate_id"], by="user")
    exported = cand.distill_export(mem_root)
    other = tmp_path / "memory2"
    project_mod.init_package(other, project_id="p2")
    created = cand.distill_import(other, exported["path"],
                                  nominator="review-return")
    assert created[0]["status"] == "pending"
    assert created[0]["origin"] == "review_return"
    # 回流只产候选：语料库仍为空，导出为 0
    assert cand.load_corpus(other) == []
    assert cand.distill_export(other)["count"] == 0


def test_distill_import_rejects_incomplete_entry(mem_root, tmp_path):
    import json
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"entries": [{"rule_id": "DG-BAD"}]}),
                 encoding="utf-8")
    with pytest.raises(cand.CandidateError):
        cand.distill_import(mem_root, p, nominator="review-return")
    assert cand.list_candidates(mem_root) == []

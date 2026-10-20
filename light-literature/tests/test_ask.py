"""LIT-D01 ask 问语料测试：白名单、拒答、上限、未核实排除。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_literature import ask as ask_mod
from light_literature.util import write_yaml


def _paper(proj: Path, pid: str, blocks: list[dict], **yaml_extra):
    pdir = proj / "Literature" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    write_yaml(pdir / "paper.yaml",
               {"paper_id": pid, "title": pid, **yaml_extra})
    (pdir / "source_map.json").write_text(json.dumps(
        {"paper_id": pid, "blocks": blocks, "pending_pages": []}),
        encoding="utf-8")


def _corpus(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    _paper(proj, "turkey_paper1", [
        {"id": "S001", "page": 1, "type": "text", "order": 1,
         "text": "The detector achieved 88.2 percent accuracy on turkey "
                 "behaviour videos from the barn cameras."},
        {"id": "S002", "page": 2, "type": "text", "order": 2,
         "text": "Feather pecking events were counted manually."},
    ])
    _paper(proj, "vision_paper2", [
        {"id": "S001", "page": 1, "type": "text", "order": 1,
         "text": "A residual network for image classification tasks."},
    ])
    _paper(proj, "unverified_paper3", [
        {"id": "S001", "page": 1, "type": "text", "order": 1,
         "text": "The zebraquark detector reached 99.9 percent accuracy."},
    ], identity_status="unverifiable")
    return proj


def test_ask_hits_and_record_written(tmp_path):
    proj = _corpus(tmp_path)
    r = ask_mod.ask(proj, "What accuracy did the detector achieve on "
                          "turkey behaviour?")
    assert r["status"] == "awaiting_answer" and r["hits"] >= 1
    text = Path(r["record"]).read_text(encoding="utf-8")
    assert "turkey_paper1" in text and "S001" in text


def test_ask_answer_with_valid_citation(tmp_path):
    proj = _corpus(tmp_path)
    r = ask_mod.ask(
        proj, "What accuracy did the detector achieve on turkey behaviour?",
        answer="The detector achieved 88.2 percent accuracy.",
        citations=["turkey_paper1#S001"])
    assert r["status"] == "answered"
    assert r["citations"] == ["turkey_paper1#S001"]


def test_ask_citation_outside_whitelist_rejected(tmp_path):
    proj = _corpus(tmp_path)
    with pytest.raises(ValueError, match="白名单"):
        ask_mod.ask(
            proj, "What accuracy did the detector achieve on turkey "
                  "behaviour?",
            answer="made up", citations=["vision_paper2#S001"])


def test_ask_citation_cap_enforced(tmp_path):
    proj = _corpus(tmp_path)
    with pytest.raises(ValueError, match="上限"):
        ask_mod.ask(
            proj, "detector accuracy turkey behaviour feather pecking",
            answer="x", citations=["turkey_paper1#S001",
                                   "turkey_paper1#S002"],
            max_citations=1)


def test_ask_unverified_paper_blocks_excluded(tmp_path):
    proj = _corpus(tmp_path)
    r = ask_mod.ask(proj, "What are the zebraquark measurement results?")
    assert r["status"] == "refused"          # 唯一命中在未核实论文里
    assert r["excluded"] and \
        r["excluded"][0]["paper_id"] == "unverified_paper3"
    text = Path(r["record"]).read_text(encoding="utf-8")
    assert ask_mod.REFUSAL_TEXT in text


def test_ask_single_generic_word_is_not_evidence(tmp_path):
    # 问题与语料只共享一个泛词 (energy) → 不构成证据，必须拒答
    proj = tmp_path / "proj"
    _paper(proj, "farm_paper", [
        {"id": "S001", "page": 1, "type": "text", "order": 1,
         "text": "Farm staff manually evaluate the video data because "
                 "the energy cost of manual review is high."},
    ])
    r = ask_mod.ask(proj, "How is energy produced in chloroplasts?")
    assert r["status"] == "refused" and r["hits"] == 0


def test_ask_out_of_corpus_refusal(tmp_path):
    proj = _corpus(tmp_path)
    r = ask_mod.ask(proj, "How does photosynthesis chlorophyll work?")
    assert r["status"] == "refused" and r["hits"] == 0
    # 拒答时不许附答案
    with pytest.raises(ValueError, match="拒答"):
        ask_mod.ask(proj, "How does photosynthesis chlorophyll work?",
                    answer="Plants use sunlight.")

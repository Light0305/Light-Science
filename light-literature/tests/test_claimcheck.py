"""LIT-D04 claim-support 测试：定位、三值落字、机械校验拒假支持。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_literature import claimcheck
from light_literature.util import write_yaml


def _paper(proj: Path, pid: str, blocks: list[dict], **yaml_extra):
    pdir = proj / "Literature" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    write_yaml(pdir / "paper.yaml",
               {"paper_id": pid, "title": pid, **yaml_extra})
    (pdir / "source_map.json").write_text(json.dumps(
        {"paper_id": pid, "blocks": blocks, "pending_pages": []}),
        encoding="utf-8")
    return pdir


def _corpus(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    _paper(proj, "paper-a_aaa111", [
        {"id": "S001", "page": 1, "type": "text", "order": 1,
         "text": "The model achieved an accuracy of 92.5 percent on the "
                 "held-out test set of 1200 images."},
        {"id": "S002", "page": 2, "type": "text", "order": 2,
         "text": "Training used a learning rate of 0.01 for 30 epochs."},
    ])
    _paper(proj, "paper-b_bbb222", [
        {"id": "S001", "page": 1, "type": "text", "order": 1,
         "text": "A survey of graph neural networks for chemistry."},
    ])
    return proj


def _ledger(proj: Path) -> list[dict]:
    path = proj / "Literature" / "claim_support.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_locate_finds_anchor(tmp_path):
    proj = _corpus(tmp_path)
    r = claimcheck.locate_claim(proj, "accuracy of 92.5 percent")
    assert r["status"] == "located"
    top = r["candidates"][0]
    assert top["paper_id"] == "paper-a_aaa111" and top["anchor"] == "S001"
    assert top["matched_numbers"] == ["92.5"]


def test_locate_not_mentioned_is_honest(tmp_path):
    proj = _corpus(tmp_path)
    r = claimcheck.locate_claim(
        proj, "quantum entanglement entropy of black holes")
    assert r["status"] == "not_mentioned"
    assert r["candidates"] == []


def test_record_supports_with_matching_numbers(tmp_path):
    proj = _corpus(tmp_path)
    row = claimcheck.record_claim_check(
        proj, "paper-a_aaa111",
        "The model achieved an accuracy of 92.5 percent",
        "supports", anchors=["S001"])
    assert row["claim_id"] == "CS001" and row["verdict"] == "supports"
    assert row["signals"]["numbers_missing_in_cited"] == []
    rows = _ledger(proj)
    assert len(rows) == 1 and rows[0]["anchors"] == ["S001"]
    # 只增：第二条追加不改第一条
    claimcheck.record_claim_check(
        proj, "paper-a_aaa111", "Training used a learning rate of 0.01",
        "supports", anchors=["S002"])
    rows = _ledger(proj)
    assert [r["claim_id"] for r in rows] == ["CS001", "CS002"]


def test_supports_rejected_when_numbers_mismatch(tmp_path):
    proj = _corpus(tmp_path)
    with pytest.raises(ValueError, match="逐字出现"):
        claimcheck.record_claim_check(
            proj, "paper-a_aaa111",
            "The model achieved an accuracy of 95.0 percent",
            "supports", anchors=["S001"])
    assert _ledger(proj) == []  # 拒绝写入，不留半成品


def test_contradicts_records_missing_numbers_as_signal(tmp_path):
    proj = _corpus(tmp_path)
    row = claimcheck.record_claim_check(
        proj, "paper-a_aaa111",
        "The model achieved an accuracy of 95.0 percent",
        "contradicts", anchors=["S001"])
    assert row["signals"]["numbers_missing_in_cited"] == ["95.0"]
    assert row["signals"]["numbers_found_in_cited"] == []


def test_fake_anchor_rejected(tmp_path):
    proj = _corpus(tmp_path)
    with pytest.raises(ValueError, match="不存在"):
        claimcheck.record_claim_check(
            proj, "paper-a_aaa111", "anything", "supports",
            anchors=["S999"])


def test_not_mentioned_without_anchors(tmp_path):
    proj = _corpus(tmp_path)
    row = claimcheck.record_claim_check(
        proj, "paper-a_aaa111",
        "The paper studies quantum entanglement entropy",
        "not_mentioned")
    assert row["signals"]["reason"] == "no_block_mentions"

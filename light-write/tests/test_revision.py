"""W7 返修子包：意见登记、逐条回复、双向对账、回复信绑定与 STALE。"""

from pathlib import Path

import pytest

from light_write.revision import (
    RevisionError, add_comment, add_response, bind_revision, check_revision,
    load_responses, save_responses,
)


def _setup(root):
    c1 = add_comment(root, "Reviewer 1", "主要结论的措辞过强，请降格或补证据。",
                     category="major", claim_ids=["C2"])
    c2 = add_comment(root, "Reviewer 2", "方法节请补充段数说明。",
                     category="minor", section_ids=["S-methods"])
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8")
                     + "\nRevised sentence. [rev:RC001]\n", encoding="utf-8")
    add_response(root, c1["comment_id"], "partial",
                 "已将措辞降格至 suggestive 档并在局限中说明。",
                 change_anchors=[{"file": "01-introduction.md",
                                  "marker": "RC001"}])
    add_response(root, c2["comment_id"], "reject",
                 "段数已在结果节图注中给出，方法节不重复。")
    return c1, c2


def test_revision_full_cycle_and_bind(drafted_pkg):
    root = drafted_pkg["root"]
    _setup(root)
    result = check_revision(root)
    assert result["ok"] is True, result["findings"]
    assert result["coverage"] == {"comments": 2, "responses": 2}
    bound = bind_revision(root)
    assert (root / "revision" / "response_letter.md").exists()
    letter = (root / "revision" / "response_letter.md").read_text(
        encoding="utf-8")
    assert bound["bound_manuscript_hash"] in letter
    assert check_revision(root)["stale"] is False


def test_revision_unanswered_comment_fails(drafted_pkg):
    root = drafted_pkg["root"]
    c1, _ = _setup(root)
    doc = load_responses(root)
    doc["responses"] = [r for r in doc["responses"]
                        if r["comment_id"] != c1["comment_id"]]
    save_responses(root, doc)
    result = check_revision(root)
    assert result["ok"] is False
    assert any(f["code"] == "revision.unanswered"
               for f in result["findings"])


def test_revision_anchor_claim_without_marker_fails(drafted_pkg):
    root = drafted_pkg["root"]
    c1 = add_comment(root, "Reviewer 1", "请修改引言。", category="major")
    add_response(root, c1["comment_id"], "accept", "已改。",
                 change_anchors=[{"file": "01-introduction.md",
                                  "marker": "RC999"}])
    result = check_revision(root)
    assert result["ok"] is False
    assert any(f["code"] == "revision.anchor_not_in_text"
               for f in result["findings"])


def test_revision_unclaimed_change_marker_fails(drafted_pkg):
    root = drafted_pkg["root"]
    _setup(root)
    disc = Path(root) / "sections" / "04-discussion.md"
    disc.write_text(disc.read_text(encoding="utf-8")
                    + "\nQuietly changed. [rev:RC777]\n", encoding="utf-8")
    result = check_revision(root)
    assert result["ok"] is False
    assert any(f["code"] == "revision.unclaimed_change"
               for f in result["findings"])


def test_revision_letter_stale_after_edit(drafted_pkg):
    root = drafted_pkg["root"]
    _setup(root)
    bind_revision(root)
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8")
                     + "One more edit.\n", encoding="utf-8")
    result = check_revision(root)
    assert result["stale"] is True
    assert result["ok"] is False
    assert any(f["code"] == "revision.letter_stale"
               for f in result["findings"])


def test_revision_accept_without_anchor_rejected(drafted_pkg):
    root = drafted_pkg["root"]
    c1 = add_comment(root, "Reviewer 1", "请大改。", category="major")
    with pytest.raises(RevisionError):
        add_response(root, c1["comment_id"], "accept", "好的。")
    with pytest.raises(RevisionError):
        add_response(root, c1["comment_id"], "partial", "", )

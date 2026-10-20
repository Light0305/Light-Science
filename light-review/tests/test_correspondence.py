"""图对应清单消费侧（v1.1 REV-D09）：源链真检 / 矛盾检出 / 未覆盖维持未检。"""

import hashlib

from light_review.checkers import check_numbers_figures

SRC = b"<svg>source</svg>"
SRC_HASH = hashlib.sha256(SRC).hexdigest()
DELIV_HASH = hashlib.sha256(b"%PDF-delivered").hexdigest()
CONTENT_HASH = "c" * 64


def _manifest(**over):
    fig = {"figure_id": "F001", "display_number": 1,
           "source_ref": "assets/fig1.svg", "source_hash": SRC_HASH,
           "caption": "Distribution of segment-level scores."}
    fig.update(over)
    return [fig]


def _delivery(corr=None, files=None):
    row = {"fig_id": "fig-1", "kind": "data",
           "files": files or [{"path": "exports/fig-1.pdf",
                               "sha256": DELIV_HASH, "role": "main_pdf"}]}
    if corr is not None:
        row["correspondence"] = corr
    return {"figures": [row]}


def _corr(**over):
    corr = {"source_assets": [{"role": "source", "path": "assets/fig1.svg",
                               "sha256": SRC_HASH}],
            "deliverables": [{"path": "exports/fig-1.pdf",
                              "sha256": DELIV_HASH}],
            "content_hash": CONTENT_HASH,
            "note": None}
    corr.update(over)
    return corr


def test_source_chain_verified_across_formats():
    checks, findings = check_numbers_figures(
        _manifest(), _delivery(corr=_corr()), set())
    row = checks[0]
    assert row["result"] == "pass"
    assert "源链真检" in row["detail"]
    assert findings == []


def test_deliverable_hash_contradiction_detected():
    bad = _corr(deliverables=[{"path": "exports/fig-1.pdf",
                               "sha256": "0" * 64}])
    checks, findings = check_numbers_figures(
        _manifest(), _delivery(corr=bad), set())
    assert checks[0]["result"] == "error"
    assert any(f["category"] == "provenance_gap" for f in findings)


def test_content_hash_mismatch_detected():
    checks, findings = check_numbers_figures(
        _manifest(content_hash="a" * 64), _delivery(corr=_corr()), set())
    assert checks[0]["result"] == "error"
    assert any("内容级哈希" in (f["detail"] or "") for f in findings)


def test_content_hash_match_verified():
    checks, findings = check_numbers_figures(
        _manifest(content_hash=CONTENT_HASH), _delivery(corr=_corr()),
        set())
    assert checks[0]["result"] == "pass"
    assert "内容级哈希两侧一致" in checks[0]["detail"]


def test_uncovered_source_stays_not_assessable():
    other = _corr(source_assets=[{"role": "script",
                                   "path": "scripts/plot.py",
                                   "sha256": "9" * 64}])
    checks, findings = check_numbers_figures(
        _manifest(), _delivery(corr=other), set())
    assert checks[0]["result"] == "not_assessable"
    assert "未覆盖" in checks[0]["detail"]
    assert findings == []


def test_no_correspondence_keeps_v10_behavior():
    checks, findings = check_numbers_figures(
        _manifest(), _delivery(corr=None), set())
    assert checks[0]["result"] == "not_assessable"
    assert "哈希对应未检" in checks[0]["detail"]


def test_empty_correspondence_note_surfaces():
    empty = {"source_assets": [], "deliverables": [],
             "content_hash": None, "note": "方法图重绘未完成"}
    checks, _ = check_numbers_figures(
        _manifest(), _delivery(corr=empty), set())
    assert checks[0]["result"] == "not_assessable"
    assert "重绘未完成" in checks[0]["detail"]

"""provenance 更新命令：append-only history、supersede 链、哈希格式门。"""

import pytest

from light_figure.project import load_package, provenance_row
from light_figure.provenance import (
    ProvenanceError, provenance_history, update_provenance_row,
)
from conftest import FAKE_HASH, FIG_DATA, FIG_METHOD


def test_update_writes_history_with_supersede_chain(pkg):
    root = pkg["root"]
    before = provenance_history(root, FIG_DATA)
    row = update_provenance_row(root, FIG_DATA,
                                {"script_hash": FAKE_HASH}, by="tester")
    assert row["script_hash"] == FAKE_HASH
    history = provenance_history(root, FIG_DATA)
    assert len(history) == len(before) + 1
    entry = history[-1]
    assert entry["by"] == "tester"
    assert entry["changes"]["script_hash"]["to"] == FAKE_HASH
    assert entry["changes"]["script_hash"]["from"] is None
    assert len(entry["supersedes"]) == 64
    # 二次更新的 supersedes 指向上一条的 row_hash
    update_provenance_row(root, FIG_DATA,
                          {"source_data_hash": FAKE_HASH}, by="tester")
    history = provenance_history(root, FIG_DATA)
    assert history[-1]["supersedes"] == history[-2]["row_hash"]


def test_update_rejects_bad_hash(pkg):
    with pytest.raises(ProvenanceError):
        update_provenance_row(pkg["root"], FIG_DATA,
                              {"script_hash": "not-a-hash"})


def test_update_rejects_malformed_redraw_source(pkg):
    with pytest.raises(ProvenanceError):
        update_provenance_row(pkg["root"], FIG_METHOD,
                              {"redraw_source": {"path": "x.vsdx"}})


def test_update_unknown_figure(pkg):
    with pytest.raises(ProvenanceError):
        update_provenance_row(pkg["root"], "fig-nope",
                              {"script_hash": FAKE_HASH})


def test_update_persists_to_disk(pkg):
    update_provenance_row(pkg["root"], FIG_DATA,
                          {"runtime_version": "python 3.12"}, by="t")
    data = load_package(pkg["root"])
    row = provenance_row(data["provenance"], FIG_DATA)
    assert row["runtime_version"] == "python 3.12"
    assert data["provenance"]["history"][-1]["fig_id"] == FIG_DATA

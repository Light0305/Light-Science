"""W5 图表回填三方对账与编号冻结：追加编号、全量重编、账实不符检出。"""

from pathlib import Path

from light_write.figures import (
    add_figure, check_figures, freeze_numbering, mark_delivered, set_caption,
    sync_intext_refs,
)
from light_write.project import load_package, save_figures


def _place(root, fid="F001"):
    results = Path(root) / "sections" / "03-results.md"
    results.write_text(
        results.read_text(encoding="utf-8")
        + f"\nOverview of the pipeline [fig:{fid}].\n"
        + "Figure 1. Pipeline overview diagram.\n",
        encoding="utf-8")


def test_figures_backfill_three_way_ok(drafted_pkg):
    root = drafted_pkg["root"]
    add_figure(root, "F001")
    _place(root)
    sync_intext_refs(root)
    set_caption(root, "F001", "Pipeline overview diagram.")
    mark_delivered(root, "F001", "figure/pkg/fig1.pdf", "abc123",
                   backfill=True)
    result = check_figures(root)
    assert result["ok"] is True, result["findings"]


def test_figures_intext_refs_mismatch_detected(drafted_pkg):
    root = drafted_pkg["root"]
    add_figure(root, "F001")
    _place(root)
    # 不跑 sync：intext_refs 仍为空，与正文实位不符 → 对账报错
    result = check_figures(root)
    assert result["ok"] is False
    assert any(f["code"] == "figures.intext_refs_mismatch"
               for f in result["findings"])


def test_figures_caption_not_in_text_detected(drafted_pkg):
    root = drafted_pkg["root"]
    add_figure(root, "F001")
    _place(root)
    sync_intext_refs(root)
    set_caption(root, "F001", "A caption that never appears in the text.")
    mark_delivered(root, "F001", "figure/pkg/fig1.pdf", "abc123",
                   backfill=True)
    result = check_figures(root)
    assert result["ok"] is False
    assert any(f["code"] == "figures.caption_not_in_text"
               for f in result["findings"])


def test_freeze_numbering_then_append_only(drafted_pkg):
    root = drafted_pkg["root"]
    add_figure(root, "F001")
    _place(root)
    sync_intext_refs(root)
    frozen = freeze_numbering(root)
    assert frozen["order"] == ["F001"]
    rows = {r["figure_id"]: r
            for r in load_package(root)["figures"]["figures"]}
    assert rows["F001"]["display_number"] == 1
    assert rows["F001"]["display_label"] == "Figure 1"
    # 冻结后新增：只许追加编号 + 落变更日志
    add_figure(root, "F002")
    figures = load_package(root)["figures"]
    rows = {r["figure_id"]: r for r in figures["figures"]}
    assert rows["F002"]["display_number"] == 2
    changes = figures["numbering"]["changes"]
    assert any(c["action"] == "append_after_freeze" for c in changes)


def test_freeze_renumber_all_logs_change(drafted_pkg):
    root = drafted_pkg["root"]
    add_figure(root, "F001")
    add_figure(root, "F002")
    _place(root, "F002")
    _place(root, "F001")
    sync_intext_refs(root)
    freeze_numbering(root)
    figures = load_package(root)["figures"]
    rows = {r["figure_id"]: r for r in figures["figures"]}
    # F002 先出现 → Figure 1；全量重编后次序对调并落日志
    assert rows["F002"]["display_number"] == 1
    out = freeze_numbering(root, renumber=True)
    assert out["frozen"] is True
    changes = load_package(root)["figures"]["numbering"]["changes"]
    assert changes[-1]["action"] == "renumber_all"

"""图组（figure group）规则与 verify 组级口径测试。

分组规则有纯函数单测固化（图注亲和合并远距离面板、图注屏障阻断
几何合并、不同最近图注不合并）；verify 组级测试用手工 middle_json
块经 parse.build_source_map 造出双分片图组后篡改 source_map，固化
校验语义。

（源自开发期第六增量测试：纯函数原属本地抽取管线，发布版已迁入
parse 模块；原集成测试走本地抽取端到端与 mixed 页路由，随研究
存档一并剔除，不在本产品发布中。）
"""

from __future__ import annotations

from light_literature import parse as parse_mod
from light_literature import project, triage, verify
from light_literature.parse import _group_figures
from light_literature.util import literature_dir, read_json, read_yaml, write_json


def _fig(x0, y0, x1, y1):
    return {"_kind": "figure", "bbox": [x0, y0, x1, y1]}


def _cap(x0, y0, x1, y1):
    return {"_kind": "caption", "bbox": [x0, y0, x1, y1],
            "caption_kind": "figure"}


# ---------- 图组：纯函数规则 ----------

def test_group_affinity_merges_distant_panels():
    """两面板间隙远超几何阈值，但最近图注相同 → 图注亲和合并一组。"""
    cap = _cap(108, 275, 504, 295)
    figs = [_fig(175, 94, 239, 221), _fig(347, 83, 467, 267)]
    groups = _group_figures(figs, [cap], [cap])
    assert len(groups) == 1 and len(groups[0]) == 2


def test_group_different_nearest_captions_stay_separate():
    cap_a = _cap(50, 200, 280, 220)
    cap_b = _cap(50, 500, 280, 520)
    figs = [_fig(60, 100, 270, 190), _fig(60, 400, 270, 490)]
    groups = _group_figures(figs, [cap_a, cap_b], [cap_a, cap_b])
    assert len(groups) == 2


def test_group_geometric_merge_and_caption_barrier():
    """无图注归属时靠几何相邻合并；两块之间夹着图注则屏障阻断。"""
    figs = [_fig(74, 99, 122, 224), _fig(74, 251, 122, 313)]  # 间隙 27pt
    assert len(_group_figures(figs, [], [])) == 1
    barrier = _cap(50, 230, 286, 245)  # 位于两块之间的图注
    groups = _group_figures(figs, [barrier], [])
    assert len(groups) == 2


def test_group_geometric_blocked_by_different_nearest_captions():
    """几何相邻但各自最近图注不同（如上下两幅独立图）→ 不合并。"""
    cap_a = _cap(50, 183, 545, 202)
    cap_b = _cap(50, 339, 286, 380)
    figs = [_fig(100, 72, 496, 173), _fig(62, 212, 275, 329)]
    groups = _group_figures(figs, [cap_a, cap_b], [cap_a, cap_b])
    assert len(groups) == 2


# ---------- 图组：verify 组级口径（篡改 source_map 固化校验语义） ----------

def _grouped_paper(tmp_path, demo_pdf):
    """造一篇带双分片图组的论文：ingest 合成 PDF 后，用手工
    middle_json 块经 parse.build_source_map 生成 source_map
    （图注亲和把两分片并为一组、共享同一图注）。"""
    proj = tmp_path / "proj"
    info = project.ingest(proj, demo_pdf, title="Two Panels One Caption")
    pid = info["paper_id"]
    pdir = literature_dir(proj) / pid
    triage.triage(proj, pid)
    paper = read_yaml(pdir / "paper.yaml")
    blocks = [
        {"type": "text", "page": 1, "bbox": [72, 60, 520, 95],
         "provenance": "engine:doc2x",
         "text": "Two Panels One Caption", "text_level": 1},
        {"type": "figure", "page": 1, "bbox": [100, 300, 240, 430],
         "provenance": "engine:doc2x",
         "asset": "assets/figures/panel_a.png"},
        {"type": "figure", "page": 1, "bbox": [280, 300, 420, 430],
         "provenance": "engine:doc2x",
         "asset": "assets/figures/panel_b.png"},
        {"type": "caption", "page": 1, "bbox": [100, 440, 420, 465],
         "provenance": "engine:doc2x",
         "text": "Figure 1: Two panels sharing one caption.",
         "caption_of": 1},
    ]
    smap, md_text, _stats = parse_mod.build_source_map(blocks, paper)
    figs = [b for b in smap["blocks"] if b.get("type") == "figure"]
    assert len(figs) == 2
    assert len({b["group_id"] for b in figs}) == 1
    assert all(b["group_role"] == "fragment" for b in figs)
    assert len({b["caption_id"] for b in figs}) == 1
    write_json(pdir / "source_map.json", smap)
    (pdir / "原文.md").write_text(md_text, encoding="utf-8")
    for name in ("panel_a.png", "panel_b.png"):
        fig = pdir / "assets" / "figures" / name
        fig.parent.mkdir(parents=True, exist_ok=True)
        fig.write_bytes(b"\x89PNG fake test asset")
    return proj, pid, pdir


def _tamper_smap(pdir, fn):
    smap = read_json(pdir / "source_map.json")
    fn(smap)
    write_json(pdir / "source_map.json", smap)


def test_verify_group_member_marked_no_caption_is_error(tmp_path, demo_pdf):
    proj, pid, pdir = _grouped_paper(tmp_path, demo_pdf)

    def tamper(smap):
        figs = [b for b in smap["blocks"] if b.get("type") == "figure"]
        figs[1]["caption_id"] = None
        figs[1]["no_caption"] = True  # 组已配图注，成员却标 no_caption

    _tamper_smap(pdir, tamper)
    report = verify.verify(proj, pid)
    assert not report["ok"]
    assert any("no_caption" in e and "不一致" in e
               for e in report["errors"])


def test_verify_unpaired_group_warns_once(tmp_path, demo_pdf):
    proj, pid, pdir = _grouped_paper(tmp_path, demo_pdf)

    def tamper(smap):
        for b in smap["blocks"]:
            if b.get("type") == "figure":
                b["caption_id"] = None
                b["no_caption"] = True

    _tamper_smap(pdir, tamper)
    report = verify.verify(proj, pid)
    group_warnings = [w for w in report["warnings"] if "整组无图注" in w]
    assert len(group_warnings) == 1  # 整组只警告一次，不按分片逐块警告

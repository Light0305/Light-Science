"""锚点校验器 + 图注配对检查 + 译文对齐校验。

校验范围：原文.md 内部锚点与 source_map.json 的一致性、F/T/E 块的
资产/内容对应、图注配对与编号序列、孤儿图注；以及（原文_中文翻译.md
存在时）译文与原文的锚点 ID 集合一致、逐块回指行格式与页码正确。
没有译文文件时译文一节标 skipped，不算失败。

图注配对自第六增量起按图组（figure group）口径校验：带 group_id 的
F 块按组判（组内共享同一 caption_id 才算配对，no_caption 只对整组
判）；无 group_id 的 F 块（旧版 source_map）自成单块组；表格不分组，
仍逐块判。
"""

from __future__ import annotations

import re
from pathlib import Path

from .util import load_paper_yaml, read_json, save_paper_yaml, write_json

_ANCHOR_RE = re.compile(r'<a id="([SCFTE]\d+)"></a>')


def verify(project_dir: Path, paper_id: str) -> dict:
    pdir, paper = load_paper_yaml(project_dir, paper_id)
    errors: list[str] = []
    warnings: list[str] = []

    smap_path = pdir / "source_map.json"
    md_path = pdir / "原文.md"
    if not smap_path.exists() or not md_path.exists():
        report = {"paper_id": paper_id, "ok": False,
                  "errors": ["source_map.json 或 原文.md 不存在，先运行 parse（Doc2X 轨）或按 SKILL.md §5 模型直读轨生成"],
                  "warnings": [],
                  "translation": {"status": "skipped",
                                    "reason": "原文.md 不存在，无从校验译文"}}
        write_json(pdir / "verify_report.json", report)
        return report
    smap = read_json(smap_path)
    md_text = md_path.read_text(encoding="utf-8")

    anchored = [b for b in smap["blocks"] if b.get("id")]
    smap_ids = [b["id"] for b in anchored]
    md_ids = _ANCHOR_RE.findall(md_text)

    # 1) 锚点一致性：source_map 与原文.md 的锚点集合必须完全相等且不重复
    if len(smap_ids) != len(set(smap_ids)):
        errors.append("source_map 中存在重复锚点 ID")
    if len(md_ids) != len(set(md_ids)):
        errors.append("原文.md 中存在重复锚点")
    missing = set(smap_ids) - set(md_ids)
    extra = set(md_ids) - set(smap_ids)
    if missing:
        errors.append(f"原文.md 缺失锚点：{sorted(missing)}")
    if extra:
        errors.append(f"原文.md 存在 source_map 没有的锚点：{sorted(extra)}")

    # 2) F/T/E 块的资产/内容对应
    for b in anchored:
        if b["type"] == "figure":
            asset = b.get("asset")
            if not asset or not (pdir / asset).exists():
                errors.append(f"{b['id']}：图资产文件缺失（{asset}）")
        elif b["type"] == "table":
            if not b.get("table_md"):
                errors.append(f"{b['id']}：表格块缺少 table_md 内容")
        elif b["type"] == "equation":
            if not b.get("text"):
                errors.append(f"{b['id']}：公式块缺少原始文本")

    # 3) 图注配对：图按组判（组内至少一块配到图注即整组完整，组内
    #    caption_id/no_caption 标记必须一致）；表逐块判（必须有
    #    caption_id 或显式 no_caption）；编号序列单调；孤儿图注警告。
    claimed = set()
    fig_groups: dict[tuple, list[dict]] = {}
    for b in anchored:
        if b["type"] == "figure":
            key = (b["page"], b.get("group_id") or b["id"])
            fig_groups.setdefault(key, []).append(b)
    multi_groups = 0
    for (page_no, gid), members in fig_groups.items():
        if len(members) > 1:
            multi_groups += 1
        member_ids = "、".join(b["id"] for b in members)
        label = gid if len(members) > 1 else members[0]["id"]
        cap_ids = {b["caption_id"] for b in members if b.get("caption_id")}
        if len(cap_ids) > 1:
            errors.append(
                f"{label}（p.{page_no}，成员 {member_ids}）："
                f"图组成员 caption_id 不一致：{sorted(cap_ids)}")
        if cap_ids:
            claimed.update(cap_ids)
            bad = [b["id"] for b in members if b.get("no_caption")]
            if bad:
                errors.append(
                    f"{label}（p.{page_no}）：图组已配图注但成员 "
                    f"{'、'.join(bad)} 仍标 no_caption，标记不一致")
        elif all(b.get("no_caption") for b in members):
            if len(members) > 1:
                warnings.append(
                    f"{gid}（p.{page_no}，成员 {member_ids}）：整组无图注"
                    "（no_caption），待人工复核")
            else:
                warnings.append(
                    f"{members[0]['id']}：无图注（no_caption），待人工复核")
        else:
            for b in members:
                if not b.get("caption_id") and not b.get("no_caption"):
                    errors.append(
                        f"{b['id']}：既无 caption_id 也无 no_caption 标记")
    for b in anchored:
        if b["type"] == "table":
            if b.get("caption_id"):
                claimed.add(b["caption_id"])
            elif not b.get("no_caption"):
                errors.append(f"{b['id']}：既无 caption_id 也无 no_caption 标记")
            if b.get("no_caption"):
                warnings.append(f"{b['id']}：无图注（no_caption），待人工复核")
    orphans = [b["id"] for b in anchored
               if b["type"] == "caption" and b["id"] not in claimed]
    for oid in orphans:
        warnings.append(f"{oid}：孤儿图注（未配对到任何图/表块）")

    for kind, label in (("figure", "Figure"), ("table", "Table")):
        # 编号序列按 series 分组查：正文（main）与附录（appendix，
        # Table A.1 型）是两套独立编号，混查必然误报撞号/跳号。
        by_series: dict[str, list] = {}
        for b in anchored:
            if b["type"] == "caption" and b.get("caption_kind") == kind:
                by_series.setdefault(
                    b.get("caption_series") or "main",
                    []).append(b["caption_number"])
        for series, nums in by_series.items():
            tag = label if series == "main" else f"{label}（{series}）"
            if len(nums) != len(set(nums)):
                errors.append(f"{tag} 图注编号重复：{nums}")
            gaps = [n for n in range(min(nums), max(nums) + 1)
                    if n not in nums] if nums else []
            if gaps:
                warnings.append(f"{tag} 图注编号跳号：缺 {gaps}（序列 {nums}）")
            if nums != sorted(nums):
                warnings.append(f"{tag} 图注编号在文档顺序中不单调：{nums}")

    # 4) 待视觉通道页必须在原文.md 中有显式标注
    for pp in smap.get("pending_pages", []):
        if f"p.{pp['page']}（待视觉通道处理）" not in md_text:
            errors.append(f"p.{pp['page']} 为待处理页但原文.md 无显式标注")

    # 5) 译文校验：原文_中文翻译.md 存在才查；锚点集合须与 source_map
    #    完全一致且不重复，每个锚点须有格式正确、页码正确的回指行。
    translation: dict = {"status": "skipped",
                         "reason": "原文_中文翻译.md 不存在"}
    zh_path = pdir / "原文_中文翻译.md"
    if zh_path.exists():
        zh_text = zh_path.read_text(encoding="utf-8")
        zh_ids = _ANCHOR_RE.findall(zh_text)
        terrors: list[str] = []
        if len(zh_ids) != len(set(zh_ids)):
            terrors.append("原文_中文翻译.md 中存在重复锚点")
        zmissing = set(smap_ids) - set(zh_ids)
        zextra = set(zh_ids) - set(smap_ids)
        if zmissing:
            terrors.append(f"译文缺失锚点：{sorted(zmissing)}")
        if zextra:
            terrors.append(f"译文存在原文没有的锚点：{sorted(zextra)}")
        page_of = {b["id"]: b["page"] for b in anchored}
        for bid in sorted(set(zh_ids) & set(smap_ids)):
            expect = f"**原文:** 原文.md#{bid}（p.{page_of[bid]}）"
            if expect not in zh_text:
                terrors.append(f"译文 {bid}：回指行缺失或格式/页码不正确"
                               f"（应为 {expect}）")
        errors.extend(terrors)
        translation = {"status": "checked",
                       "anchors_in_translation": len(zh_ids),
                       "errors": terrors}

    report = {
        "paper_id": paper_id,
        "ok": not errors,
        "anchors_in_source_map": len(smap_ids),
        "anchors_in_md": len(md_ids),
        "figure_groups": len(fig_groups),
        "multi_fragment_groups": multi_groups,
        "orphan_captions": orphans,
        "pending_pages": [p["page"] for p in smap.get("pending_pages", [])],
        "translation": translation,
        "errors": errors,
        "warnings": warnings,
    }
    write_json(pdir / "verify_report.json", report)
    paper.setdefault("status", {})["verify"] = "done" if not errors else "failed"
    save_paper_yaml(pdir, paper)
    return report

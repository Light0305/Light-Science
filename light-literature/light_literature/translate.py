"""翻译脚手架：从 source_map.json 生成 原文_中文翻译.md。

对齐方案见 deep-read-A.md 第五节 5.4：译文独立成文件、块级同 ID 对齐——
每个块复用与 原文.md 相同的 <a id> 锚点，块首写回指行
`**原文:** 原文.md#S001（p.N）`，「同 ID」即原文↔译文的连接键。
本模块只生成脚手架（占位 + 纪律说明），译文内容由执行 agent 按 SKILL.md
逐块填写；结构正确性由 verify 的译文校验保证。
"""

from __future__ import annotations

from pathlib import Path

from .util import load_paper_yaml, read_json, save_paper_yaml

_PENDING = "（待译）"


def _anchored_blocks(smap: dict) -> list[dict]:
    """source_map 中带锚点的块，按 order 排序（与 原文.md 渲染顺序一致）。"""
    anchored = [b for b in smap["blocks"] if b.get("id")]
    return sorted(anchored, key=lambda b: b.get("order") or 0)


def _block_scaffold(block: dict, by_id: dict[str, dict]) -> str:
    bid, page, btype = block["id"], block["page"], block["type"]
    head = f'\n<a id="{bid}"></a>\n**原文:** 原文.md#{bid}（p.{page}）\n'
    if btype == "text":
        level = block.get("text_level") or 0
        prefix = "## " if level == 1 else "### " if level == 2 else ""
        conf = block.get("confidence")
        note = f"<!-- 待译正文块（置信 {conf}）；术语以 术语账本.md 为准，译后在本块末尾标 [置信: 高/中/低] -->"
        return f"{head}\n{note}\n\n{prefix}{_PENDING}\n"
    if btype == "caption":
        kind = "图注" if block.get("caption_kind") == "figure" else "表注"
        num = block.get("caption_number")
        return (f"{head}\n<!-- 待译{kind} {num}；编号与数字不译、不得改动 -->\n\n"
                f"*Caption（待译）:* {_PENDING}\n")
    if btype == "figure":
        cap_id = block.get("caption_id")
        cap_ref = f"原文.md#{cap_id}" if cap_id else "无配对图注（no_caption）"
        return (f"{head}\n<!-- 图本体不翻译：只引用资产，不复制、不改动图中数据 -->\n\n"
                f'![{bid}]({block.get("asset", "")})\n\n'
                f"**图注（待译）:** {_PENDING}（配对图注 {cap_ref}，"
                "图注全文译文写在其 C 块下）\n")
    if btype == "table":
        cap_id = block.get("caption_id")
        cap_ref = f"原文.md#{cap_id}" if cap_id else "无配对表注（no_caption）"
        return (f"{head}\n<!-- 表格数据不复制、不翻译：只译表头与表注；"
                "数据本体见原文块 -->\n\n"
                f"**表头（待译）:** {_PENDING}（表格本体见 原文.md#{bid}）\n\n"
                f"**表注（待译）:** {_PENDING}（配对表注 {cap_ref}）\n")
    if btype == "equation":
        return (f"{head}\n<!-- 公式本体与 原文.md 共享同一 E 块，本文件不重复渲染，"
                "防止两处公式漂移 -->\n\n"
                "**译注（待填）:** （待填：符号含义/公式说明；无译注时写「无」）\n")
    return f"{head}\n{_PENDING}\n"


def translate_scaffold(project_dir: Path, paper_id: str) -> dict:
    """生成 原文_中文翻译.md 脚手架；返回分类型块数统计。"""
    pdir, paper = load_paper_yaml(project_dir, paper_id)
    smap_path = pdir / "source_map.json"
    if not smap_path.exists():
        raise FileNotFoundError("source_map.json 不存在，先运行 parse（Doc2X 轨）或按 SKILL.md §5 模型直读轨生成")
    smap = read_json(smap_path)
    blocks = _anchored_blocks(smap)
    by_id = {b["id"]: b for b in blocks}

    parts = [
        f"# {paper.get('title', paper_id)}（中文翻译）\n",
        f"> paper_id: {paper_id}｜本文件为翻译脚手架：块级锚点与 原文.md 同 ID "
        "对齐，译文由执行 agent 按 SKILL.md 逐块填写。\n",
        "> 术语：统一使用项目术语账本（../术语账本.md）的规范译名，不自造术语；"
        "账本没有的术语先补账本、再翻译。\n",
        "> 置信标注：每块译文末尾标 `[置信: 高/中/低]`；低置信块（术语未定、"
        "公式密集、原文块置信低）汇总进文末「翻译记录」。\n",
        "> 公式：共享 E 块不在本文件重复渲染公式本体，只写译注。\n",
    ]
    for block in blocks:
        parts.append(_block_scaffold(block, by_id))

    pending = smap.get("pending_pages", [])
    if pending:
        plist = "、".join(f"p.{p['page']}（{p['page_kind']}）" for p in pending)
        parts.append(
            f"\n## 待视觉通道页\n\n以下页面尚未解析、无锚点块，解析补齐后再补译：{plist}\n")

    parts.append(
        "\n## 翻译记录\n\n"
        "- 低置信块：（待汇总）\n"
        "- 未定术语：（待汇总；先补 ../术语账本.md 再回填译文）\n"
        "- 存疑原文：（待汇总；原文与图表矛盾时两值并记，见 SKILL.md 证据纪律）\n")

    (pdir / "原文_中文翻译.md").write_text("".join(parts), encoding="utf-8")
    paper.setdefault("status", {})["translate"] = "scaffold"
    save_paper_yaml(pdir, paper)

    counts: dict[str, int] = {}
    for b in blocks:
        counts[b["type"]] = counts.get(b["type"], 0) + 1
    return {"paper_id": paper_id, "blocks": len(blocks), "by_type": counts,
            "pending_pages": [p["page"] for p in pending]}

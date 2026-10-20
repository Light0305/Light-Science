"""按刊披露生成（Phase 2，W4/W6）：use_log × 模板记录 G 组政策 → 披露文本。

纪律（LEARNING 约束 9/10 + 草案 §四 G 组）：
- 披露的唯一依据是流程留痕 use_log（含模型版本）；工具/版本/用途从
  留痕聚合回填，**不编造措辞**：政策缺规定标题与措辞模板且无从以
  数据渲染生成时 → 点名缺口拦停，不许临场编期刊口径的话。
- 披露位置多值（disclosure_positions）：逐位置生成并落到对应节文件
  锚点块（`<!-- light-write:disclosure:<position> -->` 包裹，可重跑替换）。
- output_validity_evaluation 子项（PLOS 口径）：须作者落字的评估说明，
  工具只检查在场（manuscript.output_validity_note），不代写。
- 生成记录落 manuscript.disclosures[]：逐位置 {section_file, text_hash,
  policy_hash, use_log_hash, generated_at}——政策或留痕变动 → 记录
  STALE，投稿就绪门检出须重跑。
"""

from __future__ import annotations

import re
from pathlib import Path

from .project import load_package, save_manuscript, section_files
from .util import component_hash, sha256_text, today

ANCHOR_FMT = "<!-- light-write:disclosure:{position} -->"
ANCHOR_END_FMT = "<!-- /light-write:disclosure:{position} -->"


class DiscloseError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _aggregate(use_log):
    def uniq(field):
        seen, out = set(), []
        for e in use_log:
            v = e.get(field)
            if v and v not in seen:
                seen.add(v)
                out.append(str(v))
        return out

    return {
        "tool": ", ".join(uniq("tool")),
        "model": ", ".join(uniq("model")),
        "version": ", ".join(
            f"{e.get('model') or e.get('tool')} {e.get('model_version')}"
            for e in use_log if e.get("model_version")),
        "purpose": "; ".join(uniq("purpose")),
        "section": ", ".join(uniq("section")),
        "date": max((e.get("date") or "" for e in use_log), default=""),
    }


def _render_text(ai_policy, use_log, manuscript) -> str:
    title = ai_policy.get("disclosure_title")
    template = ai_policy.get("disclosure_wording_template")
    agg = _aggregate(use_log)
    lines = []
    if title:
        lines.append(f"**{title}**")
        lines.append("")
    if template:
        body = template
        for key, value in agg.items():
            body = body.replace("{" + key + "}", value)
        leftover = re.findall(r"\{[a-z_]+\}", body)
        if leftover:
            raise DiscloseError([
                f"披露措辞模板含无法从 use_log 回填的占位符 {leftover}："
                "不许编造，须补 use_log 字段或改模板记录"])
        lines.append(body)
    else:
        # 无规定模板：以留痕数据逐项渲染（数据呈现，不是编造措辞）
        for e in use_log:
            lines.append(
                f"- {e.get('tool')}（{e.get('model')} "
                f"{e.get('model_version')}）：{e.get('purpose')}"
                f"（节：{e.get('section')}，{e.get('date')}）")
    if ai_policy.get("output_validity_evaluation"):
        note = manuscript.get("output_validity_note")
        if not note:
            raise DiscloseError([
                "该刊 AI 政策含 output_validity_evaluation 子项（PLOS 口径）："
                "须作者在 manuscript.yaml 的 output_validity_note 落字说明"
                "如何评估 AI 输出有效性，工具不代写"])
        lines.append("")
        lines.append(note)
    return "\n".join(lines).strip() + "\n"


def _resolve_section(manuscript, position):
    """披露位置 → 节文件：优先 role 同名节，其次 section_id 同名节。"""
    for s in manuscript.get("sections") or []:
        if s.get("role") == position:
            return s
    for s in manuscript.get("sections") or []:
        if s.get("section_id") == position:
            return s
    return None


def _upsert_block(root, section, position, text):
    fname = section.get("file")
    path = Path(root) / "sections" / fname
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    begin = ANCHOR_FMT.format(position=position)
    end = ANCHOR_END_FMT.format(position=position)
    block = f"{begin}\n{text}{end}\n"
    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    if pattern.search(content):
        content = pattern.sub(block, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n" + block
    path.write_text(content, encoding="utf-8")
    return fname


def generate_disclosures(root) -> dict:
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise DiscloseError(["稿件包不存在（先 init）"])
    record = pkg["template_record"]
    if record is None:
        raise DiscloseError(["模板核查记录未登记：无从按刊生成披露"])
    ai = (record.get("G") or {}).get("ai_policy") or {}
    if not ai.get("disclosure_required"):
        return {"generated": [], "note": "该刊 AI 政策不要求披露"
                "（disclosure_required 为假），未生成披露文本"}
    gaps = []
    use_log = manuscript.get("use_log") or []
    if not use_log:
        gaps.append("use_log 为空：无 AI 使用留痕可生成披露——先按实际使用"
                    "补登 use_log（含 model_version），不许无留痕编披露")
    if not ai.get("disclosure_title") and \
            not ai.get("disclosure_wording_template"):
        gaps.append("政策缺规定声明标题与措辞模板（G 组）：不许编造措辞，"
                    "须先按期刊官方原文补全模板记录")
    positions = ai.get("disclosure_positions") or []
    if not positions:
        gaps.append("政策 disclosure_positions 为空：披露无处落")
    if gaps:
        raise DiscloseError(gaps)
    text = _render_text(ai, use_log, manuscript)
    policy_hash = component_hash(ai)
    use_log_hash = component_hash(use_log)
    generated = []
    unresolved = []
    for position in positions:
        section = _resolve_section(manuscript, position)
        if section is None:
            unresolved.append(position)
            continue
        fname = _upsert_block(root, section, position, text)
        generated.append({
            "position": position,
            "section_file": fname,
            "text_hash": sha256_text(text),
            "policy_hash": policy_hash,
            "use_log_hash": use_log_hash,
            "generated_at": today(),
        })
    if unresolved:
        raise DiscloseError([
            f"披露位置 {unresolved} 在稿件节登记中无对应节（role/section_id "
            "均未命中）：先补节登记或修正政策记录的披露位置"])
    manuscript["disclosures"] = generated
    save_manuscript(root, manuscript)
    return {"generated": generated, "positions": positions}


def disclosures_status(root) -> dict:
    """披露新鲜度：记录齐备且 policy/use_log 哈希未漂移 → fresh。"""
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"] or {}
    record = pkg["template_record"]
    recorded = manuscript.get("disclosures") or []
    if record is None:
        return {"required": None, "complete": False, "stale": None,
                "positions_recorded": []}
    ai = (record.get("G") or {}).get("ai_policy") or {}
    if not ai.get("disclosure_required"):
        return {"required": False, "complete": True, "stale": False,
                "positions_recorded": []}
    positions = ai.get("disclosure_positions") or []
    recorded_positions = [d.get("position") for d in recorded]
    policy_hash = component_hash(ai)
    use_log_hash = component_hash(manuscript.get("use_log") or [])
    stale = any(d.get("policy_hash") != policy_hash
                or d.get("use_log_hash") != use_log_hash for d in recorded)
    files = section_files(root)
    anchors_ok = all(
        any(ANCHOR_FMT.format(position=d.get("position")) in text
            for text in files.values())
        for d in recorded)
    return {
        "required": True,
        "complete": sorted(recorded_positions) == sorted(positions)
                    and anchors_ok,
        "stale": stale or not anchors_ok,
        "positions_recorded": recorded_positions,
    }

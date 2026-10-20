"""会话沉淀规程 epilogue（MM2-01）：对话里的决策与死胡同不流失。

纪律锚点（LEARNING.md / 诊断 MM2-01）：
- 收编面只吃九包加选刊的结构化产物是缺口：项目推进中大量决策、
  试错与死胡同只发生在对话里。epilogue 是独立沉淀面，两个触发位
  ——阶段定版点、用户显式收尾——接入模型按固定六类清单扫描本
  会话，逐条带 user/AI 来源标签提名。
- 只产候选（MM-13c 铁律不变）：epilogue 不新增任何直入账路径，
  全部提名走既有候选通道（kind=fact，origin=epilogue），人工
  accept 是唯一生效动作；未 accept 的候选不入任何账。
- 可核对：scan 把会话记录确定性切段（段 ID + 段哈希 + 发言人），
  提名必须引用真实存在的段；apply 时重算会话文件哈希与 scan
  对账，漂移即整批拒绝（段引用不可信，不许半收编）。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import candidates as cand_mod
from . import project as project_mod, schema
from .util import component_hash, load_structured, sha256_file, \
    sha256_text

#: epilogue 六类固定清单（成文，不许临场增减）。
EPILOGUE_CATEGORIES = {
    "decision": "决策",
    "experiment_conclusion": "实验结论",
    "dead_end": "死胡同与折返",
    "claim_change": "主张变更",
    "heuristic": "启发式",
    "pivot": "方向转向",
}

#: 类别 → 事实类型默认映射（提名可逐条覆盖 fact_type）。
FACT_TYPE_BY_CATEGORY = {
    "decision": "decision",
    "experiment_conclusion": "conclusion",
    "dead_end": "failure_record",
    "claim_change": "conclusion",
    "heuristic": "lesson",
    "pivot": "direction",
}

SOURCE_TAGS = ("user", "ai")

_SPEAKER_RE = re.compile(
    r"^(user|assistant|human|ai|Muse|system|用户|助手|模型)\s*[:：]",
    re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,3}\s")
_SPEAKER_NORM = {
    "user": "user", "human": "user", "用户": "user",
    "assistant": "ai", "ai": "ai", "Muse": "ai", "模型": "ai",
    "助手": "ai", "system": "system",
}


class EpilogueError(Exception):
    """epilogue 操作被拒。gaps 为逐条人读原因。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 切段

def segment_transcript(text: str) -> list:
    """确定性切段：发言人标记行与一至三级标题行开启新段。

    返回 [{seg_id, speaker, text, sha256, excerpt}]；speaker 归一为
    user / ai / system / unknown。切段只认行首标记，不做语义判断
    ——抽取哪几段、归哪一类是接入模型按六类清单的工作，段是锚点。
    """
    segments: list = []
    cur_speaker, cur_lines = "unknown", []

    def flush():
        body = "\n".join(cur_lines).strip()
        if body:
            segments.append({
                "seg_id": f"seg-{len(segments) + 1:03d}",
                "speaker": cur_speaker,
                "text": body,
                "sha256": sha256_text(body),
                "excerpt": body.splitlines()[0][:80],
            })

    for line in (text or "").splitlines():
        m = _SPEAKER_RE.match(line)
        if m or _HEADING_RE.match(line):
            flush()
            cur_lines = [line]
            cur_speaker = _SPEAKER_NORM.get(m.group(1).lower(),
                                            "unknown") if m else "unknown"
        else:
            cur_lines.append(line)
    flush()
    return segments


def scan_transcript(transcript_path) -> dict:
    """扫描会话记录产切段清单（纯读，无副作用，不写记忆包）。"""
    path = Path(transcript_path)
    if not path.exists():
        raise EpilogueError([f"会话记录不存在：{path}"])
    text = path.read_text(encoding="utf-8")
    return {
        "kind": "light-memory/epilogue-scan",
        "version": "1.0",
        "transcript": {
            "path": str(path),
            "sha256": sha256_file(path),
        },
        "segments": segment_transcript(text),
    }


# ---------------------------------------------------------------- 提名

def _item_gaps(item: dict, seg_ids: set, idx: int) -> list:
    gaps = []
    tag = f"第 {idx + 1} 条"
    if item.get("category") not in EPILOGUE_CATEGORIES:
        gaps.append(f"{tag}：类别不在六类清单内：{item.get('category')}")
    if item.get("source_tag") not in SOURCE_TAGS:
        gaps.append(f"{tag}：来源标签须为 user 或 ai："
                    f"{item.get('source_tag')}")
    refs = item.get("segment_refs") or []
    if not refs:
        gaps.append(f"{tag}：缺 segment_refs（提名必须锚定会话段）")
    for ref in refs:
        if ref not in seg_ids:
            gaps.append(f"{tag}：段引用不存在：{ref}")
    if not (item.get("statement") or "").strip():
        gaps.append(f"{tag}：缺 statement 草稿")
    if not (item.get("object_id") or "").strip():
        gaps.append(f"{tag}：缺 object_id（事实草稿必填，见判定落账口径）")
    return gaps


def apply_epilogue(root, scan_path, nominations_path, *,
                   nominator: str = "epilogue") -> dict:
    """按 scan 清单校验提名文件，逐条走候选通道产候选。

    提名文件形态：{items: [{category, source_tag, segment_refs,
    statement, object_id, fact_type?, valid_at?, target_fact_id?,
    rationale?}]}（裸列表亦可）。逐项校验、逐项回报：不合格条目
    点名跳过，合格条目照常提名；会话文件哈希与 scan 不符则整批
    拒绝（段引用整体不可信）。只产候选，绝不直接入账。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise EpilogueError([f"记忆项目不存在或缺登记头：{root}"])
    scan = load_structured(scan_path)
    if not isinstance(scan, dict) or \
            scan.get("kind") != "light-memory/epilogue-scan":
        raise EpilogueError([f"scan 清单形态不对：{scan_path}"])
    tpath = Path((scan.get("transcript") or {}).get("path") or "")
    if not tpath.exists():
        raise EpilogueError([f"会话记录已不存在：{tpath}（段引用无从对账）"])
    if sha256_file(tpath) != scan["transcript"].get("sha256"):
        raise EpilogueError(
            ["会话记录在 scan 之后已变更（哈希不符）：段引用整体"
             "不可信，整批拒绝；请重新 scan 后再提名"])
    data = load_structured(nominations_path)
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise EpilogueError([f"提名文件无 items：{nominations_path}"])
    seg_ids = {s.get("seg_id") for s in scan.get("segments") or []}
    version = (scan["transcript"].get("sha256") or "")[:16]

    created, gaps = [], []
    for i, item in enumerate(items):
        item_gaps = _item_gaps(item, seg_ids, i)
        if item_gaps:
            gaps += item_gaps
            continue
        category = item["category"]
        verdict = "store"
        if category == "claim_change" and item.get("target_fact_id"):
            verdict = "supersede"
        fact = {
            "statement": item["statement"].strip(),
            "fact_type": item.get("fact_type")
            or FACT_TYPE_BY_CATEGORY[category],
            "object_id": item["object_id"].strip(),
            "valid_at": item.get("valid_at"),
        }
        nomination = {
            "verdict": verdict,
            "nominator": nominator,
            "rationale": item.get("rationale")
            or f"epilogue 提名（{EPILOGUE_CATEGORIES[category]}）",
            "provenance": schema.make_provenance(
                "conversation", tpath.name,
                (item.get("segment_refs") or [None])[0], version),
            "fact": fact,
        }
        if verdict == "supersede":
            nomination["target_fact_id"] = item["target_fact_id"]
        content = {
            "nomination": nomination,
            "epilogue": {
                "category": category,
                "source_tag": item["source_tag"],
                "segment_refs": list(item.get("segment_refs") or []),
                "transcript_sha256": scan["transcript"].get("sha256"),
            },
        }
        row = cand_mod.propose(
            root, "fact", content, nominator=nominator,
            basis=list(item.get("segment_refs") or []),
            rationale=nomination["rationale"], origin="epilogue")
        created.append(row["candidate_id"])
    return {"created": created, "gaps": gaps,
            "transcript": str(tpath),
            "digest": component_hash({"scan": scan.get("transcript"),
                                      "created": created})}

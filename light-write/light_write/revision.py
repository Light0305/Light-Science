"""W7 返修子包（Phase 2）：审稿意见登记 → 逐条回复 → 双向对账 → 回复信绑定。

文件群（稿件包 revision/ 目录）：
  comments.yaml   审稿意见逐条登记 {comment_id, reviewer, text, category,
                  claim_ids[], section_ids[], round}
  responses.yaml  逐条回复 {comment_id, decision, rationale,
                  change_anchors[{file, marker}]} + 绑定头
                  {bound_manuscript_hash, bound_at}
  response_letter.md  回复信（bind 渲染的生成物，头部带绑定哈希）

双向对账（revision check）：
  正向——意见全覆盖：每条意见恰有一条回复；回复的每处改动锚点
  （[rev:<comment_id>] 标记）真实落在所指节文件中；
  反向——改动全回指：正文每个 [rev:X] 标记都被 X 的回复锚点覆盖，
  不许有无主改动，也不许回复声称改了而正文无标记。
resubmit 绑定：回复信绑当前稿件哈希；稿改而信未更新 → STALE（check 报出）。
分类与决策词表在 schema（major/minor/editorial；accept/partial/reject）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import load_package, manuscript_hash, section_files
from .util import dump_yaml, load_structured, today, utcnow

COMMENTS_NAME = "comments.yaml"
RESPONSES_NAME = "responses.yaml"
LETTER_NAME = "response_letter.md"
REV_MARK_RE_STR = r"\[rev:([A-Za-z0-9_-]+)\]"


class RevisionError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _dir(root) -> Path:
    d = Path(root) / "revision"
    d.mkdir(exist_ok=True)
    return d


def load_comments(root) -> dict:
    path = _dir(root) / COMMENTS_NAME
    if not path.exists():
        return {"comments": []}
    return load_structured(path) or {"comments": []}


def load_responses(root) -> dict:
    path = _dir(root) / RESPONSES_NAME
    if not path.exists():
        return {"bound_manuscript_hash": None, "bound_at": None,
                "responses": []}
    return load_structured(path) or {"responses": []}


def save_comments(root, doc) -> None:
    dump_yaml(_dir(root) / COMMENTS_NAME, doc)


def save_responses(root, doc) -> None:
    dump_yaml(_dir(root) / RESPONSES_NAME, doc)


def _next_id(existing) -> str:
    nums = []
    for cid in existing:
        if isinstance(cid, str) and cid.startswith("RC"):
            try:
                nums.append(int(cid[2:]))
            except ValueError:
                pass
    return f"RC{(max(nums) + 1) if nums else 1:03d}"


def add_comment(root, reviewer, text, category="major", claim_ids=None,
                section_ids=None, round_no=1) -> dict:
    root = Path(root)
    pkg = load_package(root)
    if pkg["manuscript"] is None:
        raise RevisionError(["稿件包不存在（先 init）"])
    if category not in schema.REVISION_CATEGORIES:
        raise RevisionError([
            f"意见分类 {category!r} 不在 {schema.REVISION_CATEGORIES}"])
    if not text:
        raise RevisionError(["意见原文不可为空（逐字登记，不许转述替代）"])
    doc = load_comments(root)
    cid = _next_id([c.get("comment_id") for c in doc["comments"]])
    entry = {"comment_id": cid, "reviewer": reviewer, "text": text,
             "category": category, "claim_ids": claim_ids or [],
             "section_ids": section_ids or [], "round": round_no,
             "registered_at": today()}
    doc["comments"].append(entry)
    save_comments(root, doc)
    return entry


def add_response(root, comment_id, decision, rationale, change_anchors=None) -> dict:
    root = Path(root)
    if decision not in schema.REVISION_DECISIONS:
        raise RevisionError([
            f"回复决策 {decision!r} 不在 {schema.REVISION_DECISIONS}"])
    if not rationale:
        raise RevisionError(["回复必须落理由（rationale）：accept/partial/"
                             "reject 都要说清依据，不许空回复"])
    comments = {c.get("comment_id"): c
                for c in load_comments(root)["comments"]}
    if comment_id not in comments:
        raise RevisionError([f"意见 {comment_id} 未登记：回复不许无的放矢"])
    anchors = change_anchors or []
    if decision in ("accept", "partial") and not anchors:
        raise RevisionError([
            f"{decision} 决策须登记改动锚点 change_anchors"
            "（{file, marker}：正文中 [rev:<marker>] 标记的位置）"])
    doc = load_responses(root)
    if any(r.get("comment_id") == comment_id for r in doc["responses"]):
        raise RevisionError([f"意见 {comment_id} 已有回复：改回复请直接编辑 "
                             "responses.yaml 并重新 bind（不许双回复）"])
    entry = {"comment_id": comment_id, "decision": decision,
             "rationale": rationale, "change_anchors": anchors,
             "responded_at": today()}
    doc["responses"].append(entry)
    save_responses(root, doc)
    return entry


def check_revision(root) -> dict:
    """双向对账 + 绑定新鲜度。返回 {ok, findings, coverage, stale}。"""
    import re as _re

    root = Path(root)
    findings = []

    def err(code, msg):
        findings.append({"level": "error", "code": code, "message": msg})

    comments = load_comments(root)["comments"]
    responses_doc = load_responses(root)
    responses = responses_doc.get("responses") or []
    by_comment = {}
    for r in responses:
        cid = r.get("comment_id")
        if cid in by_comment:
            err("revision.dup_response", f"意见 {cid} 有多条回复")
        by_comment[cid] = r
    comment_ids = {c.get("comment_id") for c in comments}
    for c in comments:
        if c.get("comment_id") not in by_comment:
            err("revision.unanswered",
                f"意见 {c.get('comment_id')} 无回复：意见须全覆盖")
    files = section_files(root)
    marker_re = _re.compile(REV_MARK_RE_STR)
    markers_in_text = {}  # marker -> set(files)
    for fname, text in files.items():
        for m in marker_re.finditer(text):
            markers_in_text.setdefault(m.group(1), set()).add(fname)
    covered_markers = set()
    for r in responses:
        cid = r.get("comment_id")
        if cid not in comment_ids:
            err("revision.orphan_response", f"回复指向未登记意见 {cid}")
        if r.get("decision") not in schema.REVISION_DECISIONS:
            err("revision.decision_vocab",
                f"回复 {cid} 决策 {r.get('decision')!r} 不在词表")
        if not r.get("rationale"):
            err("revision.no_rationale", f"回复 {cid} 无理由落字")
        for anchor in r.get("change_anchors") or []:
            f, marker = anchor.get("file"), anchor.get("marker")
            covered_markers.add((marker, f))
            if f not in files:
                err("revision.anchor_file_missing",
                    f"回复 {cid} 改动锚点文件 sections/{f} 不存在")
            elif marker not in markers_in_text or \
                    f not in markers_in_text.get(marker, set()):
                err("revision.anchor_not_in_text",
                    f"回复 {cid} 声称在 {f} 有改动标记 [rev:{marker}]，"
                    "正文无此标记：声称改动须有实位")
    for marker, fnames in markers_in_text.items():
        for f in fnames:
            if (marker, f) not in covered_markers:
                err("revision.unclaimed_change",
                    f"正文 {f} 的改动标记 [rev:{marker}] 未被任何回复锚点"
                    "回指：改动须全回指（双向对账）")
    bound = responses_doc.get("bound_manuscript_hash")
    stale = None
    if bound is not None:
        stale = bound != manuscript_hash(root)
        if stale:
            err("revision.letter_stale",
                "回复信绑定的稿件哈希已漂移：稿改信未更新（STALE），"
                "须更新回复后重新 bind")
    return {"ok": not findings, "findings": findings,
            "coverage": {"comments": len(comments),
                         "responses": len(responses)},
            "stale": stale}


def bind_revision(root) -> dict:
    """resubmit 检查 + 生成回复信：对账全过才许绑当前稿件哈希。"""
    root = Path(root)
    result = check_revision(root)
    errors = [f for f in result["findings"]
              if f["code"] != "revision.letter_stale"]
    if errors:
        raise RevisionError([f["message"] for f in errors])
    comments = {c.get("comment_id"): c
                for c in load_comments(root)["comments"]}
    doc = load_responses(root)
    current = manuscript_hash(root)
    lines = ["# 回复信（Response to Reviewers）", "",
             f"- 绑定稿件哈希：`{current}`",
             f"- 绑定时间：{utcnow()}",
             "- 说明：稿件在此哈希之后有任何改动，本信即 STALE，须更新后重绑。",
             ""]
    for r in doc["responses"]:
        c = comments.get(r["comment_id"]) or {}
        lines += [f"## {r['comment_id']}（{c.get('category', '')}，"
                  f"{c.get('reviewer', '')}）", "",
                  f"> {c.get('text', '')}", "",
                  f"**回复（{r['decision']}）**：{r['rationale']}", ""]
        if r.get("change_anchors"):
            lines.append("改动位置：" + "；".join(
                f"sections/{a.get('file')} [rev:{a.get('marker')}]"
                for a in r["change_anchors"]))
            lines.append("")
    letter_path = _dir(root) / LETTER_NAME
    letter_path.write_text("\n".join(lines), encoding="utf-8")
    doc["bound_manuscript_hash"] = current
    doc["bound_at"] = today()
    save_responses(root, doc)
    return {"bound_manuscript_hash": current, "letter": str(letter_path),
            "responses": len(doc["responses"])}

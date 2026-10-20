"""渠道层（Q3）与检索词最小披露构造（Q9）。

渠道是可替换层：登记表为一等工件，每条带可审计性/可复现性与
披露考量字段。自动化渠道默认关；开启须登记 light-crawler 预检
引用（crawler_precheck_ref）——本包只点名校验该引用在册，不
代行 crawler 的预检门（LD-02 分工）。

检索词最小披露：检索式只能由 IPC/LOC 分类号 + 手段短语构造；
整句技术方案、案件标题、摘要长句一律拒绝入查询（防检索词本身
泄露未公开技术方案）。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import PatentError, case_path, load_case
from .util import dump_yaml, load_structured

MAX_MEANS_PHRASE_CHARS = 20      # 手段短语单条长度上限（短语而非句子）
MAX_QUERY_TOKENS = 6             # 单条检索式的词元上限
_SENTENCE_MARKS = "。；！？.!?;"


def channel_registry() -> list:
    return [dict(c) for c in schema.CHANNELS]


def load_channel_state(root) -> dict:
    data = load_structured(case_path(root, "pool"))  # 渠道启用态随案件 novelty 目录落盘
    state_path = Path(root) / "novelty" / "channels.yaml"
    state = load_structured(state_path) or {}
    return state.get("channels") or {}


def enable_channel(root, channel_id: str, payload: dict) -> dict:
    """启用渠道。自动化渠道无 crawler 预检引用不许开；厂商/API
    渠道须登记启用考量（disclosure_acknowledged）。"""
    root = Path(root)
    load_case(root)
    registry = {c["channel_id"]: c for c in schema.CHANNELS}
    ch = registry.get(channel_id)
    if ch is None:
        raise PatentError([f"渠道 {channel_id!r} 不在登记表内（先登记后使用）"])
    gaps = []
    if ch["mode"] == "automation" and not payload.get("crawler_precheck_ref"):
        gaps.append(
            f"渠道 {channel_id} 为自动化渠道（默认关）：开启须登记 "
            "light-crawler 预检引用 crawler_precheck_ref（拍板 Q3/S4），"
            "本包不代行预检门")
    if ch["kind"] in ("vendor_api", "official_api") \
            and not payload.get("disclosure_acknowledged"):
        gaps.append(
            f"渠道 {channel_id} 为 API 渠道：启用前须登记披露考量确认"
            "（检索词将出境至该渠道，Q9）")
    if gaps:
        raise PatentError(gaps)
    state_path = Path(root) / "novelty" / "channels.yaml"
    state = load_structured(state_path) or {"channels": {}}
    state.setdefault("channels", {})[channel_id] = {
        "enabled": True,
        "mode": ch["mode"],
        "crawler_precheck_ref": payload.get("crawler_precheck_ref"),
        "enabled_by": payload.get("enabled_by") or "待填写/需确认",
        "auditability": ch["auditability"],
        "reproducibility": ch["reproducibility"],
    }
    dump_yaml(state_path, state)
    return state["channels"][channel_id]


def build_query(case: dict, *, ipc_codes=None, means_phrases=None) -> str:
    """最小披露检索式构造：只收分类号 + 手段短语。拒绝整句、
    标题与超长短语（Q9 硬规则机械面）。"""
    gaps = []
    phrases = means_phrases or []
    codes = ipc_codes or []
    title = (case.get("title") or "").strip()
    for ph in phrases:
        if len(ph) > MAX_MEANS_PHRASE_CHARS:
            gaps.append(f"手段短语超长（{len(ph)} 字，上限 "
                        f"{MAX_MEANS_PHRASE_CHARS}）：{ph!r}——检索式只许"
                        "短语不许整句技术方案（Q9）")
        if any(m in ph for m in _SENTENCE_MARKS):
            gaps.append(f"手段短语含句读符号，疑似整句：{ph!r}")
        if title and (ph == title or title in ph):
            gaps.append("手段短语与案件标题相同/包含标题：标题不得入查询（Q9）")
    for code in codes:
        if not re.fullmatch(r"[A-HY]\d{2}[A-Z]?( ?\d+/\d+)?", code.strip()):
            gaps.append(f"分类号形态可疑：{code!r}（应为 IPC/LOC 分类号）")
    if not phrases and not codes:
        gaps.append("检索式为空：至少给分类号或手段短语其一")
    if len(phrases) + len(codes) > MAX_QUERY_TOKENS:
        gaps.append(f"检索式词元超限（{len(phrases) + len(codes)}，"
                    f"上限 {MAX_QUERY_TOKENS}）：拆成多条检索式")
    if gaps:
        raise PatentError(gaps)
    parts = [f"IPC:{c.strip()}" for c in codes] + phrases
    return " AND ".join(parts)

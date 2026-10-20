"""案件登记头、事实单源、确认回执与工具使用留痕。

纪律：
- copyright.yaml 是案件登记头，顶层 status 是唯一状态读数（leader 汇总
  消费）；facts.yaml 是登记事实唯一源（HC-2），材料侧一律派生不另存。
- 确认 = 回执行（confirmations.jsonl，只增不改）：绑定被确认对象的
  内容哈希；内容一变，旧回执自动失效（HC-6），不许「确认过」含糊带过。
- tool_use.jsonl 只增不改：起草、确认、导入、渲染每个动作留一行
  （Q2 折中口径的留痕要求，也是 declaration 门的核对底账）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import (append_jsonl, dump_yaml, load_structured, read_jsonl,
                   sha256_text, today)


class CaseError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


CASE_FILE = "copyright.yaml"
FACTS_FILE = "facts.yaml"
CONFIRM_FILE = "confirmations.jsonl"
TOOL_USE_FILE = "tool_use.jsonl"


def case_path(root) -> Path:
    return Path(root) / CASE_FILE


def load_case(root) -> dict:
    p = case_path(root)
    if not p.exists():
        raise CaseError(["案件不存在（先 init）"])
    return load_structured(p) or {}


def save_case(root, case: dict) -> None:
    dump_yaml(case_path(root), case)


def status_of(root) -> str:
    return load_case(root).get("status", "")


def set_status(root, case: dict, new_status: str) -> dict:
    """状态推进：校验合法前置，越级点名拒绝。"""
    cur = case.get("status")
    allowed = schema.REQUIRES.get(new_status, ())
    if cur not in allowed:
        raise CaseError([
            f"状态不许从 {cur} 直接到 {new_status}"
            f"（合法前置：{'/'.join(allowed) or '无'}）"])
    case["status"] = new_status
    case["updated_at"] = today()
    save_case(root, case)
    return case


def init_case(root, title: str = "") -> dict:
    root = Path(root)
    if case_path(root).exists():
        raise CaseError(["案件已存在，拒绝覆盖"])
    root.mkdir(parents=True, exist_ok=True)
    case = {
        "kind": "light-software-copyright/case",
        "version": 1,
        "title": title or root.name,
        "status": "draft",
        "created_at": today(),
        "updated_at": today(),
        "jurisdiction": "CN（中国版权保护中心）",
        "rules_snapshot_date": schema.RULES_SNAPSHOT["snapshot_date"],
        "correction": None,
    }
    save_case(root, case)
    log_tool_use(root, "tool", "init", "case", "建案")
    return case


# ---------------------------------------------------------------- 事实单源
def facts_path(root) -> Path:
    return Path(root) / FACTS_FILE


def load_facts(root) -> dict:
    p = facts_path(root)
    if not p.exists():
        return {}
    return load_structured(p) or {}


def save_facts(root, facts: dict) -> None:
    dump_yaml(facts_path(root), facts)


def facts_fingerprint(facts: dict) -> str:
    import json
    return sha256_text(json.dumps(facts, ensure_ascii=False, sort_keys=True))


def validate_facts(facts: dict) -> list:
    """必填与词表校验：缺项逐项点名，不猜（HC-6）。"""
    gaps = []
    for section, key, label in schema.FACT_REQUIRED:
        val = (facts.get(section) or {}).get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            gaps.append(f"登记事实缺 {label}（{section}.{key}）")
    sw = facts.get("software") or {}
    if sw.get("kind") and sw["kind"] not in schema.SOFTWARE_KINDS:
        gaps.append(f"software.kind={sw['kind']!r} 不在词表 "
                    f"{list(schema.SOFTWARE_KINDS)}")
    dev = facts.get("development") or {}
    if dev.get("mode") and dev["mode"] not in schema.DEV_MODES:
        gaps.append(f"development.mode={dev['mode']!r} 不在词表")
    pub = facts.get("publication") or {}
    if pub.get("status") and pub["status"] not in schema.PUBLICATION_STATES:
        gaps.append(f"publication.status={pub['status']!r} 不在词表")
    if pub.get("status") == "published" and not pub.get("first_date"):
        gaps.append("发表状态为 published 但缺首次发表日期（日期逻辑须自洽）")
    return gaps


def facts_warnings(facts: dict) -> list:
    """B 级动态口径只警告不拦（HC-7）。"""
    warns = []
    main_fn = ((facts.get("functions") or {}).get("main_function") or "")
    if main_fn:
        lo, hi = schema.MAIN_FUNCTION_LEN_RANGE
        n = len(main_fn)
        if n < lo or n > hi:
            warns.append(
                f"主要功能 {n} 字：B 级信号区间为 {lo}-{hi} 字"
                "（行业转述，非官方原文），递交当日以当期表单复核，本步不拦")
    return warns


# ---------------------------------------------------------------- 确认与留痕
def log_tool_use(root, actor: str, action: str, target: str,
                 detail: str = "") -> None:
    append_jsonl(Path(root) / TOOL_USE_FILE, {
        "ts": today(), "actor": actor, "action": action,
        "target": target, "detail": detail})


def tool_use_rows(root) -> list:
    return read_jsonl(Path(root) / TOOL_USE_FILE)


def record_confirmation(root, kind: str, target: str, content_hash: str,
                        note: str = "") -> dict:
    row = {"ts": today(), "actor": "user", "kind": kind, "target": target,
           "content_hash": content_hash, "note": note}
    append_jsonl(Path(root) / CONFIRM_FILE, row)
    log_tool_use(root, "user", "confirm", f"{kind}:{target}",
                 f"确认回执 哈希 {content_hash[:12]}")
    return row


def confirmation_valid(root, kind: str, target: str,
                       current_hash: str) -> bool:
    """回执有效 = 存在同 kind/target 且哈希与当前内容一致的行（HC-6）。"""
    for row in read_jsonl(Path(root) / CONFIRM_FILE):
        if (row.get("kind") == kind and row.get("target") == target
                and row.get("content_hash") == current_hash):
            return True
    return False


def confirmations(root) -> list:
    return read_jsonl(Path(root) / CONFIRM_FILE)

"""工作区校验：登记自洽 + provenance 哈希重算 + WARC 记录逐条复算 + 账本可解析。

校验只读、逐项点名。与姊妹包口径一致：读不出的东西报点名错误，
不猜、不修、不回写。
"""

from __future__ import annotations

from pathlib import Path

from . import precheck as precheck_mod
from . import project, schema, storage
from .util import read_jsonl


def validate_workspace(root) -> list:
    problems = []
    root = Path(root)
    try:
        header = project.load_header(root)
    except project.WorkspaceError as e:
        return e.problems
    if not isinstance(header.get("lock"), dict):
        problems.append("登记头缺 lock 段（项目级合规档位锁）")

    for reg in project.list_targets(root):
        for p in schema.validate_target(reg):
            problems.append(f"目标 {reg.get('target_id')}：{p}")
        cur = precheck_mod.current_precheck(root, reg["target_id"])
        if cur["status"] == "effective" and cur["record"]:
            rate = (cur["record"].get("checks") or {}).get("rate") or {}
            if rate.get("concurrency") not in (None, schema.REQUIRED_CONCURRENCY):
                problems.append(
                    f"目标 {reg['target_id']}：生效预检的并发不是 "
                    f"{schema.REQUIRED_CONCURRENCY}（S6 定版被动过手脚？）")

    problems += storage.verify_store(root)
    problems += storage.verify_warc_refs(root)

    for name in ("events.jsonl", "provenance.jsonl", "seen.jsonl",
                 "fingerprints.jsonl"):
        path = root / name
        if path.exists():
            rows = read_jsonl(path)
            raw_lines = [ln for ln in path.read_text(
                encoding="utf-8").splitlines() if ln.strip()]
            if len(rows) != len(raw_lines):
                problems.append(f"{name} 有 {len(raw_lines) - len(rows)} 行不可解析")
    return problems

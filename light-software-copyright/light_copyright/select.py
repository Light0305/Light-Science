"""SC3 源码选择：候选清单 + 排除留痕，确认后才许渲染（HC-5/HC-6）。

候选只列证据不默认全选：逐文件给出体量与标记（第三方标识、敏感形态、
测试/夹具路径、构建物后缀），命中排除项逐条落 selection.json 的
exclusions 并写明理由。模型可建议、用户须确认（确认绑选择内容哈希）；
排除项可由用户逐个申诉改判（appeal），改判同样留痕，不许静默放行。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .case import CaseError, log_tool_use
from .snapshot import load_snapshot
from .util import dump_json, load_structured

SELECTION_FILE = "selection.json"


def _read_text(source_dir: Path, rel: str) -> str:
    try:
        return (source_dir / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def scan_candidates(root) -> dict:
    """对冻结快照逐文件体检，产候选（含建议）与排除两账。"""
    root = Path(root)
    snap = load_snapshot(root)
    source_dir = Path(snap["source_dir"])
    included, exclusions = [], []
    for meta in snap["files"]:
        rel = meta["path"]
        text = _read_text(source_dir, rel)
        reasons = []
        if rel.lower().endswith(schema.EXCLUDED_FILE_SUFFIXES):
            reasons.append("构建物/二进制类后缀")
        parts = [p.lower() for p in Path(rel).parts]
        dir_hints = ("fixture", "fixtures", "__tests__", "mock", "mocks",
                     "tests", "test")
        if any(part in dir_hints or h in part
               for part in parts[:-1] for h in dir_hints) \
                or parts[-1].startswith("test_") or parts[-1].endswith(
                    ("_test.py", ".test.js", ".spec.ts")):
            reasons.append("测试/夹具路径（登记材料只收正式源程序）")
        for marker in schema.THIRD_PARTY_MARKERS:
            if marker in text:
                # 只有出现在文件头 40 行内才算署名标识，避免正文字符串误杀
                head = "\n".join(text.splitlines()[:40])
                if marker in head:
                    reasons.append(f"文件头含版权/许可标识：{marker}"
                                   "（归属须核：第三方整份排除，自有走申诉）")
                    break
        for label, pat in schema.SECRET_PATTERNS:
            if re.search(pat, text):
                reasons.append(f"命中敏感形态：{label}")
                break
        entry = {"path": rel, "nonempty_lines": meta["nonempty_lines"],
                 "total_lines": meta["total_lines"]}
        if reasons:
            entry["reasons"] = reasons
            exclusions.append(entry)
        else:
            included.append(entry)
    sel = {
        "kind": "light-software-copyright/selection",
        "snapshot_files": snap["file_count"],
        "included": included,
        "exclusions": exclusions,
        "appealed": [],
    }
    dump_json(root / SELECTION_FILE, sel)
    log_tool_use(root, "tool", "select-scan", "selection",
                 f"入选 {len(included)} / 排除 {len(exclusions)}")
    return sel


def load_selection(root) -> dict:
    p = Path(root) / SELECTION_FILE
    if not p.exists():
        raise CaseError(["尚无选材清单（先 select）"])
    return load_structured(p)


def appeal(root, rel_path: str, reason: str) -> dict:
    """排除申诉改判：把排除项移入入选，留痕（谁、何时、理由）。"""
    root = Path(root)
    sel = load_selection(root)
    target = next((e for e in sel["exclusions"] if e["path"] == rel_path),
                  None)
    if target is None:
        raise CaseError([f"{rel_path} 不在排除清单内，无可申诉"])
    if not (reason or "").strip():
        raise CaseError(["申诉必须给理由（归属自证），不许无理由放行"])
    sel["exclusions"] = [e for e in sel["exclusions"]
                          if e["path"] != rel_path]
    sel["included"].append({"path": rel_path,
                            "nonempty_lines": target["nonempty_lines"],
                            "total_lines": target["total_lines"]})
    sel["included"].sort(key=lambda e: e["path"])
    sel.setdefault("appealed", []).append(
        {"path": rel_path, "reason": reason,
         "original_reasons": target.get("reasons", [])})
    dump_json(root / SELECTION_FILE, sel)
    log_tool_use(root, "user", "appeal", f"selection:{rel_path}", reason)
    return sel


def selection_fingerprint(sel: dict) -> str:
    import json
    from .util import sha256_text
    payload = {
        "included": sorted(e["path"] for e in sel["included"]),
        "excluded": sorted(e["path"] for e in sel["exclusions"]),
        "appealed": sorted(a["path"] for a in sel.get("appealed", [])),
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))

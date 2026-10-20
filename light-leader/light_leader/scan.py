"""status：只读扫描项目目录，逐阶段报告各包登记文件的状态。

扫描口径（与 SKILL.md §7 同源）：
- 在项目树内按登记头文件名定位各包产物（深度上限内递归，跳过隐藏
  目录与 __pycache__）；状态一律读登记头顶层 status 字段，硬门标记
  只按 layout.GATE_FIELD_FAMILIES 登记过的字段族提取（review 族按
  字段名深搜、blocked_gate 族读顶层统一字段、return_block 族读
  design 的打回/阻塞记录）。读不到、解析失败、字段缺失都逐项落字，
  不猜；状态值另按 statusmap 落规范态标注，映射外的值标注为 None。
- literature 无状态机：读 文献索引.csv 的逐篇 status 列计数，并数
  同目录 证据表.jsonl 行数。
- memory：读 memory.yaml 是否存在 + 四账行数 + registry-view.json
  是否已导出。
- 扩展位（LD-02）：patent 读 kind=light-patent/case 的 case.yaml
  （含 blocked 门字段与 ledger.yaml 期限清单）；software-copyright
  读 copyright.yaml（含 correcting 时的补正期限）；crawler 读
  data-sources 的 crawler.yaml 工作区头 + 逐目标登记/运行态 +
  prechecks 末行预检状态。扩展位不入流水线扫描，单独成组返回。
- 本模块只读，绝不写任何文件。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .layout import EXTENSIONS, GATE_FIELDS, PIPELINE, STAGES
from .statusmap import canonical
from .util import count_jsonl, deep_find, load_yaml

MAX_DEPTH = 7
_SKIP_DIRS = {"__pycache__", ".git", ".index", "node_modules"}


def _walk_files(root: Path):
    """递归产出 (相对深度, 路径)；跳过隐藏目录与缓存目录。"""
    root = Path(root)
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        if depth > MAX_DEPTH:
            continue
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name.startswith(".") or e.name in _SKIP_DIRS:
                    continue
                stack.append((e, depth + 1))
            elif e.is_file():
                yield e


def find_files(root, filename: str) -> list:
    return [p for p in _walk_files(root) if p.name == filename]


def _gate_markers(stage: str, data: dict) -> list:
    """review_unavailable 族：按 GATE_FIELDS 深搜硬门标记。

    命中 REVIEW_UNAVAILABLE 才登记；其余值（如已落收据的 review_id）
    不触发。
    """
    hits = []
    for field in GATE_FIELDS.get(stage, ()):
        val = deep_find(data, field)
        if isinstance(val, str) and "REVIEW_UNAVAILABLE" in val:
            hits.append({"field": field, "value": val,
                         "family": "review_unavailable"})
    return hits


def _gate_blocks(stage: str, data: dict, item: dict) -> list:
    """blocked_gate / return_block 两族的门记录提取（LD-04）。

    形态不合的 blocked_gate 不点名：形态问题落 item["gate_notes"]
    点名，不猜门义。return_block 族只认 design（族登记的 stages）。
    字段名变体（LD-02 集成步在字段族登记）：patent 的案件头以顶层
    blocked 字段承载同形映射，stage=patent 时按 blocked 读。
    """
    blocks = []
    field = "blocked" if stage == "patent" else "blocked_gate"
    bg = data.get(field)
    if bg is not None:
        gid = bg.get("gate_id") if isinstance(bg, dict) else None
        if isinstance(gid, str) and gid.strip():
            blocks.append({
                "family": "blocked_gate",
                "gate_id": gid.strip(),
                "detail": bg.get("detail"),
                "fix_pointer": bg.get("fix_pointer"),
            })
        else:
            item.setdefault("gate_notes", []).append(
                f"{field} 字段存在但形态不合（须为含 gate_id 的映射），"
                "未据此点名")
    if stage == "design":
        status = data.get("status")
        if status == "returned" and isinstance(data.get("return_record"),
                                                dict):
            open_items = [
                it for it in data["return_record"].get("returned_items")
                or [] if isinstance(it, dict) and not it.get("resolved")]
            if open_items:
                blocks.append({"family": "return_block",
                               "kind": "returned",
                               "open_items": open_items})
        if status == "blocked" and isinstance(data.get("block_record"),
                                               dict):
            rec = data["block_record"]
            blocks.append({"family": "return_block", "kind": "blocked",
                           "reason": rec.get("reason"),
                           "unblock_condition": rec.get("unblock_condition")})
    return blocks


def _scan_yaml_stage(root, stage: str) -> dict:
    spec = STAGES[stage]
    headers = find_files(root, spec["header"])
    items = []
    for h in headers:
        data = load_yaml(h)
        item = {"path": str(h.relative_to(root)), "status": None}
        if data is None:
            item["error"] = "登记头存在但解析失败或顶层非映射"
        else:
            item["status"] = data.get("status")
            if item["status"] is None:
                item["error"] = "登记头缺顶层 status 字段"
            item["canonical"] = canonical(stage, item["status"])
            gates = _gate_markers(stage, data)
            if gates:
                item["gates"] = gates
            blocks = _gate_blocks(stage, data, item)
            if blocks:
                item["gate_blocks"] = blocks
            if stage == "analysis":
                blocked = data.get("blocked")
                if isinstance(blocked, dict) and blocked.get("reason"):
                    item["blocked_reason"] = blocked["reason"]
        items.append(item)
    return {"stage": stage, "skill": spec["skill"], "found": bool(items),
            "items": items}


def _scan_literature(root) -> dict:
    indexes = find_files(root, "文献索引.csv")
    items = []
    for idx in indexes:
        item = {"path": str(idx.relative_to(root)), "papers": 0,
                "status_counts": {}, "evidence_rows": None}
        try:
            with idx.open(encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    item["papers"] += 1
                    st = (row.get("status") or "").strip() or "(空)"
                    item["status_counts"][st] = \
                        item["status_counts"].get(st, 0) + 1
        except Exception as exc:  # 索引不可读：落字不猜
            item["error"] = f"文献索引读取失败：{exc}"
        ev = idx.parent / "证据表.jsonl"
        if ev.is_file():
            item["evidence_rows"] = count_jsonl(ev)
        items.append(item)
    return {"stage": "literature", "skill": STAGES["literature"]["skill"],
            "found": bool(items), "items": items}


def _scan_memory(root) -> dict:
    heads = find_files(root, "memory.yaml")
    items = []
    for h in heads:
        base = h.parent
        item = {"path": str(h.relative_to(root)),
                "counts": {name: count_jsonl(base / f"{name}.jsonl")
                           for name in ("objects", "events", "facts",
                                        "relations")},
                "registry_view": (base / "registry-view.json").is_file()}
        items.append(item)
    return {"stage": "memory", "skill": STAGES["memory"]["skill"],
            "found": bool(items), "items": items}


def _scan_patent(root) -> dict:
    """专利案件：全树找 kind=light-patent/case 的 case.yaml 逐案读。"""
    items = []
    for h in find_files(root, EXTENSIONS["patent"]["header"]):
        data = load_yaml(h)
        if not isinstance(data, dict) \
                or data.get("kind") != "light-patent/case":
            continue  # 同名文件非专利案件头，不冒认
        item = {"path": str(h.relative_to(root)),
                "case_id": data.get("case_id"),
                "status": data.get("status")}
        if item["status"] is None:
            item["error"] = "案件头缺顶层 status 字段"
        item["canonical"] = canonical("patent", item["status"])
        blocks = _gate_blocks("patent", data, item)
        if blocks:
            item["gate_blocks"] = blocks
        ledger = load_yaml(h.parent / "ledger.yaml")
        if isinstance(ledger, dict):
            item["deadlines"] = [
                d for d in ledger.get("deadlines") or []
                if isinstance(d, dict)]
        items.append(item)
    return {"stage": "patent", "skill": EXTENSIONS["patent"]["skill"],
            "found": bool(items), "items": items}


def _scan_copyright(root) -> dict:
    """软著案件：全树找 copyright.yaml 逐案读顶层 status。"""
    items = []
    for h in find_files(root, EXTENSIONS["software-copyright"]["header"]):
        data = load_yaml(h)
        item = {"path": str(h.relative_to(root)), "status": None}
        if data is None:
            item["error"] = "登记头存在但解析失败或顶层非映射"
        else:
            item["status"] = data.get("status")
            if item["status"] is None:
                item["error"] = "登记头缺顶层 status 字段"
            item["canonical"] = canonical("software-copyright",
                                          item["status"])
            item["title"] = data.get("title")
            if isinstance(data.get("correction"), dict):
                item["correction"] = data["correction"]
        items.append(item)
    return {"stage": "software-copyright",
            "skill": EXTENSIONS["software-copyright"]["skill"],
            "found": bool(items), "items": items}


def _current_precheck(path: Path):
    """折叠 prechecks/<target_id>.jsonl 给出当前预检态；无预检行则 None。

    该文件是混合种类的追加日志（precheck / confirmation 行交错），
    当前态不是末行：镜像 light-crawler 自家 current_precheck 的折叠
    语义——取末条 kind=precheck 记录；其 status 为
    pending_confirmation 且存在 precheck_id 相同的 confirmation 行
    时翻为 effective；effective 且 expires_at 已过时翻为 expired。
    返回记录副本，status 字段替换为折叠后的当前态。
    """
    if not path.is_file():
        return None
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return None
    records = [r for r in rows if r.get("kind") == "precheck"]
    if not records:
        return None
    latest = dict(records[-1])
    status = latest.get("status")
    if status == "pending_confirmation":
        confirmed = any(
            r.get("kind") == "confirmation"
            and r.get("precheck_id") == latest.get("precheck_id")
            for r in rows)
        if confirmed:
            status = "effective"
    if status == "effective":
        expires = str(latest.get("expires_at") or "")
        try:
            from datetime import datetime, timezone
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                status = "expired"
        except ValueError:
            pass  # 到期时刻形态不合：保持 effective 原判，不猜
    latest["status"] = status
    return latest


def _scan_crawler(root) -> dict:
    """爬虫工作区：crawler.yaml 头 + 逐目标登记/运行态/最新预检。"""
    items = []
    for h in find_files(root, EXTENSIONS["crawler"]["header"]):
        base = h.parent
        data = load_yaml(h)
        item = {"path": str(h.relative_to(root)), "status": None,
                "targets": []}
        if data is None:
            item["error"] = "工作区头存在但解析失败或顶层非映射"
            items.append(item)
            continue
        item["status"] = data.get("status")
        item["canonical"] = canonical("crawler", item["status"])
        item["workspace_id"] = data.get("workspace_id")
        item["circuit_broken_targets"] = \
            data.get("circuit_broken_targets") or []
        targets_dir = base / "targets"
        if targets_dir.is_dir():
            for tdir in sorted(targets_dir.iterdir()):
                tpath = tdir / "target.yaml"
                if not tdir.is_dir() or not tpath.is_file():
                    continue
                t = load_yaml(tpath) or {}
                tid = t.get("target_id") or tdir.name
                state = load_yaml(tdir / "state.yaml") or {}
                pc = _current_precheck(base / "prechecks" / f"{tid}.jsonl")
                item["targets"].append({
                    "target_id": tid,
                    "channel": t.get("channel"),
                    "circuit_broken": bool(state.get("circuit_broken")),
                    "circuit_reason": state.get("circuit_reason"),
                    "precheck_status": pc.get("status") if pc else None,
                    "precheck": pc,
                })
        items.append(item)
    return {"stage": "crawler", "skill": EXTENSIONS["crawler"]["skill"],
            "found": bool(items), "items": items}


def scan_project(root) -> dict:
    """全量扫描，返回 {root, stages, extensions}（stages 顺序按流水线）。"""
    root = Path(root)
    stages = {}
    for sid in PIPELINE:
        if sid == "literature":
            stages[sid] = _scan_literature(root)
        else:
            stages[sid] = _scan_yaml_stage(root, sid)
    stages["memory"] = _scan_memory(root)
    extensions = {
        "patent": _scan_patent(root),
        "software-copyright": _scan_copyright(root),
        "crawler": _scan_crawler(root),
    }
    return {"root": str(root), "stages": stages, "extensions": extensions}


def stage_statuses(stage_scan: dict) -> list:
    """某阶段全部登记头的 status 值列表（缺失/坏头不入列）。"""
    return [it["status"] for it in stage_scan.get("items", [])
            if it.get("status")]


def any_gate(stage_scan: dict) -> list:
    """某阶段全部硬门标记（跨登记头汇总）。"""
    out = []
    for it in stage_scan.get("items", []):
        out.extend(it.get("gates", []))
    return out


def stage_gate_blocks(stage_scan: dict) -> list:
    """某阶段全部 blocked_gate / return_block 族门记录（跨登记头汇总）。"""
    out = []
    for it in stage_scan.get("items", []):
        out.extend(it.get("gate_blocks", []))
    return out

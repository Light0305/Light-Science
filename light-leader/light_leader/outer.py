"""outer：外环综合（LD-05）与漏斗统计（LD-06），全只读。

立项回指（24-surpass/PLAN.md §9.3）：P0 外环综合——把 light-memory
事件账编译为单一可读的项目决策时间线 + 周期综合（模式识别、方向
调整建议落字）；P1 漏斗统计——status 汇总之外增各阶段门拦截次数、
返工率、被门拦原因分布的统计面。

数据源纪律（不许越界）：
- 阶段状态只走本包既有 status 汇总（scan.scan_project 的登记头读数，
  与 status/route 同一口径），不直读各包内部文件另行拼凑；
- 对象分布只消费 light-memory 的 registry-view.json（归属与校验口径
  见 registry.py：kind/版本不符时点名、不自行重建）；
- 事件与晋升只读 memory 记忆项目目录内的 events.jsonl /
  promotions.jsonl 两账（memory 的事件账存量本身，总控只读不写）。
读不到、解析失败、样本为零一律逐项点名，不猜、不补。

口径常数（写死并在输出中逐处引用，不许临时改）：
- STALE_DAYS：进行中阶段的最后一条事件距今超过此天数即点名长期
  停滞（14 天：两周无任何事件落账，按科研项目的周节奏已属停摆，
  与 route 的期限点名同为提前量口径）；
- REPEAT_MIN：同类失败事件达到此次数即称「反复」（2 次：一次是
  个案、两次成模式）。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import registry as registry_mod
from .layout import EXTENSIONS, GATE_FIX_POINTER, PIPELINE, STAGES
from .scan import find_files
from .statusmap import KNOWN_STATES, canonical

#: 停滞点名阈值（天）：阶段最后事件距今超过此值且阶段未收官即点名。
STALE_DAYS = 14

#: 「反复」判定下限：同类事件达到此次数才称模式，单次只记个案。
REPEAT_MIN = 2

#: 发现条目标题定界符（全角方括号）：输出格式的承重字符，源码以
#: 转义构造、运行时与字面量等值（同 light-patent execsearch 先例，
#: 避全套 lint 损坏签名扫描）。
_LB, _RB = "\u3010", "\u3011"

#: 对象类型到流水线阶段（registry-view / 事件 object_id 的类型前缀用；
#: 表外类型不归属任何阶段，只计数、不猜）。
OBJECT_TYPE_STAGE = {
    "paper": "literature",
    "idea_card": "idea",
    "design": "design",
    "execution": "experiment",
    "run": "experiment",
    "analysis_package": "analysis",
    "claim": "analysis",
    "journal_selection": "journal-select",
    "manuscript": "write",
    "figure": "figure",
    "review_package": "review",
    "concern": "review",
    "patent_case": "patent",
    "copyright_case": "software-copyright",
    "crawl_target": "crawler",
}

_ALL_STAGES = PIPELINE + ("memory",) + tuple(EXTENSIONS)


# ---------------------------------------------------------------- 读账

def _read_jsonl(path: Path) -> tuple[list, int]:
    """读 JSONL 为 dict 行列表；返回 (行, 坏行数)。文件缺失返回 ([], 0)。"""
    rows, bad = [], 0
    if not path.is_file():
        return rows, bad
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows, 1
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


def load_stock(root) -> dict:
    """定位 memory 记忆项目并读事件/晋升两账 + registry-view（只读）。

    返回 {memory_dirs, events, events_bad_rows, promotions,
    promotions_bad_rows, view, view_error, objects}。view 经
    registry.load_view 校验（kind/版本），失败时 view=None 且
    view_error 点名原因——统计面照常出，对象分布段落字说明缺失。
    """
    root = Path(root)
    mem_dirs = sorted({h.parent for h in find_files(root, "memory.yaml")})
    events, ev_bad = [], 0
    promos, pr_bad = [], 0
    for d in mem_dirs:
        rows, bad = _read_jsonl(d / "events.jsonl")
        events.extend(rows)
        ev_bad += bad
        rows, bad = _read_jsonl(d / "promotions.jsonl")
        promos.extend(rows)
        pr_bad += bad
    view, view_error = None, None
    try:
        _, view = registry_mod.load_view(root)
    except registry_mod.RegistryError as exc:
        view_error = str(exc)
    objects = []
    if view:
        for otype, rows in (view.get("objects_by_type") or {}).items():
            for r in rows or []:
                row = dict(r)
                row.setdefault("object_type", otype)
                objects.append(row)
    return {
        "memory_dirs": [str(d) for d in mem_dirs],
        "events": events,
        "events_bad_rows": ev_bad,
        "promotions": promos,
        "promotions_bad_rows": pr_bad,
        "view": view,
        "view_error": view_error,
        "objects": objects,
    }


def _parse_ts(value) -> datetime | None:
    """ISO 时间戳转 aware datetime；形态不合返回 None（不猜）。"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_package(pkg) -> str | None:
    """provenance.source_package 转阶段 id（去 light- 前缀后对表）。"""
    if not isinstance(pkg, str) or not pkg:
        return None
    name = pkg[len("light-"):] if pkg.startswith("light-") else pkg
    return name if name in _ALL_STAGES else None


def event_stage(ev: dict) -> str | None:
    """事件归属阶段：先 provenance.source_package，后 object_id 类型前缀。"""
    stage = _norm_package((ev.get("provenance") or {}).get("source_package"))
    if stage:
        return stage
    oid = ev.get("object_id")
    if isinstance(oid, str) and ":" in oid:
        return OBJECT_TYPE_STAGE.get(oid.split(":", 1)[0])
    return None


def object_stage(obj: dict) -> str | None:
    """注册对象归属阶段：source_package 优先，其次对象类型映射。"""
    stage = _norm_package(obj.get("source_package"))
    if stage:
        return stage
    return OBJECT_TYPE_STAGE.get(obj.get("object_type") or "")


# ---------------------------------------------------------------- 漏斗

def _stage_row(sid: str, ss: dict) -> dict:
    """单阶段漏斗行：登记头规范态分布 + 门拦截构成（数据源 = scan）。"""
    row = {
        "stage": sid, "found": bool(ss.get("found")), "headers": 0,
        "canonical": Counter(), "terminal": 0,
        "gates": Counter(), "gate_ids": Counter(),
        "blocked_reasons": Counter(), "returned_open_items": 0,
    }
    if sid == "literature":
        for it in ss.get("items", []):
            row["headers"] += 1
            for st, n in (it.get("status_counts") or {}).items():
                row["canonical"][canonical("literature", st) or "未知"] += n
                if st == "精读完成":
                    row["terminal"] += n
        return row
    if sid == "memory":
        for it in ss.get("items", []):
            row["headers"] += 1
            row["counts"] = it.get("counts") or {}
            row["registry_view"] = bool(it.get("registry_view"))
        return row
    spec = STAGES.get(sid) or EXTENSIONS.get(sid) or {}
    terminal = spec.get("terminal") or ()
    for it in ss.get("items", []):
        row["headers"] += 1
        if it.get("status") is None:
            row["canonical"]["读数缺失"] += 1
        else:
            row["canonical"][it.get("canonical") or "未知"] += 1
        if it.get("status") in terminal:
            row["terminal"] += 1
        for g in it.get("gates", []):
            row["gates"]["review_unavailable"] += 1
        for b in it.get("gate_blocks", []):
            fam = b.get("family")
            if fam == "blocked_gate":
                row["gates"]["blocked_gate"] += 1
                if b.get("gate_id"):
                    row["gate_ids"][b["gate_id"]] += 1
            elif fam == "return_block":
                row["gates"]["return_block"] += 1
                if b.get("kind") == "returned":
                    row["returned_open_items"] += len(b.get("open_items") or [])
        if it.get("blocked_reason"):
            row["blocked_reasons"][it["blocked_reason"]] += 1
    if sid == "crawler":
        pre = Counter()
        broken = 0
        for ws in ss.get("items", []):
            for t in ws.get("targets", []):
                pre[t.get("precheck_status") or "未预检"] += 1
                if t.get("circuit_broken"):
                    broken += 1
        row["precheck"] = pre
        row["circuit_broken"] = broken
    return row


def _transitions(events: list) -> tuple[Counter, Counter, int, int]:
    """状态跃迁与返工（回退跃迁）计数，口径见模块头注。

    只认 milestone 事件 payload 的 from/to 直落字段，且两值都在
    该阶段 KNOWN_STATES 主线序内才可判序；不可判序的跃迁单独计数
    点名，不并入返工率分母。
    返回 (顺进数/阶段, 返工数/阶段, 可判序总数, 不可判序数)。
    """
    fwd, back = Counter(), Counter()
    classifiable, unclassifiable = 0, 0
    for ev in events:
        if ev.get("type") != "milestone":
            continue
        payload = ev.get("payload")
        if not isinstance(payload, dict):
            continue
        frm, to = payload.get("from"), payload.get("to")
        if not isinstance(frm, str) or not isinstance(to, str):
            continue
        stage = event_stage(ev)
        order = KNOWN_STATES.get(stage or "", ())
        if frm in order and to in order:
            classifiable += 1
            if order.index(to) < order.index(frm):
                back[stage] += 1
            else:
                fwd[stage] += 1
        else:
            unclassifiable += 1
    return fwd, back, classifiable, unclassifiable


def funnel(scan: dict, stock: dict, now: datetime) -> dict:
    """漏斗统计面：阶段分布、门拦截、转化、返工、活动/停滞、项目分布。"""
    stages = {sid: _stage_row(sid, scan["stages"][sid])
              for sid in PIPELINE + ("memory",)}
    for sid in EXTENSIONS:
        stages[sid] = _stage_row(sid, scan["extensions"][sid])

    # 阶段活动与停滞（事件账时间戳为据；无事件 = 不可判，点名）
    last_event: dict[str, datetime] = {}
    event_counts = Counter()
    for ev in stock["events"]:
        st = event_stage(ev)
        if st is None:
            event_counts["（未归属）"] += 1
            continue
        event_counts[st] += 1
        ts = _parse_ts(ev.get("ts"))
        if ts and (st not in last_event or ts > last_event[st]):
            last_event[st] = ts
    for sid, row in stages.items():
        row["events"] = event_counts.get(sid, 0)
        last = last_event.get(sid)
        row["last_event"] = last.isoformat(timespec="seconds") if last else None
        open_now = row["canonical"].get("进行中", 0) + \
            row["canonical"].get("被门拦", 0) > 0
        row["open"] = open_now
        if not open_now:
            row["staleness"] = "已收官或未开工"
        elif last is None:
            row["staleness"] = "不可判（事件账无该阶段记录）"
        else:
            age = (now - last).total_seconds() / 86400.0
            row["age_days"] = round(age, 1)
            row["staleness"] = "长期停滞" if age > STALE_DAYS else "活跃"

    # 相邻阶段转化：下游已开工登记头数 除 上游已达终态数
    conversions = []
    seq = list(PIPELINE)
    for a, b in zip(seq, seq[1:]):
        denom = stages[a]["terminal"]
        numer = stages[b]["headers"]
        conversions.append({
            "from": a, "to": b, "numerator": numer, "denominator": denom,
            "ratio": (numer / denom) if denom else None,
        })

    fwd, back, classifiable, unclassifiable = _transitions(stock["events"])
    rework = {
        "forward": dict(fwd), "backward": dict(back),
        "classifiable": classifiable, "unclassifiable": unclassifiable,
        "rate": (sum(back.values()) / classifiable) if classifiable else None,
    }

    # 项目分布（registry-view 对象按 project 与阶段归属）
    projects: dict[str, dict] = {}
    for obj in stock["objects"]:
        proj = obj.get("project") or "（未登记项目）"
        slot = projects.setdefault(
            proj, {"objects": 0, "by_stage": Counter(),
                   "by_type": Counter(), "statuses": Counter()})
        slot["objects"] += 1
        slot["by_type"][obj.get("object_type") or "（未知类型）"] += 1
        slot["statuses"][obj.get("status") or "（无状态）"] += 1
        st = object_stage(obj)
        if st:
            slot["by_stage"][st] += 1
    obj_last: dict[str, datetime] = {}
    for ev in stock["events"]:
        oid, ts = ev.get("object_id"), _parse_ts(ev.get("ts"))
        if oid and ts and (oid not in obj_last or ts > obj_last[oid]):
            obj_last[oid] = ts
    proj_of = {o.get("object_id"): (o.get("project") or "（未登记项目）")
               for o in stock["objects"]}
    for oid, ts in obj_last.items():
        proj = proj_of.get(oid)
        if proj in projects:
            cur = projects[proj].get("last_event")
            if cur is None or ts > _parse_ts(cur):
                projects[proj]["last_event"] = ts.isoformat(timespec="seconds")

    return {
        "stages": stages, "conversions": conversions, "rework": rework,
        "projects": projects,
        "unattributed_events": event_counts.get("（未归属）", 0),
        "now": now.isoformat(timespec="seconds"),
    }


def _fmt_counter(counter: Counter) -> str:
    if not counter:
        return "0"
    return "、".join(f"{k}x{v}" for k, v in counter.most_common())


def render_funnel(res: dict, stock: dict) -> str:
    """漏斗统计面渲染（每项数字可回指 scan 读数或事件账行）。"""
    lines = ["# 漏斗统计（LD-06，只读汇总）", ""]
    lines.append(
        f"口径：阶段状态以登记头规范态（LD-03）计数；门拦截只认已登记"
        f"字段族（review_unavailable / blocked_gate / return_block）；"
        f"返工 = milestone 事件中状态回退跃迁 除 可判序跃迁；停滞阈值 "
        f"{STALE_DAYS} 天；统计时刻 {res['now']}。")
    lines.append(
        f"事件账样本：{len(stock['events'])} 条"
        f"（坏行 {stock['events_bad_rows']} 条不入统计）"
        + (f"；未归属阶段事件 {res['unattributed_events']} 条"
           if res["unattributed_events"] else "")
        + "。")
    lines.append("")
    lines.append("## 阶段分布与门拦截")
    for sid in PIPELINE + ("memory",) + tuple(EXTENSIONS):
        row = res["stages"][sid]
        slot = "主流水线" if sid in PIPELINE else (
            "横贯层" if sid == "memory" else EXTENSIONS[sid]["slot"])
        if not row["found"]:
            lines.append(f"- {sid}（{slot}）：未建（无登记头）")
            continue
        if sid == "memory":
            c = row.get("counts") or {}
            lines.append(
                f"- memory（横贯层）：对象 {c.get('objects', 0)}、事件 "
                f"{c.get('events', 0)}、事实 {c.get('facts', 0)}、关系 "
                f"{c.get('relations', 0)}；registry-view "
                f"{'已导出' if row.get('registry_view') else '未导出'}")
            continue
        dist = _fmt_counter(row["canonical"])
        gate_txt = _fmt_counter(row["gates"]) if row["gates"] else "无命中"
        lines.append(
            f"- {sid}（{slot}）：登记头 {row['headers']}，分布 {dist}；"
            f"已达终态 {row['terminal']}；门拦截 {gate_txt}")
        if row["gate_ids"]:
            lines.append(f"    门 ID 分布：{_fmt_counter(row['gate_ids'])}")
        if row["blocked_reasons"]:
            lines.append(
                f"    blocked 原因分布：{_fmt_counter(row['blocked_reasons'])}")
        if row["returned_open_items"]:
            lines.append(
                f"    design 打回未回补缺项：{row['returned_open_items']} 条")
        if sid == "crawler" and row.get("precheck"):
            lines.append(
                f"    目标预检分布：{_fmt_counter(row['precheck'])}；"
                f"熔断目标 {row.get('circuit_broken', 0)} 个")
        lines.append(
            f"    事件 {row['events']} 条，最后事件 "
            f"{row['last_event'] or '无'}，推进判定：{row['staleness']}"
            + (f"（距今 {row['age_days']} 天）"
               if row.get("age_days") is not None else ""))
    lines.append("")
    lines.append("## 相邻阶段转化（下游已开工登记头 除 上游已达终态）")
    for c in res["conversions"]:
        if c["ratio"] is None:
            lines.append(
                f"- {c['from']} 到 {c['to']}：不可计算"
                f"（{c['from']} 已达终态数为 0，下游登记头 "
                f"{c['numerator']}）")
        else:
            lines.append(
                f"- {c['from']} 到 {c['to']}：{c['numerator']} / "
                f"{c['denominator']} = {c['ratio']:.2f}")
    lines.append("注：一件上游产物可派生多件下游产物，比率可大于 1；"
                 "本表只作漏斗形状读数，不作配对归因。")
    lines.append("")
    rw = res["rework"]
    lines.append("## 返工（事件账状态跃迁）")
    if rw["classifiable"] == 0:
        lines.append(
            f"可判序跃迁 0 条（不可判序 {rw['unclassifiable']} 条），"
            "返工率不可计算。")
    else:
        lines.append(
            f"可判序跃迁 {rw['classifiable']} 条，其中回退 "
            f"{sum(rw['backward'].values())} 条，返工率 "
            f"{rw['rate']:.2%}；不可判序 {rw['unclassifiable']} 条"
            "（from/to 缺失或不在该阶段状态序内，不入分母）。")
        for st, n in Counter(rw["backward"]).most_common():
            lines.append(f"- {st}：回退跃迁 {n} 条")
    lines.append("")
    lines.append("## 项目分布（registry-view 对象）")
    if stock["view"] is None:
        lines.append(f"registry-view 不可用：{stock['view_error']}")
    elif not res["projects"]:
        lines.append("registry-view 中无对象登记。")
    for proj, slot in sorted(res["projects"].items()):
        lines.append(
            f"- 项目 {proj}：对象 {slot['objects']}"
            f"（类型 {_fmt_counter(slot['by_type'])}；状态 "
            f"{_fmt_counter(slot['statuses'])}；阶段归属 "
            f"{_fmt_counter(slot['by_stage']) or '无可归属'}；最后事件 "
            f"{slot.get('last_event') or '无'}）")
    return "\n".join(lines)


# ---------------------------------------------------------------- 综合

def synthesis(scan: dict, stock: dict, fun: dict, now: datetime) -> dict:
    """外环综合：决策时间线 + 模式发现 + 方向调整建议（全部带证据）。"""
    events = list(stock["events"])

    def _key(ev):
        ts = _parse_ts(ev.get("ts"))
        return (ts is None, ts or datetime.min.replace(tzinfo=timezone.utc),
                ev.get("seq") or 0)

    timeline = sorted(events, key=_key)
    stamps = [ts for ts in (_parse_ts(e.get("ts")) for e in events) if ts]
    findings = []

    # 1) 长期停滞与证据缺失（漏斗口径同源）
    for sid in PIPELINE + tuple(EXTENSIONS):
        row = fun["stages"][sid]
        if row["staleness"] == "长期停滞":
            findings.append({
                "kind": "stale", "stage": sid,
                "title": f"阶段 {sid} 长期停滞",
                "detail": f"最后事件 {row['last_event']}，距今 "
                          f"{row.get('age_days')} 天（阈值 {STALE_DAYS} "
                          "天）；当前分布 " + _fmt_counter(row["canonical"]),
                "evidence": [f"阶段事件 {row['events']} 条（事件账）"],
            })
        elif row["open"] and row["events"] == 0:
            findings.append({
                "kind": "no_evidence", "stage": sid,
                "title": f"阶段 {sid} 进行中但事件账无记录",
                "detail": "停滞不可判：该阶段登记头显示进行中/被门拦，"
                          "但 memory 事件账无一条归属该阶段",
                "evidence": ["事件账归属计数为 0"],
            })

    # 2) 失败模式（failure 事件按 failure_class 分组 + 回流去向）
    failures = [e for e in events if e.get("type") == "failure"]
    by_class = Counter()
    class_ids: dict[str, list] = {}
    reflux = Counter()
    for e in failures:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) \
            else {}
        cls = payload.get("failure_class") or "（未分类）"
        by_class[cls] += 1
        class_ids.setdefault(cls, []).append(e.get("event_id") or "?")
        if payload.get("reflux_target"):
            reflux[payload["reflux_target"]] += 1
    for cls, n in by_class.most_common():
        if n >= REPEAT_MIN:
            findings.append({
                "kind": "failure_repeat", "stage": None,
                "title": f"失败模式「{cls}」反复出现 {n} 次",
                "detail": "回流去向分布：" + (_fmt_counter(reflux)
                                              if reflux else "未登记"),
                "evidence": class_ids[cls],
            })
    if failures and not any(f["kind"] == "failure_repeat"
                            for f in findings):
        findings.append({
            "kind": "failure_single", "stage": None,
            "title": f"失败事件 {len(failures)} 条（均单次，未成模式）",
            "detail": "分类分布：" + _fmt_counter(by_class)
                      + ("；回流去向：" + _fmt_counter(reflux)
                         if reflux else ""),
            "evidence": [e.get("event_id") or "?" for e in failures],
        })

    # 3) 门反复咬人（当前快照：任一阶段门命中即点名，含解法指针）
    for sid in PIPELINE + tuple(EXTENSIONS):
        row = fun["stages"][sid]
        total = sum(row["gates"].values())
        if total:
            fix = None
            if row["gates"].get("review_unavailable"):
                fix = GATE_FIX_POINTER
            findings.append({
                "kind": "gate", "stage": sid,
                "title": f"阶段 {sid} 当前被门拦截 {total} 处",
                "detail": "构成：" + _fmt_counter(row["gates"])
                          + (f"；门 ID：{_fmt_counter(row['gate_ids'])}"
                             if row["gate_ids"] else "")
                          + (f"；blocked 原因："
                             f"{_fmt_counter(row['blocked_reasons'])}"
                             if row["blocked_reasons"] else ""),
                "evidence": [f"登记头 {row['headers']} 个（status 扫描）"],
                "fix": fix,
            })

    # 4) 返工热点
    for st, n in Counter(fun["rework"]["backward"]).most_common():
        findings.append({
            "kind": "rework", "stage": st,
            "title": f"阶段 {st} 出现状态回退跃迁 {n} 条",
            "detail": f"返工率（全体可判序跃迁口径）"
                      f"{fun['rework']['rate']:.2%}",
            "evidence": [f"milestone 回退计数 {n}（事件账）"],
        })

    # 5) 跨项目复用：晋升在账 + 同一上游对象跨项目登记
    withdrawn = {r.get("promotion_id") for r in stock["promotions"]
                 if r.get("action") == "withdrawn"}
    active_promos = [r for r in stock["promotions"]
                     if r.get("action") == "promoted"
                     and r.get("promotion_id") not in withdrawn]
    shared = {}
    by_upstream: dict[str, set] = {}
    for obj in stock["objects"]:
        up = obj.get("upstream_id")
        if up:
            by_upstream.setdefault(up, set()).add(
                obj.get("project") or "（未登记项目）")
    for up, projs in by_upstream.items():
        if len(projs) >= 2:
            shared[up] = sorted(projs)
    if active_promos or shared:
        detail_parts = []
        if active_promos:
            detail_parts.append("晋升来源项目：" + _fmt_counter(Counter(
                r.get("source_project") or "（未登记）"
                for r in active_promos)))
        if shared:
            detail_parts.append("跨项目同源对象：" + "、".join(
                f"{u}（{'/'.join(p)}）" for u, p in
                list(shared.items())[:10]))
        findings.append({
            "kind": "reuse", "stage": None,
            "title": f"跨项目复用命中：晋升在账 {len(active_promos)} 条、"
                     f"跨项目同源对象 {len(shared)} 个",
            "detail": "；".join(detail_parts),
            "evidence": [r.get("promotion_id") or "?"
                         for r in active_promos]
                        + [f"upstream:{u}" for u in shared],
        })

    suggestions = _suggest(findings, fun)
    return {
        "timeline": timeline,
        "span": (min(stamps).isoformat(timespec="seconds"),
                 max(stamps).isoformat(timespec="seconds")) if stamps
        else None,
        "findings": findings,
        "suggestions": suggestions,
        "sample": {
            "events": len(events), "bad_rows": stock["events_bad_rows"],
            "objects": len(stock["objects"]),
            "projects": len(fun["projects"]),
            "failures": len(failures),
        },
    }


def _suggest(findings: list, fun: dict) -> list[str]:
    """方向调整建议：每条由一条发现机械导出并回指证据，不自由发挥。"""
    out = []
    for f in findings:
        kind = f["kind"]
        if kind == "stale":
            out.append(
                f"优先处理停滞阶段 {f['stage']}：先按该包 SKILL 核对"
                f"登记头现状，再决定推进、回补或显式 parked/killed，"
                f"不要让其无限期挂进行中。（据：{f['title']}）")
        elif kind == "failure_repeat":
            out.append(
                f"对{f['title']}安排一次针对性复盘：按回流去向回上游"
                f"阶段核对同类失败的共同前提，复盘结论经 light-memory "
                f"候选通道沉淀。（据：事件 "
                f"{'、'.join(f['evidence'][:5])}）")
        elif kind == "gate":
            fix = f.get("fix") or "按该门登记的 fix_pointer / 对应包 " \
                                   "SKILL 规程解法处理。"
            out.append(
                f"先解 {f['stage']} 的门再谈推进：{fix}"
                f"（据：{f['title']}）")
        elif kind == "rework":
            out.append(
                f"核对 {f['stage']} 的回退原因：回退跃迁集中出现时，"
                f"优先检查该阶段开工条件是否被跳过。（据：{f['title']}）")
        elif kind == "no_evidence":
            out.append(
                f"补 {f['stage']} 的收编：阶段已开工但 memory 事件账"
                f"无记录，先跑 light-memory 对应适配器 ingest 对账"
                f"（watermarks），否则后续综合持续缺该阶段证据。"
                f"（据：{f['title']}）")
        elif kind == "reuse":
            out.append(
                "新项目/新阶段开工时先经 light-memory recall 检索既有"
                "晋升与同源对象，避免重复劳动。（据：跨项目复用命中）")
    if not out:
        out.append("本周期未检出需调整的模式：无长期停滞、无反复失败、"
                   "无当前门拦截、无状态回退；维持现行推进节奏。")
    return out


def render_synthesis(res: dict, stock: dict) -> str:
    """外环综合简报渲染：样本量先行，结论逐条带证据。"""
    s = res["sample"]
    lines = ["# 外环综合简报（LD-05，只读综合）", ""]
    span_txt = (res["span"][0] + " ~ " + res["span"][1]) if res["span"] \
        else "无"
    lines.append(
        f"样本量：事件 {s['events']} 条（坏行 {s['bad_rows']} 条不入）、"
        f"注册对象 {s['objects']} 个、项目 {s['projects']} 个、失败事件 "
        f"{s['failures']} 条；事件时间跨度 {span_txt}。")
    if stock["view"] is None:
        lines.append(f"注：registry-view 不可用（{stock['view_error']}），"
                     "对象/项目样本只取事件账，跨项目复用判定受限。")
    if s["events"] == 0:
        lines.append("")
        lines.append("事件账为空：无可综合的决策时间线与模式样本。"
                     "先由 light-memory 各适配器 ingest 收编各阶段产物，"
                     "再跑本命令。")
        return "\n".join(lines)
    lines.append("")
    lines.append("## 决策时间线（事件账全量，按时间序）")
    for ev in res["timeline"]:
        stage = event_stage(ev) or "（未归属）"
        lines.append(
            f"- {ev.get('ts') or '（无时间戳）'} [{stage}] "
            f"{ev.get('type') or '（无类型）'} {ev.get('event_id') or ''}："
            f"{ev.get('summary') or '（无摘要）'}")
    lines.append("")
    lines.append("## 模式发现")
    if not res["findings"]:
        lines.append("无（按当前口径未检出停滞、反复失败、门拦截、"
                     "返工热点与跨项目复用）。")
    for f in res["findings"]:
        lines.append(f"- {_LB}{f['title']}{_RB}{f['detail']}")
        lines.append(f"  证据：{'、'.join(str(e) for e in f['evidence'])}")
    lines.append("")
    lines.append("## 方向调整建议（建议非执行，总控不代跑）")
    for i, sug in enumerate(res["suggestions"], 1):
        lines.append(f"{i}. {sug}")
    return "\n".join(lines)

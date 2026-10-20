"""干预核查点机械核验（EXP-D03，硬纪律 4 的补完）。

v1.0 的半成品：intervention_checks 只随 spec 落身份区存档，声称值 vs
实际生效值从不比对——而生态反面教训正是「声称扫了参数、实际恒定，
产出的改进按设计原理不存在」（Sakana 评测实锤）。本模块把核验做成
机械动作：

- 每条核查点登记三件：声称值 claimed、实际值来源指针 verify.source、
  核验方式 verify.kind（三类核验器：equals 相等 / range 区间内 /
  file_hash 文件哈希一致）；
- 实际值只从来源文件机械读取（JSON 取键、JSONL 逐行取键、文件字节
  哈希），run-finish 时由工具执行——不收执行者口头报告的实际值，
  不许手工标 pass 蒙混；
- 来源文件可用 "@metrics" 指代本 run 在 run-finish 登记的
  --metrics-file（其 sha256 指纹同刻落 run.yaml，事后换文件即与
  指纹不符，校验时可复核）；
- 逐条结论四态：pass / fail / unverifiable（登记了核验方式但实际
  值机械取不到，如实报取不到，不冒充通过）/ not_verified（未登记
  核验方式的 v1.0 存档形态，如实报未核验）；
- run 级总判与阻断处置在 project.finish_run：总判 failed /
  unverifiable 时 completed 终止自动转 deviated 候选。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schema import INTERVENTION_VERIFY_KINDS
from .util import canonical_json, utcnow

METRICS_REF = "@metrics"


def _distinct(values: list) -> list:
    """按规范化 JSON 去重保序（数值/字符串/结构值统一口径）。"""
    seen: dict[str, object] = {}
    for v in values:
        seen.setdefault(canonical_json(v), v)
    return list(seen.values())


def _read_key_values(path: Path, key: str) -> tuple[list, str]:
    """从 JSON / JSONL 文件机械取键值。返回 (values, error)：
    取不到时 values 为空、error 说明原因（文件不存在/键缺失等）。"""
    if not path.exists():
        return [], f"来源文件不存在：{path}"
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return [], f"来源文件不可读：{e}"
    values: list = []
    if suffix == ".jsonl":
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return [], f"来源文件第 {i} 行不是合法 JSON：{path.name}"
            if isinstance(row, dict) and key in row:
                values.append(row[key])
    elif suffix == ".json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return [], f"来源文件不是合法 JSON：{path.name}"
        rows = doc if isinstance(doc, list) else [doc]
        for row in rows:
            if isinstance(row, dict) and key in row:
                values.append(row[key])
    else:
        return [], f"来源文件格式不支持取键：{path.name}（须为 .json / .jsonl）"
    if not values:
        return [], f"来源文件 {path.name} 中无键 {key!r} 的取值"
    return values, ""


def _resolve_source_file(source: dict, metrics_file: Path | None) -> tuple[Path | None, str]:
    raw = source.get("file")
    if raw == METRICS_REF:
        if metrics_file is None:
            return None, "来源声明为 @metrics 但本 run 未登记 --metrics-file"
        return Path(metrics_file), ""
    if not raw:
        return None, "核验方式未给来源文件指针（verify.source.file）"
    return Path(str(raw)), ""


def _verify_one(check: dict, metrics_file: Path | None) -> dict:
    """核验一条核查点，返回结论记录（不抛异常：取不到实际值落
    unverifiable，核验本身不许把 run-finish 撞崩）。"""
    point = check.get("point") or "(未命名核查点)"
    claimed = check.get("claimed")
    rec: dict = {"point": point, "claimed": claimed, "actual": None,
                 "kind": None, "status": "not_verified", "detail": "",
                 "source": check.get("evidence") or ""}
    verify = check.get("verify")
    if not isinstance(verify, dict) or not verify.get("kind"):
        rec["detail"] = ("未登记核验方式（verify）：v1.0 存档形态，"
                         "只存不验——如实报未核验，不冒充已验")
        return rec
    kind = verify.get("kind")
    rec["kind"] = kind
    if kind not in INTERVENTION_VERIFY_KINDS:
        rec["status"] = "unverifiable"
        rec["detail"] = (f"核验方式 {kind!r} 不在三类核验器内"
                         f"（{list(INTERVENTION_VERIFY_KINDS)}）")
        return rec
    source = verify.get("source") or {}
    if isinstance(source, dict) and source.get("file"):
        rec["source"] = str(source.get("file"))
    path, err = _resolve_source_file(source if isinstance(source, dict) else {},
                                     metrics_file)
    if path is None:
        rec["status"] = "unverifiable"
        rec["detail"] = err
        return rec

    if kind == "file_hash":
        if not path.exists():
            rec["status"] = "unverifiable"
            rec["detail"] = f"来源文件不存在：{path}"
            return rec
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        rec["actual"] = actual
        if not isinstance(claimed, str) or not claimed.strip():
            rec["status"] = "unverifiable"
            rec["detail"] = "file_hash 核验的声称值须为 sha256 十六进制串"
            return rec
        ok = actual.lower() == claimed.strip().lower()
        rec["status"] = "pass" if ok else "fail"
        rec["detail"] = ("文件 sha256 与声称一致" if ok else
                         "文件 sha256 与声称不一致（文件内容不是声称的那一份）")
        return rec

    key = source.get("key")
    if not key:
        rec["status"] = "unverifiable"
        rec["detail"] = "equals/range 核验须给来源键（verify.source.key）"
        return rec
    values, err = _read_key_values(path, str(key))
    if err:
        rec["status"] = "unverifiable"
        rec["detail"] = err
        return rec
    distinct = _distinct(values)

    if kind == "equals":
        if isinstance(claimed, list):
            # 声称一组取值（如扫参网格）：实际取值集须恰等于声称集——
            # 声称扫参、实际恒定在此现形（生态反面教训的回归形态）
            ok = {canonical_json(v) for v in distinct} == \
                {canonical_json(v) for v in claimed}
            rec["actual"] = distinct
            rec["status"] = "pass" if ok else "fail"
            rec["detail"] = ("实际取值集与声称集一致" if ok else
                             "实际取值集与声称集不一致：声称 "
                             f"{claimed}，实际只出现 {distinct}"
                             "（声称的干预没有真正生效）")
            return rec
        if len(distinct) == 1:
            rec["actual"] = distinct[0]
            ok = distinct[0] == claimed
            rec["status"] = "pass" if ok else "fail"
            rec["detail"] = ("实际生效值与声称一致" if ok else
                             f"实际生效值 {distinct[0]!r} 与声称 {claimed!r} 不一致")
            return rec
        rec["actual"] = distinct
        rec["status"] = "fail"
        rec["detail"] = (f"实际取值不唯一（{distinct}），与声称的单一值 "
                         f"{claimed!r} 不符")
        return rec

    # kind == "range"
    lo = hi = None
    if isinstance(claimed, dict):
        lo, hi = claimed.get("min"), claimed.get("max")
    elif isinstance(claimed, (list, tuple)) and len(claimed) == 2:
        lo, hi = claimed
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        rec["status"] = "unverifiable"
        rec["detail"] = "range 核验的声称值须为 {min, max} 或 [lo, hi] 数值区间"
        return rec
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               for v in values):
        rec["status"] = "unverifiable"
        rec["detail"] = f"来源键 {key!r} 的取值含非数值，无从判区间"
        return rec
    rec["actual"] = distinct[0] if len(distinct) == 1 else [min(values), max(values)]
    ok = all(lo <= v <= hi for v in values)
    rec["status"] = "pass" if ok else "fail"
    rec["detail"] = (f"实际取值全落在声称区间 [{lo}, {hi}] 内" if ok else
                     f"实际取值 {[v for v in values if not lo <= v <= hi]} "
                     f"越出声称区间 [{lo}, {hi}]")
    return rec


def verify_intervention_checks(run: dict, *, metrics_file: Path | None = None) -> dict:
    """对 run 身份区的全部核查点逐条机械核验，返回落 run.yaml 结论区
    的核验记录块。总判口径见 schema.INTERVENTION_VERDICTS。"""
    checks = (run.get("identity") or {}).get("intervention_checks") or []
    results = []
    for check in checks:
        if isinstance(check, dict):
            results.append(_verify_one(check, metrics_file))
        else:
            results.append({"point": str(check), "claimed": None,
                            "actual": None, "kind": None,
                            "status": "not_verified",
                            "detail": "核查点不是对象形态，无从机械核验",
                            "source": ""})
    states = [r["status"] for r in results]
    if not results:
        verdict = "no_checks"
    elif "fail" in states:
        verdict = "failed"
    elif "unverifiable" in states:
        verdict = "unverifiable"
    elif "pass" in states:
        verdict = "passed"
    else:
        verdict = "not_verified"
    return {"verified_at": utcnow(), "verdict": verdict, "results": results}

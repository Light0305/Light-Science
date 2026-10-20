"""GRIM 族相容性检查（RV-09）+ 舍入区间法（RV-08，statcheck 口径）。

三件：均值粒度（GRIM 本体）、百分比粒度、合计相容性。

共同纪律：
- 容差不由人拍：由报告值的小数位导出真值区间 [v − step/2, v + step/2)，
  正确舍入（半上）永不判错（statcheck 的舍入区间法）；
- 适用性硬门：被检量元数据不齐（值/小数位/n/items/量表类型缺任一）
  或量表类型非整数粒度 → not_assessable，不许猜测启动——把连续量
  当整数检会造出毁掉法医层信誉的假阳性；
- 判败只作旗标 + 算式证据，归因留人工裁决位（forensic 侧落 finding）。

数值一律走 Decimal（由字符串构造），不经 float，避免二进制浮点
在区间边界上造假阳性/假阴性。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from . import schema

_EPS = Decimal("1e-12")


def decimals_of(printed) -> int | None:
    """报告值字符串的小数位数；非数值返回 None。"""
    s = str(printed).strip()
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    if "." not in s and "e" not in s.lower():
        return 0
    exp = -d.as_tuple().exponent
    return max(exp, 0)


def rounding_interval(printed):
    """由报告值导出真值区间 [lo, hi)（半上舍入的逆像）。

    返回 (lo, hi, decimals)；非数值返回 None。
    """
    s = str(printed).strip()
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    d = decimals_of(s)
    step = Decimal(1).scaleb(-d) if d > 0 else Decimal(1)
    half = step / 2
    return (v - half, v + half, d)


def consistent_with_rounding(printed, true_value) -> bool | None:
    """真值（可复算量）经半上舍入是否恰为报告值。真值非数值返回 None。"""
    iv = rounding_interval(printed)
    if iv is None:
        return None
    lo, hi, _ = iv
    try:
        x = Decimal(str(true_value))
    except InvalidOperation:
        return None
    return lo <= x < hi


# ---------------------------------------------------------------- 适用性硬门

def _missing_meta(entry: dict, fields) -> list:
    missing = []
    for f in fields:
        v = entry.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f)
    return missing


def _base_row(entry: dict, result: str, detail: str, evidence=None) -> dict:
    return {
        "stat_id": entry.get("stat_id"),
        "kind": entry.get("kind"),
        "result": result,
        "detail": detail,
        "formula_evidence": evidence,
        "metadata": {
            "value": entry.get("value"),
            "decimals": entry.get("decimals"),
            "n": entry.get("n"),
            "items": entry.get("items"),
            "scale_type": entry.get("scale_type"),
        },
        "missing": [],
    }


def _not_assessable(entry: dict, reason: str, missing=None) -> dict:
    row = _base_row(entry, "not_assessable", reason)
    row["missing"] = list(missing or [])
    return row


# ---------------------------------------------------------------- 均值粒度

def grim_mean(entry: dict) -> dict:
    """均值粒度：mean × n × items 须在舍入容差内相容于整数总和。"""
    missing = _missing_meta(entry, ["value", "n", "items", "scale_type"])
    d = entry.get("decimals")
    if d is None:
        derived = decimals_of(entry.get("value"))
        if derived is None:
            missing.append("decimals")
        else:
            d = derived
    if missing:
        return _not_assessable(
            entry, "元数据不齐，适用性硬门未过：" + "、".join(missing), missing)
    if entry["scale_type"] not in schema.INTEGER_SCALE_TYPES:
        return _not_assessable(
            entry, f"量表类型 {entry['scale_type']} 非整数粒度"
                   "（连续量不适用 GRIM，硬检将造假阳性）")
    iv = rounding_interval(entry["value"])
    if iv is None:
        return _not_assessable(entry, "报告值非数值")
    lo, hi, _ = iv
    n = int(entry["n"])
    items = int(entry["items"])
    total_units = n * items
    lo_k = lo * total_units
    hi_k = hi * total_units
    # 整数解存在 ⟺ ceil(lo_k) < hi_k
    k_min = int(lo_k.to_integral_value(rounding="ROUND_CEILING"))
    evidence = (f"真值均值 ∈ [{lo}, {hi})，总和单位 N=n×items={total_units}，"
                f"整数总和须 ∈ [{lo_k}, {hi_k})")
    if Decimal(k_min) < hi_k:
        return _base_row(entry, "compatible",
                         f"存在整数总和 k={k_min} 与报告均值相容",
                         evidence + f"，取 k={k_min}")
    return _base_row(entry, "incompatible",
                     "不存在整数总和与报告均值相容（旗标，归因待人工裁决）",
                     evidence + "，无整数解")


# ---------------------------------------------------------------- 百分比粒度

def grim_percent(entry: dict) -> dict:
    """百分比粒度：pct × n / 100 须在舍入容差内相容于整数计数。"""
    missing = _missing_meta(entry, ["value", "n", "scale_type"])
    if entry.get("decimals") is None and \
            decimals_of(entry.get("value")) is None:
        missing.append("decimals")
    if missing:
        return _not_assessable(
            entry, "元数据不齐，适用性硬门未过：" + "、".join(missing), missing)
    if entry["scale_type"] not in ("count", "percent"):
        return _not_assessable(
            entry, f"量表类型 {entry['scale_type']} 不是计数来源，"
                   "百分比粒度不适用")
    iv = rounding_interval(entry["value"])
    if iv is None:
        return _not_assessable(entry, "报告值非数值")
    lo, hi, _ = iv
    n = int(entry["n"])
    lo_k = lo * n / 100
    hi_k = hi * n / 100
    k_min = int(lo_k.to_integral_value(rounding="ROUND_CEILING"))
    evidence = (f"真值百分比 ∈ [{lo}, {hi})，计数 k 须 ∈ [{lo_k}, {hi_k})"
                f"（n={n}，0 ≤ k ≤ n）")
    if Decimal(k_min) < hi_k and 0 <= k_min <= n:
        return _base_row(entry, "compatible",
                         f"存在整数计数 k={k_min} 与报告百分比相容",
                         evidence + f"，取 k={k_min}")
    return _base_row(entry, "incompatible",
                     "不存在整数计数与报告百分比相容（旗标，归因待人工裁决）",
                     evidence + "，无整数解")


# ---------------------------------------------------------------- 合计相容性

def grim_total(entry: dict) -> dict:
    """合计相容性：分项之和与总计之差须 ≤ (分项数+1) × 半步长。"""
    parts = entry.get("parts")
    missing = _missing_meta(entry, ["value"])
    if not parts:
        missing.append("parts")
    if missing:
        return _not_assessable(
            entry, "元数据不齐，适用性硬门未过：" + "、".join(missing), missing)
    d = entry.get("decimals")
    if d is None:
        d = decimals_of(entry["value"])
    if d is None:
        return _not_assessable(entry, "总计值非数值，无法导出舍入容差")
    try:
        part_vals = [Decimal(str(p)) for p in parts]
        total = Decimal(str(entry["value"]))
    except InvalidOperation:
        return _not_assessable(entry, "分项或总计含非数值")
    step = Decimal(1).scaleb(-int(d)) if int(d) > 0 else Decimal(1)
    bound = (len(part_vals) + 1) * (step / 2)
    s = sum(part_vals)
    diff = abs(s - total)
    evidence = (f"Σ分项={s}，总计={total}，|差|={diff}，"
                f"容差=({len(part_vals)}+1)×{step}/2={bound}")
    if diff <= bound + _EPS:
        return _base_row(entry, "compatible", "分项之和与总计相容", evidence)
    return _base_row(entry, "incompatible",
                     "分项之和与总计超出舍入容差（旗标，归因待人工裁决）",
                     evidence)


_CHECKS = {"mean": grim_mean, "percent": grim_percent, "total": grim_total}


def run_grim(entries) -> list:
    """对登记表逐条跑相容性检查，返回 compatibility 行列表。"""
    rows = []
    for i, entry in enumerate(entries or []):
        e = dict(entry)
        e.setdefault("stat_id", f"GS{i + 1:03d}")
        kind = e.get("kind")
        if kind not in _CHECKS:
            rows.append(_not_assessable(
                e, f"kind {kind!r} 不在 GRIM 三件词表 {schema.GRIM_KINDS}"))
            continue
        rows.append(_CHECKS[kind](e))
    return rows

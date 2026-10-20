"""GRIM 族相容性检查（RV-09）+ 舍入区间法（RV-08，statcheck 口径）。

四件：均值粒度（GRIM 本体）、百分比粒度、合计相容性、GRIMMER
（mean/SD/n 三元组相容，v1.1 REV-D07：登记元数据扩 SD 字段后，
整数总和与整数平方和须同时存在，判定走精确有理数不经 float）。

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
from fractions import Fraction

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
            "sd": entry.get("sd"),
            "sd_decimals": entry.get("sd_decimals"),
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


# ---------------------------------------------------------------- GRIMMER

def _ceil_frac(x: Fraction) -> int:
    return -(-x.numerator // x.denominator)


def grim_grimmer(entry: dict) -> dict:
    """GRIMMER：mean/SD/n 三元组相容（原始整数值的总和与平方和同存）。

    判定：存在整数 T（总和）与整数 SS（平方和）使 T/n 落报告均值的
    舍入区间、且 sqrt((SS - T^2/n)/(n-1)) 落报告 SD 的舍入区间；
    附加同余约束 SS ≡ T (mod 2)（整数平方与自身同奇偶，恒等式）。
    全程 Fraction 精确运算，区间边界口径与 GRIM 三件一致（半上）。
    适用性硬门同口径：元数据不齐 / 非整数粒度 / n<2 / 复合均值
    （items>1 时参与者分数粒度为 1/items，三元组本体不适用）一律
    not_assessable，不许硬算造假阳性。
    """
    entry = dict(entry)
    entry["kind"] = "grimmer"
    missing = _missing_meta(entry, ["value", "sd", "n", "scale_type"])
    if entry.get("decimals") is None \
            and decimals_of(entry.get("value")) is None:
        missing.append("decimals")
    if entry.get("sd_decimals") is None \
            and decimals_of(entry.get("sd")) is None \
            and "sd" not in missing:
        missing.append("sd_decimals")
    if missing:
        return _not_assessable(
            entry, "元数据不齐，适用性硬门未过：" + "、".join(missing), missing)
    if entry["scale_type"] not in schema.INTEGER_SCALE_TYPES:
        return _not_assessable(
            entry, f"量表类型 {entry['scale_type']} 非整数粒度"
                   "（GRIMMER 只对整数值数据成立，硬检将造假阳性）")
    try:
        n = int(entry["n"])
    except (TypeError, ValueError):
        return _not_assessable(entry, "n 非整数，适用性硬门未过")
    if n < 2:
        return _not_assessable(
            entry, "n<2 时样本 SD 无定义，GRIMMER 不适用")
    items = entry.get("items")
    if items is not None and int(items) != 1:
        return _not_assessable(
            entry, f"items={items} 的复合均值粒度为 1/items："
                   "GRIMMER 三元组对原始整数值成立，复合分数不硬算")
    iv_m = rounding_interval(entry["value"])
    iv_s = rounding_interval(entry["sd"])
    if iv_m is None or iv_s is None:
        return _not_assessable(entry, "报告均值或 SD 非数值")
    lo_m, hi_m, _ = (Fraction(x) for x in iv_m)
    lo_s, hi_s, _ = (Fraction(x) for x in iv_s)
    if hi_s <= 0:
        return _not_assessable(entry, "报告 SD 非正，无法构成舍入区间")
    lo_s = max(lo_s, Fraction(0))
    lo2, hi2 = lo_s * lo_s, hi_s * hi_s
    t_first = _ceil_frac(lo_m * n)
    t_last = _ceil_frac(hi_m * n) - 1     # T/n < hi_m → T < hi_m * n
    evidence_head = (f"均值真值 ∈ [{iv_m[0]}, {iv_m[1]})，"
                     f"SD 真值 ∈ [{iv_s[0]}, {iv_s[1]})，n={n}，"
                     f"整数总和 T 须 ∈ [{t_first}, {t_last}]")
    if t_first > t_last:
        return _base_row(entry, "incompatible",
                         "无整数总和与报告均值相容（GRIM 层已判败）",
                         evidence_head + "，T 区间为空")
    for t in range(t_first, t_last + 1):
        base = Fraction(t * t, n)
        ss_lo = (n - 1) * lo2 + base
        ss_hi = (n - 1) * hi2 + base
        k = _ceil_frac(ss_lo)
        for cand in (k, k + 1):
            if cand < ss_hi and (cand - t) % 2 == 0:
                return _base_row(
                    entry, "compatible",
                    f"存在整数总和 T={t} 与平方和 SS={cand} 同时满足"
                    "均值与 SD 的舍入区间",
                    evidence_head + f"，取 T={t}、SS={cand}"
                    f"（SS 须 ∈ [{ss_lo}, {ss_hi}) 且 SS≡T mod 2）")
    return _base_row(entry, "incompatible",
                     "不存在整数 (总和, 平方和) 对同时满足报告均值与 SD"
                     "（旗标，归因待人工裁决）",
                     evidence_head + "，逐 T 检验均无合规整数平方和")


_CHECKS = {"mean": grim_mean, "percent": grim_percent, "total": grim_total,
           "grimmer": grim_grimmer}


def run_grim(entries) -> list:
    """对登记表逐条跑相容性检查，返回 compatibility 行列表。

    kind=mean 且登记了 sd 的条目，GRIM 行后追加一行 GRIMMER
    三元组行（同 stat_id）；kind=grimmer 的条目只跑三元组。
    """
    rows = []
    for i, entry in enumerate(entries or []):
        e = dict(entry)
        e.setdefault("stat_id", f"GS{i + 1:03d}")
        kind = e.get("kind")
        if kind not in _CHECKS:
            rows.append(_not_assessable(
                e, f"kind {kind!r} 不在 GRIM 族词表 {schema.GRIM_KINDS}"))
            continue
        rows.append(_CHECKS[kind](e))
        if kind == "mean" and e.get("sd") is not None:
            rows.append(grim_grimmer(e))
    return rows

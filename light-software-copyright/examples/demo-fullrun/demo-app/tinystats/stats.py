"""描述统计计算：均值、中位数、方差、分位数与异常值标记。"""

from __future__ import annotations

import math


def mean(values):
    """计算算术平均值。"""
    if not values:
        raise ValueError("空序列无法计算均值")
    return sum(values) / len(values)


def median(values):
    """计算中位数（偶数个取中间两数均值）。"""
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def variance(values, sample=True):
    """计算方差；sample 为真时用样本方差（n-1）。"""
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    total = sum((v - m) ** 2 for v in values)
    return total / (n - 1) if sample else total / n


def quantile(values, q):
    """线性插值分位数，q 取 0 到 1。"""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("空序列无法计算分位数")
    pos = q * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[int(pos)]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def flag_outliers(values, k=1.5):
    """按 IQR 规则标记异常值下标。"""
    if len(values) < 4:
        return []
    q1 = quantile(values, 0.25)
    q3 = quantile(values, 0.75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return [i for i, v in enumerate(values) if v < lo or v > hi]


def summarize(values):
    """汇总一份描述统计结果字典。"""
    return {
        "count": len(values),
        "mean": mean(values),
        "median": median(values),
        "stdev": math.sqrt(variance(values)),
        "min": min(values),
        "max": max(values),
        "outliers": flag_outliers(values),
    }

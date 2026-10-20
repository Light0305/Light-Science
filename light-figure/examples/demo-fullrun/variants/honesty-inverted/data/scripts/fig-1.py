# --- light-figure-script ---
# fig_id: fig-1
# style_build_hash: f39c196b05109b8a4bb139266e91238dfbe53a12436087bfab126813b03c0d9f
# column: double
# panels: {rows: 1, cols: 2}
# axes:
#   y: {direction: decreasing, limits: [60, 82], data_min: 62.187,
#       data_max: 80.898, truncated: false, truncation_declared: false}
#   x: {direction: increasing, limits: [1, 6], data_min: 1, data_max: 6,
#       truncated: false, truncation_declared: false}
# aspect: {ratio: 0.52, declared: true}
# area_encoding: none
# palette: {categorical: PAL-OI-8, continuous: PAL-BATLOW}
# --- end light-figure-script ---
"""三臂 MOTA 对比（演示数据图脚本）：a 逐段曲线、b 臂均值 ± 95% CI。"""
import csv
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "source-data" / "fig-1.csv"
ARMS = ["fixed", "oracle", "predicted"]


def _series():
    rows = list(csv.DictReader(DATA.open(encoding="utf-8")))
    out = dict()
    for arm in ARMS:
        out[arm] = [float(r["mota"]) for r in rows if r["arm"] == arm]
    return out


def draw(fig, axes):
    series = _series()
    ax = axes[0]
    for arm in ARMS:
        ax.plot(range(1, 7), series[arm], marker="o", label=arm)
    ax.set_xlim(1, 6)
    ax.set_ylim(82, 60)
    ax.set_xlabel("Video segment")
    ax.set_ylabel("MOTA (points)")
    ax.set_title("a", loc="left")
    ax.legend(title="Arm", frameon=False)
    ax2 = axes[1]
    means, cis = [], []
    for arm in ARMS:
        vals = series[arm]
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals)
                       / (len(vals) - 1))
        means.append(mean)
        cis.append(1.96 * sd / math.sqrt(len(vals)))
    ax2.errorbar(ARMS, means, yerr=cis, fmt="o", capsize=3)
    ax2.set_ylim(82, 60)
    ax2.set_ylabel("MOTA (points)")
    ax2.set_title("b", loc="left")

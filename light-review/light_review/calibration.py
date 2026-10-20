"""校准门四件（R3/RV-14/RV-15）：量表锚 / 封顶规则 / 不对称合成 / 验证台报表。

决定建议（decision.md）只有四件齐备才许生成，缺一自动降级为
问题清单 + 风险分级（meta.py 消费本模块的 assess 结果）。四件的
登记全在 calibration.yaml（按刊登记、逐条可查），验证台报表
（bench.py 产 reports/bench_report.json）以配置哈希绑定：评审
配置（席位集 / 量表 / 封顶 / 不对称权重）任一漂移，报表即过期，
校准门判不齐——不许拿旧报表给新配置的决定建议背书（RV-15：
验证配置即生产配置）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import load_package, save_calibration, save_review
from .util import component_hash, today

# 量表锚模板：百分位锚 + 反通胀口令（AgentReview SCORE_CONTROL 口径）。
# 这是技能内置的校准模板，calibration init 时按目标刊落字，可改但
# 改即配置漂移（验证台须重跑）。
DEFAULT_SCALE = {
    "name": "overall-10",
    "version": "1.0",
    "anchors": [
        {"score": 10, "percentile": "top 2%",
         "meaning": "改变领域理解的彻底工作（strong accept）"},
        {"score": 8, "percentile": "top 10%",
         "meaning": "全部主张有充分支持、方法高度原创（accept）"},
        {"score": 6, "percentile": "top 50% of accepted",
         "meaning": "主要主张有支持，少量补强非必需（borderline accept）"},
        {"score": 5, "percentile": "borderline",
         "meaning": "主要主张大体成立，有次要缺口（borderline reject）"},
        {"score": 3, "percentile": "bottom quartile",
         "meaning": "主要主张支持不足或方法问题重大（reject）"},
        {"score": 1, "percentile": "bottom",
         "meaning": "未达发表门槛或与目标刊无关（strong reject）"},
    ],
    "anti_inflation": "rebuttal 前多数稿 ≤5 分；非卓越原创不许给 7 分以上",
}

# 封顶规则模板（逐条登记：触发条件 / 封顶效应 / 出处）。
DEFAULT_CAPS = [
    {"cap_id": "CAP-01", "trigger": "open_confirmed_error",
     "effect": {"kind": "max_favorable", "band": "major_revision"},
     "description": "存在未裁决的法医 confirmed error 时，决定建议"
                    "不许比 major_revision 更有利",
     "source": "RV-14 硬门封顶 / R2 硬度 a"},
    {"cap_id": "CAP-02", "trigger": "unverified_facts_present",
     "effect": {"kind": "max_favorable", "band": "minor_revision"},
     "description": "按刊事实含 UNVERIFIED（过期/未核查）时，未核实"
                    "事实不许驱动定级：决定建议不许到 ready",
     "source": "RV-14 未核实不驱动定级 / RV-17"},
    {"cap_id": "CAP-03", "trigger": "clerical_only",
     "effect": {"kind": "min_favorable", "band": "minor_revision"},
     "description": "问题全为文书类（concern 全 minor 且无法医错误）时，"
                    "决定建议不许比 minor_revision 更不利（文书错误封顶）",
     "source": "RV-14 文书类错误一律 minor（reviewer2 C 型强制 minor）"},
]

# 不对称合成模板：reject 向权重 > accept 向（AI 评分通胀 +4.9pp 先验修正）。
DEFAULT_ASYMMETRY = {
    "reject_weight": 1.5,
    "accept_weight": 1.0,
    "note": "AI 分数不对称使用：模拟 reject/强负信号权重高于模拟 accept"
            "（评分通胀 +4.9pp 的先验修正，P04）；置信表达与人类自身 "
            "23% 分歧的天花板相称（P09）",
}


class CalibrationError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def default_calibration(journal: str | None = None) -> dict:
    """校准登记模板（init 落盘；改任何一处即配置漂移）。"""
    return {
        "version": "1.0",
        "journal": journal,
        "scale": dict(DEFAULT_SCALE),
        "caps": [dict(c) for c in DEFAULT_CAPS],
        "asymmetry": dict(DEFAULT_ASYMMETRY),
        "bench": {"report_ref": "reports/bench_report.json"},
    }


def init_calibration(root) -> dict:
    """落 calibration.yaml 模板（已存在则拒绝覆盖，配置只许显式改）。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise CalibrationError(["评审包不存在（先 init）"])
    if pkg["calibration"] is not None:
        raise CalibrationError(["calibration.yaml 已存在：配置只许显式"
                                "编辑文件（改即漂移，验证台须重跑）"])
    journal = ((review.get("intake") or {}).get("target_journal") or {}
               ).get("name")
    calibration = default_calibration(journal)
    save_calibration(root, calibration)
    review["calibration"] = {"initialized_at": today(), "journal": journal}
    review["updated_at"] = today()
    save_review(root, review)
    return calibration


def config_snapshot(root) -> dict | None:
    """评审配置快照（验证台绑定的对象）：席位集 + 量表 + 封顶 + 不对称。

    任一构成漂移 → config_hash 变 → 旧 bench 报表过期（RV-15）。
    calibration.yaml 缺失时返回 None（无配置可绑）。
    """
    pkg = load_package(root)
    calibration = pkg["calibration"]
    if calibration is None:
        return None
    seats = sorted(
        ({"seat_id": s.get("seat_id"), "role": s.get("role"),
          "model_family": s.get("model_family")}
         for s in (pkg["seats"] or {}).get("seats") or []),
        key=lambda r: r["seat_id"] or "")
    return {
        "seats": seats,
        "seats_spec": (pkg["review"].get("constraints") or {}).get("seats_spec"),
        "scale": calibration.get("scale"),
        "caps": calibration.get("caps"),
        "asymmetry": calibration.get("asymmetry"),
    }


def config_hash(root) -> str | None:
    snap = config_snapshot(root)
    return component_hash(snap) if snap is not None else None


def _check_scale(calibration) -> list:
    scale = (calibration or {}).get("scale") or {}
    gaps = []
    anchors = scale.get("anchors") or []
    if not anchors:
        gaps.append("量表锚缺失：scale.anchors 为空")
    else:
        for a in anchors:
            if a.get("score") is None or not a.get("percentile") \
                    or not a.get("meaning"):
                gaps.append(f"量表锚不完整（score/percentile/meaning "
                            f"须齐）：{a}")
    if not (scale.get("anti_inflation") or "").strip():
        gaps.append("量表缺反通胀口令（scale.anti_inflation）："
                    "百分位锚须与反通胀口令成文登记（RV-14）")
    return gaps


def _check_caps(calibration) -> list:
    caps = (calibration or {}).get("caps") or []
    gaps = []
    if not caps:
        gaps.append("封顶规则缺失：caps 为空（逐条登记触发/封顶/出处）")
    for cap in caps:
        cid = cap.get("cap_id") or "?"
        if cap.get("trigger") not in schema.CAP_TRIGGERS:
            gaps.append(f"封顶规则 {cid} 的 trigger "
                        f"{cap.get('trigger')!r} 不在触发词表")
        eff = cap.get("effect") or {}
        if eff.get("kind") not in schema.CAP_EFFECT_KINDS \
                or eff.get("band") not in schema.DECISION_BANDS:
            gaps.append(f"封顶规则 {cid} 的 effect 不完整或不在词表：{eff}")
        if not (cap.get("source") or "").strip():
            gaps.append(f"封顶规则 {cid} 缺出处（source）")
    return gaps


def _check_asymmetry(calibration) -> list:
    asym = (calibration or {}).get("asymmetry") or {}
    rw, aw = asym.get("reject_weight"), asym.get("accept_weight")
    if not isinstance(rw, (int, float)) or not isinstance(aw, (int, float)):
        return ["不对称合成权重未登记数值（reject_weight/accept_weight）"]
    if not rw > aw:
        return [f"不对称合成不成立：reject_weight {rw} 须大于 "
                f"accept_weight {aw}（AI 分数不对称使用，RV-14）"]
    return []


def assess_calibration(root) -> dict:
    """校准门四件齐备性评估（meta 决定 full/degraded 的唯一依据）。

    返回 {complete, missing, pieces}：missing 逐项点名缺件，降级时
    原样进登记头与 problem_list，不许含糊。
    """
    root = Path(root)
    pkg = load_package(root)
    calibration = pkg["calibration"]
    missing: list[str] = []
    pieces = {p: False for p in schema.CALIBRATION_PIECES}
    if calibration is None:
        return {"complete": False,
                "missing": ["calibration.yaml 缺失：校准门四件无从谈起"
                            "（先 calibration 初始化）"],
                "pieces": pieces, "bench": None}
    scale_gaps = _check_scale(calibration)
    pieces["scale_anchor"] = not scale_gaps
    missing += scale_gaps
    cap_gaps = _check_caps(calibration)
    pieces["caps"] = not cap_gaps
    missing += cap_gaps
    asym_gaps = _check_asymmetry(calibration)
    pieces["asymmetry"] = not asym_gaps
    missing += asym_gaps
    # 验证台报表：在册 + 配置哈希与当前配置一致（漂移即过期）
    bench = pkg["bench_report"]
    current_hash = config_hash(root)
    if bench is None:
        missing.append("验证台报表缺失：reports/bench_report.json 不在册"
                       "（先 bench）")
    elif bench.get("config_hash") != current_hash:
        missing.append("验证台报表过期：报表 config_hash 与当前评审配置"
                       "（席位集/量表/封顶/权重）不符，配置漂移须重跑 bench")
    else:
        pieces["bench_report"] = True
    return {"complete": not missing, "missing": missing,
            "pieces": pieces, "bench": bench}

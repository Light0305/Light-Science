"""样式编译（F1/F2，约束 4/14，草案 §1.3）：期刊合同 + 色板登记 →
可执行配置 bundle，落盘记 style_build_hash；绘图脚本只许消费编译产物。

编译产物（data/styles/）：
- bundle.json     规范记录（期刊数值 + 已解析色板 + rcParams + 尺寸推导
                  参数），style_build_hash = 其规范化哈希（不含时间戳，
                  同输入同哈希）；
- light.mplstyle  Python 侧文本产物（与 bundle 同源渲染）；
- theme.R         R 侧文本产物（ggplot2 theme + scale 定义，Phase 2
                  只产文本不执行 R）。

色板登记（消费口径，约束 4）：本模块内置 v1 登记表——条目带类型 /
感知均匀 / 色盲安全 / 灰度有序 / 许可 / 数据版本六列；期刊合同的色板
指针（entry_id + version）消费时逐项对表，版本漂移即报错（钉版本）。
数据出处：
- PAL-OI-8：Okabe & Ito (2002) 八色，学界通用值；
- PAL-BATLOW：Crameri batlow（数据版本 8.0，CC BY 4.0，DOI
  10.5281/zenodo.5503957 系），17 点采样 LUT——构建期经 cmcrameri
  1.10 读取官方数据采样落字，运行时不依赖该包。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import schema
from .project import load_package
from .util import component_hash, dump_json

BUNDLE_KIND = "light-figure/style-bundle"
STYLE_DIR = "data/styles"
DEFAULT_PANEL_ASPECT = 0.75  # 面板高/宽缺省（高宽比可经合同覆写带理由调整）

# ---------------------------------------------------------------- 色板登记表

PALETTE_REGISTRY = {
    "PAL-OI-8": {
        "entry_id": "PAL-OI-8",
        "version": "2002.1",
        "palette_type": "categorical",
        "perceptually_uniform": False,
        "colorblind_safe": True,
        "grayscale_ordered": False,
        "license": "public domain（Okabe & Ito 2002 通用色板）",
        "data_version": "Okabe-Ito 2002",
        "colors": [
            "#e69f00", "#56b4e9", "#009e73", "#f0e442",
            "#0072b2", "#d55e00", "#cc79a7", "#000000",
        ],
    },
    "PAL-BATLOW": {
        "entry_id": "PAL-BATLOW",
        "version": "8.0",
        "palette_type": "sequential",
        "perceptually_uniform": True,
        "colorblind_safe": True,
        "grayscale_ordered": True,
        "license": "CC BY 4.0（Fabio Crameri scientific colour maps）",
        "data_version": "8.0",
        "colors": [  # batlow 17 点采样 LUT（构建期实测采样，见模块头注）
            "#011959", "#0d315d", "#114360", "#175262", "#226061",
            "#356a59", "#4d734d", "#677b3e", "#828231", "#a18a2b",
            "#c09036", "#dd954d", "#f29d6d", "#fca993", "#fdb4b6",
            "#fcc0d8", "#faccfa",
        ],
    },
}

# 方法图角色色板（约束 7：色值按元素角色登记，提示词只引角色名）。
# hex 只活在本登记表与构建器侧，永不进提示词正文。
ROLE_PALETTE_REGISTRY = {
    "PAL-ROLE-METHOD": {
        "entry_id": "PAL-ROLE-METHOD",
        "version": "1.2",
        "roles": [
            {"role": "input_data", "hex": "#0072b2",
             "usage": "输入数据 / 原始素材"},
            {"role": "process", "hex": "#56b4e9",
             "usage": "中间处理 / 变换步骤"},
            {"role": "model_core", "hex": "#d55e00",
             "usage": "核心模型 / 主张承载模块"},
            {"role": "decision", "hex": "#e69f00",
             "usage": "判定 / 阈值 / 分支"},
            {"role": "output", "hex": "#009e73",
             "usage": "输出 / 结果"},
            {"role": "annotation", "hex": "#cc79a7",
             "usage": "注记 / 风险 / 边界情形"},
            {"role": "neutral", "hex": "#4d4d4d",
             "usage": "对照 / 背景结构"},
        ],
    },
}

# 面板推理角色 → 角色色板角色（提示词分区段的角色标注口径）
PANEL_ROLE_TO_PALETTE_ROLE = {
    "setup_schematic": "input_data",
    "representative_example": "input_data",
    "primary_quantitative_evidence": "model_core",
    "baseline_or_control": "neutral",
    "decomposition": "process",
    "stratification": "process",
    "orthogonal_validation": "decision",
    "perturbation_or_stress_test": "decision",
    "boundary_or_failure_case": "annotation",
    "mechanistic_evidence": "model_core",
}

SEQ_CMAP_NAME = "light_seq"


class StyleError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def role_palette(entry_id):
    return ROLE_PALETTE_REGISTRY.get(entry_id)


def role_hex(entry_id, role):
    """构建器侧按角色名取色值（提示词侧禁用本函数）。"""
    reg = ROLE_PALETTE_REGISTRY.get(entry_id) or {}
    for row in reg.get("roles") or []:
        if row["role"] == role:
            return row["hex"]
    return None


def _resolve_palette(ref, slot, gaps):
    """期刊合同色板指针 → 登记表条目（版本钉住，漂移报错）。"""
    if not isinstance(ref, dict) or not ref.get("entry_id"):
        gaps.append(f"期刊合同色板指针 palettes.{slot} 未登记"
                    "（样式编译须消费已登记色板，约束 4）")
        return None
    entry = PALETTE_REGISTRY.get(ref["entry_id"])
    if entry is None:
        gaps.append(f"色板条目 {ref['entry_id']} 不在 v1 登记表中"
                    "（姊妹仓登记表接入前只许消费内置登记条目）")
        return None
    if str(ref.get("version")) != str(entry["version"]):
        gaps.append(f"色板 {ref['entry_id']} 版本漂移：合同钉 "
                    f"{ref.get('version')}，登记表为 {entry['version']}"
                    "（消费时钉版本，漂移不许静默沿用）")
        return None
    expected_type = "categorical" if slot == "categorical" else None
    if expected_type and entry["palette_type"] != expected_type:
        gaps.append(f"色板 {ref['entry_id']} 类型为 "
                    f"{entry['palette_type']}，不许登记为分类色板槽"
                    "（分类与连续机制分开，约束 4）")
        return None
    if slot == "continuous" and entry["palette_type"] == "categorical":
        gaps.append(f"色板 {ref['entry_id']} 是分类色板，不许由连续"
                    "色图槽消费（约束 4）")
        return None
    return dict(entry)


def compile_bundle(journal_contract) -> dict:
    """期刊合同 → 样式 bundle（纯函数，同输入同输出同哈希）。"""
    jc = journal_contract or {}
    gaps = []
    if not jc.get("registered"):
        gaps.append("期刊合同未登记（registered=false）：骨架缺省值"
                    "不许编译成样式（约束 14：逐刊登记为准）")
    palettes = jc.get("palettes") or {}
    categorical = _resolve_palette(palettes.get("categorical"),
                                   "categorical", gaps)
    continuous = _resolve_palette(palettes.get("continuous"),
                                  "continuous", gaps)
    if gaps:
        raise StyleError(gaps)

    font = jc.get("font") or {}
    base_pt = float(font.get("max_pt") or schema.JOURNAL_ANCHORS["font_max_pt"])
    small_pt = float(max(font.get("min_pt") or 5.0, base_pt - 1.0))
    family = font.get("family") or "DejaVu Sans"
    columns = jc.get("columns_mm") or {}
    rcparams = {
        "font.family": family,
        "font.size": base_pt,
        "axes.titlesize": base_pt,
        "axes.labelsize": base_pt,
        "xtick.labelsize": small_pt,
        "ytick.labelsize": small_pt,
        "legend.fontsize": small_pt,
        "axes.prop_cycle_colors": categorical["colors"],
        "image.cmap": SEQ_CMAP_NAME,
        "pdf.fonttype": 42,          # 可编辑文本（未转曲），合同门据此判
        "svg.fonttype": "none",      # SVG 文本保持文本节点
        "ps.fonttype": 42,
        "savefig.dpi": 300,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
    bundle = {
        "kind": BUNDLE_KIND,
        "journal": jc.get("journal"),
        "journal_version": jc.get("version"),
        "columns_mm": {"single": columns.get("single"),
                       "double": columns.get("double")},
        "max_height_mm": jc.get("max_height_mm"),
        "font": {"family": family, "base_pt": base_pt,
                 "small_pt": small_pt,
                 "glyph_floor_pt": (jc.get("tolerances") or {}).get(
                     "glyph_floor_pt")},
        "palettes": {"categorical": categorical, "continuous": continuous},
        "rcparams": rcparams,
        "default_panel_aspect": DEFAULT_PANEL_ASPECT,
    }
    bundle["style_build_hash"] = component_hash(bundle)
    return bundle


def derive_figsize(bundle, column: str, rows: int, cols: int,
                    aspect: float | None = None) -> dict:
    """尺寸从栏宽确定性推导（约束 14：禁止逐图手填 figsize）。

    aspect 为面板高/宽（缺省 bundle 面板缺省值）；总高超期刊最大高时
    等比收缩并在结果中落字（adjusted=True），不许静默改尺寸。
    """
    columns = bundle["columns_mm"]
    if column not in columns or not columns[column]:
        raise StyleError([f"栏位 {column!r} 不在期刊合同栏宽登记中"])
    if rows < 1 or cols < 1:
        raise StyleError([f"面板行列数非法：rows={rows}, cols={cols}"])
    width_mm = float(columns[column])
    panel_w = width_mm / cols
    panel_h = panel_w * float(aspect or bundle["default_panel_aspect"])
    height_mm = panel_h * rows
    adjusted = False
    max_h = bundle.get("max_height_mm")
    if max_h and height_mm > float(max_h):
        factor = float(max_h) / height_mm
        width_mm *= factor
        height_mm *= factor
        adjusted = True
    return {
        "figsize_in": [round(width_mm / 25.4, 4), round(height_mm / 25.4, 4)],
        "width_mm": round(width_mm, 3),
        "height_mm": round(height_mm, 3),
        "column": column, "rows": rows, "cols": cols,
        "aspect": float(aspect or bundle["default_panel_aspect"]),
        "adjusted_to_max_height": adjusted,
    }


# ---------------------------------------------------------------- 文本产物

def render_mplstyle(bundle) -> str:
    rc = bundle["rcparams"]
    lines = [f"# light-figure compiled style（bundle "
             f"{bundle['style_build_hash'][:12]}…，期刊 "
             f"{bundle.get('journal')} {bundle.get('journal_version')}）"]
    for key in sorted(rc):
        value = rc[key]
        if key == "axes.prop_cycle_colors":
            colors = ", ".join(f"'{c}'" for c in value)
            lines.append(f"axes.prop_cycle: cycler('color', [{colors}])")
        elif isinstance(value, bool):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def render_r_theme(bundle) -> str:
    cat = bundle["palettes"]["categorical"]
    seq = bundle["palettes"]["continuous"]
    font = bundle["font"]
    cat_vec = ", ".join(f'"{c}"' for c in cat["colors"])
    seq_vec = ", ".join(f'"{c}"' for c in seq["colors"])
    return f"""# light-figure compiled theme（bundle {bundle['style_build_hash'][:12]}…）
# 期刊 {bundle.get('journal')} {bundle.get('journal_version')}；
# 分类色板 {cat['entry_id']}@{cat['version']}、连续色板 {seq['entry_id']}@{seq['version']}。
# 本文件为样式编译的文本产物：R 线脚本只许消费本文件，不许散写刊规数值。

light_figure_categorical <- c({cat_vec})
light_figure_sequential <- c({seq_vec})

theme_light_figure <- function() {{
  ggplot2::theme_minimal(base_size = {font['base_pt']},
                         base_family = "{font['family']}") +
    ggplot2::theme(
      axis.title = ggplot2::element_text(size = {font['base_pt']}),
      axis.text = ggplot2::element_text(size = {font['small_pt']}),
      legend.text = ggplot2::element_text(size = {font['small_pt']}),
      panel.grid.minor = ggplot2::element_blank())
}}

scale_color_light_figure_d <- function(...) {{
  ggplot2::scale_color_manual(values = light_figure_categorical, ...)
}}
scale_fill_light_figure_d <- function(...) {{
  ggplot2::scale_fill_manual(values = light_figure_categorical, ...)
}}
scale_color_light_figure_seq <- function(...) {{
  ggplot2::scale_color_gradientn(colours = light_figure_sequential, ...)
}}
"""


# ---------------------------------------------------------------- 落盘

def bundle_path(root):
    return Path(root) / STYLE_DIR / "bundle.json"


def build_style(root) -> dict:
    """编译并落盘三件产物，返回 bundle（含 style_build_hash）。"""
    root = Path(root)
    pkg = load_package(root)
    if pkg["head"] is None:
        raise StyleError(["图包不存在（先 init）"])
    bundle = compile_bundle(pkg["journal_contract"])
    out_dir = root / STYLE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_json(out_dir / "bundle.json", bundle)
    (out_dir / "light.mplstyle").write_text(
        render_mplstyle(bundle), encoding="utf-8")
    (out_dir / "theme.R").write_text(render_r_theme(bundle), encoding="utf-8")
    return bundle


def load_bundle(root) -> dict | None:
    path = bundle_path(root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def bundle_current(root) -> tuple[dict | None, str | None]:
    """(落盘 bundle, 问题)：bundle 缺失或与当前期刊合同重编译不一致时
    问题落字（样式漂移不许静默沿用）。"""
    root = Path(root)
    bundle = load_bundle(root)
    if bundle is None:
        return None, "样式 bundle 未编译：先跑 style build"
    pkg = load_package(root)
    try:
        fresh = compile_bundle(pkg["journal_contract"])
    except StyleError as e:
        return bundle, "期刊合同当前不可编译：" + "；".join(e.gaps)
    if fresh["style_build_hash"] != bundle["style_build_hash"]:
        return bundle, ("样式 bundle 与当前期刊合同不一致（哈希 "
                        f"{bundle['style_build_hash'][:12]}… ≠ 重编译 "
                        f"{fresh['style_build_hash'][:12]}…）：期刊合同已"
                        "变更，须重跑 style build")
    return bundle, None

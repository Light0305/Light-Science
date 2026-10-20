"""词表与规则表（权威定义层）。

本模块只放「口径」：状态机、图合同词表（原型/面板角色/证据层级）、
后端排他与 D2 的 R 启用条件、D3 的审计容差默认参数集（Yuan 参数）、
期刊合同数值锚、provenance 与姊妹仓接口字段。校验逻辑在 validate.py，
不许在此处散落第二份口径。

数值出处（LEARNING 约束 13/14）：
- 容差默认 = Yuan nature-skills 审计器实测参数（对齐脚本
  audit_panel_alignment.py 的 DEFAULT_TOLERANCE_PT = 1.5 pt 等），
  经拍板 D3 定为 v1 期刊合同参数：刊方更严从刊，放宽只许豁免登记。
- 期刊尺寸锚 = Nature Research Figure Guide 现行版（单栏 89 mm /
  双栏 183 mm / 最大高度 170 mm / 字号 5–7 pt）；逐刊登记以目标刊
  官方指南现行版为准，本表只作骨架缺省与量纲换算。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 状态机

STATES = ["intake", "contracted", "produced", "audited", "delivered"]

NEXT_STATE = {
    "intake": "contracted",
    "contracted": "produced",
    "produced": "audited",
    "audited": "delivered",
}

# ---------------------------------------------------------------- 承接与线别

# 承接条目 kind（草案 §1.1）：data / schematic / table
INTAKE_KINDS = ["data", "schematic", "table"]

# 图线（草案 §1.2）：line 由承接 kind 决定；table 归数据线登记
# （表格本体由 Write 承担，Figure 侧只登记其合同与交付指针）。
LINES = ["data", "schematic"]
KIND_TO_LINE = {"data": "data", "schematic": "schematic", "table": "data"}

# ---------------------------------------------------------------- 图合同

# 原型四分类（约束 1 / Yuan figure-contract）
ARCHETYPES = [
    "quantitative_grid",
    "schematic_led_composite",
    "image_plate_quant",
    "asymmetric_mixed_modality",
]

# 面板推理角色十类（约束 5：角色多样性 > 指标多样性）
PANEL_ROLES = [
    "setup_schematic",
    "representative_example",
    "primary_quantitative_evidence",
    "baseline_or_control",
    "decomposition",
    "stratification",
    "orthogonal_validation",
    "perturbation_or_stress_test",
    "boundary_or_failure_case",
    "mechanistic_evidence",
]

# 证据三层级（约束 1）
EVIDENCE_TIERS = ["hero", "validation", "controls_robustness"]

# 密度/简洁取舍（约束 7：两单方向相反，取舍须按图登记，不许默认）
DENSITY_STANCES = ["density_first", "simplicity_first"]

# ---------------------------------------------------------------- 后端（F1）

BACKENDS = ["python", "r"]

# 解析顺序五级的落盘来源词表（约束 2；草案 §1.3）
BACKEND_DECISION_SOURCES = [
    "explicit",        # ① 当前请求显式指定
    "input",           # ② 输入/工作流明显属某语言
    "task_default",    # ③ 本任务内已确立的选择
    "persisted",       # ④ 落盘偏好
    "asked",           # ⑤ 一次性提问后落定
]

DEFAULT_BACKEND = "python"  # 拍板 D2

# D2：R 启用条件（满足其一才许覆写为 R，且须逐图登记依据）
R_ENABLE_CONDITIONS = {
    "r_decisive_advantage": "图种在 R 侧有决定性优势（声明式组图/collect 收敛、ggplot 扩展专属图种）",
    "pipeline_in_r": "项目数据管线本身在 R 内（源数据与分析同语言）",
    "library_r_only": "目标刊/图种在数据图库中只有 R 侧样式/成例条目",
}

# ---------------------------------------------------------------- 期刊合同

MM_TO_PT = 72.0 / 25.4

# Nature Research Figure Guide 现行版硬数字（约束 14；仅作缺省锚，
# 逐刊登记以官方指南现行版 + 核查日期为准）
JOURNAL_ANCHORS = {
    "single_column_mm": 89.0,
    "double_column_mm": 183.0,
    "max_height_mm": 170.0,
    "font_min_pt": 5.0,
    "font_max_pt": 7.0,
    "glyph_floor_pt": 5.0,
}

KNOWN_EXPORT_FORMATS = ["pdf", "eps", "ai", "svg", "tiff", "png", "jpeg", "jpg"]

# ---------------------------------------------------------------- 容差（D3）

# 审计容差默认参数集（Yuan 参数，约束 13）。relax 指「比默认更宽松」的
# 方向：偏差类容差放宽 = 调大；字形地板是下限，放宽 = 调小。
# 刊方更严（收紧）不设限；放宽只许经 tolerance_exemptions 逐项登记。
TOLERANCE_PARAMS = {
    "alignment_pt": {
        "default": 1.5, "relax": "increase",
        "label": "面板对齐容差（plot-area 矩形量测，含 gutter）",
    },
    "collision_inset_pt": {
        "default": 0.6, "relax": "increase",
        "label": "碰撞审计文字框内缩",
    },
    "collision_min_overlap_ratio": {
        "default": 0.05, "relax": "increase",
        "label": "碰撞审计最小重叠比（占较小框）",
    },
    "collision_clip_pt": {
        "default": 0.5, "relax": "increase",
        "label": "碰撞审计出页裁剪容差",
    },
    "collision_background_exempt_ratio": {
        "default": 0.20, "relax": "increase",
        "label": "碰撞审计背景豁免面积比（填充/图像占页面比）",
    },
    "glyph_floor_pt": {
        "default": 5.0, "relax": "decrease",
        "label": "字形地板（最终 PDF 内容流 Tf 实测最小字号）",
    },
}


def tolerance_relaxed(param: str, value) -> bool:
    """value 是否比默认参数更宽松（放宽）。非数值不判（由数值校验报错）。"""
    spec = TOLERANCE_PARAMS.get(param)
    if spec is None or not isinstance(value, (int, float)) \
            or isinstance(value, bool):
        return False
    if spec["relax"] == "increase":
        return value > spec["default"]
    return value < spec["default"]


# ---------------------------------------------------------------- 色板登记

# 色板类型词表与登记六列（约束 4：类型/感知均匀/色盲安全/灰度有序/
# 许可/数据版本，必填且类型可断言；分类与连续机制分开）
PALETTE_TYPES = [
    "categorical", "sequential", "diverging", "multi_sequential", "cyclic",
]
PALETTE_REGISTRY_FIELDS = [
    "palette_type", "perceptually_uniform", "colorblind_safe",
    "grayscale_ordered", "license", "data_version",
]
BANNED_COLORMAPS = ["rainbow", "jet", "hsv"]  # 约束 4：彩虹色标禁用

# ---------------------------------------------------------------- 政策（F4/D1）

# AI 政策快照必填字段（与 Write 模板记录 AI 政策组同源，约束 8）
AI_POLICY_FIELDS = [
    "ai_images_prohibited",   # 是否禁止 AI 直接产出的图像物件
    "exhibit_exemption",      # 展示件（flow chart 等）豁免口径，无则 null
    "disclosure_required",    # 是否要求披露
    "source_url",             # 政策原文链接
    "verified_at",            # 核查日期（过期自动失效）
]
POLICY_REVIEW_CYCLE_DAYS = 180  # 缺省复核周期（与 Write 模板记录同口径）

# 方法图降级路径（约束 8：编辑否定/刊方从严时切无 AI 参考路径）
DEGRADATION_PATHS = ["normal", "no_ai_reference"]

# ---------------------------------------------------------------- 方法图后端（v1.1）

# 方法线原生后端（FIG-D02 裁决修订：Visio 主线 + PowerPoint 第二原生
# 后端）；数据图不归 PPT（演示图表无诚实门登记面）。
SCHEMATIC_BACKENDS = ["visio", "powerpoint"]
DEFAULT_SCHEMATIC_BACKEND = "visio"

# powerpoint_verified 口径（与 visio_verified 同构）：文件层构建
# （python-pptx + OPC 反读）只给 file_layer 证据，恒标 false；
# true 只许 COM 路线在 Windows + PowerPoint 实机原生导出验证后落。
PPTX_EVIDENCE_LEVELS = ["file_layer", "com_native"]

# ---------------------------------------------------------------- Visio 重绘（F5）

VISIO_ROUTES = ["com", "file_build"]  # 拍板 D4：COM 主路线 / 文件级第二路线

# ------------------------------------------------- manifest 三件（v1.1，FIG-D04/05/06）

# renderer-effective-fields 字段注册表：构建器（文件级 .vsdx 与
# python-pptx 两路）真实消费的字段全集。manifest 声明某字段
# effective=true 但不在本表 = 声明生效而构建器未消费（校验报错）；
# 形状使用本表外字段 = 写了不生效（校验报错）。字段以点路径登记
# （style.* 为形状 style 子键）。
RENDERER_CONSUMED_FIELDS = [
    "panel_id", "box_local", "text", "connect", "residue_id",
    "style.fill", "style.fill_role", "style.line", "style.line_role",
    "style.line_width_pt", "style.font_pt",
]

# arrow_plan 条目必填（FIG-D06：边事实绑定——每条边登记所绑定的
# 原图箭头事实，与逐标签核对并列成重绘核对清单）
ARROW_PLAN_FIELDS = ["arrow_plan_id", "from", "to", "fact"]

# manifest 严格模式分界：version >= 本值或已带 arrow_plan 键 →
# connect 必绑 arrow_plan；v1.0 存量 manifest 走兼容模式（迁移路径）。
MANIFEST_STRICT_VERSION = "1.1"

# 位图残留合法类别（约束 12：未登记者不许以位图形态出现在成品中）
BITMAP_RESIDUE_CLASSES = [
    "photo", "video_frame", "microscopy", "heatmap", "texture",
    "dense_evidence",
]

# ---------------------------------------------------------------- 审计（F6）

# 判决四态（约束 13；Phase 2 审计器消费，本期只定词表）
AUDIT_VERDICTS = [
    "PASS", "REVIEW_REQUIRED", "FIX_BEFORE_DELIVERY", "NOT_AUDITABLE",
]

# 审计门清单（草案 §1.7；Phase 2 实现，本期定名）
AUDIT_GATES = [
    "alignment",   # 对齐门（最终 PDF plot-area 量测）
    "collisions",  # 碰撞门（最终 PDF 几何）
    "glyph",       # 字形门（最终 PDF Tf 实测）
    "contract",    # 合同门（尺寸/格式/可编辑文本/色板合规）
    "native",      # 原生性门（方法图 .vsdx）
    "honesty",     # 诚实门（数据图，拍板 D6 分层硬度）
    "policy_block",  # 政策硬拦（参考图本体不入交付集，全线唯一政策硬拦）
]

# ---------------------------------------------------------------- 姊妹仓接口（F7）

# Figure 消费三库登记表，不直接翻仓文件（约束 16 / 草案 §四）
SISTER_LIBRARIES = ["method_gallery", "visio_components", "data_gallery"]

# ------------------------------------------------- 配色决定与参考拆解（v1.1）

# FIG-D08：配色决定来源三选一（期刊合同导出 / gallery 锚 / 用户指定）
PALETTE_DECISION_SOURCES = [
    "journal_contract", "gallery_anchor", "user_specified",
]

# FIG-D09：参考图六维拆解（academic-figure-generator Step 2 分析表
# 口径）。palette_hex 只供重绘阶段查表，不入提示词正文（正文不落
# hex 的既有纪律不变）。
REFERENCE_BREAKDOWN_DIMS = [
    "palette_hex",          # 配色（精确 hex 列表）
    "layout_flow",          # 布局流向
    "module_style",         # 模块样式
    "annotation_style",     # 标注方式
    "information_density",  # 信息密度
    "special_elements",     # 特殊元素
]

# ------------------------------------------------- Illustrator 精修段（v1.1，FIG-D03）

# 条件路线：宿主（正版 Illustrator，Win/Mac）可用才成立；缺宿主
# 回落 Visio/SVG 路并如实落字。readback 为 DOM 回读对账记录形态。
ILLUSTRATOR_REFINE_STATUSES = [
    "planned", "svg_checked", "in_refinement",
    "readback_recorded", "done",
]
ILLUSTRATOR_PREFLIGHT_ITEMS = [
    "rgb_mixed",        # RGB 混入 CMYK 工作流
    "broken_links",     # 断链置入图
    "low_res_images",   # 低分辨率置入图
    "white_overprint",  # 白色叠印
    "pdfx",             # PDF/X 合规
]

# ---------------------------------------------------------------- 逐图状态行

DELIVERY_STATUSES = ["pending", "delivered"]
AUDIT_FINALS = ["pending", "pass", "blocked"]

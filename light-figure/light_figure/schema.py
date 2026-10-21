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
# user_specified（2026-10-21 补丁）：用户按自身需求明确指定用 R——
# 指定本身即依据来源，但 reason 仍须落字说明（谁指定、为何指定），
# 无 reason 照样拦（validate 的 reason 强制不因本值豁免）。
R_ENABLE_CONDITIONS = {
    "r_decisive_advantage": "图种在 R 侧有决定性优势（声明式组图/collect 收敛、ggplot 扩展专属图种）",
    "pipeline_in_r": "项目数据管线本身在 R 内（源数据与分析同语言）",
    "library_r_only": "目标刊/图种在数据图库中只有 R 侧样式/成例条目",
    "user_specified": "用户明确指定用 R（按用户需求选 R 实现；仍须登记 reason 落字说明）",
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

# 方法线原生后端三路平权（用户 2026-10-21 裁决，推翻第二轮 FIG-D03
# 的 Illustrator 精修定位）：Visio / PowerPoint / Illustrator 三路均
# 为可对参考图做原生复刻的生产路线，合同 schematic_backend 逐图
# 分流、缺省 visio（存量兼容）；数据图不归三后端（数据图走代码线）。
SCHEMATIC_BACKENDS = ["visio", "powerpoint", "illustrator"]
DEFAULT_SCHEMATIC_BACKEND = "visio"

# powerpoint_verified 口径（与 visio_verified 同构）：文件层构建
# （python-pptx + OPC 反读）只给 file_layer 证据，恒标 false；
# true 只许 COM 路线在 Windows + PowerPoint 实机执行构建脚本 +
# export-to-verify 回读无差、且执行者经 com-verify 登记落字后落
# （登记纪律见 pptxbuild.register_com_verify 与构建单 J3）。
PPTX_EVIDENCE_LEVELS = ["file_layer", "com_native"]

# illustrator_verified 口径（三路同构）：ExtendScript 构建脚本生成
# 只给 script 证据，恒标 false；true 只许 DOM 枚举回读对账无差 +
# 回读带 Illustrator 应用名/版本 + 执行者经 ai extract --by 落字
# 后落（登记纪律见 aibuild.extract_ai 与构建单 J3）。
AI_EVIDENCE_LEVELS = ["script", "dom_readback"]

# Illustrator 语义 ID 钉扎落点（构建单 J1）：Illustrator 无
# ShapeSheet 对应物，取「对象 name = 语义 ID + PageItem.note 写
# 本标记 + 语义 ID」双写，DOM 枚举回读按 note 对账（ie3jp 以 note
# 锚定对象身份的实证形态）；与 Visio User 段、PPTX name+descr
# 构成三路等价钉扎。
AI_USER_ID_MARKER = "light-figure:user-id="
AI_ARROW_MARKER = "light-figure:arrow="

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

# ------------------------------------------------- 提示词多版变体（2026-10-21 补丁）

# 方法图提示词多版并行：同一图库三元组与角色色板之下，变体只在
# 构图 / 密度 / 布局流向三维上区分（三维口径与合同 density_stance、
# 六维拆解的 layout_flow / information_density 同源），供用户按项目与
# 论文实情选版。每版独立文件 schematic/prompts/<fig_id>.<variant>.md、
# 六段完整、既有纪律（正文无 hex / 标签度量拦截 / 配色确认门）逐版
# 适用、独立 version 迭代与归档。变体集合与 selected_variant 登记于
# 合同 prompt_variants 与 provenance 账面；参考图登记/验收须指明所据
# 变体且与选定一致，未选定不许进登记/验收。
PROMPT_VARIANTS = {
    "compact": {
        "label": "紧凑型",
        "composition": "单行主流向紧凑排布：模块沿主数据流首尾相接，"
                       "次级模块挂主干侧枝，面板间距压到最小",
        "density": "高密度：每框一概念、箭头带语义标签，信息在图内自包含",
        "layout_flow": "左入右出水平流（输入在左、产出在右）",
        "extra_negative": "不许为紧凑把标签缩到不可读或把模块框叠放",
    },
    "spacious": {
        "label": "舒展型",
        "composition": "宽松网格排布：核心模块居中放大，次级模块四周"
                       "留白分隔，一眼先读主干",
        "density": "低密度：只画核心模块与主干箭头，次要细节移入图注",
        "layout_flow": "左入右出水平流（分段推进，段间留白）",
        "extra_negative": "不许以留白为名省略元素清单内的模块"
                          "（留白是间距，不是删减）",
    },
    "layered": {
        "label": "分层型",
        "composition": "自上而下分层排布：按处理层级横向成带，同层"
                       "模块并排，层间以纵向箭头连接",
        "density": "中密度：按层递进展开细节，上层概括、下层展开",
        "layout_flow": "自上而下纵向流（顶层输入、底层产出）",
        "extra_negative": "不许跨层回指箭头绕行或斜穿其他层"
                          "（回指走层侧通道）",
    },
}

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

# --------------------------------------- Illustrator 路线（FIG-D03 已被推翻）

# 第二轮 FIG-D03 曾把 Illustrator 写死为精修路线，用户 2026-10-21
# 裁决推翻：Illustrator 是第三条生产路线（见 SCHEMATIC_BACKENDS）。
# 本段两组词表分工：
# - ILLUSTRATOR_REFINE_STATUSES：合同 illustrator_refinement 段的
#   存量校验词表（v1.1 落地，其他后端的印前登记仍可引用），保留
#   兼容不删；它不再是 Illustrator 的路线身份。
# - ILLUSTRATOR_PREFLIGHT_ITEMS：印前五项，现为 Illustrator 生产
#   路线的交付前终检段——由 DOM 回读事实机械计算、落 ai manifest
#   的 preflight 段（构建单 J4），true = 检出问题、须处置。
ILLUSTRATOR_REFINE_STATUSES = [
    "planned", "svg_checked", "in_refinement",
    "readback_recorded", "done",
]
ILLUSTRATOR_PREFLIGHT_ITEMS = [
    "rgb_mixed",        # RGB 混入 CMYK 工作流
    "broken_links",     # 断链置入图
    "low_res_images",   # 低分辨率置入图（有效 ppi 低于地板）
    "white_overprint",  # 白色叠印
    "pdfx",             # PDF/X 合规（导出面不可用/不合规）
]

# Illustrator 回读置入图有效分辨率地板（与 recheck 的位图分辨率
# 口径同源：期刊位图有效分辨率下限）
AI_PLACED_PPI_FLOOR = 200

# ---------------------------------------------------------------- 逐图状态行

DELIVERY_STATUSES = ["pending", "delivered"]
AUDIT_FINALS = ["pending", "pass", "blocked"]

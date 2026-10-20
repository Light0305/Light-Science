---
prompt_id: fig-2-prompt
fig_id: fig-2
version: 1
gallery:
  entry_id: MG-DEMO-SEED-001
  version: '0.1'
  style_anchor: anchor-pipeline-flow
  bound_prompt_version: '1'
style_rules:
  id: anchor-pipeline-flow
  version: '0.1'
role_palette:
  entry_id: PAL-ROLE-METHOD
  version: '1.2'
palette_confirmation:
  confirmed_by: demo-author
  confirmed_at: '2026-10-20'
policy_snapshot_ref: figure.yaml#ai_policy_snapshot
generated_at: '2026-10-20'
generator: light-figure prompt build
---

# 提示词 · fig-2（v1）

## 1 全局

- 核心结论：方法以视频级统计量预测逐轨迹阈值，全程无需逐视频人工调参。
- 本图回答的问题：读者能否一段内复述检测—跟踪—预测—判定流水线？
- 图型（原型）：schematic_led_composite
- 风格锚：anchor-pipeline-flow
- 阅读顺序：面板 a → 面板 b
- 画面定位：投稿级科学示意图的构图草稿（内部参考），平涂矢量风、无照片质感。

## 2 分区

### 面板 a（推理角色：setup_schematic；证据层级：hero）

- 内容：棚舍视频输入与多目标跟踪轨迹
- 主色角色：input_data（只引角色名，色值见登记表）
- 子内容：按内容逐项画成带标签的子模块，不许留空白占位框。

### 面板 b（推理角色：mechanistic_evidence；证据层级：validation）

- 内容：视频级统计量 → 阈值预测 → 逐轨迹应用 → 异常标记
- 主色角色：model_core（只引角色名，色值见登记表）
- 子内容：按内容逐项画成带标签的子模块，不许留空白占位框。

## 3 全局标注

确切标签清单（逐字使用，不许改写、增删或意译）：

- 「棚舍视频输入与多目标跟踪轨迹」
- 「视频级统计量 → 阈值预测 → 逐轨迹应用 → 异常标记」

- 维度与公式标注：只许使用标签清单与合同中出现的符号，不许自创符号体系。
- 非渲染约束声明：本文件其他段落中的一切度量数字（尺寸、字号、百分比等）仅为排版约束，**不得绘入图中**；只有语义数字（步骤号、张量形状、轴刻度）可入图。

## 4 风格规格

- 角色色板：PAL-ROLE-METHOD@1.2（已过配色确认门：demo-author @ 2026-10-20）
- 角色清单（正文只引角色名，色值由重绘阶段查登记表）：
  - input_data：输入数据 / 原始素材
  - process：中间处理 / 变换步骤
  - model_core：核心模型 / 主张承载模块
  - decision：判定 / 阈值 / 分支
  - output：输出 / 结果
  - annotation：注记 / 风险 / 边界情形
  - neutral：对照 / 背景结构
- 线条与形态：统一描边粗细层级（主干 > 支线 > 注记），圆角矩形表处理模块、直角矩形表数据块、菱形表判定。
- 密度取舍：density_first（方法图须自包含复述全部模块与数据流）

## 5 负面约束

- 不许出现伪文字、乱码字符与无意义公式符号
- 不许出现空白占位框：每个模块框必须有子内容
- 不许用省略号（… / ...）代替内容
- 不许出现元素清单之外的模块、箭头或图层
- 不许照片式渲染、3D 立体效果与投影阴影
- 不许使用彩虹色标与高饱和荧光色
- 密度优先但每个模块框仍须有子内容，不许以密度为名堆叠无标签装饰元素

## 6 政策段

- 用途定位：本提示词的产物是**内部参考草稿**（构图与风格参考），不作投稿物件；成品由 Visio 原生重绘（拍板 D1：重绘成品无 AI 生成像素）。
- 目标刊 AI 政策快照：ai_images_prohibited=True、disclosure_required=True（verified_at=2026-10-20，原文：https://example.org/ai-policy-demo-fixture）
- 硬拦：参考图本体文件不得进入交付/投稿包（policy_block 门按哈希机械执行）。
- 参考图验收（约束 9，入包前逐项执行）：逐个标签逐字对原文核对 / 每个结构对领域事实核对 / 公式、分子式、数值逐个算对——照描而不核事实是红项。

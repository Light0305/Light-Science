# light-figure

承接 light-write 图表清单的图包工具：**图合同先行、双线生成、审计与账目先行登记**。每张图先落五点合同再动手：数据图走代码线（Python 默认 / R 条件启用），方法图走「图库匹配 → GPT Image 提示词 → 用户供参考图 → Visio 原生重绘」线；交付只产 `delivery.yaml` 供 Write 回填对账。

当前版本：**v1.1（第二轮升级）+ 2026-10-21 复刻三路平权补丁**。v1.0 全部能力保留：图包数据模型与确定性校验器、样式编译、双线生产（数据图 matplotlib 执行 / 方法图提示词→参考图登记验收→文件级 .vsdx 重绘）、provenance append-only 一本账、审计引擎七门、五段状态机全门（含 delivered 交付段：`delivery.yaml` 生成 + 账行逐行复验 + 编号冻结配合）；端到端双线演示走完 intake → contracted → produced → audited → delivered（`examples/demo-fullrun/`）。v1.1 新增：PowerPoint 文件层生产路线、manifest 三件（语义 ID 钉扎 / 生效字段对账 / 箭头计划 + 无效轮次门）、合同调色板决定、图库六维拆解、交付前本地复核、Illustrator 精修入口（SVG 桥）、交付对应件清单。**平权补丁（用户裁决推翻 FIG-D03）**：方法图复刻三路对等——合同 `schematic_backend` 扩为 visio / powerpoint / illustrator 三值、共用同一 redraw manifest 契约；PowerPoint COM 升为实现形态（manifest 生成 COM 构建脚本 + export-to-verify + `com-verify` 登记对账）；Illustrator 升为第三条生产路线（manifest 生成 ExtendScript 构建/回读脚本、DOM 枚举回读对账、印前五项降为交付前终检、SVG 桥降为导入备选）；门/审计/复核/交付三后端分流，verified 三路同纪律（只认实机证据登记）。**工具层 T2 补丁（2026-10-21）**：vsdx 0.6.1 vendored 进包 + `redraw post` 后处理命令组；ai manifest 构建账按后端隔离（派生剥离外来 rounds/build 并留痕）。

## 能力

- **图包数据模型**：`figure.yaml` 登记头（承接快照 + 目标期刊区 + 逐图状态表）、`contracts/<fig_id>.yaml` 逐图五点合同（核心结论 / 证据链面板 map + 推理角色词表 / 原型四分类 / 后端 / 期刊导出合同 + 密度取舍 + 审稿风险 + 数据排除登记）、`backend.json` 后端登记、`journal_contract.yaml` 期刊图形合同、`provenance.yaml` 一本账。
- **承接（intake）**：消费 Write `figures_manifest.yaml` 或独立立项清单，落源文件哈希 + 条目快照（上游变动即承接失效）；同时开立逐图状态行、合同骨架与 provenance 账行；期刊合同登记时先过数值校验、AI 政策快照缺项逐项点名。
- **校验器**：合同五点缺项逐项报错；后端排他（同图双后端冲突拦截、R 覆写须带拍板 D2 条件依据、方法图不许登记绘图后端）；期刊合同数值合法性（栏宽/字号为正、格式白名单、色板指针完整）；容差纪律（照 Yuan 参数为默认，放宽只许逐项豁免登记、私自放宽报错、字形地板调低同罪）；provenance 必填（produced 段起 method 图缺参考图哈希或重绘源即报错）；承接快照漂移检出；姊妹仓三元组引用完整性。
- **状态机**：`intake → contracted → produced → audited → delivered`，五段门全实现、缺口逐项点名，delivered 门复验 delivery 清单与账行（见交付条）。
- **样式编译**（`style build`）：期刊合同 + 色板登记表（Okabe-Ito 八色 / Crameri batlow 实测采样 LUT / 方法图角色色板）→ `data/styles/{bundle.json, light.mplstyle, theme.R}`，记确定性 `style_build_hash`；色板版本漂移、未登记期刊、分类/连续串位一律报错。尺寸由栏宽 + 行列确定性推导，超最大高同比收缩并落标记。
- **数据图生产**（`produce`）：脚本头登记块（样式哈希 / 面板 / 坐标轴口径 / 宽高比 / 面积编码 / 色板）源级预检（禁用彩虹色标、脚本自带 figsize、登记缺项逐项落 gap）→ matplotlib 执行 → 最终 PDF + 300 dpi 预览 + plot-area 量测清单，并回填账面（运行时版本、脚本/源数据/样式哈希）。后端非 Python 或未决定时如实停住不兜底。
- **提示词产物**（`prompt build`）：六段结构（全局 / 分区 / 全局标注 / 风格规格 / 负面约束 / 政策段）+ YAML 文件头登记（图库三元组引用、风格规则、角色色板指针、配色确认、政策快照指针）；正文只引角色名不落 hex，标签含度量字面量生成前拦截；改版递增 version 并归档旧版。`--variants compact,spacious,layered` 可在同一三元组与色板下并行产多版变体（只在构图/密度/布局流向三维区分，各自独立文件与 version），`prompt select` 选定后参考图登记/验收须指明所据变体且与选定一致。
- **参考图登记与验收**（`reference add/accept`）：入包复制 + SHA-256 钉账 + 生成模型同账登记（重复登记拒绝，防静默换图）；验收三项清单（逐标签逐字 / 逐结构对事实 / 公式数值算对）须核对人逐项落字。
- **重绘 manifest 与文件级构建**（`redraw init/install/build/extract`）：manifest 单一真相源（面板四角标定、逐形状局部坐标/文本/样式角色/连接语义、位图残留预声明六类）；文件级路线手写 OPC 从零构建 .vsdx（确定性打包），构建后反抽形状清单与 manifest 对账（容差 0.02 in），`visio_verified: false` 如实落字；COM 路线只立规程、调用即落 gap。v1.1 manifest 三件：构建出的形状写入 ShapeSheet User 段语义 ID（`User.SemanticId` 等），extract 回读逐个核对；`renderer_effective_fields` 声明与渲染实际消费逐项对账（声明了没生效点名）；v1.1 起箭头先行登记 `arrow_plan` 并逐条绑定 connect，内容零变化的重复构建被 round_noop 门拒绝（轮次账 `rounds` 落盘；轮次账按后端隔离，跨路线派生不继承——见 ai 线的 `derived_from` 留痕）。文件级构建的成品另有后处理格：`redraw post` 命令组（vendored vsdx 0.6.1：抽取/改字/改色/diff，不承担重建；变更写回后强制 extract 对账并落 `post_processing` 账）。
- **PowerPoint 路线**（`pptx init/install/build/extract` + `com-script/com-verify`）：合同 `schematic_backend: visio | powerpoint | illustrator` 逐图分流；文件层由 python-pptx 从同构 manifest 生成原生形状 .pptx（幻灯片尺寸 = 图尺寸、一页一图），对象语义 ID 双写（形状名 + descr 标记），反抽对账与原生性审计（OPC 口径）齐备，产物恒标 `powerpoint_verified: false`（文件层证据级）。COM 路线为实现形态（平权补丁）：manifest 生成 PowerShell + COM 构建脚本（COM 直建形状、真连接器绑定、导出 PNG/PDF 做 export-to-verify、枚举写 JSON），`pptx com-verify` 登记对账后才许 `com_route.powerpoint_verified` 置真；COM 产物 .pptx 落回标准路径续走文件层 extract。
- **Illustrator 生产路线**（`ai init/install/build/extract`，平权补丁）：与另两路同一 manifest 契约；`ai build` 生成 ExtendScript 构建脚本（驱动 DOM 从零重建原生对象：路径/区域文本框/连接线与箭头头/登记残留置入项，语义 ID 以对象名 + `PageItem.note` 标记双写钉扎）与回读脚本（DOM 枚举：对象/逐字文本/锚点几何/置入项/印前事实）；`ai extract` 登记回读并逐项对账，印前五项由回读事实机械计算为交付前终检；证据级 script → dom_readback 两档，`illustrator_verified` 只认合格登记（对账 ok + 应用版本 + 执行者落字 + .ai 存回）。
- **合同调色板决定**（v1.1）：两线合同落 `palette_decision`（来源三值词表 journal_contract / gallery_anchor / user_specified + 依据 + 确认人/时点），缺失过不了 contracted 门；数据图 produce 把决定快照落账、审计与复核核对实际用色。
- **图库六维拆解**（v1.1）：方法图引用图库条目时合同落 `reference_breakdown` 六维（palette_hex / layout_flow / module_style / annotation_style / information_density / special_elements），提示词风格段消费五个文字维，palette_hex 只以指针出现不进正文。
- **交付前本地复核**（`recheck [--fig] [--panels]`，v1.1）：纯本地机械复核最终产物——尺寸（vs 栏宽/画布标定）、字体真嵌入（FontDescriptor 判据）、实际用色 vs 调色板决定、位图有效分辨率、语义 ID 齐备、media vs 残留登记；结论落 `audit/<fig>.recheck.json` 并声明量测口径（文件层结构量测），只产 findings 不改审计判决。
- **SVG 桥（导入备选）**：`svg-check` 对导入 Illustrator 的 SVG 做受限子集校验（只许纯矢量基元，image/script/filter/外链一律拒绝）并抽出全文文本清单作丢字对账基准（SVG 导入会静默丢字形）；合同 `illustrator_refinement` 段为 FIG-D03 遗留兼容，新图不许再以它代替生产路线登记。
- **交付对应件清单**（v1.1）：`delivery.yaml` 逐图带 `correspondence`——源资产（路径 + SHA-256，参考图本体只给哈希不进交付集）到交付文件的映射 + 内容级哈希（对齐面板组件哈希 / 反抽形状集哈希），可按实物逐项复算。
- **provenance 更新命令**（`provenance set/show`）：append-only——旧行哈希入 history 的 supersedes 链、逐字段 from→to 留痕，哈希字段强制 SHA-256 格式。
- **审计引擎**（`audit run` / `audit-status` / `audit note`）：七门在最终产物上实测——对齐（量测清单 vs 容差 1.5 pt）/ 碰撞（PyMuPDF 抽取：文字重叠比 0.05、细描边穿字、出页 0.5 pt、背景豁免 20%）/ 字形（内容流 Tf 实测 vs 地板）/ 合同（尺寸、格式白名单、色板合规；方法图查路线口径）/ 原生性（解 .vsdx：media 清单 + 形状计数，整图嵌入与未登记位图 FAIL）/ 诚实（反转轴阻断、数据被裁未声明阻断、宽高比与面积编码登记 + 警告）/ 政策硬拦（交付集任一文件哈希 == 参考图哈希即 FAIL）。判决四态 PASS / REVIEW_REQUIRED / FIX_BEFORE_DELIVERY / NOT_AUDITABLE；审计绑产物哈希，改动即 STALE；REVIEW 门须 `audit note` 落处置理由才许过 audited 门。
- **交付**（`deliver` / `deliver --unfreeze --reason`）：audited 段生成 `exports/delivery.yaml`——逐图交付文件与哈希（按实物重算）、图注哈希、provenance 汇总与 AI 披露素材、方法图 `visio_verified` 标记；生成前逐行复验 provenance 账（账面哈希按实物重算，不符即拒交付）；首次交付同步冻结编号，冻结后改图须先登记解冻（旧清单标 superseded 不删），重新交付版本递增并重新冻结。
- **报告**：`report` 生成 `FIGURE_REPORT.md`（逐图状态 / 容差与豁免 / provenance 账面 / 校验结论），手工区保留不覆盖（同 light-design 体例）。

## 快速开始

```bash
pip install -e .
light-figure init ./my-figures --title "My Paper Figures"
light-figure intake ./my-figures --manifest ../my-manuscript/figures_manifest.yaml \
    --journal-contract journal_contract.yaml --ai-policy ai_policy.yaml
# 补齐 contracts/*.yaml 五点合同、backend.json 后端决定后：
light-figure validate ./my-figures
light-figure advance ./my-figures   # → contracted
light-figure style build ./my-figures
# 数据图：写 data/scripts/<fig>.py（带登记头）+ 源数据后
light-figure produce ./my-figures fig-1
# 方法图：提示词 → 参考图 → 验收 → manifest → 构建 → 反抽对账
light-figure prompt build ./my-figures fig-2
light-figure reference add ./my-figures fig-2 --image ref.png --model-name "GPT Image"
light-figure reference accept ./my-figures fig-2 --by author \
    --labels-verbatim --structures-factual --formulas-values-checked
light-figure redraw init ./my-figures fig-2   # 补齐标定后 install
light-figure redraw install ./my-figures fig-2 --manifest manifest.json
light-figure redraw build ./my-figures fig-2
light-figure redraw extract ./my-figures fig-2
# 文件级后处理（vendored vsdx 0.6.1，不承担重建；变更写回后强制 extract 对账）：
# light-figure redraw post text ./my-figures fig-2 --find "旧标签" --replace "新标签" --by author
# light-figure redraw post fill ./my-figures fig-2 --shape predictor --fill "#d55e00"
# light-figure redraw post extract ./my-figures fig-2   # 抽取形状清单
# light-figure redraw post diff ./my-figures fig-2 --other base.vsdx
# 方法图也可走 PowerPoint（合同 schematic_backend: powerpoint 时，文件层或 COM 实现形态）：
# light-figure pptx install/build/extract ./my-figures fig-2
# light-figure pptx com-script ./my-figures fig-2   # 生成 COM 构建脚本，Windows + PowerPoint 实机执行后：
# light-figure pptx com-verify ./my-figures fig-2 --record schematic/redraw/fig-2.com-verify.json --by author
# 方法图也可走 Illustrator 生产路线（合同 schematic_backend: illustrator 时）：
# light-figure ai install/build ./my-figures fig-2  # 生成 ExtendScript 构建/回读脚本，Illustrator 实机依次执行后：
# light-figure ai extract ./my-figures fig-2 --readback schematic/redraw/fig-2.dom-readback.json --by author
light-figure advance ./my-figures   # → produced
light-figure recheck ./my-figures   # 交付前本地复核（纯本地机械复核）
light-figure audit run ./my-figures
light-figure audit note ./my-figures fig-1 --gate collisions --reason "已复核可接受"
light-figure advance ./my-figures   # → audited
light-figure deliver ./my-figures    # 生成 delivery.yaml 并冻结编号
light-figure advance ./my-figures   # → delivered
light-figure report ./my-figures     # 刷新 FIGURE_REPORT.md
```

## 设计依据

- `../07-figure/REDESIGN-DRAFT.md`：图包草案 + 用户拍板 D1–D7（政策门一硬拦一本账一次核对 / 默认 Python + R 三条件 / 容差照 Yuan 参数 / Visio 双路线 / 图库三元组 / 诚实审计分层 / 姊妹仓后置）
- `../07-figure/LEARNING.md`：16 条硬约束（图合同先行、后端排他三件套、定量图代码分流、色板双类登记、提示词结构化、政策立场与三问核查、provenance 一本账、manifest 单一真相源、最终产物实测审计、导出合同硬数字、数据诚实四项、姊妹仓登记纪律）；SKILL §15 有逐条对应表

## 测试

```bash
python -m pytest   # 201 项（见 tests/）
```

依赖：`pyyaml` + `PyMuPDF`（最终 PDF 实测审计：文字/描边/图像抽取与内容流字号量测、嵌入位图真实像素尺寸）+ `matplotlib`（默认 Python 数据图执行后端）+ `python-pptx`（PowerPoint 文件层生成与反读）。R 侧只产 theme 文本产物、不执行。

## 已知局限

1. **COM 路线未在 Windows + Visio 实机验证**：只立规程与接口，`redraw build` 对 route=com 调用即如实落 gap；文件级构建产物恒标 `visio_verified: false`，Visio 实机打开校验留待有 Windows + Visio 的环境补。
2. **R 线只产 theme.R 不执行**：后端登记为 R 的图只得到样式文本产物，produce 如实停住不跨后端兜底（拍板 D2）；R 的启用条件判定（四值：含 2026-10-21 补设的 user_specified，用户指定也须登记 reason 落字）在登记层做，不在本工具内跑 R。
3. **文件级 .vsdx 与 Visio 原生渲染有差异**：几何走多段线近似、无 Visio/LibreOffice 渲染回验，真机打开后的像素级一致性未验证，交付按未验证口径标注。
4. **演示参考图是程序绘制的替身**：demo-fullrun 的参考图由本地 PIL 程序绘制充当「用户提供参考图」，生成模型登记如实写作 stand-in，非 GPT Image 产物（见 `examples/demo-fullrun/demo-report.md` 披露清单）。
5. **对齐门依赖同源量测清单**：非本工具 produce 生成的 PDF 没有量测清单，对齐门如实落 NOT_AUDITABLE，不许声称对齐通过。
6. **政策核对的有效性依赖登记的快照**：Figure 只消费 intake 时登记的 AI 政策快照与 Write 模板记录，期刊改政策后须重新核对登记，工具不自动追踪政策更新。
7. **编号冻结是包级粒度**：整包一次冻结，不支持逐图分批冻结或逐图先行交付。
8. **碰撞门不判语义可读性**：文字与填充边沿的部分重叠只落 WARN 待人工处置，机器不判断「还能读清」。
9. **期刊合同骨架值不是登记值**：init 生成的 `journal_contract.yaml` 带 Nature 缺省锚 + `registered: false`，必须按目标刊官方指南现行版逐项登记后才可过 contracted 门。
10. **PowerPoint COM 与 Illustrator 实机未验证**（平权补丁后口径）：两条实机路线已升为实现形态——COM 构建脚本（PowerShell + COM）与 ExtendScript 构建/回读脚本均由 manifest 确定性生成、登记对账契约齐备并有文本级与夹具级测试；但实机执行需 Windows + PowerPoint / macOS 或 Windows + Illustrator 环境，本机没有，两路的 verified 在用户机器实机跑通并登记对账前恒 false，gap 已分别登记在 manifest 的 `com_route` 段与 ai 构建记录中（SKILL §16.3/§16.4），不许以脚本已生成冒充实机已验。
11. **本地复核是文件层结构量测**：recheck 量的是文件结构（尺寸登记/字体嵌入标记/用色采样/ID 与 media 清单），不是渲染像素量测；像素级一致性仍需实机打开或渲染回验。
12. **manifest 严格模式只向前**：arrow_plan/effective-fields 的严格对账只对 v1.1+ manifest（或已落 arrow_plan 的清单）生效，v1.0 格式清单宽容读、不追溯补登记。

## 封版记录

- **工具层 T2 补丁（2026-10-21）**：vsdx 后处理库 vendored 化——dave-howard/vsdx 0.6.1（BSD 3-Clause）逐字节收编进 `light_figure/vendor/vsdx/`（许可全文与逐文件 SHA-256 在该目录 LICENSE 与 VENDOR.md，版本钉死），新 `redraw post` 命令组（extract 抽取 / text 改字 / fill 改色 / diff 比对）接上 manifest 后处理环节：写前备份、临时目录副本操作、写回后落 `post_processing` 账并强制重跑 extract 对账、provenance 哈希与修正日志指针同步刷新。ai manifest 构建账按后端隔离（user-delegated 主会话裁决 2026-10-21）：从 visio/powerpoint manifest 派生时内容继承、外来 rounds/build 剥离归零并在 `derived_from` 留痕，round_noop 只在本路线账内生效——修复工具规划 P5 实测的「继承 file_build 账导致首轮 ai build 被误拦」。新增测试 13 项（201 项全过，基线 188 零变红）。发布树同步另行封版。
- **复刻三路平权补丁（2026-10-21，用户裁决推翻 FIG-D03）**：合同后端集扩为三值且三路共用同一 manifest 契约与语义 ID 纪律（Illustrator 以对象名 + note 标记 + DOM 回读实现等价钉扎）；PowerPoint COM 由只立规程升为实现形态（`pptx com-script` 生成 COM 构建脚本 + export-to-verify，`pptx com-verify` 登记枚举/导出对账，verified 置真三件套）；Illustrator 升为第三条生产路线（`ai` 命令族：ExtendScript 从零重建 + DOM 枚举回读审计 + 印前五项终检段，SVG 桥降为导入备选）；produced 门、合同门、原生性门、recheck、delivery 全部补 illustrator 分流（三后端对称，参考图位图混入照旧硬拦）。新增测试 14 项（188 项全过，基线 174 零变红；含一条既有测试的样本值调整：后端词表测试的非法样本由 illustrator 改为 photoshop，断言不变）。COM 与 Illustrator 实机执行仍为用户机器 gap，如实登记未验。
- **v1.1（2026-10-21，第二轮拍板 FIG-D02–D11）**：PowerPoint 文件层全链（合同后端分流 + pptx manifest/build/extract + OPC 原生性审计 + `powerpoint_verified: false` 口径）；manifest 三件（User.* 语义 ID 钉扎、renderer-effective-fields 对账、arrow_plan + round_noop 门）；合同 `palette_decision` 与图库六维拆解入提示词；交付前本地复核 `recheck`；Illustrator 精修的 SVG 桥受限子集校验 + 合同回读段；政策口径修订条文落字（AI 参考图经原生重绘的成品不算 AI 生图：只拦参考图本体、provenance 留痕、逐刊按当期指南原文核对）；交付 `correspondence` 对应件清单（REV-D09 同批）。演示复跑至 delivered：双图七门 PASS、recheck 双 PASS，新增 round-noop 与 pptx-chain 两变体（后者三门 PASS 后塞整页图片被 native 拦下）。测试 151 项（v1.0 的 116 项零变红 + 新增 35 项）。COM（Visio/PowerPoint）与 Illustrator 实机项为环境依赖 gap，如实登记未验。
- **v1.0（2026-10-20）**：五段状态机全门落地；双线端到端演示（`examples/demo-fullrun/`）走完 delivered，七门审计全 PASS，两个拦截变体（反转轴、整图嵌入）均被对应门拦下且不进交付。演示期间变体抓出并修复一个真实缺陷：原生性门的嵌入位图尺寸量测曾用图像文档点数冒充像素数（无 DPI 元数据时漏检整幅嵌入），已改用真实像素尺寸并加回归测试。测试 116 项（工作树与干净导出树双跑）。姊妹仓（数据图库 / 组件库 / 方法图库）按拍板 D7 在本封版后另行启动，本包只定接口。

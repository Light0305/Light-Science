# demo-fullrun 演示报告（light-figure v1.0）

## 1. 终点与全链

图包 `turkey-behaviour-figures-light-figure-de_1b4072` 走完
**intake → contracted → produced → audited → delivered**：本包无
跨模型复核门，delivered 真实可达且已到达。`deliver` 生成
`exports/delivery.yaml`（version 1）并同步冻结编号
（2026-10-20，by demo-author），逐图行 `delivery_status` 均为
delivered。全程命令与输出见 `evidence/run-log.txt`。

## 2. 逐门审计结果（终审，全部 FRESH 且 PASS）

| 图 | 门 | 判决 | 实测要点 |
|---|---|---|---|
| fig-1（数据图） | alignment | PASS | 2 面板，同行边偏差 0.0 pt（容差 1.5 pt），无豁免 |
| fig-1 | collisions | PASS | 抽取文字框 27 个，FAIL/WARN 均为 0 |
| fig-1 | glyph | PASS | 内容流 Tf 实测字号全部 ≥ 地板 5 pt |
| fig-1 | contract | PASS | 图宽与双栏 183 mm 相符，文本可抽取，色板与登记一致 |
| fig-1 | honesty | PASS | 脚本头登记正常口径：y 递增、limits [60, 82] 覆盖数据全程 [62.187, 80.898]、未截断、宽高比已声明、area_encoding=none |
| fig-2（方法图） | contract | PASS | manifest 路线 file_build 在词表内，构建记录在场 |
| fig-2 | native | PASS | 首页 12 个原生形状、包内位图 0 个（无残留登记亦无未登记位图） |
| fig-2 | policy_block | PASS | 交付集文件逐个哈希比对，均与参考图本体哈希不符（重绘成品不拦） |

无任何门落 REVIEW_REQUIRED，故本次演示未触发 `audit note` 处置
流程（该流程由单元测试覆盖）。

数据图合同要点：面板 a（primary_quantitative_evidence）逐段 MOTA
曲线、面板 b（baseline_or_control）臂均值 ± 95% CI；源数据为三臂
逐段均值（fixed 72.638 / oracle 77.887 / predicted 77.835），与
light-experiment 合成演示 summary.json 逐值一致。

方法图合同要点：面板 a setup_schematic（视频输入 + 跟踪）、
面板 b mechanistic_evidence（统计量 → 阈值预测 → 逐轨迹阈值 →
异常标记），六个模块标签与参考图逐字一致，逐标签核对已落字
（provenance label_check done，by demo-author）。

## 3. 双拦截变体（不进正式交付）

| 变体 | 操作 | 结果 |
|---|---|---|
| `variants/honesty-inverted/` | 复制主包后把 fig-1 脚本头 y 轴登记改为 decreasing 且绘图真反转 y 轴，重跑 produce + audit | 总判决 **FIX_BEFORE_DELIVERY**：honesty 门以 `honesty.reversed_axis` 阻断；其余四门仍 PASS——拦截来自诚实门本身，不是连带失败 |
| `variants/native-embed/` | 复制主包后在 manifest 里把整张参考图登记为 photo 类残留（box 占满面板 a），重建 + audit | 总判决 **FIX_BEFORE_DELIVERY**：native 门以 `native.full_page_bitmap` 阻断（登记≠放行，整幅尺寸比对抓出）；contract/policy_block 仍 PASS |

### 3.1 变体抓出的一个真实产品缺陷（已修复）

native-embed 变体首跑时**未被拦下**（总判决 PASS）。根因在审计器
`_image_dims`：它用 PyMuPDF 打开图像文档后的 page rect 冒充像素
尺寸——无 DPI 元数据的 PNG 被按 96 dpi 换算成点数，800×500 的
整幅图被量成 600×375，低于「≥ 参考图 90%」的判定线而漏检。
已修复为以 `pymupdf.Pixmap` 取真实像素尺寸（文档 rect 仅作兜底），
并新增回归测试 `test_native_gate_blocks_declared_full_page_residue`
（tests/test_audit.py）。修复后变体重跑被正确拦截（见上表）；
既有测试中「1 形状 1 位图」用例靠形状数判据通过、未受此缺陷
影响——这正是变体演示的价值：它走的是另一条判据路径。

## 4. 与 Write figures_manifest 的回填对账（人工核对记录）

`delivery.yaml` 与 Write 侧需求（SKILL §11 映射）逐项对账如下，
数值取自本次运行实物：

| Write 需要 | delivery.yaml 提供（实值） | 核对 |
|---|---|---|
| figure_id + 交付状态 | fig-1 / fig-2 两行，包状态 delivered | ✓ |
| 交付文件 + 哈希 | fig-1：`exports/fig-1.pdf` sha256 `bea57265717a…`（+ 预览 PNG 一行）；fig-2：`schematic/redraw/fig-2.vsdx` sha256 `34337f1bc797…` | ✓ 与 exports/ 实物重算一致 |
| 图注哈希对账 | 两图 `caption_hash` 与承接快照 `caption_draft_hash` 逐一相等（程序核对 True/True） | ✓ 未漂移 |
| 图件 provenance | fig-1：脚本/源数据/样式三哈希 + 运行时版本；fig-2：`provenance.yaml#fig-2` 账行指针 + 提示词版本/生成模型/参考图哈希 | ✓ 交付前 verify_provenance_rows 全过 |
| AI 披露素材 | fig-2 `ai_disclosure`：generation_model、prompt_version=1、redraw_route=file_build、reference_not_in_delivery=true | ✓ 可直接喂 Write use_log |
| Visio 验证标记 | fig-2 `visio_verified: false` + 注记「文件级路线产物，未过 Visio 实机验证」 | ✓ 如实标注 |
| 编号冻结 | `numbering.frozen=true`（2026-10-20，demo-author），与本包 delivered 同步发生 | ✓ |

## 5. 如实披露清单

- **参考图来源**：`inputs/reference-fig-2.png` 由本地 PIL 程序
  绘制（`run_demo.py` 的 `draw_reference_image`），是「用户提供
  GPT Image 参考图」的**演示替身**，不是 AI 生成图；provenance
  账面生成模型如实登记为 `local PIL script (demo stand-in)`。
  它走的是与真实参考图完全相同的登记/验收/重绘/硬拦链路。
- **图库/组件种子条目**：MG-DEMO-SEED-001、VC-DEMO-SEED-ARROW、
  DG-DEMO-SEED-001 均为演示自建种子引用（姊妹仓尚未启动，见
  SKILL §12 的 D7 时机），非真实图库条目。
- **期刊合同与政策快照**：期刊合同按 Nature Figure Guide 现行
  硬数字（89/183 mm、字号 5–7 pt 等）登记为演示合同；AI 政策
  快照为演示 fixture（source_url 为 example.org 占位），不代表
  任何真实期刊的当期政策。
- **字体替换**：期刊合同登记 Arial，本机无此字体，produce 按
  规程以 DejaVu Sans 替换并在生产结果落 `font_substituted`，
  未静默换字。
- **数据身份**：三臂 MOTA 为 light-experiment 合成演示数据
  （非真实实验结果），转写时逐值核对源 summary.json。

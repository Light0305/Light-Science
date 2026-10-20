# Zero-tuning tracker thresholds predicted from video-level statistics

> idea_id: `zero-tuning-tracker-thresholds-predicted_77cdb7` ｜ 状态: **pre_mortem_passed** ｜ 算子: evolution_chain ｜ 创建 2026-10-20 ｜ 修订 2026-10-20

**一句话**：用视频级统计量回归跟踪关联阈值，免逐集人工扫描

**生成出处**：chain_id: CH-2cd7ae29；path_string: SORT'16 → ByteTrack'22 → Zhang et al.'25 （附录 A 逐时长阈值扫描=断点 BP1）→ 本想法；note: Literature 精读卡第 16 节候选 1 与此同源，链断点为据

## 种子文献（均须带 paper_id / DOI）
- doi: 10.1016/j.compag.2025.110856；Abnormal turkey behaviour detection using self-supervised video anomaly detection and multiple object tracking
- doi: 10.1007/978-3-031-20047-2_1；ByteTrack: Multi-Object Tracking by Associating Every Detection Box

## Facet 区（骨架）
- **purpose**：tracker deployment without per-video threshold tuning — 种子论文三个关联阈值须按视频时长逐集扫描选定（附录 A），部署到新视频没有现成取值；部署层三代跟踪改进都没碰。（来源: paper）
- **mechanism**：regress association thresholds from video-level statistics — 以视频级统计量（轨迹长度分布、检测置信分布、目标密度）为输入回归 θ_modIoU / θ_high / θ_low 三阈值。（来源: chain_node）
- **evaluation**：leave-one-video-out MOTA versus per-video oracle thresholds — 留一视频交叉验证：预测阈值的 MOTA 对照逐段神谕扫描（上限）与固定阈值（下限）。（来源: user）

## 正文区
**平语方法描述**：
1. 在多段视频上复现附录 A 的逐段阈值扫描，得到（视频统计量 → 最优三阈值）样本
2. 拟合小型回归器（统计量只取视频前段，部署时不许用未来帧）
3. 新视频推理时由前段统计量直接给出三阈值，零人工调参跑跟踪
4. 留一视频交叉验证对账神谕上限与固定阈值下限
**一句话假设**：视频级统计量与最优关联阈值之间存在稳定映射，可学且可迁移到留出视频
**机制说明**：阈值本质是检测质量与遮挡强度的折中，而这两者都体现在轨迹长度、置信分布与密度统计里——统计量是阈值的因，逐集扫描只是在逐段重测这个因。
**可证伪的意外预测**：只用视频前 30 秒统计量预测的阈值，效果不差于用全程统计量——若成立，部署可在视频开头即完成标定
**贡献类型**：method

## 执行级规格区（可执行定版必填六项 + 判别实验）
- **datasets**：自建火鸡栏舍复现集；MOT17 train
- **strongest_baseline**：doi: 10.1016/j.compag.2025.110856
- **metrics**：MOTA；IDF1；HOTA
- **ablations**：去掉轨迹长度分布特征；去掉检测置信分布特征；去掉目标密度特征；回归器换常数预测（固定阈值对照）；只用前 30 秒统计量 vs 全程统计量
- **resource_budget**：{'gpu_hours': 30, 'data': '自建 6 段 + MOT17', 'weeks': 3}
- **key_details**：三阈值联合回归而非逐个独立回归（附录 A 显示三者耦合）；统计量只许用视频前段；留一视频交叉验证，禁止在留出段上调回归器超参
- **最小判别实验**：6 段自建视频上留一交叉验证：其余 5 段的（统计量→神谕θ）样本训练回归器，预测留出段三阈值并跑 Byte³Track（正: 留出段 MOTA 达神谕值 98% 以内（差 ≤2 点）且全面优于固定阈值：映射成立，进 Design；负: 任一留出段 MOTA 低于固定阈值基线：统计量→阈值映射不存在，假设为假，回炉 facet；零: 与固定阈值差 <1 点且距神谕 >2 点：判别力不足，先扩样本段数再判，不许直接宣称成立）

## 负面字段区
- **最强反对意见**：审稿人会说：你只有 6 段视频，回归器学的不过是「时长→阈值」的查表，而附录 A 本来就按时长给了两组数——增量为零
- 风险：主导阈值的变量可能是时长之外的场景因素（密度/光照/遮挡率），统计量未覆盖时预测失效
- 风险：自建复现集与作者数据分布不一致，结论外推受限

## 查新证据区（判定区 — 辅助信号不许入内）
- 判定: **PROCEED_WITH_CAUTION** ｜ 检查于: 2026-10-20 ｜ review_status: REVIEW_UNAVAILABLE
- CAUTION 薄点: delta 薄在证据覆盖：机制面与评测面在本池（Crossref+Europe PMC 两源 105 条）无实质撞车，但 OpenAlex 与 Semantic Scholar 本次全部 429，CS 会议/预印本恰是跟踪器超参自动整定类工作的主要栖息地，未撞车的结论覆盖不全；池内记录无摘要、判定止于题名级；且判定与生成同模型家族（降级通道），跨模型复核恢复后应优先复查机制面
- 检索范围: 源 ['crossref', 'openalex', 'semanticscholar', 'europepmc'] ｜ 池规模 105 ｜ 已知盲区: OpenAlex 本次全部查询失败（HTTP 429：https://api.openalex.org/works）：该源独有覆盖可能漏检，本次结论须视为覆盖不全；Semantic Scholar 本次全部查询失败（HTTP 429：https://api.semanticscholar.org/graph/v1/paper/search）：该源独有覆盖可能漏检，本次结论须视为覆盖不全；检索基于题名/摘要级元数据，未做全文比对：只在全文细节处撞车的论文可能漏检；相似度为离线文本粗排，仅作召回排序，不是判定依据（约束 3）
- 最接近工作:
  - doi: 10.3390/jimaging12090411；Task-Specific Detector Adaptation for Edge MOT: Tracking and Deployment Trade-Offs on the NVIDIA Jetson Nano.｜撞车面: ['purpose']｜delta: 同问「MOT 如何部署」但对象不同：它面向边缘硬件约束做检测器适配与权衡，不涉及关联阈值，更不做视频内容统计量→阈值预测；本想法的部署变量是视频内容而非硬件｜已核实: False
  - doi: 10.3390/ani16152408；Robust Tracking and Quantification of Open-Beak Behavior for Heat Stress Assessment in Multi-Tier Caged Rearing Broiler Breeders via Mobile Inspection.｜撞车面: ['purpose']｜delta: 同为家禽行为跟踪的部署型工作，但它解决特定行为（张口呼吸）的稳健量化，阈值仍是内部固定参数；本想法把阈值本身作为由统计量预测的对象｜已核实: False
  - doi: 10.1109/iicaiet67254.2025.11265378；Multi-level Support Thresholds for Association Mining｜撞车面: ['mechanism']｜delta: 仅词面撞车：其 association 指数据挖掘关联规则、thresholds 指支持度阈值，与多目标跟踪的关联阈值无关；列此条以明示判定读过粗排首位并逐面排除之｜已核实: False
- 判定收据: verdict_id NV-71ac845123｜判定 None｜执行 claude-opus-4.8

## 辅助字段区（只许参考、不进判定；一律「暂定，未经执行验证」）
- pairwise_record: [{'opponent': 'scale-robust-frame-aggregation-for-flock_1b4467', 'result': 'win', 'date': '2026-10-20', 'by': '演示执行者 claude-opus-4.8（与生成同家族，仅 aux 排序信号）', 'note': '正序：C1 判别实验离线可判、部署价值直接；反序复核同判（C3 为诊断型贡献，杠杆较小）'}, {'opponent': 'individual-abnormal-behaviour-profiles-b_fcefb8', 'result': 'win', 'date': '2026-10-20', 'by': '演示执行者 claude-opus-4.8（与生成同家族，仅 aux 排序信号）', 'note': '正序：C1 判别实验最便宜且结论最 crisp；反序复核同判——C1 定为本周期 top pick'}]（暂定）
- elo: 1531.2（暂定）

## 状态历史
- 2026-10-20：None → draft（light-idea new）建卡
- 2026-10-20：draft → screened（claude-opus-4.8（本周期执行者））
- 2026-10-20：screened → novelty_checked（claude-opus-4.8）
- 2026-10-20：novelty_checked → pre_mortem_passed（claude-opus-4.8（扮演执行阶段评审者逐项过清单））

# Zero-tuning tracker thresholds：留一视频交叉验证对照实验设计

> design_id: `zero-tuning-tracker-thresholds_979ee7` ｜ 状态: **reviewed** ｜ 级别: full ｜ 承接 idea: `zero-tuning-tracker-thresholds-predicted_77cdb7` ｜ 创建 2026-10-20 ｜ 修订 2026-10-20

## 输入承接（Idea 交接六项）
**原始研究问题（逐字）**：Zero-tuning tracker thresholds predicted from video-level statistics
- **datasets** → evaluation.data_protocol / plan.variables｜状态: accepted｜交接原值: [{"name": "自建火鸡栏舍复现集", "version": "6 段视频（2.5/5 分钟各 3）", "access": "自建采集（种子作者数据未公开）"}, {"name": "MOT17 train", "version": "公开基准", "access": "公开下载（仅方法先行验证，不作领域结论）"}]
- **strongest_baseline** → contract.controls（status_quo）｜状态: accepted｜交接原值: {"name": "种子论文附录 A 的逐视频神谕阈值扫描协议（上限对照）；固定阈值取种子 2.5 分钟组取值（下限对照）", "doi": "10.1016/j.compag.2025.110856"}
- **metrics** → evaluation.primary_metric / guardrail_metrics｜状态: expanded｜交接原值: [{"name": "MOTA", "convention_source": "MOTChallenge 与种子论文口径"}, {"name": "IDF1", "convention_source": "MOTChallenge 与种子论文口径"}, {"name": "HOTA", "convention_source": "HOTA 原文（IJCV 2020）与种子论文口径"}]
- **ablations** → contract.ablations｜状态: expanded｜交接原值: ["去掉轨迹长度分布特征", "去掉检测置信分布特征", "去掉目标密度特征", "回归器换常数预测（固定阈值对照）", "只用前 30 秒统计量 vs 全程统计量"]
- **resource_budget** → resources.budget / power｜状态: expanded｜交接原值: {"gpu_hours": 30, "data": "自建 6 段 + MOT17", "weeks": 3}
- **key_details** → plan / handoff.repro_fields｜状态: expanded｜交接原值: ["三阈值联合回归而非逐个独立回归（附录 A 显示三者耦合）", "统计量只许用视频前段", "留一视频交叉验证，禁止在留出段上调回归器超参"]

## 主张区（主张先行，实验从主张反推）
- **[C1]** 视频级统计量（轨迹长度分布、检测置信分布、目标密度）与最优关联阈值之间存在稳定映射：由视频前 30 秒统计量联合回归出的三阈值，在留出视频上的 MOTA 达到逐段神谕扫描的 98% 以内（差 ≤2 点），且全面优于固定阈值。（确认性）
  - 最低可信证据：6 段自建视频留一交叉：每段预测阈值 MOTA 距该段神谕 ≤2 点且高于固定阈值；ABL-04（常数预测）对照下回归优势 ≥SESOI 2 点，排除「随便给个常数就行」；ABL-06（去一切时长代理特征）后优势仍在，排除时长查表解释。
  - 为何重要：成立则跟踪器部署免逐集人工调参——种子论文附录 A 的逐时长扫描正是当前部署的实际成本；不成立（走负向判读）同样有价值：证明逐集调参为何不可避免。
- **[C2]** 只用视频前 30 秒统计量预测的阈值不差于用全程统计量（段级差 <1 点）：部署可在视频开头即完成标定（承卡 unexpected_prediction）。（确认性）
  - 最低可信证据：ABL-05：全程统计量变体与主通道（前 30 秒）在 6 段留出 MOTA 上的段级配对差 <1 点。
  - 为何重要：决定该方法是能在线部署（开头标定）还是只能离线逐段处理，是 C1 的部署形态分水岭。
- **反主张 [AC1]**：回归器只是学到「时长→阈值」查表：附录 A 本就按时长给了两组数，增量为零（承卡 strongest_objection）。（由 ABL-06（去掉一切时长代理特征后仍须成立）+ 自建集同等时长段间神谕 θ 本有差异，查表解释不掉该部分变异 排除）
- **反主张 [AC2]**：预测胜出只因下限基线太弱或调参不对等（自家方法拿到更高调参预算）。（由 固定阈值取种子论文已发表取值（非自设弱基线）+ evaluation.tuning_parity 对等条款 + 神谕上限锚（须达 98%）双向夹逼 排除）
- **反主张 [AC3]**：映射只是自建复现集分布的产物（与种子作者数据分布不一致），换分布即失效。（由 只能部分排除：S0 在 MOT17 上先验映射存在性；分布外推的残余登记在 validity.external，不许靠本设计声称排除 排除）

## 方案区
- 设计类型：对照实验型｜独立重复层级：**视频段（独立采集单元）：处理在段级独立施加、留一折以段为单位，n = 6 段；帧与轨迹只是段内观测、不是独立重复（按帧计 n 即伪重复）**
- 变量 **threshold_source**（treatment）：{'kind': 'choice', 'values': ['regressed_prefix30s', 'fixed_published', 'oracle_scan', 'constant_mean', 'regressed_fullvideo']}
- 变量 **feature_set**（treatment）：{'kind': 'choice', 'values': ['full', 'no_track_length', 'no_confidence_dist', 'no_density', 'no_duration_proxy']}
- 变量 **held_out_segment**（treatment）：{'kind': 'choice', 'values': ['seg1', 'seg2', 'seg3', 'seg4', 'seg5', 'seg6']}
- 变量 **MOTA**（outcome）：{'kind': 'range', 'min': -100, 'max': 100}
- 变量 **IDF1**（outcome）：{'kind': 'range', 'min': 0, 'max': 100}
- 变量 **HOTA**（outcome）：{'kind': 'range', 'min': 0, 'max': 100}
- 变量 **segment_duration_min**（covariate）：{'kind': 'choice', 'values': [2.5, 5.0]}
- 变量 **mean_targets_per_frame**（covariate）：{'kind': 'range', 'min': 0, 'max': 100}
- 变量 **occlusion_rate**（covariate）：{'kind': 'range', 'min': 0, 'max': 1}
- 干预生效核查点：每次跟踪运行前打印并落盘实际生效的 (θ_modIoU, θ_high, θ_low) 三元组，与该 run 登记取值逐字比对（自变量须真改变且留证：声称换了阈值实际恒定即整 run 作废）；统计量窗口审计：预测通道的统计量计算只读登记窗口内帧（前 30 秒口径帧号上限 = 30×fps），帧号范围落盘审计，越界即该 run 作废；留出段隔离断言：每折回归器训练样本段 id 清单落盘并断言不含留出段，断言记录留痕后才许开跑

## 实验契约区
- 对照 **种子论文附录 A 的逐视频神谕阈值扫描协议（上限对照）；固定阈值取种子 2.5 分钟组取值（下限对照）**（status quo 一等对照）
- 对照 **部署现状对照：固定阈值（种子论文 2.5 分钟组已发表取值，部署时不做任何逐段调整）**
- 消融 **ABL-01**：测 轨迹长度分布特征是否携带阈值信息（遮挡强度的代理）；组件重要则预期 去掉后留出段 MOTA 明显下降（≥1 点）且距神谕差距扩大
- 消融 **ABL-02**：测 检测置信分布特征是否携带阈值信息（检测质量的代理）；组件重要则预期 去掉后留出段 MOTA 明显下降（≥1 点）且距神谕差距扩大
- 消融 **ABL-03**：测 目标密度特征是否携带阈值信息（拥挤度的代理）；组件重要则预期 去掉后留出段 MOTA 明显下降（≥1 点）且距神谕差距扩大
- 消融 **ABL-04**：测 「统计量→阈值映射存在性」本身：回归相对常数预测（训练段神谕 θ 均值）有无增量；组件重要则预期 回归段均值 MOTA 优于常数预测 ≥SESOI 2 点；若不优于，主张 C1 直接不成立（本条是对主张本身的判别消融）
- 消融 **ABL-05**：测 统计量窗口充分性：全程统计量 vs 前 30 秒统计量；组件重要则预期 若前段统计量已充分（主张 C2），全程变体不优于主通道超过 1 点；明显更优则 C2 不成立
- 消融 **ABL-06**：测 时长查表反主张（AC1）：去掉一切时长代理特征（显式时长与时长单调派生量）后映射是否仍成立；组件重要则预期 去掉后回归仍优于常数预测 ≥2 点且距神谕 ≤2 点的判读不变；优势消失则 AC1 成立、C1 须回炉
- 不做消融：逐个独立回归 vs 联合回归的消融（key_details 已写死三阈值联合回归（附录 A 显示耦合），独立回归是已排除的实现选择而非待证主张；资源优先给特征组消融）
- 不做消融：更换跟踪器骨干（检测器/关联算法变体）（本设计只问阈值策略，跟踪管线固定为种子论文 Byte³Track 管线；换骨干会引入构念混淆、稀释判别力）

| run_id | 角色 | 对照 | 依赖（对照先行） | 阶段 |
|---|---|---|---|---|
| R-S0-MOT17 | sanity | — | — | S0 |
| R-ORACLE | control | — | — | S1 |
| R-FIXED | control | — | — | S1 |
| R-PRED | treatment | R-FIXED | R-ORACLE、R-FIXED | S2 |
| R-ABL-01 | ablation | — | R-ORACLE | S2 |
| R-ABL-02 | ablation | — | R-ORACLE | S2 |
| R-ABL-03 | ablation | — | R-ORACLE | S2 |
| R-ABL-04 | ablation | — | R-ORACLE | S2 |
| R-ABL-05 | ablation | — | R-ORACLE | S2 |
| R-ABL-06 | ablation | — | R-ORACLE | S2 |

## 评估协议区
- 主指标：**MOTA**（方向 higher_is_better，惯例出处 MOTChallenge 与种子论文（CEA 2025, DOI 10.1016/j.compag.2025.110856）正文口径（承卡 metrics））
- 护栏指标：IDF1（界：段均值不得低于 R-FIXED 对照 1 点以上（不许靠牺牲身份保持换 MOTA））
- 护栏指标：HOTA（界：段均值不得低于 R-FIXED 对照 1 点以上）
- 护栏指标：IDSW（界：段均值不高于 R-ORACLE 对照的 1.5 倍）
- 判读·正：留出段 MOTA 达神谕值 98% 以内（差 ≤2 点）且全面优于固定阈值：映射成立，进 Design → 主张成立口径落字：交 Analysis 按 expected_registry 对账后进 Write；部署标定流程（前 30 秒）写入方法结论
- 判读·负：任一留出段 MOTA 低于固定阈值基线：统计量→阈值映射不存在，假设为假，回炉 facet → 假设为假：回炉 light-idea 机制 facet 并回写卡 lineage；不许在 Design 内改判读、换指标或缩段重试
- 判读·零：与固定阈值差 <1 点且距神谕 >2 点：判别力不足，先扩样本段数再判，不许直接宣称成立 → 判别力不足：先扩样本段数（6 → ≥10，资源区 amendment 留痕）或扩统计量特征集再判；扩样前不许宣称成立、也不许判死
- 调参对等：三方对等登记：自家回归器超参试验 ≤20 次且只许在训练折内选择；基线侧——神谕扫描为全网格穷举（上限锚、按定义即最强，不存在对基线放水的问题）、固定阈值取已发表取值零调参；任何一方预算外调参即整折作废。
- 种子数：3｜重复数：6

## 效度登记区（四分法 · 三态）
- [conclusion] n=6 段下段级均值差的功效：2 点 SESOI 可能落在段间噪声内 — **mitigated**：功效替代口径核算（resources.power）：以段级配对差 SD≤1.5 点（附录 A 同等时长段间波动的收缩估计）为前提，6 段达 target_power 0.8；SD 恶化情形写进敏感性范围并设熔断（>2.5 点触发扩样或下调声称），不许硬判
- [conclusion] 多重比较：6 条消融逐条判读膨胀假阳性 — **mitigated**：消融只作机制归因的量级判读（预设 ≥1 点差阈值），不逐条做显著性声称；确认性结论只由主张 C1/C2 的预设判读产生
- [internal] 自变量未真改变：阈值注入失败、或统计量窗口越界偷用未来帧（时间泄漏） — **mitigated**：干预核查点三条（生效三元组回显逐字比对、统计量帧号范围审计、留出段隔离断言）执行后留证，任一不过该 run 作废重跑
- [internal] 回归器在留出段上调参/选特征（选择性泄漏） — **mitigated**：承 key_details：超参只许在训练折内选、试验次数与清单预登记；留出段 id 断言检查留痕，违反即整折作废
- [internal] 固定阈值下限锚过弱造成假胜出 — **mitigated**：下限取种子论文经同行评审的已发表取值而非自设弱值；且判读正向还须达神谕 98%，弱下限单独不足以判正
- [construct] MOTA 是否测得「部署免调参」这一构念 — **residual**：MOTA 只测跟踪质量、不测『免调参』本身。本设计把构念拆两半：质量半由 MOTA 对双锚判读；免调参半由流程事实承载（预测通道零人工介入、统计量只用前 30 秒即部署时点可得）。残余：真实部署的运维收益（省时、少出错）不在本设计测量范围内——声称边界止于『质量不低于逐段调参且流程无需人工调参』
- [construct] 「视频级统计量」构念覆盖不足：三组特征未必穷尽阈值的主导因素（光照/遮挡率等场景因素未入特征集，承卡 risks） — **residual**：正面回应卡上 risks 第 1 条：协变量（密度/遮挡率）只登记不入回归，消融与分层只能部分探测该缺口；若 ABL-04 显示映射不存在，优先怀疑构念覆盖不足——判读 null 向已预置扩特征/扩样的回炉路径，不许直接判想法死刑
- [external] 自建复现集与种子作者数据分布不一致，结论外推受限（承卡 risks 第 2 条） — **residual**：声称范围限自建集分布与 MOT17 方法层；向作者数据/其他栏舍外推须另行验证，不在本设计声称内
- [external] 仅 2 种时长、单一栏舍场景 — **mitigated**：时长分层抽样且同等时长段间保留神谕 θ 差异（时长内变异在场）；场景单一性的残余并入上一条的声称边界

## 资源区
- 功效：SESOI MOTA 2 个百分点（预测 vs 固定的段级均值差；且预测距神谕 ≤2 点）｜敏感性范围 SESOI 1 点 → 需 11 段；2 点 → 6 段（本设计）；3 点 → 4 段。若段级配对差 SD 恶化至 2.5 点，2 点 SESOI 需 11 段——超出预算即触发熔断：扩样或把主张下调为探索性，二选一落字｜推导 {'seeds': 3, 'repetitions': 6, 'eval_set_size': 6}｜核算充足: True
- 预算：算力 30 GPU 小时（承卡 resource_budget；单卡 RTX 5000 级）｜时间 3 周（承卡；含自建 6 段视频采集与标注校验）
- 熔断线：神谕扫描 GPU 消耗 @ 累计 > 20 GPU 小时（总预算 2/3）而 S1 未完 → 停扫：粗网格加密策略留痕登记后继续；不许挪用 S2 预算硬撑
- 熔断线：任一 run 同因失败次数 @ ≥3 次 → 停该 run：失败分类（实现/根本）后决定重试或回炉，不许无限重试
- 熔断线：段级配对差 SD（S1 完成后预估） @ > 2.5 点 → 功效前提失效：暂停 S2，先扩样（≥10 段）走 amendment、或把主张 C1 下调为探索性，二选一落字
- 熔断线：总工期 @ > 3 周 → 冻结新 run 启动，先保主张 C1 最小证据集（R-PRED + R-ABL-04 + R-ABL-06）

## 冻结与修订区
- 定版评审：None（None） 2026-10-20 → **None**

## 辅助区（只许参考、不进判定；一律「暂定，未经执行验证」）
- info_gain_estimates: R-PRED 与 R-ABL-04 信息增益最高（直接判主张 C1 与映射存在性）；R-ABL-05 次之（判主张 C2）；R-ABL-06 是时长查表反主张 AC1 的唯一排除者，不可省（暂定）（暂定）
- run_priority_notes: 算力熔断时保 R-PRED + R-ABL-04 + R-ABL-06 最小证据集（暂定）（暂定）
- similar_design_refs: ['light-idea 演示 C1 卡判别实验（本设计判读三向的承接来源）']（暂定）
- history_refs: []（暂定）

## 状态历史
- 2026-10-20：None → draft（light-design new）建书
- 2026-10-20：draft → reviewed（claude-opus-4.8（本演示执行者））

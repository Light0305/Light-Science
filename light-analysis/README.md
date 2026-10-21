# light-analysis

Light-Science 第五棒：吃 light-experiment 已交付（`delivered`）的执行包与
light-design 冻结的登记表，按登记行冻结的判读标准逐行回写 readout 三向
正式判定，产出**可审计的分析结论包**——每个数字判了什么、凭什么判、
强度几何、边界在哪，都落成结构化文件，Write 可直接消费、用户可逐项审计。

> **v1.0 已封版（2026-10-20）**。Phase 1 = 骨架/数据模型/校验器/A0
> 承接；Phase 2 = 最小判定计算集 + 判定/复核子流程 + 结论包填充；
> Phase 3 = 端到端演示（承 light-experiment 合成执行包判至 graded、
> 复核不可用如实停 blocked）+ SKILL/README 定版。

## 定版纪律（校验器写死，非自觉）

- **判定只认登记行**：verdicts 行必须对应 expected_registry 行 id；
  分析期新立的标准/行一律不许进判定，改判据回 Design 走 amendment。
- **只认分布不认单点**：readout_actual 必须是 {mean, spread, n, replication_level}
  四件套，单点在承接期即被拦。
- **判不了就落字**：undetermined（材料不足）/ untested（未检验）是一等
  行级终态；被作废 run 支撑的行、fundamental 失败的主张只许落 untested
  （未检验 ≠ 不成立，不许落 negative）。
- **positive 过校准门**：Type S/M 三元组必填，D 只许外部代入
  （sesoi_frozen / prior_external）——事后功效（observed power）落成字段
  规则直接拒。
- **null 必须挣来**：TOST 通过才许判 null，bounds 只许 Design 冻结 SESOI；
  判定出口是四象限（含 significant_but_equivalent、undetermined），不许塌缩。
- **贝叶斯量先过诊断门**：rank-normalized R̂ < 1.01、ESS_bulk/ESS_tail
  均 > 400 是硬字段，不过门只许落 undetermined 并注明。
- **校正族是字段**：登记头逐族声明（默认按主张族 BH-FDR，primary 可声明
  Holm），行内 p_raw/p_adj/method 须与族声明一致。
- **规格集账本先行冻结**：决策点 × 选项在约束下枚举可达组合（惰性求值
  口径），≤512 全展开、超限抽样登记种子；冻结后改动哈希即灭。
- **强度 4 档 + 冻结措辞**：conclusive/strong/suggestive/insufficient；
  自由文本禁用「显著/不显著/证明了/无影响」式表述；探索区与判定区物理
  分离，探索条目禁用判定词表。

## 分析包文件群

```
<analysis_id>/
├── analysis.yaml            # 登记头：承接区（冻结）/规格区/校正族/计数（机械汇总）
├── verdicts.jsonl           # 判定回写表（只增，改判走 supersedes 链）
├── spec_ledger.yaml         # 规格集账本：决策点/展开/三门/冻结哈希/自由度账本
├── spec_results.jsonl       # 规格 × 判定矩阵
├── exploratory/exploratory.yaml  # 探索区（物理分离，禁用判定词表）
├── conclusions.yaml         # 结论包：主张映射/强度合成/边界/数字溯源（Phase 2 填充）
├── audit.json + audit.md    # A0 可判性校验产物（双份）
└── ANALYSIS_REPORT.md       # 渲染报告
```

状态机：`intake → checked → judged → graded → delivered`（旁路 `blocked`：
复核不可用时停 delivered 之前）。行级终态不阻断包级流转，但必须全量呈现。

## CLI

```bash
pip install -e .            # 依赖仅 pyyaml
light-analysis init <pkg_dir>
light-analysis intake <pkg_dir> --execution-card <execution_card.json> \
    --registry <expected_registry.jsonl> [--design-card <design_card.json>]
light-analysis validate <pkg_dir>
light-analysis advance <pkg_dir>          # → checked（账本冻结后）
light-analysis register-sesoi <pkg_dir> --from-registry   # 主路：直读登记行结构化块
light-analysis register-sesoi <pkg_dir> --from <design 文件> \
    --pointer <点分路径> [--line <id> …]   # 指针路径（整块快照 / 裸数值兼容路）
light-analysis judge <pkg_dir> --data <judge-data.json>
light-analysis advance <pkg_dir>          # → judged
light-analysis grade <pkg_dir> [--notes <notes.json>]
light-analysis advance <pkg_dir>          # → graded
light-analysis review <pkg_dir> prepare
light-analysis review <pkg_dir> record --reviewer <名> --family <家族>
    # 或 record --review-unavailable / import --from-json <文件>
light-analysis export <pkg_dir>           # conclusion_card.json + 报告
light-analysis advance <pkg_dir>          # → delivered
light-analysis reflux <pkg_dir> --kind supplementary_ablation \
    --lines <id,…> --reason <…>           # 回流条目（只生成不越权）
light-analysis status <pkg_dir>
```

判定计算集（`calc.py`，纯标准库）：P(A>B) 经验估计/正态近似、Welch
效应量 + Hedges g + t 区间（t 分位数自实现）、TOST、BH/Holm/Bonferroni/
BY 校正（与 statsmodels 文档口径对拍）、Type S/M 闭式（Gelman & Carlin
口径，蒙特卡洛对拍）、Stouffer 合并——每项带 provenance（输入哈希），
判定数字可机械复算。

## 演示

`examples/demo-synthetic/`：对 light-experiment 合成演示执行包（明示
合成身份）的端到端判定——承接（5 行：可判 4、R-NEG 因 fundamental
失败预登记 untested）→ 规格集账本冻结（estimator × outlier_handling，
4 规格）→ SESOI 登记（合成 design 只有文本判读标准，F1 实测后经转写
件登记快照 2.0，并生成 standard_gap 回流）→ judge 逐行落字（4 行均
undetermined：方向门败于校正后 p=0.1378，Type M=3.34 亦超阈，如实
记录未绕行）→ grade（C1 support=untested、强度 insufficient、数字
溯源 9 行）→ export 交接 → delivered 被 REVIEW_UNAVAILABLE 拦停
blocked（本环境单模型家族，不伪造收据）。逐行判定表与数字一致性
核对见该目录 `demo-report.md`。

## 测试

```bash
python -m pytest   # 109 个：计算集已知答案对拍、校验器逐条纪律、
                   # 判定四象限与双门拦截、状态机逐段门、复核子流程、
                   # 对真实（合成）上游执行包的承接
```

（在无上游 light-experiment 演示包的干净检出中，真实承接一项自动
skip，其余全过。）

## 已知局限（v1.0，如实）

1. **决策点只有 estimator 改计算口径（v1.1 起落字 + 封顶）**：
   outlier_handling 等其余决策点仍只留痕不改计算——这类规格与
   主规格数值成对相同（演示 S001/S002 即此形态），方向份额只
   反映 estimator 维度的稳健性。v1.1 短期处置（ANA-D04）已落地：
   每条判定行落 robustness_scope 机械列明真算/留痕决策点及占比，
   留痕占比过半时方向性行强度自动封顶 suggestive 并点名，
   conclusions 强度 inputs 同步落字——误读面从本条文档升级为
   数据落字。未关闭的部分：outlier_handling 的真实计算（中期
   事项）仍未做，方向份额仍不许解读为全部决策点都验过。
2. **摘要材料下秩类规格退化**：只有分布四件套、无原始值时，
   median_diff 规格退化为 Welch 均值口径（结果行 note 落字），
   不做真实秩检验。
3. **贝叶斯采样走外部**：工具只对贝叶斯行做诊断字段门（R̂/ESS/
   MCSE）与落字，后验本身须外部计算后登记；工具不复算后验，
   复算抽验只覆盖判定计算集（闭式量）的范围。
4. **SESOI 登记（v1.1 已关闭原缺口）**：Design 登记行自 v1.1 起
   携带结构化 SESOI 块（DES-D01），register-sesoi 主路
   （--from-registry）直读登记行块整块快照，承接与开判双重比对、
   不一致整包拒绝；指针路径保留为旧登记表的兼容路（取到裸数值
   标 via=pointer_compat）。Design 只有文本判读标准时工具仍按
   F1 拒绝临场取数。v1.0 演示中的转写件 + standard_gap 回流
   （RX-A001）即本条缺口的实测来源，已由 DES-D01 + ANA-D02 清偿。
5. **跨模型复核依赖外部模型**：单模型家族环境只能落
   REVIEW_UNAVAILABLE 停 blocked，delivered 须异家族复核者（或
   人类专家）经 review import/record 回填后才能续推。
6. **配对/区组结构（v1.1 已关闭原缺口）**：自 v1.1 起（ANA-D03）
   判定层显式建模结构：登记行或 judge-data 条目声明 pairing
   （paired 按对齐键作差、blocked 先算区组内对照）后，效应/TOST/
   方向概率全走差值序列口径，判定行落 structure 区（mode/键/
   来源/单位数）。演示 R-FIX 形态（两臂逐段同值）在声明配对时
   可挣得 TOST 等价（包内回归用例）；未声明时仍按独立样本口径
   判并落结构假设。声明与数据不符（缺对侧、区组缺臂等）逐行落
   undetermined 点名，不静默降级。
7. **校正方法为闭式子集**：BH / Holm / Bonferroni / BY 四种；
   绑定 alpha 的两阶段法与自适应校正未实现。族口径在 intake
   一次声明，分析期改族只许走自由度账本登记，不自动重算历史判定。
8. **Type S/M 与 TOST 为正态近似闭式**：小样本、重尾分布下的近似
   误差未做模拟校准；功效极低的行以 undetermined + 三元组数值
   落字呈现，未单设「方向未定」的判定词表值。
9. **对照臂同源性（v1.1 已关闭原缺口）**：自 v1.1 起（ANA-D03）
   judge 机械识别两路同源信号——材料分臂登记的 run 引用
   （treatment_run_refs / reference_run_refs）交叠、两臂原始值
   逐元素完全相同——命中即在判定行 structure.warnings 与 note
   点名警告（仍按独立口径判并落结构假设，警告不改判）。演示
   R-FIX 行在 phase3 复跑中已被机械点名，不再只靠分析者在
   reference_label 写散文。
10. **强度合成规则写死在代码**：汇总与封顶规则（grading.py）按
    「规则先于判定冻结」的口径实现，不提供项目级配置；改规则须
    发新版并对已判包重新 grade。
11. **探索区只有纪律没有计算**：探索条目只做登记与词表拦截，
    不提供探索性统计计算工具。

## 封版记录

- v1.0（2026-10-20）：SKILL 升 v1.0（文末附 LEARNING 13 条硬约束
  对应表；失败模式附录补 F13——grade notes 形态不对时校验器须落
  结构化错误而非崩溃，演示实测发现并已修复 + 回归测试）；包版本
  pyproject 与 `__init__.__version__` 同步 1.0.0；109 测试全过。
- 演示终点如实：结论包停在 graded → blocked（REVIEW_UNAVAILABLE），
  非 delivered；真实链路（Design 真冻结 → Experiment 真执行 →
  Analysis 判定 → 异家族复核放行）待多模型环境补完后走通。
- v1.2（2026-10-21 快修批）：D-ANA-1 贝叶斯诊断缺失行整包死锁
  修复——judge 恒落机器可读 `diagnostics_status`、validate 同
  口径放行「诊断缺失/残缺 + undetermined + note 点名诊断」合法
  终态，方向性判定拦截不松。冻结真值集 v2 主张级 5/6 → 6/6、
  行级 39/39 不退化；测试 144 → 149 passed。SKILL 升 v1.2。

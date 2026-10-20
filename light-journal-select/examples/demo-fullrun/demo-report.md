# light-journal-select v1 演示报告（demo-fullrun，骨架）

> 本文件由 run_demo.py 跑完后自动生成：机器可采的事实
> 由脚本回填（第一节），叙述性结论留第四节「主线回填」
> 区，主线核对后补写。演示身份与替身披露见第三节。

## 一、运行环境与全链结果（脚本回填）

- 运行日期：2026-10-20
- OpenAlex API Key：已注入（值不落字）
- 稿件：Abnormal turkey behaviour detection in intensive farming using computer vision
- 选刊包：selection-pkg/（selection_id abnormal-turkey-behaviour-detection-in-i_c771be）
- 先例路：3/3 条检索式成功；入池 21 刊：Computers and Electronics in Agriculture, Pressacademia, International Journal of Developmental Neuroscience, Sensors, Scientific Reports, Electronics, Multimedia Tools and Applications, Nigerian Journal of Physics, Zenodo (CERN European Organization for Nuclear Research), Poultry Science, Smart Agricultural Technology, Animals, Frontiers in Veterinary Science, Frontiers in Animal Science, Agriculture, Gomal Journal of Agriculture and Biology, AgriEngineering, Edelweiss Applied Science and Technology, Biosystems Engineering, IEEE Access, International Journal of Advanced Biochemistry Research
- 近失刊：Business And Management Studies An International Journal, International Journal of Social Sciences and Management Review, Journal of Animal Ecology, Natural Hazards, International Journal of Climatology, Informatics, Nutrients, International Journal of Advanced Research in Science Communication and Technology, Functional Ecology, International Journal for Research in Applied Science and Engineering Technology, Journal of Law & Social Studies, Journal of Wireless Mobile Networks Ubiquitous Computing and Dependable Applications, Cognitive Research Principles and Implications, Balıkesır Health Sciences Journal, DergiPark (Istanbul University), Indonesian Journal of Electrical Engineering and Computer Science, GigaScience, Italian Journal of Animal Science, Van Yüzüncü Yıl University Academic Data Management System, International Scientific Journal Sui Generis, International Journal of Nursing Practice, Information Technology and Computer Engineering, Uludağ University Journal of The Faculty of Engineering, Australian Journal of Primary Health, Geophysical Journal International, International Journal of Data Science and IoT Management System, Frontiers in Medicine, Route Educational and Social Science Journal, MGIMO Review of International Relations, International Journal of Global Warming, Journal of Criminology and Criminal Law, Karadeniz Teknik Üniversitesi İletişim Araştırmaları Dergisi, Harran Üniversitesi Tıp Fakültesi Dergisi, Asthma Allergy Immunology, Expert Systems with Applications, Wildlife Society Bulletin, Primary care diabetes, Journal of the Knowledge Economy, Aestimum, Poultry, International Journal of Advanced Computer Science and Applications, Kinetik Game Technology Information System Computer Network Computing Electronics and Control, Journal of Informatics and Web Engineering, AI and Ethics, HAL (Le Centre pour la Communication Scientifique Directe), World s Poultry Science Journal, Aquaculture Fish and Fisheries, ESRJ, International Journal Science and Technology, Animal Frontiers, Science Advances, PLoS ONE, Revista de Informática Teórica e Aplicada, National Journal of Animal Health and Sustainable Livestock, Journal of Dairy Science, Devotion Journal of Research and Community Service, IEEE Sensors Journal, World Journal of Advanced Engineering Technology and Sciences, Computing and artificial intelligence., Applied Sciences, Tropical Animal Health and Production, Animal Science Papers and Reports, Journal of applied science and environmental management, Journal of Applied Animal Research, INTERANTIONAL JOURNAL OF SCIENTIFIC RESEARCH IN ENGINEERING AND MANAGEMENT, Heliyon, 電腦學刊, International Journal of Rural Criminology, International Journal of Scientific Research in Science and Technology, Discover Animals, Wasit Journal of Computer and Mathematics Science, AI, International Journal of Computer Vision, Emerging Science Journal, Archivos Latinoamericanos de Producción Animal, Animal Bioscience, Artificial Intelligence in Agriculture, International Journal of Distributed Sensor Networks, SinkrOn, Czech Journal of Animal Science, Animal Health Research Reviews, Meat Research | ISSN (Online Version) 2790-1971, IEEE Journal of Radio Frequency Identification
- 核验：22 刊落核验块（verified/unconfirmed 逐项见 selection.yaml）
- 风险门等级：Computers and Electronics in Agriculture = clear；Pressacademia = clear；International Journal of Developmental Neuroscience = clear；Sensors = clear；Scientific Reports = clear；Electronics = clear；Multimedia Tools and Applications = clear；Nigerian Journal of Physics = clear；Zenodo (CERN European Organization for Nuclear Research) = clear；Poultry Science = clear；Smart Agricultural Technology = clear；Animals = soft_warn；Frontiers in Veterinary Science = clear；Frontiers in Animal Science = clear；Agriculture = clear；Gomal Journal of Agriculture and Biology = clear；AgriEngineering = clear；Edelweiss Applied Science and Technology = clear；Biosystems Engineering = clear；IEEE Access = clear；International Journal of Advanced Biochemistry Research = clear；Journal of Fictional Turkey Studies = quasi_hard
- 风险门排除：Journal of Fictional Turkey Studies
- 分档：challenge 0 刊；target 5 刊；safety 0 刊
- 定刊：Smart Agricultural Technology（demo-author（演示代行），2026-10-20）
- 交接自检：本地结构 pass / Write 校验器 pass
- 下载清单：已下载 0 件 / 待下载 1 件（author-guide）
- 最终状态：handed_off（validate ok = True）

## 二、产物索引

- selection-pkg/selection.yaml（登记头，权威）
- selection-pkg/evidence/（OpenAlex 原始响应留痕）
- selection-pkg/SELECTION_REPORT.md（三档证据卡）
- selection-pkg/selection.json（机器可读导出）
- selection-pkg/journal/target/（download-manifest.json / check-record.json / handoff.md）
- evidence/run-log.txt（全程命令与输出）、evidence/summary.json
- inputs/（指纹/核验记录/名单 fixture/指南字段/下载登记）

## 三、披露（演示替身与种子）

1. **风险名单是 demo fixture**（inputs/name-list.csv，stop-predatory 风格）：predatory_list_hit 的靶子是演示虚构刊「Journal of Fictional Turkey Studies」（经 search 路入池），不是任何真实名单对真实期刊的命中；volume_surge 软警告为演示注入、非真实核查结论。名单与报告中的来源串均如实标注 demo-fixture。
2. **handoff 指南字段集是演示种子值**（inputs/guide-fields.json）：结构照 Elsevier elsarticle 常规与 CEA 作者指南的公开形态填写。产品纪律是字段由执行者读官网指南后提供；演示以种子集替代，逐项数值在正式投稿前须对官网 Guide for Authors 复核。
3. **指南与模板未真下载**：download-manifest 中条目均为 pending_download 并逐个点名，未伪造已下载；真文件请按 manifest 的 source_url 从官网取回后回填登记。
4. **专有指标未确认**：影响因子 / JCR 分区 / 中科院分区 / 自引率无开放渠道，核验中如实落 unconfirmed（skipped），未凭记忆报数（JS-01 / JS-11）；审稿周期官网无可抓取的官方统计，落 unconfirmed（attempted）。
5. 核验中的 annual_volume / indexing 来自 OpenAlex 源记录（聚合源，provenance=aggregator）、APC 来自 DOAJ 公开 API、scope_fit 来自官网首页主题词核对——均为本次运行联网现查并带来源与日期（JS-01）。

## 四、主线回填（2026-10-20，据真实运行结果）

- **演示结论**：全链真实联网走通，终点 `handed_off`、validate ok。注入用户自备 OpenAlex Key 后先例路 3/3 条检索式成功、21 刊入池；风险门排除虚构刊靶子（quasi_hard，只增留痕），Animals 落 soft_warn（演示注入的 volume_surge，非真实核查结论）；分档 target 5 刊 / challenge 0 / safety 0；定刊 **Smart Agricultural Technology**（target 档、risk clear、先例 6 篇覆盖 2 式，由演示脚本代行并注明）；check-record（TR-2026-623ddd）本地结构自检与真 Write 校验器自检双 pass；download-manifest 0 件 downloaded / 1 件 pending_download（author-guide，未伪造已下载）。全程产物无 Key 明文、无 surrogate 残留（grep 验收过）。
- **与预期差异**：
  1. **定刊不是 CEA**。CEA 的先例证据绝对量全池最强（7 篇、3 条检索式全覆盖），但分档按 `rate_per_10k` 单键排序取前 5 张卡，CEA 率 13.16 排第 9、未入卡；演示的 CEA 优先口径落空后，改按先例证据量在 target 档内选定 Smart Agricultural Technology（同为 Elsevier 农业技术刊，先例题名实测对口）。
  2. **challenge / safety 两档为空**。全池无一刊有 verified 分区（IF/分区为专有指标、无开放渠道，如实 unconfirmed），声望序全空 → challenge 无人够格；无 provisional 候选 → safety 为空。属「不凑数」纪律内的诚实空缺，但三档在本运行环境下实际退化为单档。
  3. **manifest 只有 1 件待下载**。定刊非 CEA 后走通用分支，只登记 author-guide 一件；CEA 分支预期的指南 + elsarticle 模板 2 件未出现（模板条目只对 CEA 分支写死）。
  4. **近失刊名单 80+ 条**。宽检索式召回噪声大，近失留痕属设计内，但报告附录可读性差。
- **发现的问题**：
  1. **【产品·分档排序】归一化率的小分母膨胀**。证据卡按 rate_per_10k 单键排序：Gomal Journal of Agriculture and Biology 以 1 篇先例、窗口发文量约 37 篇得率 270.27/万篇居首；Nigerian Journal of Physics 以 1 篇得 27.55 入卡；而 CEA（7 篇/3 式）被挤出卡外。归一化防大刊偏倚的同时引入了小刊偏倚。v1.1 建议评估卡位复合排序（先例篇数/覆盖式数与率联合）或给率设最小分母门槛。本轮按纪律未改产品代码，仅演示驱动侧兜底。
  2. **【产品·数据缺口】候选 homepage_url / guide_url 恒为 None**。OpenAlex works 响应里的 primary_location.source 是脱水记录、不含 homepage_url 字段，先例路读 `source.get("homepage_url")` 恒落空。连带后果：verify 的官网 scope 核对无从触发（本轮全池 scope_fit 皆 unconfirmed）、check-record 的 H.source_url 无产品侧兜底来源。v1.1 建议先例路补一跳 `/sources/{id}` 回填 homepage_url。本轮由演示驱动在核验时留存源记录实测 homepage 并注入 H 组与下载清单，未动产品代码。
  3. **【产品·先例路】仓库型来源入池**。Zenodo（OpenAlex source.type=repository）以候选「期刊」身份入池（未入卡、未被定刊）。v1.1 建议按 source.type 过滤或在池内显式标注非期刊来源。
  4. **【覆盖边界】verify 官网层大面积未确认**。出版商页面抓取受限、专有指标无开放渠道、审稿周期无官方可抓统计——IF / 分区 / 自引率落 skipped、APC/scope/周期落 attempted，均为如实落痕（设计内）；但当前开放数据条件下，分档实际只由先例证据 + OpenAlex/DOAJ 的收录与发文量驱动，指标层区分度有限。
  5. **【驱动修复留痕】本轮共修演示脚本 5 处，产品代码零改动**：① precedent 调用误设 `expect_fail=True`，有 Key 时 rc=0 反被判死——改正常调用、按返回 JSON 的 `queries_ok` 分支（=0 才走中止分支、部分成功不中止）；② validate 调用同类误设且与后续 rc 判断自相矛盾——改正常调用，`validate_ok = (rc == 0)`；③ 兜底选刊原按入池顺序取首张 target 卡，首轮实跑曾落到只有 1 篇先例的 Nigerian Journal of Physics——改按先例证据量（篇数→覆盖式数→归一化率）排序选定；④ 定刊 reason 模板无条件断言「主题与刊 scope 对口」——改按 scope_fit 实况措辞，未确认时明写「正式投稿前须人工核对该刊 scope」；⑤ GUIDE_FIELDS 缺 H 组、且候选官网 URL 恒缺（见问题 2）——驱动在核验阶段留存 OpenAlex 源记录实测 homepage，handoff 时注入 H.source_url（CEA 用其指南页常量、他刊用实测 homepage），取不到则不注入、让 handoff 如实报错。

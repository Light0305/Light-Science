# light-journal-select v1 演示报告（demo-fullrun，骨架）

> 本文件由 run_demo.py 跑完后自动生成：机器可采的事实
> 由脚本回填（第一节），叙述性结论留第四节「主线回填」
> 区，主线核对后补写。演示身份与替身披露见第三节。

## 一、运行环境与全链结果（脚本回填）

- 运行日期：2026-10-20
- OpenAlex API Key：已注入（值不落字）
- 稿件：Abnormal turkey behaviour detection in intensive farming using computer vision
- 选刊包：selection-pkg/（selection_id abnormal-turkey-behaviour-detection-in-i_c771be）
- 先例路：3/3 条检索式成功；入池 20 刊：Computers and Electronics in Agriculture, Pressacademia, International Journal of Developmental Neuroscience, Sensors, Scientific Reports, Electronics, Multimedia Tools and Applications, Nigerian Journal of Physics, Poultry Science, Smart Agricultural Technology, Animals, Frontiers in Veterinary Science, Frontiers in Animal Science, Agriculture, Gomal Journal of Agriculture and Biology, AgriEngineering, Edelweiss Applied Science and Technology, Biosystems Engineering, IEEE Access, International Journal of Advanced Biochemistry Research
- 近失刊：Business And Management Studies An International Journal, International Journal of Social Sciences and Management Review, Journal of Animal Ecology, Natural Hazards, International Journal of Climatology, Informatics, Nutrients, International Journal of Advanced Research in Science Communication and Technology, Functional Ecology, International Journal for Research in Applied Science and Engineering Technology, Journal of Law & Social Studies, Journal of Wireless Mobile Networks Ubiquitous Computing and Dependable Applications, Cognitive Research Principles and Implications, Balıkesır Health Sciences Journal, Indonesian Journal of Electrical Engineering and Computer Science, GigaScience, Italian Journal of Animal Science, International Scientific Journal Sui Generis, International Journal of Nursing Practice, Information Technology and Computer Engineering, Uludağ University Journal of The Faculty of Engineering, Australian Journal of Primary Health, Geophysical Journal International, International Journal of Data Science and IoT Management System, Frontiers in Medicine, Route Educational and Social Science Journal, MGIMO Review of International Relations, International Journal of Global Warming, Journal of Criminology and Criminal Law, Karadeniz Teknik Üniversitesi İletişim Araştırmaları Dergisi, Harran Üniversitesi Tıp Fakültesi Dergisi, Asthma Allergy Immunology, Expert Systems with Applications, Wildlife Society Bulletin, Primary care diabetes, Journal of the Knowledge Economy, Aestimum, Poultry, International Journal of Advanced Computer Science and Applications, Kinetik Game Technology Information System Computer Network Computing Electronics and Control, Journal of Informatics and Web Engineering, AI and Ethics, World s Poultry Science Journal, Aquaculture Fish and Fisheries, ESRJ, International Journal Science and Technology, Animal Frontiers, Science Advances, PLoS ONE, Revista de Informática Teórica e Aplicada, National Journal of Animal Health and Sustainable Livestock, Journal of Dairy Science, IEEE Sensors Journal, Devotion Journal of Research and Community Service, World Journal of Advanced Engineering Technology and Sciences, Computing and artificial intelligence., Applied Sciences, Tropical Animal Health and Production, Animal Science Papers and Reports, Journal of applied science and environmental management, Journal of Applied Animal Research, INTERANTIONAL JOURNAL OF SCIENTIFIC RESEARCH IN ENGINEERING AND MANAGEMENT, Heliyon, 電腦學刊, International Journal of Rural Criminology, International Journal of Scientific Research in Science and Technology, Discover Animals, Wasit Journal of Computer and Mathematics Science, AI, International Journal of Computer Vision, Emerging Science Journal, Archivos Latinoamericanos de Producción Animal, Animal Bioscience, Artificial Intelligence in Agriculture, International Journal of Distributed Sensor Networks, SinkrOn, Czech Journal of Animal Science, Animal Health Research Reviews, Meat Research | ISSN (Online Version) 2790-1971, IEEE Journal of Radio Frequency Identification
- 核验：21 刊落核验块（verified/unconfirmed 逐项见 selection.yaml）
- 风险门等级：Computers and Electronics in Agriculture = clear；Pressacademia = clear；International Journal of Developmental Neuroscience = clear；Sensors = clear；Scientific Reports = clear；Electronics = clear；Multimedia Tools and Applications = clear；Nigerian Journal of Physics = clear；Poultry Science = clear；Smart Agricultural Technology = clear；Animals = soft_warn；Frontiers in Veterinary Science = clear；Frontiers in Animal Science = clear；Agriculture = clear；Gomal Journal of Agriculture and Biology = clear；AgriEngineering = clear；Edelweiss Applied Science and Technology = clear；Biosystems Engineering = clear；IEEE Access = clear；International Journal of Advanced Biochemistry Research = clear；Journal of Fictional Turkey Studies = quasi_hard
- 风险门排除：Journal of Fictional Turkey Studies
- 分档：challenge 0 刊；target 5 刊；safety 0 刊
- 定刊：Computers and Electronics in Agriculture（demo-author（演示代行），2026-10-20）
- 交接自检：本地结构 pass / Write 校验器 pass
- 下载清单：已下载 0 件 / 待下载 2 件（guide-for-authors.html, elsarticle-template.zip）
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

## 四、主线回填（跑完后由主线补写）

- 演示结论：[待主线回填]
- 与预期差异：[待主线回填]
- 发现的问题：[待主线回填]

# light-leader

Light-Science 的总控技能：薄编排层。建项目骨架、只读扫描各阶段包的登记头报告全项目状态、按规则表给下一步路由、只读消费 light-memory 的对象注册统一视图。不重实现任何阶段包的逻辑，不写任何阶段包的文件。

全链：light-literature → light-idea → light-design → light-experiment → light-analysis → light-journal-select（write 前置扩展位）→ light-write → light-figure → light-review，light-memory 横贯全程。

## 快速上手

    light-leader init my-project --name my-project --title "我的课题"
    light-leader status my-project     # 逐阶段状态（只读）
    light-leader route my-project      # 硬门点名 + 下一步建议（只读）
    light-leader registry my-project   # 对象注册统一视图（只读，消费 memory 的 registry-view.json）
    light-leader funnel my-project     # 漏斗统计：阶段分布/门拦截/转化/返工/停滞（只读，LD-06）
    light-leader synthesis my-project  # 外环综合：决策时间线/模式发现/方向建议（只读，LD-05）

项目目录规范、全链接口图、阶段路由规程与跨包纪律见 [SKILL.md](SKILL.md)。

## 状态

**v1.0 已封版**（2026-10-20）。封版记录：layout 阶段规格表 + scaffold / scan / route / registry 四件 + CLI 四命令，32 测试；演示对由各包真实 demo 登记头拼成的项目跑通 init → status → route → registry 全链，route 正确点名 idea / design / analysis / write 四处 REVIEW_UNAVAILABLE 硬门，见 [examples/demo-fullrun/demo-report.md](examples/demo-fullrun/demo-report.md)。

**v1.1 构建完成、待全套统一封版**（2026-10-21）：LD-03 状态词规范化映射表（各包状态值 → 进行中 / 已达终态 / 被门拦 / 旁路，SKILL §7 成文表与代码常量同源、覆盖断言守护）+ LD-04 门字段族登记（route 点名扩至 blocked_gate 统一字段与 design 打回/阻塞记录，缺字段不点名不猜），测试增至 44 项；演示复跑四门点名不变。LD-01 路由准确率评测随第 4 步 X-01 合流。**v1.1 集成步增补**（LD-02 三包纳管）：layout 登记扩展位表（patent / software-copyright = 出口层扩展位、crawler = 通道层扩展位，三包不入十阶段主流水线），init 骨架含三落点目录与 project.yaml 的 extensions 段；status 汇总呈现三包状态，route 按触发点名（patent blocked 门与 90 日期限窗口、软著补正期限、review 交付后的出口层启动提示、爬虫预检 blocked/未预检/待确认与熔断目标），扩展位不进下一步与收官判定；LD-03 映射表补三包状态词。测试增至 58 项。

**v1.2 已封版**（2026-10-21，总纲三第六批）：LD-05 外环综合 + LD-06 漏斗统计落地（light_leader/outer.py + funnel / synthesis 两只读命令，SKILL §11 规程）——把 memory 事件账编译为决策时间线与带证据的周期综合，并给出各阶段门拦截次数、返工率与被门拦原因分布的统计面；数据源封闭（scan 汇总 + registry-view + memory 事件/晋升两账）。测试增至 68 项；演示实产与独立抽核见 demo-report §7。「只建议不执行」边界不变。

## 许可证

MIT（占位），见 [LICENSE](LICENSE)，署名 light-leader contributors。

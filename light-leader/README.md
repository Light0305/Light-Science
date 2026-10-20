# light-leader

Light-Science 的总控技能：薄编排层。建项目骨架、只读扫描各阶段包的登记头报告全项目状态、按规则表给下一步路由、只读消费 light-memory 的对象注册统一视图。不重实现任何阶段包的逻辑，不写任何阶段包的文件。

全链：light-literature → light-idea → light-design → light-experiment → light-analysis → light-journal-select（write 前置扩展位）→ light-write → light-figure → light-review，light-memory 横贯全程。

## 快速上手

    light-leader init my-project --name my-project --title "我的课题"
    light-leader status my-project     # 逐阶段状态（只读）
    light-leader route my-project      # 硬门点名 + 下一步建议（只读）
    light-leader registry my-project   # 对象注册统一视图（只读，消费 memory 的 registry-view.json）

项目目录规范、全链接口图、阶段路由规程与跨包纪律见 [SKILL.md](SKILL.md)。

## 状态

**v1.0 已封版**（2026-10-20）。封版记录：layout 阶段规格表 + scaffold / scan / route / registry 四件 + CLI 四命令，32 测试；演示对由各包真实 demo 登记头拼成的项目跑通 init → status → route → registry 全链，route 正确点名 idea / design / analysis / write 四处 REVIEW_UNAVAILABLE 硬门，见 [examples/demo-fullrun/demo-report.md](examples/demo-fullrun/demo-report.md)。

## 许可证

MIT（占位），见 [LICENSE](LICENSE)，署名 light-leader contributors。

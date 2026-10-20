"""light-leader：Light-Science 总控（薄编排层）。

只做四件事：建项目骨架（init）、只读扫描各阶段包登记头（status）、
按规则表给下一步路由（route）、只读消费 Memory 的对象注册统一视图
（registry）。不重实现任何阶段包的内部逻辑，不写任何阶段包的文件。
"""

__version__ = "1.0.0"

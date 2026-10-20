"""light-crawler：Light-Science 的项目数据采集通道层。

定位（LD-02）：通道层扩展位，不进十阶段主流水线；给
light-literature（批量线索与全文获取批）与 light-experiment
（数据集获取批）供数。合规纪律是代码硬门：无登记不抓取、
robots 失败关闭（RFC 9309 第 2.3.1.4 节）、预检分级生效、
速率只按公式取最严、被拒即停并全程留痕。
"""

__version__ = "1.0.0"

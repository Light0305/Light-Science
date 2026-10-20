"""演示用自造代码（脱敏）：时序融合模块的最小示意实现。

仅供 light-patent 演示的 scan-code 盘点与候选证据锚点使用，
不是可运行的科研代码。
"""


class TemporalFusion:
    """滑动窗口注意力时序聚合（示意）。"""

    def __init__(self, window=8):
        self.window = window

    def aggregate(self, frame_features):
        frames = frame_features[-self.window:]
        weights = [1.0 / len(frames)] * len(frames)
        return [sum(w * f for w, f in zip(weights, col))
                for col in zip(*frames)]

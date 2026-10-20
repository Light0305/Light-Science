"""演示用自造代码（脱敏）：个体基线行为分布与异常分数（示意）。"""


class IndividualBaseline:
    """按个体维护行为特征的均值与标准差，给出偏差量。"""

    def __init__(self):
        self.stats = {}

    def update(self, individual_id, vector):
        self.stats.setdefault(individual_id, []).append(vector)

    def deviation(self, individual_id, vector):
        history = self.stats.get(individual_id) or []
        if not history:
            return 0.0
        mean = sum(history) / len(history)
        return abs(vector - mean)

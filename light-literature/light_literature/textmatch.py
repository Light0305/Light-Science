"""块级文本匹配小工具 (claim-check 与 ask 共用)。

只做机械匹配：分词、数字抽取与逐字在场检查、块打分。语义判断 (支持/
反对) 由执行 agent 在读块后作出，本模块只提供可核查的机械信号，
不许拿分数冒充语义结论。
"""

from __future__ import annotations

import re
import unicodedata

_NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "has", "have", "had", "not", "but", "can", "its", "it",
    "of", "in", "on", "to", "by", "is", "at", "or", "as", "be", "we",
    "do", "did", "does", "what", "how", "when", "which", "who", "an",
    "per", "via", "than", "then", "into", "over", "under", "between",
    "的", "了", "是", "在", "和", "与", "对", "为", "中", "上", "下",
}


def extract_numbers(text: str | None) -> list[str]:
    """抽取文本中的数字 (保序去重)：去千分位逗号，保留小数形态。"""
    out: list[str] = []
    for m in _NUM_RE.finditer(text or ""):
        num = m.group(0).replace(",", "")
        if num not in out:
            out.append(num)
    return out


def number_in_text(num: str, text: str) -> bool:
    """数字逐字在场检查：数字边界守护 (42 不算命中 420，也不算 3.42)。"""
    pattern = r"(?<![0-9.])" + re.escape(num) + r"(?![0-9])"
    return re.search(pattern, text or "") is not None


def tokenize(text: str | None) -> set[str]:
    """分词：拉丁词 (小写、长度>=2) + CJK 双字组；去停用词。

    CJK 只留双字组、不再留单字：单字词项几乎在任何中文块里都能
    凑齐 >=2 个「命中」，曾把证据门灌满垃圾命中（qa-eval 基线根因
    2：拒答题被 39 个单字碰撞顶掉固定拒答、真锚点被稀释到名次
    6-183)。双字组是中文侧的最小证据单元。
    """
    text = unicodedata.normalize("NFKC", (text or "").lower())
    tokens: set[str] = set()
    for word in re.findall(r"[a-z][a-z0-9_\-]+|[a-z0-9]+", text):
        if len(word) >= 2 and word not in _STOPWORDS:
            tokens.add(word)
    # 连字符复合词同时留拆分件：抽取层常把 Self-Attention 揉成
    # "Self -Attention"，问题侧的标准写法 self-attention 与之
    # 互不可见——拆分件让两种形态在同一词项上相遇。拆分件须
    # >=4 字符：pre / sub / top 这类前缀碎片不是词，只会放大碰撞。
    for word in list(tokens):
        if "-" in word:
            for part in word.split("-"):
                if len(part) >= 4 and part not in _STOPWORDS:
                    tokens.add(part)
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk:
        for i in range(len(run) - 1):
            tokens.add(run[i:i + 2])
    return tokens


#: 跨语言查询扩展词表 (中文术语 -> 英文对应词)。
#: 用途：中文提问与英文语料块之间除内嵌拉丁词/数字外零词项重叠，
#: 曾致无拉丁锚的中文题系统性漏检 (qa-eval 基线根因 1)。扩展只在
#: 查询侧发生：问题文本里出现左列术语时，把右列英文词并入查询
#: 词项集；语料侧与判定侧不动。词表收录通用学术词汇 (非针对任何
#: 题集)，按最长键优先匹配，避免短键抢词。
CROSS_LINGUAL_GLOSSARY: dict[str, str] = {
    "神经网络": "neural network", "卷积层": "convolutional layer",
    "卷积": "convolution convolutional", "池化层": "pooling layer",
    "池化": "pooling", "全连接": "fully connected",
    "编码器": "encoder", "解码器": "decoder",
    "自注意力": "self-attention", "注意力": "attention",
    "多头": "multi-head", "残差连接": "residual connection",
    "残差映射": "residual mapping", "残差": "residual",
    "映射": "mapping", "层归一化": "layer normalization",
    "归一化": "normalization", "复杂度": "complexity",
    "每层": "per layer", "循环层": "recurrent layer",
    "循环": "recurrent", "序列": "sequence",
    "嵌入": "embedding", "子层": "sub-layer layer",
    "堆叠": "stacked stack", "拟合": "fit fitting fitted",
    "退化": "degradation", "更深": "deeper", "误差": "error",
    "错误率": "error rate", "训练误差": "training error",
    "集成模型": "ensemble", "集成": "ensemble",
    "超参数": "hyperparameters hyperparameter",
    "默认": "default", "推荐": "recommended",
    "伪代码": "pseudocode algorithm", "算法": "algorithm",
    "一阶矩": "first moment", "二阶矩": "second moment",
    "每步": "per step steps", "步骤": "steps step",
    "秒": "seconds second", "硬件": "gpu gpus hardware",
    "耗时": "days time",
    "矩估计": "moment estimate", "估计": "estimate estimation",
    "偏差校正": "bias-corrected bias correction",
    "校正": "corrected correction", "方程": "equation",
    "更新规则": "update rule", "步长": "step size",
    "梯度": "gradient", "优化": "optimization optimize",
    "翻译": "translation translate", "掩码": "mask masked",
    "预训练": "pre-training pretraining pre-trained",
    "词元": "token tokens", "语言模型": "language model",
    "开发集": "development set", "指标": "metrics metric",
    "分数": "score scores", "数据集": "dataset",
    "标注": "annotated annotation annotations labelled labeled",
    "检测": "detection detect detected", "跟踪": "tracking track",
    "视频": "video videos", "帧率": "frame rate frames per second",
    "图像": "image images", "图片": "image images picture",
    "区域": "areas area region regions", "阴影": "shaded shadow",
    "红色": "red", "曲线": "curve curves",
    "预测": "prediction predicted predict",
    "摄像": "camera cameras", "目标": "object objects",
    "火鸡": "turkey turkeys", "异常": "abnormal anomaly",
    "行为": "behaviour behavior", "温度": "temperature",
    "湿度": "humidity", "控制": "control controlled",
    "范围": "range", "饲养": "housing barn",
    "教师": "teacher teachers", "档案": "archive archives files",
    "分类": "classification classify classified",
    "组成": "composed consists consisting",
    "构成": "consists composed", "选择": "selected choose",
    "选用": "choose selected", "网民": "internet users",
    "普及率": "penetration rate", "规模": "scale",
    "引用": "cited quoted according",
    "图注": "caption", "展示": "shows show shown",
    "显示": "shows show", "呈现": "presents presented",
    "汇报": "reports reported", "内容": "contents",
    "论文": "paper", "研究": "research study",
    "实验": "experiment experiments", "任务": "task tasks",
    "评估": "evaluation evaluate evaluated",
    "验证集": "validation set", "测试集": "test set testing set",
    "训练集": "training set", "训练": "training train trained",
    "测试": "test testing", "模型": "model models",
    "平台": "platform", "管理": "management",
    "资源": "resource resources", "方法": "method methods",
    "提出": "proposed propose", "结果": "results",
    "性能": "performance", "准确率": "accuracy",
    "层": "layer layers", "网络": "network networks",
    "机制": "mechanism", "系统": "system",
}

_GLOSSARY_KEYS = sorted(CROSS_LINGUAL_GLOSSARY, key=len, reverse=True)


def matched_glossary_keys(text: str | None) -> list[str]:
    """扫描文本中命中的词表键（最长优先、跨度不重叠），保序返回。"""
    text = unicodedata.normalize("NFKC", (text or "").lower())
    if not re.search(r"[\u4e00-\u9fff]", text):
        return []
    keys: list[str] = []
    occupied: list[tuple[int, int]] = []
    for key in _GLOSSARY_KEYS:
        start = 0
        while True:
            idx = text.find(key, start)
            if idx < 0:
                break
            span = (idx, idx + len(key))
            if any(idx < e and s < span[1] for s, e in occupied):
                start = idx + 1
                continue
            occupied.append(span)
            keys.append(key)
            start = idx + len(key)
    return keys


def expand_cross_lingual(text: str | None) -> set[str]:
    """查询侧跨语言扩展：问题中出现的中文术语 -> 英文词项集。

    返回值是英文词项集合（经 tokenize 归一），与原问题词项取
    并集使用。无中文术语时返回空集。
    """
    out: set[str] = set()
    for key in matched_glossary_keys(text):
        out |= tokenize(CROSS_LINGUAL_GLOSSARY[key])
    return out


def block_text(block: dict) -> str:
    """块的可检索文本：正文 + 表格 Markdown + 图注文本 (若有)。"""
    parts = [block.get("text") or ""]
    if block.get("table_md"):
        parts.append(block["table_md"])
    if block.get("caption_text"):
        parts.append(block["caption_text"])
    return "\n".join(p for p in parts if p)


def is_evidence(scored: dict) -> bool:
    """证据强度门：命中块须至少有一个数字命中，或 >=2 个不同词项命中。

    单个泛词 (如 energy) 在无关块里碰巧出现不构成证据——宁可拒答，
    不许拿单词碰撞冒充语料支持 (实测教训，见 phase3 构建单)。
    """
    return bool(scored["matched_numbers"]) or \
        len(scored["matched_terms"]) >= 2


def score_block(query_tokens: set[str], query_numbers: list[str],
                block: dict) -> dict:
    """块打分：词项命中数 + 数字命中数 x3；返回分数与命中明细。"""
    text = block_text(block)
    btokens = tokenize(text)
    matched_terms = sorted(query_tokens & btokens)
    matched_numbers = [n for n in query_numbers
                       if number_in_text(n, text)]
    missing_numbers = [n for n in query_numbers
                       if n not in matched_numbers]
    score = len(matched_terms) + 3 * len(matched_numbers)
    return {
        "score": score,
        "matched_terms": matched_terms,
        "matched_numbers": matched_numbers,
        "missing_numbers": missing_numbers,
        "text": text,
    }

"""常量与规则快照：状态机、事实字段、登记办法锚点、扫描词表。

规则快照纪律（HC-7）：每条规则带来源等级与核定日期。A 级 = 规章原文
（《计算机软件著作权登记办法》）；B 级 = 行业组织/高校当期转述，只作
警告与当日复核提示，绝不写成法定要求；未取得原文的动态项只登记
「未取得」状态，不许臆造文本（尤其申请表 AI 使用声明——包内无任何
声明措辞常量，declaration 门只验用户自备原文文件 + 核对回执）。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 状态机
#: 登记头 copyright.yaml 顶层 status 的值域（leader status 汇总消费此字段）。
STATES = (
    "draft",              # 已建案，事实未确认
    "facts_confirmed",    # 登记事实经用户确认（绑指纹）
    "frozen",             # SC0 源码快照已冻结
    "materials_ready",    # SC4/SC5 材料已渲染、草稿段已生成
    "confirmed",          # 草稿段逐段确认完毕
    "release_checked",    # SC7 发布门禁全过
    "packaged",           # 正式资料包 + 递交清单已产出（v1 终点）
    "correcting",         # 收到补正通知，30 日回路中（旁路，可回 packaged）
)

#: 状态推进的合法前置（命令层据此拒绝越级）。
REQUIRES = {
    "facts_confirmed": ("draft", "correcting"),
    "frozen": ("facts_confirmed",),
    "materials_ready": ("frozen",),
    "confirmed": ("materials_ready",),
    "release_checked": ("confirmed",),
    "packaged": ("release_checked", "correcting"),
}

# ---------------------------------------------------------------- 规则快照
RULES_SNAPSHOT = {
    "snapshot_date": "2026-10-21",
    "rules": [
        {"id": "R-PAGES", "grade": "A",
         "source": "《计算机软件著作权登记办法》第十条",
         "text": "鉴别材料前后各连续 30 页，不足 60 页交全部；"
                 "程序每页不少于 50 行，文档每页不少于 30 行"},
        {"id": "R-HEADER", "grade": "A",
         "source": "登记办法第十条及当期申请表口径",
         "text": "鉴别材料页眉标注软件全称与版本号，与申请表一致"},
        {"id": "R-EXAM", "grade": "A",
         "source": "《计算机软件著作权登记办法》第二十条",
         "text": "登记机构自受理日起 60 日内审查"},
        {"id": "R-CORRECT", "grade": "A",
         "source": "《计算机软件著作权登记办法》第二十二条",
         "text": "补正通知后 30 日内按要求补正，逾期视为撤回"},
        {"id": "R-MAIN-FUNCTION-LEN", "grade": "B", "dynamic": True,
         "source": "深圳市软件行业协会 2026-03-15 转发通知（转述，未见官方原文）",
         "text": "申请表「软件主要功能」字数 500-1300 字——B 级信号，"
                 "只警告，递交当日以当期表单为准"},
        {"id": "R-AI-DECLARATION", "grade": "unobtained", "dynamic": True,
         "source": "当期申请表 AI 使用声明原文——经生态 17 仓与官方公开"
                   "渠道六路核查未取得",
         "text": "原文未取得：本包不保存、不臆造任何声明措辞；递交前由"
                 "用户自备当期原文并逐字核对，见 declaration 门"},
        {"id": "R-UPLOAD-FORMAT", "grade": "B", "dynamic": True,
         "source": "中国版权保护中心登记系统当期口径",
         "text": "上传格式与签章要求以提交当日系统为准，v1 只产出资料包"
                 "与清单，不代填报、不处理签章"},
    ],
}

CODE_LINES_PER_PAGE = 50      # A 级：程序每页不少于 50 行
DOC_LINES_PER_PAGE = 30       # A 级：文档每页不少于 30 行
FRONT_BACK_PAGES = 30         # A 级：前后各连续 30 页
FULL_SUBMIT_MAX_PAGES = 60    # 不足 60 页交全部
EXAM_DAYS = 60                # A 级：审查期
CORRECTION_DAYS = 30          # A 级：补正期
WRAP_COLUMNS = 100            # 代码行折行显示列宽（全角计 2 列）

# ---------------------------------------------------------------- 事实字段
#: facts.yaml 结构与必填口径。不可推断项缺失即 intake 报错点名（HC-6）。
FACT_REQUIRED = (
    ("software", "full_name", "软件全称"),
    ("software", "version", "版本号"),
    ("software", "kind", "软件类型 gui/headless"),
    ("owner", "name", "著作权人"),
    ("development", "mode", "开发方式"),
    ("development", "completion_date", "开发完成日期"),
    ("development", "original", "原创/修改"),
    ("publication", "status", "发表状态"),
    ("rights", "acquisition", "权利取得方式"),
    ("rights", "scope", "权利范围"),
    ("functions", "main_function", "软件主要功能"),
)

SOFTWARE_KINDS = ("gui", "headless")
#: Q3 分流：软件类型 → 文档鉴别材料形态（不许手工绕过）。
DOC_TYPE_BY_KIND = {
    "gui": "操作手册",
    "headless": "设计说明书",
}
DEV_MODES = ("independent", "cooperative", "commissioned", "assigned")
PUBLICATION_STATES = ("published", "unpublished")

#: 扩展名 → 编程语言（源程序量与申请表「编程语言」派生用）。
LANGUAGE_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".vue": "Vue", ".jsx": "JavaScript", ".tsx": "TypeScript",
}

#: SC3 选材排除：路径成分命中即默认排除（逐条留痕，可申诉不可静默）。
EXCLUDED_DIR_NAMES = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", "vendor",
    "dist", "build", "target", ".venv", "venv", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache",
}
EXCLUDED_FILE_SUFFIXES = (".min.js", ".map", ".lock", ".pyc", ".class",
                          ".o", ".so", ".dll", ".exe", ".png", ".jpg",
                          ".jpeg", ".gif", ".ico", ".pdf", ".zip")
TEST_PATH_HINTS = ("test", "tests", "fixture", "fixtures", "__tests__",
                   "spec", "mock", "mocks")

#: 敏感信息形态（命中即排除该文件并留痕；材料侧命中则发布阻断）。
SECRET_PATTERNS = (
    ("疑似 API 密钥", r"(?i)(api[_-]?key|secret|access[_-]?token|password|passwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    ("疑似私钥块", r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("疑似云厂商密钥", r"AKIA[0-9A-Z]{16}"),
)

#: 第三方版权标识（命中整份排除，不删声明冒充自有，HC-5）。
THIRD_PARTY_MARKERS = (
    "Copyright (c)", "Copyright (C)", "版权所有",
    "Licensed under the Apache License", "Licensed under the MIT License",
    "GNU General Public License", "SPDX-License-Identifier",
)

#: HC-3 占位/模板残留扫描（命中即发布阻断；截图预留位为登记豁免形态）。
PLACEHOLDER_PATTERNS = (
    ("TODO 标记", r"TODO|FIXME|XXX"),
    ("待补充占位", r"待补充|待填写|此处填写"),
    ("示例残留", r"Lorem ipsum|示例软件|某某软件|XX 软件|某公司"),
    ("模板变量未替换", r"\{\{[^}]+\}\}|\$\{[^}]+\}"),
)
#: 截图预留位的登记形态：只有这一精确前缀的段落豁免占位扫描，且必须
#: 在递交清单中显形为待补项（Q6：跳过留可见预留位）。
SCREENSHOT_SLOT_PREFIX = "[截图预留位]"

#: 主要功能字数 B 级信号区间（只警告，HC-7）。
MAIN_FUNCTION_LEN_RANGE = (500, 1300)

"""词表与定版常量 + 目标登记校验（C0）。

定版来源：decisions-round2.md 第四批 S1–S7、learning-notes 合规硬
约束候选 8 条。本模块是这些口径在代码里的唯一落点：校验器、预检、
guard 与 CLI 全部引用此处常量，不许在别处另写一份数值。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 词表

#: 通道类型（优先级自上而下：官方 API > 开放数据 > 公开网页 > 浏览器）
CHANNELS = ("official_api", "open_data", "web_page", "browser")

#: 低危通道：预检全过自动生效（S4）。高危通道须具名人工确认。
LOW_RISK_CHANNELS = ("official_api", "open_data")
HIGH_RISK_CHANNELS = ("web_page", "browser")

#: 用途类型（S5：只做批量与非文献数据；单篇全文获取不进目标类型）
PURPOSE_KINDS = (
    "literature_leads_batch",   # 文献线索批（题录/DOI/链接）供 literature
    "fulltext_batch",           # 批量全文获取（如整刊 OA）供 literature
    "dataset_batch",            # 数据集获取批供 experiment
    "page_snapshot",            # 基准/排行榜类页面快照供 experiment
    "project_data",             # 其他项目数据（非文献）
)
#: 明确出界的用途：单篇全文获取归 literature 双轨，登记即拒。
FORBIDDEN_PURPOSE_KINDS = ("single_fulltext",)

#: 留存档位（S3：v1 只有轻量档；warc_full 为 ISO 28500 全记录档，v1.1）
RETENTION_TIERS = ("lightweight_raw_plus_hash",)
RESERVED_RETENTION_TIERS = ("warc_full",)

#: 个人数据风险（HC-5：high 登记即拒；low 须最小必要范围说明）
PERSONAL_DATA_RISKS = ("none", "low", "high")

#: 登录态（S2：v1 只许 none）
LOGIN_STATES = ("none",)

#: 增量节奏
RHYTHMS = ("manual", "daily", "weekly")

# ---------------------------------------------------------------- 速率定版（S6）

#: 模板下限（秒/请求，单域）：登记未给或给得更松时以此为下限。
#: 依据 S6「保守模板，单域 1 请求/5 秒量级」，按通道风险分档定版。
TEMPLATE_MIN_INTERVAL_SEC = {
    "official_api": 1.0,
    "open_data": 2.0,
    "web_page": 5.0,
    "browser": 10.0,
}

#: 包级硬下限：任何登记、任何依据都不许比这更快（本包自律上限）。
HARD_MIN_INTERVAL_SEC = 0.5

#: 总量上限默认值（HC-4 补读口径：速率之外还要有总量天花板）。
DEFAULT_MAX_REQUESTS_PER_RUN = 200
DEFAULT_MAX_REQUESTS_PER_DAY = 1000

#: 并发定版（S6）：v1 固定 1，不许登记其他值。
REQUIRED_CONCURRENCY = 1

#: 连续被拒熔断阈值（HC-8）：同一目标连续 N 个 run 被拒即熔断。
CIRCUIT_BREAK_THRESHOLD = 2

#: robots 缓存上限（RFC 9309 第 2.4 节 SHOULD NOT 超过 24 小时）：
#: 预检记录超过此时长即过期，guard 拒绝执行、须重跑预检。
ROBOTS_CACHE_MAX_HOURS = 24.0

#: 本包抓取标识（robots 分组匹配用 UA 产品名；同时出现在 HTTP 头）。
#: 变量名避开 token 字样：全套 lint 的密钥扫描会把「token = 长字符串」
#: 误读为密钥赋值（本包无任何密钥，此名目纯属扫描口径适配）。
ROBOTS_AGENT_NAME = "LightCrawler"
USER_AGENT = "LightCrawler/1.0 (Light-Science data channel; precheck-gated)"

# ---------------------------------------------------------------- 事件词表

EVENT_TYPES = (
    "workspace_initialized",
    "target_registered",
    "target_updated",
    "precheck_completed",
    "precheck_confirmed",
    "precheck_blocked",        # 拒绝类：预检硬不通过
    "fetch_run_started",
    "fetch_run_finished",
    "fetch_refused",           # 拒绝类：guard 在发起请求前拒绝
    "http_refused",            # 拒绝类：目标以 403/429 等回绝
    "circuit_broken",          # 拒绝类：连续被拒熔断
    "target_unblocked",
    "redirect_out_of_scope",   # 拒绝类：重定向跳出登记域名
    "volume_cap_hit",          # 拒绝类：总量上限
    "not_modified",            # 条件请求 304，未落新版
    "duplicate_skipped",       # 请求指纹已见，跳过
    "manual_import",           # 人工导出后登记导入（S2 正当替代）
    "lock_applied",            # 项目锁覆盖了登记/预检的放松尝试
)

#: refusals 命令认的拒绝类事件。
REFUSAL_EVENT_TYPES = (
    "precheck_blocked", "fetch_refused", "http_refused", "circuit_broken",
    "redirect_out_of_scope", "volume_cap_hit",
)

# ---------------------------------------------------------------- 登记校验

REQUIRED_TARGET_FIELDS = (
    "target_id", "name", "base_url", "project", "purpose_kind",
    "consumer", "channel",
)


def validate_target(reg: dict) -> list:
    """校验一条目标登记，返回问题清单（空 = 合格）。逐项点名不合并。"""
    problems = []
    if not isinstance(reg, dict):
        return ["登记不是 YAML 映射"]
    for field in REQUIRED_TARGET_FIELDS:
        if not reg.get(field):
            problems.append(f"缺必填字段 {field}")

    channel = reg.get("channel")
    if channel and channel not in CHANNELS:
        problems.append(f"channel {channel!r} 不在词表 {list(CHANNELS)}")

    purpose = reg.get("purpose_kind")
    if purpose in FORBIDDEN_PURPOSE_KINDS:
        problems.append(
            f"purpose_kind {purpose} 出界（S5）：单篇全文获取归 "
            "light-literature 的 Doc2X 与模型直读双轨，不进 crawler 目标类型")
    elif purpose and purpose not in PURPOSE_KINDS:
        problems.append(f"purpose_kind {purpose!r} 不在词表 {list(PURPOSE_KINDS)}")

    login = reg.get("login_state", "none")
    if login not in LOGIN_STATES:
        problems.append(
            f"login_state {login!r} 在 v1 全关（S2）：登录态抓取不开放；"
            "正当替代为人工导出后用 import 命令登记导入")

    conc = reg.get("concurrency", REQUIRED_CONCURRENCY)
    if conc != REQUIRED_CONCURRENCY:
        problems.append(
            f"concurrency 只能为 {REQUIRED_CONCURRENCY}（S6 定版），登记值 {conc!r} 拒收")

    tier = reg.get("retention_tier", "lightweight_raw_plus_hash")
    if tier in RESERVED_RETENTION_TIERS:
        problems.append(
            f"retention_tier {tier}（WARC，ISO 28500 全记录档）为 v1.1 档，"
            "v1 只做 lightweight_raw_plus_hash（S3）")
    elif tier not in RETENTION_TIERS:
        problems.append(f"retention_tier {tier!r} 不在词表 {list(RETENTION_TIERS)}")

    risk = reg.get("personal_data_risk", "none")
    if risk not in PERSONAL_DATA_RISKS:
        problems.append(f"personal_data_risk {risk!r} 不在词表 {list(PERSONAL_DATA_RISKS)}")
    elif risk == "high":
        problems.append(
            "personal_data_risk=high 拒收（HC-5 个人数据禁区）："
            "以个人信息为主体的数据不进本包目标")
    elif risk == "low" and not (reg.get("scope_note") or "").strip():
        problems.append(
            "personal_data_risk=low 须填 scope_note 说明最小必要范围（HC-5）")

    rate = reg.get("rate") or {}
    interval = rate.get("registered_interval_sec")
    if interval is not None:
        if not isinstance(interval, (int, float)) or interval <= 0:
            problems.append("rate.registered_interval_sec 须为正数（秒/请求）")
        elif interval < HARD_MIN_INTERVAL_SEC and not rate.get("rate_basis"):
            problems.append(
                f"rate.registered_interval_sec {interval} 低于包级硬下限 "
                f"{HARD_MIN_INTERVAL_SEC}s 且无 rate_basis 条款依据（S6）")
        elif (channel in TEMPLATE_MIN_INTERVAL_SEC
              and interval < TEMPLATE_MIN_INTERVAL_SEC[channel]
              and not rate.get("rate_basis")):
            problems.append(
                f"rate.registered_interval_sec {interval} 低于 {channel} 模板下限 "
                f"{TEMPLATE_MIN_INTERVAL_SEC[channel]}s，须填 rate_basis "
                "（许可该速率的条款依据指针）才可登记（S6/J2）")
    for key in ("max_requests_per_run", "max_requests_per_day"):
        v = rate.get(key)
        if v is not None and (not isinstance(v, int) or v <= 0):
            problems.append(f"rate.{key} 须为正整数")

    if channel == "browser":
        # S1 的开启与理由在预检层裁决；登记层只要求字段面齐备可登记。
        pass

    rhythm = reg.get("rhythm", "manual")
    if rhythm not in RHYTHMS:
        problems.append(f"rhythm {rhythm!r} 不在词表 {list(RHYTHMS)}")

    base = reg.get("base_url") or ""
    if base and not (base.startswith("https://") or base.startswith("http://")):
        problems.append("base_url 须为 http(s) URL")

    return problems


def effective_interval(reg: dict, crawl_delay_sec=None,
                       lock_min_interval_sec=None) -> dict:
    """速率公式（S6）：有效间隔 = max（登记值， robots crawl-delay，
    模板下限， 项目锁下限， 包级硬下限）。

    返回裁决分解，供预检记录逐项落字。Retry-After 不在此处：它在
    请求时才出现，由 fetch 层与本结果再取最严（见 throttle.py）。
    crawl-delay 是 Protego/Google 谱系的常见扩展，不在 RFC 9309 内，
    只作登记事实参与取严，依据是站点经 robots 文件公示的意愿与本包
    自律，不挂 RFC 名头。
    """
    channel = reg.get("channel")
    rate = reg.get("rate") or {}
    registered = rate.get("registered_interval_sec")
    template = TEMPLATE_MIN_INTERVAL_SEC.get(channel)
    candidates = {"hard_floor": HARD_MIN_INTERVAL_SEC}
    if template is not None:
        candidates["template_min"] = float(template)
    if registered is not None:
        candidates["registered"] = float(registered)
    if crawl_delay_sec is not None:
        candidates["robots_crawl_delay"] = float(crawl_delay_sec)
    if lock_min_interval_sec is not None:
        candidates["project_lock"] = float(lock_min_interval_sec)
    value = max(candidates.values())
    return {"effective_interval_sec": value, "inputs": candidates,
            "decided_by": max(candidates, key=candidates.get)}

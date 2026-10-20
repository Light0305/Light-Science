"""速率执行：请求间隔取严 + Retry-After 解析（S6/HC-8）。

公式：实际等待 = max（预检裁决的有效间隔， Retry-After（若上次响
应给出）)。Retry-After 双形态（秒数 / HTTP 日期）都解析。crawl-delay
不在此处——它已在预检期并入有效间隔，依据是站点公示意愿而非 RFC。
"""

from __future__ import annotations

import time
from datetime import timezone
from email.utils import parsedate_to_datetime

from .util import parse_ts, utcnow


def parse_retry_after(value):
    """解析 Retry-After 头为秒数；不可解析返回 None。"""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = parse_ts(utcnow())
    return max(0.0, (dt - now).total_seconds())


class Throttler:
    """按目标域执行的间隔器。sleep 可注入（测试用记录器代替真睡）。"""

    def __init__(self, effective_interval_sec: float, sleep=time.sleep,
                 clock=time.monotonic):
        self.interval = float(effective_interval_sec)
        self._sleep = sleep
        self._clock = clock
        self._last_at = None
        self.retry_after_sec = None  # 上次响应给出的 Retry-After（取严用）

    def wait(self) -> float:
        """等到可发下一个请求，返回实际等待秒数。首个请求不等。"""
        need = self.interval
        if self.retry_after_sec is not None:
            need = max(need, self.retry_after_sec)
        if self._last_at is None:
            self._last_at = self._clock()
            return 0.0
        elapsed = self._clock() - self._last_at
        wait_for = max(0.0, need - elapsed)
        if wait_for > 0:
            self._sleep(wait_for)
        self._last_at = self._clock()
        return wait_for

    def note_response(self, headers: dict) -> None:
        ra = None
        for k, v in (headers or {}).items():
            if k.lower() == "retry-after":
                ra = parse_retry_after(v)
        self.retry_after_sec = ra

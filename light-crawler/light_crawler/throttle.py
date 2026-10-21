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
    """按目标域执行的间隔器。sleep 可注入（测试用记录器代替真睡）。

    自适应（能力强化批）：base_interval 是预检裁决的有效间隔，
    自适应只许在其上加严或向它回落，永不低于它——礼貌不是给
    速率公式开口子。服务器错误/网络错误使当前间隔乘性加严
    （上限 max_interval），连续成功 3 次后逐步回落向基线。
    """

    BACKOFF_FACTOR = 1.5
    RECOVER_FACTOR = 1.25
    RECOVER_STREAK = 3

    def __init__(self, effective_interval_sec: float, sleep=time.sleep,
                 clock=time.monotonic, max_interval_sec: float = 300.0):
        self.base_interval = float(effective_interval_sec)
        self.interval = float(effective_interval_sec)
        self.max_interval = float(max_interval_sec)
        self._sleep = sleep
        self._clock = clock
        self._last_at = None
        self.retry_after_sec = None  # 上次响应给出的 Retry-After（取严用）
        self._ok_streak = 0
        self.adaptations = []  # (kind, old, new) 自适应留痕

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

    def note_outcome(self, kind: str) -> float:
        """记录一次请求结局并自适应当前间隔，返回新间隔。

        kind: ok / server_error / network_error。加严立即生效；
        回落须连续成功 RECOVER_STREAK 次，且永不低于 base。
        """
        if kind in ("server_error", "network_error"):
            self._ok_streak = 0
            new = min(self.max_interval,
                      max(self.interval * self.BACKOFF_FACTOR,
                          self.interval + 1.0))
            if new != self.interval:
                self.adaptations.append((kind, self.interval, new))
                self.interval = new
        elif kind == "ok":
            self._ok_streak += 1
            if self._ok_streak >= self.RECOVER_STREAK \
                    and self.interval > self.base_interval:
                new = max(self.base_interval,
                          self.interval / self.RECOVER_FACTOR)
                self.adaptations.append((kind, self.interval, new))
                self.interval = new
                self._ok_streak = 0
        return self.interval

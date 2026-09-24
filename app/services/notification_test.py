"""Rate-limited real test sends for account notification rules.

``NotificationSender`` knows how to talk to one channel; it does not know which
rule belongs to which user.  This service resolves the rule through
``db_manager.get_notification_test_target`` (which validates ownership) and
keeps the outbound call rate limited, because every test sends a real message
to a third-party service.
"""

from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from typing import Any

from loguru import logger

from .notification_channels import NotificationChannelConfigError
from .notification_sender import NotificationSendError, NotificationSender


class NotificationTestError(RuntimeError):
    """A safe, user-facing test-send failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "notification_send_failed",
        status_code: int = 400,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.public_message = message
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after

    def detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": self.public_message}
        if self.retry_after:
            detail["retry_after"] = self.retry_after
        return detail


class NotificationTestRateLimiter:
    """Fixed-window limiter keyed per user and rule."""

    def __init__(self, *, window_seconds: float = 60.0, max_attempts: int = 5) -> None:
        self.window_seconds = window_seconds
        self.max_attempts = max_attempts
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def acquire(self, key: str) -> float:
        """Return 0 when the attempt is allowed, else seconds until a slot frees."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                return self.window_seconds - (now - hits[0])
            hits.append(now)
            return 0.0


notification_test_rate_limiter = NotificationTestRateLimiter()


class NotificationTestService:
    """Send one real notification through the channel bound to a rule."""

    def __init__(
        self,
        db_manager: Any,
        *,
        sender: NotificationSender | None = None,
        limiter: NotificationTestRateLimiter | None = None,
    ) -> None:
        self.db_manager = db_manager
        self.sender = sender or NotificationSender()
        self.limiter = limiter

    async def send_rule_test(
        self,
        rule_id: int,
        user_id: int,
        user_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._check_rate_limit(rule_id, user_id)

        # 该查询同时校验规则、渠道和闲鱼账号归属，且刻意不按启用状态过滤，
        # 这样停用的规则也能用来排查渠道连通性。
        target = self.db_manager.get_notification_test_target(rule_id, user_id)
        if not target:
            raise NotificationTestError(
                "通知规则不存在或不属于当前用户",
                code="notification_rule_not_found",
                status_code=404,
            )

        request_id = uuid.uuid4().hex
        started = time.monotonic()
        try:
            receipt = await self.sender.send(
                target["channel_type"],
                target["channel_config"],
                self._message(target, request_id),
                request_id=request_id,
            )
        except NotificationChannelConfigError as exc:
            self._log("config_invalid", rule_id, user_info, target)
            raise NotificationTestError(
                str(exc),
                code=exc.code,
                status_code=422,
            ) from exc
        except NotificationSendError as exc:
            self._log("send_failed", rule_id, user_info, target)
            raise NotificationTestError(
                exc.public_message,
                code=exc.code,
                status_code=502,
            ) from exc

        self._log("success", rule_id, user_info, target)
        return {
            "success": True,
            "message": "测试通知已发送",
            "request_id": request_id,
            "channel": {
                "id": target["channel_id"],
                "name": target["channel_name"],
                "type": receipt.channel_type,
            },
            "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    def _check_rate_limit(self, rule_id: int, user_id: int) -> None:
        if not self.limiter:
            return
        wait = self.limiter.acquire(f"{user_id}:{rule_id}")
        if wait > 0:
            raise NotificationTestError(
                "测试发送过于频繁，请稍后重试",
                code="notification_test_rate_limited",
                status_code=429,
                retry_after=max(1, math.ceil(wait)),
            )

    @staticmethod
    def _message(target: dict[str, Any], request_id: str) -> str:
        rule_name = str(target.get("name") or "").strip() or f"#{target['id']}"
        return (
            "【闲鱼超级管家】通知渠道测试\n"
            f"闲鱼账号：{target['cookie_id']}\n"
            f"通知规则：{rule_name}\n"
            f"请求 ID：{request_id}"
        )

    @staticmethod
    def _log(result: str, rule_id: int, user_info: Any, target: dict[str, Any]) -> None:
        # 渠道配置含 webhook 密钥和 SMTP 密码，任何分支都不落日志。
        logger.info(
            f"source=notification_test rule_id={rule_id} "
            f"user={((user_info or {}).get('username')) or ''} "
            f"channel_type={target['channel_type']} result={result}"
        )

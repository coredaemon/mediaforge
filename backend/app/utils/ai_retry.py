from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from .ai_errors import is_retryable_error

T = TypeVar("T")

RETRY_BACKOFF_SECONDS = (1, 2)


class RetryExhaustedError(Exception):
    def __init__(self, original: Exception, attempts: int, duration_ms: int) -> None:
        self.original = original
        self.attempts = attempts
        self.duration_ms = duration_ms
        super().__init__(str(original))


async def execute_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int | Callable[[Exception], int] = 3,
    started: float | None = None,
) -> tuple[T, int]:
    started_at = started if started is not None else time.perf_counter()
    last_exc: Exception | None = None
    current_max_attempts = 1 if callable(max_attempts) else max_attempts
    attempt = 0
    while attempt < current_max_attempts:
        if attempt > 0:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])
        try:
            return await operation(), attempt + 1
        except Exception as exc:
            last_exc = exc
            if callable(max_attempts):
                current_max_attempts = max(1, max_attempts(exc))
            if attempt + 1 < current_max_attempts and is_retryable_error(exc):
                continue
            duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
            raise RetryExhaustedError(exc, attempts=attempt + 1, duration_ms=duration_ms) from exc
        finally:
            attempt += 1
    if last_exc is not None:
        duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        raise RetryExhaustedError(last_exc, attempts=current_max_attempts, duration_ms=duration_ms) from last_exc
    raise RuntimeError("execute_with_retry finished without result")


async def post_with_retry(
    url: str,
    *,
    timeout: float,
    params: dict | None = None,
    json: dict | None = None,
    headers: dict | None = None,
    max_attempts: int | Callable[[Exception], int] = 3,
) -> tuple[httpx.Response, int]:
    started = time.perf_counter()

    async def _post() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, params=params, json=json, headers=headers)
            response.raise_for_status()
            return response

    response, attempts = await execute_with_retry(_post, max_attempts=max_attempts, started=started)
    return response, attempts

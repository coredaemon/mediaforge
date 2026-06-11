from __future__ import annotations

import re

import httpx

from ..schemas.recognition import LlmPreflightCheck

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def sanitize_error_text(value: str) -> str:
    value = re.sub(r"([?&]key=)[^&\s']+", r"\1[redacted]", value)
    value = re.sub(r"(Bearer\s+)[A-Za-z0-9._-]+", r"\1[redacted]", value, flags=re.IGNORECASE)
    return value


def extract_status_code(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def is_retryable_error(exc: Exception) -> bool:
    status = extract_status_code(exc)
    if status is not None and status in RETRYABLE_STATUS_CODES:
        return True
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            httpx.PoolTimeout,
        ),
    ):
        return True
    return False


def classify_error_type(exc: Exception) -> str:
    status = extract_status_code(exc)
    if status == 429:
        return "rate_limited"
    if status in {500, 502, 503, 504}:
        return "temporary_unavailable"
    if status in {401, 403}:
        return "auth_error"
    if status == 404:
        return "model_not_found"
    if status == 400:
        return "invalid_request"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.ReadError)):
        return "connection_error"
    return exc.__class__.__name__


def humanize_ai_error(
    error: str | None = None,
    status_code: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    error_type: str | None = None,
) -> str:
    if error_type == "not_configured":
        return "Облачная модель не настроена. Выберите провайдер и модель в настройках."
    if error_type == "invalid_json":
        return "Облачная модель ответила, но JSON некорректен. Попробуйте другую модель."
    if error_type == "unexpected_payload":
        return "Облачная модель ответила в неожиданном формате."
    if status_code == 503 or error_type == "temporary_unavailable":
        return "Облачная модель временно недоступна. Попробуйте ещё раз позже или выберите другую модель."
    if status_code == 429 or error_type == "rate_limited":
        return "Превышен лимит запросов к облачной модели. Попробуйте позже или выберите запасную модель."
    if status_code in {401, 403} or error_type == "auth_error":
        return "API-ключ не принят провайдером. Проверьте ключ в настройках."
    if status_code == 404 or error_type == "model_not_found":
        return "Модель не найдена у провайдера. Нажмите «Найти модели» и выберите модель из списка."
    if error_type == "timeout" or (error and "timeout" in error.lower()):
        return "Облачная модель не ответила вовремя. Можно попробовать ещё раз или выбрать более быструю модель."
    if error_type == "connection_error":
        return "Не удалось подключиться к облачной модели. Проверьте сеть и настройки провайдера."
    if error and "503" in error:
        return "Облачная модель временно недоступна. Попробуйте ещё раз позже или выберите другую модель."
    if error:
        return "Ошибка облачной модели. Откройте технические детали для подробностей."
    return "Ошибка облачной модели."


def enrich_preflight_check(check: LlmPreflightCheck) -> LlmPreflightCheck:
    if check.ok:
        return check
    updates: dict[str, object] = {}
    if not check.human_message:
        status_code = None
        if check.error:
            match = re.search(r"\b(429|500|502|503|504)\b", check.error)
            if match:
                status_code = int(match.group(1))
        updates["human_message"] = humanize_ai_error(
            check.error,
            status_code=status_code,
            provider=check.provider,
            model=check.model,
            error_type=check.error_type,
        )
    if check.error_type in {"temporary_unavailable", "rate_limited", "timeout", "connection_error"}:
        updates["retryable"] = True
    return check.model_copy(update=updates) if updates else check


def build_preflight_failure_message(
    local: LlmPreflightCheck,
    cloud: LlmPreflightCheck,
    cloud_fallback: LlmPreflightCheck | None,
) -> str | None:
    if not local.ok:
        return local.human_message or local.error or "Локальная AI-модель не отвечает."
    cloud_ok = cloud.ok or (cloud_fallback.ok if cloud_fallback else False)
    if cloud_ok:
        return None
    if cloud_fallback is None:
        return "Запасная модель не настроена. Настройте её или повторите проверку основной модели позже."
    if cloud_fallback and not cloud_fallback.ok:
        if cloud.retryable and cloud_fallback.retryable:
            return (
                "Локальная модель работает, но облачные модели временно недоступны. "
                "Без облачного fallback анализ остановлен."
            )
        return (
            cloud.human_message
            or cloud_fallback.human_message
            or "Облачные модели недоступны. Без облачного fallback анализ остановлен."
        )
    return cloud.human_message or cloud.error


def build_preflight_warning(
    cloud: LlmPreflightCheck,
    cloud_fallback: LlmPreflightCheck | None,
) -> str | None:
    if cloud.ok:
        return None
    if not cloud_fallback or not cloud_fallback.ok:
        return None
    if cloud.retryable or cloud.error_type == "temporary_unavailable":
        return "Основная облачная модель временно недоступна, будет использоваться запасная."
    return "Основная облачная модель недоступна, будет использоваться запасная."

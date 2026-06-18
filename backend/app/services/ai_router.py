from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..repositories.app_settings_repository import AppSettingsRepository
from ..utils.ai_errors import sanitize_error_text
from .openrouter_client import OPENROUTER_BASE_URL, OpenRouterClient

AiQualityGate = Callable[[dict[str, Any]], tuple[bool, str | None]]


@dataclass
class AiModelAttempt:
    model: str
    ok: bool
    duration_ms: int
    error: str | None = None
    response_valid_json: bool = False


@dataclass
class AiRouterResult:
    ok: bool
    provider: str
    model: str | None
    attempted_models: list[AiModelAttempt] = field(default_factory=list)
    normalized_json: dict[str, Any] | None = None
    raw_response: str | None = None
    human_message: str | None = None
    technical_error: str | None = None
    duration_ms: int = 0


class AiChainExecutor:
    def __init__(self, client: OpenRouterClient) -> None:
        self.client = client

    async def run_json(
        self,
        *,
        models: list[str],
        messages: list[dict[str, str]],
        quality_gate: AiQualityGate | None = None,
    ) -> AiRouterResult:
        started = time.perf_counter()
        attempts: list[AiModelAttempt] = []
        last_error = "No models configured."
        for model in [m.strip() for m in models if m.strip()]:
            model_started = time.perf_counter()
            try:
                chat = await self.client.chat_json(model=model, messages=messages)
                parsed = extract_json_object(chat.content)
                if parsed is None:
                    last_error = "Response was not valid JSON."
                    attempts.append(
                        AiModelAttempt(
                            model=model,
                            ok=False,
                            duration_ms=chat.duration_ms,
                            error=last_error,
                            response_valid_json=False,
                        )
                    )
                    continue
                if quality_gate is not None:
                    passed, reason = quality_gate(parsed)
                    if not passed:
                        last_error = reason or "Quality gate failed."
                        attempts.append(
                            AiModelAttempt(
                                model=model,
                                ok=False,
                                duration_ms=chat.duration_ms,
                                error=last_error,
                                response_valid_json=True,
                            )
                        )
                        continue
                attempts.append(
                    AiModelAttempt(model=model, ok=True, duration_ms=chat.duration_ms, response_valid_json=True)
                )
                return AiRouterResult(
                    ok=True,
                    provider="openrouter",
                    model=model,
                    attempted_models=attempts,
                    normalized_json=parsed,
                    raw_response=_sanitize_preview(chat.content),
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                )
            except Exception as exc:
                last_error = sanitize_error_text(str(exc))
                attempts.append(
                    AiModelAttempt(
                        model=model,
                        ok=False,
                        duration_ms=max(0, int((time.perf_counter() - model_started) * 1000)),
                        error=last_error,
                    )
                )
        return AiRouterResult(
            ok=False,
            provider="openrouter",
            model=None,
            attempted_models=attempts,
            human_message="OpenRouter model chain failed; MediaForge will use legacy or deterministic fallback.",
            technical_error=last_error,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )


class AiRouterService:
    def __init__(self, session) -> None:
        self.settings = AppSettingsRepository(session)

    async def openrouter_executor(self) -> AiChainExecutor | None:
        settings = await self.settings.get_or_create()
        if not settings.openrouter_api_key:
            return None
        return AiChainExecutor(
            OpenRouterClient(settings.openrouter_api_key, settings.openrouter_base_url or OPENROUTER_BASE_URL)
        )


def extract_json_object(value: str) -> dict[str, Any] | None:
    text = value.strip()
    if not text:
        return None
    if "```" in text:
        import re

        match = re.search(r"```(?:json)?\s*(?P<body>.*?)```", text, re.I | re.S)
        if match:
            text = match.group("body").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_model_chain(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def dump_model_chain(value: list[str] | None) -> str | None:
    if value is None:
        return None
    return json.dumps([item.strip() for item in value if item.strip()], ensure_ascii=False)


def _sanitize_preview(value: str) -> str:
    value = sanitize_error_text(value.replace("\r", " ").replace("\n", " ").strip())
    return value[:2000]

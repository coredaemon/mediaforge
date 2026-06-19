import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..schemas.recognition import LlmPreflightCheck, NormalizedTitle
from ..schemas.recognition_context import RecognitionContext
from ..utils.ai_errors import (
    classify_error_type,
    extract_status_code,
    humanize_ai_error,
    is_retryable_error,
    sanitize_error_text,
)
from ..utils.ai_response_normalization import coerce_normalized_title
from ..utils.ai_retry import RetryExhaustedError, execute_with_retry, post_with_retry

_TIMEOUT_SECONDS = 90.0
_PREFLIGHT_TEST = "mediaforge-preflight"


@dataclass
class NormalizeParseResult:
    title: NormalizedTitle
    warnings: list[str] = field(default_factory=list)


class TitleNormalizerClient(Protocol):
    async def normalize(
        self,
        original_name: str,
        parser_title: str | None,
        parser_year: int | None,
        context: RecognitionContext | None = None,
    ) -> NormalizeParseResult:
        """Return a normalized title suggestion for one media item."""

    async def preflight(self, expected_provider: str) -> LlmPreflightCheck:
        """Run a real generation request and validate the JSON response."""


class OllamaTitleNormalizer:
    def __init__(self, base_url: str, model: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "gemma3"

    async def normalize(
        self,
        original_name: str,
        parser_title: str | None,
        parser_year: int | None,
        context: RecognitionContext | None = None,
    ) -> NormalizeParseResult:
        payload = {
            "model": self.model,
            "prompt": _prompt(original_name, parser_title, parser_year, context),
            "stream": False,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            body = response.json().get("response", "{}")
        return _parse_normalized_json(body, parser_title=parser_title, parser_year=parser_year)

    async def preflight(self, expected_provider: str = "local") -> LlmPreflightCheck:
        started = time.perf_counter()
        try:
            payload = {
                "model": self.model,
                "prompt": _preflight_prompt(expected_provider),
                "stream": False,
                "format": "json",
            }
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                text = response.json().get("response", "")
            return _validate_preflight_response(
                text,
                expected_provider=expected_provider,
                provider="ollama",
                model=self.model,
                endpoint=self.base_url,
                duration_ms=_duration_ms(started),
            )
        except Exception as exc:
            return _failed_preflight("ollama", self.model, self.base_url, started, exc)


class OpenAICompatibleTitleNormalizer:
    def __init__(
        self,
        base_url: str,
        model: str | None,
        api_key: str | None = None,
        *,
        provider_name: str = "openai-compatible",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "local-model"
        self.api_key = api_key
        self.provider_name = provider_name

    async def normalize(
        self,
        original_name: str,
        parser_title: str | None,
        parser_year: int | None,
        context: RecognitionContext | None = None,
    ) -> NormalizeParseResult:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": _prompt(original_name, parser_title, parser_year, context)}],
            "temperature": 0,
        }
        if self.api_key:
            response, _ = await post_with_retry(
                _openai_compatible_url(self.base_url, "chat/completions"),
                timeout=_TIMEOUT_SECONDS,
                json=payload,
                headers=headers,
            )
            body = response.json()["choices"][0]["message"]["content"]
        else:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(_openai_compatible_url(self.base_url, "chat/completions"), json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()["choices"][0]["message"]["content"]
        return _parse_normalized_json(body, parser_title=parser_title, parser_year=parser_year)

    async def preflight(self, expected_provider: str = "local") -> LlmPreflightCheck:
        started = time.perf_counter()
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": _preflight_prompt(expected_provider)}],
                "temperature": 0,
            }
            if self.api_key:
                response, attempts = await post_with_retry(
                    _openai_compatible_url(self.base_url, "chat/completions"),
                    timeout=_TIMEOUT_SECONDS,
                    json=payload,
                    headers=headers,
                )
                text = response.json()["choices"][0]["message"]["content"]
                duration_ms = _duration_ms(started)
            else:
                attempts = 1
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    response = await client.post(_openai_compatible_url(self.base_url, "chat/completions"), json=payload, headers=headers)
                    response.raise_for_status()
                    text = response.json()["choices"][0]["message"]["content"]
                duration_ms = _duration_ms(started)
            return _validate_preflight_response(
                text,
                expected_provider=expected_provider,
                provider=self.provider_name,
                model=self.model,
                endpoint=self.base_url,
                duration_ms=duration_ms,
                attempts=attempts,
            )
        except Exception as exc:
            return _failed_preflight(self.provider_name, self.model, self.base_url, started, exc)


class OpenRouterChainTitleNormalizer:
    def __init__(self, api_key: str, base_url: str, models: list[str], stage: str) -> None:
        from .ai_router import AiChainExecutor
        from .openrouter_client import OpenRouterClient

        self.base_url = base_url.rstrip("/")
        self.models = [model for model in models if model]
        self.model = self.models[0] if self.models else None
        self.stage = stage
        self.executor = AiChainExecutor(OpenRouterClient(api_key, self.base_url))

    async def normalize(
        self,
        original_name: str,
        parser_title: str | None,
        parser_year: int | None,
        context: RecognitionContext | None = None,
    ) -> NormalizeParseResult:
        if not self.models:
            raise ValueError("OpenRouter model chain is empty.")
        result = await self.executor.run_json(
            models=self.models,
            messages=[{"role": "user", "content": _prompt(original_name, parser_title, parser_year, context)}],
            quality_gate=lambda data: (bool(data.get("clean_title") or data.get("tmdb_queries")), "No usable title or TMDB query."),
        )
        if not result.ok or result.normalized_json is None:
            raise ValueError(result.technical_error or result.human_message or "OpenRouter chain failed.")
        title, warnings = coerce_normalized_title(
            result.normalized_json,
            parser_title=parser_title,
            parser_year=parser_year,
        )
        fallback_count = max(0, len(result.attempted_models) - 1)
        if fallback_count:
            warnings.append(f"OpenRouter used fallback model after {fallback_count} failed attempt(s).")
        self.model = result.model
        return NormalizeParseResult(title=title, warnings=warnings)

    async def preflight(self, expected_provider: str = "local") -> LlmPreflightCheck:
        started = time.perf_counter()
        if not self.models:
            return LlmPreflightCheck(
                ok=False,
                provider="openrouter",
                endpoint=self.base_url,
                error="OpenRouter model chain is empty.",
                error_type="not_configured",
            )
        result = await self.executor.run_json(
            models=self.models,
            messages=[{"role": "user", "content": _preflight_prompt(expected_provider)}],
            quality_gate=lambda data: (
                data.get("ok") is True and data.get("test") == _PREFLIGHT_TEST,
                "Preflight JSON did not match expected fields.",
            ),
        )
        if result.ok:
            self.model = result.model
            return LlmPreflightCheck(
                ok=True,
                provider="openrouter",
                model=result.model,
                endpoint=self.base_url,
                duration_ms=result.duration_ms,
                response_valid_json=True,
                message=f"OpenRouter {self.stage} chain responded successfully",
                attempts=len(result.attempted_models),
                attempted_models=_attempts_payload(result.attempted_models),
            )
        return LlmPreflightCheck(
            ok=False,
            provider="openrouter",
            model=self.model,
            endpoint=self.base_url,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            response_valid_json=False,
            error=result.technical_error,
            human_message=result.human_message,
            error_type="chain_failed",
            attempts=max(1, len(result.attempted_models)),
            attempted_models=_attempts_payload(result.attempted_models),
            retryable=True,
        )


class GeminiTitleNormalizer:
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or "gemini-2.0-flash"

    async def normalize(
        self,
        original_name: str,
        parser_title: str | None,
        parser_year: int | None,
        context: RecognitionContext | None = None,
    ) -> NormalizeParseResult:
        payload = {"contents": [{"parts": [{"text": _prompt(original_name, parser_title, parser_year, context)}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        response, _ = await post_with_retry(
            url,
            timeout=_TIMEOUT_SECONDS,
            params={"key": self.api_key},
            json=payload,
        )
        parts = response.json()["candidates"][0]["content"]["parts"]
        body = "".join(part.get("text", "") for part in parts)
        return _parse_normalized_json(body, parser_title=parser_title, parser_year=parser_year)

    async def preflight(self, expected_provider: str = "gemini") -> LlmPreflightCheck:
        started = time.perf_counter()
        try:
            payload = {"contents": [{"parts": [{"text": _preflight_prompt(expected_provider)}]}]}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            response, attempts = await post_with_retry(
                url,
                timeout=_TIMEOUT_SECONDS,
                params={"key": self.api_key},
                json=payload,
            )
            parts = response.json()["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
            return _validate_preflight_response(
                text,
                expected_provider=expected_provider,
                provider="gemini",
                model=self.model,
                endpoint="https://generativelanguage.googleapis.com/v1beta",
                duration_ms=_duration_ms(started),
                attempts=attempts,
            )
        except Exception as exc:
            return _failed_preflight("gemini", self.model, None, started, exc)


def _parse_normalized_json(
    value: str,
    *,
    parser_title: str | None = None,
    parser_year: int | None = None,
) -> NormalizeParseResult:
    parsed = _extract_json(value)
    if parsed.data is None:
        raise json.JSONDecodeError("Response was not valid JSON.", value, 0)
    title, warnings = coerce_normalized_title(
        parsed.data,
        parser_title=parser_title,
        parser_year=parser_year,
    )
    return NormalizeParseResult(title=title, warnings=warnings)


def _preflight_prompt(expected_provider: str) -> str:
    provider = "gemini" if expected_provider == "gemini" else "local"
    return (
        "You are MediaForge recognition preflight.\n"
        "Return only valid JSON, no markdown:\n"
        f'{{"ok":true,"provider":"{provider}","test":"{_PREFLIGHT_TEST}"}}'
    )


def _validate_preflight_response(
    text: str,
    expected_provider: str,
    provider: str,
    model: str | None,
    endpoint: str | None,
    duration_ms: int,
    attempts: int = 1,
) -> LlmPreflightCheck:
    preview = _sanitize_preview(text)
    parsed = _extract_json(text)
    expected = "gemini" if expected_provider == "gemini" else "local"
    if parsed.data is None:
        return LlmPreflightCheck(
            ok=False,
            provider=provider,
            model=model,
            endpoint=endpoint,
            duration_ms=duration_ms,
            response_valid_json=False,
            response_had_markdown=parsed.had_markdown,
            response_preview=preview,
            error="Response was not valid JSON.",
            error_type="invalid_json",
        )
    ok = parsed.data.get("ok") is True
    provider_ok = parsed.data.get("provider") == expected
    test_ok = parsed.data.get("test") == _PREFLIGHT_TEST
    return LlmPreflightCheck(
        ok=ok and provider_ok and test_ok,
        provider=provider,
        model=model,
        endpoint=endpoint,
        duration_ms=duration_ms,
        response_valid_json=True,
        response_had_markdown=parsed.had_markdown,
        response_preview=preview,
        message=f"{provider} responded successfully" if ok and provider_ok and test_ok else None,
        error=None if ok and provider_ok and test_ok else "Preflight JSON did not match expected fields.",
        error_type=None if ok and provider_ok and test_ok else "unexpected_payload",
        attempts=attempts,
        retryable=False,
    )


def _failed_preflight(
    provider: str,
    model: str | None,
    endpoint: str | None,
    started: float,
    exc: Exception,
) -> LlmPreflightCheck:
    attempts = 1
    duration_ms = _duration_ms(started)
    original = exc
    if isinstance(exc, RetryExhaustedError):
        original = exc.original
        attempts = exc.attempts
        duration_ms = exc.duration_ms
    status_code = extract_status_code(original)
    error_type = classify_error_type(original)
    technical = sanitize_error_text(str(original))
    human = humanize_ai_error(
        technical,
        status_code=status_code,
        provider=provider,
        model=model,
        error_type=error_type,
    )
    return LlmPreflightCheck(
        ok=False,
        provider=provider,
        model=model,
        endpoint=endpoint,
        duration_ms=duration_ms,
        response_valid_json=False,
        error=technical,
        human_message=human,
        error_type=error_type,
        attempts=attempts,
        retryable=is_retryable_error(original),
    )


@dataclass
class ParsedJson:
    data: dict[str, Any] | None
    had_markdown: bool


def _extract_json(text: str) -> ParsedJson:
    stripped = text.strip()
    had_markdown = "```" in stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start : end + 1]
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return ParsedJson(data=None, had_markdown=had_markdown)
    return ParsedJson(data=data if isinstance(data, dict) else None, had_markdown=had_markdown)


def _sanitize_preview(text: str) -> str:
    preview = text.replace("\r", " ").replace("\n", " ").strip()
    if len(preview) > 240:
        preview = f"{preview[:237]}..."
    return preview


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _attempts_payload(attempts) -> list[dict[str, Any]]:
    return [
        {
            "model": attempt.model,
            "ok": attempt.ok,
            "duration_ms": attempt.duration_ms,
            "attempts": attempt.attempts,
            "http_status": attempt.http_status,
            "error_type": attempt.error_type,
            "error": attempt.error,
            "human_message": attempt.human_message,
            "response_valid_json": attempt.response_valid_json,
        }
        for attempt in attempts
    ]


def _openai_compatible_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    prefix = "" if base.endswith("/v1") else "/v1"
    return f"{base}{prefix}/{path.lstrip('/')}"


def _prompt(
    original_name: str,
    parser_title: str | None,
    parser_year: int | None,
    context: RecognitionContext | None = None,
) -> str:
    context = context or RecognitionContext()
    context_lines = [
        f"Original filename: {original_name!r}.",
        f"Parser title: {parser_title!r}. Parser year: {parser_year!r}.",
        f"Folder name: {context.folder_name!r}.",
        f"Sidecar title: {context.sidecar_title!r}. Sidecar year: {context.sidecar_year!r}.",
        f"Sidecar overview: {(context.sidecar_overview or '')[:300]!r}.",
        f"Sidecar IDs: tmdb={context.sidecar_tmdb_id}, imdb={context.sidecar_imdb_id}, tvdb={context.sidecar_tvdb_id}.",
        f"Sidecar source: {context.sidecar_source_path!r}.",
        f"Local poster: {context.local_poster_path!r}. Local backdrop: {context.local_backdrop_path!r}.",
        f"Memory IDs: tmdb={context.memory_tmdb_id}, imdb={context.memory_imdb_id}, tvdb={context.memory_tvdb_id}.",
        f"Failed TMDB queries: {context.failed_tmdb_queries}.",
        f"Language preference: {context.language_preference}.",
    ]
    return (
        "Normalize a media filename for TMDB search.\n"
        "If a reliable external ID exists in sidecar or memory context, do not ignore it.\n"
        "Prefer external IDs over title guesses. AI must not replace ID lookup.\n"
        "For Russian/Cyrillic titles, preserve Cyrillic in clean_title and first tmdb_queries entry.\n"
        "Do not translate Russian title to English unless it is original title or fallback query.\n"
        "Return JSON exactly in this shape:\n"
        "{\n"
        '  "media_type": "movie",\n'
        '  "clean_title": "Отец",\n'
        '  "year": 2026,\n'
        '  "season": null,\n'
        '  "episode": null,\n'
        '  "junk_tokens": ["AMZN", "REPACK", "1080p"],\n'
        '  "tmdb_queries": ["Отец 2026", "Отец"],\n'
        '  "confidence": 0.82,\n'
        '  "needs_review": true,\n'
        '  "explanation": "..."\n'
        "}\n"
        "tmdb_queries MUST be an array of strings.\n"
        "Do not return objects inside tmdb_queries.\n"
        "Do not return markdown.\n"
        "Remove release groups, streaming tags, quality/audio/video codecs, and team names.\n"
        + "\n".join(context_lines)
    )

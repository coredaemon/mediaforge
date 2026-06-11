import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..schemas.recognition import LlmPreflightCheck, NormalizedTitle
from ..utils.ai_response_normalization import coerce_normalized_title

_TIMEOUT_SECONDS = 90.0
_PREFLIGHT_TEST = "mediaforge-preflight"


@dataclass
class NormalizeParseResult:
    title: NormalizedTitle
    warnings: list[str] = field(default_factory=list)


class TitleNormalizerClient(Protocol):
    async def normalize(
        self, original_name: str, parser_title: str | None, parser_year: int | None
    ) -> NormalizeParseResult:
        """Return a normalized title suggestion for one media item."""

    async def preflight(self, expected_provider: str) -> LlmPreflightCheck:
        """Run a real generation request and validate the JSON response."""


class OllamaTitleNormalizer:
    def __init__(self, base_url: str, model: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "gemma3"

    async def normalize(
        self, original_name: str, parser_title: str | None, parser_year: int | None
    ) -> NormalizeParseResult:
        payload = {
            "model": self.model,
            "prompt": _prompt(original_name, parser_title, parser_year),
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
    def __init__(self, base_url: str, model: str | None, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "local-model"
        self.api_key = api_key

    async def normalize(
        self, original_name: str, parser_title: str | None, parser_year: int | None
    ) -> NormalizeParseResult:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": _prompt(original_name, parser_title, parser_year)}],
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers)
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
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
            return _validate_preflight_response(
                text,
                expected_provider=expected_provider,
                provider="openai-compatible",
                model=self.model,
                endpoint=self.base_url,
                duration_ms=_duration_ms(started),
            )
        except Exception as exc:
            return _failed_preflight("openai-compatible", self.model, self.base_url, started, exc)


class GeminiTitleNormalizer:
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or "gemini-2.0-flash"

    async def normalize(
        self, original_name: str, parser_title: str | None, parser_year: int | None
    ) -> NormalizeParseResult:
        payload = {"contents": [{"parts": [{"text": _prompt(original_name, parser_title, parser_year)}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, params={"key": self.api_key}, json=payload)
            response.raise_for_status()
            parts = response.json()["candidates"][0]["content"]["parts"]
            body = "".join(part.get("text", "") for part in parts)
        return _parse_normalized_json(body, parser_title=parser_title, parser_year=parser_year)

    async def preflight(self, expected_provider: str = "gemini") -> LlmPreflightCheck:
        started = time.perf_counter()
        try:
            payload = {"contents": [{"parts": [{"text": _preflight_prompt(expected_provider)}]}]}
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(url, params={"key": self.api_key}, json=payload)
                response.raise_for_status()
                parts = response.json()["candidates"][0]["content"]["parts"]
                text = "".join(part.get("text", "") for part in parts)
            return _validate_preflight_response(
                text,
                expected_provider=expected_provider,
                provider="gemini",
                model=self.model,
                endpoint="https://generativelanguage.googleapis.com/v1beta",
                duration_ms=_duration_ms(started),
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
    )


def _failed_preflight(
    provider: str,
    model: str | None,
    endpoint: str | None,
    started: float,
    exc: Exception,
) -> LlmPreflightCheck:
    return LlmPreflightCheck(
        ok=False,
        provider=provider,
        model=model,
        endpoint=endpoint,
        duration_ms=_duration_ms(started),
        response_valid_json=False,
        error=sanitize_error_text(str(exc)),
        error_type=exc.__class__.__name__,
    )


def sanitize_error_text(value: str) -> str:
    value = re.sub(r"([?&]key=)[^&\\s']+", r"\1[redacted]", value)
    value = re.sub(r"(Bearer\\s+)[A-Za-z0-9._-]+", r"\1[redacted]", value, flags=re.IGNORECASE)
    return value


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


def _prompt(original_name: str, parser_title: str | None, parser_year: int | None) -> str:
    return (
        "Normalize a media filename for TMDB search.\n"
        "Return JSON exactly in this shape:\n"
        "{\n"
        '  "media_type": "movie",\n'
        '  "clean_title": "In the Grey",\n'
        '  "year": 2026,\n'
        '  "season": null,\n'
        '  "episode": null,\n'
        '  "junk_tokens": ["AMZN", "New Team", "REPACK", "1080p"],\n'
        '  "tmdb_queries": ["In the Grey 2026", "In the Grey"],\n'
        '  "confidence": 0.82,\n'
        '  "needs_review": true,\n'
        '  "explanation": "..."\n'
        "}\n"
        "tmdb_queries MUST be an array of strings.\n"
        "Do not return objects inside tmdb_queries.\n"
        "Do not return markdown.\n"
        "Remove release groups, streaming tags, quality/audio/video codecs, and team names.\n"
        f"Original filename: {original_name!r}. Parser title: {parser_title!r}. Parser year: {parser_year!r}."
    )

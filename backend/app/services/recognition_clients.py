import json
from typing import Protocol

import httpx

from ..schemas.recognition import NormalizedTitle

_TIMEOUT_SECONDS = 20.0


class TitleNormalizerClient(Protocol):
    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None) -> NormalizedTitle:
        """Return a normalized title suggestion for one media item."""


class OllamaTitleNormalizer:
    def __init__(self, base_url: str, model: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "gemma3"

    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None) -> NormalizedTitle:
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
        return _parse_normalized_json(body)


class OpenAICompatibleTitleNormalizer:
    def __init__(self, base_url: str, model: str | None, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "local-model"
        self.api_key = api_key

    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None) -> NormalizedTitle:
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
        return _parse_normalized_json(body)


class GeminiTitleNormalizer:
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or "gemini-2.0-flash"

    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None) -> NormalizedTitle:
        payload = {"contents": [{"parts": [{"text": _prompt(original_name, parser_title, parser_year)}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, params={"key": self.api_key}, json=payload)
            response.raise_for_status()
            parts = response.json()["candidates"][0]["content"]["parts"]
            body = "".join(part.get("text", "") for part in parts)
        return _parse_normalized_json(body)


def _parse_normalized_json(value: str) -> NormalizedTitle:
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end >= start:
        value = value[start : end + 1]
    data = json.loads(value)
    return NormalizedTitle.model_validate(data)


def _prompt(original_name: str, parser_title: str | None, parser_year: int | None) -> str:
    return (
        "Normalize a media filename for TMDB search. Return strict JSON only with keys: "
        "clean_title, year, media_type, confidence, junk_tokens, explanation, tmdb_queries. "
        "Remove release groups, streaming tags, quality/audio/video codecs, and team names. "
        f"Original filename: {original_name!r}. Parser title: {parser_title!r}. Parser year: {parser_year!r}."
    )

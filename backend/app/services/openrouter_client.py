from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..schemas.settings import CloudModelRead
from ..utils.ai_errors import sanitize_error_text
from ..utils.ai_retry import post_with_retry

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT_SECONDS = 90.0


@dataclass
class OpenRouterChatResult:
    model: str
    content: str
    attempts: int
    duration_ms: int
    raw_json: dict[str, Any]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        *,
        app_title: str = "MediaForge",
        http_referer: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or OPENROUTER_BASE_URL).rstrip("/")
        self.app_title = app_title
        self.http_referer = http_referer

    async def list_models(self) -> list[CloudModelRead]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self._url("models"), headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise RuntimeError(sanitize_error_text(str(exc))) from exc

        models: list[CloudModelRead] = []
        for item in data.get("data", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else None
            models.append(
                CloudModelRead(
                    id=str(item["id"]),
                    label=str(item.get("name") or item["id"]),
                    display_name=item.get("name"),
                    description=item.get("description"),
                    context_length=_int_or_none(item.get("context_length")),
                    pricing=pricing,
                    provider=_provider_from_model_id(str(item["id"])),
                    is_free=_is_free(pricing),
                    supported_generation_methods=["chat.completions"],
                )
            )
        return models

    async def chat_json(self, *, model: str, messages: list[dict[str, str]]) -> OpenRouterChatResult:
        started = time.perf_counter()
        payload = {"model": model, "messages": messages, "temperature": 0, "response_format": {"type": "json_object"}}
        try:
            response, attempts = await post_with_retry(
                self._url("chat/completions"),
                timeout=_TIMEOUT_SECONDS,
                json=payload,
                headers=self._headers(),
            )
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(sanitize_error_text(str(exc))) from exc
        return OpenRouterChatResult(
            model=model,
            content=content,
            attempts=attempts,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            raw_json=data,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Title": self.app_title}
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def _provider_from_model_id(model_id: str) -> str | None:
    return model_id.split("/", 1)[0] if "/" in model_id else None


def _is_free(pricing: dict | None) -> bool | None:
    if pricing is None:
        return None
    prompt = str(pricing.get("prompt", "")).strip()
    completion = str(pricing.get("completion", "")).strip()
    return prompt in {"0", "0.0", "0.000000"} and completion in {"0", "0.0", "0.000000"}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

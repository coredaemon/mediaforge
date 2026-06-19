import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MediaItemStatus, MediaType
from ..models.media_item import MediaItem
from ..models.recognition_memory import RecognitionCorrection
from ..repositories.app_settings_repository import AppSettingsRepository
from ..repositories.media_item_repository import MediaItemRepository
from ..repositories.recognition_memory_repository import (
    RecognitionMemoryRepository,
    dump_tokens,
    load_tokens,
)
from ..repositories.scan_session_repository import ScanSessionRepository
from ..schemas.recognition_context import RecognitionContext
from ..schemas.recognition import (
    NormalizedTitle,
    RecognitionCorrectionCreate,
    RecognitionCorrectionRead,
    RecognitionNormalizeResult,
    RecognitionPreflightResult,
    LlmPreflightCheck,
)
from ..utils.media_name_parser import clean_title
from .recognition_clients import (
    GeminiTitleNormalizer,
    OllamaTitleNormalizer,
    OpenAICompatibleTitleNormalizer,
    OpenRouterChainTitleNormalizer,
    TitleNormalizerClient,
)
from .ai_router import parse_model_chain
from .openrouter_client import OPENROUTER_BASE_URL
from .scan_session_service import ScanSessionNotFoundError


class RecognitionService:
    def __init__(
        self,
        session: AsyncSession,
        local_client: TitleNormalizerClient | None = None,
        gemini_client: TitleNormalizerClient | None = None,
    ) -> None:
        self.session = session
        self.media_items = MediaItemRepository(session)
        self.memory = RecognitionMemoryRepository(session)
        self.scan_sessions = ScanSessionRepository(session)
        self.settings = AppSettingsRepository(session)
        self.local_client = local_client
        self.gemini_client = gemini_client

    async def create_correction(
        self,
        item_id: int,
        payload: RecognitionCorrectionCreate,
    ) -> RecognitionCorrectionRead:
        item = await self.media_items.get_by_id(item_id)
        if item is None:
            raise MediaItemNotFoundError(f"Media item {item_id} was not found.")

        correction = await self.memory.create_correction(
            RecognitionCorrection(
                media_item_id=item.id,
                original_title=item.original_title,
                previous_title=item.parsed_title,
                corrected_title=payload.corrected_title.strip(),
                corrected_year=payload.corrected_year,
                corrected_media_type=payload.corrected_media_type,
                removed_tokens_json=dump_tokens(payload.removed_tokens),
                confidence=payload.confidence,
            )
        )
        for token in payload.removed_tokens:
            await self.memory.upsert_remove_token(token)

        item.parsed_title = correction.corrected_title
        item.year = correction.corrected_year
        item.ai_clean_title = correction.corrected_title
        item.ai_year = correction.corrected_year
        item.ai_media_type = correction.corrected_media_type
        item.ai_confidence = correction.confidence or 1.0
        item.ai_junk_tokens = load_tokens(correction.removed_tokens_json)
        item.ai_explanation = "Manual correction saved to recognition memory."
        item.tmdb_queries = _dedupe_queries([correction.corrected_title, item.parsed_title])
        if correction.corrected_media_type in {MediaType.MOVIE, MediaType.TV_EPISODE, MediaType.TV_SHOW}:
            item.media_type = MediaType(correction.corrected_media_type)
        item.status = MediaItemStatus.NEEDS_REVIEW
        item.needs_review = True

        await self.session.commit()
        await self.session.refresh(correction)
        return _correction_read(correction)

    async def normalize_scan_session(self, scan_session_id: int) -> RecognitionNormalizeResult:
        return await self._normalize_scan_session(scan_session_id, use_gemini=False)

    async def resolve_with_gemini(self, scan_session_id: int) -> RecognitionNormalizeResult:
        return await self._normalize_scan_session(scan_session_id, use_gemini=True)

    async def preflight(self) -> RecognitionPreflightResult:
        settings = await self.settings.get_or_create()
        if not settings.recognition_ai_enabled:
            skipped = LlmPreflightCheck(
                ok=True,
                provider="disabled",
                message="AI-assisted recognition is disabled.",
            )
            return RecognitionPreflightResult(ok=True, local=skipped, cloud=skipped)

        local_client = await self._get_client(use_gemini=False)
        cloud_client = await self._get_client(use_gemini=True, use_fallback=False)
        fallback_client = await self._get_client(use_gemini=True, use_fallback=True)
        local = (
            await local_client.preflight("local")
            if local_client
            else _missing_fast_preflight(settings)
        )
        cloud = (
            await cloud_client.preflight("gemini")
            if cloud_client
            else _missing_cloud_preflight(settings.cloud_ai_provider, settings.cloud_ai_model, settings.cloud_ai_api_key)
        )
        cloud_fallback = None
        if fallback_client is not None:
            cloud_fallback = await fallback_client.preflight("gemini")
        from ..utils.ai_errors import (
            build_preflight_failure_message,
            build_preflight_warning,
            enrich_preflight_check,
        )

        local = enrich_preflight_check(local)
        cloud = enrich_preflight_check(cloud)
        if cloud_fallback is not None:
            cloud_fallback = enrich_preflight_check(cloud_fallback)
        cloud_ok = cloud.ok or (cloud_fallback.ok if cloud_fallback else False)
        fast_nonfatal = _fast_openrouter_failure_is_nonfatal(local)
        ok = (local.ok and cloud_ok) or (fast_nonfatal and cloud_ok)
        warning = build_preflight_warning(cloud, cloud_fallback)
        if fast_nonfatal and cloud_ok and not local.ok:
            warning = (
                "Быстрый AI-анализ временно недоступен, но умная AI-проверка или запасная модель работает. "
                "Анализ можно продолжить."
            )
        message = build_preflight_failure_message(local, cloud, cloud_fallback) if not ok else None
        return RecognitionPreflightResult(
            ok=ok,
            local=local,
            cloud=cloud,
            cloud_fallback=cloud_fallback,
            warning=warning,
            message=message,
        )

    async def _normalize_scan_session(self, scan_session_id: int, use_gemini: bool) -> RecognitionNormalizeResult:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")
        items = list(await self.media_items.list_by_scan_session(scan_session_id))

        remove_tokens = await self.memory.list_remove_tokens()
        client = await self._get_client(use_gemini=use_gemini, use_fallback=False)
        fallback_client = await self._get_client(use_gemini=use_gemini, use_fallback=True) if use_gemini else None
        normalized_count = 0
        skipped_count = 0
        error_count = 0

        for item in items:
            started = time.perf_counter()
            if item.reused_from_memory or item.status == MediaItemStatus.MATCHED or item.tmdb_id:
                self._mark_ai_diagnostics(
                    item,
                    use_gemini=use_gemini,
                    status="skipped",
                    duration_ms=0,
                    error="Reused from processed media memory." if item.reused_from_memory else None,
                    response_valid_json=None,
                    model=getattr(client, "model", None) if client else None,
                )
                skipped_count += 1
                continue
            try:
                rule_title = clean_title(item.parsed_title or item.original_title or "", remove_tokens=remove_tokens) or None
                active_client = client
                used_fallback = False
                if active_client is None and fallback_client is not None:
                    active_client = fallback_client
                    used_fallback = True
                if active_client is None:
                    self._mark_ai_diagnostics(
                        item,
                        use_gemini=use_gemini,
                        status="failed",
                        duration_ms=0,
                        error="LLM client is not configured.",
                        response_valid_json=False,
                        model=None,
                    )
                    error_count += 1
                    continue
                context = _build_recognition_context(item)
                try:
                    parse_result = await active_client.normalize(
                        item.original_title or "",
                        rule_title,
                        item.year,
                        context,
                    )
                except Exception as primary_exc:
                    if fallback_client is not None and active_client is not fallback_client:
                        active_client = fallback_client
                        used_fallback = True
                        parse_result = await active_client.normalize(
                            item.original_title or "",
                            rule_title,
                            item.year,
                            context,
                        )
                    else:
                        raise primary_exc
                self._apply_suggestion(item, parse_result.title, rule_title=rule_title, use_gemini=use_gemini)
                warning_parts: list[str] = []
                if parse_result.warnings:
                    warning_parts.extend(parse_result.warnings)
                if used_fallback:
                    warning_parts.append("Used fallback cloud model.")
                warning_text = "; ".join(warning_parts) if warning_parts else None
                self._mark_ai_diagnostics(
                    item,
                    use_gemini=use_gemini,
                    status="success",
                    duration_ms=_duration_ms(started),
                    error=warning_text,
                    response_valid_json=True,
                    model=getattr(active_client, "model", None),
                )
                normalized_count += 1
            except Exception as exc:
                self._mark_ai_diagnostics(
                    item,
                    use_gemini=use_gemini,
                    status="failed",
                    duration_ms=_duration_ms(started),
                    error=str(exc),
                    response_valid_json=not isinstance(exc, json.JSONDecodeError),
                    model=getattr(client, "model", None) if client else getattr(fallback_client, "model", None),
                )
                error_count += 1

        await self.session.commit()
        return RecognitionNormalizeResult(
            scan_session_id=scan_session_id,
            normalized_count=normalized_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )

    async def _get_client(self, use_gemini: bool, use_fallback: bool = False) -> TitleNormalizerClient | None:
        settings = await self.settings.get_or_create()
        if use_gemini:
            if use_fallback:
                return _build_fallback_cloud_client(settings)
            if self.gemini_client is not None:
                return self.gemini_client
            return _build_primary_cloud_client(settings)
        if self.local_client is not None:
            return self.local_client

        openrouter_client = _build_openrouter_client(settings, stage="fast")
        if openrouter_client is not None:
            return openrouter_client

        provider = settings.ai_provider or "none"
        if provider == "ollama":
            return OllamaTitleNormalizer(settings.ai_base_url or "http://127.0.0.1:11434", settings.ai_model)
        if provider in {"lmstudio", "custom"}:
            default_url = "http://127.0.0.1:1234" if provider == "lmstudio" else settings.ai_base_url
            if default_url:
                return OpenAICompatibleTitleNormalizer(default_url, settings.ai_model, settings.ai_api_key)
        return None

    def _apply_suggestion(
        self,
        item: MediaItem,
        suggestion: NormalizedTitle | None,
        rule_title: str | None,
        use_gemini: bool,
    ) -> None:
        previous_parser_title = item.parsed_title
        clean = suggestion.clean_title if suggestion and suggestion.clean_title else rule_title
        year = suggestion.year if suggestion and suggestion.year else item.year
        media_type = suggestion.media_type if suggestion and suggestion.media_type else None
        confidence = suggestion.confidence if suggestion else None
        junk_tokens = suggestion.junk_tokens if suggestion else []
        explanation = suggestion.explanation if suggestion else "Recognition memory token rules applied."
        queries = suggestion.tmdb_queries if suggestion else []

        if use_gemini:
            item.gemini_clean_title = clean
            item.gemini_year = year
            item.gemini_media_type = media_type
            item.gemini_confidence = confidence
            item.gemini_junk_tokens = junk_tokens
            item.gemini_explanation = explanation
        else:
            item.ai_clean_title = clean
            item.ai_year = year
            item.ai_media_type = media_type
            item.ai_confidence = confidence
            item.ai_junk_tokens = junk_tokens
            item.ai_explanation = explanation

        if clean:
            item.parsed_title = clean
        if year:
            item.year = year
        if media_type:
            try:
                parsed_type = MediaType(media_type)
                if parsed_type in {MediaType.MOVIE, MediaType.TV_EPISODE, MediaType.TV_SHOW}:
                    item.media_type = parsed_type
            except ValueError:
                pass
        item.tmdb_queries = _dedupe_queries([*(queries or []), clean, previous_parser_title, item.original_title])

    def _mark_ai_diagnostics(
        self,
        item: MediaItem,
        use_gemini: bool,
        status: str,
        duration_ms: int | None,
        error: str | None,
        response_valid_json: bool | None,
        model: str | None,
    ) -> None:
        if use_gemini:
            item.gemini_status = status
            item.gemini_duration_ms = duration_ms
            item.gemini_error = error
            item.gemini_response_valid_json = response_valid_json
            item.gemini_model = model
        else:
            item.local_ai_status = status
            item.local_ai_duration_ms = duration_ms
            item.local_ai_error = error
            item.local_ai_response_valid_json = response_valid_json
            item.local_ai_model = model


def _correction_read(correction: RecognitionCorrection) -> RecognitionCorrectionRead:
    return RecognitionCorrectionRead(
        id=correction.id,
        media_item_id=correction.media_item_id,
        original_title=correction.original_title,
        previous_title=correction.previous_title,
        corrected_title=correction.corrected_title,
        corrected_year=correction.corrected_year,
        corrected_media_type=correction.corrected_media_type,
        removed_tokens=load_tokens(correction.removed_tokens_json),
        confidence=correction.confidence,
        created_at=correction.created_at,
    )


def _dedupe_queries(values: list[str | None]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip()
        key = normalized.lower()
        if normalized and key not in seen:
            queries.append(normalized)
            seen.add(key)
    return queries[:5]


class MediaItemNotFoundError(LookupError):
    """Raised when a media item id does not exist."""


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _missing_cloud_preflight(provider: str | None, model: str | None, key: str | None) -> LlmPreflightCheck:
    if provider in {None, "none"}:
        return LlmPreflightCheck(
            ok=False,
            provider=provider or "none",
            model=model,
            error="Cloud AI provider is not configured.",
            error_type="not_configured",
        )
    if provider == "gemini" and not _usable_secret(key):
        return LlmPreflightCheck(
            ok=False,
            provider="gemini",
            model=model,
            error="Gemini API key is not configured.",
            error_type="not_configured",
        )
    if not model:
        return LlmPreflightCheck(
            ok=False,
            provider=provider,
            error="Cloud AI model is not selected.",
            error_type="not_configured",
        )
    return LlmPreflightCheck(
        ok=False,
        provider=provider,
        model=model,
        error="Cloud AI client is not configured.",
        error_type="not_configured",
    )


def _fast_openrouter_failure_is_nonfatal(check: LlmPreflightCheck) -> bool:
    if check.ok or check.provider != "openrouter":
        return False
    if check.error_type == "auth_error":
        return False
    if check.error_type == "not_configured":
        return False
    return True


def _missing_fast_preflight(settings) -> LlmPreflightCheck:
    if _usable_secret(settings.openrouter_api_key) and parse_model_chain(settings.openrouter_smart_chain):
        return LlmPreflightCheck(
            ok=False,
            provider="openrouter",
            endpoint=settings.openrouter_base_url or OPENROUTER_BASE_URL,
            error="OpenRouter fast chain is empty.",
            error_type="skipped",
            human_message="Быстрая цепочка OpenRouter не настроена. MediaForge проверит умную цепочку.",
        )
    return LlmPreflightCheck(
        ok=False,
        provider=settings.ai_provider or "none",
        model=settings.ai_model,
        endpoint=settings.ai_base_url,
        error="Local LLM is not configured.",
        error_type="not_configured",
    )


def _build_recognition_context(item: MediaItem) -> RecognitionContext:
    from pathlib import Path

    folder_name = None
    if item.original_title:
        folder_name = Path(item.original_title).parent.name
    return RecognitionContext(
        folder_name=folder_name,
        sidecar_title=item.sidecar_title,
        sidecar_year=item.sidecar_year,
        sidecar_overview=item.sidecar_overview,
        sidecar_tmdb_id=item.sidecar_tmdb_id,
        sidecar_imdb_id=item.sidecar_imdb_id,
        sidecar_tvdb_id=item.sidecar_tvdb_id,
        sidecar_source_path=item.sidecar_source_path,
        local_poster_path=item.local_poster_path,
        local_backdrop_path=item.local_backdrop_path,
        memory_tmdb_id=item.tmdb_id if item.reused_from_memory else None,
        memory_imdb_id=item.imdb_id if item.reused_from_memory else None,
        memory_tvdb_id=item.tvdb_id if item.reused_from_memory else None,
        failed_tmdb_queries=item.tmdb_queries or [],
    )


def _build_primary_cloud_client(settings) -> TitleNormalizerClient | None:
    openrouter_client = _build_openrouter_client(settings, stage="smart")
    if openrouter_client is not None:
        return openrouter_client
    if settings.cloud_ai_provider == "gemini" and _usable_secret(settings.cloud_ai_api_key) and settings.cloud_ai_model:
        return GeminiTitleNormalizer(settings.cloud_ai_api_key, settings.cloud_ai_model)
    if settings.cloud_ai_provider in {"openai", "custom"} and settings.cloud_ai_model:
        return OpenAICompatibleTitleNormalizer(
            settings.cloud_ai_base_url or "https://api.openai.com",
            settings.cloud_ai_model,
            settings.cloud_ai_api_key if _usable_secret(settings.cloud_ai_api_key) else None,
        )
    return None


def _build_fallback_cloud_client(settings) -> TitleNormalizerClient | None:
    if _usable_secret(settings.openrouter_api_key):
        chain = parse_model_chain(settings.openrouter_smart_chain)
        if len(chain) > 1:
            return OpenRouterChainTitleNormalizer(
                settings.openrouter_api_key,
                settings.openrouter_base_url or OPENROUTER_BASE_URL,
                chain[1:],
                "smart-fallback",
            )
    provider = settings.cloud_ai_fallback_provider
    model = settings.cloud_ai_fallback_model
    if not provider or provider == "none" or not model:
        return None
    key = settings.cloud_ai_fallback_api_key
    if not _usable_secret(key) and provider == settings.cloud_ai_provider:
        key = settings.cloud_ai_api_key
    if provider == "gemini":
        if not _usable_secret(key):
            return None
        return GeminiTitleNormalizer(key, model)
    if provider in {"openai", "custom"}:
        return OpenAICompatibleTitleNormalizer(
            settings.cloud_ai_base_url or "https://api.openai.com",
            model,
            key if _usable_secret(key) else None,
        )
    return None


def _build_openrouter_client(settings, *, stage: str) -> TitleNormalizerClient | None:
    if not _usable_secret(settings.openrouter_api_key):
        return None
    chain = parse_model_chain(settings.openrouter_smart_chain if stage == "smart" else settings.openrouter_fast_chain)
    if not chain:
        return None
    return OpenRouterChainTitleNormalizer(
        settings.openrouter_api_key,
        settings.openrouter_base_url or OPENROUTER_BASE_URL,
        chain,
        stage,
    )


def _usable_secret(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return value.strip() not in {"MediaOrganizer_API_Key", "YOUR_API_KEY", "PASTE_API_KEY_HERE"}

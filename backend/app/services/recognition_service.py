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
    TitleNormalizerClient,
)
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
        cloud_client = await self._get_client(use_gemini=True)
        local = (
            await local_client.preflight("local")
            if local_client
            else LlmPreflightCheck(
                ok=False,
                provider=settings.ai_provider or "none",
                model=settings.ai_model,
                endpoint=settings.ai_base_url,
                error="Local LLM is not configured.",
                error_type="not_configured",
            )
        )
        cloud = (
            await cloud_client.preflight("gemini")
            if cloud_client
            else _missing_cloud_preflight(settings.cloud_ai_provider, settings.cloud_ai_model, settings.cloud_ai_api_key)
        )
        return RecognitionPreflightResult(ok=local.ok and cloud.ok, local=local, cloud=cloud)

    async def _normalize_scan_session(self, scan_session_id: int, use_gemini: bool) -> RecognitionNormalizeResult:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")
        items = list(await self.media_items.list_by_scan_session(scan_session_id))

        remove_tokens = await self.memory.list_remove_tokens()
        client = await self._get_client(use_gemini=use_gemini)
        normalized_count = 0
        skipped_count = 0
        error_count = 0

        for item in items:
            started = time.perf_counter()
            if item.reused_from_memory or item.status == MediaItemStatus.MATCHED:
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
                if client is None:
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
                parse_result = await client.normalize(item.original_title or "", rule_title, item.year)
                self._apply_suggestion(item, parse_result.title, rule_title=rule_title, use_gemini=use_gemini)
                warning_text = "; ".join(parse_result.warnings) if parse_result.warnings else None
                self._mark_ai_diagnostics(
                    item,
                    use_gemini=use_gemini,
                    status="success",
                    duration_ms=_duration_ms(started),
                    error=warning_text,
                    response_valid_json=True,
                    model=getattr(client, "model", None),
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
                    model=getattr(client, "model", None) if client else None,
                )
                error_count += 1

        await self.session.commit()
        return RecognitionNormalizeResult(
            scan_session_id=scan_session_id,
            normalized_count=normalized_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )

    async def _get_client(self, use_gemini: bool) -> TitleNormalizerClient | None:
        settings = await self.settings.get_or_create()
        if use_gemini:
            if self.gemini_client is not None:
                return self.gemini_client
            if settings.cloud_ai_provider == "gemini" and _usable_secret(settings.cloud_ai_api_key) and settings.cloud_ai_model:
                return GeminiTitleNormalizer(settings.cloud_ai_api_key, settings.cloud_ai_model)
            if settings.cloud_ai_provider in {"openai", "custom"} and settings.cloud_ai_model:
                return OpenAICompatibleTitleNormalizer(
                    settings.cloud_ai_base_url or "https://api.openai.com",
                    settings.cloud_ai_model,
                    settings.cloud_ai_api_key if _usable_secret(settings.cloud_ai_api_key) else None,
                )
            return None
        if self.local_client is not None:
            return self.local_client

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


def _usable_secret(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return value.strip() not in {"MediaOrganizer_API_Key", "YOUR_API_KEY", "PASTE_API_KEY_HERE"}

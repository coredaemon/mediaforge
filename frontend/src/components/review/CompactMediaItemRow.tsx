import { useEffect, useState, type ReactNode } from "react";
import {
  formatAiStatusLabel,
  humanizeAiError,
} from "../../aiLabels";
import { getItemBadges } from "../../badges";
import {
  labelMatchSource,
  labelMediaType,
  labelReviewDecision,
  statusTone,
  type BadgeTone,
} from "../../labels";
import type { MediaItem } from "../../types";
import { tmdbImageUrl } from "../../utils/tmdb";

export type CorrectionPayload = {
  corrected_title: string;
  corrected_year?: number | null;
  corrected_media_type?: string | null;
  removed_tokens?: string[];
  confidence?: number | null;
};

export type ReviewPayload = {
  decision: string;
  note?: string | null;
  manual_title?: string | null;
  manual_year?: number | null;
  manual_tmdb_id?: number | null;
  manual_imdb_id?: string | null;
  manual_tvdb_id?: number | null;
  manual_media_type?: string | null;
};

type Props = {
  item: MediaItem;
  variant: "matched" | "review";
  busy: boolean;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (itemId: number) => void;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
  renderManualReview?: (item: MediaItem) => ReactNode;
};

function fmt(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

function Badge({
  value,
  label,
  tone,
}: {
  value: string | null | undefined;
  label: string;
  tone?: BadgeTone;
}) {
  return <span className={`status-badge ${tone ?? statusTone(value)}`}>{label}</span>;
}

function CorrectionForm({
  item,
  busy,
  onSubmit,
}: {
  item: MediaItem;
  busy: boolean;
  onSubmit: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.ai_clean_title ?? item.parsed_title ?? "");
  const [year, setYear] = useState<string>(String(item.ai_year ?? item.year ?? ""));
  const [mediaType, setMediaType] = useState(item.ai_media_type ?? item.media_type);
  const [tokens, setTokens] = useState((item.ai_junk_tokens ?? []).join(", "));

  useEffect(() => {
    setTitle(item.ai_clean_title ?? item.parsed_title ?? "");
    setYear(String(item.ai_year ?? item.year ?? ""));
    setMediaType(item.ai_media_type ?? item.media_type);
    setTokens((item.ai_junk_tokens ?? []).join(", "));
  }, [item]);

  return (
    <details className="correction-form">
      <summary>Ручное исправление</summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!title.trim()) return;
          void onSubmit(item, {
            corrected_title: title.trim(),
            corrected_year: year === "" ? null : Number(year),
            corrected_media_type: mediaType,
            removed_tokens: tokens.split(",").map((token) => token.trim()).filter(Boolean),
            confidence: 1,
          });
        }}
      >
        <div className="correction-grid">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
          <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Год" inputMode="numeric" />
          <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
            <option value="MOVIE">{labelMediaType("MOVIE")}</option>
            <option value="TV_EPISODE">{labelMediaType("TV_EPISODE")}</option>
            <option value="TV_SHOW">{labelMediaType("TV_SHOW")}</option>
            <option value="UNKNOWN">{labelMediaType("UNKNOWN")}</option>
          </select>
          <input value={tokens} onChange={(e) => setTokens(e.target.value)} placeholder="Токены для удаления" />
        </div>
        <button type="submit" disabled={busy || !title.trim()}>
          Сохранить и повторить поиск TMDB
        </button>
      </form>
    </details>
  );
}

function AiDiagnosticMessage({
  provider,
  status,
  validJson,
  error,
}: {
  provider: string;
  status: string | null;
  validJson: boolean | null;
  error: string | null;
}) {
  const label = formatAiStatusLabel(status, validJson, Boolean(error));
  const humanError = error ? humanizeAiError(error) : null;
  return (
    <div className="ai-diagnostic">
      <span>
        {provider}: {label}
      </span>
      {humanError ? <small className="error-text">Ошибка: {humanError}</small> : null}
    </div>
  );
}

function RecognitionEvidence({ item }: { item: MediaItem }) {
  return (
    <div className="recognition-evidence">
      <span>
        Парсер: {fmt(item.parsed_title)} {item.year ? `(${item.year})` : ""}
      </span>
      {item.sidecar_source_path ? <span>Источник NFO: {item.sidecar_source_path}</span> : null}
      {item.match_source ? <span>Источник совпадения: {labelMatchSource(item.match_source)}</span> : null}
      <AiDiagnosticMessage
        provider="Локальная AI-модель"
        status={item.local_ai_status}
        validJson={item.local_ai_response_valid_json}
        error={item.local_ai_error}
      />
      <AiDiagnosticMessage
        provider="Облачная AI-модель"
        status={item.gemini_status}
        validJson={item.gemini_response_valid_json}
        error={item.gemini_error}
      />
    </div>
  );
}

export function CompactMediaItemRow({
  item,
  variant,
  busy,
  selectable = false,
  selected = false,
  onToggleSelect,
  onCandidates,
  onCorrection,
  onDecision,
  renderManualReview,
}: Props) {
  const localPoster = item.local_poster_path ?? item.sidecar_poster_path;
  const poster =
    item.poster_url ??
    tmdbImageUrl(item.poster_path) ??
    (localPoster ? `file:///${localPoster.replace(/\\/g, "/")}` : null);
  const title =
    item.localized_title ?? item.matched_title ?? item.parsed_title ?? item.original_title ?? `Объект #${item.id}`;
  const badges = getItemBadges(item);
  const isIgnored = item.review_decision === "ignored";
  const isDeferred = item.review_decision === "deferred";
  const isApproved = item.review_decision === "approved" || item.review_decision === "manual_override";

  return (
    <div
      className={`review-item-row item-card ${item.reused_from_memory ? "memory-reused" : ""} ${isIgnored || isDeferred ? "review-muted" : ""}`}
    >
      {selectable ? (
        <label className="item-select-checkbox">
          <input
            type="checkbox"
            checked={selected}
            disabled={busy}
            onChange={() => onToggleSelect?.(item.id)}
          />
        </label>
      ) : null}
      <div className="review-item-poster">
        {poster ? (
          <img src={poster} alt={title} loading="lazy" />
        ) : (
          <div className="poster-placeholder compact-poster-placeholder">Нет постера</div>
        )}
      </div>
      <div className="review-item-body">
        <div className="review-item-header">
          <div>
            <strong>{title}</strong>
            <p className="muted review-item-meta-line">
              {labelMediaType(item.media_type)}
              {item.year ? ` · ${item.year}` : ""}
              {item.season_number && item.episode_number
                ? ` · S${String(item.season_number).padStart(2, "0")}E${String(item.episode_number).padStart(2, "0")}`
                : ""}
              {item.match_source ? ` · ${labelMatchSource(item.match_source)}` : ""}
            </p>
          </div>
          <div className="item-badges">
            {badges.map((badge) => (
              <Badge key={badge.key} value={badge.key} label={badge.label} tone={badge.tone} />
            ))}
          </div>
        </div>
        {variant === "review" ? <p className="muted">Файл: {item.original_title}</p> : null}
        <div className="item-meta review-item-ids">
          <span>TMDB: {fmt(item.tmdb_id)}</span>
          <span>IMDb: {fmt(item.imdb_id)}</span>
          {item.tvdb_id ? <span>TVDB: {fmt(item.tvdb_id)}</span> : null}
          {item.wikidata_id ? <span>Wikidata: {fmt(item.wikidata_id)}</span> : null}
          <span>Уверенность: {formatPercent(item.match_confidence ?? item.ai_confidence ?? item.confidence)}</span>
        </div>
        {item.localized_overview ? <p className="review-item-overview">{item.localized_overview}</p> : null}
        <div className="item-review-actions">
          {isApproved ? (
            <button type="button" disabled className="btn-muted">
              Одобрено
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onDecision(item.id, { decision: "approved", note: "Подтверждено пользователем" })}
            >
              Добавить
            </button>
          )}
          {isIgnored || isDeferred ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onDecision(item.id, { decision: "approved", note: "Вернуть в план" })}
            >
              Вернуть в план
            </button>
          ) : (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onDecision(item.id, { decision: "ignored", note: "Не добавлять" })}
              >
                Не добавлять
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onDecision(item.id, { decision: "deferred", note: "Отложено" })}
              >
                Отложить
              </button>
            </>
          )}
          <button type="button" onClick={() => void onCandidates(item.id)}>
            Кандидаты
          </button>
        </div>
        <details className="manual-review-panel-wrap">
          <summary>Ручная проверка</summary>
          {renderManualReview ? renderManualReview(item) : null}
        </details>
        <details className="recognition-tech-details">
          <summary>Технические детали распознавания</summary>
          <RecognitionEvidence item={item} />
          {variant === "review" ? <CorrectionForm item={item} busy={busy} onSubmit={onCorrection} /> : null}
        </details>
        {isIgnored ? <Badge value="ignored" label="Исключено" tone="warning" /> : null}
        {isDeferred ? <Badge value="deferred" label="Отложено" tone="warning" /> : null}
        {isApproved ? <Badge value="approved" label={labelReviewDecision(item.review_decision)} tone="success" /> : null}
      </div>
    </div>
  );
}

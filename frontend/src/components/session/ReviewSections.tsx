import { useState } from "react";

import {
  ApiError,
  formatTmdbError,
  manualTmdbLookup,
  manualTmdbSearch,
  manualTvTmdbLookup,
  manualTvTmdbSearch,
} from "../../api";
import { labelMediaItemStatus, labelMediaType, labelOperationStatus, labelOperationType, labelPlanStatus, type BadgeTone } from "../../labels";
import type { MediaFile, MediaItem, OperationPlan, PlanOperation, TmdbSearchResult, TvShow } from "../../types";
import { isBulkSelectable } from "../../utils/bulkSelection";
import { candidatePosterUrl } from "../../utils/tmdb";
import { validateIdLookupInput } from "../../validation";
import { CompactMediaItemRow } from "../review/CompactMediaItemRow";
import { tvShowReviewState, type TvReviewState } from "./tvReviewState";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

function fmt(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

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

function fileNameFromPath(path?: string | null): string {
  if (!path) return "—";
  return path.split(/[\\/]/).pop() || path;
}

export function TvReviewSection({
  shows,
  busy,
  planStale,
  onDecision,
  onShowUpdated,
  onRebuildPlan,
}: {
  shows: TvShow[];
  busy: boolean;
  planStale: boolean;
  onDecision: (showId: number, decision: string) => Promise<void>;
  onShowUpdated: (message: string) => Promise<void>;
  onRebuildPlan: () => void;
}) {
  const [manualShowId, setManualShowId] = useState<number | null>(null);
  const episodeCount = shows.reduce(
    (total, show) => total + show.seasons.reduce((seasonTotal, season) => seasonTotal + season.episodes.length, 0),
    0,
  );
  const needsReview = shows.filter((show) => show.needs_review || show.seasons.some((season) => season.episodes.some((episode) => episode.needs_review))).length;
  const includedCount = shows.filter((show) => tvShowReviewState(show) === "included" || tvShowReviewState(show) === "manual_override").length;
  const ignoredCount = shows.filter((show) => tvShowReviewState(show) === "ignored").length;
  const deferredCount = shows.filter((show) => tvShowReviewState(show) === "deferred").length;

  if (shows.length === 0) {
    return <p className="muted compact-section-row">Сериалы: не обнаружены</p>;
  }

  return (
    <section className="panel compact-review-section tv-review-section">
      <div className="section-heading">
        <h3>Проверка сериалов</h3>
        <span className="muted">
          В план: {includedCount} · Эпизодов: {episodeCount} · Требуют проверки: {needsReview} · исключено: {ignoredCount} · отложено: {deferredCount}
        </span>
      </div>
      {planStale ? (
        <p className="message warning">Р ешения по сериалам изменились. Пересоберите план сериалов.</p>
      ) : null}
      <div className="review-item-list">
        {shows.map((show) => {
          const state = tvShowReviewState(show);
          const status = tvShowStatusParts(show);
          return (
            <article className="compact-media-row tv-show-row" key={show.id}>
              {show.poster_url ? <img className="poster-thumb" src={show.poster_url} alt="" /> : <div className="poster-thumb placeholder" />}
              <div className="compact-media-main">
                <div className="compact-media-title-row">
                  <strong>{state === "needs_review" ? "Возможное совпадение: " : ""}{show.title}{show.year ? ` (${show.year})` : ""}</strong>
                  <span className="tv-status-badges">
                    {status.map((part) => (
                      <span key={part.label} className={`status-badge ${part.tone}`}>{part.label}</span>
                    ))}
                  </span>
                </div>
                <p className="muted">
                  Сериал · {show.tmdb_id ? `TMDB ${show.tmdb_id}` : "TMDB не выбран"}
                  {show.tvdb_id ? ` · TVDB ${show.tvdb_id}` : ""}
                  {show.imdb_id ? ` · IMDb ${show.imdb_id}` : ""}
                  {show.match_source ? ` · ${show.match_source}` : ""}
                </p>
                <p className="muted">
                  Сезонов: {show.seasons.length} · Эпизодов:{" "}
                  {show.seasons.reduce((total, season) => total + season.episodes.length, 0)}
                </p>
                {show.overview ? <p className="compact-overview">{show.overview}</p> : null}
                {state === "needs_review" && show.ai_reasoning_summary ? (
                  <p className="message warning">Причина: {show.ai_reasoning_summary}</p>
                ) : null}
                {show.warnings?.length ? <p className="message warning">{show.warnings.join("; ")}</p> : null}
                <TvShowActions
                  show={show}
                  state={state}
                  busy={busy}
                  manualOpen={manualShowId === show.id}
                  onToggleManual={() => setManualShowId((current) => (current === show.id ? null : show.id))}
                  onDecision={onDecision}
                />
                {manualShowId === show.id ? (
                  <TvManualMatchPanel
                    show={show}
                    busy={busy}
                    onUpdated={async () => {
                      setManualShowId(null);
                      await onShowUpdated("Совпадение изменено. Пересоберите план сериалов.");
                    }}
                  />
                ) : null}
                <div className="tv-season-list">
                  {show.seasons.map((season, seasonIndex) => (
                    <details key={season.id} open={show.seasons.length <= 2 || seasonIndex === 0} className="tv-season-details">
                      <summary>
                        Сезон {season.season_number} — {season.episodes.length} серий
                      </summary>
                      <div className="tv-episode-list">
                        {season.episodes.map((episode) => (
                          <div className="tv-episode-row" key={episode.id}>
                            <span>S{String(episode.season_number).padStart(2, "0")}E{String(episode.episode_number).padStart(2, "0")}</span>
                            <span className="path-text" title={episode.source_path ?? undefined}>{fileNameFromPath(episode.source_path)}</span>
                            <span>{episode.title ?? "Название будет уточнено"}</span>
                            {episode.issue || episode.warning ? <span className="status-badge warning">{episode.issue ?? episode.warning}</span> : null}
                            {episode.source_path ? (
                              <details className="tv-episode-path">
                                <summary>Путь</summary>
                                <code>{episode.source_path}</code>
                              </details>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <div className="pipeline-actions">
        <button type="button" disabled={busy || needsReview > 0} onClick={onRebuildPlan}>
          Пересобрать план сериалов
        </button>
      </div>
    </section>
  );
}

function tvShowStatusParts(show: TvShow): { label: string; tone: BadgeTone }[] {
  const state = tvShowReviewState(show);
  if (state === "manual_override") return [{ label: "Выбрано вручную", tone: "info" }, { label: "Включён в план", tone: "success" }];
  if (state === "included") return [{ label: "Включён в план", tone: "success" }];
  if (state === "needs_review") return [{ label: "Требует проверки", tone: "warning" }];
  if (state === "ignored") return [{ label: "Исключён из плана", tone: "neutral" }];
  return [{ label: "Отложен", tone: "warning" }];
}

function TvShowActions({
  show,
  state,
  busy,
  manualOpen,
  onToggleManual,
  onDecision,
}: {
  show: TvShow;
  state: TvReviewState;
  busy: boolean;
  manualOpen: boolean;
  onToggleManual: () => void;
  onDecision: (showId: number, decision: string) => Promise<void>;
}) {
  if (state === "needs_review") {
    return (
      <div className="manual-review-actions">
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "approved")}>Подтвердить</button>
        <button type="button" disabled={busy} onClick={onToggleManual}>{manualOpen ? "Скрыть замену" : "Изменить совпадение"}</button>
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "ignored")}>Не добавлять</button>
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "deferred")}>Отложить</button>
      </div>
    );
  }
  if (state === "ignored" || state === "deferred") {
    return (
      <div className="manual-review-actions">
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "approved")}>Вернуть в план</button>
        <button type="button" disabled={busy} onClick={onToggleManual}>{manualOpen ? "Скрыть замену" : "Изменить совпадение"}</button>
      </div>
    );
  }
  return (
    <div className="manual-review-actions">
      <button type="button" disabled={busy} onClick={onToggleManual}>{manualOpen ? "Скрыть замену" : "Изменить совпадение"}</button>
      <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "ignored")}>Исключить из плана</button>
      <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "deferred")}>Отложить</button>
    </div>
  );
}

function TvManualMatchPanel({
  show,
  busy,
  onUpdated,
}: {
  show: TvShow;
  busy: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [query, setQuery] = useState(show.title);
  const [year, setYear] = useState(String(show.year ?? ""));
  const [tmdbId, setTmdbId] = useState(String(show.tmdb_id ?? ""));
  const [imdbId, setImdbId] = useState(show.imdb_id ?? "");
  const [tvdbId, setTvdbId] = useState(String(show.tvdb_id ?? ""));
  const [candidates, setCandidates] = useState<TmdbSearchResult[]>([]);
  const [localBusy, setLocalBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disabled = busy || localBusy;

  async function runManualAction(action: () => Promise<void>) {
    setLocalBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? formatTmdbError(err.message) : "Операция не удалась.");
    } finally {
      setLocalBusy(false);
    }
  }

  async function selectByIds(payload: { tmdb_id?: number | null; imdb_id?: string | null; tvdb_id?: number | null }) {
    await manualTvTmdbLookup(show.id, { ...payload, select: true });
    await onUpdated();
  }

  return (
    <div className="manual-review-panel tv-manual-match-panel">
      <h4>Изменить совпадение сериала</h4>
      <div className="manual-review-grid">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Название" />
        <input value={year} onChange={(event) => setYear(event.target.value)} placeholder="Год" inputMode="numeric" />
      </div>
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={disabled || !query.trim()}
          onClick={() => void runManualAction(async () => {
            const results = await manualTvTmdbSearch(show.id, {
              query: query.trim(),
              year: year.trim() ? Number(year) : null,
            });
            setCandidates(results);
            setMessage(results.length > 0 ? `Найдено кандидатов: ${results.length}` : "Кандидаты не найдены.");
          })}
        >
          Найти
        </button>
      </div>
      <h4>Загрузить по ID</h4>
      <p className="muted manual-review-hint">
        TMDB ID загружает сериал напрямую. IMDb и TVDB ищутся через TMDB Find.
      </p>
      <div className="manual-review-grid">
        <input value={tmdbId} onChange={(event) => setTmdbId(event.target.value)} placeholder="TMDB ID" inputMode="numeric" />
        <input value={imdbId} onChange={(event) => setImdbId(event.target.value)} placeholder="IMDb ID" />
        <input value={tvdbId} onChange={(event) => setTvdbId(event.target.value)} placeholder="TVDB ID" inputMode="numeric" />
      </div>
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={disabled || (!tmdbId.trim() && !imdbId.trim() && !tvdbId.trim())}
          onClick={() => void runManualAction(async () => {
            const validation = validateIdLookupInput(tmdbId, imdbId, tvdbId);
            if (!validation.valid) {
              setError(validation.error ?? "Некорректный ID");
              return;
            }
            await selectByIds({
              tmdb_id: tmdbId.trim() ? Number(tmdbId) : null,
              imdb_id: imdbId.trim() || null,
              tvdb_id: tvdbId.trim() ? Number(tvdbId) : null,
            });
          })}
        >
          Загрузить
        </button>
      </div>
      {message ? <p className="message success">{message}</p> : null}
      {error ? <p className="message error">{error}</p> : null}
      {candidates.length > 0 ? (
        <div className="candidate-list tv-candidate-list">
          {candidates.map((candidate) => {
            const poster = candidatePosterUrl(candidate);
            return (
              <div className="candidate-card visual-candidate-card" key={`${candidate.media_type}-${candidate.tmdb_id}`}>
                {poster ? <img className="candidate-poster" src={poster} alt={candidate.title} loading="lazy" /> : <div className="poster-placeholder compact-poster-placeholder">Нет постера</div>}
                <div className="candidate-content">
                  <strong>{candidate.title}{candidate.year ? ` (${candidate.year})` : ""}</strong>
                  <p className="muted">
                    TMDB {candidate.tmdb_id} · {candidate.original_title ?? "оригинальное название не указано"}
                  </p>
                  <p>{candidate.overview ?? "Описание отсутствует."}</p>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={disabled}
                    onClick={() => void runManualAction(() => selectByIds({ tmdb_id: candidate.tmdb_id }))}
                  >
                    Выбрать этот сериал
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function ItemList({
  items,
  variant,
  busy,
  selectable = false,
  selectedIds,
  onToggleSelect,
  onCandidates,
  onCorrection,
  onDecision,
}: {
  items: MediaItem[];
  variant: "matched" | "review";
  busy: boolean;
  selectable?: boolean;
  selectedIds?: Set<number>;
  onToggleSelect?: (itemId: number) => void;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  if (items.length === 0) {
    return <p className="muted">Нет объектов в этом разделе.</p>;
  }
  return (
    <div className="review-item-list">
      {items.map((item) => (
        <CompactMediaItemRow
          key={item.id}
          item={item}
          variant={variant}
          busy={busy}
          selectable={selectable && isBulkSelectable(item)}
          selected={selectedIds?.has(item.id) ?? false}
          onToggleSelect={onToggleSelect}
          onCandidates={onCandidates}
          onCorrection={onCorrection}
          onDecision={onDecision}
          renderManualReview={(rowItem) => (
            <ManualReviewPanel item={rowItem} busy={busy} onCandidates={onCandidates} onDecision={onDecision} />
          )}
        />
      ))}
    </div>
  );
}

function ManualReviewPanel({
  item,
  busy,
  onCandidates,
  onDecision,
}: {
  item: MediaItem;
  busy: boolean;
  onCandidates: (itemId: number) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.manual_title ?? item.parsed_title ?? "");
  const [year, setYear] = useState(String(item.manual_year ?? item.year ?? ""));
  const [mediaType, setMediaType] = useState(item.manual_media_type ?? item.media_type);
  const [tmdbId, setTmdbId] = useState(String(item.manual_tmdb_id ?? item.tmdb_id ?? ""));
  const [imdbId, setImdbId] = useState(item.manual_imdb_id ?? item.imdb_id ?? "");
  const [tvdbId, setTvdbId] = useState(String(item.manual_tvdb_id ?? item.tvdb_id ?? ""));
  const [idError, setIdError] = useState<string | null>(null);

  return (
    <div className="manual-review-panel">
      <h4>Найти по названию</h4>
      <div className="manual-review-grid">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
        <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Год" inputMode="numeric" />
        <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
          <option value="MOVIE">Фильм</option>
          <option value="TV_SHOW">Сериал</option>
          <option value="TV_EPISODE">Серия</option>
        </select>
      </div>
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={busy || !title.trim()}
          onClick={() =>
            void (async () => {
              await manualTmdbSearch(item.id, {
                query: title.trim(),
                year: year === "" ? null : Number(year),
                media_type: mediaType === "MOVIE" ? "movie" : "tv",
              });
              await onCandidates(item.id);
            })()
          }
        >
          Искать в TMDB
        </button>
      </div>
      <h4>Загрузить по ID</h4>
      <p className="muted manual-review-hint">
        Заполните один из ID. TMDB ID используется напрямую. IMDb/TVDB ищутся через TMDB Find.
      </p>
      <div className="manual-review-grid">
        <input value={tmdbId} onChange={(e) => setTmdbId(e.target.value)} placeholder="TMDB ID" inputMode="numeric" />
        <input value={imdbId} onChange={(e) => setImdbId(e.target.value)} placeholder="IMDb ID" />
        <input value={tvdbId} onChange={(e) => setTvdbId(e.target.value)} placeholder="TVDB ID" inputMode="numeric" />
      </div>
      {idError ? <p className="message error">{idError}</p> : null}
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={busy || (!tmdbId && !imdbId && !tvdbId)}
          onClick={() =>
            void (async () => {
              const validation = validateIdLookupInput(tmdbId, imdbId, tvdbId);
              if (!validation.valid) {
                setIdError(validation.error ?? "Некорректный ID");
                return;
              }
              setIdError(null);
              await manualTmdbLookup(item.id, {
                tmdb_id: tmdbId.trim() ? Number(tmdbId) : null,
                imdb_id: imdbId.trim() || null,
                tvdb_id: tvdbId.trim() ? Number(tvdbId) : null,
                media_type: mediaType === "MOVIE" ? "movie" : "tv",
              });
              await onCandidates(item.id);
            })()
          }
        >
          Загрузить по ID
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void onDecision(item.id, {
              decision: "approved",
              note: "Подтверждено пользователем",
            })
          }
        >
          Подтвердить выбранный вариант
        </button>
        <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "ignored", note: "Не добавлять" })}>
          Не добавлять
        </button>
        <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "deferred", note: "Отложено" })}>
          Отложить
        </button>
        <button
          type="button"
          disabled={busy || (!tmdbId && !imdbId)}
          onClick={() =>
            void onDecision(item.id, {
              decision: "manual_override",
              manual_title: title.trim() || null,
              manual_year: year === "" ? null : Number(year),
              manual_tmdb_id: tmdbId ? Number(tmdbId) : null,
              manual_imdb_id: imdbId || null,
              manual_tvdb_id: tvdbId ? Number(tvdbId) : null,
              manual_media_type: mediaType,
              note: "Исправлено вручную",
            })
          }
        >
          Сохранить исправление
        </button>
      </div>
    </div>
  );
}

export function TechnicalTables({
  files,
  items,
  plans,
  operations,
  onCandidates,
  onOperations,
}: {
  files: MediaFile[];
  items: MediaItem[];
  plans: OperationPlan[];
  operations: PlanOperation[];
  onCandidates: (itemId: number) => Promise<void>;
  onOperations: (planId: number) => Promise<void>;
}) {
  return (
    <div className="technical-tables">
      <h4>Файлы</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {files.map((f) => (
              <tr key={f.id}>
                <td>{f.id}</td>
                <td>{f.kind}</td>
                <td>{f.file_name}</td>
                <td>{fmt(f.media_item_id)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Объекты</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{labelMediaType(item.media_type)}</td>
                <td>{labelMediaItemStatus(item.status)}</td>
                <td>{item.parsed_title ?? "—"}</td>
                <td>
                  <button type="button" onClick={() => void onCandidates(item.id)}>Кандидаты</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Планы</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id}>
                <td>{plan.id}</td>
                <td>{labelPlanStatus(plan.status)}</td>
                <td>{formatDate(plan.created_at)}</td>
                <td>
                  <button type="button" onClick={() => void onOperations(plan.id)}>Операции</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Технический список операций</summary>
        <div className="table-wrap">
          <table>
            <tbody>
              {operations.map((op) => (
                <tr key={op.id}>
                  <td>{op.id}</td>
                  <td>{labelOperationType(op.operation_type)}</td>
                  <td>{labelOperationStatus(op.status)}</td>
                  <td>{op.validation_status ?? "—"}</td>
                  <td className="path-text">{op.source_path ?? "—"}</td>
                  <td className="path-text">{op.target_path ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

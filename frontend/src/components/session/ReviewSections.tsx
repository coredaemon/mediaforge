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
  if (!path) return "вЂ”";
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
    return <p className="muted compact-section-row">РЎРµСЂРёР°Р»С‹: РЅРµ РѕР±РЅР°СЂСѓР¶РµРЅС‹</p>;
  }

  return (
    <section className="panel compact-review-section tv-review-section">
      <div className="section-heading">
        <h3>РџСЂРѕРІРµСЂРєР° СЃРµСЂРёР°Р»РѕРІ</h3>
        <span className="muted">
          Р’ РїР»Р°РЅ: {includedCount} В· Р­РїРёР·РѕРґРѕРІ: {episodeCount} В· РўСЂРµР±СѓСЋС‚ РїСЂРѕРІРµСЂРєРё: {needsReview} В· РёСЃРєР»СЋС‡РµРЅРѕ: {ignoredCount} В· РѕС‚Р»РѕР¶РµРЅРѕ: {deferredCount}
        </span>
      </div>
      {planStale ? (
        <p className="message warning">Р РµС€РµРЅРёСЏ РїРѕ СЃРµСЂРёР°Р»Р°Рј РёР·РјРµРЅРёР»РёСЃСЊ. РџРµСЂРµСЃРѕР±РµСЂРёС‚Рµ РїР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ.</p>
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
                  <strong>{state === "needs_review" ? "Р’РѕР·РјРѕР¶РЅРѕРµ СЃРѕРІРїР°РґРµРЅРёРµ: " : ""}{show.title}{show.year ? ` (${show.year})` : ""}</strong>
                  <span className="tv-status-badges">
                    {status.map((part) => (
                      <span key={part.label} className={`status-badge ${part.tone}`}>{part.label}</span>
                    ))}
                  </span>
                </div>
                <p className="muted">
                  РЎРµСЂРёР°Р» В· {show.tmdb_id ? `TMDB ${show.tmdb_id}` : "TMDB РЅРµ РІС‹Р±СЂР°РЅ"}
                  {show.tvdb_id ? ` В· TVDB ${show.tvdb_id}` : ""}
                  {show.imdb_id ? ` В· IMDb ${show.imdb_id}` : ""}
                  {show.match_source ? ` В· ${show.match_source}` : ""}
                </p>
                <p className="muted">
                  РЎРµР·РѕРЅРѕРІ: {show.seasons.length} В· Р­РїРёР·РѕРґРѕРІ:{" "}
                  {show.seasons.reduce((total, season) => total + season.episodes.length, 0)}
                </p>
                {show.overview ? <p className="compact-overview">{show.overview}</p> : null}
                {state === "needs_review" && show.ai_reasoning_summary ? (
                  <p className="message warning">РџСЂРёС‡РёРЅР°: {show.ai_reasoning_summary}</p>
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
                      await onShowUpdated("РЎРѕРІРїР°РґРµРЅРёРµ РёР·РјРµРЅРµРЅРѕ. РџРµСЂРµСЃРѕР±РµСЂРёС‚Рµ РїР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ.");
                    }}
                  />
                ) : null}
                <div className="tv-season-list">
                  {show.seasons.map((season, seasonIndex) => (
                    <details key={season.id} open={show.seasons.length <= 2 || seasonIndex === 0} className="tv-season-details">
                      <summary>
                        РЎРµР·РѕРЅ {season.season_number} вЂ” {season.episodes.length} СЃРµСЂРёР№
                      </summary>
                      <div className="tv-episode-list">
                        {season.episodes.map((episode) => (
                          <div className="tv-episode-row" key={episode.id}>
                            <span>S{String(episode.season_number).padStart(2, "0")}E{String(episode.episode_number).padStart(2, "0")}</span>
                            <span className="path-text" title={episode.source_path ?? undefined}>{fileNameFromPath(episode.source_path)}</span>
                            <span>{episode.title ?? "РќР°Р·РІР°РЅРёРµ Р±СѓРґРµС‚ СѓС‚РѕС‡РЅРµРЅРѕ"}</span>
                            {episode.issue || episode.warning ? <span className="status-badge warning">{episode.issue ?? episode.warning}</span> : null}
                            {episode.source_path ? (
                              <details className="tv-episode-path">
                                <summary>РџСѓС‚СЊ</summary>
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
          РџРµСЂРµСЃРѕР±СЂР°С‚СЊ РїР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ
        </button>
      </div>
    </section>
  );
}

type TvReviewState = "included" | "needs_review" | "ignored" | "deferred" | "manual_override";

export function tvShowReviewState(show: TvShow): TvReviewState {
  if (show.review_decision === "ignored") return "ignored";
  if (show.review_decision === "deferred") return "deferred";
  if (show.review_decision === "manual_override") return "manual_override";
  if (show.needs_review || show.seasons.some((season) => season.episodes.some((episode) => episode.needs_review))) return "needs_review";
  return "included";
}

function tvShowStatusParts(show: TvShow): { label: string; tone: BadgeTone }[] {
  const state = tvShowReviewState(show);
  if (state === "manual_override") return [{ label: "Р’С‹Р±СЂР°РЅРѕ РІСЂСѓС‡РЅСѓСЋ", tone: "info" }, { label: "Р’РєР»СЋС‡С‘РЅ РІ РїР»Р°РЅ", tone: "success" }];
  if (state === "included") return [{ label: "Р’РєР»СЋС‡С‘РЅ РІ РїР»Р°РЅ", tone: "success" }];
  if (state === "needs_review") return [{ label: "РўСЂРµР±СѓРµС‚ РїСЂРѕРІРµСЂРєРё", tone: "warning" }];
  if (state === "ignored") return [{ label: "РСЃРєР»СЋС‡С‘РЅ РёР· РїР»Р°РЅР°", tone: "neutral" }];
  return [{ label: "РћС‚Р»РѕР¶РµРЅ", tone: "warning" }];
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
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "approved")}>РџРѕРґС‚РІРµСЂРґРёС‚СЊ</button>
        <button type="button" disabled={busy} onClick={onToggleManual}>{manualOpen ? "РЎРєСЂС‹С‚СЊ Р·Р°РјРµРЅСѓ" : "РР·РјРµРЅРёС‚СЊ СЃРѕРІРїР°РґРµРЅРёРµ"}</button>
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "ignored")}>РќРµ РґРѕР±Р°РІР»СЏС‚СЊ</button>
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "deferred")}>РћС‚Р»РѕР¶РёС‚СЊ</button>
      </div>
    );
  }
  if (state === "ignored" || state === "deferred") {
    return (
      <div className="manual-review-actions">
        <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "approved")}>Р’РµСЂРЅСѓС‚СЊ РІ РїР»Р°РЅ</button>
        <button type="button" disabled={busy} onClick={onToggleManual}>{manualOpen ? "РЎРєСЂС‹С‚СЊ Р·Р°РјРµРЅСѓ" : "РР·РјРµРЅРёС‚СЊ СЃРѕРІРїР°РґРµРЅРёРµ"}</button>
      </div>
    );
  }
  return (
    <div className="manual-review-actions">
      <button type="button" disabled={busy} onClick={onToggleManual}>{manualOpen ? "РЎРєСЂС‹С‚СЊ Р·Р°РјРµРЅСѓ" : "РР·РјРµРЅРёС‚СЊ СЃРѕРІРїР°РґРµРЅРёРµ"}</button>
      <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "ignored")}>РСЃРєР»СЋС‡РёС‚СЊ РёР· РїР»Р°РЅР°</button>
      <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "deferred")}>РћС‚Р»РѕР¶РёС‚СЊ</button>
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
      setError(err instanceof ApiError ? formatTmdbError(err.message) : "РћРїРµСЂР°С†РёСЏ РЅРµ СѓРґР°Р»Р°СЃСЊ.");
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
      <h4>РР·РјРµРЅРёС‚СЊ СЃРѕРІРїР°РґРµРЅРёРµ СЃРµСЂРёР°Р»Р°</h4>
      <div className="manual-review-grid">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="РќР°Р·РІР°РЅРёРµ" />
        <input value={year} onChange={(event) => setYear(event.target.value)} placeholder="Р“РѕРґ" inputMode="numeric" />
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
            setMessage(results.length > 0 ? `РќР°Р№РґРµРЅРѕ РєР°РЅРґРёРґР°С‚РѕРІ: ${results.length}` : "РљР°РЅРґРёРґР°С‚С‹ РЅРµ РЅР°Р№РґРµРЅС‹.");
          })}
        >
          РќР°Р№С‚Рё
        </button>
      </div>
      <h4>Р—Р°РіСЂСѓР·РёС‚СЊ РїРѕ ID</h4>
      <p className="muted manual-review-hint">
        TMDB ID Р·Р°РіСЂСѓР¶Р°РµС‚ СЃРµСЂРёР°Р» РЅР°РїСЂСЏРјСѓСЋ. IMDb Рё TVDB РёС‰СѓС‚СЃСЏ С‡РµСЂРµР· TMDB Find.
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
              setError(validation.error ?? "РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ ID");
              return;
            }
            await selectByIds({
              tmdb_id: tmdbId.trim() ? Number(tmdbId) : null,
              imdb_id: imdbId.trim() || null,
              tvdb_id: tvdbId.trim() ? Number(tvdbId) : null,
            });
          })}
        >
          Р—Р°РіСЂСѓР·РёС‚СЊ
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
                {poster ? <img className="candidate-poster" src={poster} alt={candidate.title} loading="lazy" /> : <div className="poster-placeholder compact-poster-placeholder">РќРµС‚ РїРѕСЃС‚РµСЂР°</div>}
                <div className="candidate-content">
                  <strong>{candidate.title}{candidate.year ? ` (${candidate.year})` : ""}</strong>
                  <p className="muted">
                    TMDB {candidate.tmdb_id} В· {candidate.original_title ?? "РѕСЂРёРіРёРЅР°Р»СЊРЅРѕРµ РЅР°Р·РІР°РЅРёРµ РЅРµ СѓРєР°Р·Р°РЅРѕ"}
                  </p>
                  <p>{candidate.overview ?? "РћРїРёСЃР°РЅРёРµ РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚."}</p>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={disabled}
                    onClick={() => void runManualAction(() => selectByIds({ tmdb_id: candidate.tmdb_id }))}
                  >
                    Р’С‹Р±СЂР°С‚СЊ СЌС‚РѕС‚ СЃРµСЂРёР°Р»
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
    return <p className="muted">РќРµС‚ РѕР±СЉРµРєС‚РѕРІ РІ СЌС‚РѕРј СЂР°Р·РґРµР»Рµ.</p>;
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
      <h4>РќР°Р№С‚Рё РїРѕ РЅР°Р·РІР°РЅРёСЋ</h4>
      <div className="manual-review-grid">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="РќР°Р·РІР°РЅРёРµ" />
        <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Р“РѕРґ" inputMode="numeric" />
        <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
          <option value="MOVIE">Р¤РёР»СЊРј</option>
          <option value="TV_SHOW">РЎРµСЂРёР°Р»</option>
          <option value="TV_EPISODE">РЎРµСЂРёСЏ</option>
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
          РСЃРєР°С‚СЊ РІ TMDB
        </button>
      </div>
      <h4>Р—Р°РіСЂСѓР·РёС‚СЊ РїРѕ ID</h4>
      <p className="muted manual-review-hint">
        Р—Р°РїРѕР»РЅРёС‚Рµ РѕРґРёРЅ РёР· ID. TMDB ID РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РЅР°РїСЂСЏРјСѓСЋ. IMDb/TVDB РёС‰СѓС‚СЃСЏ С‡РµСЂРµР· TMDB Find.
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
                setIdError(validation.error ?? "РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ ID");
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
          Р—Р°РіСЂСѓР·РёС‚СЊ РїРѕ ID
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void onDecision(item.id, {
              decision: "approved",
              note: "РџРѕРґС‚РІРµСЂР¶РґРµРЅРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»РµРј",
            })
          }
        >
          РџРѕРґС‚РІРµСЂРґРёС‚СЊ РІС‹Р±СЂР°РЅРЅС‹Р№ РІР°СЂРёР°РЅС‚
        </button>
        <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "ignored", note: "РќРµ РґРѕР±Р°РІР»СЏС‚СЊ" })}>
          РќРµ РґРѕР±Р°РІР»СЏС‚СЊ
        </button>
        <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "deferred", note: "РћС‚Р»РѕР¶РµРЅРѕ" })}>
          РћС‚Р»РѕР¶РёС‚СЊ
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
              note: "РСЃРїСЂР°РІР»РµРЅРѕ РІСЂСѓС‡РЅСѓСЋ",
            })
          }
        >
          РЎРѕС…СЂР°РЅРёС‚СЊ РёСЃРїСЂР°РІР»РµРЅРёРµ
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
      <h4>Р¤Р°Р№Р»С‹</h4>
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
      <h4>РћР±СЉРµРєС‚С‹</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{labelMediaType(item.media_type)}</td>
                <td>{labelMediaItemStatus(item.status)}</td>
                <td>{item.parsed_title ?? "вЂ”"}</td>
                <td>
                  <button type="button" onClick={() => void onCandidates(item.id)}>РљР°РЅРґРёРґР°С‚С‹</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>РџР»Р°РЅС‹</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id}>
                <td>{plan.id}</td>
                <td>{labelPlanStatus(plan.status)}</td>
                <td>{formatDate(plan.created_at)}</td>
                <td>
                  <button type="button" onClick={() => void onOperations(plan.id)}>РћРїРµСЂР°С†РёРё</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>РўРµС…РЅРёС‡РµСЃРєРёР№ СЃРїРёСЃРѕРє РѕРїРµСЂР°С†РёР№</summary>
        <div className="table-wrap">
          <table>
            <tbody>
              {operations.map((op) => (
                <tr key={op.id}>
                  <td>{op.id}</td>
                  <td>{labelOperationType(op.operation_type)}</td>
                  <td>{labelOperationStatus(op.status)}</td>
                  <td>{op.validation_status ?? "вЂ”"}</td>
                  <td className="path-text">{op.source_path ?? "вЂ”"}</td>
                  <td className="path-text">{op.target_path ?? "вЂ”"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

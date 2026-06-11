import { useEffect, useState } from "react";
import { ApiError, manualTmdbLookup, manualTmdbSearch } from "../../api";
import { labelMediaType, statusTone, type BadgeTone } from "../../labels";
import type { MediaItem, TmdbMatchCandidate } from "../../types";
import { candidateBackdropUrl, candidatePosterUrl } from "../../utils/tmdb";

type Props = {
  open: boolean;
  item: MediaItem | null;
  candidates: TmdbMatchCandidate[];
  busy: boolean;
  onClose: () => void;
  onSelect: (candidateId: number) => void;
  onCandidatesChange: (candidates: TmdbMatchCandidate[]) => void;
  onError: (message: string) => void;
};

function fmt(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
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

function CandidateReviewCard({
  candidate,
  busy,
  onSelect,
}: {
  candidate: TmdbMatchCandidate;
  busy: boolean;
  onSelect: () => void;
}) {
  const poster = candidatePosterUrl(candidate);
  const backdrop = candidateBackdropUrl(candidate);
  return (
    <div className={`candidate-card visual-candidate-card ${candidate.is_selected ? "selected" : ""}`}>
      <div className="candidate-visuals">
        {poster ? (
          <img className="candidate-poster" src={poster} alt={candidate.title} loading="lazy" />
        ) : (
          <div className="poster-placeholder compact-poster-placeholder">Нет постера</div>
        )}
        {backdrop ? <img className="candidate-backdrop" src={backdrop} alt="" loading="lazy" /> : null}
      </div>
      <div className="candidate-content">
        <div className="section-heading">
          <div>
            <strong>{candidate.title}</strong>
            <p className="muted">
              {fmt(candidate.original_title)} · {labelMediaType(candidate.media_type)} · {fmt(candidate.year)}
            </p>
          </div>
          {candidate.is_selected ? <Badge value="MATCHED" label="Выбранный вариант" tone="success" /> : null}
        </div>
        {candidate.overview_is_fallback ? (
          <p className="message warning">Описание на русском не найдено, показан английский вариант.</p>
        ) : null}
        <p>{candidate.overview ?? "Описание отсутствует."}</p>
        <div className="candidate-meta">
          <span>TMDB: {candidate.tmdb_id}</span>
          <span>IMDb: {fmt(candidate.imdb_id)}</span>
          {candidate.tvdb_id ? <span>TVDB: {candidate.tvdb_id}</span> : null}
          {candidate.wikidata_id ? <span>Wikidata: {candidate.wikidata_id}</span> : null}
          <span>Язык: {fmt(candidate.metadata_language)}</span>
          <span>Оценка: {candidate.score.toFixed(2)}</span>
          <span>Рейтинг: {fmt(candidate.vote_average)}</span>
        </div>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || candidate.is_selected || candidate.id < 0}
          onClick={onSelect}
        >
          {candidate.is_selected ? "Этот вариант выбран" : "Выбрать этот вариант"}
        </button>
      </div>
    </div>
  );
}

function ManualCandidateSearch({
  itemId,
  busy,
  onResults,
  onError,
}: {
  itemId: number;
  busy: boolean;
  onResults: (candidates: TmdbMatchCandidate[]) => void;
  onError: (message: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [year, setYear] = useState("");
  const [mediaType, setMediaType] = useState("movie");
  const [tmdbId, setTmdbId] = useState("");
  const [imdbId, setImdbId] = useState("");
  const [tvdbId, setTvdbId] = useState("");

  return (
    <div className="manual-candidate-search">
      <strong>Найти другой вариант</strong>
      <div className="manual-review-grid">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
        <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Год" inputMode="numeric" />
        <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
          <option value="movie">Фильм</option>
          <option value="tv">Сериал</option>
        </select>
        <input value={tmdbId} onChange={(e) => setTmdbId(e.target.value)} placeholder="TMDB ID" inputMode="numeric" />
        <input value={imdbId} onChange={(e) => setImdbId(e.target.value)} placeholder="IMDb ID" />
        <input value={tvdbId} onChange={(e) => setTvdbId(e.target.value)} placeholder="TVDB ID" inputMode="numeric" />
      </div>
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={busy || !title.trim()}
          onClick={() =>
            void (async () => {
              try {
                onResults(
                  await manualTmdbSearch(itemId, {
                    query: title.trim(),
                    year: year === "" ? null : Number(year),
                    media_type: mediaType,
                  }),
                );
              } catch (err) {
                onError(err instanceof ApiError ? err.message : "Поиск не удался");
              }
            })()
          }
        >
          Искать
        </button>
        <button
          type="button"
          disabled={busy || (!tmdbId && !imdbId && !tvdbId)}
          onClick={() =>
            void (async () => {
              try {
                const candidate = await manualTmdbLookup(itemId, {
                  tmdb_id: tmdbId ? Number(tmdbId) : null,
                  imdb_id: imdbId || null,
                  tvdb_id: tvdbId ? Number(tvdbId) : null,
                  media_type: mediaType,
                });
                onResults([candidate]);
              } catch (err) {
                onError(err instanceof ApiError ? err.message : "Загрузка по ID не удалась");
              }
            })()
          }
        >
          Загрузить по ID
        </button>
      </div>
    </div>
  );
}

export function CandidatesModal({
  open,
  item,
  candidates,
  busy,
  onClose,
  onSelect,
  onCandidatesChange,
  onError,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open || !item) return null;

  const title =
    item.localized_title ?? item.matched_title ?? item.parsed_title ?? item.original_title ?? `Объект #${item.id}`;

  return (
    <div className="modal-overlay candidates-modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal-card candidates-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="section-heading">
          <h3>Кандидаты TMDB: {title}</h3>
          <button type="button" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <ManualCandidateSearch
          itemId={item.id}
          busy={busy}
          onResults={onCandidatesChange}
          onError={onError}
        />
        {candidates.length === 0 ? (
          <p className="muted">Кандидатов пока нет. Сначала запустите поиск в TMDB.</p>
        ) : (
          <div className="candidate-list">
            {candidates.map((candidate) => (
              <CandidateReviewCard
                key={candidate.id}
                candidate={candidate}
                busy={busy}
                onSelect={() => onSelect(candidate.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

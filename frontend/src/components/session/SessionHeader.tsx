import { Link } from "react-router-dom";

import { labelScanSessionStatus, statusTone } from "../../labels";
import { t } from "../../i18n";
import type { ScanSession } from "../../types";
import { formatPath } from "../../utils/formatPath";

function Badge({ value, label }: { value: string; label: string }) {
  return <span className={`status-badge ${statusTone(value)}`}>{label}</span>;
}

type Props = {
  session: ScanSession | null;
  sessionId: number;
  busy: boolean;
  actionLoading: string | null;
  loading: boolean;
  sessionError: string | null;
  nestingWarning: string | null;
  onDelete: () => void;
};

export function SessionHeader({
  session,
  sessionId,
  busy,
  actionLoading,
  loading,
  sessionError,
  nestingWarning,
  onDelete,
}: Props) {
  return (
    <section className="panel">
      <div className="session-header-row">
        <Link to="/">← Назад</Link>
        {session ? (
          <div className="session-header-actions">
            <Badge value={session.status} label={labelScanSessionStatus(session.status)} />
            <button type="button" className="btn-danger" disabled={busy} onClick={onDelete}>
              {actionLoading === "delete" ? t.common.loading : t.detail.deleteSessionButton}
            </button>
          </div>
        ) : null}
      </div>
      <div className="section-heading">
        <div>
          <h2>Сессия #{sessionId}</h2>
          {session ? (
            <p className="muted" title={`${session.source_path} → ${session.target_path}`}>
              <span className="path-short">{formatPath(session.source_path)}</span> →{" "}
              <span className="path-short">{formatPath(session.target_path)}</span>
            </p>
          ) : null}
        </div>
      </div>
      {loading && !session ? <p className="muted">Загрузка...</p> : null}
      {sessionError ? <div className="message error">{sessionError}</div> : null}
      {nestingWarning ? <div className="message warning">{nestingWarning}</div> : null}
      {session?.error_message ? <div className="message error">{session.error_message}</div> : null}
    </section>
  );
}

type Props = {
  open: boolean;
  busy: boolean;
  checked: boolean;
  variant?: "movie" | "tv" | "rollback";
  onCheckedChange: (checked: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ApplyConfirmModal({ open, busy, checked, variant = "movie", onCheckedChange, onConfirm, onCancel }: Props) {
  if (!open) return null;
  const isTv = variant === "tv";
  const isRollback = variant === "rollback";

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card">
        <h3>{isRollback ? "Откатить изменения" : isTv ? "Применить план сериалов" : "Применить план"}</h3>
        <p>
          {isRollback
            ? "MediaForge выполнит откат последнего применённого плана: вернёт перемещённые файлы, удалит созданные NFO и изображения, а пустые созданные папки удалит."
            : isTv
            ? "MediaForge создаст папки сериалов и сезонов, перенесёт серии, запишет tvshow/episode NFO и скачает изображения."
            : "Вы собираетесь применить план. MediaForge начнёт создавать папки, перемещать файлы, записывать metadata и скачивать изображения."}
        </p>
        <p>
          <strong>{isRollback ? "Файлы снова будут изменены на диске." : "Файлы будут изменены на диске."}</strong>
        </p>
        <p>Продолжить?</p>
        <label className="apply-confirm-checkbox">
          <input type="checkbox" checked={checked} onChange={(e) => onCheckedChange(e.target.checked)} />
          {isRollback
            ? "Я понимаю, что MediaForge откатит изменения последнего применения"
            : isTv
              ? "Я понимаю, что серии будут перемещены и metadata будет записана"
              : "Я понимаю, что файлы будут изменены"}
        </label>
        <div className="modal-actions">
          <button type="button" disabled={busy} onClick={onCancel}>
            Отмена
          </button>
          <button type="button" className="btn-primary" disabled={busy || !checked} onClick={onConfirm}>
            {isRollback ? "Откатить" : "Применить"}
          </button>
        </div>
      </div>
    </div>
  );
}

type Props = {
  open: boolean;
  busy: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ApplyConfirmModal({ open, busy, checked, onCheckedChange, onConfirm, onCancel }: Props) {
  if (!open) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal-card">
        <h3>Применить план</h3>
        <p>
          Вы собираетесь применить план. MediaForge начнёт создавать папки, перемещать файлы, записывать metadata и
          скачивать изображения.
        </p>
        <p>
          <strong>Файлы будут изменены на диске.</strong>
        </p>
        <p>Продолжить?</p>
        <label className="apply-confirm-checkbox">
          <input type="checkbox" checked={checked} onChange={(e) => onCheckedChange(e.target.checked)} />
          Я понимаю, что файлы будут изменены
        </label>
        <div className="modal-actions">
          <button type="button" disabled={busy} onClick={onCancel}>
            Отмена
          </button>
          <button type="button" className="btn-primary" disabled={busy || !checked} onClick={onConfirm}>
            Применить
          </button>
        </div>
      </div>
    </div>
  );
}

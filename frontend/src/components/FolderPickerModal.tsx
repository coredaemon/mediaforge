import { useEffect, useState } from "react";
import { ApiError, browseDirectory, getFilesystemRoots } from "../api";
import { t } from "../i18n";
import type { BrowseResult } from "../types";

interface FolderPickerModalProps {
  isOpen: boolean;
  initialPath?: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function FolderPickerModal({ isOpen, initialPath, onSelect, onClose }: FolderPickerModalProps) {
  const [roots, setRoots] = useState<string[]>([]);
  const [browse, setBrowse] = useState<BrowseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    void loadRoots();
    if (initialPath) {
      void navigate(initialPath);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  async function loadRoots() {
    try {
      const data = await getFilesystemRoots();
      setRoots(data);
    } catch {
      setRoots([]);
    }
  }

  async function navigate(path: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await browseDirectory(path);
      setBrowse(result);
      if (!result.readable && result.error) {
        setError(result.error);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка загрузки папки");
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) {
    return null;
  }

  const currentPath = browse?.current_path ?? "";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <strong>{t.picker.title}</strong>
          <button type="button" className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Drives / roots */}
        {roots.length > 0 ? (
          <div className="roots-row">
            <span className="muted">{t.picker.drives}:</span>
            {roots.map((root) => (
              <button key={root} type="button" className="root-btn" onClick={() => void navigate(root)}>
                {root}
              </button>
            ))}
          </div>
        ) : null}

        {/* Current path breadcrumb */}
        {currentPath ? (
          <div className="current-path">
            <span className="muted">{t.picker.currentPath}: </span>
            <span className="path-text">{currentPath}</span>
          </div>
        ) : null}

        {/* Up button */}
        {browse?.parent_path ? (
          <button type="button" className="up-btn" onClick={() => void navigate(browse.parent_path!)}>
            {t.picker.up}
          </button>
        ) : null}

        {/* Error */}
        {error ? <div className="message error">{error}</div> : null}

        {/* Directory list */}
        <div className="folder-list">
          {loading ? <p className="muted" style={{ padding: "0.75rem" }}>{t.common.loading}</p> : null}
          {!loading && browse && browse.directories.length === 0 && browse.readable ? (
            <p className="muted" style={{ padding: "0.75rem" }}>{t.picker.emptyFolder}</p>
          ) : null}
          {!loading && browse
            ? browse.directories.map((dir) => (
                <div
                  key={dir.path}
                  className="folder-item"
                  role="button"
                  tabIndex={0}
                  onClick={() => void navigate(dir.path)}
                  onKeyDown={(e) => e.key === "Enter" && void navigate(dir.path)}
                >
                  📁 {dir.name}
                </div>
              ))
            : null}
        </div>

        {/* Actions */}
        <div className="form-actions">
          <button
            type="button"
            disabled={!currentPath}
            onClick={() => {
              onSelect(currentPath);
              onClose();
            }}
          >
            {t.picker.selectButton}
          </button>
          <button type="button" onClick={onClose}>
            {t.common.cancel}
          </button>
        </div>
      </div>
    </div>
  );
}

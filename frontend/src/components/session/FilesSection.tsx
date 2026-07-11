import type { MediaFile } from "../../types";

type Props = {
  files: MediaFile[];
};

export function FilesSection({ files }: Props) {
  if (files.length === 0) {
    return <p className="muted compact-section-row">Файлов пока нет.</p>;
  }
  return (
    <section className="panel">
      <h3>Файлы</h3>
      <p className="muted">Найдено файлов: {files.length}</p>
    </section>
  );
}

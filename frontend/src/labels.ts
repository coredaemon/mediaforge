export type BadgeTone = "success" | "warning" | "danger" | "neutral" | "info";

const mediaTypeLabels: Record<string, string> = {
  MOVIE: "Фильм",
  TV_SHOW: "Сериал",
  TV_EPISODE: "Серия",
  EXTRA: "Дополнительно",
  UNKNOWN: "Неизвестно",
  movie: "Фильм",
  tv: "Сериал",
};

const mediaItemStatusLabels: Record<string, string> = {
  DISCOVERED: "Найдено",
  NEEDS_REVIEW: "Проверить",
  IGNORED: "Игнорируется",
  MATCHING: "Ищем в TMDB",
  MATCHED: "Найдено в TMDB",
  UNMATCHED: "Не найдено",
};

const scanSessionStatusLabels: Record<string, string> = {
  CREATED: "Создана",
  DISCOVERING: "Сканирование",
  DISCOVERED: "Файлы найдены",
  PARSING: "Распознавание",
  PARSED: "Распознано",
  FAILED: "Ошибка",
  CANCELLED: "Отменена",
};

const operationTypeLabels: Record<string, string> = {
  CREATE_DIR: "Создать папку",
  MOVE_FILE: "Переместить файл",
  COPY_FILE: "Скопировать файл",
  WRITE_TEXT_FILE: "Записать метаданные",
  DOWNLOAD_FILE: "Скачать изображение",
  DELETE_EMPTY_DIR: "Удалить пустую папку",
};

const operationPreviewLabels: Record<string, string> = {
  CREATE_DIR: "Будет создана папка",
  MOVE_FILE: "Будет перемещён файл",
  COPY_FILE: "Будет скопирован файл",
  WRITE_TEXT_FILE: "Будет записан файл метаданных",
  DOWNLOAD_FILE: "Будет скачано изображение",
  DELETE_EMPTY_DIR: "Будет удалена пустая папка",
};

const operationStatusLabels: Record<string, string> = {
  PENDING: "Ожидает",
  RUNNING: "Выполняется",
  DONE: "Готово",
  FAILED: "Ошибка",
  SKIPPED: "Пропущено",
  ROLLED_BACK: "Откачено",
};

const planStatusLabels: Record<string, string> = {
  DRAFT: "Черновик",
  READY: "Готов",
  APPLYING: "Применяется",
  APPLIED: "Применён",
  PARTIAL: "Частично",
  COMPLETED: "Выполнен",
  FAILED: "Ошибка",
  ROLLED_BACK: "Откачено",
  running: "Выполняется",
  completed: "Выполнен",
  failed: "Ошибка",
  partial: "Частично",
  rolled_back: "Откачено",
};

const reviewDecisionLabels: Record<string, string> = {
  pending: "Ожидает решения",
  approved: "Подтверждено",
  ignored: "Исключено",
  deferred: "Отложено",
  manual_override: "Исправлено вручную",
};

export function labelMediaType(value: string | null | undefined): string {
  return value ? (mediaTypeLabels[value] ?? value) : "Неизвестно";
}

export function labelMediaItemStatus(value: string | null | undefined): string {
  return value ? (mediaItemStatusLabels[value] ?? value) : "Неизвестно";
}

export function labelScanSessionStatus(value: string | null | undefined): string {
  return value ? (scanSessionStatusLabels[value] ?? value) : "Неизвестно";
}

export function labelOperationType(value: string | null | undefined): string {
  return value ? (operationTypeLabels[value] ?? value) : "Неизвестно";
}

export function labelOperationPreview(value: string | null | undefined): string {
  return value ? (operationPreviewLabels[value] ?? labelOperationType(value)) : "Операция";
}

export function labelOperationStatus(value: string | null | undefined): string {
  return value ? (operationStatusLabels[value] ?? value) : "Неизвестно";
}

export function labelPlanStatus(value: string | null | undefined): string {
  return value ? (planStatusLabels[value] ?? value) : "Неизвестно";
}

export function labelReviewDecision(value: string | null | undefined): string {
  return value ? (reviewDecisionLabels[value] ?? value) : "Неизвестно";
}

const matchSourceLabels: Record<string, string> = {
  tmdb: "TMDB",
  sidecar_tmdb_id: "Локальный ID",
  sidecar_imdb_id: "Локальный ID",
  sidecar_tvdb_id: "Локальный ID",
  memory: "Память",
  manual: "Вручную",
};

export function labelMatchSource(value: string | null | undefined): string {
  if (!value) return "—";
  return matchSourceLabels[value] ?? value;
}

export function statusTone(value: string | null | undefined): BadgeTone {
  if (!value) return "neutral";
  if (["MATCHED", "READY", "DONE", "COMPLETED", "APPLIED", "PARSED", "DISCOVERED", "approved"].includes(value)) return "success";
  if (["ignored", "deferred", "ROLLED_BACK", "rolled_back"].includes(value)) return "warning";
  if (["NEEDS_REVIEW", "DRAFT"].includes(value)) return "warning";
  if (["FAILED", "UNMATCHED"].includes(value)) return "danger";
  if (["DISCOVERING", "PARSING", "MATCHING", "RUNNING", "APPLYING"].includes(value)) return "info";
  return "neutral";
}

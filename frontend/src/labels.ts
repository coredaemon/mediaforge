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
  COMPLETED: "Выполнен",
  FAILED: "Ошибка",
  ROLLED_BACK: "Откачен",
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

export function statusTone(value: string | null | undefined): BadgeTone {
  if (!value) return "neutral";
  if (["MATCHED", "READY", "DONE", "COMPLETED", "PARSED", "DISCOVERED"].includes(value)) return "success";
  if (["NEEDS_REVIEW", "DRAFT"].includes(value)) return "warning";
  if (["FAILED", "UNMATCHED"].includes(value)) return "danger";
  if (["DISCOVERING", "PARSING", "MATCHING", "RUNNING", "APPLYING"].includes(value)) return "info";
  return "neutral";
}

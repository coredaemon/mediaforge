import type { LlmPreflightCheck } from "./types";

export function humanizeAiError(
  error: string | null | undefined,
  errorType?: string | null,
  statusHint?: number | null,
): string {
  if (errorType === "not_configured") {
    return "Облачная модель не настроена. Выберите провайдер и модель в настройках.";
  }
  if (errorType === "invalid_json") {
    return "Облачная модель ответила, но JSON некорректен. Попробуйте другую модель.";
  }
  if (statusHint === 503 || errorType === "temporary_unavailable" || (error && /\b503\b/.test(error))) {
    return "Облачная модель временно недоступна. Попробуйте ещё раз позже или выберите другую модель.";
  }
  if (statusHint === 429 || errorType === "rate_limited") {
    return "Превышен лимит запросов к облачной модели. Попробуйте позже или выберите запасную модель.";
  }
  if (statusHint === 401 || statusHint === 403 || errorType === "auth_error") {
    return "API-ключ не принят провайдером. Проверьте ключ в настройках.";
  }
  if (statusHint === 404 || errorType === "model_not_found") {
    return "Модель не найдена у провайдера. Нажмите «Найти модели» и выберите модель из списка.";
  }
  if (errorType === "timeout" || (error && /timeout/i.test(error))) {
    return "Облачная модель не ответила вовремя. Можно попробовать ещё раз или выбрать более быструю модель.";
  }
  if (errorType === "connection_error") {
    return "Не удалось подключиться к облачной модели. Проверьте сеть и настройки провайдера.";
  }
  if (error) {
    return "Ошибка облачной модели. Откройте технические детали для подробностей.";
  }
  return "Ошибка облачной модели.";
}

export function formatAiStatusLabel(
  status: string | null,
  validJson: boolean | null,
  hasError: boolean,
): string {
  if (!status || status === "not_run") return "не запускалось";
  if (status === "success" && hasError) return "ответ получен, формат исправлен автоматически";
  if (status === "success") return "успешно";
  if (status === "skipped") return "пропущено";
  if (status === "failed" && validJson === false) return "ошибка вызова или некорректный JSON";
  if (status === "failed") return "ошибка";
  return status;
}

export function formatPreflightStatusLabel(check: LlmPreflightCheck | null | undefined): string {
  if (!check) return "не запускалось";
  if (check.ok) return `работает, ${check.duration_ms} мс`;
  if (check.error_type === "not_configured") return "не настроена";
  if (check.error_type === "temporary_unavailable" || check.retryable) return "временно недоступна";
  if (check.error_type === "auth_error") return "ошибка ключа";
  if (check.error_type === "model_not_found") return "модель не найдена";
  if (check.error_type === "rate_limited") return "превышен лимит";
  if (check.error_type === "timeout") return "таймаут";
  if (check.error_type === "invalid_json") return "некорректный JSON";
  if (check.error_type === "connection_error") return "ошибка соединения";
  return "ошибка";
}

export function getPreflightShortMessage(check: LlmPreflightCheck | null | undefined): string | null {
  if (!check || check.ok) return null;
  return check.human_message ?? humanizeAiError(check.error, check.error_type);
}

export function isRetryableErrorLabel(check: LlmPreflightCheck | null | undefined): boolean {
  return Boolean(check?.retryable);
}

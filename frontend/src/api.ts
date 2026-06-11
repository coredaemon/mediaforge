import type {
  AppSettingsRead,
  AppSettingsUpdate,
  BrowseResult,
  CloudAiTestRequest,
  CloudModelsRequest,
  CloudModelsResult,
  HealthResponse,
  LocalModelsResult,
  MediaFile,
  MediaItem,
  OperationPlan,
  PlanOperation,
  RecognitionCorrection,
  RecognitionCorrectionCreate,
  RecognitionNormalizeResult,
  RecognitionPreflightResult,
  RecognitionTokenRule,
  ReviewDecisionRequest,
  ScanSession,
  ScanSessionCreate,
  TestConnectionResult,
  TmdbManualLookupRequest,
  TmdbManualSearchRequest,
  TmdbMatchCandidate,
  TmdbMatchResult,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type PydanticError = { msg?: string; loc?: (string | number)[]; type?: string };

function formatPydanticErrors(errors: PydanticError[]): string {
  return errors
    .map((e) => {
      const field = e.loc ? e.loc.filter((l) => l !== "body").join(" → ") : "";
      return field ? `${field}: ${e.msg ?? "invalid"}` : (e.msg ?? "invalid");
    })
    .join("; ");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      ...init,
    });
  } catch {
    // Network-level error: backend is down or unreachable.
    throw new ApiError(0, `Backend недоступен. Проверьте, что сервер запущен на ${API_BASE_URL}`);
  }

  if (!response.ok) {
    let message = `Ошибка ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string | PydanticError[] };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        message = formatPydanticErrors(payload.detail);
      }
    } catch {
      // Response body is not JSON — keep HTTP status message.
      const text = await response.text().catch(() => "");
      if (text) message = `Ошибка ${response.status}: ${text.slice(0, 200)}`;
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function listScanSessions(): Promise<ScanSession[]> {
  return request<ScanSession[]>("/scan-sessions");
}

export function createScanSession(payload: ScanSessionCreate): Promise<ScanSession> {
  return request<ScanSession>("/scan-sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getScanSession(sessionId: number): Promise<ScanSession> {
  return request<ScanSession>(`/scan-sessions/${sessionId}`);
}

export function deleteScanSession(sessionId: number): Promise<{ ok: boolean; id: number }> {
  return request<{ ok: boolean; id: number }>(`/scan-sessions/${sessionId}`, { method: "DELETE" });
}

export function discoverSession(sessionId: number): Promise<ScanSession> {
  return request<ScanSession>(`/scan-sessions/${sessionId}/discover`, { method: "POST" });
}

export function parseSession(sessionId: number): Promise<ScanSession> {
  return request<ScanSession>(`/scan-sessions/${sessionId}/parse`, { method: "POST" });
}

export function matchTmdbSession(sessionId: number, force = false): Promise<TmdbMatchResult> {
  const query = force ? "?force=true" : "";
  return request<TmdbMatchResult>(`/scan-sessions/${sessionId}/match-tmdb${query}`, { method: "POST" });
}

export function normalizeLocalAi(sessionId: number): Promise<RecognitionNormalizeResult> {
  return request<RecognitionNormalizeResult>(`/scan-sessions/${sessionId}/normalize-local-ai`, { method: "POST" });
}

export function resolveWithGemini(sessionId: number): Promise<RecognitionNormalizeResult> {
  return request<RecognitionNormalizeResult>(`/scan-sessions/${sessionId}/resolve-with-gemini`, { method: "POST" });
}

export function recognitionPreflight(): Promise<RecognitionPreflightResult> {
  return request<RecognitionPreflightResult>("/recognition/preflight", { method: "POST" });
}

export function createPlan(sessionId: number, force = false): Promise<OperationPlan> {
  const query = force ? "?force=true" : "";
  return request<OperationPlan>(`/scan-sessions/${sessionId}/plan${query}`, { method: "POST" });
}

export function listFiles(sessionId: number): Promise<MediaFile[]> {
  return request<MediaFile[]>(`/scan-sessions/${sessionId}/files`);
}

export function listItems(sessionId: number): Promise<MediaItem[]> {
  return request<MediaItem[]>(`/scan-sessions/${sessionId}/items`);
}

export function listPlans(sessionId: number): Promise<OperationPlan[]> {
  return request<OperationPlan[]>(`/scan-sessions/${sessionId}/plans`);
}

export function listPlanOperations(planId: number): Promise<PlanOperation[]> {
  return request<PlanOperation[]>(`/operation-plans/${planId}/operations`);
}

export function listTmdbCandidates(itemId: number): Promise<TmdbMatchCandidate[]> {
  return request<TmdbMatchCandidate[]>(`/items/${itemId}/tmdb-candidates`);
}

export function selectTmdbCandidate(itemId: number, candidateId: number): Promise<TmdbMatchCandidate> {
  return request<TmdbMatchCandidate>(`/items/${itemId}/tmdb-candidates/${candidateId}/select`, {
    method: "POST",
  });
}

export function manualTmdbSearch(itemId: number, payload: TmdbManualSearchRequest): Promise<TmdbMatchCandidate[]> {
  return request<TmdbMatchCandidate[]>(`/items/${itemId}/tmdb-search`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function manualTmdbLookup(itemId: number, payload: TmdbManualLookupRequest): Promise<TmdbMatchCandidate> {
  return request<TmdbMatchCandidate>(`/items/${itemId}/tmdb-lookup`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function applyReviewDecision(itemId: number, payload: ReviewDecisionRequest): Promise<MediaItem> {
  return request<MediaItem>(`/items/${itemId}/review-decision`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createRecognitionCorrection(
  itemId: number,
  payload: RecognitionCorrectionCreate,
): Promise<RecognitionCorrection> {
  return request<RecognitionCorrection>(`/items/${itemId}/corrections`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listRecognitionCorrections(): Promise<RecognitionCorrection[]> {
  return request<RecognitionCorrection[]>("/recognition-memory/corrections");
}

export function listRecognitionTokenRules(): Promise<RecognitionTokenRule[]> {
  return request<RecognitionTokenRule[]>("/recognition-memory/token-rules");
}

export function formatTmdbError(message: string): string {
  if (message.includes("TMDB_API_KEY is not configured") || message.includes("не настроен")) {
    return "TMDB API ключ не настроен. Перейдите в Настройки и добавьте ключ.";
  }
  return message;
}

// Settings
export function getSettings(): Promise<AppSettingsRead> {
  return request<AppSettingsRead>("/settings");
}

export function updateSettings(payload: AppSettingsUpdate): Promise<AppSettingsRead> {
  return request<AppSettingsRead>("/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function testTmdbConnection(apiKey?: string): Promise<TestConnectionResult> {
  const query = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
  return request<TestConnectionResult>(`/settings/test-tmdb${query}`, { method: "POST" });
}

export function testAiConnection(): Promise<TestConnectionResult> {
  return request<TestConnectionResult>("/settings/test-ai", { method: "POST" });
}

export function getCloudAiModels(payload: CloudModelsRequest): Promise<CloudModelsResult> {
  return request<CloudModelsResult>("/settings/cloud-ai/models", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function testCloudAi(payload: CloudAiTestRequest): Promise<RecognitionPreflightResult["cloud"]> {
  return request<RecognitionPreflightResult["cloud"]>("/settings/cloud-ai/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getOllamaModels(endpoint?: string): Promise<LocalModelsResult> {
  const query = endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : "";
  return request<LocalModelsResult>(`/settings/local-ai/ollama/models${query}`);
}

export function getLmStudioModels(endpoint?: string): Promise<LocalModelsResult> {
  const query = endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : "";
  return request<LocalModelsResult>(`/settings/local-ai/lmstudio/models${query}`);
}

// Filesystem
export function getFilesystemRoots(): Promise<string[]> {
  return request<string[]>("/filesystem/roots");
}

export function browseDirectory(path: string): Promise<BrowseResult> {
  return request<BrowseResult>(`/filesystem/browse?path=${encodeURIComponent(path)}`);
}

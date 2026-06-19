import { useEffect, useState } from "react";
import {
  getCloudAiModels,
  getLmStudioModels,
  getOllamaModels,
  getSettings,
  recognitionPreflight,
  testCloudAi,
  testTmdbConnection,
  updateSettings,
} from "../api";
import { humanizeAiError } from "../aiLabels";
import { t } from "../i18n";
import type { AppSettingsRead, CloudModel, LlmPreflightCheck } from "../types";
import { FolderPickerModal } from "./FolderPickerModal";

type AiProvider = "none" | "gemini" | "ollama" | "lmstudio" | "custom";
type CloudAiProvider = "none" | "gemini" | "openai" | "openrouter" | "custom";

interface WizardData {
  tmdbKey: string;
  aiProvider: AiProvider;
  aiApiKey: string;
  aiBaseUrl: string;
  aiModel: string;
  cloudAiProvider: CloudAiProvider;
  cloudAiApiKey: string;
  cloudAiBaseUrl: string;
  cloudAiModel: string;
  cloudAiFallbackProvider: CloudAiProvider;
  cloudAiFallbackApiKey: string;
  cloudAiFallbackModel: string;
  openrouterApiKey: string;
  openrouterBaseUrl: string;
  openrouterFastChain: string[];
  openrouterSmartChain: string[];
  recognitionAiEnabled: boolean;
  sourcePath: string;
  targetPath: string;
}

interface SetupWizardProps {
  editMode?: boolean;
  onComplete: () => void;
}

type Step = 1 | 2 | 3 | 4 | 5;

type TestUiStatus = "idle" | "success" | "error";

interface CloudTestState {
  status: TestUiStatus;
  message: string;
  technicalError?: string;
  attempts?: ChainAttempt[];
}

interface ChainAttempt {
  model: string;
  ok: boolean;
  durationMs: number;
  attempts?: number;
  httpStatus?: number | null;
  errorType?: string | null;
  error?: string | null;
  humanMessage?: string | null;
  responseValidJson?: boolean;
}

function emptyCloudTest(): CloudTestState {
  return { status: "idle", message: "" };
}

function cloudTestFromResult(result: LlmPreflightCheck): CloudTestState {
  const attempts =
    result.attempted_models?.map((attempt) => ({
      model: attempt.model,
      ok: attempt.ok,
      durationMs: attempt.duration_ms,
      attempts: attempt.attempts,
      httpStatus: attempt.http_status,
      errorType: attempt.error_type,
      error: attempt.error,
      humanMessage: attempt.human_message,
      responseValidJson: attempt.response_valid_json,
    })) ?? [];
  if (result.ok) {
    return {
      status: "success",
      message: result.human_message ?? `Подключение успешно (${result.duration_ms} мс, попыток: ${result.attempts ?? 1})`,
      attempts,
    };
  }
  return {
    status: "error",
    message: result.human_message ?? humanizeAiError(result.error, result.error_type),
    technicalError: result.error ?? undefined,
    attempts,
  };
}

function CloudTestMessage({ test }: { test: CloudTestState }) {
  if (test.status === "idle") return null;
  return (
    <div className={`message ${test.status === "success" ? "info" : "error"}`}>
      {test.message}
      {test.technicalError ? (
        <details className="technical-error">
          <summary>Технические детали</summary>
          <pre>{test.technicalError}</pre>
        </details>
      ) : null}
      {test.attempts && test.attempts.length > 0 ? (
        <ul className="chain-attempts">
          {test.attempts.map((attempt, index) => (
            <li key={`${attempt.model}-${index}`} className={attempt.ok ? "ok" : "failed"}>
              <strong>{attempt.ok ? "Успешно" : "Пропущено"}:</strong> {attempt.model}
              <span className="muted"> {attempt.durationMs} мс</span>
              {!attempt.ok && attempt.humanMessage ? <span> — {attempt.humanMessage}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

interface ModelSearchSelectProps {
  label: string;
  value: string;
  models: CloudModel[];
  placeholder: string;
  onChange: (value: string) => void;
}

function ModelSearchSelect({ label, value, models, placeholder, onChange }: ModelSearchSelectProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "free" | "paid">("all");
  const normalizedQuery = query.trim().toLowerCase();
  const visibleModels = models
    .filter((model) => {
      if (filter === "free" && !model.is_free) return false;
      if (filter === "paid" && model.is_free) return false;
      if (!normalizedQuery) return true;
      return [model.id, model.label, model.display_name ?? "", model.provider ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);
    })
    .slice(0, 50);
  const knownValue = !value || models.length === 0 || models.some((model) => model.id === value);

  return (
    <label className="model-search">
      <span>{label}</span>
      <input
        value={value || query}
        onChange={(event) => {
          const nextValue = event.target.value;
          onChange(nextValue);
          setQuery(nextValue);
        }}
        placeholder={placeholder}
      />
      <div className="model-filter-row" aria-label="Фильтр моделей">
        <button type="button" className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
          Все
        </button>
        <button type="button" className={filter === "free" ? "active" : ""} onClick={() => setFilter("free")}>
          Бесплатные
        </button>
        <button type="button" className={filter === "paid" ? "active" : ""} onClick={() => setFilter("paid")}>
          Платные
        </button>
      </div>
      {models.length === 0 ? (
        <small className="muted">Модели ещё не загружены. Нажмите «Найти модели» или введите model id вручную.</small>
      ) : null}
      {value && !knownValue ? (
        <small className="muted">Этой модели нет в загруженном списке. Она будет сохранена как ручной model id.</small>
      ) : null}
      {visibleModels.length > 0 ? (
        <div className="model-results">
          {visibleModels.map((model) => (
            <button
              key={model.id}
              type="button"
              className={model.id === value ? "selected" : ""}
              onClick={() => {
                onChange(model.id);
                setQuery("");
              }}
            >
              <span>{model.label || model.id}</span>
              <small>
                {model.provider ? `${model.provider} · ` : ""}
                {model.is_free ? "бесплатная" : "платная"}
                {model.context_length ? ` · ${model.context_length.toLocaleString("ru-RU")} токенов` : ""}
              </small>
            </button>
          ))}
        </div>
      ) : models.length > 0 ? (
        <small className="muted">По этому запросу моделей не найдено. Можно ввести model id вручную.</small>
      ) : null}
    </label>
  );
}

const AI_PROVIDER_LABELS: Record<AiProvider, string> = {
  none: t.wizard.aiProviders.none,
  gemini: t.wizard.aiProviders.gemini,
  ollama: t.wizard.aiProviders.ollama,
  lmstudio: t.wizard.aiProviders.lmstudio,
  custom: t.wizard.aiProviders.custom,
};

/** Normalise path for equality comparison: forward slashes, no trailing slash, lowercase. */
function normalisePath(p: string): string {
  return p.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

/** Returns a validation error if paths conflict (same, or one contains the other), else null. */
function detectPathConflict(source: string, target: string): string | null {
  if (!source.trim() || !target.trim()) return null;
  const s = normalisePath(source);
  const tgt = normalisePath(target);
  if (s === tgt) {
    return "Папка с файлами и папка медиатеки не должны совпадать. Выберите отдельную папку для результата.";
  }
  if (tgt.startsWith(s + "/")) {
    return (
      "Папка медиатеки находится внутри папки с файлами. " +
      "Выберите отдельную папку, иначе MediaForge может повторно сканировать уже обработанные файлы."
    );
  }
  if (s.startsWith(tgt + "/")) {
    return "Папка с файлами находится внутри папки медиатеки. Выберите отдельную папку с исходниками.";
  }
  return null;
}

export function SetupWizard({ editMode = false, onComplete }: SetupWizardProps) {
  const [step, setStep] = useState<Step>(editMode ? 2 : 1);
  const [data, setData] = useState<WizardData>({
    tmdbKey: "",
    aiProvider: "none",
    aiApiKey: "",
    aiBaseUrl: "",
    aiModel: "",
    cloudAiProvider: "gemini",
    cloudAiApiKey: "",
    cloudAiBaseUrl: "",
    cloudAiModel: "gemini-2.0-flash",
    cloudAiFallbackProvider: "none",
    cloudAiFallbackApiKey: "",
    cloudAiFallbackModel: "",
    openrouterApiKey: "",
    openrouterBaseUrl: "https://openrouter.ai/api/v1",
    openrouterFastChain: [],
    openrouterSmartChain: [],
    recognitionAiEnabled: true,
    sourcePath: "",
    targetPath: "",
  });
  const [savedSettings, setSavedSettings] = useState<AppSettingsRead | null>(null);

  // Load current settings on mount to show "key saved" indicators.
  useEffect(() => {
    getSettings()
      .then((s) => {
        setSavedSettings(s);
        setData((prev) => ({
          ...prev,
          aiProvider: (s.ai_provider as AiProvider | null) ?? "none",
          aiBaseUrl: s.ai_base_url ?? "",
          aiModel: s.ai_model ?? "",
          cloudAiProvider: (s.cloud_ai_provider as CloudAiProvider | null) ?? "gemini",
          cloudAiBaseUrl: s.cloud_ai_base_url ?? "",
          cloudAiModel: s.cloud_ai_model ?? "gemini-2.0-flash",
          cloudAiFallbackProvider: (s.cloud_ai_fallback_provider as CloudAiProvider | null) ?? "none",
          cloudAiFallbackModel: s.cloud_ai_fallback_model ?? "",
          openrouterBaseUrl: s.openrouter_base_url ?? "https://openrouter.ai/api/v1",
          openrouterFastChain: s.openrouter_fast_chain ?? [],
          openrouterSmartChain: s.openrouter_smart_chain ?? [],
          recognitionAiEnabled: s.recognition_ai_enabled,
          sourcePath: prev.sourcePath || s.default_source_path || "",
          targetPath: prev.targetPath || s.default_target_path || "",
        }));
      })
      .catch(() => {
        // Backend may not be reachable yet — continue without prefill.
      });
  }, []);

  const tmdbConfigured = savedSettings?.tmdb_configured ?? false;

  const [tmdbShowKey, setTmdbShowKey] = useState(false);
  const [tmdbTestResult, setTmdbTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [tmdbTesting, setTmdbTesting] = useState(false);

  const [, setAiTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [aiModels, setAiModels] = useState<string[]>([]);
  const [aiSearching, setAiSearching] = useState(false);
  const [cloudModels, setCloudModels] = useState<string[]>([]);
  const [cloudFallbackModels, setCloudFallbackModels] = useState<string[]>([]);
  const [openrouterModels, setOpenrouterModels] = useState<CloudModel[]>([]);
  const [openrouterSearching, setOpenrouterSearching] = useState(false);
  const [openrouterFastTest, setOpenrouterFastTest] = useState<CloudTestState>(emptyCloudTest());
  const [openrouterSmartTest, setOpenrouterSmartTest] = useState<CloudTestState>(emptyCloudTest());
  const [openrouterFastTesting, setOpenrouterFastTesting] = useState(false);
  const [openrouterSmartTesting, setOpenrouterSmartTesting] = useState(false);
  const [cloudSearching, setCloudSearching] = useState(false);
  const [cloudFallbackSearching, setCloudFallbackSearching] = useState(false);
  const [primaryCloudTest, setPrimaryCloudTest] = useState<CloudTestState>(emptyCloudTest());
  const [fallbackCloudTest, setFallbackCloudTest] = useState<CloudTestState>(emptyCloudTest());
  const [overallCloudTest, setOverallCloudTest] = useState<CloudTestState>(emptyCloudTest());
  const [primaryCloudTesting, setPrimaryCloudTesting] = useState(false);
  const [fallbackCloudTesting, setFallbackCloudTesting] = useState(false);
  const [overallCloudTesting, setOverallCloudTesting] = useState(false);

  const [pickerOpen, setPickerOpen] = useState<"source" | "target" | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Computed: conflict message if paths are identical or nested, null if ok.
  const folderConflictMsg = detectPathConflict(data.sourcePath, data.targetPath);
  const foldersConflict = folderConflictMsg !== null;

  function update(patch: Partial<WizardData>) {
    setData((prev) => ({ ...prev, ...patch }));
  }

  async function handleTestTmdb() {
    setTmdbTesting(true);
    setTmdbTestResult(null);
    try {
      // Pass new key if user typed one; otherwise backend uses the saved key.
      const result = await testTmdbConnection(data.tmdbKey || undefined);
      setTmdbTestResult(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка при проверке TMDB";
      setTmdbTestResult({ success: false, message: msg });
    } finally {
      setTmdbTesting(false);
    }
  }

  async function handleSearchModels() {
    setAiSearching(true);
    setAiModels([]);
    try {
      const endpoint = data.aiBaseUrl || undefined;
      const result =
        data.aiProvider === "ollama"
          ? await getOllamaModels(endpoint)
          : await getLmStudioModels(endpoint);
      setAiModels(result.models);
      if (!result.success) {
        setAiTestResult({ success: false, message: result.message ?? "Не удалось найти модели" });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка при поиске моделей";
      setAiTestResult({ success: false, message: msg });
    } finally {
      setAiSearching(false);
    }
  }

  async function handleSearchCloudFallbackModels() {
    setCloudFallbackSearching(true);
    setCloudFallbackModels([]);
    try {
      const result = await getCloudAiModels({
        provider: data.cloudAiFallbackProvider,
        api_key: data.cloudAiFallbackApiKey || data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setCloudFallbackModels(result.models.map((model) => model.id));
      if (!result.success) {
        setFallbackCloudTest({
          status: "error",
          message: result.message ?? "Не удалось загрузить список моделей",
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить список моделей";
      setFallbackCloudTest({ status: "error", message: msg });
    } finally {
      setCloudFallbackSearching(false);
    }
  }

  async function handleSearchCloudModels() {
    setCloudSearching(true);
    setCloudModels([]);
    try {
      const result = await getCloudAiModels({
        provider: data.cloudAiProvider,
        api_key: data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setCloudModels(result.models.map((model) => model.id));
      if (!result.success) {
        setPrimaryCloudTest({
          status: "error",
          message: result.message ?? "Не удалось загрузить список моделей",
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить список моделей";
      setPrimaryCloudTest({ status: "error", message: msg });
    } finally {
      setCloudSearching(false);
    }
  }

  async function handleSearchOpenRouterModels() {
    setOpenrouterSearching(true);
    setOpenrouterModels([]);
    try {
      const result = await getCloudAiModels({
        provider: "openrouter",
        api_key: data.openrouterApiKey || null,
        base_url: data.openrouterBaseUrl || null,
      });
      setOpenrouterModels(result.models);
      if (!result.success) {
        setOpenrouterFastTest({
          status: "error",
          message: result.message ?? "Не удалось загрузить модели OpenRouter",
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить модели OpenRouter";
      setOpenrouterFastTest({ status: "error", message: msg });
    } finally {
      setOpenrouterSearching(false);
    }
  }

  async function handleTestOpenRouterChain(stage: "fast" | "smart") {
    const chain = stage === "fast" ? data.openrouterFastChain : data.openrouterSmartChain;
    const setTesting = stage === "fast" ? setOpenrouterFastTesting : setOpenrouterSmartTesting;
    const setTest = stage === "fast" ? setOpenrouterFastTest : setOpenrouterSmartTest;
    setTesting(true);
    setTest(emptyCloudTest());
    try {
      await updateSettings({
        openrouter_api_key: data.openrouterApiKey || null,
        openrouter_base_url: data.openrouterBaseUrl || null,
        openrouter_fast_chain: data.openrouterFastChain,
        openrouter_smart_chain: data.openrouterSmartChain,
      });
      const result = await testCloudAi({
        provider: "openrouter",
        model: chain[0] ?? "",
        models: chain,
        stage,
        api_key: data.openrouterApiKey || null,
        base_url: data.openrouterBaseUrl || null,
      });
      setTest(cloudTestFromResult(result));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Проверка OpenRouter не удалась";
      setTest({ status: "error", message: humanizeAiError(msg) });
    } finally {
      setTesting(false);
    }
  }

  async function persistAiSettingsForTest() {
    const aiPayload: Record<string, unknown> = {
      ai_provider: data.aiProvider,
      ai_base_url: data.aiBaseUrl || null,
      ai_model: data.aiModel || null,
      cloud_ai_provider: data.cloudAiProvider,
      cloud_ai_base_url: data.cloudAiBaseUrl || null,
      cloud_ai_model: data.cloudAiModel || null,
      cloud_ai_fallback_provider: data.cloudAiFallbackProvider,
      cloud_ai_fallback_model: data.cloudAiFallbackModel || null,
      openrouter_base_url: data.openrouterBaseUrl || null,
      openrouter_fast_chain: data.openrouterFastChain,
      openrouter_smart_chain: data.openrouterSmartChain,
      recognition_ai_enabled: data.recognitionAiEnabled,
    };
    if (data.aiApiKey) aiPayload.ai_api_key = data.aiApiKey;
    if (data.cloudAiApiKey) aiPayload.cloud_ai_api_key = data.cloudAiApiKey;
    if (data.cloudAiFallbackApiKey) aiPayload.cloud_ai_fallback_api_key = data.cloudAiFallbackApiKey;
    if (data.openrouterApiKey) aiPayload.openrouter_api_key = data.openrouterApiKey;
    await updateSettings(aiPayload);
  }

  async function handleTestCloudAi() {
    setPrimaryCloudTesting(true);
    setPrimaryCloudTest(emptyCloudTest());
    try {
      const result = await testCloudAi({
        provider: data.cloudAiProvider,
        model: data.cloudAiModel,
        api_key: data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setPrimaryCloudTest(cloudTestFromResult(result));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Проверка основной модели не удалась";
      setPrimaryCloudTest({ status: "error", message: humanizeAiError(msg) });
    } finally {
      setPrimaryCloudTesting(false);
    }
  }

  async function handleTestCloudFallbackAi() {
    setFallbackCloudTesting(true);
    setFallbackCloudTest(emptyCloudTest());
    try {
      const result = await testCloudAi({
        provider: data.cloudAiFallbackProvider,
        model: data.cloudAiFallbackModel,
        api_key: data.cloudAiFallbackApiKey || data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setFallbackCloudTest(cloudTestFromResult(result));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Проверка запасной модели не удалась";
      setFallbackCloudTest({ status: "error", message: humanizeAiError(msg) });
    } finally {
      setFallbackCloudTesting(false);
    }
  }

  async function handleTestAllAiConnections() {
    setOverallCloudTesting(true);
    setOverallCloudTest(emptyCloudTest());
    try {
      await persistAiSettingsForTest();
      const result = await recognitionPreflight();
      setPrimaryCloudTest(cloudTestFromResult(result.cloud));
      if (result.cloud_fallback) {
        setFallbackCloudTest(cloudTestFromResult(result.cloud_fallback));
      }
      if (result.ok) {
        setOverallCloudTest({
          status: "success",
          message: result.warning
            ? `AI-подключения работают. ${result.warning}`
            : "Все AI-подключения работают.",
        });
      } else {
        setOverallCloudTest({
          status: "error",
          message: result.message ?? "Проверка AI не пройдена.",
        });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Проверка AI не удалась";
      setOverallCloudTest({ status: "error", message: humanizeAiError(msg) });
    } finally {
      setOverallCloudTesting(false);
    }
  }

  async function handleSave() {
    if (foldersConflict) {
      setSaveError(folderConflictMsg ?? "Проверьте папки.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      // Only include keys if the user actually typed something new.
      // Empty field must NOT overwrite a saved key.
      const payload: Record<string, unknown> = {
        ai_provider: data.aiProvider,
        ai_base_url: data.aiBaseUrl || null,
        ai_model: data.aiModel || null,
        cloud_ai_provider: data.cloudAiProvider,
        cloud_ai_base_url: data.cloudAiBaseUrl || null,
        cloud_ai_model: data.cloudAiModel || null,
        cloud_ai_fallback_provider: data.cloudAiFallbackProvider,
        cloud_ai_fallback_model: data.cloudAiFallbackModel || null,
        openrouter_base_url: data.openrouterBaseUrl || null,
        openrouter_fast_chain: data.openrouterFastChain,
        openrouter_smart_chain: data.openrouterSmartChain,
        recognition_ai_enabled: data.recognitionAiEnabled,
        default_source_path: data.sourcePath || null,
        default_target_path: data.targetPath || null,
        setup_completed: true,
      };
      if (data.tmdbKey) payload.tmdb_api_key = data.tmdbKey;
      if (data.aiApiKey) payload.ai_api_key = data.aiApiKey;
      if (data.cloudAiApiKey) payload.cloud_ai_api_key = data.cloudAiApiKey;
      if (data.cloudAiFallbackApiKey) payload.cloud_ai_fallback_api_key = data.cloudAiFallbackApiKey;
      if (data.openrouterApiKey) payload.openrouter_api_key = data.openrouterApiKey;
      await updateSettings(payload);
      onComplete();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ошибка сохранения";
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  }

  const steps: { num: Step; label: string }[] = [
    { num: 1, label: t.wizard.stepWelcome },
    { num: 2, label: t.wizard.stepTmdb },
    { num: 3, label: t.wizard.stepAi },
    { num: 4, label: t.wizard.stepFolders },
    { num: 5, label: t.wizard.stepDone },
  ];

  return (
    <div className="wizard-wrap">
      {/* Step indicators */}
      <div className="wizard-steps">
        {steps.map((s) => (
          <div key={s.num} className={`wizard-step ${step === s.num ? "active" : step > s.num ? "done" : ""}`}>
            <span className="step-num">{step > s.num ? "✓" : s.num}</span>
            <span className="step-label">{s.label}</span>
          </div>
        ))}
      </div>

      <div className="panel wizard-body">
        {/* ── Step 1: Welcome ── */}
        {step === 1 ? (
          <div>
            <h2>{t.wizard.welcomeTitle}</h2>
            <p>{t.wizard.welcomeText}</p>
            <div className="form-actions">
              <button type="button" className="btn-primary" onClick={() => setStep(2)}>
                {t.wizard.startSetup}
              </button>
            </div>
          </div>
        ) : null}

        {/* ── Step 2: TMDB ── */}
        {step === 2 ? (
          <div>
            <h2>{t.wizard.tmdbTitle}</h2>
            <p>{t.wizard.tmdbDescription}</p>
            <div className="form-grid">
              {/* Key status badge */}
              {tmdbConfigured ? (
                <div className="message info" style={{ marginBottom: 0 }}>
                  ✓ TMDB-ключ сохранён. Оставьте поле пустым, чтобы не менять ключ.
                </div>
              ) : (
                <div className="message warning" style={{ marginBottom: 0 }}>
                  TMDB-ключ не настроен. Получите бесплатный ключ на{" "}
                  <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noreferrer">
                    themoviedb.org
                  </a>
                  .
                </div>
              )}

              <label>
                {tmdbConfigured ? "Новый ключ (необязательно)" : t.wizard.tmdbKeyLabel}
                <div className="input-row">
                  <input
                    type={tmdbShowKey ? "text" : "password"}
                    value={data.tmdbKey}
                    onChange={(e) => {
                      update({ tmdbKey: e.target.value });
                      setTmdbTestResult(null);
                    }}
                    placeholder={
                      tmdbConfigured
                        ? "Введите новый ключ, чтобы заменить сохранённый"
                        : "Вставьте API ключ с themoviedb.org"
                    }
                  />
                  <button type="button" onClick={() => setTmdbShowKey((v) => !v)}>
                    {tmdbShowKey ? "Скрыть" : "Показать"}
                  </button>
                </div>
                <small className="muted">{t.wizard.tmdbKeyHint}</small>
              </label>
              <div className="form-actions">
                {/* Can test saved key OR a newly typed key */}
                <button
                  type="button"
                  disabled={(!data.tmdbKey && !tmdbConfigured) || tmdbTesting}
                  onClick={() => void handleTestTmdb()}
                >
                  {tmdbTesting
                    ? t.wizard.tmdbTesting
                    : data.tmdbKey
                      ? "Проверить новый ключ"
                      : "Проверить сохранённый ключ"}
                </button>
              </div>
              {tmdbTestResult ? (
                <div className={`message ${tmdbTestResult.success ? "info" : "error"}`}>
                  {tmdbTestResult.message}
                </div>
              ) : null}
            </div>
            <div className="form-actions wizard-nav">
              {!editMode ? (
                <button type="button" onClick={() => setStep(1)}>
                  {t.common.prev}
                </button>
              ) : null}
              <button type="button" onClick={() => setStep(3)}>
                {t.common.next}
              </button>
              <button type="button" className="btn-link" onClick={() => setStep(3)}>
                {t.wizard.tmdbSkip}
              </button>
            </div>
          </div>
        ) : null}

        {/* ── Step 3: AI ── */}
        {step === 3 ? (
          <div>
            <h2>{t.wizard.aiTitle}</h2>
            <p>{t.wizard.aiDescription}</p>
            <div className="form-grid">
              <details className="legacy-ai-settings">
                <summary>Расширенные настройки старых AI-провайдеров</summary>
              <label>
                {t.wizard.aiProviderLabel}
                <select
                  value={data.aiProvider}
                  onChange={(e) => {
                    update({ aiProvider: e.target.value as AiProvider, aiBaseUrl: "", aiModel: "" });
                    setAiModels([]);
                    setAiTestResult(null);
                  }}
                >
                  {Object.entries(AI_PROVIDER_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              {data.aiProvider === "gemini" ? (
                <>
                  <label>
                    {t.wizard.aiApiKeyLabel}
                    <input
                      type="password"
                      value={data.aiApiKey}
                      onChange={(e) => update({ aiApiKey: e.target.value })}
                      placeholder="AIza..."
                    />
                  </label>
                  <label>
                    {t.wizard.aiModelLabel}
                    <input
                      value={data.aiModel || t.wizard.aiModelDefault}
                      onChange={(e) => update({ aiModel: e.target.value })}
                    />
                  </label>
                </>
              ) : null}

              {data.aiProvider === "ollama" || data.aiProvider === "lmstudio" ? (
                <>
                  <label>
                    {t.wizard.aiEndpointLabel}
                    <input
                      value={data.aiBaseUrl || (data.aiProvider === "ollama" ? "http://127.0.0.1:11434" : "http://127.0.0.1:1234")}
                      onChange={(e) => update({ aiBaseUrl: e.target.value })}
                    />
                  </label>
                  <div className="form-actions">
                    <button type="button" disabled={aiSearching} onClick={() => void handleSearchModels()}>
                      {aiSearching ? t.wizard.aiSearching : t.wizard.aiSearchModels}
                    </button>
                  </div>
                  {aiModels.length > 0 ? (
                    <label>
                      {t.wizard.aiModelLabel}
                      <select
                        value={data.aiModel}
                        onChange={(e) => update({ aiModel: e.target.value })}
                      >
                        <option value="">— выберите модель —</option>
                        {aiModels.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                </>
              ) : null}

              {data.aiProvider === "custom" ? (
                <>
                  <label>
                    {t.wizard.aiEndpointLabel}
                    <input
                      value={data.aiBaseUrl}
                      onChange={(e) => update({ aiBaseUrl: e.target.value })}
                      placeholder="http://..."
                    />
                  </label>
                  <label>
                    {t.wizard.aiApiKeyLabel} (optional)
                    <input
                      type="password"
                      value={data.aiApiKey}
                      onChange={(e) => update({ aiApiKey: e.target.value })}
                    />
                  </label>
                  <label>
                    {t.wizard.aiModelLabel}
                    <input
                      value={data.aiModel}
                      onChange={(e) => update({ aiModel: e.target.value })}
                    />
                  </label>
                </>
              ) : null}
              </details>

              <label>
                <span>AI-распознавание</span>
                <select
                  value={data.recognitionAiEnabled ? "enabled" : "disabled"}
                  onChange={(e) => update({ recognitionAiEnabled: e.target.value === "enabled" })}
                >
                  <option value="enabled">Включено: проверять LLM перед анализом</option>
                  <option value="disabled">Выключено: только встроенный парсер</option>
                </select>
                {!data.recognitionAiEnabled ? (
                  <small className="muted">
                    AI-распознавание выключено. MediaForge будет использовать только встроенный парсер, качество распознавания может быть ниже.
                  </small>
                ) : null}
              </label>

              {data.recognitionAiEnabled ? (
                <>
                  <h4>AI-провайдер: OpenRouter</h4>
                  <label>
                    API-ключ OpenRouter
                    <input
                      type="password"
                      value={data.openrouterApiKey}
                      onChange={(e) => update({ openrouterApiKey: e.target.value })}
                      placeholder="sk-or-..."
                    />
                    {savedSettings?.openrouter_configured ? (
                      <small className="muted">Ключ сохранён. Оставьте поле пустым, чтобы не менять ключ.</small>
                    ) : null}
                  </label>
                  <label>
                    Адрес API OpenRouter
                    <input
                      value={data.openrouterBaseUrl}
                      onChange={(e) => update({ openrouterBaseUrl: e.target.value })}
                      placeholder="https://openrouter.ai/api/v1"
                    />
                  </label>
                  <div className="form-actions">
                    <button type="button" disabled={openrouterSearching} onClick={() => void handleSearchOpenRouterModels()}>
                      {openrouterSearching ? "Поиск..." : "Найти модели"}
                    </button>
                  </div>
                  <h4>Цепочка быстрого анализа</h4>
                  {[0, 1, 2, 3].map((index) => (
                    <ModelSearchSelect
                      key={`fast-${index}`}
                      label={index === 3 ? "Резервная дешёвая модель" : `Модель ${index + 1}`}
                      value={data.openrouterFastChain[index] ?? ""}
                      models={openrouterModels}
                      placeholder="google/gemini-2.0-flash-exp:free"
                      onChange={(value) => {
                        const chain = [...data.openrouterFastChain];
                        chain[index] = value;
                        update({ openrouterFastChain: chain.map((item) => item.trim()).filter(Boolean) });
                      }}
                    />
                  ))}
                  <small className="muted">
                    Резервная модель используется только если первые три модели быстрого анализа недоступны или вернули плохой ответ.
                  </small>
                  <div className="form-actions">
                    <button
                      type="button"
                      disabled={openrouterFastTesting || data.openrouterFastChain.length === 0}
                      onClick={() => void handleTestOpenRouterChain("fast")}
                    >
                      {openrouterFastTesting ? "Проверка..." : "Проверить быстрый анализ"}
                    </button>
                  </div>
                  <CloudTestMessage test={openrouterFastTest} />
                  <h4>Цепочка умной проверки</h4>
                  {[0, 1].map((index) => (
                    <ModelSearchSelect
                      key={`smart-${index}`}
                      label={`Модель ${index + 1}`}
                      value={data.openrouterSmartChain[index] ?? ""}
                      models={openrouterModels}
                      placeholder="openai/gpt-4o-mini"
                      onChange={(value) => {
                        const chain = [...data.openrouterSmartChain];
                        chain[index] = value;
                        update({ openrouterSmartChain: chain.map((item) => item.trim()).filter(Boolean) });
                      }}
                    />
                  ))}
                  <div className="form-actions">
                    <button
                      type="button"
                      disabled={openrouterSmartTesting || data.openrouterSmartChain.length === 0}
                      onClick={() => void handleTestOpenRouterChain("smart")}
                    >
                      {openrouterSmartTesting ? "Проверка..." : "Проверить умную проверку"}
                    </button>
                  </div>
                  <CloudTestMessage test={openrouterSmartTest} />
                  <details className="legacy-ai-settings">
                    <summary>Расширенные облачные настройки</summary>
                  <h4>Основная облачная модель</h4>
                  <label>
                    Провайдер основной модели
                    <select
                      value={data.cloudAiProvider}
                      onChange={(e) => {
                        update({ cloudAiProvider: e.target.value as CloudAiProvider, cloudAiModel: "", cloudAiBaseUrl: "" });
                        setCloudModels([]);
                      }}
                    >
                      <option value="none">Выключено</option>
                      <option value="gemini">Gemini</option>
                      <option value="openai">OpenAI / ChatGPT</option>
                      <option value="openrouter">OpenRouter</option>
                      <option value="custom">Совместимый с OpenAI API</option>
                    </select>
                  </label>
                  {data.cloudAiProvider !== "none" ? (
                    <>
                      <label>
                        API-ключ основной модели
                        <input
                          type="password"
                          value={data.cloudAiApiKey}
                          onChange={(e) => update({ cloudAiApiKey: e.target.value })}
                          placeholder="Вставьте API-ключ"
                        />
                        {savedSettings?.cloud_primary_configured ? (
                          <small className="muted">Ключ сохранён. Оставьте поле пустым, чтобы не менять.</small>
                        ) : null}
                      </label>
                      {data.cloudAiProvider === "custom" ? (
                        <label>
                          Адрес API
                          <input
                            value={data.cloudAiBaseUrl}
                            onChange={(e) => update({ cloudAiBaseUrl: e.target.value })}
                            placeholder="https://api.example.com"
                          />
                        </label>
                      ) : null}
                      <div className="form-actions">
                        <button type="button" disabled={cloudSearching} onClick={() => void handleSearchCloudModels()}>
                          {cloudSearching ? "Поиск..." : "Найти модели"}
                        </button>
                      </div>
                      {cloudModels.length > 0 ? (
                        <label>
                          Модель
                          <select value={data.cloudAiModel} onChange={(e) => update({ cloudAiModel: e.target.value })}>
                            <option value="">— выберите модель —</option>
                            {cloudModels.map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        </label>
                      ) : data.cloudAiProvider === "custom" ? (
                        <label>
                          Модель
                          <input
                            value={data.cloudAiModel}
                            onChange={(e) => update({ cloudAiModel: e.target.value })}
                            placeholder="model id"
                          />
                        </label>
                      ) : null}
                      <div className="form-actions">
                        <button
                          type="button"
                          disabled={primaryCloudTesting || !data.cloudAiModel}
                          onClick={() => void handleTestCloudAi()}
                        >
                          {primaryCloudTesting ? "Проверка..." : "Проверить основную модель"}
                        </button>
                      </div>
                      <CloudTestMessage test={primaryCloudTest} />
                    </>
                  ) : null}

                  <h4>Запасная облачная модель</h4>
                  <label>
                    Провайдер запасной модели
                    <select
                      value={data.cloudAiFallbackProvider}
                      onChange={(e) => {
                        update({ cloudAiFallbackProvider: e.target.value as CloudAiProvider, cloudAiFallbackModel: "" });
                        setCloudFallbackModels([]);
                      }}
                    >
                      <option value="none">Выключено</option>
                      <option value="gemini">Gemini</option>
                      <option value="openai">OpenAI / ChatGPT</option>
                      <option value="openrouter">OpenRouter</option>
                      <option value="custom">Совместимый с OpenAI API</option>
                    </select>
                  </label>
                  {data.cloudAiFallbackProvider !== "none" ? (
                    <>
                      <label>
                        API-ключ запасной модели
                        <input
                          type="password"
                          value={data.cloudAiFallbackApiKey}
                          onChange={(e) => update({ cloudAiFallbackApiKey: e.target.value })}
                          placeholder="Вставьте запасной API-ключ"
                        />
                        {savedSettings?.cloud_fallback_configured ? (
                          <small className="muted">Ключ сохранён. Оставьте поле пустым, чтобы не менять.</small>
                        ) : (
                          <small className="muted">
                            Если ключ запасной модели не указан, будет использован ключ основной модели для того же провайдера.
                          </small>
                        )}
                      </label>
                      <div className="form-actions">
                        <button type="button" disabled={cloudFallbackSearching} onClick={() => void handleSearchCloudFallbackModels()}>
                          {cloudFallbackSearching ? "Поиск..." : "Найти модели"}
                        </button>
                      </div>
                      {cloudFallbackModels.length > 0 ? (
                        <label>
                          Модель
                          <select value={data.cloudAiFallbackModel} onChange={(e) => update({ cloudAiFallbackModel: e.target.value })}>
                            <option value="">— выберите модель —</option>
                            {cloudFallbackModels.map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <label>
                          Модель
                          <input
                            value={data.cloudAiFallbackModel}
                            onChange={(e) => update({ cloudAiFallbackModel: e.target.value })}
                            placeholder="model id"
                          />
                        </label>
                      )}
                      <div className="form-actions">
                        <button
                          type="button"
                          disabled={fallbackCloudTesting || !data.cloudAiFallbackModel}
                          onClick={() => void handleTestCloudFallbackAi()}
                        >
                          {fallbackCloudTesting ? "Проверка..." : "Проверить запасную модель"}
                        </button>
                      </div>
                      <CloudTestMessage test={fallbackCloudTest} />
                    </>
                  ) : null}
                  {data.cloudAiProvider !== "none" ? (
                    <div className="form-actions">
                      <button
                        type="button"
                        disabled={overallCloudTesting}
                        onClick={() => void handleTestAllAiConnections()}
                      >
                        {overallCloudTesting ? "Проверка..." : "Проверить всё AI-подключение"}
                      </button>
                    </div>
                  ) : null}
                  <CloudTestMessage test={overallCloudTest} />
                  </details>
                </>
              ) : null}

            </div>
            <div className="form-actions wizard-nav">
              <button type="button" onClick={() => setStep(2)}>
                {t.common.prev}
              </button>
              <button type="button" onClick={() => setStep(4)}>
                {t.common.next}
              </button>
            </div>
          </div>
        ) : null}

        {/* ── Step 4: Folders ── */}
        {step === 4 ? (
          <div>
            <h2>{t.wizard.foldersTitle}</h2>
            <p>{t.wizard.foldersDescription}</p>
            <div className="form-grid">
              <label>
                {t.wizard.sourceFolderLabel}
                <div className="input-row">
                  <input
                    value={data.sourcePath}
                    onChange={(e) => update({ sourcePath: e.target.value })}
                    placeholder="D:\Media\Inbox"
                  />
                  <button type="button" onClick={() => setPickerOpen("source")}>
                    {t.common.selectFolder}
                  </button>
                </div>
              </label>
              <label>
                {t.wizard.targetFolderLabel}
                <div className="input-row">
                  <input
                    value={data.targetPath}
                    onChange={(e) => update({ targetPath: e.target.value })}
                    placeholder="D:\Media\Library"
                  />
                  <button type="button" onClick={() => setPickerOpen("target")}>
                    {t.common.selectFolder}
                  </button>
                </div>
              </label>
              {foldersConflict ? (
                <div className="message warning">{folderConflictMsg}</div>
              ) : null}
            </div>
            <div className="form-actions wizard-nav">
              <button type="button" onClick={() => setStep(3)}>
                {t.common.prev}
              </button>
              <button
                type="button"
                disabled={foldersConflict}
                title={foldersConflict ? folderConflictMsg : undefined}
                onClick={() => setStep(5)}
              >
                {t.common.next}
              </button>
            </div>
          </div>
        ) : null}

        {/* ── Step 5: Summary ── */}
        {step === 5 ? (
          <div>
            <h2>{t.wizard.summaryTitle}</h2>
            <div className="summary-grid" style={{ marginBottom: "1.5rem" }}>
              <div className="summary-item">
                <strong>{t.wizard.summaryTmdb}</strong>
                <span>
                  {data.tmdbKey
                    ? "Будет сохранён новый TMDB-ключ"
                    : tmdbConfigured
                      ? "TMDB-ключ сохранён"
                      : "TMDB не настроен"}
                </span>
              </div>
              <div className="summary-item">
                <strong>{t.wizard.summaryAi}</strong>
                <span>
                  {data.recognitionAiEnabled
                    ? `OpenRouter: быстрых моделей ${data.openrouterFastChain.length}, умных моделей ${data.openrouterSmartChain.length}`
                    : "AI-распознавание выключено"}
                </span>
              </div>
              <div className="summary-item">
                <strong>{t.wizard.summarySource}</strong>
                <span>{data.sourcePath || t.wizard.notSet}</span>
              </div>
              <div className="summary-item">
                <strong>{t.wizard.summaryTarget}</strong>
                <span>{data.targetPath || t.wizard.notSet}</span>
              </div>
            </div>
            {saveError ? <div className="message error">{saveError}</div> : null}
            <div className="form-actions wizard-nav">
              <button type="button" onClick={() => setStep(4)}>
                {t.common.prev}
              </button>
              <button type="button" className="btn-primary" disabled={saving} onClick={() => void handleSave()}>
                {saving ? "Сохранение..." : t.wizard.saveAndStart}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {/* Folder picker modals */}
      <FolderPickerModal
        isOpen={pickerOpen === "source"}
        initialPath={data.sourcePath}
        onSelect={(path) => update({ sourcePath: path })}
        onClose={() => setPickerOpen(null)}
      />
      <FolderPickerModal
        isOpen={pickerOpen === "target"}
        initialPath={data.targetPath}
        onSelect={(path) => update({ targetPath: path })}
        onClose={() => setPickerOpen(null)}
      />
    </div>
  );
}

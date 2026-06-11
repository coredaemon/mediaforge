import { useEffect, useState } from "react";
import {
  getCloudAiModels,
  getLmStudioModels,
  getOllamaModels,
  getSettings,
  testAiConnection,
  testCloudAi,
  testTmdbConnection,
  updateSettings,
} from "../api";
import { t } from "../i18n";
import type { AppSettingsRead } from "../types";
import { FolderPickerModal } from "./FolderPickerModal";

type AiProvider = "none" | "gemini" | "ollama" | "lmstudio" | "custom";
type CloudAiProvider = "none" | "gemini" | "openai" | "custom";

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
  recognitionAiEnabled: boolean;
  sourcePath: string;
  targetPath: string;
}

interface SetupWizardProps {
  editMode?: boolean;
  onComplete: () => void;
}

type Step = 1 | 2 | 3 | 4 | 5;

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

  const [aiTestResult, setAiTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [aiTesting, setAiTesting] = useState(false);
  const [aiModels, setAiModels] = useState<string[]>([]);
  const [aiSearching, setAiSearching] = useState(false);
  const [cloudModels, setCloudModels] = useState<string[]>([]);
  const [cloudFallbackModels, setCloudFallbackModels] = useState<string[]>([]);
  const [cloudSearching, setCloudSearching] = useState(false);
  const [cloudFallbackSearching, setCloudFallbackSearching] = useState(false);

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

  async function handleTestAi() {
    setAiTesting(true);
    setAiTestResult(null);
    // Persist AI settings first so the backend can test them.
    const aiPayload: Record<string, unknown> = {
      ai_provider: data.aiProvider,
      ai_base_url: data.aiBaseUrl || null,
      ai_model: data.aiModel || null,
      cloud_ai_provider: data.cloudAiProvider,
      cloud_ai_base_url: data.cloudAiBaseUrl || null,
      cloud_ai_model: data.cloudAiModel || null,
      cloud_ai_fallback_provider: data.cloudAiFallbackProvider,
      cloud_ai_fallback_model: data.cloudAiFallbackModel || null,
      recognition_ai_enabled: data.recognitionAiEnabled,
    };
    if (data.aiApiKey) aiPayload.ai_api_key = data.aiApiKey;
    if (data.cloudAiApiKey) aiPayload.cloud_ai_api_key = data.cloudAiApiKey;
    if (data.cloudAiFallbackApiKey) aiPayload.cloud_ai_fallback_api_key = data.cloudAiFallbackApiKey;
    await updateSettings(aiPayload);
    try {
      const result = await testAiConnection();
      setAiTestResult(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка при проверке AI";
      setAiTestResult({ success: false, message: msg });
    } finally {
      setAiTesting(false);
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
        setAiTestResult({ success: false, message: result.message ?? "Fallback models could not be loaded" });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Fallback models could not be loaded";
      setAiTestResult({ success: false, message: msg });
    } finally {
      setCloudFallbackSearching(false);
    }
  }

  async function handleSearchCloudModels() {
    setCloudSearching(true);
    setCloudModels([]);
    setAiTestResult(null);
    try {
      const result = await getCloudAiModels({
        provider: data.cloudAiProvider,
        api_key: data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setCloudModels(result.models.map((model) => model.id));
      if (!result.success) {
        setAiTestResult({ success: false, message: result.message ?? "Cloud models could not be loaded" });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Cloud models could not be loaded";
      setAiTestResult({ success: false, message: msg });
    } finally {
      setCloudSearching(false);
    }
  }

  async function handleTestCloudAi() {
    setAiTesting(true);
    setAiTestResult(null);
    try {
      const result = await testCloudAi({
        provider: data.cloudAiProvider,
        model: data.cloudAiModel,
        api_key: data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setAiTestResult({
        success: result.ok,
        message: result.ok ? `Cloud AI connected in ${result.duration_ms} ms` : (result.error ?? "Cloud AI test failed"),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Cloud AI test failed";
      setAiTestResult({ success: false, message: msg });
    } finally {
      setAiTesting(false);
    }
  }

  async function handleTestCloudFallbackAi() {
    setAiTesting(true);
    setAiTestResult(null);
    try {
      const result = await testCloudAi({
        provider: data.cloudAiFallbackProvider,
        model: data.cloudAiFallbackModel,
        api_key: data.cloudAiFallbackApiKey || data.cloudAiApiKey || null,
        base_url: data.cloudAiBaseUrl || null,
      });
      setAiTestResult({
        success: result.ok,
        message: result.ok ? `Fallback cloud connected in ${result.duration_ms} ms` : (result.error ?? "Fallback test failed"),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Fallback test failed";
      setAiTestResult({ success: false, message: msg });
    } finally {
      setAiTesting(false);
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
        recognition_ai_enabled: data.recognitionAiEnabled,
        default_source_path: data.sourcePath || null,
        default_target_path: data.targetPath || null,
        setup_completed: true,
      };
      if (data.tmdbKey) payload.tmdb_api_key = data.tmdbKey;
      if (data.aiApiKey) payload.ai_api_key = data.aiApiKey;
      if (data.cloudAiApiKey) payload.cloud_ai_api_key = data.cloudAiApiKey;
      if (data.cloudAiFallbackApiKey) payload.cloud_ai_fallback_api_key = data.cloudAiFallbackApiKey;
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

              <label>
                <span>AI-assisted recognition</span>
                <select
                  value={data.recognitionAiEnabled ? "enabled" : "disabled"}
                  onChange={(e) => update({ recognitionAiEnabled: e.target.value === "enabled" })}
                >
                  <option value="enabled">Enabled: require LLM preflight before analysis</option>
                  <option value="disabled">Disabled: parser-only mode</option>
                </select>
                {!data.recognitionAiEnabled ? (
                  <small className="muted">
                    AI recognition is disabled. MediaForge will use only the deterministic parser, so recognition quality may be lower.
                  </small>
                ) : null}
              </label>

              {data.recognitionAiEnabled ? (
                <>
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
                      <option value="none">Disabled</option>
                      <option value="gemini">Gemini</option>
                      <option value="openai">OpenAI / ChatGPT</option>
                      <option value="custom">Custom OpenAI-compatible</option>
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
                          placeholder="Paste API key"
                        />
                        {savedSettings?.cloud_primary_configured ? (
                          <small className="muted">Ключ сохранён. Оставьте поле пустым, чтобы не менять.</small>
                        ) : null}
                      </label>
                      {data.cloudAiProvider === "custom" ? (
                        <label>
                          Cloud base URL
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
                          Cloud model
                          <input
                            value={data.cloudAiModel}
                            onChange={(e) => update({ cloudAiModel: e.target.value })}
                            placeholder="model id"
                          />
                        </label>
                      ) : null}
                      <div className="form-actions">
                        <button type="button" disabled={aiTesting || !data.cloudAiModel} onClick={() => void handleTestCloudAi()}>
                          {aiTesting ? "Проверка..." : "Проверить основную модель"}
                        </button>
                      </div>
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
                      <option value="none">Disabled</option>
                      <option value="gemini">Gemini</option>
                      <option value="openai">OpenAI / ChatGPT</option>
                      <option value="custom">Custom OpenAI-compatible</option>
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
                          placeholder="Paste fallback API key"
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
                          disabled={aiTesting || !data.cloudAiFallbackModel}
                          onClick={() => void handleTestCloudFallbackAi()}
                        >
                          {aiTesting ? "Проверка..." : "Проверить запасную модель"}
                        </button>
                      </div>
                    </>
                  ) : null}
                </>
              ) : null}

              {data.aiProvider !== "none" ? (
                <div className="form-actions">
                  <button type="button" disabled={aiTesting} onClick={() => void handleTestAi()}>
                    {aiTesting ? t.wizard.aiTesting : t.wizard.aiTest}
                  </button>
                </div>
              ) : null}

              {aiTestResult ? (
                <div className={`message ${aiTestResult.success ? "info" : "error"}`}>
                  {aiTestResult.message}
                </div>
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
                  {data.aiProvider === "none"
                    ? "AI-помощник выключен"
                    : data.aiModel
                      ? `${AI_PROVIDER_LABELS[data.aiProvider]}: ${data.aiModel}`
                      : AI_PROVIDER_LABELS[data.aiProvider]}
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

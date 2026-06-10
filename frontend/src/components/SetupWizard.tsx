import { useEffect, useState } from "react";
import {
  getLmStudioModels,
  getOllamaModels,
  getSettings,
  testAiConnection,
  testTmdbConnection,
  updateSettings,
} from "../api";
import { t } from "../i18n";
import type { AppSettingsRead } from "../types";
import { FolderPickerModal } from "./FolderPickerModal";

type AiProvider = "none" | "gemini" | "ollama" | "lmstudio" | "custom";

interface WizardData {
  tmdbKey: string;
  aiProvider: AiProvider;
  aiApiKey: string;
  aiBaseUrl: string;
  aiModel: string;
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
    };
    if (data.aiApiKey) aiPayload.ai_api_key = data.aiApiKey;
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
        default_source_path: data.sourcePath || null,
        default_target_path: data.targetPath || null,
        setup_completed: true,
      };
      if (data.tmdbKey) payload.tmdb_api_key = data.tmdbKey;
      if (data.aiApiKey) payload.ai_api_key = data.aiApiKey;
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

export const t = {
  appName: "MediaForge",

  // Navigation
  nav: {
    sessions: "Сессии",
    about: "О приложении / Статус",
    settings: "Настройки",
  },

  // Health
  health: {
    online: "Backend подключён",
    checking: "Проверка backend...",
    offline: "Backend недоступен",
  },

  // Common
  common: {
    loading: "Загрузка...",
    error: "Ошибка",
    back: "← Назад",
    save: "Сохранить",
    cancel: "Отмена",
    close: "Закрыть",
    open: "Открыть",
    next: "Далее",
    prev: "Назад",
    done: "Готово",
    check: "Проверить",
    select: "Выбрать",
    selectFolder: "Выбрать папку",
    noData: "Нет данных",
    yes: "Да",
    no: "Нет",
  },

  // Sessions page
  sessions: {
    title: "Сессии сканирования",
    createTitle: "Создать сессию сканирования",
    sourceFolder: "Папка с файлами",
    targetFolder: "Папка медиатеки",
    sourcePlaceholder: "D:/Media/Inbox",
    targetPlaceholder: "D:/Media/Library",
    createButton: "Создать",
    creating: "Создание...",
    noSessions: "Сессий пока нет",
    id: "ID",
    status: "Статус",
    created: "Создана",
    openButton: "Открыть",
    quickStart: "Быстрый старт",
    quickStartHint:
      "Укажите папку с медиафайлами и целевую папку медиатеки, затем нажмите «Создать».",
  },

  // Session detail
  detail: {
    backToSessions: "← Все сессии",
    sessionTitle: "Сессия #",
    sourceFolder: "Папка с файлами",
    targetFolder: "Папка медиатеки",
    status: "Статус",
    updated: "Обновлена",
    safetyNotice:
      "MediaForge работает в безопасном режиме preview. Файлы не перемещаются и не изменяются.",
    // Actions
    discover: "Сканировать",
    discovering: "Сканирование...",
    parse: "Распознать",
    parsing: "Распознавание...",
    matchTmdb: "Найти в TMDB",
    matchingTmdb: "Поиск в TMDB...",
    createPlan: "Построить план",
    planning: "Построение плана...",
    // Sections
    filesSection: "Файлы",
    itemsSection: "Объекты",
    plansSection: "Планы",
    operationsSection: "Операции",
    showCandidates: "Кандидаты TMDB",
    showOperations: "Операции",
    noFiles: "Файлов пока нет. Нажмите «Сканировать».",
    noItems: "Объектов пока нет. Нажмите «Распознать».",
    noPlans: "Планов пока нет. Нажмите «Построить план».",
    noOperations: "Выберите план, чтобы посмотреть операции.",
    noCandidates: "Кандидатов нет.",
    tmdbCandidatesFor: "TMDB-кандидаты для объекта #",
    operationsForPlan: "Операции плана #",
    // Table headers
    kind: "Тип",
    fileName: "Имя файла",
    extension: "Расш.",
    size: "Размер",
    mediaItem: "Объект",
    scanError: "Ошибка",
    mediaType: "Тип медиа",
    parsedTitle: "Распознанное название",
    year: "Год",
    season: "Сезон",
    episode: "Эпизод",
    tmdbId: "TMDB ID",
    matchedTitle: "Совпадение",
    matchedYear: "Год совпадения",
    confidence: "Уверенность",
    needsReview: "Требует проверки",
    planStatus: "Статус",
    operationType: "Тип операции",
    sourcePath: "Откуда",
    targetPath: "Куда",
    score: "Оценка",
    selected: "Выбран",
  },

  // Status page
  statusPage: {
    title: "О приложении / Статус",
    description:
      "MediaForge — локальный организатор медиатеки. Через этот UI можно запустить pipeline discovery → parse → TMDB match → plan без изменения файлов на диске.",
    backendUrl: "Backend URL",
    frontendUrl: "Frontend URL",
    healthLabel: "Backend",
    disclaimer:
      "Apply, rollback, скачивание постеров и запись NFO не реализованы. Планирование — только preview.",
  },

  // Setup wizard
  wizard: {
    stepWelcome: "Добро пожаловать",
    stepTmdb: "TMDB",
    stepAi: "AI-помощник",
    stepFolders: "Папки",
    stepDone: "Готово",
    //
    welcomeTitle: "Добро пожаловать в MediaForge",
    welcomeText:
      "MediaForge поможет привести медиатеку фильмов и сериалов к аккуратной структуре для Jellyfin, Plex и Kodi. На этом этапе приложение только анализирует файлы и строит безопасный план. Файлы не перемещаются.",
    startSetup: "Начать настройку",
    //
    tmdbTitle: "Подключение TMDB",
    tmdbDescription:
      "TMDB используется для автоматического распознавания названий фильмов и сериалов. Ключ хранится только локально на этом компьютере и не попадает в GitHub.",
    tmdbKeyLabel: "TMDB API ключ",
    tmdbKeyPlaceholder: "Вставьте API ключ с themoviedb.org",
    tmdbKeyHint: "Ключ можно получить бесплатно на themoviedb.org/settings/api",
    tmdbSkip: "Пропустить (настроить позже)",
    tmdbTest: "Проверить подключение",
    tmdbTesting: "Проверяется...",
    //
    aiTitle: "AI-помощник",
    aiDescription: "AI-помощник помогает с нестандартными названиями файлов. Можно настроить позже.",
    aiProviderLabel: "Провайдер",
    aiProviders: {
      none: "Не использовать AI",
      gemini: "Gemini (Google)",
      ollama: "Ollama (локальный)",
      lmstudio: "LM Studio (локальный)",
      custom: "Custom OpenAI-compatible",
    },
    aiApiKeyLabel: "API ключ",
    aiModelLabel: "Модель",
    aiModelDefault: "gemini-2.0-flash",
    aiEndpointLabel: "Endpoint",
    aiSearchModels: "Найти модели",
    aiSearching: "Поиск...",
    aiModelsFound: "Найдено моделей:",
    aiNoModels: "Модели не найдены",
    aiTest: "Проверить подключение",
    aiTesting: "Проверяется...",
    //
    foldersTitle: "Папки по умолчанию",
    foldersDescription:
      "Эти пути будут подставляться при создании новой сессии. Их можно изменить для каждой сессии отдельно.",
    sourceFolderLabel: "Папка с файлами",
    targetFolderLabel: "Папка медиатеки",
    //
    summaryTitle: "Настройки готовы",
    summaryTmdb: "TMDB",
    summaryAi: "AI-помощник",
    summarySource: "Папка с файлами",
    summaryTarget: "Папка медиатеки",
    configured: "настроен",
    notConfigured: "не настроен",
    disabled: "выключен",
    notSet: "не указана",
    saveAndStart: "Сохранить и начать работу",
    backToSettings: "Вернуться к настройкам",
  },

  // Folder picker
  picker: {
    title: "Выбор папки",
    drives: "Диски",
    up: "↑ Наверх",
    currentPath: "Текущий путь",
    selectButton: "Выбрать эту папку",
    emptyFolder: "Папка пуста",
    accessDenied: "Нет доступа",
  },
} as const;

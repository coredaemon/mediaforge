# MediaForge

MediaForge — локальный организатор медиатеки фильмов и сериалов. Помогает привести коллекцию к аккуратной структуре для Jellyfin, Plex и Kodi: сканирует папки, парсит имена файлов, сопоставляет метаданные с TMDB и строит безопасный dry-run план. Файлы не перемещаются без явного подтверждения.

Репозиторий публичный. Реальные API-ключи, токены, локальные настройки, базы данных, кэши и медиафайлы никогда не попадают в commits.

## Текущие возможности

`create session → discover → parse → match TMDB → build dry-run plan → inspect operations`

- FastAPI backend, SQLite + SQLAlchemy 2.0 async
- Сканирование папок без изменения файлов
- Детерминированный парсер имён видеофайлов
- Сопоставление с TMDB как каноническим источником метаданных
- Dry-run planning: список будущих операций в БД без реального выполнения
- Веб-интерфейс с мастером первого запуска, выбором папок, поддержкой Ollama/LM Studio/Gemini
- Локальные настройки в SQLite (не попадают в git)

## Быстрый старт на Windows

### Установка (один раз)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

### Запуск

```powershell
.\scripts\start-dev.ps1
```

Откроет два окна PowerShell:
- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

Откройте `http://127.0.0.1:5173` в браузере.

### Первый запуск через мастер

При первом открытии UI покажет мастер настройки (5 шагов):

1. **Добро пожаловать** — описание режима safe preview
2. **TMDB** — вставьте API ключ с [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)
3. **AI-помощник** — выберите провайдера (Gemini, Ollama, LM Studio, Custom) или «Не использовать»
4. **Папки** — выберите папки через встроенный file browser или введите вручную
5. **Готово** — сохранить и начать работу

Вернуться к настройкам позже: кнопка **⚙ Настройки** в шапке.

### Где хранятся настройки

Настройки (в т.ч. ключи) хранятся в локальной SQLite базе `mediaforge.local.sqlite3`.
Файл находится в `.gitignore` и никогда не попадает в репозиторий.

**Ключи не попадают в GitHub.** `GET /settings` возвращает только флаги `tmdb_configured` / `ai_configured`, но не сами ключи.

## Раздельный запуск

```powershell
.\scripts\start-backend.ps1   # Backend на 8000
.\scripts\start-frontend.ps1  # Frontend на 5173
```

## Backend команды

Установить зависимости:

```bash
pip install -e ".[dev]"
```

Инициализировать БД:

```bash
python -m backend.scripts.init_db
```

Запустить backend:

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Health: `GET http://127.0.0.1:8000/health`

## Frontend команды

```bash
cd frontend
npm install
cp .env.example .env    # при необходимости изменить VITE_API_BASE_URL
npm run dev             # dev-сервер на :5173
npm run build           # production build
```

## Как настроить TMDB

1. Зарегистрируйтесь на [themoviedb.org](https://www.themoviedb.org) бесплатно
2. Перейдите в Settings → API → Request an API Key
3. Скопируйте **API Read Access Token** или **API Key (v3 auth)**
4. Вставьте в мастер настройки MediaForge или в `.env`:
   ```
   TMDB_API_KEY=ваш_ключ
   ```

## Как подключить Gemini

1. Получите ключ на [aistudio.google.com](https://aistudio.google.com)
2. В мастере настройки выберите провайдер **Gemini**
3. Вставьте API ключ и укажите модель (например `gemini-2.0-flash`)

## Как подключить Ollama

1. Установите [Ollama](https://ollama.ai) и запустите хотя бы одну модель: `ollama pull mistral`
2. В мастере выберите **Ollama**, нажмите **Найти модели** — список загрузится автоматически
3. Endpoint по умолчанию: `http://127.0.0.1:11434`

## Как подключить LM Studio

1. Запустите [LM Studio](https://lmstudio.ai) и включите Local Server (порт 1234)
2. В мастере выберите **LM Studio**, нажмите **Найти модели**
3. Endpoint по умолчанию: `http://127.0.0.1:1234`

## AI Preflight

AI-assisted recognition starts with `POST /recognition/preflight`. MediaForge sends real short generation requests before analysis:

- local LLM: Ollama `/api/generate` or an OpenAI-compatible `/v1/chat/completions` endpoint
- cloud LLM: Gemini `generateContent`

The prompt asks the model to return strict JSON:

```json
{"ok":true,"provider":"local","test":"mediaforge-preflight"}
```

For Gemini the expected provider is `gemini`. MediaForge parses the response, validates `ok === true`, validates `test === "mediaforge-preflight"`, and checks the provider. Markdown-wrapped JSON is extracted but reported with `response_had_markdown: true`.

## TV series recognition

MediaForge now has a first group-first TV workflow. It builds compact folder tree context, extracts deterministic TV hints, creates show/season/episode records, optionally enriches them through TMDB TV endpoints, and shows a separate TV review block in the session page.

Pipeline:

```text
folder tree -> TV hints -> local grouping -> TMDB TV match -> cloud audit -> TV review -> TV dry-run plan
```

The TV dry-run plan writes operations directly under the selected target root:

```text
{target}/{Show Title} ({Year})/
  tvshow.nfo
  poster.jpg
  fanart.jpg
  Season 01/
    {Show Title} - S01E01 - {Episode Title}.mkv
    {Show Title} - S01E01 - {Episode Title}.nfo
```

No extra `TV Shows` folder is added by the new TV planner. TV apply is intentionally disabled in this release; generated operations are for inspection only. Movie apply remains enabled and unchanged.

## OpenRouter-first AI routing

MediaForge now treats OpenRouter as the preferred AI provider. Settings store an OpenRouter key, base URL, a fast-analysis model chain, and a smart-audit model chain. The raw key is write-only: empty values and placeholders do not overwrite a saved key, and GET settings returns only `openrouter_configured`.

The fast chain is used for first-pass cleanup and TV folder grouping. The smart chain is used for audit/refinement. Each chain tries models in order and falls through on transport errors, retryable HTTP errors, invalid JSON, empty output, or quality-gate failure. Legacy Ollama, Gemini, OpenAI, and custom OpenAI-compatible settings remain available as fallback/advanced paths when OpenRouter is not configured.

OpenRouter model discovery uses `GET https://openrouter.ai/api/v1/models` and shows returned IDs plus metadata such as display name, context length, pricing/free markers, and provider prefix when available. Chat completions use the OpenAI-compatible `POST /chat/completions` endpoint.

## Folder classification and scanner diagnostics

After scanning, MediaForge can classify a folder as `movies`, `tv`, `mixed`, or `unknown` using deterministic evidence from video counts, folder structure, TV episode hints, movie year hints, sidecars, and extensions. The session page shows the classification confidence, reason, known video extensions, ignored extensions, nested folder count, and a warning when files exist but no supported video files were detected.

The scanner now recognizes common TV/video extensions including `.mkv`, `.mp4`, `.avi`, `.mov`, `.m4v`, `.ts`, `.m2ts`, `.mts`, `.webm`, `.wmv`, and `.flv`, case-insensitively. This fixes the real-world failure mode where a TV source folder had files but `video = 0`.

If AI-assisted recognition is enabled, analysis does not continue unless both local and cloud preflight checks pass. If Ollama is down, the selected model is unavailable, Gemini is missing, the key is invalid, or the model returns invalid JSON, the UI stops the pipeline and shows the failed provider, model, duration, error type, and a sanitized response preview. Parser-only mode is available only when AI-assisted recognition is explicitly disabled in settings.

Per-item diagnostics are saved for local AI and Gemini normalization: status, duration, model, JSON validity, and sanitized error text. These diagnostics are shown in the session review cards so it is visible whether AI actually ran. If a model returns useful title/year data but `tmdb_queries` or other fields are in a non-ideal format, MediaForge normalizes them automatically and records a short warning instead of failing the item.

The target folder selected when creating a scan session is the actual destination root. MediaForge does not add a `Movies` subfolder automatically for movies; planned paths look like `{target}/{Title} ({Year})/{Title} ({Year}){ext}`.

Scan sessions can be deleted from the sessions list or session detail page. Deletion removes only analysis records from SQLite (files, items, TMDB candidates, plans, operations). User correction history is detached, not deleted. Global processed media memory and recognition token rules are preserved. Media files on disk are never deleted.

## Память обработанных медиа

MediaForge stores a global `ProcessedMediaRecord` for each recognized video file. File identity uses `file_name + size + modified_at` (Windows-safe, case-insensitive). When a later scan session finds the same unchanged file, MediaForge restores the previous title/year/TMDB match/external IDs and skips local AI, Gemini, and TMDB unless `force=true`. The session dashboard shows how many files were reused from memory.

## Русская локализация TMDB

TMDB search and details use `language=ru-RU` by default (`include_adult=false`, `region=RU` for movies). If Russian title/overview is missing, MediaForge falls back to `en-US`. Poster/backdrop selection prefers `ru`, then neutral/null, then `en`.

## External IDs for Jellyfin/Plex/Kodi

After TMDB match or manual candidate selection, MediaForge stores TMDB ID plus external IDs (`imdb_id`, `tvdb_id`, `wikidata_id`), localized title/overview, poster/backdrop URLs, and metadata language on the media item, TMDB candidates, and processed media record. These fields will be used later for NFO generation.

Cloud AI settings use the same flow as local providers: paste API key, fetch models from the provider, select a model from the dropdown, then test the selected model. Gemini model discovery calls the Gemini models API and filters models that support `generateContent`. OpenAI/ChatGPT-compatible discovery calls `/v1/models` on the configured provider endpoint. Empty key fields and placeholders such as `MediaOrganizer_API_Key`, `YOUR_API_KEY`, and `PASTE_API_KEY_HERE` are ignored and are never sent as real API keys.

Облачные провайдеры (Gemini, OpenAI-compatible) иногда возвращают временные ошибки `503` или `429`. MediaForge автоматически повторяет такие запросы (до 3 попыток с паузой 1 и 2 секунды). Если основная облачная модель недоступна, но запасная настроена и отвечает, анализ продолжается с запасной моделью. API-ключи сохраняются локально в SQLite и не возвращаются в `GET /settings`.

## Workflow через UI

1. Откройте `http://127.0.0.1:5173`
2. Пройдите мастер настройки
3. Создайте сессию сканирования (укажите папку с файлами и папку медиатеки через picker)
4. На странице сессии последовательно:
   - **Сканировать** → находит все медиафайлы
   - **Распознать** → парсит имена файлов
   - **Найти в TMDB** → сопоставляет с TMDB
   - **Построить план** → создаёт список будущих операций
5. Просмотрите **Операции** — файлы ещё не перемещены

**Планирование — только preview. Файлы не перемещаются.**

## TMDB ключ (env fallback)

Альтернативно ключ можно указать в `.env`:

```bash
TMDB_API_KEY=
```

Приоритет: настройки в БД → `.env`. Не коммитить `.env` с реальными ключами.

## Безопасность и поведение ключей

- **Ключи никогда не показываются в UI.** `GET /settings` возвращает только флаги `tmdb_configured` / `ai_configured`.
- **Пустое поле не удаляет сохранённый ключ.** Если вы открыли настройки и оставили поле ключа пустым — старый ключ сохранится.
- **Замена ключа:** введите новый ключ и сохраните. Только непустое значение перезапишет старое.
- **Проверка сохранённого ключа:** кнопка «Проверить сохранённый ключ» на шаге TMDB тестирует ключ из БД без его показа.

## Создание сессии сканирования

- **Исходная папка** (source) и **папка медиатеки** (target) должны быть разными.
  Одинаковые пути запрещены как на клиенте, так и на сервере.
- Обе папки должны существовать на момент создания сессии.
- Поддерживаются Windows-пути с обратными слэшами (`D:\Фильмы`) и кириллица.

## Troubleshooting

### Вижу просто «Ошибка»

Ранее frontend показывал generic «Ошибка» при любой проблеме сети или API.
Теперь показывается конкретное сообщение:
- **Backend недоступен** — сервер не запущен, проверьте `start-dev.ps1`
- **TMDB отклонил ключ** — неверный API key
- **TMDB не ответил вовремя** — проблемы с интернетом
- **TMDB-ключ не настроен** — нужно добавить ключ в настройках

### «Не удалось загрузить сессии»

Причины:
1. Backend не запущен — откройте терминал и запустите `.\scripts\start-backend.ps1`
2. Backend только запускается — подождите 2–3 секунды и обновите страницу
3. БД не инициализирована — запустите `python -m backend.scripts.init_db`
   (или просто перезапустите backend — с версии fix/settings он создаёт таблицы автоматически)

### Ошибка 500 при открытии сессии

**Симптом:** страница сессии показывает «Ошибка 500», хотя сессия появляется в списке.

**Причина:** локальная БД была создана со старой схемой — в таблице `media_items` отсутствуют столбцы
`tmdb_media_type`, `matched_title`, `matched_year`, `match_confidence`, которые были добавлены позднее.
FastAPI не может выполнить SELECT и возвращает 500.

**Решение:** backend автоматически применяет миграцию при запуске (добавляет столбцы через
`ALTER TABLE`). Перезапустите backend:

```powershell
.\scripts\start-backend.ps1
```

Или запустите миграцию вручную:

```powershell
python -m backend.scripts.init_db
```

После этого откройте страницу сессии — ошибка исчезнет.

### Папки source и target должны быть разными и не вложенными

MediaForge проверяет пути при создании сессии. Запрещены:

| Ситуация | Пример | Сообщение |
|----------|--------|-----------|
| source == target | `D:\Фильмы` → `D:\Фильмы` | «Папки не должны совпадать» |
| target внутри source | `D:\Фильмы` → `D:\Фильмы\Медиасервер` | «Папка медиатеки находится внутри папки с файлами» |
| source внутри target | `D:\Фильмы\Inbox` → `D:\Фильмы` | «Папка с файлами находится внутри папки медиатеки» |

Проверка работает для Windows-путей (backslash/forward slash, разный регистр, кириллица).

**Почему это важно:** если target находится внутри source, MediaForge при повторном сканировании
обнаружит уже организованные файлы и попытается обработать их снова.

### TMDB key не проверяется / «ключ не настроен»

1. Убедитесь, что ключ сохранён: перейдите в Настройки → шаг TMDB → должна быть зелёная плашка «TMDB-ключ сохранён»
2. Нажмите «Проверить сохранённый ключ» — бэкенд использует ключ из БД
3. Если плашки нет — вставьте ключ и сохраните настройки

## API endpoints

| Method | Path | Описание |
|--------|------|----------|
| GET | `/health` | Статус backend |
| GET | `/settings` | Настройки (без ключей) |
| PUT | `/settings` | Сохранить настройки |
| POST | `/settings/test-tmdb` | Проверить TMDB подключение |
| POST | `/settings/test-ai` | Проверить AI подключение |
| GET | `/settings/local-ai/ollama/models` | Модели Ollama |
| GET | `/settings/local-ai/lmstudio/models` | Модели LM Studio |
| GET | `/filesystem/roots` | Список дисков/корней |
| GET | `/filesystem/browse?path=...` | Просмотр папки |
| POST | `/scan-sessions` | Создать сессию |
| GET | `/scan-sessions` | Список сессий |
| POST | `/scan-sessions/{id}/discover` | Сканировать |
| POST | `/scan-sessions/{id}/parse` | Распознать |
| POST | `/scan-sessions/{id}/match-tmdb` | Найти в TMDB |
| POST | `/scan-sessions/{id}/plan` | Построить план |
| GET | `/scan-sessions/{id}/plans` | Планы сессии |
| GET | `/operation-plans/{id}/operations` | Операции плана |
| POST | `/scan-sessions/{id}/review/approve-all` | Массовое одобрение |
| POST | `/scan-sessions/{id}/review/bulk-decision` | Массовое решение по выбранным |
| POST | `/operation-plans/{id}/validate` | Проверить план перед apply |
| POST | `/operation-plans/{id}/apply` | Применить план (`confirm: true`) |
| GET | `/operation-plans/{id}/apply-runs` | Журнал применения |
| POST | `/items/{id}/tmdb-search` | Ручной поиск TMDB |
| POST | `/items/{id}/tmdb-lookup` | Lookup по TMDB/IMDb/TVDB ID |
| POST | `/items/{id}/review-decision` | Решение пользователя |
| POST | `/items/{id}/tmdb-candidates/{id}/select` | Выбор кандидата |

## Основной сценарий через UI

Откройте страницу сессии и нажмите **Начать анализ**. MediaForge последовательно выполнит discovery, parsing, TMDB matching и построит dry-run план. Каждый шаг показывает понятный статус: ожидает, выполняется, готово или ошибка.

## Начать анализ

Кнопка **Начать анализ** запускает полный безопасный pipeline. Если один из шагов завершится ошибкой, уже выполненные шаги останутся отмечены как готовые, а на экране появится понятное сообщение. Отдельные кнопки сканирования, распознавания, поиска TMDB и построения плана доступны в блоке **Ручной режим**.

## Использование локальных метаданных

MediaForge читает sidecar-файлы рядом с видео: `movie.nfo`, `{имя}.nfo`, `tvshow.nfo`, постеры (`poster.jpg`, `folder.jpg`, `fanart.jpg` и др.).

Приоритет распознавания:

```text
ID lookup (manual → sidecar → memory) → NFO title/year → filename/AI → TMDB search → manual review
```

Если в NFO есть TMDB/IMDb/TVDB ID, они используются раньше поиска по названию. Локальный постер не означает TMDB match — только визуальная подсказка.

Технические детали распознавания (parser, local/cloud AI, sidecar source) скрыты в collapsible блоке на карточке item.

## Ручная проверка и исправление

Если MediaForge распознал фильм неправильно, на карточке объекта доступен блок **Ручная проверка**:

- введите название, год, тип, TMDB / IMDb / TVDB ID;
- **Искать в TMDB** — ручной поиск с `ru-RU`, fallback на `en-US`;
- **Загрузить по ID** — прямой lookup по TMDB / IMDb / TVDB ID;
- **Подтвердить выбранный вариант** — `approved`;
- **Не добавлять** — `ignored`, объект исключается из плана;
- **Отложить** — `deferred`, объект исключается из плана;
- **Сохранить исправление** — `manual_override`, данные сохраняются в memory.

На странице сессии блок **Проверка найденных фильмов** объединяет карточки объектов, массовые действия и кнопки **Добавить / Не добавлять / Отложить** на каждой карточке.

## Поиск по TMDB ID / IMDb ID / TVDB ID

В панели **Кандидаты TMDB** сверху есть блок **Найти другой вариант** с полями названия, года, типа и внешних ID. Кнопки **Искать** и **Загрузить по ID** вызывают:

- `POST /items/{item_id}/tmdb-search`
- `POST /items/{item_id}/tmdb-lookup`

## Добавить / Не добавлять / Отложить

`POST /items/{item_id}/review-decision` сохраняет решение пользователя. Planning строит операции только для `MATCHED` объектов без `ignored` / `deferred`. Исключённые и отложенные объекты отображаются в предупреждении при просмотре плана.

## Основная и запасная облачная модель

В настройках доступны блоки **Cloud AI primary** и **Cloud AI fallback**. Если основная модель недоступна (timeout, invalid JSON, rate limit), pipeline пробует запасную. Preflight проверяет обе модели и показывает предупреждение, если работает только fallback.

`GET /settings` возвращает `cloud_primary_configured` / `cloud_fallback_configured`, но не raw API keys. Пустое поле ключа не затирает сохранённый ключ.

## Ручной выбор TMDB-кандидата

В блоках объектов нажмите **Кандидаты TMDB**, чтобы увидеть варианты, найденные для конкретного фильма или серии. Для каждого кандидата показаны название, оригинальное название, год, тип, score, рейтинг, популярность и описание. Нажмите **Выбрать этот вариант**, чтобы назначить кандидата вручную. После выбора объект становится `MATCHED`, а предыдущий выбранный кандидат сбрасывается.

Endpoint: `POST /items/{item_id}/tmdb-candidates/{candidate_id}/select`

## Пересобрать план

После ручного выбора TMDB-кандидата нажмите **Пересобрать план**. UI вызовет `POST /scan-sessions/{id}/plan?force=true`, обновит список планов и операций и покажет сообщение **План пересобран**.

## Массовое подтверждение

В блоке **Проверка найденных фильмов** доступны массовые действия:

- **Одобрить всё найденное** — `POST /scan-sessions/{id}/review/approve-all` с `scope: matched`. Одобряются только `MATCHED` объекты с `tmdb_id`, не требующие ручной проверки. `ignored` / `deferred` не меняются.
- **Одобрить выбранные** — тот же endpoint с `scope: selected` и `item_ids`.
- **Не добавлять / Отложить выбранные** — `POST /scan-sessions/{id}/review/bulk-decision`.

После массового действия UI показывает счётчики: одобрено, пропущено, исключено, отложено.

## Применение плана

Workflow разделён на этапы:

1. **Preview** — `POST /scan-sessions/{id}/plan` строит план без изменений на диске.
2. **Validate** — `POST /operation-plans/{id}/validate` проверяет конфликты (существующие файлы, изменённые источники, небезопасные пути, недоверенные URL).
3. **Confirm** — в UI нужен checkbox «Я понимаю, что файлы будут изменены».
4. **Apply** — `POST /operation-plans/{id}/apply` с `{ "confirm": true }` выполняет операции последовательно.

По умолчанию **существующие файлы не перезаписываются**. При конфликтах apply блокируется. Журнал сохраняется в `apply_runs` и `apply_operation_logs` (основа для будущего rollback).

Поддерживаемые операции apply: `CREATE_DIR`, `MOVE_FILE`, `WRITE_TEXT_FILE` (movie.nfo), `DOWNLOAD_FILE` (только `https://image.tmdb.org/`).

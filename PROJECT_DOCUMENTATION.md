# Полная техническая документация: Freelance Leads Monitor

> **Автор:** Андрей Пименов ([`@horizontal42`](https://github.com/Horizontal42))  
> **Стек:** Python 3.12, asyncio, aiogram 3, aiosqlite (WAL), httpx, feedparser, pydantic v2, pydantic-settings, Antigravity CLI (`gemini-3.8-flash-medium` / `claude-sonnet-4-6`) / Mistral API.  
> **Версия:** 0.1.0 (MVP)  
> **Дата актуализации:** Октябрь 2026  

---

## 1. Назначение системы и бизнес-контекст

Система решает задачу автоматического мониторинга русскоязычных бирж фриланса, первичного эвристического отсева нерелевантного трафика (без затрат на LLM), глубокого анализа прошедших заказов нейросетью по авторским регламентам и оперативной доставки готовых откликов в личный Telegram-бот.

### Бизнес-правила и регламенты (на базе `FREELANCE_PROFILE.md`):
1. **Скорость первого контакта:** На фрилансе первые 3-5 откликов забирают 80% внимания клиента. Задача системы - доставить готовый отклик на смартфон в течение 1-2 минут после публикации заказа.
2. **Запрет маркеров ИИ в откликах:**
   - **Строжайший запрет длинных тире `—`:** живые люди в чатах нажимают только обычный дефис `-`. Длинное тире моментально палит генерацию. В системе реализован принудительный санитизатор `replace("—", "-")`.
   - **Запрет шаблонных списков со звездочками:** никаких `**Стек:**`, `**Преимущества:**`, `**Сроки:**`. Текст отклика строится естественными связными абзацами с живым ритмом.
   - **Правило первых 140 символов:** первые 2 предложения видны в превью ленты биржи. Они сразу бьют в боль клиента и подтверждают опыт без приветственных штампов ("Здравствуйте, меня зовут Андрей...").
   - **Опора на реальные проекты из `PROJECTS_DOSSIER.md`:** отклик обязан ссылаться на настоящие кейсы:
     * `Speech Analytics (Intervesp)` (FastAPI, Celery, WhisperX, Bitrix24 REST API, difflib fuzzy, malloc_trim);
     * `Avia_Pars` (aiogram 3, curl_cffi обход TLS, patchright Chromium в изолированном subprocess, residential socks5 relay, Circuit Breaker);
     * `leads-monitor` (hh.ru, DaData, Google Sheets API, SQLite);
     * `netsleuth` (сетевой CLI, Win32 Iphlpapi через ctypes без админки);
     * `AgroTech CV` (компьютерное зрение, YOLOv8, OpenCV, ByteTrack).
3. **Ценовая политика:**
   - Минимальный бюджет заказа: **от 10 000 руб.** (или "по договоренности").
   - Стратегия холодного старта: привлекательная цена по нижней границе вилки с обоснованием готовой базой кода, без демпинга в убыток.
   - Расчет сроков по формуле PERT: $E = \frac{O + 4M + P}{6}$, $\sigma = \frac{P - O}{6}$.

---

## 2. Реалии рынка бирж (Результаты разведки 2026 года)

Перед реализацией была проведена прямая сетевая разведка площадок:
1. **Хабр Фриланс (`freelance.habr.com`):**
   - **ЗАКРЫТ НАВСЕГДА.** Сервер отдает `HTTP 410 Gone` с официальным сообщением о ликвидации сервиса. Парсинг невозможен.
2. **Kwork (`kwork.ru`):**
   - **Идеальный источник.** В HTML-странице категорий `c=11` (Разработка и IT) и `c=41` (Скрипты, боты и mini apps) содержится нативный JSON `window.stateData` со всеми проектами (`wants`), точными бюджетами, описаниями и счетчиком уже поданных заявок (`kwork_count`).
   - Парсится GET-запросом через `httpx` с браузерными заголовками раз в 2-3 минуты. Блокировок и Cloudflare нет.
3. **FL.ru (`fl.ru`):**
   - **Стабильный источник.** Имеет открытый публичный RSS-фид `https://www.fl.ru/rss/all.xml`.
   - Не блокирует запросы с браузерным User-Agent. Бюджеты извлекаются регулярными выражениями с декодированием HTML-сущностей (`&#8381;` $\to$ `₽`).
4. **Freelance.ru (`freelance.ru`):**
   - Рабочий каталог заказов на `https://freelance.ru/task`. Доступен для расширения вторым этапом.
5. **Агрегаторы (например, `alot.pro`):**
   - Закрыты авторизацией (платная подписка), куки-сессиями и Firebase. Главный минус - лаг в 15-30 минут, убивающий преимущество быстрого отклика. Прямой сбор первоисточников в разы эффективнее.

---

## 3. Архитектура и трехуровневая воронка (Tiering)

```text
               [ Биржи: Kwork (c=11, c=41) ]      [ FL.ru (RSS) ]
                               \                      /
                                v                    v
                        [ Ingestion: BaseCollector ]
                                     │ RawOrder
                                     ▼
                        [ SQLite: Дедупликация ]
                        (source, external_id UNIQUE)
                                     │
                                     ▼
                        [ 1. Hard-Filter (Эвристика) ]
                        - Бюджет >= 10 000 ₽ или договоренность
                        - Черный список стоп-слов
                        - Белый список ключевых слов
                                     │
                    ┌────────────────┴────────────────┐
                    │ Не прошел                       │ Прошел (4-8 заказов в день)
                    ▼                                 ▼
            [ Tier 3: Мусор ]                 [ 2. LLM-Анализ ]
         (Статус: REJECTED,               (Antigravity CLI / Mistral API)
          без вызова нейросети)           - Оценка рисков и сложности (1-10)
                                          - Скор привлекательности (1-10)
                                          - PERT расчет сроков и цены
                                          - Отклик без ИИ-маркеров (дефисы "-")
                                                      │
                                     ┌────────────────┴────────────────┐
                                     │ Скор < 7                        │ Скор >= 7
                                     ▼                                 ▼
                            [ Tier 2: Обычные ]               [ Tier 1: Горячие лиды ]
                            - База данных SQLite              - 🚀 Мгновенный пуш в Telegram
                            - Доступны на сайте / дашборде    - Интерактивные кнопки (1 клик)
                            - Google Таблицы (без спама)      - Запись в базу SQLite и на сайт
```

---

## 4. Структура каталогов и назначение файлов

```text
jobs/
├── data/
│   └── jobs.db                  # Локальная база данных SQLite (WAL-режим)
├── src/
│   ├── __init__.py
│   ├── config.py                # Pydantic Settings (.env, дефолтные стоп-слова, ключевики)
│   ├── main.py                  # Точка входа: CLI (--once) и фоновый демон с Telegram-ботом
│   ├── models/                  # Доменные Pydantic-модели (DTO)
│   │   ├── __init__.py
│   │   ├── order.py             # RawOrder, SourcePlatform, OrderPriority, OrderStatus, FilterResult
│   │   └── analysis.py          # AnalysisResult, PertEstimate
│   ├── collectors/              # Модули сбора (Ingestion)
│   │   ├── __init__.py
│   │   ├── base.py              # Абстрактный класс BaseCollector
│   │   ├── kwork.py             # KworkCollector (парсинг window.stateData)
│   │   └── fl_ru.py             # FlRuCollector (парсинг RSS FL.ru)
│   ├── filters/                 # Эвристический Hard-Filter
│   │   ├── __init__.py
│   │   └── pre_filter.py        # HardFilter (проверка бюджета, стоп-слов, ключевиков)
│   ├── analyzer/                # LLM-анализ и генерация откликов
│   │   ├── __init__.py
│   │   ├── base.py              # Абстрактный BaseLLMClient
│   │   ├── prompts.py           # Промпты с инъекцией регламента и досье проектов
│   │   ├── antigravity_client.py# Runner через локальный CLI agy (gemini-3.8-flash-medium)
│   │   ├── mistral_client.py    # Резервный клиент Mistral API (ministral-8b/codestral)
│   │   └── factory.py           # Фабрика get_llm_client() по переменной LLM_PROVIDER
│   ├── storage/                 # Слой персистентности (SQLite WAL)
│   │   ├── __init__.py
│   │   ├── db.py                # Инициализация схемы и индексов через aiosqlite
│   │   └── repository.py        # OrderRepository (CRUD, дедупликация, статистика)
│   ├── notifiers/               # Пайплайн и доставка уведомлений
│   │   ├── __init__.py
│   │   ├── pipeline.py          # LeadsPipeline (оркестрация и роутинг по уровням)
│   │   └── telegram_notifier.py # Форматирование карточки и отправка в Telegram
│   └── bot/                     # Telegram-бот (aiogram 3)
│       ├── __init__.py
│       ├── bot.py               # Фабрика Bot и Dispatcher с DI репозитория
│       ├── handlers.py          # Обработчики команд (/start, /scan, /stats, /recent) и кнопок
│       └── keyboards.py         # Inline-клавиатура (Скопировать отклик, Открыть заказ, В архив)
├── tests/                       # Автотесты (pytest, 100% pass)
│   ├── __init__.py
│   ├── test_collectors.py       # Тесты парсинга Kwork и живого RSS FL.ru
│   ├── test_storage_and_filter.py# Тесты SQLite WAL и HardFilter
│   ├── test_analyzer.py         # Тесты промптов, парсинга JSON и санитизации дефисов
│   └── test_pipeline_e2e.py     # End-to-end тест роутинга заказов (Tier 1/2/3)
├── .env.example                 # Шаблон переменных окружения
├── .gitignore                   # Исключения Git (.venv, data/*.db, .env)
├── pyproject.toml               # Конфигурация сборки и зависимости проекта
└── README.md                    # Краткое руководство пользователя
```

---

## 5. Подробный разбор каждого модуля

### 5.1. Конфигурация ([`src/config.py`](file:///home/horizontal42/jobs/src/config.py))
Использует `pydantic-settings`. Загружает параметры из `.env` с типизацией:
- `DEFAULT_STOP_WORDS`: диплом, курсовая, реферат, 1С, верстка, Tilda, WordPress, SEO, копирайтинг, накрутка, отзывы.
- `DEFAULT_KEYWORDS`: python, парсер, бот, telegram, aiogram, fastapi, django, CRM, битрикс24, api, интеграция, LLM, ИИ, нейросеть, whisper, автоматизация, scraping, selenium, playwright, opencv, yolo, RAG, qdrant, tauri.
- `MIN_BUDGET`: 10 000 руб.
- `HOT_SCORE_THRESHOLD`: 7 (порог для отправки в Telegram).
- `ANTIGRAVITY_MODEL`: `gemini-3.8-flash-medium` (оптимальный баланс глубины мышления и скорости генерации в 5-10 сек).

### 5.2. Модели данных ([`src/models/`](file:///home/horizontal42/jobs/src/models))
- **`RawOrder`**: входная модель сборщика (`source`, `external_id`, `title`, `description`, `url`, `price`, `is_negotiable`, `tags`, `created_at`, `raw_payload`). Имеет свойство `full_text` для фильтрации.
- **`FilterResult`**: результат пре-фильтра (`passed: bool`, `reason: str`, `matched_keywords`, `matched_stopwords`).
- **`AnalysisResult`**: строгий структурированный контракт ответа LLM:
  * `take_order: bool`
  * `score: int` (1-10)
  * `priority: OrderPriority` (`hot` | `normal`)
  * `executive_summary: str`
  * `recommended_price: float`
  * `price_justification: str`
  * `realistic_days: float`
  * `matched_project: str` (зацепка за досье)
  * `complexity: int` (1-10)
  * `pure_dev_hours: float`
  * `risks_and_pitfalls: List[str]`
  * `proposal_text: str` (готовый живой текст отклика)
  * `pert: PertEstimate` (`optimistic_days`, `most_likely_days`, `pessimistic_days`, `expected_days`, `sigma`)

### 5.3. Сборщики заказов ([`src/collectors/`](file:///home/horizontal42/jobs/src/collectors))
- **`KworkCollector`**:
  * Делает GET-запрос к `https://kwork.ru/projects?c={cat_id}` (`c=11` - IT, `c=41` - боты).
  * Находит `window.stateData` и декодирует его через `json.JSONDecoder().raw_decode()`.
  * Извлекает `possiblePriceLimit` (или `priceLimit`). Если цена 0 или не указана, выставляет `is_negotiable = True`.
- **`FlRuCollector`**:
  * Делает GET-запрос к `https://www.fl.ru/rss/all.xml`.
  * Парсит XML через `feedparser`.
  * Регулярным выражением вытаскивает бюджет (например, `Бюджет: 150 000 ₽` или `35 000 руб.`), корректно обрабатывая HTML-сущности. Извлекает ID проекта из ссылки вида `/projects/5526844/...`.

### 5.4. Эвристический Hard-Filter ([`src/filters/pre_filter.py`](file:///home/horizontal42/jobs/src/filters/pre_filter.py))
Отрабатывает за доли миллисекунды:
1. Ищет стоп-слова в тексте. Для коротких терминов (до 3 символов, таких как `1с`, `smm`, `seo`) использует строгие границы слов (`\b`), предотвращая ложные срабатывания. Если найдено хотя бы одно стоп-слово - отказ.
2. Проверяет бюджет: если указан точный бюджет `< 10 000 ₽` и нет флага договоренности - отказ.
3. Ищет ключевые слова из белого списка. Если нет ни одного совпадения - отказ.

### 5.5. LLM-движок и промптинг ([`src/analyzer/`](file:///home/horizontal42/jobs/src/analyzer))
- **`prompts.py`**:
  * Содержит полный системный промпт с инъекцией всех 7 проектов из досье разработчика и правил из регламента откликов.
  * Требует строгий JSON-формат.
- **`antigravity_client.py`**:
  * Асинхронно вызывает команду:
    ```bash
    agy -p "<prompt>" --model gemini-3.8-flash-medium --output-format text
    ```
  * Очищает вывод от markdown-оберток (```json).
  * Выполняет принудительную санитизацию: `text.replace("—", "-").replace("–", "-")`.
  * Валидирует результат в модель `AnalysisResult`.
- **`mistral_client.py`**:
  * Реализует запасной путь через официальный Mistral API (`https://api.mistral.ai/v1/chat/completions`) с параметром `response_format={"type": "json_object"}`.

### 5.6. Хранилище SQLite WAL ([`src/storage/`](file:///home/horizontal42/jobs/src/storage))
- Схема базы данных `orders`:
  * `id` INTEGER PRIMARY KEY
  * `source` TEXT (kwork / fl_ru)
  * `external_id` TEXT
  * `title`, `description`, `url`
  * `price`, `is_negotiable`
  * `status` (new / rejected / analyzed / sent_to_tg / archived)
  * `priority` (trash / normal / hot)
  * `score`, `recommended_price`, `realistic_days`, `matched_project`
  * `proposal_text`, `analysis_json`
  * `created_at`, `updated_at`
  * Индексы на `(source, external_id)`, `priority`, `status`, `created_at`.
- Подключение оборачивается асинхронным контекстным менеджером с прагмами:
  ```sql
  PRAGMA journal_mode = WAL;
  PRAGMA synchronous = NORMAL;
  ```

### 5.7. Пайплайн обработки ([`src/notifiers/pipeline.py`](file:///home/horizontal42/jobs/src/notifiers/pipeline.py))
Оркестрирует жизненный цикл каждого заказа:
1. `is_duplicate()` $\to$ пропуск, если заказ уже есть в базе.
2. `hard_filter.evaluate()` $\to$ если не прошел, сохраняется в базу со статусом `REJECTED` и приоритетом `TRASH` с указанием причины (повторно не анализируется).
3. `llm_client.analyze_order()` $\to$ получение структурированного ответа.
4. Запись в SQLite.
5. Если `score >= 7` $\to$ отправка в Telegram через `TelegramNotifier`, выставление статуса `SENT_TO_TG`.
6. Если `score < 7` $\to$ статус `ANALYZED`, приоритет `NORMAL`. Заказ тихо ждет на сервере/сайте без спама в телефон.

### 5.8. Telegram-бот на aiogram 3 ([`src/bot/`](file:///home/horizontal42/jobs/src/bot))
- **Карточка заказа:** формируется в безопасном HTML-формате (`html.escape`):
  * Бейдж: `🔥 [ГОРЯЧИЙ ЛИД | СКОР 8/10]`
  * Биржа и кликабельная ссылка на заказ
  * Бюджет клиента vs Рекомендуемая цена
  * Срок по PERT ($E$ и $\sigma$)
  * Проект из досье и сложность
  * Подводные камни и резюме
- **Интерактивные кнопки под карточкой:**
  * **`📋 Скопировать отклик`** (`copy:{order_id}`): бот находит в базе сгенерированный отклик и присылает его отдельным сообщением внутри тега `<blockquote>` (в Telegram на смартфоне текст копируется в буфер обмена в один тап!).
  * **`🔗 Открыть заказ`**: прямая URL-кнопка для перехода на биржу.
  * **`📦 В архив`** (`archive:{order_id}`): помечает заказ как `ARCHIVED` в базе данных, редактирует карточку, добавляя плашку `[В АРХИВЕ]`, и убирает кнопки.
- **Команды бота:**
  * `/start`: статус системы, проверка ID администратора, список команд.
  * `/scan`: запуск внеочередного сбора прямо сейчас с выводом отчета по найденным заказам.
  * `/stats`: статистика базы (всего, горячие, обычные, отсеянные, отправленные).
  * `/recent`: список последних 5 заказов со статусами и ссылками.

---

## 6. Конфигурация окружения (`.env`)

Создайте файл `.env` в корне каталога `~/jobs` (на базе `.env.example`):

```env
# Telegram Bot Configuration
# Токен бота от @BotFather
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
# Твой личный Telegram ID (узнать у @userinfobot)
ADMIN_CHAT_ID=123456789

# LLM Provider Configuration
# "antigravity" (бесплатно через локальный CLI agy) или "mistral"
LLM_PROVIDER=antigravity
# Модели: gemini-3.8-flash-medium (рекомендуется), gemini-3.8-flash-low, claude-sonnet-4-6
ANTIGRAVITY_MODEL=gemini-3.8-flash-medium

# Опционально: если LLM_PROVIDER=mistral
MISTRAL_API_KEY=
MISTRAL_MODEL=ministral-8b-latest

# Storage Configuration
DB_PATH=data/jobs.db

# Polling Intervals (в секундах)
KWORK_POLL_INTERVAL=180
FL_POLL_INTERVAL=180

# Hard Filter Settings
MIN_BUDGET=10000
HOT_SCORE_THRESHOLD=7
```

---

## 7. Развертывание, запуск и обслуживание

### 7.1. Первичная настройка виртуального окружения
```bash
cd ~/jobs
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 7.2. Запуск тестов
Все модули покрыты тестами (`tests/`):
```bash
.venv/bin/pytest -v
# Ожидаемый результат: 11 passed
```

### 7.3. Разовый запуск сканирования (--once)
Идеально для проверки работы без запуска бота или для работы по системному cron:
```bash
.venv/bin/python -m src.main --once
```

### 7.4. Запуск демона с фоновым воркером и Telegram-ботом
```bash
.venv/bin/python -m src.main
```

### 7.5. Автозапуск через Systemd (для VDS-сервера)
Создайте файл `/etc/systemd/system/freelance-monitor.service`:
```ini
[Unit]
Description=Freelance Leads Monitor Daemon
After=network.target

[Service]
Type=simple
User=horizontal42
WorkingDirectory=/home/horizontal42/jobs
ExecStart=/home/horizontal42/jobs/.venv/bin/python -m src.main
Restart=always
RestartSec=10
EnvironmentFile=/home/horizontal42/jobs/.env

[Install]
WantedBy=multi-user.target
```

Управление сервисом:
```bash
sudo systemctl daemon-reload
sudo systemctl enable freelance-monitor
sudo systemctl start freelance-monitor
sudo journalctl -u freelance-monitor -f
```

---

## 8. Перспективы развития и точки расширения (Roadmap)

Архитектура изначально спроектирована модульной:
1. **Объединение с `leads-monitor`:**
   Чтобы собирать B2B-вакансии с hh.ru, достаточно создать класс `HhCollector(BaseCollector)` в каталоге `src/collectors/` и добавить его в список сборщиков в `src/main.py`.
2. **Веб-дашборд на личном домене:**
   База SQLite лежит в `data/jobs.db`. Достаточно написать простой бэкенд на FastAPI (1 файл `src/web/app.py`), который читает заказы через `OrderRepository.get_recent_orders()` и рендерит веб-страницу с архивом и фильтрами.
3. **Google Таблицы:**
   Создать `GoogleSheetsNotifier` в `src/notifiers/`, который параллельно записывает Tier 2 и Tier 1 заказы в онлайн-таблицу (код работы с `gspread` можно скопировать из твоего `leads-monitor`).
4. **Подключение Freelance.ru:**
   Создать `FreelanceRuCollector` для парсинга `https://freelance.ru/task`.

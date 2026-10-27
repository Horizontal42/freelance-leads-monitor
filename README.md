# Freelance Leads Monitor

[English](README.md) · [Русский](README.ru.md)

Cross-exchange freelance lead monitoring and evaluation daemon for Russian-speaking platforms (Kwork, FL.ru, Freelance.ru, Pchel.net, Remote-job). Features heuristic hard-filtering, two-stage cascaded LLM analysis (Mistral for ingestion scoring, Antigravity `agy` for on-demand proposals), real-time Telegram delivery via aiogram 3, and an interactive FastAPI dashboard for `jobs.3dvex.ru`.

```bash
$ python -m src.main --once
2026-10-26 23:59:00 [INFO] Ingestion started across 5 platforms...
2026-10-26 23:59:02 [INFO] Collected: Kwork (14), FL.ru (22), Freelance.ru (18), Pchel.net (12), Remote-job (8)
2026-10-26 23:59:03 [INFO] HardFilter: 71 rejected (diplomas, 1C, low budget), 3 passed to LLM
2026-10-26 23:59:05 [INFO] Mistral: Evaluated 3 leads (1 Hot, 2 Normal). PERT & market price calculated.
2026-10-26 23:59:06 [INFO] Telegram: Delivered 1 Hot lead to @horizontal42 with action keyboard.
2026-10-26 23:59:06 [INFO] Pipeline complete. New leads persisted in SQLite WAL.
```

Built specifically for Andrey Pimenov ([`@horizontal42`](https://github.com/Horizontal42)) following [`docs/FREELANCE_PROFILE.md`](docs/FREELANCE_PROFILE.md), [`docs/PROJECTS_DOSSIER.md`](docs/PROJECTS_DOSSIER.md), and [`docs/RESUME_HH.md`](docs/RESUME_HH.md).

---

## Supported Exchanges

| Exchange | Method | Rate Limits & Protection | PRO / Free Filter |
|---|---|---|---|
| **Kwork** | Server-side `window.stateData` JSON (IT & Bots categories) | 180s poll, browser headers | Free responses |
| **FL.ru** | Official RSS feed (`/rss/all.xml`) | Standard XML polling | Gated by `(для всех)` in title |
| **Freelance.ru** | HTML card scraping (`/task` & `?q=python`) | 180s poll, desktop User-Agent | Gated by `task-card__pro` badge |
| **Pchel.net** | HTML parsing (`/jobs/programming/`) | Auto USD-to-RUB conversion (rate 95.0) | Open IT tasks |
| **Remote-job** | HTML project feed (`/search?searchType=project`) | Clean title & budget normalization | Open remote projects |

---

## Architecture & Data Flow

```text
[ Kwork ]  [ FL.ru ]  [ Freelance.ru ]  [ Pchel.net ]  [ Remote-job ]
    │          │             │               │              │
    └──────────┴──────┬──────┴───────────────┴──────────────┘
                      │ Periodic HTTP polling (180s)
                      ▼
              [ BaseCollector ]
                      │ List[RawOrder]
                      ▼
            [ SQLite Deduplication ]
             (is_duplicate check)
                      │ Fresh RawOrder
                      ▼
            [ 1. HardFilter ]
             - Min budget: 10,000 ₽ or negotiable
             - Stop words rejection (diplomas, 1C, layout, Tilda, SEO)
             - Keyword matching (Python, bots, parsers, CRM, FastAPI, LLM)
             - PRO-only filter check
                      │
       ┌──────────────┴──────────────┐
       │ Rejected                    │ Passed (Target Leads)
       ▼                             ▼
  [ Tier 3: Trash ]           [ OrderEnricher ]
  - Status: REJECTED          - Full task description pre-fetch
  - No LLM calls              - Attachment reader (.txt, .json, .py)
                                     │ Full text & files (No URLs passed)
                                     ▼
                              [ 2. LLM Analysis (Ministral 14B) ]
                              - Prompt without URLs (saves tokens & time)
                              - 3-4 sentence concise executive summary
                              - Preliminary PERT estimate: E = (O + 4M + P)/6, σ
                              - Market price evaluation & justification
                              - Complexity, hours, risks, dossier matching
                              - proposal_text remains ""
                                     │
                      ┌──────────────┴──────────────┐
                      │ Score < 7                   │ Score >= 7
                      ▼                             ▼
             [ Tier 2: Normal ]            [ Tier 1: Hot Leads ]
             - Saved in SQLite             - Saved in SQLite
             - Visible in Web UI           - Visible in Web UI (Hot tab)
                                           - 🚀 Instant Telegram alert
                                                  │
                                                  ▼
                                    [ On-Demand Proposal Generation ]
                                     User clicks "Сгенерировать отклик"
                                     (Telegram inline button or Web button)
                                                  │
                                                  ▼
                                    [ 3. Antigravity CLI (agy -p) ]
                                    - Bespoke human response from dossier
                                    - Strict ban on em-dashes "-"
                                    - First 140 chars preview rule
                                    - Persisted in SQLite & copied in 1-click
```

Full details on module boundaries, resilience guarantees, and data flows are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Web Dashboard & Telegram Bot

### Web Dashboard (`jobs.3dvex.ru:8086`)
- **Tab Navigation:** `Горячие лиды (Tier 1)`, `Все прошедшие`, `Потенциальные (Tier 2)`, `Отсеянные (Tier 3)`, `Аналитика бирж`, `Правила и фильтры`.
- **Live Search:** instant client-side search across titles, descriptions, and technology tags.
- **PRO / Free Toggle:** switch between free applications only and all projects with one click.
- **Publication Timestamp:** clear display of publication date and time (`🕒 Опубликован: ...`) on every card.
- **One-Click Proposal Generation & Copy:** interactive button triggering Antigravity proposal generation and copying to clipboard.

### Telegram Bot (`aiogram 3`)
- **Instant Hot Alerts:** push notifications for leads scoring $\ge 7/10$.
- **Card Format:** source exchange, publication time, PRO access badge, budget, PERT timeline ($E$, $\sigma$), matched portfolio case, and risks.
- **Interactive Buttons:**
  - `⚡ Сгенерировать отклик`: triggers Antigravity CLI on-demand.
  - `📋 Скопировать`: sends proposal text formatted for 1-tap mobile copying.
  - `🔗 Открыть заказ`: direct link to exchange listing.
  - `📦 В архив`: marks order as archived and dismisses buttons.
- **Commands:** `/start`, `/scan` (run manual scraping cycle), `/stats`, `/recent`.

---

## Configuration

All configuration is strictly separated: secrets live in `.env` and application parameters live in [`config.yml`](config.yml).

### Credentials (`.env`)
```bash
cp .env.example .env
```

```env
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_CHAT_ID=123456789
MISTRAL_API_KEY=your_mistral_api_key
```

### Application Settings (`config.yml`)
- `storage.db_path`: path to SQLite database (`data/jobs.db`).
- `web.host` & `web.port`: web dashboard binding (`0.0.0.0:8086`).
- `polling`: intervals per exchange.
- `filter`: `min_budget` (10,000 ₽), `hot_score_threshold` (7), `stop_words`, `keywords`.
- `llm`: provider selection (`hybrid`, `antigravity`, `mistral`), binary path, models, and timeouts.
- `prompts`: developer profile, complete project dossier (Speech Analytics, Avia_Pars, netsleuth, summarum, leads-monitor, Sort_YM, AgroTech CV, RAG), rules, and system prompt templates.

---

## Install & Quickstart

### Requirements
- Python 3.12 or newer
- Linux, macOS, or Windows
- SQLite 3.35+ (with WAL mode support)
- Antigravity CLI (`agy`) installed and authenticated for Stage 2 on-demand proposals

### Setup
```bash
git clone https://github.com/Horizontal42/freelance-leads-monitor.git
cd freelance-leads-monitor

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Edit .env with your BOT_TOKEN, ADMIN_CHAT_ID, and MISTRAL_API_KEY
```

### Run Tests
```bash
.venv/bin/pytest -v
```

### Run Single Scan
```bash
.venv/bin/python -m src.main --once
```

### Run Full Daemon (Web + Telegram Bot + Background Polling)
```bash
.venv/bin/python -m src.main
```

---

## For Developers

```bash
.venv/bin/pytest -v            # Run test suite (21 unit and integration tests)
.venv/bin/ruff check .         # Code style & linting
.venv/bin/mypy src             # Type checking
```

Architecture, data structures, and reasoning behind design choices: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## License

PolyForm Noncommercial 1.0.0
https://github.com/Horizontal42/freelance-leads-monitor/blob/master/LICENSE - free for personal, educational, and other non-commercial use.

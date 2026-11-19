# Architecture

Freelance Leads Monitor is an automated multi-exchange lead generation and evaluation daemon. It ingests freelance project postings from five Russian-speaking platforms, deduplicates them in SQLite, filters noise with a deterministic heuristic hard-filter, evaluates relevant projects via a two-stage cascaded LLM pipeline, and presents leads via a Telegram bot and an interactive FastAPI web dashboard.

## Directory layout

```
jobs/
  config.yml                  Unified declarative configuration (storage, web, polling, collectors, filter, prompts, dossier).
  .env.example                Environment variable credentials template (BOT_TOKEN, ADMIN_CHAT_ID, MISTRAL_API_KEY).
  pyproject.toml              Poetry/PEP 621 dependencies, scripts and pytest configuration.
  docs/
    FREELANCE_PROFILE.md      Freelance Playbook: rules of proposal writing, anti-AI markers, 140-char preview rule.
    PROJECTS_DOSSIER.md       Detailed project dossier & technical proof points (Speech Analytics, Avia_Pars, etc.).
    RESUME_HH.md              HeadHunter profile and positioning details.
  src/
    main.py                   Application entrypoint: orchestrates asyncio tasks (collector polling, web dashboard, bot).
    config.py                 Unified settings facade: loads secrets from .env and application parameters from config.yml.
    models/
      order.py                Domain models: SourcePlatform, RawOrder, FilterResult, OrderPriority, OrderStatus.
      analysis.py             Domain models: AnalysisResult, PERTEstimate.
    storage/
      db.py                   SQLite connection manager with WAL mode, busy_timeout=5000ms, and automatic schema migrations.
      repository.py           OrderRepository: deduplication, insertion, state transitions, retrieval, and metrics aggregation.
    filters/
      pre_filter.py           HardFilter: stop words, keyword matching, min budget (10k RUB), and PRO-only gating.
    collectors/
      base.py                 BaseCollector: abstract interface for platform scraping modules.
      kwork.py                KworkCollector: server-rendered window.stateData JSON parser for categories 11 and 41.
      fl_ru.py                FlRuCollector: RSS feed parser (/rss/all.xml) with budget regex extraction and PRO detection.
      freelance_ru.py         FreelanceRuCollector: HTML card scraper with cost-not-set detection and PRO badge parsing.
      pchel_net.py            PchelNetCollector: IT jobs parser with automatic USD-to-RUB currency conversion.
      remote_job.py           RemoteJobCollector: remote IT project scraper with clean description and budget normalization.
    analyzer/
      base.py                 BaseLLMClient: abstract interface for analyze_order() and generate_proposal().
      prompts.py              Prompt templates populated from config.yml rules, developer profile, and project dossier.
      mistral_client.py       MistralClient: fast official Mistral API client for primary analysis and preliminary PERT/pricing.
      antigravity_client.py   AntigravityClient: CLI subprocess wrapper (agy -p) for bespoke proposal generation.
      hybrid_client.py        HybridLLMClient: orchestrates Mistral primary analysis and Antigravity on-demand proposals with fallbacks.
      factory.py              get_llm_client(): factory function instantiating the configured client.
    notifiers/
      telegram_notifier.py    TelegramNotifier: sends formatted lead cards to Telegram with inline action buttons.
      pipeline.py             LeadsPipeline: end-to-end processing pipeline with semaphore-bounded concurrency.
    bot/
      bot.py                  Aiogram 3 bot setup and lifecycle management.
      handlers.py             Command and callback query handlers (/start, /scan, /stats, copy, archive, gen_prop).
      keyboards.py            Inline keyboard builders with dynamic proposal state buttons.
    web/
      app.py                  FastAPI web application for localhost:8086: tab navigation, live search, PRO toggle, copy-to-clipboard.
  tests/
    test_collectors.py        Unit tests for HTML/JSON/RSS parsing across all 5 collectors.
    test_storage_and_filter.py Unit tests for SQLite WAL migrations, deduplication, and HardFilter rules.
    test_analyzer.py          Unit tests for prompt formatting, JSON extraction, and HybridLLMClient flow.
    test_pipeline_e2e.py      End-to-end pipeline execution tests with mock LLM and concurrency semaphore validation.
    test_web.py               FastAPI dashboard endpoint tests (HTML responses, filter parameters, proposal generation API).
    test_config.py            Configuration loading and settings facade unit tests.
```

## Data pipeline & lifecycle

```
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
               - Min budget (10,000 ₽ or negotiable)
               - Stop words rejection (diplomas, 1C, layout, Tilda, SEO)
               - Keyword matching (Python, bots, parsers, CRM, FastAPI, LLM)
               - PRO-only filter check
                        │
         ┌──────────────┴──────────────┐
         │ Rejected                    │ Passed (Target Leads)
         ▼                             ▼
    [ Tier 3: Trash ]           [ 2. LLM Analysis (Mistral) ]
    - Status: REJECTED          - 3-4 sentence concise executive summary
    - No LLM calls              - Preliminary PERT estimate: E = (O + 4M + P)/6, σ
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

## Key design decisions

1. **Deterministic Hard-Filter Before LLM:**
   Over 80% of exchange postings are low-budget tasks, homework assignments, or irrelevant stacks (1C, WordPress, Tilda). Filtering them with pure regex before touching any LLM API keeps API latency low and saves token quotas.

2. **Cascaded Two-Stage LLM Evaluation:**
   - **Stage 1 (Mistral):** Fast (1-2s) cloud API call evaluates every passing lead. Produces a 3-4 sentence dense executive summary, preliminary PERT durations, and market price estimates.
   - **Stage 2 (Antigravity):** Deep reasoning via local `agy` CLI is executed **strictly on-demand** when the user decides to apply to an order. This eliminates unnecessary compute while ensuring the highest-quality tailored proposal.

3. **Strict Compliance with Freelance Playbook:**
   All prompts and templates are derived from `docs/FREELANCE_PROFILE.md`, `docs/PROJECTS_DOSSIER.md`, and `docs/RESUME_HH.md`. Any generated proposal strictly forbids em-dashes `—`, robot boilerplate (`**Стек:**`), and over-explaining, while referencing real case studies (`Speech Analytics`, `Avia_Pars`, `netsleuth`, `summarum`, `AgroTech CV`).

4. **Zero-Downtime Resilience:**
   - Database runs in SQLite WAL (Write-Ahead Logging) mode with `PRAGMA busy_timeout = 5000`.
   - Network scrapers use isolated try/except blocks and per-platform user-agent emulation; failure on one platform does not impact others.
   - Telegram notifier gracefully handles network glitches and rate limits without terminating background workers.

"""Prompts and instructions based on FREELANCE_PROFILE.md and PROJECTS_DOSSIER.md."""

from typing import Any, Dict, Optional
from src.config import settings
from src.models.order import RawOrder

DEFAULT_SYSTEM_PROMPT = """Ты - старший Python-разработчик и ассистент Андрея Пименова (@horizontal42, Junior+/Middle).
Твоя задача - объективно оценить заказ с биржи фриланса и сформировать ответ СТРОГО в формате JSON по заданной схеме.

БЭКГРАУНД РАЗРАБОТЧИКА (БАЗА ПРОЕКТОВ ИЗ ДОСЬЕ):
1. Speech Analytics (Intervesp): B2B речевая аналитика. FastAPI, Celery, WhisperX, Qwen 32B, Bitrix24 REST API, детерминированный роутинг оценок с fuzzy-проверкой цитат (difflib, flip-rate 0%), сброс памяти через malloc_trim ctypes, генерация накопительных PDF-отчетов O(n).
2. Avia_Pars: Telegram-бот на aiogram 3, SQLite WAL, Circuit Breaker, асинхронные очереди, высокая надежность под нагрузкой.
3. leads-monitor: B2B автоматизация. Поиск вакансий hh.ru, DaData API, LLM-анализ, Google Sheets API (gspread), SQLite.
4. netsleuth: Кроссплатформенный сетевой CLI на Python (Typer, Rich, httpx), обвязка Iphlpapi.dll (Win32 API) без прав админа, 850+ тестов.
5. summarum: Десктопный калькулятор с Pratt-парсером естественного языка (Tauri 2, Rust, TypeScript).
6. RAG-ассистент: Поиск по сложной номенклатуре и ГОСТам на LangChain, Qdrant, FastAPI для 130+ менеджеров.
7. AgroTech CV: Видеоаналитика с IP-камер (YOLOv8, ByteTrack, IsolationForest, OpenCV, CUDA).

ЖЕСТКИЕ ПРАВИЛА:
1. Запрет длинных тире (em-dash)! Используй только обычные дефисы "-".
2. Краткая суть задачи (executive_summary): сформулируй в 3-4 емких предложениях (что сделать, стек, ключевая техническая сложность). Чем меньше лишних слов, тем лучше, но ровно 3-4 предложения.
3. Оценивай реальные риски (лимиты, блокировки, капчи, WAF, нестабильные API).
4. Первоначальный расчет сроков по методике PERT: E = (O + 4M + P) / 6, sigma = (P - O) / 6.
5. Расчет двух видов стоимости (Mistral):
   - ОБЪЕКТИВНАЯ РЫНОЧНАЯ ЦЕНА (market_price): рассчитай чистую объективную рыночную стоимость разработки в рублях ИСКЛЮЧИТЕЛЬНО на основе времени (pure_dev_hours), технической сложности (complexity) и ставки 750-1000 руб/час (либо рыночной стоимости ботов/парсеров). КАТЕГОРИЧЕСКИ НЕ привязывайся к бюджету заказчика при расчете market_price!
   - ТАКТИЧЕСКАЯ РЕКОМЕНДУЕМАЯ ЦЕНА (recommended_price): ставка, которую стоит предложить конкретному заказчику с учетом его бюджета (если у клиента указан желаемый и допустимый бюджет, например на Kwork, целься ближе к допустимому максимуму или давай обоснованный оффер).
   - В поле price_justification четко сравни рыночную цену с бюджетом клиента (демпинг / нормальный бюджет) и обоснуй стратегию.
   - Независимый глубокий расчет рыночной ставки на основе поиска по биржам в интернете производит Antigravity при генерации отклика по требованию.
6. Поле proposal_text оставь пустым (""), так как отклик генерируется по требованию пользователя через Antigravity.
7. Все материалы задачи и файлы уже полностью извлечены и предоставлены во входных данных. Тебе ЗАПРЕЩЕНО переходить по внешним ссылкам, использовать инструменты экспорта страниц или вызывать браузер.

ФОРМАТ ОТВЕТА (СТРОГО JSON):
{
  "take_order": true,
  "score": 8,
  "priority": "hot",
  "executive_summary": "Краткая суть задачи в 3-4 емких предложениях.",
  "market_price": 15000,
  "recommended_price": 12000,
  "price_justification": "Рынок ~15 000 ₽ исходя из 15ч работы. Заказчик рассчитывает на 12 000 ₽, рекомендуем предложить 12 000 ₽.",
  "realistic_days": 4.0,
  "matched_project": "Avia_Pars",
  "complexity": 5,
  "pure_dev_hours": 12.0,
  "risks_and_pitfalls": [
    "Лимиты API внешнего сервиса",
    "Необходимость очередей и повторных попыток при высокой нагрузке"
  ],
  "proposal_text": "",
  "pert": {
    "optimistic_days": 2.0,
    "most_likely_days": 4.0,
    "pessimistic_days": 7.0,
    "expected_days": 4.17,
    "sigma": 0.83
  }
}
"""

DEFAULT_PROPOSAL_PROMPT_TEMPLATE = """Ты - старший Python-разработчик и ассистент Андрея Пименова (@horizontal42, Junior+/Middle).
Твоя задача:
1. ПРОВЕСТИ РЫНОЧНУЮ ОЦЕНКУ С ВЕБ-ПОИСКОМ:
   - ОБЯЗАТЕЛЬНО используй веб-поиск (search_web), чтобы проверить реальные актуальные расценки на российских биржах фриланса (Kwork, FL.ru, Хабр Фриланс) для аналогичных задач.
   - Определи обоснованную рыночную цену задачи (recommended_price в рублях) без демпинга с учетом сложности и стека.
   - Сформулируй краткое обоснование цены и стратегию торга (price_justification) с разбором бюджета заказчика.
2. СОСТАВИТЬ ИДЕАЛЬНЫЙ, ПРОДАЮЩИЙ ОТКЛИК (proposal_text):
   - ПРАВИЛО ПЕРВЫХ 140 СИМВОЛОВ: первые 2 предложения видны в превью на бирже. Сразу к сути и боли заказчика: "Добрый день. По опыту интеграции с Битрикс24..." или "Добрый день. Разрабатывал аналогичного Telegram-бота...".
   - ТОЧНЫЕ ФАКТЫ ИЗ ДОСЬЕ: ссылайся на реальный опыт разработчика (FastAPI, aiogram 3, Bitrix24 REST API, Celery, WhisperX, Qdrant).
   - ЗАПРЕТ МАРКЕРОВ ИИ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать длинное тире (em-dash)! Используй ТОЛЬКО обычный дефис "-". Никаких списков с жирными заголовками (**Стек:**, **Преимущества:**), никакого канцелярита и роботизированного официоза.
   - В конце задай конкретный технический вопрос по задаче или предложи обсудить детали в чате.

БЭКГРАУНД РАЗРАБОТЧИКА (БАЗА ПРОЕКТОВ ИЗ ДОСЬЕ):
{dossier_text}

ДАННЫЕ ЗАКАЗА:
Источник: {source}
Название: {title}
Бюджет: {price}
Описание задачи:
{description}

{extra_context}

ФОРМАТ ОТВЕТА (СТРОГО JSON):
```json
{{
  "market_price": 40000,
  "recommended_price": 35000,
  "price_justification": "Объективная рыночная стоимость аналогичных задач на биржах ~40 000 ₽. С учетом бюджета заказчика рекомендуем заходить с 35 000 ₽.",
  "proposal_text": "Готовый текст отклика для отправки клиенту..."
}}
```
Верни ТОЛЬКО JSON-блок, строго с обычными дефисами "-" (без длинных тире).
"""


DEFAULT_COVER_LETTER_TEMPLATE = """Ты - старший карьерный консультант и технический ментор Андрея Пименова (@horizontal42, Junior+/Middle AI/Python-разработчик).
Твоя задача - составить идеальное, персонализированное и убедительное сопроводительное письмо (Cover Letter) для отклика на вакансию HeadHunter (hh.ru).

ЖЕСТКИЕ ПРАВИЛА:
1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать длинное тире (em-dash)! Используй ТОЛЬКО обычный дефис "-".
2. Никаких шаблонных робо-приветствий вроде "Я с большим энтузиазмом ознакомился с вашей вакансией..." и списков с жирными маркерами (**Стек:**, **О себе:**). Пиши живым, деловым языком уверенного разработчика.
3. ПРАВИЛО ПЕРВЫХ 150 СИМВОЛОВ: первые 2-3 строчки HR видит в превью. Сразу зацепи релевантным стеком и реальным коммерческим опытом!
4. ОПИРАЙСЯ НА РЕАЛЬНЫЙ ОПЫТ ИЗ РЕЗЮМЕ АНДРЕЯ:
   - Cortex IT: B2B речевая аналитика звонков (WhisperX, pyannote, Qwen 32B, FastAPI, Celery, Bitrix24), корпоративный RAG на Qdrant/LangChain, компьютерное зрение YOLOv8/ByteTrack.
   - Компьютерный Цехъ: разработка системы тестирования оборудования LaptopTester (WMI, smartctl, ReportLab).
   - Стек: Python, FastAPI, Celery, Redis, PostgreSQL, Docker, Linux, Git.
   - Ссылайся именно на те проекты и технологии, которые упомянуты в требованиях вакансии!
5. Подчеркни умение быстро погружаться в бизнес-задачи (благодаря коммерческому бэкграунду в B2B-переговорах в Zoon и Cortex IT).
6. В конце: готовность выполнить адекватное тестовое задание или созвониться для технического скрининга. Контакты: Telegram @horizontal42, email: frolka84@gmail.com.
7. УЧЕТ ПРОБЕЛОВ В ТРЕБОВАНИЯХ (SKILLS GAP): если в контексте указаны пробелы в стеке и стратегия парирования, используй ее в тексте: покажи крепкий смежный опыт (FastAPI/Celery/Docker/WhisperX) и готовность быстро применить аналогичные инструменты без долгого онбординга.

РЕЗЮМЕ КАНДИДАТА:
{dossier_text}

ДАННЫЕ ВАКАНСИИ:
Название: {title}
{extra_context}
Описание вакансии:
{description}

ФОРМАТ ОТВЕТА (СТРОГО JSON):
```json
{{
  "proposal_text": "Готовый текст сопроводительного письма..."
}}
```
Верни ТОЛЬКО JSON-блок, строго с обычными дефисами "-" (без длинных тире).
"""

DEFAULT_VACANCY_SYSTEM_PROMPT = """Ты - старший AI/Python-разработчик и карьерный ментор Андрея Пименова (@horizontal42, Junior+/Middle).
Твоя задача - объективно проанализировать вакансию с HeadHunter (hh.ru) под профиль и резюме Андрея и сформировать ответ СТРОГО в формате JSON по заданной схеме.

БЭКГРАУНД И РЕЗЮМЕ КАНДИДАТА (АНДРЕЙ ПИМЕНОВ):
{dossier_text}

ЖЕСТКИЕ ПРАВИЛА:
1. Запрет длинных тире (em-dash)! Используй только обычные дефисы "-".
2. О компании (company_overview): 2-3 емких предложения (сфера бизнеса, масштаб, специфика продукта компании).
3. Требования к кандидату (candidate_requirements): ключевой стек, требуемый опыт, адекватность требований к грейду.
4. Чем предстоит заниматься (job_responsibilities): реальные рабочие задачи, разработка и поддержка каких модулей.
5. Подводные камни и скрытые риски (risks_and_pitfalls): овертаймы, замаскированные продажи/холодные звонки, неоплачиваемое тестовое задание, требования сеньора под видом джуна, легаси кодовая база, размытые зоны ответственности.
6. Почему подходит Андрею (match_reason): конкретные точки пересечения резюме Андрея (Cortex IT, Speech Analytics WhisperX, RAG Qdrant, CV YOLOv8, FastAPI, Celery) с требованиями вакансии.
7. Анализ пробелов в стеке (Skills Gap):
   - skills_gap: укажи конкретные технологии или навыки из описания вакансии, которых нет в резюме Андрея (например, "Kubernetes, vLLM, RabbitMQ"). Если все ключевые требования закрыты резюме, напиши "Критичных пробелов нет".
   - skills_gap_counter: как парировать этот пробел в сопроводительном письме (например, "Опереться на опыт работы с Docker Compose, асинхронными очередями Celery/Redis и батчингом WhisperX на GPU").
8. Оценка привлекательности от 1 до 10 (score): если стек хорошо совпадает и адекватные условия - score 7-10 (priority: "hot"). Если частичное совпадение или неясные условия - score 4-6 (priority: "normal"). Если неадекват или полный оффтоп - score 1-3 (priority: "trash").
9. Поле proposal_text оставь пустым (""), так как сопроводительное письмо генерируется по отдельному требованию пользователя через Antigravity.

ФОРМАТ ОТВЕТА (СТРОГО JSON):
{{
  "take_order": true,
  "score": 8,
  "priority": "hot",
  "executive_summary": "Краткая суть вакансии в 2-3 емких предложениях.",
  "company_overview": "Информация о компании и продукте.",
  "candidate_requirements": "Требования к стеку и грейду.",
  "job_responsibilities": "Чем предстоит заниматься на практике.",
  "match_reason": "Конкретное совпадение со стеком и опытом Андрея.",
  "skills_gap": "Требуется опыт с Kubernetes и vLLM.",
  "skills_gap_counter": "Опереться на Docker Compose, батчинг на GPU в WhisperX и быстрое погружение.",
  "recommended_price": 0,
  "price_justification": "",
  "realistic_days": 0,
  "matched_project": "Cortex IT (RAG / Speech Analytics)",
  "complexity": 5,
  "pure_dev_hours": 0,
  "risks_and_pitfalls": [
    "Возможное объемное тестовое задание",
    "Необходимость быстрого погружения в существующую кодовую базу"
  ],
  "proposal_text": ""
}}
"""


def get_system_prompt() -> str:
    """Получить актуальный системный промпт из конфигурации config.yml."""
    prompt = getattr(settings, "ANALYSIS_SYSTEM_PROMPT", "")
    return prompt if prompt else DEFAULT_SYSTEM_PROMPT


def get_proposal_template() -> str:
    """Получить актуальный шаблон отклика из конфигурации config.yml."""
    tmpl = getattr(settings, "PROPOSAL_PROMPT_TEMPLATE", "")
    if tmpl:
        return tmpl
    dossier = getattr(settings, "DOSSIER_TEXT", "")
    return DEFAULT_PROPOSAL_PROMPT_TEMPLATE.replace("{dossier_text}", dossier)


def get_vacancy_system_prompt() -> str:
    """Получить актуальный системный промпт анализа вакансий HH.ru."""
    prompt = getattr(settings, "VACANCY_ANALYSIS_SYSTEM_PROMPT", "")
    if prompt:
        return prompt
    dossier = getattr(settings, "DOSSIER_TEXT", "")
    return DEFAULT_VACANCY_SYSTEM_PROMPT.format(dossier_text=dossier)


def get_cover_letter_template() -> str:
    """Получить актуальный шаблон сопроводительного письма."""
    tmpl = getattr(settings, "COVER_LETTER_TEMPLATE", "")
    if tmpl:
        return tmpl
    dossier = getattr(settings, "DOSSIER_TEXT", "")
    return DEFAULT_COVER_LETTER_TEMPLATE.replace("{dossier_text}", dossier)


# Для обратной совместимости
SYSTEM_PROMPT = get_system_prompt()
PROPOSAL_PROMPT_TEMPLATE = get_proposal_template()


def build_vacancy_analysis_prompt(order: RawOrder) -> str:
    """Сформировать промпт анализа вакансии HH.ru для LLM."""
    salary_info = (
        f"{int(order.price)} ₽"
        if order.price
        else ("По договоренности" if order.is_negotiable else "Не указана")
    )
    tags_info = ", ".join(order.tags) if order.tags else "Нет"
    meta_info = (
        f"\n\nМЕТАДАННЫЕ ВАКАНСИИ:\n{order.attachments_text.strip()}"
        if order.attachments_text
        else ""
    )

    user_content = f"""
ПРОАНАЛИЗИРУЙ ВАКАНСИЮ:
Источник: HEADHUNTER (hh.ru, ID: {order.external_id})
Название: {order.title}
Зарплата: {salary_info}
Теги и навыки: {tags_info}{meta_info}

ОПИСАНИЕ И ТРЕБОВАНИЯ ВАКАНСИИ:
{order.description}

ВАЖНО: Все материалы вакансии уже предоставлены выше.
Сформируй JSON-ответ строго по инструкции. Обязательно заполни поля: company_overview, candidate_requirements, job_responsibilities, match_reason, risks_and_pitfalls, score, priority.
Поле proposal_text оставь пустой строкой.
"""
    return f"{get_vacancy_system_prompt()}\n\n{user_content}"


def build_cover_letter_prompt(
    order: RawOrder,
    analysis_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Сформировать промпт для генерации сопроводительного письма (Cover Letter) для HH.ru."""
    extra_context = ""
    if analysis_data:
        company = analysis_data.get("company_overview", "")
        reqs = analysis_data.get("candidate_requirements", "")
        tasks = analysis_data.get("job_responsibilities", "")
        match = analysis_data.get("match_reason", "")
        gap = analysis_data.get("skills_gap", "")
        counter = analysis_data.get("skills_gap_counter", "")

        extra_lines = [
            f"- О компании: {company}" if company else "",
            f"- Требования: {reqs}" if reqs else "",
            f"- Задачи: {tasks}" if tasks else "",
            f"- Точки совпадения со стеком Андрея: {match}" if match else "",
        ]
        if gap and gap != "Критичных пробелов нет":
            extra_lines.append(f"- Пробелы в стеке: {gap}")
            if counter:
                extra_lines.append(f"- Как парировать пробел: {counter}")

        valid_lines = [l for l in extra_lines if l]
        if valid_lines:
            extra_context = "Контекст анализа вакансии:\n" + "\n".join(valid_lines) + "\n"
    if order.attachments_text and order.attachments_text.strip():
        extra_context += f"\nДополнительные данные:\n{order.attachments_text.strip()}\n"

    full_description = order.description
    template = get_cover_letter_template()
    return template.format(
        title=order.title,
        description=full_description,
        extra_context=extra_context,
    )


def build_analysis_prompt(order: RawOrder) -> str:
    """Сформировать промпт анализа заказа/вакансии для LLM."""
    from src.models.order import SourcePlatform
    if order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER):
        return build_vacancy_analysis_prompt(order)

    price_info = (
        f"{int(order.price)} ₽"
        if order.price
        else ("По договоренности" if order.is_negotiable else "Не указан")
    )
    tags_info = ", ".join(order.tags) if order.tags else "Нет"

    attachments_block = ""
    if order.attachments_text and order.attachments_text.strip():
        attachments_block = (
            f"\n\nПРИКРЕПЛЕННЫЕ К ЗАКАЗУ ФАЙЛЫ И МАТЕРИАЛЫ:\n"
            f"{order.attachments_text.strip()}"
        )

    user_content = f"""
ПРОАНАЛИЗИРУЙ ЗАКАЗ:
Источник: {order.source.value.upper()} (ID: {order.external_id})
Название: {order.title}
Бюджет заказчика: {price_info}
Теги: {tags_info}

ПОЛНОЕ ТЕХНИЧЕСКОЕ ЗАДАНИЕ (ВЫГРУЖЕНО ИЗ СИСТЕМЫ):
{order.description}{attachments_block}

ВАЖНО: Все материалы задачи и файлы уже полностью извлечены и предоставлены выше. Тебе НЕ нужно переходить по внешним ссылкам, вызывать браузер или экспортировать заказ извне.
Сформируй JSON-ответ строго по инструкции. Поле proposal_text оставь пустой строкой.
"""
    return f"{get_system_prompt()}\n\n{user_content}"


def build_proposal_prompt(
    order: RawOrder,
    analysis_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Сформировать промпт для генерации отклика или сопроводительного письма."""
    from src.models.order import SourcePlatform
    if order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER):
        return build_cover_letter_prompt(order, analysis_data)
    price_info = (
        f"{int(order.price)} ₽"
        if order.price
        else ("По договоренности" if order.is_negotiable else "Не указан")
    )
    extra_context = ""
    if analysis_data:
        matched = analysis_data.get("matched_project")
        summary = analysis_data.get("executive_summary")
        risks = analysis_data.get("risks_and_pitfalls", [])
        extra_context = (
            f"Контекст анализа:\n"
            f"- Наиболее близкий кейс из досье: {matched}\n"
            f"- Суть задачи: {summary}\n"
            f"- Риски: {', '.join(risks) if risks else 'стандартные'}\n"
        )

    full_description = order.description
    if order.attachments_text and order.attachments_text.strip():
        full_description = (
            f"{order.description}\n\n[Прикрепленные файлы и материалы]:\n{order.attachments_text.strip()}"
        )

    template = get_proposal_template()
    return template.format(
        source=order.source.value.upper(),
        title=order.title,
        price=price_info,
        description=full_description,
        extra_context=extra_context,
    )


def build_chat_prompt(
    order: RawOrder,
    analysis_data: Optional[Dict[str, Any]] = None,
    proposal_text: Optional[str] = None,
    history: Optional[list] = None,
    user_message: str = "",
) -> str:
    """Сформировать контекстный промпт для ответа на вопрос разработчика по конкретному заказу/вакансии."""
    dossier_text = settings.PROMPTS_CONFIG.projects_dossier
    price_info = (
        f"{int(order.price)} ₽"
        if order.price
        else ("По договоренности" if order.is_negotiable else "Не указан")
    )

    full_description = order.description
    if order.attachments_text and order.attachments_text.strip():
        full_description = (
            f"{order.description}\n\n[Прикрепленные файлы и материалы]:\n{order.attachments_text.strip()}"
        )

    analysis_context = ""
    if analysis_data:
        items = []
        if analysis_data.get("executive_summary"):
            items.append(f"Суть задачи: {analysis_data['executive_summary']}")
        if analysis_data.get("matched_project"):
            items.append(f"Кейс из досье: {analysis_data['matched_project']}")
        if analysis_data.get("complexity"):
            items.append(f"Оценка сложности: {analysis_data['complexity']}/10")
        if analysis_data.get("risks_and_pitfalls"):
            items.append(f"Риски: {', '.join(analysis_data['risks_and_pitfalls'])}")
        if analysis_data.get("recommended_price"):
            items.append(f"Оценка рыночной стоимости: {analysis_data['recommended_price']} ₽")
        if analysis_data.get("price_justification"):
            items.append(f"Обоснование цены: {analysis_data['price_justification']}")
        if analysis_data.get("company_overview"):
            items.append(f"Компания: {analysis_data['company_overview']}")
        if analysis_data.get("candidate_requirements"):
            items.append(f"Требования: {analysis_data['candidate_requirements']}")
        if analysis_data.get("skills_gap"):
            items.append(f"Пробелы в стеке: {analysis_data['skills_gap']}")
        if analysis_data.get("skills_gap_counter"):
            items.append(f"Парирование пробелов: {analysis_data['skills_gap_counter']}")
        if items:
            analysis_context = "ДАННЫЕ ПРЕДЫДУЩЕГО АНАЛИЗА:\n" + "\n".join(f"- {i}" for i in items) + "\n"

    prop_context = ""
    if proposal_text and proposal_text.strip():
        label = "Cover Letter" if order.source.value in ("hh_ru", "habr_career") else "Отклик"
        prop_context = f"СГЕНЕРИРОВАННЫЙ {label.upper()}:\n{proposal_text.strip()}\n"

    history_context = ""
    if history:
        history_lines = []
        for msg in history:
            role_label = "Андрей (Разработчик)" if msg.get("role") == "user" else f"ИИ ({msg.get('model', 'assistant')})"
            history_lines.append(f"{role_label}: {msg.get('message', '')}")
        if history_lines:
            history_context = "ИСТОРИЯ ПЕРЕПИСКИ ПО ЗАКАЗУ:\n" + "\n".join(history_lines) + "\n"

    return f"""Ты - старший технический ментор и ассистент Андрея Пименова (@horizontal42, Junior+/Middle Python/AI разработчик).
Андрей обратился к тебе с вопросом по конкретному заказу или вакансии.
Ответь четко, практично, по делу и профессионально. Помогай оценивать стек, архитектуру, риски, тактику переговоров или ответы заказчику.

ЖЕСТКИЕ ПРАВИЛА:
1. Запрет длинных тире (em-dash)! Используй только обычные дефисы "-".
2. Не используй шаблоны, канцелярит и лишние вводные слова. Отвечай сразу по существу.
3. Опирайся на реальный профиль и стек Андрея из досье.

БЭКГРАУНД РАЗРАБОТЧИКА:
{dossier_text}

ДАННЫЕ ЗАКАЗА / ВАКАНСИИ:
Источник: {order.source.value.upper()} (ID: {order.external_id})
Название: {order.title}
Бюджет / Зарплата: {price_info}
ТЗ / Описание:
{full_description}

{analysis_context}
{prop_context}
{history_context}
ВОПРОС АНДРЕЯ:
{user_message}

ТВОЙ ОТВЕТ:
"""

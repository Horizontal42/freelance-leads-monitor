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
5. Оценка рыночной цены:
   - Поля recommended_price и price_justification оставь 0 и "" (актуальный расчет ставки на основе поиска по биржам в интернете производит Antigravity при генерации отклика по кнопке).
6. Поле proposal_text оставь пустым (""), так как отклик генерируется по требованию пользователя через Antigravity.
7. Все материалы задачи и файлы уже полностью извлечены и предоставлены во входных данных. Тебе ЗАПРЕЩЕНО переходить по внешним ссылкам, использовать инструменты экспорта страниц или вызывать браузер.

ФОРМАТ ОТВЕТА (СТРОГО JSON):
{
  "take_order": true,
  "score": 8,
  "priority": "hot",
  "executive_summary": "Краткая суть задачи в 3-4 емких предложениях.",
  "recommended_price": 0,
  "price_justification": "",
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
  "recommended_price": 35000,
  "price_justification": "Разбор бюджета заказчика, рыночная вилка по результатам поиска цен на биржах, стратегия торга",
  "proposal_text": "Готовый текст отклика для отправки клиенту..."
}}
```
Верни ТОЛЬКО JSON-блок, строго с обычными дефисами "-" (без длинных тире).
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


# Для обратной совместимости
SYSTEM_PROMPT = get_system_prompt()
PROPOSAL_PROMPT_TEMPLATE = get_proposal_template()


def build_analysis_prompt(order: RawOrder) -> str:
    """Сформировать промпт анализа заказа для LLM."""
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
    """Сформировать промпт для генерации отклика по требованию."""
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

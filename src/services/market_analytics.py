"""Service for IT market analytics, skill demand tracking, and daily trends."""

import json
import logging
import re
import statistics
from typing import Any, Dict, List, Optional
from src.storage.db import get_db_connection
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)

# Полная таксономия IT-навыков для общерыночного анализа
TECH_SKILLS_TAXONOMY: List[tuple[str, str, str]] = [
    # (Имя навыка, Категория, Regex паттерн)
    # 1. Языки программирования
    ("Python", "Languages", r"\bpython\b"),
    ("JavaScript", "Languages", r"\b(?:javascript|js)\b"),
    ("TypeScript", "Languages", r"\b(?:typescript|ts)\b"),
    ("Golang", "Languages", r"\b(?:golang|go)\b"),
    ("Java", "Languages", r"\bjava\b(?!script)"),
    ("C++ / C", "Languages", r"\b(?:c\+\+|cpp|\bc\b)\b"),
    ("C# / .NET", "Languages", r"\b(?:c#|csharp|\.net)\b"),
    ("PHP", "Languages", r"\bphp\b"),
    ("Rust", "Languages", r"\brust\b"),
    ("Kotlin", "Languages", r"\bkotlin\b"),
    ("Swift", "Languages", r"\bswift\b"),
    # 2. Бэкенд и фреймворки
    ("FastAPI", "Backend", r"\bfastapi\b"),
    ("Django", "Backend", r"\bdjango\b"),
    ("Flask", "Backend", r"\bflask\b"),
    ("Node.js / NestJS", "Backend", r"\b(?:node(?:\.js)?|nestjs|express(?:\.js)?)\b"),
    ("Spring Boot", "Backend", r"\b(?:spring|spring boot)\b"),
    ("Laravel", "Backend", r"\blaravel\b"),
    ("REST API / gRPC", "Backend", r"\b(?:rest\s*api|grpc|graphql)\b"),
    # 3. AI, LLM, RAG и Машинное обучение
    ("LLM / Agents / GPT", "AI & ML", r"\b(?:llm|gpt|openai|claude|gemini|mistral|llama|crewai|ai[- ]?agent|ии[- ]?агент|нейросет)\b"),
    ("RAG / Vector DB", "AI & ML", r"\b(?:rag|qdrant|chroma|pinecone|векторн)\b"),
    ("Whisper / Речевая аналитика", "AI & ML", r"\b(?:whisper|stt|tts|speech|транскриб|распознавание речи)\b"),
    ("Computer Vision / YOLO", "AI & ML", r"\b(?:yolo|opencv|cv|компьютерн[а-я]* зрени)\b"),
    ("PyTorch / ML Engineering", "AI & ML", r"\b(?:pytorch|tensorflow|scikit|fine[- ]?tuning|lora|huggingface|машинн[а-я]* обучен)\b"),
    ("Ollama / Local LLM", "AI & ML", r"\b(?:ollama|vllm|deepseek|локальн[а-я]* модель)\b"),
    # 4. Боты, автоматизация и CRM
    ("Telegram Bot", "Automation", r"\b(?:telegram|aiogram|telebot|тг[- ]?бот|чат[- ]?бот)\b"),
    ("Парсинг / Scraping", "Automation", r"\b(?:парс|scraping|crawler|playwright|selenium|beautifulsoup)\b"),
    ("CRM / Битрикс24 / amoCRM", "Automation", r"\b(?:bitrix|битрикс|amocrm|планфикс|planfix|мойсклад)\b"),
    ("n8n / Make / No-Code", "Automation", r"\b(?:n8n|zapier|make\.com)\b"),
    # 5. Базы данных и Data Engineering
    ("PostgreSQL / SQL", "Databases", r"\b(?:postgres|postgresql|mysql|sqlite|sql)\b"),
    ("Redis / Очереди", "Databases", r"\b(?:redis|celery|rabbitmq|kafka)\b"),
    ("Data Engineering / ETL", "Databases", r"\b(?:clickhouse|etl|dbt|airflow|data\s*engineer)\b"),
    ("MongoDB / NoSQL", "Databases", r"\b(?:mongo|mongodb|nosql)\b"),
    # 6. Инфраструктура и DevOps
    ("Docker / K8s", "DevOps", r"\b(?:docker|kubernetes|k8s)\b"),
    ("Linux / Администрирование", "DevOps", r"\b(?:linux|ubuntu|debian|centos|systemd|bash|shell)\b"),
    ("CI/CD / DevOps", "DevOps", r"\b(?:ci[-/]cd|gitlab[- ]?ci|github actions|jenkins|devops)\b"),
    # 7. Фронтенд и мобильная разработка
    ("React / Next.js", "Frontend", r"\b(?:react|next\.?js)\b"),
    ("Vue.js", "Frontend", r"\b(?:vue|nuxt)\b"),
    ("Mobile / Flutter", "Frontend", r"\b(?:flutter|react native|ios|android)\b"),
]


class MarketAnalyticsService:
    """Сервис анализа общерыночного спроса, отслеживания динамики технологий и трендов."""

    def __init__(self, repo: Optional[OrderRepository] = None) -> None:
        self.repo = repo or OrderRepository()

    async def calculate_daily_snapshot(
        self,
        target_date: str,
        source_type: str = "all",  # 'order', 'vacancy', 'all'
        scope: str = "all_it",      # 'all_it', 'specialized'
    ) -> Dict[str, Any]:
        """Рассчитать снимок показателей за конкретный календарный день (YYYY-MM-DD)."""
        conds = ["date(created_at) = ?"]
        params: List[Any] = [target_date]

        # 1. Разделение по типу источника (заказы vs вакансии)
        if source_type == "order":
            conds.append("source NOT IN ('hh_ru', 'habr_career')")
        elif source_type == "vacancy":
            conds.append("source IN ('hh_ru', 'habr_career')")

        # 2. Охват: 'specialized' (только подходящие под наш профиль) vs 'all_it' (все IT)
        if scope == "specialized":
            conds.append("priority != 'trash'")

        where_clause = f"WHERE {' AND '.join(conds)}"

        async with self.repo._get_conn() as db:
            query = f"""
                SELECT
                    id, source, price, is_responded, is_skipped, priority,
                    title, description, tags, attachments_text
                FROM orders
                {where_clause}
            """
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return {
                "date": target_date,
                "source_type": source_type,
                "scope": scope,
                "total_count": 0,
                "responded_count": 0,
                "skipped_count": 0,
                "hot_count": 0,
                "avg_price": None,
                "median_price": None,
                "min_price": None,
                "max_price": None,
                "top_skills": {},
                "sources_breakdown": {},
                "ai_summary": None,
            }

        total_count = len(rows)
        responded_count = sum(1 for r in rows if r["is_responded"] == 1)
        skipped_count = sum(1 for r in rows if r["is_skipped"] == 1)
        hot_count = sum(1 for r in rows if r["priority"] == "hot")

        # Цены / зарплаты (фильтруем нулевые и отрицательные значения)
        prices = [r["price"] for r in rows if r["price"] and r["price"] > 0]
        avg_price = round(statistics.mean(prices), 0) if prices else None
        median_price = round(statistics.median(prices), 0) if prices else None
        min_price = min(prices) if prices else None
        max_price = max(prices) if prices else None

        # Разделение по источникам
        sources_breakdown: Dict[str, int] = {}
        for r in rows:
            src = r["source"]
            sources_breakdown[src] = sources_breakdown.get(src, 0) + 1

        # Частотный анализ навыков по всей таксономии IT
        skill_counts: Dict[str, int] = {}
        for r in rows:
            text = f"{r['title'] or ''} {r['description'] or ''} {r['tags'] or ''} {r['attachments_text'] or ''}".lower()
            for skill_name, _category, pattern in TECH_SKILLS_TAXONOMY:
                if re.search(pattern, text, re.IGNORECASE):
                    skill_counts[skill_name] = skill_counts.get(skill_name, 0) + 1

        # Сортируем навыки по убыванию частотности
        sorted_skills = dict(
            sorted(skill_counts.items(), key=lambda item: item[1], reverse=True)
        )

        snapshot = {
            "date": target_date,
            "source_type": source_type,
            "scope": scope,
            "total_count": total_count,
            "responded_count": responded_count,
            "skipped_count": skipped_count,
            "hot_count": hot_count,
            "avg_price": avg_price,
            "median_price": median_price,
            "min_price": min_price,
            "max_price": max_price,
            "top_skills": sorted_skills,
            "sources_breakdown": sources_breakdown,
            "ai_summary": None,
        }

        # Сохраняем снимок в БД
        await self.repo.save_market_snapshot(snapshot)
        return snapshot

    async def backfill_all_history(self) -> int:
        """Пересчитать и сохранить ежедневные снимки рынка за все доступные в БД даты."""
        dates = await self.repo.get_distinct_order_dates()
        count = 0
        for d in dates:
            for source_type in ["all", "order", "vacancy"]:
                for scope in ["all_it", "specialized"]:
                    await self.calculate_daily_snapshot(
                        target_date=d, source_type=source_type, scope=scope
                    )
                    count += 1
        logger.info("Бэкфилл аналитики рынка завершен: сохранено %d снимков.", count)
        return count

    async def get_trends_data(
        self,
        source_type: str = "vacancy",
        scope: str = "all_it",
        days: int = 30,
    ) -> Dict[str, Any]:
        """Сформировать агрегированные данные трендов и динамики за указанное число дней."""
        snapshots = await self.repo.get_market_snapshots(
            source_type=source_type, scope=scope, limit=days
        )
        if not snapshots:
            return {
                "source_type": source_type,
                "scope": scope,
                "days_count": 0,
                "snapshots": [],
                "aggregated_skills": [],
                "latest_snapshot": None,
            }

        # Сортируем по дате от старых к новым для построения графиков
        timeline = sorted(snapshots, key=lambda s: s["date"])

        # Суммарная частотность навыков за весь выбранный период
        total_items_in_period = sum(s["total_count"] for s in timeline)
        all_skills: Dict[str, Dict[str, Any]] = {}
        for s in timeline:
            top_skills = s.get("top_skills", {})
            for skill_name, cnt in top_skills.items():
                if skill_name not in all_skills:
                    # Находим категорию навыка
                    cat = "Other"
                    for sk, c, _ in TECH_SKILLS_TAXONOMY:
                        if sk == skill_name:
                            cat = c
                            break
                    all_skills[skill_name] = {"count": 0, "category": cat}
                all_skills[skill_name]["count"] += cnt

        aggregated_skills = []
        for name, data in all_skills.items():
            pct = round(data["count"] / total_items_in_period * 100, 1) if total_items_in_period > 0 else 0.0
            aggregated_skills.append({
                "name": name,
                "category": data["category"],
                "count": data["count"],
                "pct": pct,
            })
        aggregated_skills.sort(key=lambda x: x["count"], reverse=True)

        return {
            "source_type": source_type,
            "scope": scope,
            "days_count": len(timeline),
            "snapshots": timeline,
            "aggregated_skills": aggregated_skills,
            "latest_snapshot": timeline[-1] if timeline else None,
        }

    async def generate_ai_market_summary(
        self,
        llm_client: Any,
        source_type: str = "vacancy",
        scope: str = "all_it",
        days: int = 14,
    ) -> str:
        """Сформировать краткую AI-сводку рыночных трендов через Mistral 14B."""
        trends = await self.get_trends_data(
            source_type=source_type, scope=scope, days=days
        )
        snapshots = trends["snapshots"]
        if not snapshots:
            return "Недостаточно данных для формирования рыночной сводки."

        # Формируем компактную таблицу топ-15 навыков и динамики
        top_skills_summary = ", ".join(
            [f"{s['name']}: {s['count']} ({s['pct']}%)" for s in trends["aggregated_skills"][:15]]
        )

        avg_salaries = [
            f"{s['date']}: {int(s['avg_price'])} ₽ (всего {s['total_count']})"
            for s in snapshots
            if s.get("avg_price")
        ]
        salary_str = "; ".join(avg_salaries[-7:]) or "данных о ставках нет"

        prompt = (
            f"Ты - ведущий аналитик IT-рынка труда и технологических трендов (ноябрь 2026 года).\n"
            f"Проанализируй агрегированные данные по направлению '{source_type}' (охват: '{scope}') за последние {days} дней:\n\n"
            f"1. Топ востребованных навыков и технологий:\n{top_skills_summary}\n\n"
            f"2. Динамика публикаций и средних вилок/ставок:\n{salary_str}\n\n"
            f"Сформулируй четкую, плотную выжимку строго в 3-4 емких абзацах:\n"
            f"- Главные технологические драйверы спроса (какие стеки лидируют и растут).\n"
            f"- Уровень бюджетов/зарплат и динамика рынка.\n"
            f"- Практические рекомендации разработчикам (куда смещается фокус: AI-агенты, RAG, бэкенд, автоматизация).\n"
            f"ПРАВИЛА: Никаких длинных тире (em-dash), только дефисы '-'. Без общих фраз, предельно конкретно и фактологично."
        )

        try:
            logger.info("Запрос аналитической сводки рынка у Mistral 14B...")
            # Если llm_client имеет метод chat_text или mistral/antigravity
            if hasattr(llm_client, "mistral") and llm_client.mistral.api_key:
                response = await self._call_mistral_text(llm_client.mistral, prompt)
            elif hasattr(llm_client, "antigravity"):
                response = await self._call_antigravity_text(llm_client.antigravity, prompt)
            else:
                response = "LLM-клиент не настроен для генерации текста."

            # Сохраняем сгенерированную сводку в самый свежий снимок
            if snapshots:
                latest = snapshots[-1]
                await self.repo.save_market_ai_summary(
                    date=latest["date"],
                    source_type=source_type,
                    scope=scope,
                    ai_summary=response,
                )
            return response
        except Exception as e:
            logger.error("Ошибка при генерации AI-сводки рынка: %s", e)
            return f"Ошибка формирования сводки: {e}"

    async def _call_mistral_text(self, mistral_client: Any, prompt: str) -> str:
        """Прямой вызов Mistral API для текстовой генерации."""
        import httpx
        url = mistral_client.api_url
        headers = {
            "Authorization": f"Bearer {mistral_client.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": mistral_client.model or "ministral-14b-latest",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        async with mistral_client.semaphore:
            await mistral_client.rate_limiter.acquire()
            async with httpx.AsyncClient(timeout=mistral_client.timeout_seconds) as client:
                res = await client.post(url, headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
                text = data["choices"][0]["message"]["content"].strip()
                # Удаляем em-dash
                return text.replace("—", "-").replace("–", "-")

    async def _call_antigravity_text(self, antigravity_client: Any, prompt: str) -> str:
        """Вызов Antigravity CLI при недоступности Mistral."""
        res = await antigravity_client._run_antigravity(prompt)
        return res.replace("—", "-").replace("–", "-")

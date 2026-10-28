"""FastAPI Web Dashboard for Freelance Leads Monitor (jobs.3dvex.ru)."""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template
from src.config import settings
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Freelance Leads Monitor | jobs.3dvex.ru</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        dark: {
                            900: '#0f172a',
                            800: '#1e293b',
                            700: '#334155',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        .tab-active { border-bottom: 2px solid #3b82f6; color: #60a5fa; font-weight: 600; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans antialiased selection:bg-blue-600 selection:text-white">

    <!-- Top Navigation -->
    <header class="bg-slate-900 border-b border-slate-800 sticky top-0 z-50 backdrop-blur bg-slate-900/90">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <span class="text-2xl">⚡</span>
                <div>
                    <h1 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                        Freelance Leads Monitor
                        <span class="text-xs font-normal px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300 border border-blue-700/50">jobs.3dvex.ru</span>
                    </h1>
                    <p class="text-xs text-slate-400">Автоматический мониторинг Kwork и FL.ru с ИИ-оценкой</p>
                </div>
            </div>

            <div class="flex items-center space-x-4">
                <button onclick="window.location.reload()" class="text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-md border border-slate-700 flex items-center gap-1.5 transition">
                    🔄 Обновить
                </button>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full space-y-6">

        <!-- Stats Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-sm">
                <div class="text-xs font-medium text-slate-400 uppercase tracking-wider">Всего заказов</div>
                <div class="text-2xl font-extrabold text-white mt-1">{{ stats.total }}</div>
            </div>
            <div class="bg-slate-900 border border-amber-900/40 p-4 rounded-xl shadow-sm bg-gradient-to-br from-amber-950/20 to-transparent">
                <div class="text-xs font-medium text-amber-400 uppercase tracking-wider flex items-center gap-1">
                    <span>🔥</span> Горячие (Tier 1)
                </div>
                <div class="text-2xl font-extrabold text-amber-300 mt-1">{{ stats.hot }}</div>
            </div>
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-sm">
                <div class="text-xs font-medium text-blue-400 uppercase tracking-wider flex items-center gap-1">
                    <span>⚡</span> Обычные (Tier 2)
                </div>
                <div class="text-2xl font-extrabold text-blue-300 mt-1">{{ stats.normal }}</div>
            </div>
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-sm">
                <div class="text-xs font-medium text-slate-500 uppercase tracking-wider flex items-center gap-1">
                    <span>🗑</span> Отсеяно (Tier 3)
                </div>
                <div class="text-2xl font-extrabold text-slate-400 mt-1">{{ stats.trash }}</div>
            </div>
        </div>

        <!-- Filters Section -->
        <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-wrap items-center justify-between gap-4">
            <!-- Priority Filter -->
            <div class="flex items-center space-x-1 sm:space-x-2 text-sm">
                <span class="text-xs text-slate-400 font-semibold mr-1 uppercase">Приоритет:</span>
                <a href="/?priority=&source={{ selected_source }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if not selected_priority %}bg-blue-600 text-white{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Все
                </a>
                <a href="/?priority=hot&source={{ selected_source }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_priority == 'hot' %}bg-amber-600 text-white{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    🔥 Hot
                </a>
                <a href="/?priority=normal&source={{ selected_source }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_priority == 'normal' %}bg-blue-600 text-white{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    ⚡ Normal
                </a>
                <a href="/?priority=trash&source={{ selected_source }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_priority == 'trash' %}bg-slate-700 text-white{% else %}bg-slate-800 text-slate-400 hover:bg-slate-700{% endif %}">
                    🗑 Trash
                </a>
            </div>

            <!-- Source Filter -->
            <div class="flex items-center space-x-1 sm:space-x-2 text-sm">
                <span class="text-xs text-slate-400 font-semibold mr-1 uppercase">Биржа:</span>
                <a href="/?priority={{ selected_priority }}&source=" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if not selected_source %}bg-indigo-600 text-white{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Все
                </a>
                <a href="/?priority={{ selected_priority }}&source=kwork" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'kwork' %}bg-indigo-600 text-white{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Kwork
                </a>
                <a href="/?priority={{ selected_priority }}&source=fl_ru" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'fl_ru' %}bg-indigo-600 text-white{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    FL.ru
                </a>
            </div>
        </div>

        <!-- Orders Feed -->
        <div class="space-y-4">
            {% if not orders %}
                <div class="bg-slate-900 border border-slate-800 p-12 text-center rounded-xl text-slate-400">
                    <p class="text-lg font-medium text-slate-300">Заказы не найдены</p>
                    <p class="text-xs mt-1">Попробуйте сбросить фильтры или дождаться следующего цикла опроса бирж.</p>
                </div>
            {% endif %}

            {% for order in orders %}
                <div class="bg-slate-900 border {% if order.priority == 'hot' %}border-amber-500/50 shadow-lg shadow-amber-950/20{% elif order.priority == 'trash' %}border-slate-800 opacity-70{% else %}border-slate-800{% endif %} p-5 rounded-xl transition hover:border-slate-700 space-y-4">

                    <!-- Header Row -->
                    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div class="flex items-center space-x-2">
                            <!-- Platform Badge -->
                            <span class="text-xs font-bold uppercase px-2.5 py-1 rounded-md {% if order.source == 'kwork' %}bg-emerald-950 text-emerald-300 border border-emerald-800/60{% else %}bg-blue-950 text-blue-300 border border-blue-800/60{% endif %}">
                                {{ order.source }}
                            </span>

                            <!-- Priority Badge -->
                            {% if order.priority == 'hot' %}
                                <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1">
                                    🔥 HOT ({{ order.score }}/10)
                                </span>
                            {% elif order.priority == 'normal' %}
                                <span class="text-xs font-medium px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                                    ⚡ NORMAL ({{ order.score or '-' }}/10)
                                </span>
                            {% else %}
                                <span class="text-xs font-medium px-2 py-0.5 rounded-md bg-red-950/50 text-red-400 border border-red-900/40">
                                    🗑 REJECTED
                                </span>
                            {% endif %}

                            <span class="text-xs text-slate-500">
                                {{ order.created_at }}
                            </span>
                        </div>

                        <!-- Price Pill -->
                        <div class="text-right">
                            <span class="text-base font-extrabold text-white">
                                {% if order.price %}
                                    {{ "{:,.0f}".format(order.price).replace(',', ' ') }} ₽
                                {% elif order.is_negotiable %}
                                    Договорная
                                {% else %}
                                    Не указан
                                {% endif %}
                            </span>
                            {% if order.recommended_price %}
                                <div class="text-xs text-emerald-400">
                                    Реком.: {{ "{:,.0f}".format(order.recommended_price).replace(',', ' ') }} ₽
                                </div>
                            {% endif %}
                        </div>
                    </div>

                    <!-- Title & Link -->
                    <div>
                        <h2 class="text-lg font-bold text-white hover:text-blue-400 transition">
                            <a href="{{ order.url }}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5">
                                {{ order.title }}
                                <span class="text-xs text-slate-500 font-normal">🔗</span>
                            </a>
                        </h2>
                        {% if order.filter_reason and order.priority == 'trash' %}
                            <p class="text-xs text-red-400 mt-1 font-mono">Причина отсева: {{ order.filter_reason }}</p>
                        {% endif %}
                    </div>

                    <!-- Metrics Grid (for analyzed orders) -->
                    {% if order.score %}
                        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 text-xs">
                            <div>
                                <span class="text-slate-500 block">Кейс из досье</span>
                                <span class="font-semibold text-slate-200">{{ order.matched_project or '-' }}</span>
                            </div>
                            <div>
                                <span class="text-slate-500 block">Срок (PERT)</span>
                                <span class="font-semibold text-slate-200">
                                    {% if order.realistic_days %}{{ order.realistic_days }} дн.{% else %}-{% endif %}
                                </span>
                            </div>
                            <div>
                                <span class="text-slate-500 block">Сложность</span>
                                <span class="font-semibold text-slate-200">
                                    {% if order.analysis and order.analysis.complexity %}{{ order.analysis.complexity }}/10{% else %}-{% endif %}
                                </span>
                            </div>
                            <div>
                                <span class="text-slate-500 block">Чистое время</span>
                                <span class="font-semibold text-slate-200">
                                    {% if order.analysis and order.analysis.pure_dev_hours %}{{ order.analysis.pure_dev_hours }} ч.{% else %}-{% endif %}
                                </span>
                            </div>
                        </div>
                    {% endif %}

                    <!-- Description Preview -->
                    {% if order.description %}
                        <div class="text-xs text-slate-300 leading-relaxed max-h-24 overflow-y-auto whitespace-pre-line bg-slate-950/30 p-2.5 rounded border border-slate-800/40">
                            {{ order.description }}
                        </div>
                    {% endif %}

                    <!-- Proposal Section (if generated) -->
                    {% if order.proposal_text %}
                        <div class="bg-blue-950/20 border border-blue-900/40 p-3.5 rounded-lg space-y-2">
                            <div class="flex items-center justify-between">
                                <span class="text-xs font-semibold text-blue-400 uppercase tracking-wider flex items-center gap-1">
                                    <span>✍️</span> Готовый отклик (без ИИ-штампов, только дефисы)
                                </span>
                                <button onclick="copyProposal(this, 'proposal-{{ order.id }}')" class="text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white px-2.5 py-1 rounded shadow transition flex items-center gap-1">
                                    📋 Скопировать
                                </button>
                            </div>
                            <pre id="proposal-{{ order.id }}" class="text-xs text-slate-200 whitespace-pre-line bg-slate-900 p-2.5 rounded border border-slate-800 leading-relaxed select-all">{{ order.proposal_text }}</pre>
                        </div>
                    {% endif %}

                </div>
            {% endfor %}
        </div>

    </main>

    <!-- Footer -->
    <footer class="bg-slate-900 border-t border-slate-800 py-6 text-center text-xs text-slate-500">
        <p>Freelance Leads Monitor • jobs.3dvex.ru • Разработано для @horizontal42</p>
    </footer>

    <!-- Copy Script -->
    <script>
        function copyProposal(button, elementId) {
            const el = document.getElementById(elementId);
            if (!el) return;
            const text = el.innerText || el.textContent;
            navigator.clipboard.writeText(text).then(() => {
                const originalHtml = button.innerHTML;
                button.innerHTML = '✅ Скопировано!';
                button.classList.replace('bg-blue-600', 'bg-emerald-600');
                button.classList.replace('hover:bg-blue-500', 'hover:bg-emerald-500');
                setTimeout(() => {
                    button.innerHTML = originalHtml;
                    button.classList.replace('bg-emerald-600', 'bg-blue-600');
                    button.classList.replace('hover:bg-emerald-500', 'hover:bg-blue-500');
                }, 2000);
            }).catch(err => {
                alert('Не удалось скопировать: ' + err);
            });
        }
    </script>
</body>
</html>
"""


def create_web_app(repo: Optional[OrderRepository] = None) -> FastAPI:
    """Создать и настроить экземпляр FastAPI приложения."""
    app = FastAPI(
        title="Freelance Leads Monitor",
        description="Web dashboard for monitoring freelance leads on jobs.3dvex.ru",
        version="0.1.0",
    )

    repository = repo or OrderRepository()

    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard(
        request: Request,
        priority: Optional[str] = Query(None, description="Фильтр по приоритету (hot, normal, trash)"),
        source: Optional[str] = Query(None, description="Фильтр по источнику (kwork, fl_ru)"),
        limit: int = Query(60, ge=1, le=200),
    ):
        p_filter = priority.strip().lower() if priority else None
        s_filter = source.strip().lower() if source else None

        raw_orders = await repository.get_recent_orders(
            limit=limit,
            priority=p_filter,
            source=s_filter,
        )

        # Распаковываем analysis_json для каждого заказа при наличии
        formatted_orders: List[Dict[str, Any]] = []
        for o in raw_orders:
            item = dict(o)
            if item.get("analysis_json"):
                try:
                    item["analysis"] = json.loads(item["analysis_json"])
                except Exception:
                    item["analysis"] = None
            else:
                item["analysis"] = None
            formatted_orders.append(item)

        stats = await repository.get_stats()

        template = Template(DASHBOARD_HTML)
        html_content = template.render(
            orders=formatted_orders,
            stats=stats,
            selected_priority=p_filter or "",
            selected_source=s_filter or "",
        )
        return HTMLResponse(content=html_content)

    @app.get("/api/orders", response_class=JSONResponse)
    async def get_orders_api(
        priority: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 50,
    ):
        orders = await repository.get_recent_orders(
            limit=limit,
            priority=priority,
            source=source,
        )
        return {"orders": orders}

    @app.get("/api/stats", response_class=JSONResponse)
    async def get_stats_api():
        stats = await repository.get_stats()
        return stats

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app

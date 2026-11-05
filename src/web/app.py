"""FastAPI Web Dashboard for Freelance Leads Monitor (jobs.3dvex.ru)."""

from datetime import datetime
import html
import json
import logging
import re
import secrets
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Template
from src.analyzer.factory import get_llm_client
from src.config import settings
from src.models.analysis import AnalysisResult, extract_clean_text_items
from src.models.order import OrderPriority, RawOrder, SourcePlatform
from src.services.hh_applicant_service import HhApplicantService
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)


def format_bullet_html(raw_val: Any, accent: str = "slate") -> str:
    """Форматирует анализ вакансии в аккуратный маркированный HTML-список с подсветкой ключевых терминов."""
    items = extract_clean_text_items(raw_val)
    if not items:
        return ""

    if len(items) == 1 and len(items[0]) < 120 and "•" not in items[0]:
        escaped = html.escape(items[0])
        rendered = re.sub(r"\*\*(.*?)\*\*", r'<strong class="text-white font-semibold">\1</strong>', escaped)
        return f'<p class="leading-relaxed">{rendered}</p>'

    html_bullets = []
    bullet_dot = f'<span class="text-xs text-{accent}-400 mt-0.5 shrink-0">•</span>'
    for item in items:
        escaped = html.escape(item)
        rendered = re.sub(r"\*\*(.*?)\*\*", r'<strong class="text-white font-semibold">\1</strong>', escaped)
        html_bullets.append(
            f'<li class="flex items-start gap-2">{bullet_dot}<span>{rendered}</span></li>'
        )
    return f'<ul class="space-y-1.5 leading-relaxed">{"".join(html_bullets)}</ul>'

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>Freelance Leads & HH Vacancies Monitor | jobs.3dvex.ru</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        dark: {
                            950: '#090d16',
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
        .tab-btn.active {
            border-bottom: 2px solid #3b82f6;
            color: #60a5fa;
            font-weight: 600;
        }
        .custom-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scroll::-webkit-scrollbar-track { background: #0f172a; }
        .custom-scroll::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        button, [role="button"], a, .cursor-pointer {
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
    </style>
    <script>
        window.APP_BUILD_VERSION = "2.4.5";
        function logClient(action, data) {
            try {
                const payload = Object.assign({ action: action }, data || {});
                fetch('/api/client-log', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).catch(() => {});
            } catch(e) {}
        }
        window.onerror = function(msg, url, line, col, err) {
            logClient('client_js_error', {
                type: 'error',
                msg: String(msg) + ' at ' + String(url) + ':' + String(line) + ':' + String(col),
                stack: err ? err.stack : null
            });
        };
        window.onunhandledrejection = function(event) {
            logClient('client_unhandled_rejection', {
                type: 'error',
                msg: String(event ? event.reason : 'unknown')
            });
        };
    </script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans antialiased selection:bg-blue-600 selection:text-white" ontouchstart="">

    <!-- Top Navigation Header -->
    <header class="bg-slate-900/95 border-b border-slate-800 sticky top-0 z-50 backdrop-blur">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <span class="text-2xl">⚡</span>
                <div>
                    <h1 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                        Freelance Leads Monitor
                        <span class="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-blue-950 text-blue-300 border border-blue-800/60">jobs.3dvex.ru</span>
                        <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/80 select-none" title="Версия интерфейса">v2.4.5</span>
                    </h1>
                    <p class="text-xs text-slate-400">
                        {% if active_section == 'hh_ru' %}
                            Поиск AI & Python вакансий на HeadHunter под стек Андрея Пименова
                        {% else %}
                            Мониторинг Kwork, FL.ru, Freelance.ru, Pchel.net, Remote-job с ИИ-откликами
                        {% endif %}
                    </p>
                </div>
            </div>

            <div class="flex items-center space-x-3">
                <span class="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono bg-slate-800/80 text-emerald-400 border border-emerald-900/50">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    LLM: {{ llm_provider|upper }}
                </span>
                <button onclick="window.location.reload()" class="text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-700 flex items-center gap-1.5 transition">
                    🔄 Обновить
                </button>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full space-y-6">

        <!-- Top Section Switcher -->
        <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-1.5 bg-slate-900/90 border border-slate-800 rounded-2xl shadow-inner">
            <div class="flex items-center space-x-2 flex-wrap gap-y-1.5">
                <a href="/?section=freelance&tab=hot" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition {% if active_section == 'freelance' and active_tab not in ['settings', 'config'] %}bg-blue-600 text-white shadow-lg shadow-blue-500/25 font-bold{% else %}text-slate-400 hover:text-slate-200 hover:bg-slate-800/60{% endif %}">
                    <span class="text-base">💼</span>
                    <span>Фриланс-биржи</span>
                    <span class="text-xs px-2 py-0.5 rounded-full {% if active_section == 'freelance' and active_tab not in ['settings', 'config'] %}bg-blue-700/80 text-blue-100{% else %}bg-slate-800 text-slate-400{% endif %} font-mono">{{ extended_stats.freelance.total if extended_stats.freelance else extended_stats.total }}</span>
                </a>
                <a href="/?section=hh_ru&tab=hot" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition {% if active_section == 'hh_ru' and active_tab not in ['settings', 'config'] %}bg-gradient-to-r from-red-600 to-rose-600 text-white shadow-lg shadow-rose-500/25 font-bold{% else %}text-slate-400 hover:text-slate-200 hover:bg-slate-800/60{% endif %}">
                    <span class="text-base">🏢</span>
                    <span>Вакансии и найм</span>
                    <span class="text-xs px-2 py-0.5 rounded-full {% if active_section == 'hh_ru' and active_tab not in ['settings', 'config'] %}bg-rose-700/80 text-rose-100{% else %}bg-slate-800 text-slate-400{% endif %} font-mono">{{ extended_stats.hh_ru.total if extended_stats.hh_ru else 0 }}</span>
                </a>
                <a href="/?tab=settings" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition {% if active_tab == 'settings' %}bg-indigo-600 text-white shadow-lg shadow-indigo-500/25 font-bold{% else %}text-slate-400 hover:text-slate-200 hover:bg-slate-800/60{% endif %}">
                    <span class="text-base">⚙️</span>
                    <span>Настройки</span>
                </a>
                <a href="/?tab=config" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition {% if active_tab == 'config' %}bg-amber-600 text-white shadow-lg shadow-amber-500/25 font-bold{% else %}text-slate-400 hover:text-slate-200 hover:bg-slate-800/60{% endif %}">
                    <span class="text-base">🛠</span>
                    <span>Конфиг системы</span>
                </a>
            </div>

            <div class="text-xs text-slate-400 hidden lg:flex items-center gap-2 pr-3">
                {% if active_tab == 'config' %}
                    <span>🛠 Системный конфигуратор параметров (config.yml)</span>
                {% elif active_tab == 'settings' %}
                    <span>⚙️ Быстрые настройки фильтрации и бирж</span>
                {% elif active_section == 'freelance' %}
                    <span>📊 Источники: Kwork, FL.ru, Freelance.ru, Pchel.net</span>
                {% else %}
                    <span>🎯 Источники: HeadHunter (hh.ru) и Хабр Карьера</span>
                {% endif %}
            </div>
        </div>

        {% if active_tab not in ['settings', 'config'] %}
        <!-- Top Overview Stats Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    {% if active_section == 'hh_ru' %}Всего вакансий{% else %}Всего в базе{% endif %}
                </div>
                <div class="text-2xl font-black text-white mt-0.5">{{ stats.total }}</div>
            </div>
            <div class="bg-gradient-to-br from-amber-950/30 to-slate-900/80 border border-amber-900/50 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1">
                    <span>🔥</span> {% if active_section == 'hh_ru' %}Топ совпадения{% else %}Горячие (Tier 1){% endif %}
                </div>
                <div class="text-2xl font-black text-amber-300 mt-0.5">{{ stats.hot }}</div>
            </div>
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-blue-400 uppercase tracking-wider flex items-center gap-1">
                    <span>⚡</span> {% if active_section == 'hh_ru' %}Потенциальные{% else %}Обычные (Tier 2){% endif %}
                </div>
                <div class="text-2xl font-black text-blue-300 mt-0.5">{{ stats.normal }}</div>
            </div>
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                    <span>🗑</span> Отсеяно (Tier 3)
                </div>
                <div class="text-2xl font-black text-slate-400 mt-0.5">{{ stats.trash }}</div>
            </div>
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                    <span>📱</span> В Telegram
                </div>
                <div class="text-2xl font-black text-emerald-300 mt-0.5">{{ stats.sent_to_tg }}</div>
            </div>
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-purple-400 uppercase tracking-wider flex items-center gap-1">
                    <span>💰</span> {% if active_section == 'hh_ru' %}Средняя з/п Hot{% else %}Средний чек Hot{% endif %}
                </div>
                <div class="text-xl font-black text-purple-300 mt-1">
                    {% if stats.avg_hot_price %}{{ "{:,.0f}".format(stats.avg_hot_price).replace(",", " ") }} ₽{% else %}-{% endif %}
                </div>
            </div>
        </div>

        <!-- Section Navigation Tabs -->
        <div class="border-b border-slate-800 flex items-center justify-between overflow-x-auto custom-scroll">
            <nav class="flex space-x-1 sm:space-x-4 min-w-max">
                {% if active_section == 'freelance' %}
                    <a href="/?section=freelance&tab=hot&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'hot' %}active border-b-2 border-amber-500 text-amber-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>🔥</span> Горячие лиды
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono">{{ stats.hot }}</span>
                    </a>
                    <a href="/?section=freelance&tab=all&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'all' %}active border-b-2 border-blue-500 text-blue-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>⚡</span> Все прошедшие
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-mono">{{ stats.hot + stats.normal }}</span>
                    </a>
                    <a href="/?section=freelance&tab=normal&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'normal' %}active border-b-2 border-blue-500 text-blue-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>🎯</span> Потенциальные (Tier 2)
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">{{ stats.normal }}</span>
                    </a>
                    <a href="/?section=freelance&tab=responded&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'responded' %}active border-b-2 border-emerald-500 text-emerald-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}" title="Заказы, на которые вы уже откликнулись">
                        <span>✅</span> Отклики
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono">{{ stats.responded or 0 }}</span>
                    </a>
                    <a href="/?section=freelance&tab=trash&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'trash' %}active border-b-2 border-slate-500 text-slate-300 font-bold{% else %}text-slate-500 hover:text-slate-300{% endif %}">
                        <span>🗑</span> Отсеянные (Tier 3)
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">{{ stats.trash }}</span>
                    </a>
                    <a href="/?section=freelance&tab=analytics" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'analytics' %}active border-b-2 border-purple-500 text-purple-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>📊</span> Аналитика бирж
                    </a>
                    <a href="/?section=freelance&tab=rules" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'rules' %}active border-b-2 border-emerald-500 text-emerald-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>📋</span> Словарь фильтров
                    </a>
                    <a href="/?section=freelance&tab=health" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'health' %}active border-b-2 border-teal-500 text-teal-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>🩺</span> Статус бирж (Health)
                    </a>
                {% else %}
                    <!-- HH.ru Tabs -->
                    <a href="/?section=hh_ru&tab=hot" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'hot' %}active border-b-2 border-amber-500 text-amber-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>🔥</span> Топ совпадения (Score ≥ 7)
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono">{{ stats.hot }}</span>
                    </a>
                    <a href="/?section=hh_ru&tab=all" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'all' %}active border-b-2 border-blue-500 text-blue-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>⚡</span> Все вакансии
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-mono">{{ stats.hot + stats.normal }}</span>
                    </a>
                    <a href="/?section=hh_ru&tab=normal" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'normal' %}active border-b-2 border-blue-500 text-blue-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>🎯</span> Потенциальные (Score 4-6)
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">{{ stats.normal }}</span>
                    </a>
                    <a href="/?section=hh_ru&tab=responded&source={{ selected_source }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'responded' %}active border-b-2 border-emerald-500 text-emerald-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}" title="Вакансии, на которые вы уже откликнулись">
                        <span>✅</span> Отклики
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono">{{ stats.responded or 0 }}</span>
                    </a>
                    <a href="/?section=hh_ru&tab=trash" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'trash' %}active border-b-2 border-slate-500 text-slate-300 font-bold{% else %}text-slate-500 hover:text-slate-300{% endif %}">
                        <span>🗑</span> Отсеянные фильтрами
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">{{ stats.trash }}</span>
                    </a>
                    <a href="/?section=hh_ru&tab=analytics" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'analytics' %}active border-b-2 border-purple-500 text-purple-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>📊</span> Аналитика вакансий
                    </a>
                    <a href="/?section=hh_ru&tab=profile" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'profile' %}active border-b-2 border-rose-500 text-rose-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>👤</span> Профиль поиска & Стек
                    </a>
                    <a href="/?section=hh_ru&tab=health" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'health' %}active border-b-2 border-teal-500 text-teal-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                        <span>🩺</span> Статус бирж (Health)
                    </a>
                {% endif %}
            </nav>
        </div>
        {% endif %}

        {% if active_tab in ['hot', 'all', 'normal', 'trash', 'responded', 'skipped'] %}
        <!-- URL Quick Lookup & Import Bar -->
        <div class="bg-gradient-to-r from-blue-950/40 via-slate-900 to-indigo-950/40 border border-blue-900/50 p-3 sm:p-3.5 rounded-xl flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shadow-sm">
            <div class="flex items-center gap-2 text-xs font-semibold text-blue-300 whitespace-nowrap pl-1">
                <span>🔗</span>
                <span>Импорт / Поиск ссылки:</span>
            </div>
            <div class="relative flex-1">
                <input type="url" id="importOrderUrl" onkeydown="if(event.key==='Enter') lookupOrImportOrder()" placeholder="Вставьте ссылку на заказ или вакансию (hh.ru, kwork.ru, fl.ru, freelance.ru, pchel.net, habr.com...)" class="w-full bg-slate-950 border border-slate-700/80 text-slate-100 text-xs rounded-lg px-3 py-2 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition placeholder-slate-500 font-mono">
            </div>
            <button id="importOrderBtn" type="button" onclick="lookupOrImportOrder()" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 shadow-md shadow-blue-600/30 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed">
                <span>⚡</span>
                <span id="importBtnLabel">Найти или Анализировать</span>
            </button>
        </div>

        <!-- Advanced Filter & Control Bar -->
        <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3">
            <!-- Row 1: Search box & Sort & Quick Toggle -->
            <div class="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
                <!-- Live Search Box -->
                <div class="relative flex-1">
                    <span class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 text-sm">🔍</span>
                    <input type="text" id="orderSearch" oninput="applyClientFilters()" placeholder="{% if active_section == 'hh_ru' %}Живой поиск по компании, вакансии, стеку, навыкам, городу...{% else %}Живой поиск по заголовку, технологиям, стеку, сути...{% endif %}" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-sm rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-blue-500 placeholder-slate-500 transition">
                </div>

                <!-- Sort Dropdown -->
                <div class="flex items-center gap-2">
                    <label for="orderSortSelect" class="text-xs text-slate-400 font-semibold whitespace-nowrap">Сортировка:</label>
                    <select id="orderSortSelect" onchange="applyClientFilters()" class="bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2 focus:border-blue-500 outline-none">
                        <option value="default">По дате (сначала новые)</option>
                        <option value="score_desc">По оценке (Score: 10 → 1)</option>
                        <option value="price_desc">По цене/з-п (сначала дорогие)</option>
                        <option value="price_asc">По цене/з-п (сначала доступные)</option>
                    </select>
                </div>

                {% if active_section == 'freelance' %}
                <!-- Free / PRO Filter Toggle -->
                <div>
                    <a href="/?section=freelance&tab={{ active_tab }}&source={{ selected_source }}&free_only={% if free_only %}0{% else %}1{% endif %}" class="px-3.5 py-2 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 {% if free_only %}bg-emerald-600 text-white shadow-md{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700{% endif %}">
                        {% if free_only %}
                            <span>✅</span> Только бесплатные отклики
                        {% else %}
                            <span>🔓</span> Все отклики (включая PRO)
                        {% endif %}
                    </a>
                </div>
                {% endif %}
            </div>

            <!-- Row 2: Price Range & Topic Chips -->
            <div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
                <!-- Topic Filter Chips -->
                <div class="flex items-center space-x-1.5 overflow-x-auto custom-scroll py-1" id="topicChipsContainer">
                    <span class="text-xs text-slate-400 font-semibold uppercase mr-1">Тематика:</span>
                    {% if active_section == 'freelance' %}
                        <button type="button" onclick="setTopicFilter('all', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-blue-600 text-white font-bold">Все</button>
                        <button type="button" onclick="setTopicFilter('ai-first', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-purple-950 text-purple-300 border border-purple-700/60 hover:bg-purple-900/60 font-semibold">🚀 AI-First</button>
                        <button type="button" onclick="setTopicFilter('бот', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🤖 Боты & TG</button>
                        <button type="button" onclick="setTopicFilter('парсер', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🕷 Парсинг</button>
                        <button type="button" onclick="setTopicFilter('ai', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🧠 ИИ & LLM</button>
                        <button type="button" onclick="setTopicFilter('fastapi', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">⚙️ Бэкенд</button>
                        <button type="button" onclick="setTopicFilter('битрикс', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🔗 CRM</button>
                    {% else %}
                        <button type="button" onclick="setTopicFilter('all', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-rose-600 text-white font-bold">Все</button>
                        <button type="button" onclick="setTopicFilter('ai-first', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-purple-950 text-purple-300 border border-purple-700/60 hover:bg-purple-900/60 font-semibold">🚀 AI-First</button>
                        <button type="button" onclick="setTopicFilter('ai', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🧠 AI & LLM</button>
                        <button type="button" onclick="setTopicFilter('python', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🐍 Python</button>
                        <button type="button" onclick="setTopicFilter('ml', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">📊 ML & Data</button>
                        <button type="button" onclick="setTopicFilter('удален', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🏠 Удаленка</button>
                    {% endif %}
                </div>

                <!-- Price Range Filter Inputs -->
                <div class="flex items-center gap-2 text-xs flex-wrap">
                    <span class="text-slate-400 font-semibold uppercase">{% if active_section == 'hh_ru' %}З/П от:{% else %}Бюджет от:{% endif %}</span>
                    <input type="number" id="filterPriceMin" oninput="applyClientFilters()" placeholder="0 ₽" class="w-24 bg-slate-950 border border-slate-800 text-slate-200 rounded px-2.5 py-1 text-xs outline-none focus:border-blue-500 font-mono">
                    <span class="text-slate-500">до</span>
                    <input type="number" id="filterPriceMax" oninput="applyClientFilters()" placeholder="макс" class="w-24 bg-slate-950 border border-slate-800 text-slate-200 rounded px-2.5 py-1 text-xs outline-none focus:border-blue-500 font-mono">
                    <button type="button" onclick="resetFilters()" class="text-[11px] text-slate-400 hover:text-white px-2 py-1 bg-slate-800 rounded border border-slate-700 transition">Сброс</button>

                    <label class="flex items-center gap-1.5 cursor-pointer text-xs text-slate-300 hover:text-white select-none bg-slate-950 border border-slate-800 hover:border-slate-700 px-2.5 py-1 rounded transition ml-1" title="Скрывать заказы и вакансии, на которые уже отправлен отклик">
                        <input type="checkbox" id="filterHideResponded" onchange="applyClientFilters()" class="w-3.5 h-3.5 rounded bg-slate-900 border-slate-700 text-emerald-500 focus:ring-0 cursor-pointer">
                        <span class="flex items-center gap-1"><span>🙈</span> Скрывать отклики</span>
                    </label>

                    <label class="flex items-center gap-1.5 cursor-pointer text-xs text-slate-300 hover:text-white select-none bg-slate-950 border border-slate-800 hover:border-slate-700 px-2.5 py-1 rounded transition ml-1" title="Показывать пропущенные (скипнутые) заказы и вакансии">
                        <input type="checkbox" id="filterShowSkipped" onchange="applyClientFilters()" class="w-3.5 h-3.5 rounded bg-slate-900 border-slate-700 text-rose-500 focus:ring-0 cursor-pointer">
                        <span class="flex items-center gap-1"><span>⏭️</span> Показать скип</span>
                    </label>
                </div>
            </div>

            <!-- Row 3: Platform Filter Row & Match Count -->
            <div class="flex items-center space-x-1.5 overflow-x-auto custom-scroll pt-2 border-t border-slate-800/80">
                <span class="text-xs text-slate-400 font-semibold uppercase mr-1">Площадка:</span>
                {% if active_section == 'freelance' %}
                    <a href="/?section=freelance&tab={{ active_tab }}&source=&free_only={{ free_only }}" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if not selected_source %}bg-blue-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">Все</a>
                    <a href="/?section=freelance&tab={{ active_tab }}&source=kwork&free_only={{ free_only }}" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if selected_source == 'kwork' %}bg-emerald-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">Kwork</a>
                    <a href="/?section=freelance&tab={{ active_tab }}&source=fl_ru&free_only={{ free_only }}" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if selected_source == 'fl_ru' %}bg-blue-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">FL.ru</a>
                    <a href="/?section=freelance&tab={{ active_tab }}&source=freelance_ru&free_only={{ free_only }}" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if selected_source == 'freelance_ru' %}bg-purple-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">Freelance.ru</a>
                    <a href="/?section=freelance&tab={{ active_tab }}&source=pchel_net&free_only={{ free_only }}" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if selected_source == 'pchel_net' %}bg-amber-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">Pchel.net</a>
                {% else %}
                    <a href="/?section=hh_ru&tab={{ active_tab }}&source=" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if not selected_source %}bg-rose-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">Все вакансии</a>
                    <a href="/?section=hh_ru&tab={{ active_tab }}&source=hh_ru" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if selected_source == 'hh_ru' %}bg-rose-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">HeadHunter (hh.ru)</a>
                    <a href="/?section=hh_ru&tab={{ active_tab }}&source=habr_career" class="px-3 py-1 rounded-lg text-xs font-medium transition {% if selected_source == 'habr_career' %}bg-cyan-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">Хабр Карьера</a>
                {% endif %}
                <span id="filterCountBadge" class="ml-auto text-xs text-slate-400 font-mono"></span>
            </div>
        </div>

        <!-- Orders & Vacancies Feed List -->
        <div id="ordersContainer" class="space-y-4">
            {% if not orders %}
                <div class="bg-slate-900 border border-slate-800 p-12 text-center rounded-xl text-slate-400">
                    <p class="text-lg font-medium text-slate-300">
                        {% if active_section == 'hh_ru' %}Вакансии в этой категории пока не найдены{% else %}В этой категории заказы пока не найдены{% endif %}
                    </p>
                    <p class="text-xs mt-1">
                        {% if active_section == 'hh_ru' %}
                            Для сбора вакансий укажите HH_APP_TOKEN в .env (получите на dev.hh.ru).
                        {% else %}
                            Они появятся в реальном времени при следующем цикле опроса бирж.
                        {% endif %}
                    </p>
                </div>
            {% endif %}

            {% for order in orders %}
                <div id="order-{{ order.id }}" class="order-card bg-slate-900 border {% if order.priority == 'hot' %}border-amber-500/50 shadow-lg shadow-amber-950/20{% elif order.priority == 'trash' %}border-slate-800 opacity-60{% else %}border-slate-800{% endif %} {% if order.is_responded %}opacity-65 border-dashed{% endif %} {% if order.is_skipped %}opacity-45 border-rose-950/40{% endif %} p-5 rounded-xl transition hover:border-slate-700 space-y-3.5" data-id="{{ order.id }}" data-ai-first="{{ 1 if order.is_ai_first else 0 }}" data-title="{{ order.title|lower }}" data-desc="{{ order.description|lower }} {{ order.attachments_text|lower if order.attachments_text else '' }}" data-price="{{ order.price or 0 }}" data-score="{{ order.score or 0 }}" data-responded="{{ 1 if order.is_responded else 0 }}" data-skipped="{{ 1 if order.is_skipped else 0 }}" data-created="{{ order.created_at or '' }}">

                    <!-- Card Header Row -->
                    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div class="flex items-center space-x-2 flex-wrap gap-y-1">
                            <!-- Platform Badge -->
                            <span class="text-xs font-bold uppercase px-2.5 py-1 rounded-md {% if order.source == 'hh_ru' %}bg-rose-950 text-rose-300 border border-rose-800/60{% elif order.source == 'habr_career' %}bg-cyan-950 text-cyan-300 border border-cyan-800/60{% elif order.source == 'kwork' %}bg-emerald-950 text-emerald-300 border border-emerald-800/60{% elif order.source == 'fl_ru' %}bg-blue-950 text-blue-300 border border-blue-800/60{% elif order.source == 'freelance_ru' %}bg-purple-950 text-purple-300 border border-purple-800/60{% elif order.source == 'pchel_net' %}bg-amber-950 text-amber-300 border border-amber-800/60{% else %}bg-cyan-950 text-cyan-300 border border-cyan-800/60{% endif %}">
                                {{ 'Хабр Карьера' if order.source == 'habr_career' else (order.source|upper) }}
                            </span>

                            <!-- Responded Status Toggle Button -->
                            <button type="button" onclick="toggleResponded('{{ order.id }}', this)" id="responded-btn-{{ order.id }}" class="responded-toggle-btn text-xs px-2.5 py-0.5 rounded-md transition flex items-center gap-1.5 border font-medium {% if order.is_responded %}bg-emerald-950/90 text-emerald-300 border-emerald-700/80 hover:bg-emerald-900/90{% else %}bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700{% endif %}" title="Отметить, что отклик уже отправлен">
                                <span class="responded-icon">{% if order.is_responded %}✅{% else %}⬜{% endif %}</span>
                                <span class="responded-text">{% if order.is_responded %}Откликнулся{% else %}Не откликнулся{% endif %}</span>
                            </button>

                            <!-- Skip / Ignore Button -->
                            <button type="button" onclick="toggleSkipped('{{ order.id }}', this)" id="skip-btn-{{ order.id }}" class="skip-toggle-btn text-xs px-2 py-0.5 rounded-md transition flex items-center gap-1 border font-medium {% if order.is_skipped %}bg-rose-950/90 text-rose-300 border-rose-700/80 hover:bg-rose-900/90{% else %}bg-slate-950 text-slate-400 border-slate-800 hover:text-rose-300 hover:border-slate-700{% endif %}" title="Пропустить этот заказ/вакансию (скрыть из активной ленты)">
                                <span class="skip-icon">{% if order.is_skipped %}↩️{% else %}⏭️{% endif %}</span>
                                <span class="skip-text">{% if order.is_skipped %}Вернуть{% else %}Скип{% endif %}</span>
                            </button>

                            {% if order.source not in ['hh_ru', 'habr_career'] %}
                                <!-- Paid vs Free Response Badge (Freelance only) -->
                                {% if order.is_pro_only %}
                                    <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-purple-950/80 text-purple-300 border border-purple-800/60 flex items-center gap-1" title="Требуется аккаунт PRO / платный отклик">
                                        ⭐ Только PRO
                                    </span>
                                {% else %}
                                    <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 flex items-center gap-1" title="Бесплатный отклик для всех">
                                        🔓 Для всех
                                    </span>
                                {% endif %}
                            {% endif %}

                            <!-- Priority & Score Badge -->
                            {% if order.priority == 'hot' %}
                                <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1 font-mono">
                                    🔥 HOT ({{ order.score or 8 }}/10)
                                </span>
                            {% elif order.priority == 'normal' %}
                                <span class="text-xs font-medium px-2 py-0.5 rounded-md bg-blue-950/60 text-blue-300 border border-blue-800/40 font-mono">
                                    ⚡ NORMAL ({{ order.score or '-' }}/10)
                                </span>
                            {% else %}
                                <span class="text-xs font-medium px-2 py-0.5 rounded-md bg-red-950/50 text-red-400 border border-red-900/40">
                                    🗑 REJECTED
                                </span>
                            {% endif %}

                            {% if order.matched_project %}
                                <span class="text-xs font-medium px-2 py-0.5 rounded-md bg-indigo-950 text-indigo-300 border border-indigo-800/60">
                                    🎯 Кейс: {{ order.matched_project }}
                                </span>
                            {% endif %}

                            {% if order.is_ai_first %}
                                <span class="text-xs font-bold uppercase px-2.5 py-0.5 rounded-md bg-purple-900/70 text-purple-200 border border-purple-500/80 flex items-center gap-1 shadow-sm font-mono tracking-wide" title="Приоритетное AI-First / Agentic направление">
                                    <span>🚀</span> AI-FIRST
                                </span>
                            {% endif %}

                            {% if order.price and order.price >= 1500 and order.price <= 9000 and order.source not in ['hh_ru', 'habr_career'] %}
                                <span class="text-xs font-bold uppercase px-2.5 py-0.5 rounded-md bg-amber-950/70 text-amber-300 border border-amber-600/60 flex items-center gap-1 font-mono tracking-wide" title="Быстрый микро-заказ (Quick Win)">
                                    <span>⚡</span> QUICK WIN
                                </span>
                            {% endif %}

                            <span class="text-xs text-slate-400 font-mono bg-slate-950/80 border border-slate-800 px-2 py-0.5 rounded-md flex items-center gap-1" title="Дата и время">
                                🕒 {{ order.created_at[:16].replace('T', ' ') if order.created_at else 'Только что' }}
                            </span>

                            {% if order.is_responded and order.responded_at %}
                                <span class="text-xs text-emerald-300 font-mono bg-emerald-950/80 border border-emerald-800/80 px-2 py-0.5 rounded-md flex items-center gap-1" title="Дата отправки отклика">
                                    🎯 Отклик: {{ order.responded_at[:16].replace('T', ' ') if order.responded_at else '' }}
                                </span>
                            {% endif %}
                        </div>

                        <!-- Price / Salary Pills -->
                        <div class="flex flex-wrap items-center gap-2">
                            {% if order.source in ['hh_ru', 'habr_career'] %}
                                <div class="flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 px-3 py-1 rounded-lg">
                                    <span class="text-xs text-slate-400 font-medium">💰 Зарплата:</span>
                                    {% if order.price %}
                                        <span class="text-sm font-bold text-emerald-400 font-mono">
                                            {{ "{:,.0f}".format(order.price).replace(",", " ") }} ₽
                                        </span>
                                    {% elif order.is_negotiable %}
                                        <span class="text-xs font-semibold text-blue-400">
                                            По договоренности
                                        </span>
                                    {% else %}
                                        <span class="text-xs font-medium text-slate-500">
                                            Не указана
                                        </span>
                                    {% endif %}
                                </div>
                            {% else %}
                                <!-- Client Budget -->
                                <div class="flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 px-3 py-1 rounded-lg">
                                    <span class="text-xs text-slate-400 font-medium">💰 Бюджет клиента:</span>
                                    {% if order.price %}
                                        <span class="text-sm font-bold text-emerald-400 font-mono">
                                            {{ "{:,.0f}".format(order.price).replace(",", " ") }} ₽
                                        </span>
                                    {% elif order.is_negotiable %}
                                        <span class="text-xs font-semibold text-blue-400">
                                            По договоренности
                                        </span>
                                    {% else %}
                                        <span class="text-xs font-medium text-slate-500">
                                            Не указан
                                        </span>
                                    {% endif %}
                                </div>

                                <!-- Market Price (Unanchored, by hours/complexity) -->
                                {% set mkt_price = order.market_price or (order.analysis.market_price if order.analysis else None) %}
                                <div id="market-price-pill-{{ order.id }}" class="flex items-center gap-1.5 {% if mkt_price and mkt_price > 0 %}bg-amber-950/40 border border-amber-800/60{% else %}bg-slate-950/60 border border-slate-800{% endif %} px-3 py-1 rounded-lg" title="Объективная рыночная стоимость без привязки к бюджету заказчика (по часам и сложности)">
                                    <span class="text-xs text-amber-400 font-medium">🎯 Рыночная:</span>
                                    <span class="text-sm font-bold text-amber-300 font-mono">
                                        {% if mkt_price and mkt_price > 0 %}
                                            {{ "{:,.0f}".format(mkt_price).replace(",", " ") }} ₽
                                        {% else %}
                                            <span class="text-xs text-slate-400 font-normal">-</span>
                                        {% endif %}
                                    </span>
                                </div>

                                <!-- Recommended Price (Tactical) -->
                                {% set rec_price = order.recommended_price or (order.analysis.recommended_price if order.analysis else None) %}
                                {% set has_prop = (order.proposal_text or (order.analysis and order.analysis.proposal_text)) %}
                                <div id="rec-price-pill-{{ order.id }}" class="flex items-center gap-1.5 {% if rec_price and rec_price > 0 %}bg-emerald-950/40 border border-emerald-800/60{% else %}bg-slate-950/60 border border-slate-800{% endif %} px-3 py-1 rounded-lg" title="{% if has_prop %}Рекомендуемая ставка отклика на основе поиска (agy){% else %}Тактическая рекомендуемая ставка Mistral с учетом бюджета клиента{% endif %}">
                                    <span class="text-xs text-emerald-400 font-medium">💡 Рекомендуемая:</span>
                                    <span class="text-sm font-bold text-emerald-300 font-mono">
                                        {% if rec_price and rec_price > 0 %}
                                            {{ "{:,.0f}".format(rec_price).replace(",", " ") }} ₽{% if not has_prop %}<span class="text-[10px] text-emerald-400/80 font-normal ml-0.5">(предв.)</span>{% endif %}
                                        {% else %}
                                            <span class="text-xs text-slate-400 font-normal">по кнопке (agy)</span>
                                        {% endif %}
                                    </span>
                                </div>
                            {% endif %}
                        </div>
                    </div>

                    <!-- Title & Link -->
                    <div>
                        <h2 class="text-base sm:text-lg font-semibold text-white leading-snug">
                            <a href="{{ order.url }}" target="_blank" class="hover:text-blue-400 transition inline-flex items-center gap-1.5">
                                {{ order.title }}
                                <span class="text-xs text-slate-500">↗</span>
                            </a>
                        </h2>
                    </div>

                    {% if order.source in ['hh_ru', 'habr_career'] and order.attachments_text %}
                        <!-- Vacancy Meta Highlights -->
                        <div class="text-xs bg-slate-950/80 border border-slate-800 p-2.5 rounded-lg text-slate-300 font-mono space-y-0.5">
                            {{ order.attachments_text.replace('\\n', '<br>')|safe }}
                        </div>
                    {% endif %}

                    <!-- Mistral AI Structured Breakdown for Vacancy or Project -->
                    {% if order.analysis %}
                        {% if order.source in ['hh_ru', 'habr_career'] %}
                            <!-- Dedicated HH Vacancy Breakdown Card -->
                            <div class="bg-slate-950/90 border border-rose-950/60 p-4 rounded-xl space-y-3">
                                <div class="text-xs font-bold uppercase tracking-wider text-rose-400 flex items-center gap-1.5 border-b border-slate-800 pb-2">
                                    <span>🤖</span> Анализ вакансии нейросетью Mistral под стек Андрея:
                                </div>

                                <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                                    <!-- Company Overview -->
                                    {% if order.analysis.company_overview %}
                                        <div class="bg-slate-900/80 border border-slate-800/80 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-slate-200 flex items-center gap-1.5">
                                                <span>🏢</span> О компании:
                                            </div>
                                            <div class="text-slate-300 leading-relaxed">{{ format_bullet_html(order.analysis.company_overview, 'slate') | safe }}</div>
                                        </div>
                                    {% endif %}

                                    <!-- Candidate Requirements -->
                                    {% if order.analysis.candidate_requirements %}
                                        <div class="bg-slate-900/80 border border-slate-800/80 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-slate-200 flex items-center gap-1.5">
                                                <span>🎯</span> Требования к кандидату:
                                            </div>
                                            <div class="text-slate-300 leading-relaxed">{{ format_bullet_html(order.analysis.candidate_requirements, 'rose') | safe }}</div>
                                        </div>
                                    {% endif %}

                                    <!-- Job Responsibilities -->
                                    {% if order.analysis.job_responsibilities %}
                                        <div class="bg-slate-900/80 border border-slate-800/80 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-slate-200 flex items-center gap-1.5">
                                                <span>🛠</span> Чем предстоит заниматься:
                                            </div>
                                            <div class="text-slate-300 leading-relaxed">{{ format_bullet_html(order.analysis.job_responsibilities, 'blue') | safe }}</div>
                                        </div>
                                    {% endif %}

                                    <!-- Andrei's Match Reason -->
                                    {% if order.analysis.match_reason %}
                                        <div class="bg-slate-900/80 border border-emerald-900/40 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-emerald-300 flex items-center gap-1.5">
                                                <span>💡</span> Соответствие резюме Андрея:
                                            </div>
                                            <div class="text-emerald-200 leading-relaxed">{{ format_bullet_html(order.analysis.match_reason, 'emerald') | safe }}</div>
                                        </div>
                                    {% endif %}

                                    <!-- Skills Gap & Counter Strategy -->
                                    {% if order.analysis.skills_gap and order.analysis.skills_gap != "Критичных пробелов нет" %}
                                        <div class="col-span-1 md:col-span-2 bg-slate-900/90 border border-amber-900/50 p-3 rounded-lg space-y-1.5">
                                            <div class="font-bold text-amber-400 flex items-center gap-1.5">
                                                <span>⚠️</span> Пробелы в требованиях (Skills Gap):
                                            </div>
                                            <div class="text-amber-200 text-xs leading-relaxed font-mono bg-amber-950/40 p-2 rounded border border-amber-900/40">{{ format_bullet_html(order.analysis.skills_gap, 'amber') | safe }}</div>
                                            {% if order.analysis.skills_gap_counter %}
                                                <div class="text-[11px] text-slate-300 pt-1 flex items-start gap-1.5">
                                                    <span class="font-semibold text-emerald-400 shrink-0">🛡 Парирование в Cover Letter:</span>
                                                    <div class="text-slate-200">{{ format_bullet_html(order.analysis.skills_gap_counter, 'emerald') | safe }}</div>
                                                </div>
                                            {% endif %}
                                        </div>
                                    {% elif order.analysis.skills_gap == "Критичных пробелов нет" %}
                                        <div class="col-span-1 md:col-span-2 bg-emerald-950/30 border border-emerald-900/40 p-2.5 rounded-lg text-emerald-300 text-xs flex items-center gap-2">
                                            <span>✅</span>
                                            <span><b>Полное соответствие:</b> Критичных пробелов в стеке не выявлено.</span>
                                        </div>
                                    {% endif %}
                                </div>

                                {% if order.analysis.risks_and_pitfalls %}
                                    <div class="text-xs bg-slate-900/80 border border-amber-900/40 p-3 rounded-lg space-y-1">
                                        <div class="font-bold text-amber-400 flex items-center gap-1.5">
                                            <span>⚠️</span> Подводные камни и риски:
                                        </div>
                                        <ul class="text-slate-300 space-y-0.5 list-disc list-inside">
                                            {% for risk in order.analysis.risks_and_pitfalls %}
                                                <li>{{ risk }}</li>
                                            {% endfor %}
                                        </ul>
                                    </div>
                                {% endif %}

                                <!-- Cover Letter Box (on demand) -->
                                {% set is_hh = order.source == 'hh_ru' %}
                                <div id="proposal-box-{{ order.id }}">
                                    {% if order.proposal_text or (order.analysis and order.analysis.proposal_text) %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 space-y-2">
                                            <div class="flex flex-wrap items-center justify-between gap-2">
                                                <span class="text-xs font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                                                    <span>✉️</span> Сгенерированное Cover Letter (agy):
                                                </span>
                                                <div class="flex flex-wrap items-center gap-2">
                                                    <button type="button" onclick="generateProposal('{{ order.id }}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition active:scale-95 cursor-pointer">
                                                        🔄 Перегенерировать
                                                    </button>
                                                    {% if is_hh %}
                                                        {% if order.is_responded %}
                                                            <span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default">
                                                                <span>✅</span> Отклик отправлен
                                                            </span>
                                                        {% else %}
                                                            <button type="button" onclick="applyVacancyHH('{{ order.id }}', this)" class="apply-hh-btn text-xs bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm cursor-pointer select-none">
                                                                <span>🚀</span> Откликнуться на HH
                                                            </button>
                                                        {% endif %}
                                                    {% endif %}
                                                    <button type="button" onclick="copyProposal('proposal-text-{{ order.id }}', this)" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium px-3 py-1 rounded-md transition flex items-center gap-1 border border-slate-700 active:scale-95 cursor-pointer select-none">
                                                        <span>📋</span> Скопировать Cover Letter
                                                    </button>
                                                </div>
                                            </div>
                                            <div id="proposal-text-{{ order.id }}" onclick="copyProposalText(this)" title="Нажмите, чтобы скопировать текст в буфер обмена" class="text-xs font-mono bg-slate-900/90 hover:bg-slate-900 text-slate-200 p-3.5 rounded-lg border border-slate-800 hover:border-slate-600 whitespace-pre-wrap leading-relaxed select-text cursor-pointer transition">
{{ order.proposal_text or order.analysis.proposal_text }}</div>
                                        </div>
                                    {% else %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2">
                                            <span class="text-xs text-slate-400">Сопроводительное письмо генерируется под конкретную вакансию.</span>
                                            <div class="flex flex-wrap items-center gap-2">
                                                {% if is_hh %}
                                                    {% if order.is_responded %}
                                                        <span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default">
                                                            <span>✅</span> Отклик отправлен
                                                        </span>
                                                    {% else %}
                                                        <button type="button" onclick="applyVacancyHH('{{ order.id }}', this)" class="apply-hh-btn text-xs bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-medium px-3.5 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-sm cursor-pointer select-none">
                                                            <span>🚀</span> Откликнуться на HH
                                                        </button>
                                                    {% endif %}
                                                {% endif %}
                                                <button type="button" onclick="generateProposal('{{ order.id }}', this)" class="text-xs bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 active:scale-95 text-white font-semibold px-4 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-md cursor-pointer select-none">
                                                    <span>✨</span> Сгенерировать Cover Letter (agy)
                                                </button>
                                            </div>
                                        </div>
                                    {% endif %}
                                </div>
                            </div>
                        {% else %}
                            <!-- Standard Freelance Order LLM Box -->
                            {% if order.analysis.executive_summary %}
                                <div class="text-xs bg-slate-950/80 border border-blue-900/40 p-2.5 rounded-lg text-blue-200 flex items-start gap-2">
                                    <span class="text-blue-400 mt-0.5">📝</span>
                                    <div>
                                        <strong class="text-blue-300 font-semibold uppercase text-[10px] tracking-wider block mb-0.5">Краткая суть задачи (ИИ):</strong>
                                        <span>{{ order.analysis.executive_summary }}</span>
                                    </div>
                                </div>
                            {% endif %}

                            <div class="bg-slate-950 border border-slate-800 p-4 rounded-xl space-y-3">
                                <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
                                    <div class="flex items-center space-x-3 text-slate-400">
                                        {% if order.analysis.complexity %}
                                            <span>⚙️ Сложность: <strong class="text-slate-200">{{ order.analysis.complexity }}/10</strong></span>
                                        {% endif %}
                                        {% if order.analysis.pure_dev_hours %}
                                            <span>⏱ Чистая разработка: <strong class="text-slate-200">{{ order.analysis.pure_dev_hours }} ч</strong></span>
                                        {% endif %}
                                        {% if order.analysis.realistic_days %}
                                            <span>📅 Срок: <strong class="text-slate-200">{{ order.analysis.realistic_days }} дн</strong></span>
                                        {% endif %}
                                    </div>

                                    {% if order.analysis.pert %}
                                        <div class="text-xs font-mono bg-slate-900 px-2.5 py-1 rounded border border-slate-800 text-amber-300" title="PERT: E = (O + 4M + P)/6">
                                            PERT E = {{ order.analysis.pert.expected_days }} дн (±{{ order.analysis.pert.sigma }}σ)
                                        </div>
                                    {% endif %}
                                </div>

                                <!-- Financial Evaluation and Price Strategy Box -->
                                {% if order.analysis.recommended_price or order.analysis.market_price or order.analysis.price_justification %}
                                    {% set has_agy_prop = (order.proposal_text or (order.analysis and order.analysis.proposal_text)) %}
                                    <div class="text-xs bg-slate-900/80 border border-amber-900/40 p-2.5 rounded-lg text-slate-300 space-y-1.5">
                                        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-1.5">
                                            <span class="text-amber-400 font-semibold uppercase text-[10px] tracking-wider flex items-center gap-1">
                                                <span>🎯</span> Финансовая оценка и стратегия ставок {% if has_agy_prop %}(agy с веб-поиском):{% else %}(анализ Mistral):{% endif %}
                                            </span>
                                            <div class="flex items-center gap-3 font-mono text-xs">
                                                {% if order.analysis.market_price %}
                                                    <span class="text-amber-300">
                                                        🎯 Рыночная: <b>{{ "{:,.0f}".format(order.analysis.market_price).replace(",", " ") }} ₽</b>
                                                    </span>
                                                {% endif %}
                                                {% if order.analysis.recommended_price %}
                                                    <span class="text-emerald-300">
                                                        💡 Рекомендуемая: <b>{{ "{:,.0f}".format(order.analysis.recommended_price).replace(",", " ") }} ₽</b>
                                                    </span>
                                                {% endif %}
                                            </div>
                                        </div>
                                        {% if order.analysis.price_justification %}
                                            <p class="text-slate-300 text-[11px] leading-relaxed">
                                                {{ order.analysis.price_justification }}
                                            </p>
                                        {% endif %}
                                    </div>
                                {% endif %}

                                {% if order.analysis.risks_and_pitfalls %}
                                    <div class="space-y-1">
                                        <span class="text-xs font-semibold text-amber-400 uppercase tracking-wider">⚠️ Риски и нюансы:</span>
                                        <ul class="text-xs text-slate-300 space-y-1 list-disc list-inside">
                                            {% for risk in order.analysis.risks_and_pitfalls %}
                                                <li>{{ risk }}</li>
                                            {% endfor %}
                                        </ul>
                                    </div>
                                {% endif %}

                                <!-- Proposal Container (Pre-generated or On-demand) -->
                                <div id="proposal-box-{{ order.id }}">
                                    {% if order.proposal_text or (order.analysis and order.analysis.proposal_text) %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 space-y-2">
                                            <div class="flex items-center justify-between">
                                                <span class="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                                                    <span>✍️</span> Сгенерированный отклик:
                                                </span>
                                                <div class="flex items-center space-x-2">
                                                    <button type="button" onclick="generateProposal('{{ order.id }}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition active:scale-95 cursor-pointer">
                                                        🔄 Перегенерировать
                                                    </button>
                                                    <button type="button" onclick="copyProposal('proposal-text-{{ order.id }}', this)" class="text-xs bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm cursor-pointer select-none">
                                                        <span>📋</span> Скопировать отклик
                                                    </button>
                                                </div>
                                            </div>
                                            <div id="proposal-text-{{ order.id }}" onclick="copyProposalText(this)" title="Нажмите, чтобы скопировать текст в буфер обмена" class="text-xs font-mono bg-slate-900/90 hover:bg-slate-900 text-slate-200 p-3.5 rounded-lg border border-slate-800 hover:border-slate-600 whitespace-pre-wrap leading-relaxed select-text cursor-pointer transition">
{{ order.proposal_text or order.analysis.proposal_text }}</div>
                                        </div>
                                    {% else %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 flex items-center justify-between">
                                            <span class="text-xs text-slate-400">Отклик не генерировался для экономии квот.</span>
                                            <button type="button" onclick="generateProposal('{{ order.id }}', this)" class="text-xs bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 active:scale-95 text-white font-semibold px-4 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-md cursor-pointer select-none">
                                                <span>✨</span> Сгенерировать отклик (ИИ)
                                            </button>
                                        </div>
                                    {% endif %}
                                </div>
                            </div>
                        {% endif %}
                    {% else %}
                        <!-- Order without initial analysis: proposal generation on demand -->
                        {% set is_vac = order.source in ['hh_ru', 'habr_career'] %}
                        {% set is_hh = order.source == 'hh_ru' %}
                        <div id="proposal-box-{{ order.id }}">
                            {% if order.proposal_text %}
                                <div class="mt-3 pt-3 border-t border-slate-800 space-y-2">
                                    <div class="flex flex-wrap items-center justify-between gap-2">
                                        <span class="text-xs font-semibold {% if is_vac %}text-rose-400{% else %}text-emerald-400{% endif %} uppercase tracking-wider flex items-center gap-1">
                                            <span>{% if is_vac %}✉️{% else %}✍️{% endif %}</span> {% if is_vac %}Сгенерированное Cover Letter (agy):{% else %}Сгенерированный отклик:{% endif %}
                                        </span>
                                        <div class="flex flex-wrap items-center gap-2">
                                            <button type="button" onclick="generateProposal('{{ order.id }}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition active:scale-95 cursor-pointer">
                                                🔄 Перегенерировать
                                            </button>
                                            {% if is_hh %}
                                                {% if order.is_responded %}
                                                    <span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default">
                                                        <span>✅</span> Отклик отправлен
                                                    </span>
                                                {% else %}
                                                    <button type="button" onclick="applyVacancyHH('{{ order.id }}', this)" class="apply-hh-btn text-xs bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm cursor-pointer select-none">
                                                        <span>🚀</span> Откликнуться на HH
                                                    </button>
                                                {% endif %}
                                            {% endif %}
                                            <button type="button" onclick="copyProposal('proposal-text-{{ order.id }}', this)" class="text-xs {% if is_vac %}bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700{% else %}bg-emerald-600 hover:bg-emerald-500 text-white{% endif %} font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm active:scale-95 cursor-pointer select-none">
                                                <span>📋</span> {% if is_vac %}Скопировать Cover Letter{% else %}Скопировать отклик{% endif %}
                                            </button>
                                        </div>
                                    </div>
                                    <div id="proposal-text-{{ order.id }}" onclick="copyProposalText(this)" title="Нажмите, чтобы скопировать текст в буфер обмена" class="text-xs font-mono bg-slate-900/90 hover:bg-slate-900 text-slate-200 p-3.5 rounded-lg border border-slate-800 hover:border-slate-600 whitespace-pre-wrap leading-relaxed select-text cursor-pointer transition">
{{ order.proposal_text }}</div>
                                </div>
                            {% else %}
                                <div class="mt-3 pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2">
                                    <span class="text-xs text-slate-400">{% if is_vac %}Сопроводительное письмо генерируется под конкретную вакансию.{% else %}Отклик не генерировался для экономии квот.{% endif %}</span>
                                    <div class="flex flex-wrap items-center gap-2">
                                        {% if is_hh %}
                                            {% if order.is_responded %}
                                                <span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default">
                                                    <span>✅</span> Отклик отправлен
                                                </span>
                                            {% else %}
                                                <button type="button" onclick="applyVacancyHH('{{ order.id }}', this)" class="apply-hh-btn text-xs bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-medium px-3.5 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-sm cursor-pointer select-none">
                                                    <span>🚀</span> Откликнуться на HH
                                                </button>
                                            {% endif %}
                                        {% endif %}
                                        <button type="button" onclick="generateProposal('{{ order.id }}', this)" class="text-xs {% if is_vac %}bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500{% else %}bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500{% endif %} text-white font-semibold px-4 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-md active:scale-95 cursor-pointer select-none">
                                            <span>✨</span> {% if is_vac %}Сгенерировать Cover Letter (agy){% else %}Сгенерировать отклик (ИИ){% endif %}
                                        </button>
                                    </div>
                                </div>
                            {% endif %}
                        </div>
                    {% endif %}

                    <!-- Description / Text -->
                    <div class="text-sm text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                        <p class="whitespace-pre-line">{{ order.description }}</p>
                    </div>

                    <!-- If Rejected (Tier 3) -> Filter Reason -->
                    {% if order.priority == 'trash' and order.filter_reason %}
                        <div class="text-xs bg-red-950/30 border border-red-900/40 p-2.5 rounded-lg text-red-300 flex items-center gap-2">
                            <span>🚫</span>
                            <span><b>Причина отсева:</b> {{ order.filter_reason }}</span>
                        </div>
                    {% endif %}

                    <!-- Order Action Bar: Chat toggle -->
                    <div class="pt-2 flex items-center justify-between border-t border-slate-800/80">
                        <button type="button" onclick="toggleOrderChat('{{ order.id }}')" id="chat-toggle-btn-{{ order.id }}" class="text-xs bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700/60 px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-sm">
                            <span>💬</span>
                            <span>Вопрос по заказу</span>
                            {% if order.messages_count and order.messages_count > 0 %}
                                <span id="chat-badge-{{ order.id }}" class="bg-indigo-600 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold ml-0.5">{{ order.messages_count }}</span>
                            {% else %}
                                <span id="chat-badge-{{ order.id }}" class="hidden bg-indigo-600 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold ml-0.5">0</span>
                            {% endif %}
                        </button>
                        <span class="text-[11px] text-slate-500 font-mono">ID: {{ order.external_id }}</span>
                    </div>

                    <!-- Collapsible Chat Drawer -->
                    <div id="chat-container-{{ order.id }}" class="hidden bg-slate-950 border border-indigo-950/70 rounded-xl p-3.5 space-y-3 transition-all duration-200">
                        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
                            <div class="flex items-center gap-2">
                                <span class="text-xs font-bold text-slate-200 flex items-center gap-1">
                                    <span>💬</span> Вопрос по задаче
                                </span>
                                <span class="text-[10px] text-slate-400">(сохраняет историю и контекст)</span>
                            </div>
                            <div class="flex items-center gap-1.5 text-xs">
                                <label for="chat-model-{{ order.id }}" class="text-[11px] text-slate-400">Модель:</label>
                                <select id="chat-model-{{ order.id }}" class="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 focus:ring-1 focus:ring-indigo-500 outline-none">
                                    <option value="auto" selected>✨ Авто ({% if order.proposal_text %}agy{% else %}Mistral{% endif %})</option>
                                    <option value="mistral">Mistral (быстрый совет)</option>
                                    <option value="antigravity">Antigravity agy (глубокий анализ)</option>
                                </select>
                            </div>
                        </div>

                        <!-- Chat Message History -->
                        <div id="chat-messages-{{ order.id }}" class="space-y-2.5 max-h-80 overflow-y-auto pr-1 text-xs">
                            <div class="text-center py-3 text-slate-500 text-xs">
                                <span>Загрузка диалога...</span>
                            </div>
                        </div>

                        <!-- Quick suggestion chips -->
                        <div class="flex flex-wrap gap-1.5 pt-1">
                            <button type="button" onclick="setQuickChatPrompt('{{ order.id }}', 'Какие здесь скрытые риски и подводные камни?')" class="text-[10px] bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 px-2 py-1 rounded transition">
                                ⚠️ Скрытые риски?
                            </button>
                            <button type="button" onclick="setQuickChatPrompt('{{ order.id }}', 'Как аргументировать заказчику вилку стоимости?')" class="text-[10px] bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 px-2 py-1 rounded transition">
                                💰 Аргументация цены
                            </button>
                            <button type="button" onclick="setQuickChatPrompt('{{ order.id }}', 'Подойдет ли стек Андрея и сколько займет разработка?')" class="text-[10px] bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 px-2 py-1 rounded transition">
                                ⏱ Стек и сроки
                            </button>
                        </div>

                        <!-- Input Box -->
                        <div class="flex items-center gap-2 pt-1">
                            <input type="text" id="chat-input-{{ order.id }}" onkeydown="if(event.key==='Enter') sendOrderMessage('{{ order.id }}')" placeholder="Задай вопрос модели по этой задаче..." class="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                            <button type="button" onclick="sendOrderMessage('{{ order.id }}')" id="chat-send-btn-{{ order.id }}" class="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-4 py-2 rounded-lg text-xs transition flex items-center gap-1 shrink-0 shadow-sm">
                                <span>Спросить</span>
                            </button>
                        </div>
                    </div>
                </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if active_tab == 'analytics' %}
        <!-- Analytics View -->
        <div class="space-y-6">
            <!-- Header Banner -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                    <h2 class="text-xl font-bold text-white flex items-center gap-2">
                        <span>📊</span>
                        {% if active_section == 'hh_ru' %}
                            Аналитика воронки вакансий (HeadHunter)
                        {% else %}
                            Аналитика воронки фриланс-бирж
                        {% endif %}
                    </h2>
                    <p class="text-xs text-slate-400 mt-1">
                        Динамика откликов, конверсия Hot-лидов, скорость реакции и ключевые компетенции
                    </p>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-xs px-3 py-1 rounded-lg bg-slate-950 border border-slate-800 text-slate-400 font-mono">
                        Раздел: <b class="text-slate-200">{% if active_section == 'hh_ru' %}HeadHunter / Вакансии{% else %}Фриланс-биржи{% endif %}</b>
                    </span>
                </div>
            </div>

            <!-- KPI Cards Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <!-- Card 1: Responses by Period -->
                <div class="bg-slate-900 border border-emerald-950/60 p-5 rounded-xl space-y-2 relative overflow-hidden">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Отклики</span>
                        <span class="text-base">🎯</span>
                    </div>
                    <div class="flex items-baseline gap-2">
                        <span class="text-2xl font-bold font-mono text-emerald-400">{{ section_analytics.resp_total if section_analytics else 0 }}</span>
                        <span class="text-xs text-slate-400">всего</span>
                    </div>
                    <div class="text-xs font-mono text-slate-400 pt-2 border-t border-slate-800 flex justify-between">
                        <span>Сегодня: <b class="text-white">{{ section_analytics.resp_today if section_analytics else 0 }}</b></span>
                        <span>7 дн: <b class="text-white">{{ section_analytics.resp_7d if section_analytics else 0 }}</b></span>
                        <span>30 дн: <b class="text-white">{{ section_analytics.resp_30d if section_analytics else 0 }}</b></span>
                    </div>
                </div>

                <!-- Card 2: Hot Conversion -->
                <div class="bg-slate-900 border border-amber-950/60 p-5 rounded-xl space-y-2 relative overflow-hidden">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Конверсия Hot</span>
                        <span class="text-base">🔥</span>
                    </div>
                    <div class="flex items-baseline gap-2">
                        <span class="text-2xl font-bold font-mono text-amber-400">{{ section_analytics.hot_conversion if section_analytics else 0 }}%</span>
                        <span class="text-xs text-slate-400">в отклик</span>
                    </div>
                    <div class="text-xs font-mono text-slate-400 pt-2 border-t border-slate-800">
                        Откликнулись на <b>{{ section_analytics.hot_responded if section_analytics else 0 }}</b> из <b>{{ section_analytics.hot_total if section_analytics else 0 }}</b> Hot-лидов
                    </div>
                </div>

                <!-- Card 3: Response Velocity -->
                <div class="bg-slate-900 border border-blue-950/60 p-5 rounded-xl space-y-2 relative overflow-hidden">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Скорость реакции</span>
                        <span class="text-base">⏱️</span>
                    </div>
                    <div class="flex items-baseline gap-2">
                        <span class="text-2xl font-bold font-mono text-blue-400">{{ section_analytics.response_velocity if section_analytics else 'Нет данных' }}</span>
                    </div>
                    <div class="text-xs font-mono text-slate-400 pt-2 border-t border-slate-800">
                        Среднее время от сбора до отклика
                    </div>
                </div>

                <!-- Card 4: Pipeline Money / Skipped -->
                <div class="bg-slate-900 border border-purple-950/60 p-5 rounded-xl space-y-2 relative overflow-hidden">
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                            {% if active_section == 'hh_ru' %}Вилка з/п в откликах{% else %}Пайплайн в откликах{% endif %}
                        </span>
                        <span class="text-base">💰</span>
                    </div>
                    <div class="flex items-baseline gap-2">
                        <span class="text-2xl font-bold font-mono text-purple-400">
                            {% if section_analytics and section_analytics.total_pipeline_rub > 0 %}
                                {{ "{:,}".format(section_analytics.total_pipeline_rub).replace(',', ' ') }} ₽
                            {% else %}
                                По договоренности
                            {% endif %}
                        </span>
                    </div>
                    <div class="text-xs font-mono text-slate-400 pt-2 border-t border-slate-800 flex justify-between">
                        <span>Средний чек: <b>{{ "{:,}".format(section_analytics.avg_resp_rub if section_analytics else 0).replace(',', ' ') }} ₽</b></span>
                        <span title="Скипнуто">Скип: <b class="text-rose-400">{{ section_analytics.skipped_total if section_analytics else 0 }}</b></span>
                    </div>
                </div>
            </div>

            <!-- Top Technologies & Skills Breakdown -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- User Target Skills in Hot Leads -->
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                    <div class="flex items-center justify-between">
                        <h3 class="text-sm font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-2">
                            <span>🎯</span> Ваши целевые навыки (в Hot-лидах)
                        </h3>
                        <span class="text-xs text-slate-400 font-mono">Стек под профиль</span>
                    </div>
                    {% if section_analytics and section_analytics.top_skills %}
                        <div class="flex flex-wrap gap-2">
                            {% for skill in section_analytics.top_skills %}
                                <div class="flex items-center gap-1.5 bg-slate-950 border border-slate-800 hover:border-emerald-600/60 px-3 py-1.5 rounded-lg transition group">
                                    <span class="text-xs font-medium text-slate-200 group-hover:text-emerald-300">{{ skill.name }}</span>
                                    <span class="text-xs font-mono px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 font-bold border border-emerald-900/60">{{ skill.count }} ({{ skill.pct }}%)</span>
                                </div>
                            {% endfor %}
                        </div>
                    {% else %}
                        <p class="text-xs text-slate-500 italic">Пока недостаточно Hot-лидов для выделения навыков.</p>
                    {% endif %}
                </div>

                <!-- Broad Market-wide Demand -->
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                    <div class="flex items-center justify-between">
                        <h3 class="text-sm font-bold text-blue-400 uppercase tracking-wider flex items-center gap-2">
                            <span>🌐</span> Общерыночный спрос (все заказы и вакансии)
                        </h3>
                        <span class="text-xs text-slate-400 font-mono">Срез всего рынка</span>
                    </div>
                    {% if section_analytics and section_analytics.market_skills %}
                        <div class="flex flex-wrap gap-2">
                            {% for skill in section_analytics.market_skills %}
                                <div class="flex items-center gap-1.5 bg-slate-950 border border-slate-800 hover:border-blue-600/60 px-3 py-1.5 rounded-lg transition group">
                                    <span class="text-xs font-medium text-slate-200 group-hover:text-blue-300">{{ skill.name }}</span>
                                    <span class="text-xs font-mono px-1.5 py-0.5 rounded bg-blue-950/80 text-blue-300 font-bold border border-blue-900/60">{{ skill.count }} ({{ skill.pct }}%)</span>
                                </div>
                            {% endfor %}
                        </div>
                    {% else %}
                        <p class="text-xs text-slate-500 italic">Пока недостаточно данных для анализа рынка.</p>
                    {% endif %}
                </div>
            </div>

            <!-- Platform / Sources Table Breakdown -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>📋</span> Детализация по площадкам раздела
                </h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm text-slate-300">
                        <thead class="bg-slate-950 text-slate-400 text-xs uppercase border-b border-slate-800">
                            <tr>
                                <th class="p-3">Площадка</th>
                                <th class="p-3">Всего</th>
                                <th class="p-3">🔥 Hot (Tier 1)</th>
                                <th class="p-3">⚡ Normal (Tier 2)</th>
                                <th class="p-3">🗑 Trash (Tier 3)</th>
                                <th class="p-3">🎯 Откликов</th>
                                <th class="p-3">⏭️ Скипнуто</th>
                                <th class="p-3">Конверсия в Hot</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800">
                            {% set source_list = extended_stats.by_source_vacancies if active_section == 'hh_ru' else extended_stats.by_source_freelance %}
                            {% for item in source_list %}
                                <tr class="hover:bg-slate-800/40 transition">
                                    <td class="p-3 font-semibold uppercase text-slate-200">
                                        {{ 'Хабр Карьера' if item.source == 'habr_career' else ('HeadHunter' if item.source == 'hh_ru' else item.source|upper) }}
                                    </td>
                                    <td class="p-3 font-mono font-bold">{{ item.total }}</td>
                                    <td class="p-3 font-mono text-amber-400 font-bold">{{ item.hot }}</td>
                                    <td class="p-3 font-mono text-blue-400">{{ item.normal }}</td>
                                    <td class="p-3 font-mono text-slate-500">{{ item.trash }}</td>
                                    <td class="p-3 font-mono text-emerald-400 font-bold">{{ item.responded or 0 }}</td>
                                    <td class="p-3 font-mono text-rose-400">{{ item.skipped or 0 }}</td>
                                    <td class="p-3 font-mono">
                                        {% if item.total > 0 %}
                                            {{ "{:.1f}%".format((item.hot / item.total) * 100) }}
                                        {% else %}0%{% endif %}
                                    </td>
                                </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        {% endif %}

        {% if active_tab == 'rules' %}
        <!-- Rules & Filters Interactive Manager -->
        <div class="space-y-6">
            <!-- Header Bar with Action Controls -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900 border border-slate-800 p-5 rounded-xl shadow-sm">
                <div>
                    <h2 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🛠</span> Интерактивное управление правилами и фильтрами
                    </h2>
                    <p class="text-xs text-slate-400 mt-1">
                        Добавляйте и удаляйте ключевые слова, стоп-слова и исключения должностей. Изменения сохраняются в базе и сразу применяются к воркерам.
                    </p>
                </div>
                <div class="flex items-center gap-2 flex-wrap">
                    <button type="button" onclick="saveCustomRules()" id="saveRulesBtn" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow-md shadow-emerald-950/40">
                        <span>💾</span> Сохранить фильтры
                    </button>
                    <button type="button" onclick="resetRulesToDefault()" class="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition border border-slate-700">
                        <span>↺</span> Сбросить к config.yml
                    </button>
                    <a href="/?tab=settings" class="px-3 py-2 bg-blue-950/60 hover:bg-blue-900/60 text-blue-300 text-xs font-medium rounded-lg transition border border-blue-800/60">
                        <span>⚙️</span> Другие настройки
                    </a>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- Whitelist Keywords -->
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4 flex flex-col">
                    <div class="flex items-center justify-between">
                        <h3 class="text-sm font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🎯</span> Белый список ключевых слов (<span id="kwCount">{{ keywords|length }}</span>)
                        </h3>
                        <span class="text-xs text-slate-400 font-mono">Мин. 1 совпадение</span>
                    </div>

                    <!-- Add Keyword Input -->
                    <div class="flex items-center gap-2">
                        <input type="text" id="newKeywordInput" onkeydown="if(event.key==='Enter') addKeyword()" placeholder="Добавить ключевое слово..." class="flex-1 bg-slate-950 border border-slate-800 text-slate-100 text-xs rounded-lg px-3 py-2 outline-none focus:border-emerald-500 font-mono">
                        <button type="button" onclick="addKeyword()" class="px-3 py-2 bg-emerald-600/80 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition shrink-0">
                            + Добавить
                        </button>
                    </div>

                    <!-- Keywords Tag Container -->
                    <div id="keywordsContainer" class="flex flex-wrap gap-1.5 max-h-96 overflow-y-auto custom-scroll pr-1 flex-1">
                        {% for kw in keywords %}
                            <span class="rule-chip group inline-flex items-center gap-1 text-xs font-mono bg-emerald-950/60 text-emerald-300 border border-emerald-800/50 px-2.5 py-1 rounded-md" data-term="{{ kw }}">
                                <span>{{ kw }}</span>
                                <button type="button" onclick="removeRuleTerm(this)" class="text-emerald-500 hover:text-white font-bold ml-1 focus:outline-none" title="Удалить">×</button>
                            </span>
                        {% endfor %}
                    </div>
                </div>

                <!-- Blacklist Stop-words -->
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4 flex flex-col">
                    <div class="flex items-center justify-between">
                        <h3 class="text-sm font-bold text-red-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🚫</span> Черный список стоп-слов (<span id="swCount">{{ stop_words|length }}</span>)
                        </h3>
                        <span class="text-xs text-slate-400 font-mono">Мгновенный отсев</span>
                    </div>

                    <!-- Add Stopword Input -->
                    <div class="flex items-center gap-2">
                        <input type="text" id="newStopwordInput" onkeydown="if(event.key==='Enter') addStopword()" placeholder="Добавить стоп-слово..." class="flex-1 bg-slate-950 border border-slate-800 text-slate-100 text-xs rounded-lg px-3 py-2 outline-none focus:border-red-500 font-mono">
                        <button type="button" onclick="addStopword()" class="px-3 py-2 bg-red-600/80 hover:bg-red-500 text-white text-xs font-bold rounded-lg transition shrink-0">
                            + Добавить
                        </button>
                    </div>

                    <!-- Stopwords Tag Container -->
                    <div id="stopwordsContainer" class="flex flex-wrap gap-1.5 max-h-96 overflow-y-auto custom-scroll pr-1 flex-1">
                        {% for sw in stop_words %}
                            <span class="rule-chip group inline-flex items-center gap-1 text-xs font-mono bg-red-950/40 text-red-300 border border-red-900/40 px-2.5 py-1 rounded-md" data-term="{{ sw }}">
                                <span>{{ sw }}</span>
                                <button type="button" onclick="removeRuleTerm(this)" class="text-red-500 hover:text-white font-bold ml-1 focus:outline-none" title="Удалить">×</button>
                            </span>
                        {% endfor %}
                    </div>
                </div>
            </div>

            <!-- Title Exclusions Block (Drop Titles) -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                <div class="flex items-center justify-between">
                    <div>
                        <h3 class="text-sm font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🛑</span> Исключаемые должности и грейды вакансий (<span id="dtCount">{{ drop_titles|length if drop_titles else 0 }}</span>)
                        </h3>
                        <p class="text-xs text-slate-400 mt-1">
                            Вакансии, содержащие эти слова в названии (например, Senior, Lead), отсеиваются сборщиком. Middle и мидл разрешены.
                        </p>
                    </div>
                </div>

                <div class="flex items-center gap-2">
                    <input type="text" id="newDropTitleInput" onkeydown="if(event.key==='Enter') addDropTitle()" placeholder="Добавить исключаемую должность..." class="flex-1 bg-slate-950 border border-slate-800 text-slate-100 text-xs rounded-lg px-3 py-2 outline-none focus:border-amber-500 font-mono">
                    <button type="button" onclick="addDropTitle()" class="px-3 py-2 bg-amber-600/80 hover:bg-amber-500 text-white text-xs font-bold rounded-lg transition shrink-0">
                        + Добавить
                    </button>
                </div>

                <div id="dropTitlesContainer" class="flex flex-wrap gap-1.5">
                    {% for dt in drop_titles %}
                        <span class="rule-chip group inline-flex items-center gap-1 text-xs font-mono bg-amber-950/40 text-amber-300 border border-amber-900/40 px-2.5 py-1 rounded-md" data-term="{{ dt }}">
                            <span>{{ dt }}</span>
                            <button type="button" onclick="removeRuleTerm(this)" class="text-amber-500 hover:text-white font-bold ml-1 focus:outline-none" title="Удалить">×</button>
                        </span>
                    {% endfor %}
                </div>
            </div>

            <!-- Recalculate Trigger Panel -->
            <div class="bg-gradient-to-r from-blue-950/30 via-slate-900 to-indigo-950/30 border border-blue-900/40 p-5 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-4">
                <div class="space-y-1">
                    <h4 class="text-sm font-bold text-white flex items-center gap-2">
                        <span>🔄</span> Пересчитать отсеянные заказы и вакансии
                    </h4>
                    <p class="text-xs text-slate-400">
                        После изменения ключевиков или стоп-слов запустите локальный пересчет: отсеянные ранее заказы будут перепроверены по новым правилам и восстановлены в ленту Hot / Normal.
                    </p>
                </div>
                <button type="button" onclick="runRecalculateFromRules()" id="rulesRecalcBtn" class="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white text-xs font-bold rounded-lg transition flex items-center gap-2 shadow-md shadow-blue-900/40 shrink-0">
                    <span>🚀</span> Запустить пересчет базы
                </button>
            </div>
        </div>
        {% endif %}

        {% if active_tab == 'profile' %}
        <!-- HH Profile & Resume View -->
        <div class="space-y-6">
            <!-- Andrei Pimenov Resume Summary -->
            <div class="bg-slate-900 border border-rose-950/60 p-6 rounded-xl space-y-4">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-4">
                    <div>
                        <h3 class="text-lg font-bold text-white flex items-center gap-2">
                            <span>👤</span> Пименов Андрей Дмитриевич
                            <span class="text-xs px-2 py-0.5 rounded-md bg-blue-950 text-blue-300 border border-blue-800 font-mono">@Horizontal84</span>
                        </h3>
                        <p class="text-xs text-slate-400 mt-1">Разработчик решений на базе AI / Специалист по автоматизации (AI), Python-разработчик</p>
                    </div>
                    <div class="text-xs font-mono text-slate-400">
                        Контакты: pimenoffandrew@gmail.com | Telegram: @Horizontal84
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🎙</span> Речевая аналитика звонков
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Cortex IT (6 мес). WhisperX, pyannote, Qwen 32B, FastAPI, Celery, Redis, PostgreSQL, Bitrix24 REST API, Weasyprint. Батчинг на GPU, оптимизация памяти, детерминированная валидация оценок.
                        </p>
                    </div>

                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-blue-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🧠</span> Корпоративный RAG-ассистент
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Cortex IT. Qdrant, LangChain, FastAPI. Индексация сложной номенклатуры, таблиц и ГОСТов для отдела продаж 130+ менеджеров компании.
                        </p>
                    </div>

                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>📹</span> Видеоаналитика & CV
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Cortex IT / AgroTech. YOLOv8, ByteTrack, IsolationForest, OpenCV, CUDA, FastAPI, Docker. Потоковая детекция с IP-камер 24/7.
                        </p>
                    </div>

                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-purple-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>💻</span> LaptopTester & Warehouse
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Компьютерный Цехъ (10 мес). Python, PyQt5, ReportLab, WMI, smartctl, Google Sheets API. Диагностика ноутбуков, печать PDF-этикеток.
                        </p>
                    </div>

                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🤖</span> Боты и надежный бэкенд
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Avia_Pars. aiogram 3, asyncio, SQLite WAL, Circuit Breaker, устойчивость к сбоям внешних API, 200+ тестов.
                        </p>
                    </div>

                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>💼</span> B2B переговоры & продажи
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Zoon, Пензагро-58. Опыт деловой коммуникации с владельцами бизнеса, понимание коммерческих метрик, воронки продаж и конверсии.
                        </p>
                    </div>
                </div>
            </div>

            <!-- HH Active Queries & Filters -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-3">
                    <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        <span>🔎</span> Активные поисковые запросы hh.ru ({{ hh_config.queries|length }})
                    </h4>
                    <div class="space-y-1.5 max-h-80 overflow-y-auto custom-scroll pr-1">
                        {% for q in hh_config.queries %}
                            <div class="text-xs font-mono bg-slate-950/90 text-rose-300 border border-slate-800/80 p-2.5 rounded-lg select-all">
                                {{ q }}
                            </div>
                        {% endfor %}
                    </div>
                </div>

                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                    <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        <span>🛡</span> Фильтрация уровня и стоп-слов
                    </h4>
                    <div class="space-y-2 text-xs text-slate-300">
                        <div class="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
                            <span class="font-semibold text-amber-400">Отсеиваемый грейд:</span>
                            <p class="font-mono text-[11px] text-slate-400">{{ hh_config.drop_title }}</p>
                        </div>
                        <div class="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
                            <span class="font-semibold text-emerald-400">Сохраняемые Junior-позиции:</span>
                            <p class="font-mono text-[11px] text-slate-400">{{ hh_config.junior_title }}</p>
                        </div>
                        <div class="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
                            <span class="font-semibold text-red-400">Отсеиваемый опыт:</span>
                            <p class="font-mono text-[11px] text-slate-400">{{ hh_config.drop_experience | join(', ') }}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% endif %}

        {% if active_tab == 'health' %}
        <!-- Live Health Check View -->
        <div class="space-y-6">
            <!-- Header bar with trigger -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🩺</span> Мониторинг доступности бирж, ИИ-моделей и базы данных
                    </h3>
                    <p class="text-xs text-slate-400 mt-1">
                        Проверка сетевой доступности внешних площадок, времени отклика (latency), статусов Mistral, Antigravity и SQLite.
                    </p>
                </div>
                <div class="flex items-center gap-3">
                    <span id="health-uptime-badge" class="text-xs bg-slate-800 text-teal-300 font-mono px-2.5 py-1 rounded-lg border border-slate-700">
                        ⏳ Аптайм: {{ uptime_info.uptime if uptime_info else '0 мин.' }}
                    </span>
                    <span id="health-last-checked" class="text-xs text-slate-400 font-mono">
                        {% if health_data and health_data.checked_at %}
                            Проверено: {{ health_data.checked_at }}
                        {% endif %}
                    </span>
                    <button id="health-refresh-btn" onclick="runLiveHealthCheck()" class="text-xs bg-teal-600 hover:bg-teal-500 text-white font-semibold px-4 py-2 rounded-lg transition flex items-center gap-1.5 shadow-md">
                        <span>🔄</span> Проверить сейчас
                    </button>
                </div>
            </div>

            <!-- Overall status banner -->
            <div id="health-overall-banner" class="p-3.5 rounded-xl border text-xs font-semibold flex items-center justify-between {% if health_data and health_data.all_ok %}bg-emerald-950/40 border-emerald-900/60 text-emerald-300{% else %}bg-amber-950/40 border-amber-900/60 text-amber-300{% endif %}">
                <div class="flex items-center gap-2">
                    <span id="health-overall-icon">{% if health_data and health_data.all_ok %}🟢{% else %}⚠️{% endif %}</span>
                    <span id="health-overall-text">
                        {% if health_data and health_data.all_ok %}
                            Все системы и биржи работают штатно
                        {% else %}
                            Часть систем недоступна или имеет задержки отклика
                        {% endif %}
                    </span>
                </div>
                <span class="text-[11px] font-mono text-slate-400">Параллельный опрос через httpx / asyncio</span>
            </div>

            <!-- Freelance & Vacancies Exchanges Status Grid -->
            <div class="space-y-3">
                <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span>🌐</span> Биржи фриланса и платформы вакансий ({{ health_data.exchanges|length if health_data else 6 }})
                </h4>
                <div id="health-exchanges-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                    {% if health_data and health_data.exchanges %}
                        {% for ex in health_data.exchanges %}
                            <div class="bg-slate-900/90 border {% if ex.ok %}border-slate-800{% else %}border-red-900/60 bg-red-950/10{% endif %} p-4 rounded-xl space-y-2.5">
                                <div class="flex items-center justify-between">
                                    <div class="font-bold text-sm text-white flex items-center gap-1.5">
                                        <span>{% if ex.ok %}🟢{% else %}🔴{% endif %}</span>
                                        <span>{{ ex.name }}</span>
                                    </div>
                                    <span class="text-xs font-mono font-bold px-2 py-0.5 rounded border {% if ex.latency_ms < 1000 %}bg-emerald-950 text-emerald-400 border border-emerald-800/60{% elif ex.latency_ms < 2500 %}bg-amber-950 text-amber-400 border border-amber-800/60{% else %}bg-red-950 text-red-400 border border-red-800/60{% endif %}">
                                        {{ ex.latency_ms }} ms
                                    </span>
                                </div>
                                <div class="text-xs text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-2">
                                    <span class="font-mono truncate max-w-[200px]" title="{{ ex.url }}">{{ ex.url }}</span>
                                    <span class="font-mono font-semibold {% if ex.ok %}text-emerald-400{% else %}text-red-400{% endif %}">
                                        {{ 'HTTP ' ~ ex.status_code if ex.status_code else (ex.error or 'ERR') }}
                                    </span>
                                </div>
                            </div>
                        {% endfor %}
                    {% else %}
                        <div class="col-span-3 text-center py-6 text-slate-500 text-xs">
                            Нажмите кнопку «Проверить сейчас» для получения актуальных данных.
                        </div>
                    {% endif %}
                </div>
            </div>

            <!-- AI Models & DB Status Grid -->
            <div class="space-y-3">
                <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span>⚡</span> ИИ-модели и внутренняя инфраструктура
                </h4>
                <div id="health-services-grid" class="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                    {% if health_data and health_data.services %}
                        {% for svc in health_data.services %}
                            <div class="bg-slate-900/90 border {% if svc.ok %}border-slate-800{% else %}border-red-900/60 bg-red-950/10{% endif %} p-4 rounded-xl space-y-2.5">
                                <div class="flex items-center justify-between">
                                    <div class="font-bold text-sm text-white flex items-center gap-1.5">
                                        <span>{% if svc.ok %}🟢{% else %}🔴{% endif %}</span>
                                        <span>{{ svc.name }}</span>
                                    </div>
                                    <span class="text-xs font-mono font-bold px-2 py-0.5 rounded border {% if svc.latency_ms < 500 %}bg-emerald-950 text-emerald-400 border border-emerald-800/60{% elif svc.latency_ms < 1500 %}bg-amber-950 text-amber-400 border border-amber-800/60{% else %}bg-red-950 text-red-400 border border-red-800/60{% endif %}">
                                        {{ svc.latency_ms }} ms
                                    </span>
                                </div>
                                <div class="text-xs text-slate-400 border-t border-slate-800/80 pt-2 font-mono">
                                    {% if svc.details %}
                                        <div class="text-slate-300 truncate" title="{{ svc.details }}">{{ svc.details }}</div>
                                    {% elif svc.error %}
                                        <div class="text-red-400 truncate" title="{{ svc.error }}">{{ svc.error }}</div>
                                    {% else %}
                                        <div class="text-emerald-400">OK</div>
                                    {% endif %}
                                </div>
                            </div>
                        {% endfor %}
                    {% endif %}
                </div>
            </div>
        </div>
        {% endif %}

        {% if active_tab == 'settings' %}
        <!-- Dynamic Settings View -->
        <div class="space-y-6">
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>⚙️</span> Интерактивные настройки мониторинга и фильтрации
                    </h3>
                    <p class="text-xs text-slate-400 mt-1">
                        Все изменения сохраняются в базу данных SQLite и моментально применяются в конвейере сбора и в Telegram-боте (/settings).
                    </p>
                </div>
                <button onclick="saveAllSettingsForm()" class="text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 rounded-lg transition flex items-center gap-1.5 shadow-md">
                    <span>💾</span> Сохранить все
                </button>
            </div>

            <!-- Local Database Re-evaluation Card -->
            <div class="bg-gradient-to-r from-indigo-950/40 via-slate-900 to-purple-950/40 border border-indigo-900/50 p-6 rounded-xl space-y-4 shadow-sm">
                <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                    <div>
                        <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                            <span>⚡</span> Локальный пересчет базы заказов и вакансий
                        </h4>
                        <p class="text-xs text-slate-400 mt-1">
                            Переоценка сохраненных в базе SQLite заказов и вакансий по текущим правилам фильтрации, ключевым и стоп-словам <strong>без запросов к внешним API бирж</strong>.
                        </p>
                    </div>
                    <button type="button" id="recalculateBtn" onclick="runRecalculate()" class="text-xs bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white font-bold px-4 py-2.5 rounded-lg transition flex items-center gap-2 shadow-md shadow-indigo-600/30 whitespace-nowrap">
                        <span>⚡</span>
                        <span id="recalculateBtnText">Запустить пересчет</span>
                    </button>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
                    <!-- Scope Selection -->
                    <div class="space-y-1.5">
                        <label for="recalc_scope" class="text-xs font-semibold text-slate-300 block">
                            🎯 Область пересчета:
                        </label>
                        <select id="recalc_scope" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-500">
                            <option value="trash">Только отсеянные (Trash) - вернуть подходящие</option>
                            <option value="all">Вся база (все заказы и вакансии)</option>
                            <option value="hh_ru">Только вакансии (hh.ru / Хабр)</option>
                            <option value="freelance">Только фриланс-биржи</option>
                        </select>
                    </div>

                    <!-- Limit Selection -->
                    <div class="space-y-1.5">
                        <label for="recalc_limit" class="text-xs font-semibold text-slate-300 block">
                            🔢 Лимит записей:
                        </label>
                        <select id="recalc_limit" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-indigo-500">
                            <option value="100">Последние 100 записей</option>
                            <option value="300" selected>Последние 300 записей</option>
                            <option value="1000">Последние 1000 записей</option>
                            <option value="0">Вся история базы без ограничений</option>
                        </select>
                    </div>

                    <!-- AI analyze recovered -->
                    <div class="flex items-center pt-5">
                        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                            <input type="checkbox" id="recalc_analyze_llm" checked class="w-4 h-4 text-indigo-600 rounded bg-slate-950 border-slate-800 focus:ring-indigo-500">
                            <span>Запускать AI-анализ для восстановленных</span>
                        </label>
                    </div>
                </div>

                <div id="recalcProgress" class="hidden text-xs bg-slate-950 border border-indigo-900/40 p-3 rounded-lg text-indigo-300 font-mono flex items-center gap-2">
                    <span class="animate-spin">⏳</span>
                    <span id="recalcStatusText">Выполняется локальный пересчет базы данных...</span>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Platform Toggles -->
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                    <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                        <span>🌐</span> Активные биржи и платформы
                    </h4>
                    <p class="text-xs text-slate-400">
                        Отключение биржи останавливает сохранение и отправку новых уведомлений с этой площадки.
                    </p>
                    <div class="space-y-3 pt-1">
                        <!-- Kwork -->
                        <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                            <span class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span> Kwork (фриланс)
                            </span>
                            <input type="checkbox" id="setting_platform_kwork" onchange="autoSaveSetting('platform_kwork', this.checked)" {% if settings_map.platform_kwork %}checked{% endif %} class="w-4 h-4 text-emerald-600 rounded bg-slate-900 border-slate-700 focus:ring-emerald-500">
                        </label>

                        <!-- FL.ru -->
                        <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                            <span class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-blue-400"></span> FL.ru (фриланс)
                            </span>
                            <input type="checkbox" id="setting_platform_fl_ru" onchange="autoSaveSetting('platform_fl_ru', this.checked)" {% if settings_map.platform_fl_ru %}checked{% endif %} class="w-4 h-4 text-blue-600 rounded bg-slate-900 border-slate-700 focus:ring-blue-500">
                        </label>

                        <!-- Freelance.ru -->
                        <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                            <span class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-purple-400"></span> Freelance.ru (фриланс)
                            </span>
                            <input type="checkbox" id="setting_platform_freelance_ru" onchange="autoSaveSetting('platform_freelance_ru', this.checked)" {% if settings_map.platform_freelance_ru %}checked{% endif %} class="w-4 h-4 text-purple-600 rounded bg-slate-900 border-slate-700 focus:ring-purple-500">
                        </label>

                        <!-- Pchel.net -->
                        <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                            <span class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span> Pchel.net (фриланс)
                            </span>
                            <input type="checkbox" id="setting_platform_pchel_net" onchange="autoSaveSetting('platform_pchel_net', this.checked)" {% if settings_map.platform_pchel_net %}checked{% endif %} class="w-4 h-4 text-amber-600 rounded bg-slate-900 border-slate-700 focus:ring-amber-500">
                        </label>

                        <!-- HeadHunter -->
                        <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                            <span class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span> HeadHunter (hh.ru вакансии)
                            </span>
                            <input type="checkbox" id="setting_platform_hh_ru" onchange="autoSaveSetting('platform_hh_ru', this.checked)" {% if settings_map.platform_hh_ru %}checked{% endif %} class="w-4 h-4 text-rose-600 rounded bg-slate-900 border-slate-700 focus:ring-rose-500">
                        </label>

                        <!-- Habr Career -->
                        <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                            <span class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                                <span class="w-2.5 h-2.5 rounded-full bg-cyan-400"></span> Хабр Карьера (вакансии)
                            </span>
                            <input type="checkbox" id="setting_platform_habr_career" onchange="autoSaveSetting('platform_habr_career', this.checked)" {% if settings_map.platform_habr_career %}checked{% endif %} class="w-4 h-4 text-cyan-600 rounded bg-slate-900 border-slate-700 focus:ring-cyan-500">
                        </label>
                    </div>
                </div>

                <!-- Filters & Thresholds -->
                <div class="space-y-6">
                    <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                        <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                            <span>🎯</span> Фильтрация и пороги отбора
                        </h4>

                        <!-- PRO filter toggle -->
                        <div class="space-y-2">
                            <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                                <div>
                                    <div class="text-xs font-semibold text-slate-200">Отсекать заказы только для PRO</div>
                                    <div class="text-[11px] text-slate-400">При включении заказы, требующие платного аккаунта, не будут попадать в уведомления</div>
                                </div>
                                <input type="checkbox" id="setting_filter_pro_only" onchange="autoSaveSetting('filter_pro_only', this.checked)" {% if settings_map.filter_pro_only %}checked{% endif %} class="w-4 h-4 text-indigo-600 rounded bg-slate-900 border-slate-700 focus:ring-indigo-500">
                            </label>
                        </div>

                        <!-- Min Budget -->
                        <div class="space-y-1.5 pt-2">
                            <label for="setting_min_budget" class="text-xs font-semibold text-slate-300 block">
                                💰 Минимальный бюджет заказа (₽):
                            </label>
                            <p class="text-[11px] text-slate-400">Заказы с указанным бюджетом ниже этой суммы отсеиваются в Tier 3 (произвольное число).</p>
                            <div class="relative">
                                <input type="number" id="setting_min_budget" min="0" step="500" value="{{ settings_map.min_budget if settings_map.min_budget is not none else 10000 }}" onchange="autoSaveSetting('min_budget', parseInt(this.value, 10) || 0)" placeholder="10000" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 pr-8 focus:border-indigo-500 outline-none">
                                <span class="absolute right-3 top-2.5 text-xs text-slate-500 font-medium">₽</span>
                            </div>
                        </div>

                        <!-- Quick Wins: Allow quick micro-orders -->
                        <div class="flex items-center justify-between p-3.5 bg-slate-950/70 border border-slate-800 rounded-lg">
                            <div class="space-y-0.5 pr-4">
                                <span class="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                                    <span>⚡</span> Пропускать быстрые заказы (Quick Wins)
                                </span>
                                <p class="text-[11px] text-slate-400">
                                    Не отсекать точечные микро-задачи (скрипты, парсеры, вебхуки, доработки ботов) с бюджетом от 2 000 ₽.
                                </p>
                            </div>
                            <input type="checkbox" id="setting_allow_quick_orders" class="w-4 h-4 accent-amber-500 rounded cursor-pointer" {% if settings_map.allow_quick_orders is not none and settings_map.allow_quick_orders %}checked{% endif %} onchange="autoSaveSetting('allow_quick_orders', this.checked)">
                        </div>

                        <!-- Quick min budget -->
                        <div class="space-y-1.5 pt-1">
                            <label for="setting_quick_min_budget" class="text-xs font-semibold text-slate-300 block">
                                ⚡ Мин. бюджет быстрых задач (₽):
                            </label>
                            <p class="text-[11px] text-slate-400">Порог для точечных скриптов и задач автоматизации (по умолчанию 2 000 ₽).</p>
                            <div class="relative">
                                <input type="number" id="setting_quick_min_budget" min="500" step="500" value="{{ settings_map.quick_min_budget if settings_map.quick_min_budget is not none else 2000 }}" onchange="autoSaveSetting('quick_min_budget', parseInt(this.value, 10) || 2000)" placeholder="2000" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 pr-8 focus:border-indigo-500 outline-none">
                                <span class="absolute right-3 top-2.5 text-xs text-slate-500 font-medium">₽</span>
                            </div>
                        </div>

                        <!-- Hot score threshold -->
                        <div class="space-y-1.5 pt-2">
                            <label for="setting_hot_score_threshold" class="text-xs font-semibold text-slate-300 block">
                                🔥 Порог Hot (Tier 1 совпадения):
                            </label>
                            <p class="text-[11px] text-slate-400">Минимальный балл Mistral/Agy (от 1 до 10) для присвоения категории Hot и мгновенной отправки в Telegram.</p>
                            <div class="relative">
                                <input type="number" id="setting_hot_score_threshold" min="1" max="10" step="1" value="{{ settings_map.hot_score_threshold if settings_map.hot_score_threshold is not none else 7 }}" onchange="autoSaveSetting('hot_score_threshold', parseInt(this.value, 10) || 7)" placeholder="7" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 pr-12 focus:border-indigo-500 outline-none">
                                <span class="absolute right-3 top-2.5 text-xs text-slate-500 font-medium">/ 10</span>
                            </div>
                        </div>
                    </div>

                    <!-- Vacancy Settings (City, Work Format, Min Salary) -->
                    <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                        <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                            <span>💼</span> Параметры поиска вакансий (hh.ru / Хабр Карьера)
                        </h4>

                        <!-- City / Region -->
                        <div class="space-y-1.5">
                            <label for="setting_vacancy_city" class="text-xs font-semibold text-slate-300 block">
                                📍 Город / Регион:
                            </label>
                            <select id="setting_vacancy_city" onchange="autoSaveSetting('vacancy_city', this.value)" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 focus:border-indigo-500 outline-none">
                                <option value="all" {% if settings_map.vacancy_city == 'all' or not settings_map.vacancy_city %}selected{% endif %}>Все города (без привязки)</option>
                                <option value="moscow" {% if settings_map.vacancy_city == 'moscow' %}selected{% endif %}>Москва</option>
                                <option value="spb" {% if settings_map.vacancy_city == 'spb' %}selected{% endif %}>Санкт-Петербург</option>
                                <option value="russia" {% if settings_map.vacancy_city == 'russia' %}selected{% endif %}>Вся Россия</option>
                            </select>
                        </div>

                        <!-- Work Format -->
                        <div class="space-y-1.5 pt-2">
                            <label for="setting_vacancy_work_format" class="text-xs font-semibold text-slate-300 block">
                                🏠 Формат работы:
                            </label>
                            <select id="setting_vacancy_work_format" onchange="autoSaveSetting('vacancy_work_format', this.value)" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 focus:border-indigo-500 outline-none">
                                <option value="all" {% if settings_map.vacancy_work_format == 'all' or not settings_map.vacancy_work_format %}selected{% endif %}>Любой формат работы</option>
                                <option value="remote" {% if settings_map.vacancy_work_format == 'remote' %}selected{% endif %}>Только удаленная работа (Remote)</option>
                                <option value="hybrid" {% if settings_map.vacancy_work_format == 'hybrid' %}selected{% endif %}>Гибридный график (Hybrid)</option>
                                <option value="office" {% if settings_map.vacancy_work_format == 'office' %}selected{% endif %}>Офис / Полный день (Office)</option>
                            </select>
                        </div>

                        <!-- Vacancy Min Salary -->
                        <div class="space-y-1.5 pt-2">
                            <label for="setting_vacancy_min_salary" class="text-xs font-semibold text-slate-300 block">
                                💵 Минимальная зарплата вакансии (₽):
                            </label>
                            <p class="text-[11px] text-slate-400">Вакансии с указанной зарплатой ниже этой суммы отсеиваются в Tier 3 (укажите 0 для любых).</p>
                            <div class="relative">
                                <input type="number" id="setting_vacancy_min_salary" min="0" step="5000" value="{{ settings_map.vacancy_min_salary if settings_map.vacancy_min_salary is not none else 80000 }}" onchange="autoSaveSetting('vacancy_min_salary', parseInt(this.value, 10) || 0)" placeholder="80000" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 pr-8 focus:border-indigo-500 outline-none">
                                <span class="absolute right-3 top-2.5 text-xs text-slate-500 font-medium">₽</span>
                            </div>
                        </div>

                        <!-- Allow Negotiable Vacancies Toggle -->
                        <div class="space-y-2 pt-2">
                            <label class="flex items-center justify-between p-3 bg-slate-950/80 border border-slate-800 rounded-lg cursor-pointer hover:border-slate-700 transition">
                                <div>
                                    <div class="text-xs font-semibold text-slate-200">Пропускать вакансии по договоренности</div>
                                    <div class="text-[11px] text-slate-400">Если выключено, вакансии без указанной зарплаты отсеиваются в Tier 3</div>
                                </div>
                                <input type="checkbox" id="setting_vacancy_allow_negotiable" onchange="autoSaveSetting('vacancy_allow_negotiable', this.checked)" {% if settings_map.vacancy_allow_negotiable is not false %}checked{% endif %} class="w-4 h-4 text-indigo-600 rounded bg-slate-900 border-slate-700 focus:ring-indigo-500">
                            </label>
                        </div>
                    </div>

                    <!-- HeadHunter OAuth Applicant Account Card -->
                    <div class="bg-gradient-to-r from-rose-950/40 via-slate-900 to-indigo-950/40 border border-rose-900/50 p-6 rounded-xl space-y-4 shadow-sm">
                        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                            <div>
                                <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                                    <span>🚀</span> HeadHunter: Отклики в 1 клик (OAuth)
                                </h4>
                                <p class="text-xs text-slate-400 mt-1">
                                    Подключение аккаунта соискателя HeadHunter для автоматической отправки сопроводительных писем и откликов в 1 клик без ручного перехода на сайт.
                                </p>
                            </div>
                            <div>
                                {% if hh_applicant_status and hh_applicant_status.authorized %}
                                    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
                                        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                        {{ hh_applicant_status.user_name or 'Подключено к HH' }}
                                    </span>
                                {% else %}
                                    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
                                        <span class="w-2 h-2 rounded-full bg-amber-400"></span>
                                        Не подключено
                                    </span>
                                {% endif %}
                            </div>
                        </div>

                        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pt-1">
                            {% if hh_applicant_status and hh_applicant_status.authorized %}
                                <div class="space-y-3 w-full">
                                    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                                        <div class="text-xs text-slate-300">
                                            Активное резюме: <strong class="text-white">{{ hh_applicant_status.resume_title or 'Основное' }}</strong>
                                            {% if hh_applicant_status.resume_id %}
                                                <span class="text-[11px] text-slate-500 font-mono ml-2">(ID: {{ hh_applicant_status.resume_id }})</span>
                                            {% else %}
                                                <span class="text-[11px] text-amber-400 font-medium ml-2">⚠️ Укажите ID резюме ниже</span>
                                            {% endif %}
                                        </div>
                                        <a href="/hh/auth" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold px-3 py-1.5 rounded-lg border border-slate-700 transition flex items-center gap-1.5">
                                            <span>🔄</span> Переподключить OAuth
                                        </a>
                                    </div>

                                    <!-- Resume ID input -->
                                    <div class="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg space-y-1.5">
                                        <label for="setting_hh_resume_id" class="text-xs font-semibold text-slate-300 block">
                                            📄 Выбор резюме для откликов (ID или ссылка из профиля hh.ru):
                                        </label>
                                        <div class="flex items-center gap-2">
                                            <input type="text" id="setting_hh_resume_id" value="{{ hh_applicant_status.resume_id or '' }}" placeholder="Например: 1cb3f... или https://hh.ru/resume/1cb3f..." class="w-full bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 outline-none focus:border-rose-500 font-mono">
                                            <button type="button" onclick="saveCustomResumeId()" class="text-xs bg-rose-600 hover:bg-rose-500 text-white font-semibold px-4 py-2 rounded-lg transition whitespace-nowrap flex items-center gap-1">
                                                <span>💾</span> Сохранить ID
                                            </button>
                                        </div>
                                        <p class="text-[11px] text-slate-400">
                                            Откройте ваше резюме на hh.ru, скопируйте ссылку или ID из адресной строки и сохраните. При отклике будет использоваться именно оно.
                                        </p>
                                    </div>
                                </div>
                            {% else %}
                                <p class="text-xs text-slate-400 max-w-xl">
                                    Нажмите кнопку справа, чтобы авторизоваться на hh.ru. Приложение получит защищенный токен соискателя.
                                </p>
                                <a href="/hh/auth" class="text-xs bg-rose-600 hover:bg-rose-500 text-white font-bold px-4 py-2 rounded-lg transition flex items-center gap-2 shadow-md shadow-rose-600/30 whitespace-nowrap">
                                    <span>🔑</span> Подключить аккаунт HeadHunter
                                </a>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% endif %}

        {% if active_tab == 'config' %}
        <!-- Full System Config (config.yml) GUI Editor -->
        <div class="space-y-6">
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🛠</span> Системная конфигурация и графический редактор (config.yml)
                    </h3>
                    <p class="text-xs text-slate-400 mt-1">
                        Все параметры config.yml доступны для настройки в визуальном интерфейсе с валидацией схемы Pydantic.
                    </p>
                </div>
                <div class="flex items-center gap-2">
                    <button type="button" onclick="window.location.reload()" class="text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 px-3.5 py-2 rounded-lg border border-slate-700 transition">
                        Сбросить
                    </button>
                    <button type="button" id="saveGuiConfigBtn" onclick="saveGuiConfig()" class="text-xs bg-amber-600 hover:bg-amber-500 text-white font-semibold px-4 py-2 rounded-lg transition flex items-center gap-1.5 shadow-md">
                        <span>💾</span> Сохранить настройки config.yml
                    </button>
                </div>
            </div>

            <!-- Security Badge -->
            <div class="bg-slate-900/60 border border-blue-900/40 p-3.5 rounded-xl flex items-center gap-2.5 text-xs text-blue-300">
                <span class="text-base">🔒</span>
                <span><strong>Безопасность:</strong> Все секреты и учетные данные (.env: BOT_TOKEN, MISTRAL_API_KEY, HH_APP_TOKEN) изолированы и защищены.</span>
            </div>

            <form id="configGuiForm" class="space-y-6">
                <!-- Group 1: Polling intervals & Server -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <!-- Polling Intervals Card -->
                    <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4">
                        <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                            <span>⏱</span> Интервалы опроса (секунды)
                        </h4>
                        <div class="space-y-3">
                            <div>
                                <label class="block text-xs font-semibold text-slate-300 mb-1">Фриланс базовый цикл (сек):</label>
                                <input type="number" id="cfg_poll_interval" value="{{ yaml_app_config.polling.interval_seconds }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-emerald-400 mb-1">Вакансии HH.ru & Хабр (сек, по умолч. 1800):</label>
                                <input type="number" id="cfg_poll_vac_interval" value="{{ yaml_app_config.polling.vacancies_interval_seconds }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                            </div>
                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">Kwork интервал:</label>
                                    <input type="number" id="cfg_poll_kwork" value="{{ yaml_app_config.polling.kwork_interval }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">FL.ru интервал:</label>
                                    <input type="number" id="cfg_poll_fl" value="{{ yaml_app_config.polling.fl_interval }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                                </div>
                            </div>
                            <label class="flex items-center gap-2 text-xs text-slate-300 pt-1 cursor-pointer">
                                <input type="checkbox" id="cfg_poll_backfill" {% if yaml_app_config.polling.initial_backfill %}checked{% endif %} class="rounded bg-slate-950 border-slate-700 text-amber-600 focus:ring-amber-500">
                                <span>Глубокий опрос (бэкфилл 3-5 страниц) при холодном старте</span>
                            </label>
                        </div>
                    </div>

                    <!-- Server & Storage Card -->
                    <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4">
                        <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                            <span>🌐</span> Сервер и Хранилище SQLite
                        </h4>
                        <div class="space-y-3">
                            <div>
                                <label class="block text-xs font-semibold text-slate-300 mb-1">Путь к базе данных (SQLite):</label>
                                <input type="text" id="cfg_storage_db" value="{{ yaml_app_config.storage.db_path }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                            </div>
                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs text-slate-300 mb-1">Web Host:</label>
                                    <input type="text" id="cfg_web_host" value="{{ yaml_app_config.web.host }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-300 mb-1">Web Port:</label>
                                    <input type="number" id="cfg_web_port" value="{{ yaml_app_config.web.port }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Group 2: Filters, Thresholds & Scoring -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4">
                    <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                        <span>🎯</span> Фильтрация и пороги отбора
                    </h4>
                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div>
                            <label class="block text-xs font-semibold text-slate-300 mb-1">Мин. бюджет фриланса (₽):</label>
                            <input type="number" id="cfg_filter_min_budget" value="{{ yaml_app_config.filter.min_budget }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-amber-300 mb-1">Порог Hot фриланс (1-10):</label>
                            <select id="cfg_filter_hot_threshold" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500">
                                {% for s in range(5, 11) %}
                                    <option value="{{ s }}" {% if yaml_app_config.filter.hot_score_threshold == s %}selected{% endif %}>{{ s }} / 10</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-emerald-400 mb-1">Порог Hot вакансий (1-10):</label>
                            <select id="cfg_filter_vac_hot_threshold" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500">
                                {% for s in range(5, 11) %}
                                    <option value="{{ s }}" {% if yaml_app_config.filter.vacancy_hot_score_threshold == s %}selected{% endif %}>{{ s }} / 10</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-emerald-400 mb-1">Мин. зарплата вакансии (₽):</label>
                            <input type="number" id="cfg_filter_vac_min_salary" value="{{ yaml_app_config.filter.vacancy_min_salary }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                        </div>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                            <input type="checkbox" id="cfg_filter_vac_negotiable" {% if yaml_app_config.filter.vacancy_allow_negotiable %}checked{% endif %} class="rounded bg-slate-950 border-slate-700 text-amber-600 focus:ring-amber-500">
                            <span>Разрешать вакансии с неуказанной зарплатой (по договоренности)</span>
                        </label>
                        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                            <input type="checkbox" id="cfg_filter_pro_only" {% if yaml_app_config.filter.filter_pro_only %}checked{% endif %} class="rounded bg-slate-950 border-slate-700 text-amber-600 focus:ring-amber-500">
                            <span>Отсекать заказы только для PRO</span>
                        </label>
                    </div>

                    <!-- Keywords & Stopwords Textareas -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        <div>
                            <label class="block text-xs font-semibold text-emerald-400 mb-1">Белый список ключевых слов (по одному на строку):</label>
                            <textarea id="cfg_filter_keywords" rows="5" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 font-mono text-xs text-slate-200 focus:outline-none focus:border-amber-500 custom-scroll">{{ yaml_app_config.filter.keywords|join('\n') }}</textarea>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-rose-400 mb-1">Черный список стоп-слов (по одному на строку):</label>
                            <textarea id="cfg_filter_stopwords" rows="5" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 font-mono text-xs text-slate-200 focus:outline-none focus:border-amber-500 custom-scroll">{{ yaml_app_config.filter.stop_words|join('\n') }}</textarea>
                        </div>
                    </div>
                </div>

                <!-- Group 3: LLM & Models -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4">
                    <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                        <span>🤖</span> ИИ-провайдер и Модели (LLM)
                    </h4>
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div>
                            <label class="block text-xs font-semibold text-slate-300 mb-1">Основной провайдер:</label>
                            <select id="cfg_llm_provider" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500">
                                <option value="antigravity" {% if yaml_app_config.llm.provider == 'antigravity' %}selected{% endif %}>Antigravity (Google AGY CLI)</option>
                                <option value="mistral" {% if yaml_app_config.llm.provider == 'mistral' %}selected{% endif %}>Mistral API</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-slate-300 mb-1">Agy модель:</label>
                            <input type="text" id="cfg_agy_model" value="{{ yaml_app_config.llm.antigravity.model }}" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500 font-mono">
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-slate-300 mb-1">Agy effort (глубина):</label>
                            <select id="cfg_agy_effort" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-amber-500">
                                {% for eff in ['low', 'medium', 'high', 'xhigh', 'max'] %}
                                    <option value="{{ eff }}" {% if yaml_app_config.llm.antigravity.effort == eff %}selected{% endif %}>{{ eff }}</option>
                                {% endfor %}
                            </select>
                        </div>
                    </div>
                </div>

                <!-- Group 4: Collectors Queries -->
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-4">
                    <h4 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
                        <span>🏢</span> Поисковые запросы сборщиков (HH.ru & Хабр)
                    </h4>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-semibold text-rose-300 mb-1">HeadHunter (hh.ru) запросы (по одному на строку):</label>
                            <textarea id="cfg_hh_queries" rows="6" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 font-mono text-xs text-slate-200 focus:outline-none focus:border-amber-500 custom-scroll">{{ yaml_app_config.collectors.hh_ru.queries|join('\n') }}</textarea>
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-cyan-300 mb-1">Хабр Карьера запросы (по одному на строку):</label>
                            <textarea id="cfg_habr_queries" rows="6" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 font-mono text-xs text-slate-200 focus:outline-none focus:border-amber-500 custom-scroll">{{ yaml_app_config.collectors.habr_career.queries|join('\n') }}</textarea>
                        </div>
                    </div>
                </div>

                <!-- Collapsible Raw YAML Editor -->
                <details class="bg-slate-900 border border-slate-800 p-5 rounded-xl">
                    <summary class="text-xs font-bold text-slate-400 uppercase tracking-wider cursor-pointer hover:text-slate-200">
                        <span>📝</span> Исходный код config.yml (сырой YAML редактор)
                    </summary>
                    <div class="pt-4 space-y-3">
                        <textarea id="yamlConfigEditor" rows="20" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-xs text-slate-200 focus:outline-none focus:border-amber-500 custom-scroll leading-relaxed" spellcheck="false">{{ raw_config_yaml }}</textarea>
                        <div class="flex justify-end">
                            <button type="button" onclick="saveYamlConfig()" class="text-xs bg-slate-800 hover:bg-slate-700 text-amber-400 border border-amber-600/50 font-semibold px-4 py-2 rounded-lg transition">
                                Сохранить из YAML-текста
                            </button>
                        </div>
                    </div>
                </details>
            </form>
        </div>
        {% endif %}

    </main>

    <!-- Toast Notification for Copy -->
    <div id="copyToast" class="fixed bottom-20 right-6 z-50 pointer-events-none bg-emerald-600 text-white px-4 py-2.5 rounded-lg shadow-xl text-xs font-semibold flex items-center gap-2 transform translate-y-20 opacity-0 transition-all duration-200 select-none">
        <span>✅</span> Текст успешно скопирован в буфер обмена!
    </div>

    <!-- Scroll To Top Button -->
    <button id="scrollToTopBtn" onclick="scrollToTop()" type="button" aria-label="Вернуться наверх" class="fixed bottom-6 right-6 z-40 bg-blue-600/90 hover:bg-blue-500 active:bg-blue-700 text-white p-3.5 rounded-full shadow-xl shadow-blue-900/40 border border-blue-400/40 backdrop-blur transition-all duration-300 opacity-0 translate-y-10 pointer-events-none flex items-center justify-center group focus:outline-none cursor-pointer" title="Вернуться наверх">
        <svg class="w-5 h-5 transform group-hover:-translate-y-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18" />
        </svg>
    </button>

    <script>
        async function copyToClipboard(text) {
            if (!text) return false;
            // 1. Попытка через execCommand в текущем синхронном user-gesture стеке (iOS Safari надежность)
            try {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.setAttribute('readonly', '');
                ta.style.position = 'fixed';
                ta.style.left = '-9999px';
                ta.style.top = '0';
                ta.style.fontSize = '16px';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                ta.setSelectionRange(0, text.length);
                const success = document.execCommand('copy');
                document.body.removeChild(ta);
                if (success) return true;
            } catch (err) {
                console.warn('execCommand copy fallback:', err);
            }

            // 2. Современный Clipboard API
            if (navigator.clipboard && navigator.clipboard.writeText) {
                try {
                    await navigator.clipboard.writeText(text);
                    return true;
                } catch (e) {
                    console.warn('navigator.clipboard error:', e);
                }
            }
            return false;
        }

        async function copyProposalText(boxEl) {
            if (!boxEl) return;
            const text = (boxEl.innerText || boxEl.textContent || '').trim();
            if (!text) return;

            logClient('click_copy_text', { length: text.length });
            await copyToClipboard(text);

            const toast = document.getElementById('copyToast');
            if (toast) {
                toast.innerHTML = '<span>✅</span> Текст успешно скопирован в буфер обмена!';
                toast.classList.remove('translate-y-20', 'opacity-0');
            }
            const origBorder = boxEl.style.borderColor;
            boxEl.style.borderColor = '#10b981';
            boxEl.classList.add('ring-1', 'ring-emerald-500/50');

            const container = boxEl.closest('[id^="proposal-box-"]') || boxEl.parentElement;
            const btn = container ? container.querySelector('button[onclick*="copyProposal("]') : null;

            let origBtnText = '';
            if (btn) {
                origBtnText = btn.innerHTML;
                btn.innerHTML = '<span>✅</span> Скопировано!';
                btn.classList.add('bg-emerald-600', 'text-white');
            }

            setTimeout(() => {
                if (toast) {
                    toast.classList.add('translate-y-20', 'opacity-0');
                }
                boxEl.style.borderColor = origBorder;
                boxEl.classList.remove('ring-1', 'ring-emerald-500/50');
                if (btn && origBtnText) {
                    btn.innerHTML = origBtnText;
                }
            }, 2000);
        }

        function copyProposal(elementId, btn) {
            const el = document.getElementById(elementId);
            if (!el) return;
            copyProposalText(el);
        }

        async function generateProposal(orderId, btn) {
            logClient('click_generate_proposal', { order_id: orderId });
            const origHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span>⏳</span> Генерация (agy)...';

            const card = document.querySelector(`.order-card[data-id="${orderId}"]`);
            const isResponded = card ? (card.getAttribute('data-responded') === '1') : false;
            const box = document.getElementById(`proposal-box-${orderId}`);

            let progressEl = null;
            let seconds = 0;
            let timerInterval = null;
            if (box) {
                progressEl = document.createElement('div');
                progressEl.id = `gen-progress-${orderId}`;
                progressEl.className = "mt-2 p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs text-rose-200 flex items-center justify-between gap-3 animate-pulse select-none";
                progressEl.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="animate-spin text-sm">⚙️</span>
                        <span><b>ИИ составляет персонализированное сопроводительное письмо...</b> (~20-30 сек)</span>
                    </div>
                    <span class="text-[11px] text-rose-300 font-mono" id="gen-timer-${orderId}">0с</span>
                `;
                box.appendChild(progressEl);

                const timerSpan = progressEl.querySelector(`#gen-timer-${orderId}`);
                timerInterval = setInterval(() => {
                    seconds++;
                    if (timerSpan) timerSpan.innerText = `${seconds}с`;
                }, 1000);
            }

            try {
                const res = await fetch(`/api/orders/${orderId}/generate-proposal`, {
                    method: 'POST',
                    credentials: 'same-origin'
                });
                const data = await res.json();
                if (timerInterval) clearInterval(timerInterval);
                if (progressEl) progressEl.remove();

                if (data.ok && data.proposal_text) {
                    if (data.recommended_price) {
                        const pill = document.getElementById(`rec-price-pill-${orderId}`);
                        if (pill) {
                            pill.className = "flex items-center gap-1.5 bg-emerald-950/40 border border-emerald-800/60 px-3 py-1 rounded-lg";
                            const formatted = new Intl.NumberFormat('ru-RU').format(data.recommended_price) + ' ₽';
                            pill.innerHTML = `<span class="text-xs text-emerald-400 font-medium">💡 Рекомендуемая:</span> <span class="text-sm font-bold text-emerald-300 font-mono">${formatted}</span>`;
                        }
                    }
                    if (data.market_price) {
                        const mktPill = document.getElementById(`market-price-pill-${orderId}`);
                        if (mktPill) {
                            mktPill.className = "flex items-center gap-1.5 bg-amber-950/40 border border-amber-800/60 px-3 py-1 rounded-lg";
                            const formattedM = new Intl.NumberFormat('ru-RU').format(data.market_price) + ' ₽';
                            mktPill.innerHTML = `<span class="text-xs text-amber-400 font-medium">🎯 Рыночная:</span> <span class="text-sm font-bold text-amber-300 font-mono">${formattedM}</span>`;
                        }
                    }

                    let finBlock = '';
                    if (data.recommended_price || data.market_price || data.price_justification) {
                        const recFormatted = data.recommended_price ? new Intl.NumberFormat('ru-RU').format(data.recommended_price) + ' ₽' : '';
                        const mktFormatted = data.market_price ? new Intl.NumberFormat('ru-RU').format(data.market_price) + ' ₽' : '';
                        finBlock = `
                            <div class="text-xs bg-slate-900/90 border border-amber-900/50 p-2.5 rounded-lg text-slate-300 space-y-1.5 mb-2">
                                <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-1.5">
                                    <span class="text-amber-400 font-semibold uppercase text-[10px] tracking-wider flex items-center gap-1">
                                        <span>🎯</span> Оценка ставок (agy с веб-поиском):
                                    </span>
                                    <div class="flex items-center gap-3 font-mono text-xs">
                                        ${mktFormatted ? `<span class="text-amber-300">🎯 Рыночная: <b>${mktFormatted}</b></span>` : ''}
                                        ${recFormatted ? `<span class="text-emerald-300">💡 Рекомендуемая: <b>${recFormatted}</b></span>` : ''}
                                    </div>
                                </div>
                                ${data.price_justification ? `<p class="text-slate-300 text-[11px] leading-relaxed">${escapeHtml(data.price_justification)}</p>` : ''}
                            </div>
                        `;
                    }

                    if (box) {
                        const isHh = (data.is_hh || data.source === 'hh_ru');
                        const isVac = isHh || (data.source === 'habr_career');
                        const titleText = isVac ? 'Сгенерированное Cover Letter (agy):' : 'Сгенерированный отклик:';
                        const icon = isVac ? '✉️' : '✍️';
                        const btnClass = isVac ? 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700' : 'bg-emerald-600 hover:bg-emerald-500 text-white';
                        const btnCopyText = isVac ? 'Скопировать Cover Letter' : 'Скопировать отклик';

                        let hhApplyHtml = '';
                        if (isHh) {
                            if (isResponded) {
                                hhApplyHtml = `<span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default">
                                    <span>✅</span> Отклик отправлен
                                </span>`;
                            } else {
                                hhApplyHtml = `<button type="button" onclick="applyVacancyHH('${orderId}', this)" class="apply-hh-btn text-xs bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm cursor-pointer select-none">
                                    <span>🚀</span> Откликнуться на HH
                                </button>`;
                            }
                        }

                        box.className = "mt-3 pt-3 border-t border-slate-800 space-y-2";
                        box.innerHTML = `
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <span class="text-xs font-semibold ${isVac ? 'text-rose-400' : 'text-emerald-400'} uppercase tracking-wider flex items-center gap-1">
                                    <span>${icon}</span> ${titleText}
                                </span>
                                <div class="flex flex-wrap items-center gap-2">
                                    <button type="button" onclick="generateProposal('${orderId}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition active:scale-95 cursor-pointer">
                                        🔄 Перегенерировать
                                    </button>
                                    ${hhApplyHtml}
                                    <button type="button" onclick="copyProposal('proposal-text-${orderId}', this)" class="text-xs ${btnClass} font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm active:scale-95 cursor-pointer select-none">
                                        <span>📋</span> ${btnCopyText}
                                    </button>
                                </div>
                            </div>
                            ${finBlock}
                            <div id="proposal-text-${orderId}" onclick="copyProposalText(this)" title="Нажмите, чтобы скопировать текст в буфер обмена" class="text-xs font-mono bg-slate-900/90 hover:bg-slate-900 text-slate-200 p-3.5 rounded-lg border border-slate-800 hover:border-slate-600 whitespace-pre-wrap leading-relaxed select-text cursor-pointer transition">${escapeHtml(data.proposal_text)}</div>
                        `;
                    }
                    logClient('generate_proposal_success', { order_id: orderId });
                    showToast('Отклик успешно сгенерирован!');
                } else {
                    logClient('generate_proposal_failed', { type: 'error', order_id: orderId, msg: data.error });
                    alert('Ошибка генерации: ' + (data.error || 'не удалось составить отклик'));
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            } catch (e) {
                logClient('generate_proposal_exception', { type: 'error', order_id: orderId, msg: String(e) });
                if (timerInterval) clearInterval(timerInterval);
                if (progressEl) progressEl.remove();
                alert('Сетевая ошибка: ' + e);
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }

        async function autoSaveSetting(key, value) {
            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ [key]: value })
                });
                const data = await res.json();
                if (data.ok) {
                    showToast('Настройка сохранена!');
                } else {
                    alert('Ошибка сохранения: ' + (data.error || 'неизвестная ошибка'));
                }
            } catch (e) {
                alert('Сетевая ошибка сохранения: ' + e);
            }
        }

        async function saveCustomResumeId() {
            const input = document.getElementById('setting_hh_resume_id');
            if (!input) return;
            let val = input.value.trim();
            if (val.includes('/resume/')) {
                const match = val.match(/\\/resume\\/([a-zA-Z0-9_-]+)/);
                if (match) val = match[1];
            }
            if (!val) {
                alert('Пожалуйста, укажите ID резюме или ссылку на него с hh.ru');
                return;
            }
            await autoSaveSetting('hh_resume_id', val);
            showToast('ID резюме сохранен: ' + val);
            setTimeout(() => window.location.reload(), 600);
        }

        async function saveAllSettingsForm() {
            const getEl = id => document.getElementById(id);
            const isChecked = (id, defVal) => {
                const el = getEl(id);
                return el ? el.checked : defVal;
            };
            const getVal = (id, defVal) => {
                const el = getEl(id);
                return el ? el.value : defVal;
            };
            const getInt = (id, defVal) => {
                const val = parseInt(getVal(id, ''), 10);
                return isNaN(val) ? defVal : val;
            };

            const payload = {
                platform_kwork: isChecked('setting_platform_kwork', true),
                platform_fl_ru: isChecked('setting_platform_fl_ru', true),
                platform_freelance_ru: isChecked('setting_platform_freelance_ru', true),
                platform_pchel_net: isChecked('setting_platform_pchel_net', true),
                platform_hh_ru: isChecked('setting_platform_hh_ru', true),
                platform_habr_career: isChecked('setting_platform_habr_career', true),
                filter_pro_only: isChecked('setting_filter_pro_only', false),
                min_budget: getInt('setting_min_budget', 10000),
                hot_score_threshold: getInt('setting_hot_score_threshold', 7),
                vacancy_city: getVal('setting_vacancy_city', 'all'),
                vacancy_work_format: getVal('setting_vacancy_work_format', 'all'),
                vacancy_min_salary: getInt('setting_vacancy_min_salary', 80000),
                vacancy_allow_negotiable: isChecked('setting_vacancy_allow_negotiable', true)
            };
            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.ok) {
                    showToast('Все настройки успешно сохранены!');
                } else {
                    alert('Ошибка сохранения настроек: ' + (data.error || 'неизвестная ошибка'));
                }
            } catch (e) {
                alert('Ошибка сети: ' + e);
            }
        }

        async function runRecalculate() {
            const btn = document.getElementById('recalculateBtn');
            const btnText = document.getElementById('recalculateBtnText');
            const progress = document.getElementById('recalcProgress');
            const statusText = document.getElementById('recalcStatusText');

            const scopeEl = document.getElementById('recalc_scope');
            const limitEl = document.getElementById('recalc_limit');
            const analyzeEl = document.getElementById('recalc_analyze_llm');

            const scope = scopeEl ? scopeEl.value : 'trash';
            const limit = limitEl ? parseInt(limitEl.value, 10) : 300;
            const analyze_llm = analyzeEl ? analyzeEl.checked : true;

            const origText = btnText ? btnText.innerText : 'Запустить пересчет';
            if (btn) btn.disabled = true;
            if (btnText) btnText.innerText = 'Пересчет...';
            if (progress) progress.classList.remove('hidden');
            if (statusText) statusText.innerText = 'Выполняется локальная переоценка базы данных...';

            try {
                const res = await fetch('/api/orders/recalculate', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scope: scope,
                        limit: limit,
                        analyze_llm: analyze_llm
                    })
                });
                const data = await res.json();
                if (data.ok) {
                    showToast('Локальный пересчет успешно завершен!');
                    if (statusText) statusText.innerText = `✅ ${data.message}`;
                    alert(`✅ ${data.message}`);
                } else {
                    alert('Ошибка пересчета: ' + (data.error || 'неизвестная ошибка'));
                    if (statusText) statusText.innerText = `❌ Ошибка: ${data.error}`;
                }
            } catch (err) {
                alert('Сетевая ошибка при пересчете: ' + err);
                if (statusText) statusText.innerText = `❌ Сетевая ошибка: ${err}`;
            } finally {
                if (btn) btn.disabled = false;
                if (btnText) btnText.innerText = origText;
            }
        }

        function removeRuleTerm(btn) {
            const chip = btn.closest('.rule-chip');
            if (chip) {
                chip.remove();
                updateRuleCounters();
            }
        }

        function addTermToContainer(containerId, term, bgClass, textClass, borderClass, btnClass) {
            const cleanTerm = term.trim().toLowerCase();
            if (!cleanTerm) return;
            const container = document.getElementById(containerId);
            if (!container) return;

            const existing = Array.from(container.querySelectorAll('.rule-chip')).some(c => c.getAttribute('data-term') === cleanTerm);
            if (existing) {
                showToast('Этот термин уже добавлен!');
                return;
            }

            const span = document.createElement('span');
            span.className = `rule-chip group inline-flex items-center gap-1 text-xs font-mono ${bgClass} ${textClass} border ${borderClass} px-2.5 py-1 rounded-md`;
            span.setAttribute('data-term', cleanTerm);
            span.innerHTML = `<span>${cleanTerm}</span><button type="button" onclick="removeRuleTerm(this)" class="${btnClass} hover:text-white font-bold ml-1 focus:outline-none" title="Удалить">×</button>`;
            container.appendChild(span);
            updateRuleCounters();
        }

        function addKeyword() {
            const input = document.getElementById('newKeywordInput');
            if (input && input.value) {
                addTermToContainer('keywordsContainer', input.value, 'bg-emerald-950/60', 'text-emerald-300', 'border-emerald-800/50', 'text-emerald-500');
                input.value = '';
            }
        }

        function addStopword() {
            const input = document.getElementById('newStopwordInput');
            if (input && input.value) {
                addTermToContainer('stopwordsContainer', input.value, 'bg-red-950/40', 'text-red-300', 'border-red-900/40', 'text-red-500');
                input.value = '';
            }
        }

        function addDropTitle() {
            const input = document.getElementById('newDropTitleInput');
            if (input && input.value) {
                addTermToContainer('dropTitlesContainer', input.value, 'bg-amber-950/40', 'text-amber-300', 'border-amber-900/40', 'text-amber-500');
                input.value = '';
            }
        }

        function updateRuleCounters() {
            const getCount = id => document.querySelectorAll(`#${id} .rule-chip`).length;
            const kwEl = document.getElementById('kwCount');
            if (kwEl) kwEl.innerText = getCount('keywordsContainer');
            const swEl = document.getElementById('swCount');
            if (swEl) swEl.innerText = getCount('stopwordsContainer');
            const dtEl = document.getElementById('dtCount');
            if (dtEl) dtEl.innerText = getCount('dropTitlesContainer');
        }

        async function saveCustomRules() {
            const getTerms = id => Array.from(document.querySelectorAll(`#${id} .rule-chip`)).map(c => c.getAttribute('data-term')).filter(Boolean);
            const keywords = getTerms('keywordsContainer');
            const stop_words = getTerms('stopwordsContainer');
            const drop_titles = getTerms('dropTitlesContainer');

            const payload = {
                filter_keywords: keywords,
                filter_stop_words: stop_words,
                filter_drop_titles: drop_titles,
            };

            const btn = document.getElementById('saveRulesBtn');
            if (btn) btn.disabled = true;

            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.ok) {
                    showToast('Правила фильтрации успешно сохранены в базе!');
                } else {
                    alert('Ошибка сохранения: ' + (data.error || 'неизвестная ошибка'));
                }
            } catch (e) {
                alert('Сетевая ошибка: ' + e);
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function resetRulesToDefault() {
            if (!confirm('Сбросить все ключевые слова, стоп-слова и исключения к значениям по умолчанию из config.yml?')) return;
            try {
                const res = await fetch('/api/settings/reset-rules', {
                    method: 'POST',
                    credentials: 'same-origin',
                });
                const data = await res.json();
                if (data.ok) {
                    showToast('Правила сброшены к значениям по умолчанию!');
                    setTimeout(() => window.location.reload(), 500);
                } else {
                    alert('Ошибка сброса: ' + (data.error || 'неизвестная ошибка'));
                }
            } catch (e) {
                alert('Сетевая ошибка: ' + e);
            }
        }

        async function runRecalculateFromRules() {
            const btn = document.getElementById('rulesRecalcBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>⏳</span> Пересчет...';
            }
            try {
                const res = await fetch('/api/orders/recalculate', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ scope: 'trash', limit: 400, analyze_llm: false })
                });
                const data = await res.json();
                if (data.ok) {
                    const rec = data.stats.recovered || 0;
                    showToast(`Пересчет завершен! Восстановлено лидов: ${rec}`);
                } else {
                    alert('Ошибка пересчета: ' + (data.error || 'неизвестная ошибка'));
                }
            } catch(e) {
                alert('Сетевая ошибка пересчета: ' + e);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>🚀</span> Запустить пересчет базы';
                }
            }
        }

        async function runLiveHealthCheck() {
            const btn = document.getElementById('health-refresh-btn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>⏳</span> Проверяем...';
            }
            try {
                const res = await fetch('/api/health-check');
                const data = await res.json();
                if (data.checked_at) {
                    const timeEl = document.getElementById('health-last-checked');
                    if (timeEl) timeEl.innerText = 'Проверено: ' + data.checked_at;
                }
                const banner = document.getElementById('health-overall-banner');
                const bannerIcon = document.getElementById('health-overall-icon');
                const bannerText = document.getElementById('health-overall-text');
                if (banner && data.all_ok) {
                    banner.className = "p-3.5 rounded-xl border text-xs font-semibold flex items-center justify-between bg-emerald-950/40 border-emerald-900/60 text-emerald-300";
                    if (bannerIcon) bannerIcon.innerText = "🟢";
                    if (bannerText) bannerText.innerText = "Все системы и биржи работают штатно";
                } else if (banner) {
                    banner.className = "p-3.5 rounded-xl border text-xs font-semibold flex items-center justify-between bg-amber-950/40 border-amber-900/60 text-amber-300";
                    if (bannerIcon) bannerIcon.innerText = "⚠️";
                    if (bannerText) bannerText.innerText = "Часть систем недоступна или имеет задержки отклика";
                }

                // Render exchanges
                const exGrid = document.getElementById('health-exchanges-grid');
                if (exGrid && Array.isArray(data.exchanges)) {
                    exGrid.innerHTML = data.exchanges.map(ex => {
                        const border = ex.ok ? 'border-slate-800' : 'border-red-900/60 bg-red-950/10';
                        const badgeColor = ex.latency_ms < 1000 ? 'bg-emerald-950 text-emerald-400 border-emerald-800/60' : (ex.latency_ms < 2500 ? 'bg-amber-950 text-amber-400 border-amber-800/60' : 'bg-red-950 text-red-400 border-red-800/60');
                        const statusText = ex.status_code ? `HTTP ${ex.status_code}` : (ex.error || 'ERR');
                        const statusColor = ex.ok ? 'text-emerald-400' : 'text-red-400';
                        return `
                            <div class="bg-slate-900/90 border ${border} p-4 rounded-xl space-y-2.5">
                                <div class="flex items-center justify-between">
                                    <div class="font-bold text-sm text-white flex items-center gap-1.5">
                                        <span>${ex.ok ? '🟢' : '🔴'}</span>
                                        <span>${escapeHtml(ex.name)}</span>
                                    </div>
                                    <span class="text-xs font-mono font-bold px-2 py-0.5 rounded border ${badgeColor}">
                                        ${ex.latency_ms} ms
                                    </span>
                                </div>
                                <div class="text-xs text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-2">
                                    <span class="font-mono truncate max-w-[200px]" title="${escapeHtml(ex.url)}">${escapeHtml(ex.url)}</span>
                                    <span class="font-mono font-semibold ${statusColor}">${escapeHtml(statusText)}</span>
                                </div>
                            </div>
                        `;
                    }).join('');
                }

                // Render services
                const svcGrid = document.getElementById('health-services-grid');
                if (svcGrid && Array.isArray(data.services)) {
                    svcGrid.innerHTML = data.services.map(svc => {
                        const border = svc.ok ? 'border-slate-800' : 'border-red-900/60 bg-red-950/10';
                        const badgeColor = svc.latency_ms < 500 ? 'bg-emerald-950 text-emerald-400 border-emerald-800/60' : (svc.latency_ms < 1500 ? 'bg-amber-950 text-amber-400 border-amber-800/60' : 'bg-red-950 text-red-400 border-red-800/60');
                        let detailHtml = '<div class="text-emerald-400">OK</div>';
                        if (svc.details) {
                            detailHtml = `<div class="text-slate-300 truncate" title="${escapeHtml(svc.details)}">${escapeHtml(svc.details)}</div>`;
                        } else if (svc.error) {
                            detailHtml = `<div class="text-red-400 truncate" title="${escapeHtml(svc.error)}">${escapeHtml(svc.error)}</div>`;
                        }
                        return `
                            <div class="bg-slate-900/90 border ${border} p-4 rounded-xl space-y-2.5">
                                <div class="flex items-center justify-between">
                                    <div class="font-bold text-sm text-white flex items-center gap-1.5">
                                        <span>${svc.ok ? '🟢' : '🔴'}</span>
                                        <span>${escapeHtml(svc.name)}</span>
                                    </div>
                                    <span class="text-xs font-mono font-bold px-2 py-0.5 rounded border ${badgeColor}">
                                        ${svc.latency_ms} ms
                                    </span>
                                </div>
                                <div class="text-xs text-slate-400 border-t border-slate-800/80 pt-2 font-mono">
                                    ${detailHtml}
                                </div>
                            </div>
                        `;
                    }).join('');
                }
                showToast('Данные мониторинга обновлены!');
            } catch (e) {
                alert('Ошибка при выполнении проверки: ' + e);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>🔄</span> Проверить сейчас';
                }
            }
        }

        function showToast(msg) {
            const toast = document.getElementById('copyToast');
            if (!toast) return;
            const orig = toast.innerHTML;
            toast.innerHTML = `<span>✅</span> ${escapeHtml(msg)}`;
            toast.classList.remove('translate-y-20', 'opacity-0');
            setTimeout(() => {
                toast.classList.add('translate-y-20', 'opacity-0');
                setTimeout(() => { toast.innerHTML = orig; }, 300);
            }, 2500);
        }

        let activeTopic = 'all';

        function isVacancySection() {
            const href = window.location.href;
            return href.includes('section=hh_ru') || href.includes('section=hh') || href.includes('section=vacancies');
        }

        function setTopicFilter(topic, btn) {
            activeTopic = topic;
            document.querySelectorAll('.topic-chip').forEach(el => {
                el.classList.remove('bg-blue-600', 'bg-rose-600', 'text-white', 'font-bold');
                el.classList.add('bg-slate-800', 'text-slate-300');
            });
            const isHh = isVacancySection();
            const activeClass = isHh ? 'bg-rose-600' : 'bg-blue-600';
            btn.classList.remove('bg-slate-800', 'text-slate-300');
            btn.classList.add(activeClass, 'text-white', 'font-bold');
            applyClientFilters();
        }

        function resetFilters() {
            const sInput = document.getElementById('orderSearch');
            if (sInput) sInput.value = '';
            const minInput = document.getElementById('filterPriceMin');
            if (minInput) minInput.value = '';
            const maxInput = document.getElementById('filterPriceMax');
            if (maxInput) maxInput.value = '';
            const sortSel = document.getElementById('orderSortSelect');
            if (sortSel) sortSel.value = 'default';
            activeTopic = 'all';
            const isHh = isVacancySection();
            const activeClass = isHh ? 'bg-rose-600' : 'bg-blue-600';
            document.querySelectorAll('.topic-chip').forEach((el, idx) => {
                if (idx === 0) {
                    el.className = `topic-chip px-3 py-1 rounded-lg text-xs font-medium transition ${activeClass} text-white font-bold`;
                } else {
                    el.className = 'topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700';
                }
            });
            applyClientFilters();
        }

        async function toggleResponded(orderId, btn) {
            if (!orderId) return;
            try {
                const resp = await fetch(`/api/orders/${orderId}/toggle-responded`, { method: 'POST' });
                const data = await resp.json();
                if (data.ok) {
                    const card = document.querySelector(`.order-card[data-id="${orderId}"]`);
                    const isResp = !!data.is_responded;
                    if (card) {
                        card.setAttribute('data-responded', isResp ? '1' : '0');
                        if (isResp) {
                            card.classList.add('opacity-65', 'border-dashed');
                        } else {
                            card.classList.remove('opacity-65', 'border-dashed');
                        }
                    }
                    if (btn) {
                        const icon = btn.querySelector('.responded-icon');
                        const text = btn.querySelector('.responded-text');
                        if (icon) icon.innerText = isResp ? '✅' : '⬜';
                        if (text) text.innerText = isResp ? 'Откликнулся' : 'Не откликнулся';
                        if (isResp) {
                            btn.className = "responded-toggle-btn text-xs px-2.5 py-0.5 rounded-md transition flex items-center gap-1.5 border font-medium bg-emerald-950/90 text-emerald-300 border-emerald-700/80 hover:bg-emerald-900/90";
                        } else {
                            btn.className = "responded-toggle-btn text-xs px-2.5 py-0.5 rounded-md transition flex items-center gap-1.5 border font-medium bg-slate-950 text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700";
                        }
                    }
                    showToast(isResp ? 'Отмечено: отклик отправлен' : 'Отметка отклика снята');
                    applyClientFilters();
                }
            } catch (e) {
                alert('Ошибка обновления статуса: ' + e);
            }
        }

        async function applyVacancyHH(orderId, btn) {
            if (!orderId) return;
            logClient('click_apply_hh', { order_id: orderId });
            const origHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span>⏳</span> Отправка на HH...';

            const propTextEl = document.getElementById(`proposal-text-${orderId}`);
            let progressEl = null;
            let seconds = 0;
            let timerInterval = null;
            const box = document.getElementById(`proposal-box-${orderId}`);

            if (!propTextEl && box) {
                progressEl = document.createElement('div');
                progressEl.id = `apply-progress-${orderId}`;
                progressEl.className = "mt-2 p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs text-rose-200 flex items-center justify-between gap-3 animate-pulse select-none";
                progressEl.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="animate-spin text-sm">⚙️</span>
                        <span><b>ИИ составляет письмо и отправляет отклик на HH...</b> (~20-30 сек)</span>
                    </div>
                    <span class="text-[11px] text-rose-300 font-mono" id="apply-timer-${orderId}">0с</span>
                `;
                box.appendChild(progressEl);

                const timerSpan = progressEl.querySelector(`#apply-timer-${orderId}`);
                timerInterval = setInterval(() => {
                    seconds++;
                    if (timerSpan) timerSpan.innerText = `${seconds}с`;
                }, 1000);
            }

            try {
                const resp = await fetch(`/api/vacancies/${orderId}/apply`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });
                let data;
                try {
                    data = await resp.json();
                } catch (parseErr) {
                    throw new Error(`Ошибка сервера (${resp.status}): ${resp.statusText || 'Internal Server Error'}`);
                }
                if (timerInterval) clearInterval(timerInterval);
                if (progressEl) progressEl.remove();

                if (data.ok) {
                    btn.innerHTML = '<span>✅</span> Отклик отправлен';
                    btn.disabled = true;
                    btn.className = "text-xs px-2.5 py-1 rounded-md transition flex items-center gap-1 border font-medium bg-slate-900/80 text-emerald-400 border-slate-800 cursor-default";

                    const card = document.querySelector(`.order-card[data-id="${orderId}"]`);
                    if (card) {
                        card.setAttribute('data-responded', '1');
                        card.classList.add('opacity-65', 'border-dashed');
                        card.querySelectorAll('.apply-hh-btn').forEach(b => {
                            b.outerHTML = '<span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default"><span>✅</span> Отклик отправлен</span>';
                        });
                    }
                    const respBtn = document.getElementById(`responded-btn-${orderId}`);
                    if (respBtn) {
                        const icon = respBtn.querySelector('.responded-icon');
                        const text = respBtn.querySelector('.responded-text');
                        if (icon) icon.innerText = '✅';
                        if (text) text.innerText = 'Откликнулся';
                        respBtn.className = "responded-toggle-btn text-xs px-2.5 py-0.5 rounded-md transition flex items-center gap-1.5 border font-medium bg-emerald-950/90 text-emerald-300 border-emerald-700/80 hover:bg-emerald-900/90";
                    }

                    if (data.proposal_text && box && !document.getElementById(`proposal-text-${orderId}`)) {
                        box.className = "mt-3 pt-3 border-t border-slate-800 space-y-2";
                        box.innerHTML = `
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <span class="text-xs font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                                    <span>✉️</span> Сгенерированное Cover Letter (agy):
                                </span>
                                <div class="flex flex-wrap items-center gap-2">
                                    <button type="button" onclick="generateProposal('${orderId}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition active:scale-95 cursor-pointer">
                                        🔄 Перегенерировать
                                    </button>
                                    <span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-emerald-400 border border-slate-800 flex items-center gap-1 cursor-default">
                                        <span>✅</span> Отклик отправлен
                                    </span>
                                    <button type="button" onclick="copyProposal('proposal-text-${orderId}', this)" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium px-3 py-1 rounded-md transition flex items-center gap-1 border border-slate-700 active:scale-95 cursor-pointer select-none">
                                        <span>📋</span> Скопировать Cover Letter
                                    </button>
                                </div>
                            </div>
                            <div id="proposal-text-${orderId}" onclick="copyProposalText(this)" title="Нажмите, чтобы скопировать текст в буфер обмена" class="text-xs font-mono bg-slate-900/90 hover:bg-slate-900 text-slate-200 p-3.5 rounded-lg border border-slate-800 hover:border-slate-600 whitespace-pre-wrap leading-relaxed select-text cursor-pointer transition">${escapeHtml(data.proposal_text)}</div>
                        `;
                    }

                    logClient('apply_hh_success', { order_id: orderId });
                    showToast(data.message || 'Отклик успешно отправлен на HeadHunter!');
                    applyClientFilters();
                } else if (data.status === 'api_forbidden') {
                    logClient('apply_hh_api_forbidden', { order_id: orderId });
                    btn.innerHTML = origHtml;
                    btn.disabled = false;

                    const letterToCopy = data.copy_letter || data.proposal_text;
                    if (letterToCopy) {
                        await copyToClipboard(letterToCopy);
                    }

                    if (data.proposal_text && box && !document.getElementById(`proposal-text-${orderId}`)) {
                        box.className = "mt-3 pt-3 border-t border-slate-800 space-y-2";
                        box.innerHTML = `
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <span class="text-xs font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                                    <span>✉️</span> Сгенерированное Cover Letter (agy):
                                </span>
                                <div class="flex flex-wrap items-center gap-2">
                                    <button type="button" onclick="generateProposal('${orderId}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition active:scale-95 cursor-pointer">
                                        🔄 Перегенерировать
                                    </button>
                                    <button type="button" onclick="copyProposal('proposal-text-${orderId}', this)" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium px-3 py-1 rounded-md transition flex items-center gap-1 border border-slate-700 active:scale-95 cursor-pointer select-none">
                                        <span>📋</span> Скопировать Cover Letter
                                    </button>
                                </div>
                            </div>
                            <div id="proposal-text-${orderId}" onclick="copyProposalText(this)" title="Нажмите, чтобы скопировать текст в буфер обмена" class="text-xs font-mono bg-slate-900/90 hover:bg-slate-900 text-slate-200 p-3.5 rounded-lg border border-slate-800 hover:border-slate-600 whitespace-pre-wrap leading-relaxed select-text cursor-pointer transition">${escapeHtml(data.proposal_text)}</div>
                        `;
                    }

                    showToast('Письмо скопировано в буфер! Открываем hh.ru...');
                    if (data.url) {
                        setTimeout(() => {
                            window.open(data.url, '_blank');
                        }, 400);
                    }
                } else if (data.status === 'closed' || data.status === 'not_found') {
                    logClient('apply_hh_closed', { order_id: orderId, msg: data.message });
                    btn.outerHTML = `<span class="text-xs px-2.5 py-1 rounded-md font-medium bg-slate-900/80 text-amber-400 border border-amber-900/40 flex items-center gap-1 cursor-default" title="${escapeHtml(data.message || 'Вакансия закрыта')}">
                        <span>⚠️</span> Вакансия закрыта на HH
                    </span>`;
                    const card = document.querySelector(`.order-card[data-id="${orderId}"]`);
                    if (card) {
                        card.classList.add('opacity-50');
                    }
                    showToast(data.message || 'Вакансия закрыта на hh.ru');
                } else if (data.need_auth) {
                    logClient('apply_hh_need_auth', { order_id: orderId });
                    btn.innerHTML = origHtml;
                    btn.disabled = false;
                    if (confirm((data.message || 'Требуется подключение HeadHunter.') + '\\n\\nПерейти к авторизации на hh.ru сейчас?')) {
                        window.location.href = data.auth_url || '/hh/auth';
                    }
                } else if (data.requires_test) {
                    logClient('apply_hh_requires_test', { order_id: orderId });
                    btn.innerHTML = origHtml;
                    btn.disabled = false;
                    alert((data.message || 'Работодатель требует прохождения опросника/теста.') + '\\n\\nОткройте вакансию на hh.ru и ответьте на вопросы работодателя.');
                    if (data.url) {
                        window.open(data.url, '_blank');
                    }
                } else {
                    logClient('apply_hh_failed', { type: 'error', order_id: orderId, msg: data.error || data.message });
                    btn.innerHTML = origHtml;
                    btn.disabled = false;
                    alert(data.error || data.message || 'Ошибка отправки отклика.');
                }
            } catch (e) {
                logClient('apply_hh_exception', { type: 'error', order_id: orderId, msg: String(e) });
                if (timerInterval) clearInterval(timerInterval);
                if (progressEl) progressEl.remove();
                btn.innerHTML = origHtml;
                btn.disabled = false;
                alert('Сетевая ошибка при отклике: ' + e);
            }
        }

        async function toggleSkipped(orderId, btn) {
            if (!orderId) return;
            try {
                const resp = await fetch(`/api/orders/${orderId}/toggle-skipped`, { method: 'POST' });
                const data = await resp.json();
                if (data.ok) {
                    const card = document.querySelector(`.order-card[data-id="${orderId}"]`);
                    const isSkipped = !!data.is_skipped;
                    if (card) {
                        card.setAttribute('data-skipped', isSkipped ? '1' : '0');
                        if (isSkipped) {
                            card.classList.add('opacity-45', 'border-rose-950/40');
                        } else {
                            card.classList.remove('opacity-45', 'border-rose-950/40');
                        }
                    }
                    if (btn) {
                        const icon = btn.querySelector('.skip-icon');
                        const text = btn.querySelector('.skip-text');
                        if (icon) icon.innerText = isSkipped ? '↩️' : '⏭️';
                        if (text) text.innerText = isSkipped ? 'Вернуть' : 'Скип';
                        if (isSkipped) {
                            btn.className = "skip-toggle-btn text-xs px-2 py-0.5 rounded-md transition flex items-center gap-1 border font-medium bg-rose-950/90 text-rose-300 border-rose-700/80 hover:bg-rose-900/90";
                        } else {
                            btn.className = "skip-toggle-btn text-xs px-2 py-0.5 rounded-md transition flex items-center gap-1 border font-medium bg-slate-950 text-slate-400 border-slate-800 hover:text-rose-300 hover:border-slate-700";
                        }
                    }
                    showToast(isSkipped ? 'Заказ скрыт (скипнут)' : 'Заказ возвращен');
                    applyClientFilters();
                }
            } catch (e) {
                alert('Ошибка обновления статуса скипа: ' + e);
            }
        }

        function applyClientFilters() {
            const queryEl = document.getElementById('orderSearch');
            const query = queryEl ? queryEl.value.toLowerCase().trim() : '';
            const minEl = document.getElementById('filterPriceMin');
            const minPrice = minEl && minEl.value ? parseFloat(minEl.value) : null;
            const maxEl = document.getElementById('filterPriceMax');
            const maxPrice = maxEl && maxEl.value ? parseFloat(maxEl.value) : null;
            const sortEl = document.getElementById('orderSortSelect');
            const sortMode = sortEl ? sortEl.value : 'default';
            const hideRespondedEl = document.getElementById('filterHideResponded');
            const hideResponded = hideRespondedEl ? hideRespondedEl.checked : false;
            try { localStorage.setItem('hideResponded', hideResponded ? '1' : '0'); } catch(e){}

            const showSkippedEl = document.getElementById('filterShowSkipped');
            const showSkipped = showSkippedEl ? showSkippedEl.checked : false;
            try { localStorage.setItem('showSkipped', showSkipped ? '1' : '0'); } catch(e){}

            const urlParams = new URLSearchParams(window.location.search);
            const currentTab = urlParams.get('tab') || 'hot';
            const targetOrderId = urlParams.get('order_id') || (window.location.hash.startsWith('#order-') ? window.location.hash.replace('#order-', '') : null);

            const container = document.getElementById('ordersContainer');
            if (!container) return;
            const cards = Array.from(container.querySelectorAll('.order-card'));

            let visibleCount = 0;
            cards.forEach(card => {
                // Если карточка является целевой (передана в URL или hash), она всегда остается видимой
                if (targetOrderId && card.getAttribute('data-id') === targetOrderId) {
                    card.style.display = 'block';
                    visibleCount++;
                    return;
                }

                const title = card.getAttribute('data-title') || '';
                const desc = card.getAttribute('data-desc') || '';
                const price = parseFloat(card.getAttribute('data-price') || '0');
                const isResponded = card.getAttribute('data-responded') === '1';
                const isSkipped = card.getAttribute('data-skipped') === '1';

                // Поиск по тексту
                const matchesText = !query || title.includes(query) || desc.includes(query);

                // Фильтр по тематике/тегу
                let matchesTopic = true;
                if (activeTopic === 'ai-first') {
                    const isAiFirst = (card.getAttribute('data-ai-first') === '1');
                    matchesTopic = isAiFirst || title.includes('ai-first') || title.includes('ai first') || desc.includes('ai-first') || desc.includes('agentic');
                } else if (activeTopic !== 'all') {
                    matchesTopic = title.includes(activeTopic) || desc.includes(activeTopic);
                }

                // Фильтр по диапазону цен
                let matchesPrice = true;
                if (minPrice !== null && price > 0 && price < minPrice) matchesPrice = false;
                if (maxPrice !== null && price > 0 && price > maxPrice) matchesPrice = false;

                // Фильтр скрытия уже отправленных откликов
                let matchesResponded = true;
                if (hideResponded && isResponded && currentTab !== 'responded') {
                    matchesResponded = false;
                }

                // Фильтр скрытия пропущенных (скипнутых) заказов
                let matchesSkipped = true;
                if (isSkipped && !showSkipped && currentTab !== 'skipped') {
                    matchesSkipped = false;
                }

                if (matchesText && matchesTopic && matchesPrice && matchesResponded && matchesSkipped) {
                    card.style.display = 'block';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            // Сортировка
            cards.sort((a, b) => {
                if (sortMode === 'score_desc') {
                    const scoreA = parseFloat(a.getAttribute('data-score') || '0');
                    const scoreB = parseFloat(b.getAttribute('data-score') || '0');
                    return scoreB - scoreA;
                }
                if (sortMode === 'price_desc') {
                    const priceA = parseFloat(a.getAttribute('data-price') || '0');
                    const priceB = parseFloat(b.getAttribute('data-price') || '0');
                    return priceB - priceA;
                }
                if (sortMode === 'price_asc') {
                    const priceA = parseFloat(a.getAttribute('data-price') || '0');
                    const priceB = parseFloat(b.getAttribute('data-price') || '0');
                    if (priceA === 0 && priceB > 0) return 1;
                    if (priceB === 0 && priceA > 0) return -1;
                    return priceA - priceB;
                }
                // default: по времени поступления в систему (новые заказы сверху)
                const idA = parseInt(a.getAttribute('data-id') || '0', 10);
                const idB = parseInt(b.getAttribute('data-id') || '0', 10);
                return idB - idA;
            });
            cards.forEach(card => container.appendChild(card));

            const countBadge = document.getElementById('filterCountBadge');
            if (countBadge) {
                countBadge.innerText = `Найдено: ${visibleCount} из ${cards.length}`;
            }
        }

        function filterOrdersClient() {
            applyClientFilters();
        }

        function setQuickChatPrompt(orderId, text) {
            const input = document.getElementById(`chat-input-${orderId}`);
            if (input) {
                input.value = text;
                input.focus();
            }
        }

        async function toggleOrderChat(orderId) {
            const container = document.getElementById(`chat-container-${orderId}`);
            if (!container) return;
            const isHidden = container.classList.contains('hidden');
            if (isHidden) {
                container.classList.remove('hidden');
                await loadOrderChatMessages(orderId);
                const input = document.getElementById(`chat-input-${orderId}`);
                if (input) input.focus();
            } else {
                container.classList.add('hidden');
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function loadOrderChatMessages(orderId) {
            const box = document.getElementById(`chat-messages-${orderId}`);
            if (!box) return;
            try {
                const res = await fetch(`/api/orders/${orderId}/chat`);
                const data = await res.json();
                if (data.ok && Array.isArray(data.messages)) {
                    renderChatMessages(orderId, data.messages);
                } else {
                    box.innerHTML = `<div class="text-slate-500 text-center py-2">Не удалось загрузить историю диалога.</div>`;
                }
            } catch (e) {
                box.innerHTML = `<div class="text-red-400 text-center py-2">Ошибка подключения: ${escapeHtml(e.message)}</div>`;
            }
        }

        function renderChatMessages(orderId, messages) {
            const box = document.getElementById(`chat-messages-${orderId}`);
            if (!box) return;
            if (!messages || messages.length === 0) {
                box.innerHTML = `
                    <div class="text-slate-500 text-center py-3 bg-slate-900/40 rounded-lg border border-slate-800/60">
                        <p class="text-slate-400 font-medium text-xs">Нет сообщений в диалоге.</p>
                        <p class="text-[11px] text-slate-500 mt-0.5">Задай вопрос по рискам, стеку, переписке или оценке бюджета.</p>
                    </div>
                `;
                return;
            }

            let html = '';
            messages.forEach(m => {
                const isUser = m.role === 'user';
                const timeStr = m.created_at ? m.created_at.substring(11, 16) : '';
                if (isUser) {
                    html += `
                        <div class="flex justify-end">
                            <div class="max-w-[85%] bg-indigo-950/80 border border-indigo-800/60 rounded-xl rounded-tr-sm p-2.5 text-slate-100 space-y-1">
                                <div class="flex items-center justify-between gap-3 text-[10px] text-indigo-300 font-semibold">
                                    <span>👤 Андрей</span>
                                    ${timeStr ? `<span class="font-mono text-slate-400">${timeStr}</span>` : ''}
                                </div>
                                <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(m.message)}</div>
                            </div>
                        </div>
                    `;
                } else {
                    const modelName = m.model || 'assistant';
                    const isAgy = modelName.toLowerCase().includes('antigravity') || modelName.toLowerCase().includes('agy');
                    const badgeBg = isAgy ? 'bg-purple-950/80 border-purple-800/60 text-purple-300' : 'bg-amber-950/80 border-amber-800/60 text-amber-300';
                    const icon = isAgy ? '✨' : '⚡';
                    html += `
                        <div class="flex justify-start">
                            <div class="max-w-[90%] bg-slate-900 border border-slate-800 rounded-xl rounded-tl-sm p-3 text-slate-200 space-y-1.5 shadow-sm">
                                <div class="flex items-center justify-between gap-3 text-[10px]">
                                    <span class="px-1.5 py-0.5 rounded border ${badgeBg} font-mono flex items-center gap-1 font-semibold">
                                        <span>${icon}</span> ${escapeHtml(modelName)}
                                    </span>
                                    ${timeStr ? `<span class="font-mono text-slate-500">${timeStr}</span>` : ''}
                                </div>
                                <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(m.message)}</div>
                            </div>
                        </div>
                    `;
                }
            });
            box.innerHTML = html;
            box.scrollTop = box.scrollHeight;
        }

        async function sendOrderMessage(orderId) {
            const input = document.getElementById(`chat-input-${orderId}`);
            const btn = document.getElementById(`chat-send-btn-${orderId}`);
            const modelSelect = document.getElementById(`chat-model-${orderId}`);
            if (!input || !btn || btn.disabled) return;

            const text = input.value.trim();
            if (!text) return;

            const modelVal = modelSelect ? modelSelect.value : 'auto';
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            const origBtnHtml = btn.innerHTML;
            btn.innerHTML = '<span>⏳ Думает...</span>';

            const box = document.getElementById(`chat-messages-${orderId}`);
            const tempBubbleId = `temp-bubble-${Date.now()}`;
            const tempUserBubble = `
                <div id="${tempBubbleId}" class="flex justify-end">
                    <div class="max-w-[85%] bg-indigo-950/80 border border-indigo-800/60 rounded-xl rounded-tr-sm p-2.5 text-slate-100 space-y-1">
                        <div class="flex items-center justify-between gap-3 text-[10px] text-indigo-300 font-semibold">
                            <span>👤 Андрей</span>
                            <span class="font-mono text-slate-400">сейчас</span>
                        </div>
                        <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(text)}</div>
                    </div>
                </div>
            `;
            const hadNoMessages = box && box.innerText.includes('Нет сообщений');
            if (hadNoMessages) {
                box.innerHTML = tempUserBubble;
            } else if (box) {
                box.insertAdjacentHTML('beforeend', tempUserBubble);
                box.scrollTop = box.scrollHeight;
            }

            try {
                const res = await fetch(`/api/orders/${orderId}/chat`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, model: modelVal })
                });
                const data = await res.json();
                if (data.ok && data.reply) {
                    await loadOrderChatMessages(orderId);
                    const badge = document.getElementById(`chat-badge-${orderId}`);
                    if (badge) {
                        const cur = parseInt(badge.innerText || '0', 10);
                        badge.innerText = isNaN(cur) ? 2 : cur + 2;
                        badge.classList.remove('hidden');
                    }
                } else {
                    alert('Ошибка ответа модели: ' + (data.error || 'не удалось получить ответ'));
                    // Restore text to input on error
                    input.value = text;
                    const tempEl = document.getElementById(tempBubbleId);
                    if (tempEl) tempEl.remove();
                    if (hadNoMessages) await loadOrderChatMessages(orderId);
                }
            } catch (e) {
                alert('Сетевая ошибка при отправке вопроса: ' + e);
                input.value = text;
                const tempEl = document.getElementById(tempBubbleId);
                if (tempEl) tempEl.remove();
                if (hadNoMessages) await loadOrderChatMessages(orderId);
            } finally {
                input.disabled = false;
                btn.disabled = false;
                btn.innerHTML = origBtnHtml;
                input.focus();
            }
        }

        window.toggleChat = toggleOrderChat;
        window.sendOrderChatMessage = sendOrderMessage;

        async function saveYamlConfig() {
            const editor = document.getElementById('yamlConfigEditor');
            if (!editor) return;
            const yamlText = editor.value;
            const btn = document.getElementById('saveYamlBtn');
            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>⏳ Проверка схемы...</span>';
            }
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ yaml: yamlText })
                });
                const data = await res.json();
                if (data.ok) {
                    alert('✅ Конфигурация успешно сохранена и применена!');
                    window.location.reload();
                } else {
                    alert('❌ Ошибка валидации конфигурации:\\n' + (data.error || 'Неверный формат YAML'));
                }
            } catch (e) {
                alert('❌ Ошибка отправки запроса: ' + e);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        }

        async function saveGuiConfig() {
            if (!document.getElementById('cfg_filter_keywords')) return;
            const btn = document.getElementById('saveGuiConfigBtn');
            const origHtml = btn ? btn.innerHTML : '';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>⏳ Сохранение...</span>';
            }

            try {
                const getVal = id => {
                    const el = document.getElementById(id);
                    return el ? el.value : '';
                };
                const getInt = (id, defVal = 0) => {
                    const val = parseInt(getVal(id), 10);
                    return isNaN(val) ? defVal : val;
                };
                const getChecked = id => {
                    const el = document.getElementById(id);
                    return el ? el.checked : false;
                };
                const getLines = id => {
                    const val = getVal(id);
                    return val.split('\\n').map(s => s.trim()).filter(Boolean);
                };

                const payload = {
                    polling: {
                        interval_seconds: getInt('cfg_poll_interval', 180),
                        vacancies_interval_seconds: getInt('cfg_poll_vac_interval', 1800),
                        kwork_interval: getInt('cfg_poll_kwork', 180),
                        fl_interval: getInt('cfg_poll_fl', 180),
                        initial_backfill: getChecked('cfg_poll_backfill')
                    },
                    storage: {
                        db_path: getVal('cfg_storage_db').trim() || 'data/jobs.db'
                    },
                    web: {
                        host: getVal('cfg_web_host').trim() || '0.0.0.0',
                        port: getInt('cfg_web_port', 8086)
                    },
                    filter: {
                        min_budget: getInt('cfg_filter_min_budget', 10000),
                        hot_score_threshold: getInt('cfg_filter_hot_threshold', 7),
                        vacancy_hot_score_threshold: getInt('cfg_filter_vac_hot_threshold', 8),
                        vacancy_min_salary: getInt('cfg_filter_vac_min_salary', 80000),
                        vacancy_allow_negotiable: getChecked('cfg_filter_vac_negotiable'),
                        filter_pro_only: getChecked('cfg_filter_pro_only'),
                        keywords: getLines('cfg_filter_keywords'),
                        stop_words: getLines('cfg_filter_stopwords')
                    },
                    llm: {
                        provider: getVal('cfg_llm_provider') || 'antigravity',
                        antigravity: {
                            model: getVal('cfg_agy_model').trim() || 'gemini-3.8-flash-medium',
                            effort: getVal('cfg_agy_effort') || 'medium'
                        }
                    },
                    collectors: {
                        hh_ru: {
                            queries: getLines('cfg_hh_queries')
                        },
                        habr_career: {
                            queries: getLines('cfg_habr_queries')
                        }
                    }
                };

                const res = await fetch('/api/config', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: payload })
                });
                const data = await res.json();
                if (data.ok) {
                    alert('✅ Настройки успешно сохранены в config.yml и применены!');
                    window.location.reload();
                } else {
                    alert('❌ Ошибка валидации настроек:\\n' + (data.error || 'Ошибка сохранения'));
                }
            } catch (e) {
                alert('❌ Ошибка отправки запроса: ' + e);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            }
        }

        async function lookupOrImportOrder() {
            const inputEl = document.getElementById('importOrderUrl');
            const btnEl = document.getElementById('importOrderBtn');
            const labelEl = document.getElementById('importBtnLabel');
            if (!inputEl) return;

            const rawUrl = (inputEl.value || '').trim();
            if (!rawUrl || (!rawUrl.startsWith('http://') && !rawUrl.startsWith('https://'))) {
                alert('Пожалуйста, введите корректную ссылку, начинающуюся с http:// или https://');
                inputEl.focus();
                return;
            }

            const origHtml = labelEl ? labelEl.innerHTML : '';
            if (btnEl) btnEl.disabled = true;
            if (labelEl) labelEl.innerHTML = 'Загрузка и анализ...';

            try {
                const res = await fetch('/api/orders/lookup-or-add', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: rawUrl })
                });
                const data = await res.json();

                if (!res.ok || !data.ok) {
                    alert('Ошибка: ' + (data.error || 'Не удалось обработать ссылку'));
                    return;
                }

                const order = data.order;
                const status = data.status;

                const isHh = (order.source === 'hh_ru' || order.source === 'habr_career');
                const targetSection = isHh ? 'hh_ru' : 'freelance';
                const targetTab = (order.priority === 'trash') ? 'trash' : ((order.priority === 'hot') ? 'hot' : 'all');
                const targetUrl = `/?section=${targetSection}&tab=${targetTab}&order_id=${order.id}#order-${order.id}`;

                // 1. Проверяем, есть ли уже карточка на текущей странице
                const card = document.querySelector(`.order-card[data-id="${order.id}"]`);
                if (card) {
                    card.style.display = 'block';
                    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    card.classList.add('ring-4', 'ring-amber-400', 'border-amber-400');
                    setTimeout(() => {
                        card.classList.remove('ring-4', 'ring-amber-400', 'border-amber-400');
                    }, 4000);
                    showToast(`Заказ найден в базе (ID #${order.id})! Перешли к нему.`);
                } else {
                    const toastMsg = (status === 'created')
                        ? `Заказ добавлен и проанализирован (ID #${order.id})! Перенаправляем...`
                        : `Заказ найден в базе (ID #${order.id})! Перенаправляем...`;
                    showToast(toastMsg);
                    inputEl.value = '';
                    setTimeout(() => {
                        const currentPathAndQuery = window.location.pathname + window.location.search;
                        const targetPathAndQuery = targetUrl.split('#')[0];
                        if (currentPathAndQuery === targetPathAndQuery) {
                            window.location.hash = `order-${order.id}`;
                            window.location.reload();
                        } else {
                            window.location.href = targetUrl;
                        }
                    }, 400);
                }
            } catch (err) {
                alert('Сетевая ошибка при анализе ссылки: ' + err);
            } finally {
                if (btnEl) btnEl.disabled = false;
                if (labelEl) labelEl.innerHTML = origHtml || 'Найти или Анализировать';
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            try {
                const savedHide = localStorage.getItem('hideResponded');
                const hideRespondedEl = document.getElementById('filterHideResponded');
                if (savedHide === '1' && hideRespondedEl) {
                    hideRespondedEl.checked = true;
                    applyClientFilters();
                }
            } catch(e) {}

            try {
                const savedShowSkipped = localStorage.getItem('showSkipped');
                const showSkippedEl = document.getElementById('filterShowSkipped');
                if (savedShowSkipped === '1' && showSkippedEl) {
                    showSkippedEl.checked = true;
                    applyClientFilters();
                }
            } catch(e) {}

            try {
                const urlParams = new URLSearchParams(window.location.search);
                const targetId = urlParams.get('order_id') || (window.location.hash.startsWith('#order-') ? window.location.hash.replace('#order-', '') : null);
                if (targetId) {
                    const targetCard = document.querySelector(`.order-card[data-id="${targetId}"]`);
                    if (targetCard) {
                        targetCard.style.display = 'block';
                        setTimeout(() => {
                            targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            targetCard.classList.add('ring-4', 'ring-emerald-400', 'border-emerald-400');
                            setTimeout(() => {
                                targetCard.classList.remove('ring-4', 'ring-emerald-400', 'border-emerald-400');
                            }, 5000);
                        }, 200);
                    }
                }
            } catch(e) {}
        });

        function scrollToTop() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        }

        window.addEventListener('scroll', () => {
            const btn = document.getElementById('scrollToTopBtn');
            if (!btn) return;
            if (window.scrollY > 350) {
                btn.classList.remove('opacity-0', 'translate-y-10', 'pointer-events-none');
                btn.classList.add('opacity-100', 'translate-y-0');
            } else {
                btn.classList.add('opacity-0', 'translate-y-10', 'pointer-events-none');
                btn.classList.remove('opacity-100', 'translate-y-0');
            }
        }, { passive: true });
    </script>
</body>
</html>
"""


security = HTTPBasic(realm="Freelance Leads Monitor", auto_error=False)


def verify_basic_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> str:
    """Проверка HTTP Basic Auth учетных данных для защиты дашборда и API."""
    # Публичный эндпоинт проверки здоровья и телеметрии
    if request.url.path in ("/health", "/api/client-log"):
        return "public"

    if not getattr(settings, "WEB_AUTH_ENABLED", True):
        return "anonymous"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": 'Basic realm="Freelance Leads Monitor"'},
        )

    expected_username = getattr(settings, "WEB_AUTH_USERNAME", "Horizontal42")
    expected_password = getattr(settings, "WEB_AUTH_PASSWORD", "qaz403111")

    is_correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"), expected_username.encode("utf8")
    )
    is_correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"), expected_password.encode("utf8")
    )

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": 'Basic realm="Freelance Leads Monitor"'},
        )
    return credentials.username


def create_web_app(
    repo: Optional[OrderRepository] = None,
    enable_auth: Optional[bool] = None,
) -> FastAPI:
    """Создать и настроить экземпляр FastAPI приложения с защитой по HTTP Basic Auth."""
    auth_dep = []
    auth_active = getattr(settings, "WEB_AUTH_ENABLED", True) if enable_auth is None else enable_auth
    if auth_active:
        auth_dep.append(Depends(verify_basic_auth))

    app = FastAPI(
        title="Freelance Leads Monitor",
        description="Web dashboard for monitoring freelance leads on jobs.3dvex.ru",
        version="0.3.0",
        dependencies=auth_dep,
    )

    @app.middleware("http")
    async def add_no_cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    repository = repo or OrderRepository()

    @app.post("/api/client-log")
    async def api_client_log(request: Request):
        """Логирование действий, кликов и ошибок с клиентской стороны (браузера)."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        log_type = body.get("type", "info")
        action = body.get("action", "")
        order_id = body.get("order_id") or ""
        msg = body.get("msg") or ""
        stack = body.get("stack") or ""
        ua = request.headers.get("user-agent", "")[:120]
        if log_type == "error":
            logger.error("[CLIENT-ERROR] action=%s order=%s msg=%s stack=%s ua=%s", action, order_id, msg, stack, ua)
        else:
            logger.info("[CLIENT-LOG] action=%s order=%s msg=%s ua=%s", action, order_id, msg, ua)
        return JSONResponse({"ok": True})

    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard(
        request: Request,
        section: str = Query("freelance", description="Раздел сайта: freelance (биржи фриланса) или hh_ru (вакансии HeadHunter)"),
        tab: str = Query("hot", description="Активная вкладка (hot, all, normal, trash, analytics, rules, profile)"),
        source: Optional[str] = Query(None, description="Фильтр по источнику (kwork, fl_ru, freelance_ru, pchel_net, remote_job, hh_ru)"),
        free_only: int = Query(0, description="Фильтр только бесплатных откликов (1 - без PRO, 0 - все)"),
        order_id: Optional[int] = Query(None, description="ID конкретного заказа для целевого показа в ленте"),
        limit: int = Query(80, ge=1, le=300),
    ):
        active_section = "hh_ru" if section.strip().lower() in ["hh_ru", "hh"] else "freelance"
        active_tab = tab.strip().lower()
        s_filter = source.strip().lower() if source else None
        only_free_flag = bool(free_only)

        # Определяем фильтр приоритета по вкладке
        p_filter: Optional[str] = None
        if active_tab == "hot":
            p_filter = "hot"
        elif active_tab == "normal":
            p_filter = "normal"
        elif active_tab == "trash":
            p_filter = "trash"
        elif active_tab == "all":
            p_filter = None

        raw_orders: List[Dict[str, Any]] = []
        if active_tab in ["hot", "all", "normal", "trash", "responded", "skipped"]:
            raw_orders = await repository.get_recent_orders(
                limit=limit,
                priority=p_filter,
                source=s_filter,
                only_free=only_free_flag,
                section=active_section,
                only_responded=(active_tab == "responded"),
                only_skipped=(active_tab == "skipped"),
                hide_skipped=(active_tab not in ["skipped", "responded"]),
            )

        def check_is_ai_first(it: Dict[str, Any]) -> bool:
            check_str = f"{it.get('title') or ''}\n{it.get('description') or ''}\n{it.get('attachments_text') or ''}".lower()
            return bool(re.search(r"ai[- ]?first|ai[- ]?native|agentic|ai[- ]?агент|ai[- ]?agents?", check_str))

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
            item["is_ai_first"] = check_is_ai_first(item)
            formatted_orders.append(item)

        if order_id:
            # Гарантируем, что целевой заказ присутствует на странице даже если он за пределами limit
            target_order = await repository.get_by_id(order_id)
            if target_order:
                # Если раздел не был явно передан в запросе, настраиваем под целевой заказ
                if "section" not in request.query_params:
                    order_is_hh = target_order.get("source") in ["hh_ru", "habr_career"]
                    active_section = "hh_ru" if order_is_hh else "freelance"

                # Удаляем старое вхождение если есть и вставляем на самый верх
                formatted_orders = [o for o in formatted_orders if o.get("id") != order_id]
                item = dict(target_order)
                if item.get("analysis_json"):
                    try:
                        item["analysis"] = json.loads(item["analysis_json"])
                    except Exception:
                        item["analysis"] = None
                else:
                    item["analysis"] = None
                item["is_ai_first"] = check_is_ai_first(item)
                formatted_orders.insert(0, item)

        extended_stats = await repository.get_extended_stats()
        current_stats = (
            extended_stats.get("hh_ru", {})
            if active_section == "hh_ru"
            else extended_stats.get("freelance", {})
        )
        if not current_stats:
            current_stats = extended_stats

        current_settings = await repository.get_all_settings()
        default_settings_map = {
            "platform_kwork": True,
            "platform_fl_ru": True,
            "platform_freelance_ru": True,
            "platform_pchel_net": True,
            "platform_hh_ru": True,
            "platform_habr_career": True,
            "filter_pro_only": False,
            "min_budget": 10000,
            "quick_min_budget": 2000,
            "allow_quick_orders": True,
            "hot_score_threshold": 7,
            "vacancy_city": "all",
            "vacancy_work_format": "all",
            "vacancy_min_salary": 0,
        }
        effective_settings = {**default_settings_map, **current_settings}

        health_data = None
        if active_tab == "health":
            from src.services.health_check import HealthCheckService
            try:
                health_data = await HealthCheckService().run_full_check()
            except Exception as e:
                logger.error("Ошибка при выполнении health check: %s", e)
                health_data = {
                    "all_ok": False,
                    "checked_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                    "exchanges": [],
                    "services": [],
                    "error": str(e),
                }

        from src.services.uptime import get_system_status_info
        uptime_info = get_system_status_info()

        from src.config import CONFIG_YAML_PATH
        raw_config_yaml = ""
        if CONFIG_YAML_PATH.exists():
            try:
                with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
                    raw_config_yaml = f.read()
            except Exception as e:
                logger.error("Ошибка чтения %s: %s", CONFIG_YAML_PATH, e)

        section_analytics = None
        if active_tab == "analytics":
            section_analytics = await repository.get_section_analytics(section=active_section)

        effective_keywords = current_settings.get("filter_keywords", settings.KEYWORDS)
        effective_stop_words = current_settings.get("filter_stop_words", settings.STOP_WORDS)
        default_drop_titles = [t.strip() for t in settings.COLLECTORS_HH_RU.drop_title.split("|") if t.strip()]
        effective_drop_titles = current_settings.get("filter_drop_titles", default_drop_titles)

        hh_svc = HhApplicantService(repository)
        hh_applicant_status = await hh_svc.get_applicant_status()

        template = Template(DASHBOARD_HTML, autoescape=True)
        html_content = template.render(
            orders=formatted_orders,
            active_section=active_section,
            stats=current_stats,
            current_stats=current_stats,
            extended_stats=extended_stats,
            section_analytics=section_analytics,
            active_tab=active_tab,
            selected_source=s_filter or "",
            free_only=1 if only_free_flag else 0,
            keywords=effective_keywords,
            stop_words=effective_stop_words,
            drop_titles=effective_drop_titles,
            llm_provider=settings.LLM_PROVIDER,
            hh_config=settings.COLLECTORS_HH_RU,
            dossier_items=settings.PROMPTS_CONFIG.projects_dossier,
            settings_map=effective_settings,
            hh_applicant_status=hh_applicant_status,
            health_data=health_data,
            uptime_info=uptime_info,
            raw_config_yaml=raw_config_yaml,
            yaml_app_config=settings.app_config,
            format_bullet_html=format_bullet_html,
        )
        return HTMLResponse(content=html_content)

    @app.get("/hh/auth")
    async def hh_auth_redirect():
        """Перенаправление на OAuth страницу авторизации HeadHunter."""
        hh_svc = HhApplicantService(repository)
        auth_url = hh_svc.get_auth_url()
        return RedirectResponse(url=auth_url)

    @app.get("/callback")
    async def hh_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
        """Callback для OAuth обмена авторизационного кода HeadHunter на токен."""
        if error or not code:
            err_param = error or "missing_code"
            return RedirectResponse(url=f"/?section=hh_ru&tab=settings&hh_error={err_param}")
        hh_svc = HhApplicantService(repository)
        res = await hh_svc.exchange_code(code)
        if res.get("ok"):
            return RedirectResponse(url="/?section=hh_ru&tab=settings&hh_connected=1")
        else:
            import urllib.parse
            err_msg = urllib.parse.quote(str(res.get("error", "auth_failed")))
            return RedirectResponse(url=f"/?section=hh_ru&tab=settings&hh_error={err_msg}")

    @app.post("/api/vacancies/{order_id}/apply")
    async def api_apply_vacancy(order_id: int):
        """Отправить отклик на вакансию HeadHunter в 1 клик через API соискателя."""
        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Вакансия не найдена в базе данных"})

        source = order_data.get("source")
        if source != "hh_ru" and source != SourcePlatform.HH_RU:
            return JSONResponse(status_code=400, content={"ok": False, "error": "1-click отклик доступен только для вакансий HeadHunter"})

        vac_id = order_data.get("external_id")
        if not vac_id:
            url = order_data.get("url") or ""
            m = re.search(r"/vacancy/(\d+)", url)
            if m:
                vac_id = m.group(1)

        if not vac_id:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Не удалось определить ID вакансии на hh.ru"})

        hh_svc = HhApplicantService(repository)
        status_info = await hh_svc.get_applicant_status()
        if not status_info.get("connected"):
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "need_auth": True,
                    "message": "Аккаунт HeadHunter не подключен. Авторизуйтесь для включения откликов в 1 клик.",
                    "auth_url": status_info.get("auth_url"),
                },
            )

        cover_letter = order_data.get("proposal_text")
        if not cover_letter and order_data.get("analysis_json"):
            try:
                an = json.loads(order_data["analysis_json"])
                cover_letter = an.get("proposal_text")
            except Exception:
                pass

        if not cover_letter:
            try:
                analysis_data = None
                if order_data.get("analysis_json"):
                    try:
                        analysis_data = json.loads(order_data["analysis_json"])
                    except Exception:
                        pass
                raw_order = RawOrder(
                    source=SourcePlatform.HH_RU,
                    external_id=str(vac_id),
                    title=order_data.get("title", ""),
                    description=order_data.get("description", ""),
                    url=order_data.get("url", ""),
                    price=order_data.get("price"),
                    currency=order_data.get("currency") or "RUB",
                    skills=[],
                    raw_data=order_data,
                )
                llm = get_llm_client()
                prop_res = await llm.generate_proposal(raw_order, analysis_data)
                cover_letter = str(prop_res)
                await repository.update_proposal(order_id=order_id, proposal_text=cover_letter)
            except Exception as e:
                logger.error("Ошибка автогенерации письма для вакансии HH #%s: %s", order_id, e, exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={"ok": False, "error": f"Ошибка генерации сопроводительного письма: {e}"},
                )

        result = await hh_svc.apply_to_vacancy(str(vac_id), cover_letter)
        if result.get("ok"):
            await repository.toggle_responded(order_id, is_responded=True)
            return JSONResponse(
                content={
                    "ok": True,
                    "status": "applied",
                    "message": result.get("message", "Отклик успешно отправлен на HeadHunter!"),
                    "proposal_text": cover_letter,
                }
            )

        result["proposal_text"] = cover_letter
        return JSONResponse(status_code=400, content=result)

    @app.post("/api/orders/{order_id}/toggle-responded")
    async def api_toggle_responded(order_id: int):
        """Переключить статус отклика (откликнулся / не откликнулся)."""
        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Заказ или вакансия не найдена"})

        new_state = await repository.toggle_responded(order_id)
        return JSONResponse(content={"ok": True, "is_responded": new_state})

    @app.post("/api/orders/{order_id}/toggle-skipped")
    async def api_toggle_skipped(order_id: int):
        """Переключить статус пропуска (скипа) заказа или вакансии."""
        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Заказ или вакансия не найдена"})

        new_state = await repository.toggle_skipped(order_id)
        return JSONResponse(content={"ok": True, "is_skipped": new_state})

    @app.post("/api/orders/{order_id}/generate-proposal")
    async def api_generate_proposal(order_id: int):
        """Сгенерировать отклик или Cover Letter для заказа/вакансии по требованию."""
        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Заказ или вакансия не найдена"})

        from src.analyzer.factory import get_llm_client
        llm_client = get_llm_client()

        try:
            try:
                src_platform = SourcePlatform(order_data["source"])
            except Exception:
                src_platform = SourcePlatform.CUSTOM

            raw_order = RawOrder(
                source=src_platform,
                external_id=order_data["external_id"],
                title=order_data["title"],
                description=order_data["description"] or "",
                url=order_data["url"],
                price=order_data["price"],
                is_negotiable=bool(order_data.get("is_negotiable", 0)),
                is_pro_only=bool(order_data.get("is_pro_only", 0)),
                attachments_text=order_data.get("attachments_text"),
            )

            analysis_data = None
            if order_data.get("analysis_json"):
                try:
                    analysis_data = json.loads(order_data["analysis_json"])
                except Exception:
                    analysis_data = None

            proposal_res = await llm_client.generate_proposal(raw_order, analysis_data)
            proposal_text = str(proposal_res)
            rec_price = getattr(proposal_res, "recommended_price", None)
            mkt_price = getattr(proposal_res, "market_price", None)
            price_just = getattr(proposal_res, "price_justification", None)
            est_days = getattr(proposal_res, "estimated_days", None)

            await repository.update_proposal(
                order_id,
                proposal_text=proposal_text,
                recommended_price=rec_price,
                market_price=mkt_price,
                price_justification=price_just,
                estimated_days=est_days,
            )
            is_hh = (raw_order.source == SourcePlatform.HH_RU)
            return {
                "ok": True,
                "is_hh": is_hh,
                "source": raw_order.source.value,
                "proposal_text": proposal_text,
                "recommended_price": rec_price,
                "market_price": mkt_price,
                "price_justification": price_just,
                "estimated_days": est_days,
            }
        except Exception as e:
            logger.error("Ошибка при генерации для заказа/вакансии #%d: %s", order_id, e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.get("/api/orders/{order_id}/chat")
    async def get_order_chat(order_id: int):
        """Получить историю переписки по заказу."""
        messages = await repository.get_chat_messages(order_id)
        return {"ok": True, "messages": messages}

    @app.post("/api/orders/{order_id}/chat")
    async def post_order_chat(order_id: int, request: Request):
        """Задать вопрос модели по заказу и получить ответ с сохранением истории."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Невалидный JSON"})

        user_message = str(body.get("message", "")).strip()
        model_choice = str(body.get("model", "auto")).strip()

        if not user_message:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Сообщение не может быть пустым"})

        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Заказ или вакансия не найдена"})

        from src.analyzer.factory import get_llm_client
        llm_client = get_llm_client()

        try:
            try:
                src_platform = SourcePlatform(order_data["source"])
            except Exception:
                src_platform = SourcePlatform.CUSTOM

            raw_order = RawOrder(
                source=src_platform,
                external_id=order_data["external_id"],
                title=order_data["title"],
                description=order_data["description"] or "",
                url=order_data["url"],
                price=order_data["price"],
                is_negotiable=bool(order_data.get("is_negotiable", 0)),
                is_pro_only=bool(order_data.get("is_pro_only", 0)),
                attachments_text=order_data.get("attachments_text"),
            )
            analysis_data = None
            if order_data.get("analysis_json"):
                try:
                    analysis_data = json.loads(order_data["analysis_json"])
                except Exception:
                    analysis_data = None
            proposal_text = order_data.get("proposal_text")
            history = await repository.get_chat_messages(order_id)

            # 1. Вызываем модель
            reply_text, model_used = await llm_client.chat_order(
                order=raw_order,
                analysis_data=analysis_data,
                proposal_text=proposal_text,
                history=history,
                user_message=user_message,
                model_preference=model_choice,
            )

            # 2. Сохраняем вопрос пользователя и ответ модели только после успешного ответа
            await repository.add_chat_message(
                order_id=order_id,
                role="user",
                model="user",
                message=user_message,
            )
            await repository.add_chat_message(
                order_id=order_id,
                role="assistant",
                model=model_used,
                message=reply_text,
            )

            return {
                "ok": True,
                "reply": reply_text,
                "model": model_used,
            }
        except Exception as e:
            logger.error("Ошибка в чате по заказу #%d: %s", order_id, e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.post("/api/orders/lookup-or-add", response_class=JSONResponse)
    async def api_lookup_or_add_order(request: Request):
        """Найти заказ или вакансию по URL в базе данных, либо скачать, добавить и проанализировать."""
        try:
            body = await request.json()
            url = (body.get("url") or "").strip()
            if not url:
                return JSONResponse(status_code=400, content={"ok": False, "error": "Поле url обязательно для заполнения"})

            from src.analyzer.factory import get_llm_client
            from src.services.order_importer import OrderImporterService

            importer = OrderImporterService()
            llm_client = get_llm_client()
            result = await importer.import_or_lookup(url=url, repo=repository, llm_client=llm_client)
            return JSONResponse(content=result)
        except Exception as e:
            logger.error("Ошибка при поиске или импорте заказа по URL: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": f"Ошибка обработки ссылки: {str(e)}"})

    @app.post("/api/orders/recalculate", response_class=JSONResponse)
    async def api_recalculate_orders(request: Request):
        """Локальный пересчет и переоценка заказов и вакансий в базе по актуальным правилам без внешних API."""
        try:
            body = await request.json()
            scope = body.get("scope", "trash")
            limit = int(body.get("limit", 300))
            analyze_llm = bool(body.get("analyze_llm", True))

            from src.analyzer.factory import get_llm_client
            from src.services.recalculator import DatabaseRecalculator

            recalculator = DatabaseRecalculator(repo=repository)
            llm_client = get_llm_client() if analyze_llm else None
            result = await recalculator.run(
                scope=scope,
                limit=limit,
                analyze_llm=analyze_llm,
                llm_client=llm_client,
            )
            return JSONResponse(content=result)
        except Exception as e:
            logger.error("Ошибка при локальном пересчете базы: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": f"Ошибка пересчета: {str(e)}"})

    @app.get("/api/orders", response_class=JSONResponse)
    async def get_orders_api(
        priority: Optional[str] = None,
        source: Optional[str] = None,
        section: Optional[str] = None,
        limit: int = 50,
    ):
        orders = await repository.get_recent_orders(
            limit=limit,
            priority=priority,
            source=source,
            section=section,
        )
        return {"orders": orders}

    @app.get("/api/stats", response_class=JSONResponse)
    async def get_stats_api():
        try:
            stats = await repository.get_extended_stats()
            return stats
        except Exception as e:
            logger.error("Ошибка получения статистики: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.get("/api/health-check", response_class=JSONResponse)
    async def api_health_check_full():
        """Запустить полную проверку доступности бирж, LLM и базы данных."""
        try:
            from src.services.health_check import HealthCheckService
            from src.services.uptime import get_system_status_info
            service = HealthCheckService()
            result = await service.run_full_check()
            result["uptime"] = get_system_status_info()
            return result
        except Exception as e:
            logger.error("Ошибка проверки здоровья: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.get("/api/settings", response_class=JSONResponse)
    async def api_get_settings():
        """Получить все сохраненные настройки."""
        settings_map = await repository.get_all_settings()
        defaults = {
            "platform_kwork": True,
            "platform_fl_ru": True,
            "platform_freelance_ru": True,
            "platform_pchel_net": True,
            "platform_hh_ru": True,
            "platform_habr_career": True,
            "filter_pro_only": False,
            "min_budget": 10000,
            "quick_min_budget": 2000,
            "allow_quick_orders": True,
            "hot_score_threshold": 7,
            "vacancy_city": "all",
            "vacancy_work_format": "all",
            "vacancy_min_salary": 0,
            "vacancy_allow_negotiable": True,
        }
        return {"ok": True, "settings": {**defaults, **settings_map}}

    @app.post("/api/settings", response_class=JSONResponse)
    async def api_save_settings(request: Request):
        """Обновить настройки мониторинга."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Невалидный JSON"})

        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Ожидается JSON-объект"})

        allowed_keys = {
            "platform_kwork",
            "platform_fl_ru",
            "platform_freelance_ru",
            "platform_pchel_net",
            "platform_hh_ru",
            "platform_habr_career",
            "filter_pro_only",
            "min_budget",
            "quick_min_budget",
            "allow_quick_orders",
            "hot_score_threshold",
            "vacancy_city",
            "vacancy_work_format",
            "vacancy_min_salary",
            "vacancy_allow_negotiable",
            "filter_keywords",
            "filter_stop_words",
            "filter_drop_titles",
        }

        for key, val in body.items():
            if key in allowed_keys:
                await repository.set_setting(key, val)

        all_settings = await repository.get_all_settings()
        return {"ok": True, "settings": all_settings}

    @app.post("/api/settings/reset-rules", response_class=JSONResponse)
    async def api_reset_rules():
        """Сбросить кастомные правила фильтрации к значениям по умолчанию из config.yml."""
        for key in ["filter_keywords", "filter_stop_words", "filter_drop_titles"]:
            await repository.delete_setting(key)
        return {"ok": True}

    @app.get("/api/config", response_class=JSONResponse)
    async def api_get_config():
        """Получить текущий config.yml без секретов."""
        from src.config import CONFIG_YAML_PATH, settings
        if not CONFIG_YAML_PATH.exists():
            return JSONResponse(status_code=404, content={"ok": False, "error": "config.yml не найден"})

        with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
            raw_text = f.read()

        return {
            "ok": True,
            "yaml": raw_text,
            "config": settings.app_config.model_dump(),
        }

    @app.post("/api/config", response_class=JSONResponse)
    async def api_save_config(request: Request):
        """Сохранить и применить обновленный config.yml с валидацией схемы."""
        import yaml
        from src.config import CONFIG_YAML_PATH, YamlAppConfig, settings

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Невалидный JSON"})

        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "Ожидается JSON-объект"})

        yaml_text = body.get("yaml")
        config_dict = body.get("config")

        if yaml_text and isinstance(yaml_text, str):
            try:
                parsed = yaml.safe_load(yaml_text)
                if not isinstance(parsed, dict):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "YAML должен быть словарем"})
                validated = YamlAppConfig.model_validate(parsed)
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": f"Ошибка валидации YAML: {e}"})
        elif config_dict and isinstance(config_dict, dict):
            try:
                current_dict = settings.app_config.model_dump()
                if CONFIG_YAML_PATH.exists():
                    try:
                        with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
                            disk_data = yaml.safe_load(f)
                            if isinstance(disk_data, dict):
                                current_dict = disk_data
                    except Exception:
                        pass

                def deep_update(target: dict, source: dict) -> dict:
                    for k, v in source.items():
                        if isinstance(v, dict) and isinstance(target.get(k), dict):
                            deep_update(target[k], v)
                        else:
                            target[k] = v
                    return target

                merged = deep_update(current_dict, config_dict)
                validated = YamlAppConfig.model_validate(merged)
                yaml_text = yaml.dump(merged, allow_unicode=True, sort_keys=False)
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": f"Ошибка валидации настроек: {e}"})
        else:
            return JSONResponse(status_code=400, content={"ok": False, "error": "Поле yaml или config обязательно"})

        # Сохраняем на диск и применяем в памяти
        try:
            with open(CONFIG_YAML_PATH, "w", encoding="utf-8") as f:
                f.write(yaml_text)
            settings.app_config = validated
            return {"ok": True, "message": "Конфигурация успешно сохранена и применена"}
        except Exception as e:
            logger.error("Ошибка записи config.yml: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": f"Ошибка записи файла: {e}"})

    @app.api_route("/health", methods=["GET", "HEAD"])
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app

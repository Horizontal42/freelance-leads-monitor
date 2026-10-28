"""FastAPI Web Dashboard for Freelance Leads Monitor (jobs.3dvex.ru)."""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template
from src.config import settings
from src.models.order import OrderPriority, RawOrder, SourcePlatform
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans antialiased selection:bg-blue-600 selection:text-white">

    <!-- Top Navigation Header -->
    <header class="bg-slate-900/95 border-b border-slate-800 sticky top-0 z-50 backdrop-blur">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <span class="text-2xl">⚡</span>
                <div>
                    <h1 class="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                        Freelance Leads Monitor
                        <span class="text-xs font-mono font-normal px-2.5 py-0.5 rounded-full bg-blue-950 text-blue-300 border border-blue-800/60">jobs.3dvex.ru</span>
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
                    <a href="/?section=hh_ru&tab=trash" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'trash' %}active border-b-2 border-slate-500 text-slate-300 font-bold{% else %}text-slate-500 hover:text-slate-300{% endif %}">
                        <span>🗑</span> Отсеянные фильтрами
                        <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">{{ stats.trash }}</span>
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

        {% if active_tab in ['hot', 'all', 'normal', 'trash'] %}
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
                        <button type="button" onclick="setTopicFilter('бот', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🤖 Боты & TG</button>
                        <button type="button" onclick="setTopicFilter('парсер', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🕷 Парсинг</button>
                        <button type="button" onclick="setTopicFilter('ai', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🧠 ИИ & LLM</button>
                        <button type="button" onclick="setTopicFilter('fastapi', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">⚙️ Бэкенд</button>
                        <button type="button" onclick="setTopicFilter('битрикс', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🔗 CRM</button>
                    {% else %}
                        <button type="button" onclick="setTopicFilter('all', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-rose-600 text-white font-bold">Все</button>
                        <button type="button" onclick="setTopicFilter('ai', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🧠 AI & LLM</button>
                        <button type="button" onclick="setTopicFilter('python', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🐍 Python</button>
                        <button type="button" onclick="setTopicFilter('ml', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">📊 ML & Data</button>
                        <button type="button" onclick="setTopicFilter('удален', this)" class="topic-chip px-3 py-1 rounded-lg text-xs font-medium transition bg-slate-800 text-slate-300 hover:bg-slate-700">🏠 Удаленка</button>
                    {% endif %}
                </div>

                <!-- Price Range Filter Inputs -->
                <div class="flex items-center gap-2 text-xs">
                    <span class="text-slate-400 font-semibold uppercase">{% if active_section == 'hh_ru' %}З/П от:{% else %}Бюджет от:{% endif %}</span>
                    <input type="number" id="filterPriceMin" oninput="applyClientFilters()" placeholder="0 ₽" class="w-24 bg-slate-950 border border-slate-800 text-slate-200 rounded px-2.5 py-1 text-xs outline-none focus:border-blue-500 font-mono">
                    <span class="text-slate-500">до</span>
                    <input type="number" id="filterPriceMax" oninput="applyClientFilters()" placeholder="макс" class="w-24 bg-slate-950 border border-slate-800 text-slate-200 rounded px-2.5 py-1 text-xs outline-none focus:border-blue-500 font-mono">
                    <button type="button" onclick="resetFilters()" class="text-[11px] text-slate-400 hover:text-white px-2 py-1 bg-slate-800 rounded border border-slate-700 transition">Сброс</button>
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
                <div class="order-card bg-slate-900 border {% if order.priority == 'hot' %}border-amber-500/50 shadow-lg shadow-amber-950/20{% elif order.priority == 'trash' %}border-slate-800 opacity-60{% else %}border-slate-800{% endif %} p-5 rounded-xl transition hover:border-slate-700 space-y-3.5" data-title="{{ order.title|lower }}" data-desc="{{ order.description|lower }} {{ order.attachments_text|lower if order.attachments_text else '' }}" data-price="{{ order.price or 0 }}" data-score="{{ order.score or 0 }}" data-created="{{ order.created_at or '' }}">

                    <!-- Card Header Row -->
                    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div class="flex items-center space-x-2 flex-wrap gap-y-1">
                            <!-- Platform Badge -->
                            <span class="text-xs font-bold uppercase px-2.5 py-1 rounded-md {% if order.source == 'hh_ru' %}bg-rose-950 text-rose-300 border border-rose-800/60{% elif order.source == 'habr_career' %}bg-cyan-950 text-cyan-300 border border-cyan-800/60{% elif order.source == 'kwork' %}bg-emerald-950 text-emerald-300 border border-emerald-800/60{% elif order.source == 'fl_ru' %}bg-blue-950 text-blue-300 border border-blue-800/60{% elif order.source == 'freelance_ru' %}bg-purple-950 text-purple-300 border border-purple-800/60{% elif order.source == 'pchel_net' %}bg-amber-950 text-amber-300 border border-amber-800/60{% else %}bg-cyan-950 text-cyan-300 border border-cyan-800/60{% endif %}">
                                {{ 'Хабр Карьера' if order.source == 'habr_career' else (order.source|upper) }}
                            </span>

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

                            <span class="text-xs text-slate-400 font-mono bg-slate-950/80 border border-slate-800 px-2 py-0.5 rounded-md flex items-center gap-1" title="Дата и время">
                                🕒 {{ order.created_at[:16].replace('T', ' ') if order.created_at else 'Только что' }}
                            </span>
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
                                            <p class="text-slate-300 leading-relaxed">{{ order.analysis.company_overview }}</p>
                                        </div>
                                    {% endif %}

                                    <!-- Candidate Requirements -->
                                    {% if order.analysis.candidate_requirements %}
                                        <div class="bg-slate-900/80 border border-slate-800/80 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-slate-200 flex items-center gap-1.5">
                                                <span>🎯</span> Требования к кандидату:
                                            </div>
                                            <p class="text-slate-300 leading-relaxed">{{ order.analysis.candidate_requirements }}</p>
                                        </div>
                                    {% endif %}

                                    <!-- Job Responsibilities -->
                                    {% if order.analysis.job_responsibilities %}
                                        <div class="bg-slate-900/80 border border-slate-800/80 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-slate-200 flex items-center gap-1.5">
                                                <span>🛠</span> Чем предстоит заниматься:
                                            </div>
                                            <p class="text-slate-300 leading-relaxed">{{ order.analysis.job_responsibilities }}</p>
                                        </div>
                                    {% endif %}

                                    <!-- Andrei's Match Reason -->
                                    {% if order.analysis.match_reason %}
                                        <div class="bg-slate-900/80 border border-emerald-900/40 p-3 rounded-lg space-y-1">
                                            <div class="font-bold text-emerald-300 flex items-center gap-1.5">
                                                <span>💡</span> Соответствие резюме Андрея:
                                            </div>
                                            <p class="text-emerald-200 leading-relaxed">{{ order.analysis.match_reason }}</p>
                                        </div>
                                    {% endif %}

                                    <!-- Skills Gap & Counter Strategy -->
                                    {% if order.analysis.skills_gap and order.analysis.skills_gap != "Критичных пробелов нет" %}
                                        <div class="col-span-1 md:col-span-2 bg-slate-900/90 border border-amber-900/50 p-3 rounded-lg space-y-1.5">
                                            <div class="font-bold text-amber-400 flex items-center gap-1.5">
                                                <span>⚠️</span> Пробелы в требованиях (Skills Gap):
                                            </div>
                                            <p class="text-amber-200 text-xs leading-relaxed font-mono bg-amber-950/40 p-2 rounded border border-amber-900/40">{{ order.analysis.skills_gap }}</p>
                                            {% if order.analysis.skills_gap_counter %}
                                                <div class="text-[11px] text-slate-300 pt-1 flex items-start gap-1.5">
                                                    <span class="font-semibold text-emerald-400 shrink-0">🛡 Парирование в Cover Letter:</span>
                                                    <span class="text-slate-200">{{ order.analysis.skills_gap_counter }}</span>
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
                                <div id="proposal-box-{{ order.id }}">
                                    {% if order.proposal_text or (order.analysis and order.analysis.proposal_text) %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 space-y-2">
                                            <div class="flex items-center justify-between">
                                                <span class="text-xs font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                                                    <span>✉️</span> Сгенерированное Cover Letter (agy):
                                                </span>
                                                <div class="flex items-center space-x-2">
                                                    <button onclick="generateProposal('{{ order.id }}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition">
                                                        🔄 Перегенерировать
                                                    </button>
                                                    <button onclick="copyProposal('proposal-text-{{ order.id }}', this)" class="text-xs bg-rose-600 hover:bg-rose-500 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm">
                                                        <span>📋</span> Скопировать Cover Letter
                                                    </button>
                                                </div>
                                            </div>
                                            <div id="proposal-text-{{ order.id }}" class="text-xs font-mono bg-slate-900/90 text-slate-200 p-3.5 rounded-lg border border-slate-800 whitespace-pre-wrap leading-relaxed select-all">
{{ order.proposal_text or order.analysis.proposal_text }}</div>
                                        </div>
                                    {% else %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 flex items-center justify-between">
                                            <span class="text-xs text-slate-400">Сопроводительное письмо генерируется под конкретную вакансию.</span>
                                            <button onclick="generateProposal('{{ order.id }}', this)" class="text-xs bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white font-semibold px-4 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-md">
                                                <span>✨</span> Сгенерировать Cover Letter (agy)
                                            </button>
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
                                                    <button onclick="generateProposal('{{ order.id }}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition">
                                                        🔄 Перегенерировать
                                                    </button>
                                                    <button onclick="copyProposal('proposal-text-{{ order.id }}', this)" class="text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm">
                                                        <span>📋</span> Скопировать отклик
                                                    </button>
                                                </div>
                                            </div>
                                            <div id="proposal-text-{{ order.id }}" class="text-xs font-mono bg-slate-900/90 text-slate-200 p-3.5 rounded-lg border border-slate-800 whitespace-pre-wrap leading-relaxed select-all">
{{ order.proposal_text or order.analysis.proposal_text }}</div>
                                        </div>
                                    {% else %}
                                        <div class="mt-3 pt-3 border-t border-slate-800 flex items-center justify-between">
                                            <span class="text-xs text-slate-400">Отклик не генерировался для экономии квот.</span>
                                            <button onclick="generateProposal('{{ order.id }}', this)" class="text-xs bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold px-4 py-1.5 rounded-lg transition flex items-center gap-1.5 shadow-md">
                                                <span>✨</span> Сгенерировать отклик (ИИ)
                                            </button>
                                        </div>
                                    {% endif %}
                                </div>
                            </div>
                        {% endif %}
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
        <!-- Analytics & Platform Breakdown View -->
        <div class="space-y-6">
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <span>📊</span> Сводная статистика по биржам и конверсии
                </h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm text-slate-300">
                        <thead class="bg-slate-950 text-slate-400 text-xs uppercase border-b border-slate-800">
                            <tr>
                                <th class="p-3">Биржа</th>
                                <th class="p-3">Всего заказов</th>
                                <th class="p-3">🔥 Hot (Tier 1)</th>
                                <th class="p-3">⚡ Normal (Tier 2)</th>
                                <th class="p-3">🗑 Trash (Tier 3)</th>
                                <th class="p-3">Конверсия в Hot</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800">
                            {% for item in extended_stats.by_source %}
                                <tr class="hover:bg-slate-800/40 transition">
                                    <td class="p-3 font-semibold uppercase text-slate-200">{{ item.source }}</td>
                                    <td class="p-3 font-mono font-bold">{{ item.total }}</td>
                                    <td class="p-3 font-mono text-amber-400 font-bold">{{ item.hot }}</td>
                                    <td class="p-3 font-mono text-blue-400">{{ item.normal }}</td>
                                    <td class="p-3 font-mono text-slate-500">{{ item.trash }}</td>
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
        <!-- Rules, Stop-Words & Config View -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Whitelist -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                <div class="flex items-center justify-between">
                    <h3 class="text-sm font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                        <span>🎯</span> Белый список ключевых слов ({{ keywords|length }})
                    </h3>
                    <span class="text-xs text-slate-400 font-mono">Мин. 1 совпадение</span>
                </div>
                <div class="flex flex-wrap gap-1.5">
                    {% for kw in keywords %}
                        <span class="text-xs font-mono bg-emerald-950/60 text-emerald-300 border border-emerald-800/50 px-2.5 py-1 rounded-md">
                            {{ kw }}
                        </span>
                    {% endfor %}
                </div>
            </div>

            <!-- Blacklist -->
            <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-4">
                <div class="flex items-center justify-between">
                    <h3 class="text-sm font-bold text-red-400 uppercase tracking-wider flex items-center gap-1.5">
                        <span>🚫</span> Черный список стоп-слов ({{ stop_words|length }})
                    </h3>
                    <span class="text-xs text-slate-400 font-mono">Мгновенный отсев</span>
                </div>
                <div class="flex flex-wrap gap-1.5 max-h-96 overflow-y-auto custom-scroll pr-1">
                    {% for sw in stop_words %}
                        <span class="text-xs font-mono bg-red-950/40 text-red-300 border border-red-900/40 px-2.5 py-1 rounded-md">
                            {{ sw }}
                        </span>
                    {% endfor %}
                </div>
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
                            <span class="text-xs px-2 py-0.5 rounded-md bg-blue-950 text-blue-300 border border-blue-800 font-mono">@horizontal42</span>
                        </h3>
                        <p class="text-xs text-slate-400 mt-1">Разработчик решений на базе AI / Специалист по автоматизации (AI), Python-разработчик</p>
                    </div>
                    <div class="text-xs font-mono text-slate-400">
                        Контакты: frolka84@gmail.com | Telegram: @horizontal42
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
                    <div class="bg-slate-950/80 border border-slate-800 p-4 rounded-xl space-y-2">
                        <div class="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                            <span>🎙</span> Речевая аналитика звонков
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">
                            Cortex IT (6 мес). WhisperX, pyannote, Qwen 32B, FastAPI, Celery, Redis, PostgreSQL, Bitrix24 REST API, Weasyprint. Батчинг на GPU, сброс памяти malloc_trim, flip-rate 0%.
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
                            <p class="text-[11px] text-slate-400">Заказы с указанным бюджетом ниже этой суммы отсеиваются в Tier 3.</p>
                            <select id="setting_min_budget" onchange="autoSaveSetting('min_budget', parseInt(this.value, 10))" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 focus:border-indigo-500 outline-none">
                                <option value="5000" {% if settings_map.min_budget == 5000 %}selected{% endif %}>5 000 ₽</option>
                                <option value="10000" {% if settings_map.min_budget == 10000 %}selected{% endif %}>10 000 ₽ (по умолчанию)</option>
                                <option value="15000" {% if settings_map.min_budget == 15000 %}selected{% endif %}>15 000 ₽</option>
                                <option value="20000" {% if settings_map.min_budget == 20000 %}selected{% endif %}>20 000 ₽</option>
                                <option value="30000" {% if settings_map.min_budget == 30000 %}selected{% endif %}>30 000 ₽</option>
                                <option value="50000" {% if settings_map.min_budget == 50000 %}selected{% endif %}>50 000 ₽</option>
                            </select>
                        </div>

                        <!-- Hot score threshold -->
                        <div class="space-y-1.5 pt-2">
                            <label for="setting_hot_score_threshold" class="text-xs font-semibold text-slate-300 block">
                                🔥 Порог Hot (Tier 1 совпадения):
                            </label>
                            <p class="text-[11px] text-slate-400">Минимальный балл Mistral/Agy (1-10) для присвоения категории Hot и мгновенной отправки в Telegram.</p>
                            <select id="setting_hot_score_threshold" onchange="autoSaveSetting('hot_score_threshold', parseInt(this.value, 10))" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 focus:border-indigo-500 outline-none">
                                <option value="6" {% if settings_map.hot_score_threshold == 6 %}selected{% endif %}>6 / 10 (мягкий отбор)</option>
                                <option value="7" {% if settings_map.hot_score_threshold == 7 %}selected{% endif %}>7 / 10 (рекомендуемый)</option>
                                <option value="8" {% if settings_map.hot_score_threshold == 8 %}selected{% endif %}>8 / 10 (строгий отбор)</option>
                                <option value="9" {% if settings_map.hot_score_threshold == 9 %}selected{% endif %}>9 / 10 (только топовые)</option>
                            </select>
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
                            <p class="text-[11px] text-slate-400">Вакансии с указанной зарплатой ниже этой суммы отсеиваются в Tier 3.</p>
                            <select id="setting_vacancy_min_salary" onchange="autoSaveSetting('vacancy_min_salary', parseInt(this.value, 10))" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2.5 focus:border-indigo-500 outline-none">
                                <option value="0" {% if not settings_map.vacancy_min_salary %}selected{% endif %}>Любая (включая по договоренности)</option>
                                <option value="80000" {% if settings_map.vacancy_min_salary == 80000 %}selected{% endif %}>от 80 000 ₽</option>
                                <option value="100000" {% if settings_map.vacancy_min_salary == 100000 %}selected{% endif %}>от 100 000 ₽</option>
                                <option value="120000" {% if settings_map.vacancy_min_salary == 120000 %}selected{% endif %}>от 120 000 ₽</option>
                                <option value="150000" {% if settings_map.vacancy_min_salary == 150000 %}selected{% endif %}>от 150 000 ₽</option>
                                <option value="200000" {% if settings_map.vacancy_min_salary == 200000 %}selected{% endif %}>от 200 000 ₽</option>
                            </select>
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
    <div id="copyToast" class="fixed bottom-6 right-6 z-50 bg-emerald-600 text-white px-4 py-2.5 rounded-lg shadow-xl text-xs font-semibold flex items-center gap-2 transform translate-y-20 opacity-0 transition-all duration-200">
        <span>✅</span> Текст успешно скопирован в буфер обмена!
    </div>

    <script>
        function copyProposal(elementId, btn) {
            const el = document.getElementById(elementId);
            if (!el) return;
            const text = el.innerText;
            navigator.clipboard.writeText(text).then(() => {
                const toast = document.getElementById('copyToast');
                toast.classList.remove('translate-y-20', 'opacity-0');
                const origText = btn.innerHTML;
                btn.innerHTML = '<span>✅</span> Скопировано!';
                btn.classList.replace('bg-emerald-600', 'bg-emerald-700');
                btn.classList.replace('bg-rose-600', 'bg-rose-700');
                setTimeout(() => {
                    toast.classList.add('translate-y-20', 'opacity-0');
                    btn.innerHTML = origText;
                    btn.classList.replace('bg-emerald-700', 'bg-emerald-600');
                    btn.classList.replace('bg-rose-700', 'bg-rose-600');
                }, 2000);
            });
        }

        async function generateProposal(orderId, btn) {
            const origHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span>⏳</span> Генерация (agy)...';
            try {
                const res = await fetch(`/api/orders/${orderId}/generate-proposal`, { method: 'POST' });
                const data = await res.json();
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

                    const box = document.getElementById(`proposal-box-${orderId}`);
                    const isHh = data.is_hh;
                    const titleText = isHh ? 'Сгенерированное Cover Letter (agy):' : 'Сгенерированный отклик:';
                    const icon = isHh ? '✉️' : '✍️';
                    const btnClass = isHh ? 'bg-rose-600 hover:bg-rose-500' : 'bg-emerald-600 hover:bg-emerald-500';
                    const btnCopyText = isHh ? 'Скопировать Cover Letter' : 'Скопировать отклик';

                    box.className = "mt-3 pt-3 border-t border-slate-800 space-y-2";
                    box.innerHTML = `
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-semibold ${isHh ? 'text-rose-400' : 'text-emerald-400'} uppercase tracking-wider flex items-center gap-1">
                                <span>${icon}</span> ${titleText}
                            </span>
                            <div class="flex items-center space-x-2">
                                <button onclick="generateProposal('${orderId}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition">
                                    🔄 Перегенерировать
                                </button>
                                <button onclick="copyProposal('proposal-text-${orderId}', this)" class="text-xs ${btnClass} text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm">
                                    <span>📋</span> ${btnCopyText}
                                </button>
                            </div>
                        </div>
                        ${finBlock}
                        <div id="proposal-text-${orderId}" class="text-xs font-mono bg-slate-900/90 text-slate-200 p-3.5 rounded-lg border border-slate-800 whitespace-pre-wrap leading-relaxed select-all">${data.proposal_text}</div>
                    `;
                } else {
                    alert('Ошибка генерации: ' + (data.error || 'не удалось составить отклик'));
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            } catch (e) {
                alert('Сетевая ошибка: ' + e);
                btn.disabled = false;
                btn.innerHTML = origHtml;
            }
        }

        async function autoSaveSetting(key, value) {
            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
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

        async function saveAllSettingsForm() {
            const payload = {
                platform_kwork: document.getElementById('setting_platform_kwork')?.checked ?? true,
                platform_fl_ru: document.getElementById('setting_platform_fl_ru')?.checked ?? true,
                platform_freelance_ru: document.getElementById('setting_platform_freelance_ru')?.checked ?? true,
                platform_pchel_net: document.getElementById('setting_platform_pchel_net')?.checked ?? true,
                platform_hh_ru: document.getElementById('setting_platform_hh_ru')?.checked ?? true,
                platform_habr_career: document.getElementById('setting_platform_habr_career')?.checked ?? true,
                filter_pro_only: document.getElementById('setting_filter_pro_only')?.checked ?? false,
                min_budget: parseInt(document.getElementById('setting_min_budget')?.value || '10000', 10),
                hot_score_threshold: parseInt(document.getElementById('setting_hot_score_threshold')?.value || '7', 10)
            };
            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.ok) {
                    showToast('Все настройки успешно сохранены!');
                } else {
                    alert('Ошибка сохранения настроек');
                }
            } catch (e) {
                alert('Ошибка сети: ' + e);
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

        function setTopicFilter(topic, btn) {
            activeTopic = topic;
            document.querySelectorAll('.topic-chip').forEach(el => {
                el.classList.remove('bg-blue-600', 'bg-rose-600', 'text-white', 'font-bold');
                el.classList.add('bg-slate-800', 'text-slate-300');
            });
            const isHh = window.location.href.includes('section=hh_ru');
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
            const isHh = window.location.href.includes('section=hh_ru');
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

        function applyClientFilters() {
            const queryEl = document.getElementById('orderSearch');
            const query = queryEl ? queryEl.value.toLowerCase().trim() : '';
            const minEl = document.getElementById('filterPriceMin');
            const minPrice = minEl && minEl.value ? parseFloat(minEl.value) : null;
            const maxEl = document.getElementById('filterPriceMax');
            const maxPrice = maxEl && maxEl.value ? parseFloat(maxEl.value) : null;
            const sortEl = document.getElementById('orderSortSelect');
            const sortMode = sortEl ? sortEl.value : 'default';

            const container = document.getElementById('ordersContainer');
            if (!container) return;
            const cards = Array.from(container.querySelectorAll('.order-card'));

            let visibleCount = 0;
            cards.forEach(card => {
                const title = card.getAttribute('data-title') || '';
                const desc = card.getAttribute('data-desc') || '';
                const price = parseFloat(card.getAttribute('data-price') || '0');

                // Поиск по тексту
                const matchesText = !query || title.includes(query) || desc.includes(query);

                // Фильтр по тематике/тегу
                let matchesTopic = true;
                if (activeTopic !== 'all') {
                    matchesTopic = title.includes(activeTopic) || desc.includes(activeTopic);
                }

                // Фильтр по диапазону цен
                let matchesPrice = true;
                if (minPrice !== null && price > 0 && price < minPrice) matchesPrice = false;
                if (maxPrice !== null && price > 0 && price > maxPrice) matchesPrice = false;

                if (matchesText && matchesTopic && matchesPrice) {
                    card.style.display = 'block';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            // Сортировка
            if (sortMode !== 'default') {
                cards.sort((a, b) => {
                    const priceA = parseFloat(a.getAttribute('data-price') || '0');
                    const priceB = parseFloat(b.getAttribute('data-price') || '0');
                    const scoreA = parseFloat(a.getAttribute('data-score') || '0');
                    const scoreB = parseFloat(b.getAttribute('data-score') || '0');

                    if (sortMode === 'score_desc') return scoreB - scoreA;
                    if (sortMode === 'price_desc') return priceB - priceA;
                    if (sortMode === 'price_asc') return priceA - priceB;
                    return 0;
                });
                cards.forEach(card => container.appendChild(card));
            }

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
            if (!input || !btn) return;

            const text = input.value.trim();
            if (!text) return;

            const modelVal = modelSelect ? modelSelect.value : 'auto';
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            const origBtnHtml = btn.innerHTML;
            btn.innerHTML = '<span>⏳ Думает...</span>';

            const box = document.getElementById(`chat-messages-${orderId}`);
            const tempUserBubble = `
                <div class="flex justify-end">
                    <div class="max-w-[85%] bg-indigo-950/80 border border-indigo-800/60 rounded-xl rounded-tr-sm p-2.5 text-slate-100 space-y-1">
                        <div class="flex items-center justify-between gap-3 text-[10px] text-indigo-300 font-semibold">
                            <span>👤 Андрей</span>
                            <span class="font-mono text-slate-400">сейчас</span>
                        </div>
                        <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(text)}</div>
                    </div>
                </div>
            `;
            if (box && box.innerText.includes('Нет сообщений')) {
                box.innerHTML = tempUserBubble;
            } else if (box) {
                box.insertAdjacentHTML('beforeend', tempUserBubble);
                box.scrollTop = box.scrollHeight;
            }

            try {
                const res = await fetch(`/api/orders/${orderId}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, model: modelVal })
                });
                const data = await res.json();
                if (data.ok && data.reply) {
                    await loadOrderChatMessages(orderId);
                    const badge = document.getElementById(`chat-badge-${orderId}`);
                    if (badge) {
                        const cur = parseInt(badge.innerText || '0', 10);
                        badge.innerText = cur + 2;
                        badge.classList.remove('hidden');
                    }
                } else {
                    alert('Ошибка ответа модели: ' + (data.error || 'не удалось получить ответ'));
                }
            } catch (e) {
                alert('Сетевая ошибка при отправке вопроса: ' + e);
            } finally {
                input.disabled = false;
                btn.disabled = false;
                btn.innerHTML = origBtnHtml;
                input.focus();
            }
        }

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
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ yaml: yamlText })
                });
                const data = await res.json();
                if (data.ok) {
                    alert('✅ Конфигурация успешно сохранена и применена!');
                    window.location.reload();
                } else {
                    alert('❌ Ошибка валидации конфигурации:\n' + (data.error || 'Неверный формат YAML'));
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
                    return val.split('\n').map(s => s.trim()).filter(Boolean);
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
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: payload })
                });
                const data = await res.json();
                if (data.ok) {
                    alert('✅ Настройки успешно сохранены в config.yml и применены!');
                    window.location.reload();
                } else {
                    alert('❌ Ошибка валидации настроек:\n' + (data.error || 'Ошибка сохранения'));
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
    </script>
</body>
</html>
"""


def create_web_app(repo: Optional[OrderRepository] = None) -> FastAPI:
    """Создать и настроить экземпляр FastAPI приложения."""
    app = FastAPI(
        title="Freelance Leads Monitor",
        description="Web dashboard for monitoring freelance leads on jobs.3dvex.ru",
        version="0.3.0",
    )

    repository = repo or OrderRepository()

    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard(
        request: Request,
        section: str = Query("freelance", description="Раздел сайта: freelance (биржи фриланса) или hh_ru (вакансии HeadHunter)"),
        tab: str = Query("hot", description="Активная вкладка (hot, all, normal, trash, analytics, rules, profile)"),
        source: Optional[str] = Query(None, description="Фильтр по источнику (kwork, fl_ru, freelance_ru, pchel_net, remote_job, hh_ru)"),
        free_only: int = Query(0, description="Фильтр только бесплатных откликов (1 - без PRO, 0 - все)"),
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
        if active_tab in ["hot", "all", "normal", "trash"]:
            raw_orders = await repository.get_recent_orders(
                limit=limit,
                priority=p_filter,
                source=s_filter,
                only_free=only_free_flag,
                section=active_section,
            )

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

        template = Template(DASHBOARD_HTML, autoescape=True)
        html_content = template.render(
            orders=formatted_orders,
            active_section=active_section,
            stats=current_stats,
            current_stats=current_stats,
            extended_stats=extended_stats,
            active_tab=active_tab,
            selected_source=s_filter or "",
            free_only=1 if only_free_flag else 0,
            keywords=settings.KEYWORDS,
            stop_words=settings.STOP_WORDS,
            llm_provider=settings.LLM_PROVIDER,
            hh_config=settings.COLLECTORS_HH_RU,
            dossier_items=settings.PROMPTS_CONFIG.projects_dossier,
            settings_map=effective_settings,
            health_data=health_data,
            uptime_info=uptime_info,
            raw_config_yaml=raw_config_yaml,
            yaml_app_config=settings.app_config,
        )
        return HTMLResponse(content=html_content)

    @app.post("/api/orders/{order_id}/generate-proposal")
    async def api_generate_proposal(order_id: int):
        """Сгенерировать отклик или Cover Letter для заказа/вакансии по требованию."""
        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Заказ или вакансия не найдена"})

        from src.analyzer.factory import get_llm_client
        llm_client = get_llm_client()

        raw_order = RawOrder(
            source=SourcePlatform(order_data["source"]),
            external_id=order_data["external_id"],
            title=order_data["title"],
            description=order_data["description"] or "",
            url=order_data["url"],
            price=order_data["price"],
            is_negotiable=bool(order_data.get("is_negotiable", 0)),
            is_pro_only=bool(order_data.get("is_pro_only", 0)),
            attachments_text=order_data.get("attachments_text"),
        )

        analysis_data = (
            json.loads(order_data["analysis_json"])
            if order_data.get("analysis_json")
            else None
        )

        try:
            proposal_res = await llm_client.generate_proposal(raw_order, analysis_data)
            proposal_text = str(proposal_res)
            rec_price = getattr(proposal_res, "recommended_price", None)
            mkt_price = getattr(proposal_res, "market_price", None)
            price_just = getattr(proposal_res, "price_justification", None)

            await repository.update_proposal(
                order_id,
                proposal_text=proposal_text,
                recommended_price=rec_price,
                market_price=mkt_price,
                price_justification=price_just,
            )
            is_hh = raw_order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)
            return {
                "ok": True,
                "is_hh": is_hh,
                "proposal_text": proposal_text,
                "recommended_price": rec_price,
                "market_price": mkt_price,
                "price_justification": price_just,
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

        raw_order = RawOrder(
            source=SourcePlatform(order_data["source"]),
            external_id=order_data["external_id"],
            title=order_data["title"],
            description=order_data["description"] or "",
            url=order_data["url"],
            price=order_data["price"],
            is_negotiable=bool(order_data.get("is_negotiable", 0)),
            is_pro_only=bool(order_data.get("is_pro_only", 0)),
            attachments_text=order_data.get("attachments_text"),
        )
        analysis_data = (
            json.loads(order_data["analysis_json"])
            if order_data.get("analysis_json")
            else None
        )
        proposal_text = order_data.get("proposal_text")

        history = await repository.get_chat_messages(order_id)

        try:
            # 1. Сохраняем вопрос пользователя
            await repository.add_chat_message(
                order_id=order_id,
                role="user",
                model="user",
                message=user_message,
            )

            # 2. Вызываем модель
            reply_text, model_used = await llm_client.chat_order(
                order=raw_order,
                analysis_data=analysis_data,
                proposal_text=proposal_text,
                history=history,
                user_message=user_message,
                model_preference=model_choice,
            )

            # 3. Сохраняем ответ модели
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
        stats = await repository.get_extended_stats()
        return stats

    @app.get("/api/health-check", response_class=JSONResponse)
    async def api_health_check_full():
        """Запустить полную проверку доступности бирж, LLM и базы данных."""
        from src.services.health_check import HealthCheckService
        from src.services.uptime import get_system_status_info
        service = HealthCheckService()
        result = await service.run_full_check()
        result["uptime"] = get_system_status_info()
        return result

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
            "hot_score_threshold",
            "vacancy_city",
            "vacancy_work_format",
            "vacancy_min_salary",
            "vacancy_allow_negotiable",
        }

        for key, val in body.items():
            if key in allowed_keys:
                await repository.set_setting(key, val)

        all_settings = await repository.get_all_settings()
        return {"ok": True, "settings": all_settings}

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

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app

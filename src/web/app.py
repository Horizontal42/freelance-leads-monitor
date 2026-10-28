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

        <!-- Top Section Switcher (Freelance Orders vs HeadHunter Vacancies) -->
        <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-1.5 bg-slate-900/90 border border-slate-800 rounded-2xl shadow-inner">
            <div class="flex items-center space-x-2">
                <a href="/?section=freelance&tab=hot" class="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition {% if active_section == 'freelance' %}bg-blue-600 text-white shadow-lg shadow-blue-500/25 font-bold{% else %}text-slate-400 hover:text-slate-200 hover:bg-slate-800/60{% endif %}">
                    <span class="text-base">💼</span>
                    <span>Фриланс-биржи</span>
                    <span class="text-xs px-2 py-0.5 rounded-full {% if active_section == 'freelance' %}bg-blue-700/80 text-blue-100{% else %}bg-slate-800 text-slate-400{% endif %} font-mono">{{ extended_stats.freelance.total if extended_stats.freelance else extended_stats.total }}</span>
                </a>
                <a href="/?section=hh_ru&tab=hot" class="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition {% if active_section == 'hh_ru' %}bg-gradient-to-r from-red-600 to-rose-600 text-white shadow-lg shadow-rose-500/25 font-bold{% else %}text-slate-400 hover:text-slate-200 hover:bg-slate-800/60{% endif %}">
                    <span class="text-base">🏢</span>
                    <span>Вакансии HH.ru</span>
                    <span class="text-xs px-2 py-0.5 rounded-full {% if active_section == 'hh_ru' %}bg-rose-700/80 text-rose-100{% else %}bg-slate-800 text-slate-400{% endif %} font-mono">{{ extended_stats.hh_ru.total if extended_stats.hh_ru else 0 }}</span>
                </a>
            </div>

            <div class="text-xs text-slate-400 hidden lg:flex items-center gap-2 pr-3">
                {% if active_section == 'freelance' %}
                    <span>📊 Источники: Kwork, FL.ru, Freelance.ru, Pchel.net, Remote-job</span>
                {% else %}
                    <span>🎯 Стек Андрея: AI-агенты, RAG Qdrant, WhisperX, CV YOLOv8, FastAPI, Celery</span>
                {% endif %}
            </div>
        </div>

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
                        <span>⚙️</span> Правила и фильтры
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
                {% endif %}
            </nav>
        </div>

        {% if active_tab in ['hot', 'all', 'normal', 'trash'] %}
        <!-- Search & Filter Bar -->
        <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3">
            <div class="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
                <!-- Live Search Box -->
                <div class="relative flex-1">
                    <span class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 text-sm">🔍</span>
                    <input type="text" id="orderSearch" onkeyup="filterOrdersClient()" placeholder="{% if active_section == 'hh_ru' %}Живой поиск по компании, названию вакансии, стеку, городу...{% else %}Живой поиск по заголовку, технологиям, стеку, сути...{% endif %}" class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-sm rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-blue-500 placeholder-slate-500 transition">
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

            {% if active_section == 'freelance' %}
            <!-- Source Badges Filter Row -->
            <div class="flex items-center space-x-1.5 overflow-x-auto custom-scroll pt-1 border-t border-slate-800/80">
                <span class="text-xs text-slate-400 font-semibold uppercase mr-1">Биржа:</span>
                <a href="/?section=freelance&tab={{ active_tab }}&source=&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if not selected_source %}bg-blue-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Все
                </a>
                <a href="/?section=freelance&tab={{ active_tab }}&source=kwork&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'kwork' %}bg-emerald-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Kwork
                </a>
                <a href="/?section=freelance&tab={{ active_tab }}&source=fl_ru&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'fl_ru' %}bg-blue-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    FL.ru
                </a>
                <a href="/?section=freelance&tab={{ active_tab }}&source=freelance_ru&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'freelance_ru' %}bg-purple-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Freelance.ru
                </a>
                <a href="/?section=freelance&tab={{ active_tab }}&source=pchel_net&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'pchel_net' %}bg-amber-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Pchel.net
                </a>
                <a href="/?section=freelance&tab={{ active_tab }}&source=remote_job&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'remote_job' %}bg-cyan-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Remote-job
                </a>
            </div>
            {% endif %}
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
                <div class="order-card bg-slate-900 border {% if order.priority == 'hot' %}border-amber-500/50 shadow-lg shadow-amber-950/20{% elif order.priority == 'trash' %}border-slate-800 opacity-60{% else %}border-slate-800{% endif %} p-5 rounded-xl transition hover:border-slate-700 space-y-3.5" data-title="{{ order.title|lower }}" data-desc="{{ order.description|lower }} {{ order.attachments_text|lower if order.attachments_text else '' }}">

                    <!-- Card Header Row -->
                    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div class="flex items-center space-x-2 flex-wrap gap-y-1">
                            <!-- Platform Badge -->
                            <span class="text-xs font-bold uppercase px-2.5 py-1 rounded-md {% if order.source == 'hh_ru' %}bg-rose-950 text-rose-300 border border-rose-800/60{% elif order.source == 'kwork' %}bg-emerald-950 text-emerald-300 border border-emerald-800/60{% elif order.source == 'fl_ru' %}bg-blue-950 text-blue-300 border border-blue-800/60{% elif order.source == 'freelance_ru' %}bg-purple-950 text-purple-300 border border-purple-800/60{% elif order.source == 'pchel_net' %}bg-amber-950 text-amber-300 border border-amber-800/60{% else %}bg-cyan-950 text-cyan-300 border border-cyan-800/60{% endif %}">
                                {{ order.source }}
                            </span>

                            {% if order.source != 'hh_ru' %}
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
                            {% if order.source == 'hh_ru' %}
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

                                <!-- Market / AI Recommended Price -->
                                {% set rec_price = order.recommended_price or (order.analysis.recommended_price if order.analysis else None) %}
                                {% set has_prop = (order.proposal_text or (order.analysis and order.analysis.proposal_text)) %}
                                <div id="market-price-pill-{{ order.id }}" class="flex items-center gap-1.5 {% if rec_price and rec_price > 0 %}bg-amber-950/40 border border-amber-800/60{% else %}bg-slate-950/60 border border-slate-800{% endif %} px-3 py-1 rounded-lg" title="{% if has_prop %}Рыночная ставка на основе веб-поиска (agy){% else %}Предварительная расчетная оценка Mistral по часам и сложности{% endif %}">
                                    <span class="text-xs text-amber-400 font-medium">🎯 Рыночная:</span>
                                    <span class="text-sm font-bold text-amber-300 font-mono">
                                        {% if rec_price and rec_price > 0 %}
                                            {{ "{:,.0f}".format(rec_price).replace(",", " ") }} ₽{% if not has_prop %}<span class="text-[10px] text-amber-400/80 font-normal ml-0.5">(предв.)</span>{% endif %}
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

                    {% if order.source == 'hh_ru' and order.attachments_text %}
                        <!-- Vacancy Meta Highlights -->
                        <div class="text-xs bg-slate-950/80 border border-slate-800 p-2.5 rounded-lg text-slate-300 font-mono space-y-0.5">
                            {{ order.attachments_text.replace('\\n', '<br>')|safe }}
                        </div>
                    {% endif %}

                    <!-- Mistral AI Structured Breakdown for Vacancy or Project -->
                    {% if order.analysis %}
                        {% if order.source == 'hh_ru' %}
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
                                {% if order.analysis.recommended_price or order.analysis.price_justification %}
                                    {% set has_agy_prop = (order.proposal_text or (order.analysis and order.analysis.proposal_text)) %}
                                    <div class="text-xs bg-slate-900/80 border border-amber-900/40 p-2.5 rounded-lg text-slate-300 space-y-1">
                                        <div class="flex flex-wrap items-center justify-between gap-2">
                                            <span class="text-amber-400 font-semibold uppercase text-[10px] tracking-wider flex items-center gap-1">
                                                <span>🎯</span> Финансовая оценка и стратегия торга {% if has_agy_prop %}(agy с веб-поиском):{% else %}(предварительно Mistral):{% endif %}
                                            </span>
                                            {% if order.analysis.recommended_price %}
                                                <span class="font-mono font-bold text-amber-300">
                                                    {% if has_agy_prop %}Рыночная ставка: {% else %}Предварительная ставка: {% endif %}{{ "{:,.0f}".format(order.analysis.recommended_price).replace(",", " ") }} ₽
                                                </span>
                                            {% endif %}
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
                        const pill = document.getElementById(`market-price-pill-${orderId}`);
                        if (pill) {
                            pill.className = "flex items-center gap-1.5 bg-amber-950/40 border border-amber-800/60 px-3 py-1 rounded-lg";
                            const formatted = new Intl.NumberFormat('ru-RU').format(data.recommended_price) + ' ₽';
                            pill.innerHTML = `<span class="text-xs text-amber-400 font-medium">🎯 Рыночная:</span> <span class="text-sm font-bold text-amber-300 font-mono">${formatted}</span>`;
                        }
                    }

                    let finBlock = '';
                    if (data.recommended_price || data.price_justification) {
                        const recFormatted = data.recommended_price ? new Intl.NumberFormat('ru-RU').format(data.recommended_price) + ' ₽' : '';
                        finBlock = `
                            <div class="text-xs bg-slate-900/90 border border-amber-900/50 p-2.5 rounded-lg text-slate-300 space-y-1 mb-2">
                                <div class="flex flex-wrap items-center justify-between gap-1">
                                    <span class="text-amber-400 font-semibold uppercase text-[10px] tracking-wider flex items-center gap-1">
                                        <span>🎯</span> Рыночная оценка и стратегия торга (agy с веб-поиском):
                                    </span>
                                    ${recFormatted ? `<span class="font-mono font-bold text-amber-300">Рыночная ставка: ${recFormatted}</span>` : ''}
                                </div>
                                ${data.price_justification ? `<p class="text-slate-300 text-[11px] leading-relaxed">${data.price_justification}</p>` : ''}
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

        function filterOrdersClient() {
            const query = document.getElementById('orderSearch').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.order-card');
            cards.forEach(card => {
                const title = card.getAttribute('data-title') || '';
                const desc = card.getAttribute('data-desc') || '';
                if (!query || title.includes(query) || desc.includes(query)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
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
            price_just = getattr(proposal_res, "price_justification", None)

            await repository.update_proposal(
                order_id,
                proposal_text=proposal_text,
                recommended_price=rec_price,
                price_justification=price_just,
            )
            is_hh = raw_order.source == SourcePlatform.HH_RU
            return {
                "ok": True,
                "is_hh": is_hh,
                "proposal_text": proposal_text,
                "recommended_price": rec_price,
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

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app

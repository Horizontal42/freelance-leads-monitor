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
    <title>Freelance Leads Monitor | jobs.3dvex.ru</title>
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
                    <p class="text-xs text-slate-400">Мониторинг Kwork, FL.ru, Freelance.ru, Pchel.net, Remote-job с ИИ-откликами</p>
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

        <!-- Top Overview Stats Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Всего в базе</div>
                <div class="text-2xl font-black text-white mt-0.5">{{ stats.total }}</div>
            </div>
            <div class="bg-gradient-to-br from-amber-950/30 to-slate-900/80 border border-amber-900/50 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1">
                    <span>🔥</span> Горячие (Tier 1)
                </div>
                <div class="text-2xl font-black text-amber-300 mt-0.5">{{ stats.hot }}</div>
            </div>
            <div class="bg-slate-900/80 border border-slate-800 p-3.5 rounded-xl">
                <div class="text-[11px] font-semibold text-blue-400 uppercase tracking-wider flex items-center gap-1">
                    <span>⚡</span> Обычные (Tier 2)
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
                    <span>💰</span> Средний чек Hot
                </div>
                <div class="text-xl font-black text-purple-300 mt-1">
                    {% if stats.avg_hot_price %}{{ "{:,.0f}".format(stats.avg_hot_price).replace(",", " ") }} ₽{% else %}-{% endif %}
                </div>
            </div>
        </div>

        <!-- Main Tab Navigation -->
        <div class="border-b border-slate-800 flex items-center justify-between overflow-x-auto custom-scroll">
            <nav class="flex space-x-1 sm:space-x-4 min-w-max">
                <a href="/?tab=hot&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'hot' %}active border-b-2 border-amber-500 text-amber-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                    <span>🔥</span> Горячие лиды
                    <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono">{{ stats.hot }}</span>
                </a>
                <a href="/?tab=all&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'all' %}active border-b-2 border-blue-500 text-blue-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                    <span>⚡</span> Все прошедшие
                    <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-mono">{{ stats.hot + stats.normal }}</span>
                </a>
                <a href="/?tab=normal&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'normal' %}active border-b-2 border-blue-500 text-blue-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                    <span>🎯</span> Потенциальные (Tier 2)
                    <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">{{ stats.normal }}</span>
                </a>
                <a href="/?tab=trash&source={{ selected_source }}&free_only={{ free_only }}" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'trash' %}active border-b-2 border-slate-500 text-slate-300 font-bold{% else %}text-slate-500 hover:text-slate-300{% endif %}">
                    <span>🗑</span> Отсеянные (Tier 3)
                    <span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">{{ stats.trash }}</span>
                </a>
                <a href="/?tab=analytics" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'analytics' %}active border-b-2 border-purple-500 text-purple-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                    <span>📊</span> Аналитика бирж
                </a>
                <a href="/?tab=rules" class="tab-btn px-4 py-3 text-sm font-medium transition flex items-center gap-1.5 {% if active_tab == 'rules' %}active border-b-2 border-emerald-500 text-emerald-400 font-bold{% else %}text-slate-400 hover:text-slate-200{% endif %}">
                    <span>⚙️</span> Правила и фильтры
                </a>
            </nav>
        </div>

        {% if active_tab in ['hot', 'all', 'normal', 'trash'] %}
        <!-- Search & Platform Filter Bar -->
        <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-3">
            <div class="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
                <!-- Live Search Box -->
                <div class="relative flex-1">
                    <span class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 text-sm">🔍</span>
                    <input type="text" id="orderSearch" onkeyup="filterOrdersClient()" placeholder="Живой поиск по заголовку, технологиям, стеку, сути..." class="w-full bg-slate-950 border border-slate-800 text-slate-200 text-sm rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-blue-500 placeholder-slate-500 transition">
                </div>

                <!-- Free / PRO Filter Toggle -->
                <div>
                    <a href="/?tab={{ active_tab }}&source={{ selected_source }}&free_only={% if free_only %}0{% else %}1{% endif %}" class="px-3.5 py-2 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 {% if free_only %}bg-emerald-600 text-white shadow-md{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700{% endif %}">
                        {% if free_only %}
                            <span>✅</span> Только бесплатные отклики
                        {% else %}
                            <span>🔓</span> Все отклики (включая PRO)
                        {% endif %}
                    </a>
                </div>
            </div>

            <!-- Source Badges Filter Row -->
            <div class="flex items-center space-x-1.5 overflow-x-auto custom-scroll pt-1 border-t border-slate-800/80">
                <span class="text-xs text-slate-400 font-semibold uppercase mr-1">Биржа:</span>
                <a href="/?tab={{ active_tab }}&source=&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if not selected_source %}bg-blue-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Все
                </a>
                <a href="/?tab={{ active_tab }}&source=kwork&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'kwork' %}bg-emerald-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Kwork
                </a>
                <a href="/?tab={{ active_tab }}&source=fl_ru&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'fl_ru' %}bg-blue-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    FL.ru
                </a>
                <a href="/?tab={{ active_tab }}&source=freelance_ru&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'freelance_ru' %}bg-purple-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Freelance.ru
                </a>
                <a href="/?tab={{ active_tab }}&source=pchel_net&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'pchel_net' %}bg-amber-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Pchel.net
                </a>
                <a href="/?tab={{ active_tab }}&source=remote_job&free_only={{ free_only }}" class="px-3 py-1.5 rounded-lg text-xs font-medium transition {% if selected_source == 'remote_job' %}bg-cyan-600 text-white font-bold{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    Remote-job
                </a>
            </div>
        </div>

        <!-- Orders Feed List -->
        <div id="ordersContainer" class="space-y-4">
            {% if not orders %}
                <div class="bg-slate-900 border border-slate-800 p-12 text-center rounded-xl text-slate-400">
                    <p class="text-lg font-medium text-slate-300">В этой категории заказы пока не найдены</p>
                    <p class="text-xs mt-1">Они появятся в реальном времени при следующем цикле опроса бирж.</p>
                </div>
            {% endif %}

            {% for order in orders %}
                <div class="order-card bg-slate-900 border {% if order.priority == 'hot' %}border-amber-500/50 shadow-lg shadow-amber-950/20{% elif order.priority == 'trash' %}border-slate-800 opacity-60{% else %}border-slate-800{% endif %} p-5 rounded-xl transition hover:border-slate-700 space-y-3.5" data-title="{{ order.title|lower }}" data-desc="{{ order.description|lower }}">

                    <!-- Card Header Row -->
                    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div class="flex items-center space-x-2 flex-wrap gap-y-1">
                            <!-- Platform Badge -->
                            <span class="text-xs font-bold uppercase px-2.5 py-1 rounded-md {% if order.source == 'kwork' %}bg-emerald-950 text-emerald-300 border border-emerald-800/60{% elif order.source == 'fl_ru' %}bg-blue-950 text-blue-300 border border-blue-800/60{% elif order.source == 'freelance_ru' %}bg-purple-950 text-purple-300 border border-purple-800/60{% elif order.source == 'pchel_net' %}bg-amber-950 text-amber-300 border border-amber-800/60{% else %}bg-cyan-950 text-cyan-300 border border-cyan-800/60{% endif %}">
                                {{ order.source }}
                            </span>

                            <!-- Paid vs Free Response Badge -->
                            {% if order.is_pro_only %}
                                <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-purple-950/80 text-purple-300 border border-purple-800/60 flex items-center gap-1" title="Требуется аккаунт PRO / платный отклик">
                                    ⭐ Только PRO
                                </span>
                            {% else %}
                                <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 flex items-center gap-1" title="Бесплатный отклик для всех">
                                    🔓 Для всех
                                </span>
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

                            <span class="text-xs text-slate-400 font-mono bg-slate-950/80 border border-slate-800 px-2 py-0.5 rounded-md flex items-center gap-1" title="Дата и время публикации заказа">
                                🕒 {{ order.created_at[:16].replace('T', ' ') if order.created_at else 'Только что' }}
                            </span>
                        </div>

                        <!-- Price Pill -->
                        <div>
                            {% if order.price %}
                                <span class="text-sm font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-3 py-1 rounded-lg font-mono">
                                    {{ "{:,.0f}".format(order.price).replace(",", " ") }} ₽
                                </span>
                            {% elif order.is_negotiable %}
                                <span class="text-xs font-medium text-blue-400 bg-blue-950/60 border border-blue-800/60 px-2.5 py-1 rounded-lg">
                                    Договорная
                                </span>
                            {% else %}
                                <span class="text-xs font-medium text-slate-500 bg-slate-800 px-2 py-1 rounded-lg">
                                    Бюджет не указан
                                </span>
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

                    <!-- Executive Summary Box (Brief info from AI) -->
                    {% if order.analysis and order.analysis.executive_summary %}
                        <div class="text-xs bg-slate-950/80 border border-blue-900/40 p-2.5 rounded-lg text-blue-200 flex items-start gap-2">
                            <span class="text-blue-400 mt-0.5">📝</span>
                            <div>
                                <strong class="text-blue-300 font-semibold uppercase text-[10px] tracking-wider block mb-0.5">Краткая суть задачи (ИИ):</strong>
                                <span>{{ order.analysis.executive_summary }}</span>
                            </div>
                        </div>
                    {% endif %}

                    <!-- Description -->
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

                    <!-- LLM Analysis Section (if present) -->
                    {% if order.analysis %}
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

                                <!-- PERT Formula metrics -->
                                {% if order.analysis.pert %}
                                    <div class="text-xs font-mono bg-slate-900 px-2.5 py-1 rounded border border-slate-800 text-amber-300" title="PERT: E = (O + 4M + P)/6">
                                        PERT E = {{ order.analysis.pert.expected_days }} дн (±{{ order.analysis.pert.sigma }}σ)
                                    </div>
                                {% endif %}
                            </div>

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

    </main>

    <!-- Toast Notification for Copy -->
    <div id="copyToast" class="fixed bottom-6 right-6 z-50 bg-emerald-600 text-white px-4 py-2.5 rounded-lg shadow-xl text-xs font-semibold flex items-center gap-2 transform translate-y-20 opacity-0 transition-all duration-200">
        <span>✅</span> Отклик скопирован в буфер обмена!
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
                setTimeout(() => {
                    toast.classList.add('translate-y-20', 'opacity-0');
                    btn.innerHTML = origText;
                    btn.classList.replace('bg-emerald-700', 'bg-emerald-600');
                }, 2000);
            });
        }

        async function generateProposal(orderId, btn) {
            const origHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span>⏳</span> Генерация отклика...';
            try {
                const res = await fetch(`/api/orders/${orderId}/generate-proposal`, { method: 'POST' });
                const data = await res.json();
                if (data.ok && data.proposal_text) {
                    const box = document.getElementById(`proposal-box-${orderId}`);
                    box.className = "mt-3 pt-3 border-t border-slate-800 space-y-2";
                    box.innerHTML = `
                        <div class="flex items-center justify-between">
                            <span class="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                                <span>✍️</span> Сгенерированный отклик:
                            </span>
                            <div class="flex items-center space-x-2">
                                <button onclick="generateProposal('${orderId}', this)" class="text-xs text-slate-400 hover:text-slate-200 transition">
                                    🔄 Перегенерировать
                                </button>
                                <button onclick="copyProposal('proposal-text-${orderId}', this)" class="text-xs bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-3 py-1 rounded-md transition flex items-center gap-1 shadow-sm">
                                    <span>📋</span> Скопировать отклик
                                </button>
                            </div>
                        </div>
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
        tab: str = Query("hot", description="Активная вкладка (hot, all, normal, trash, analytics, rules)"),
        source: Optional[str] = Query(None, description="Фильтр по источнику (kwork, fl_ru, freelance_ru, pchel_net, remote_job)"),
        free_only: int = Query(0, description="Фильтр только бесплатных откликов (1 - без PRO, 0 - все)"),
        limit: int = Query(80, ge=1, le=300),
    ):
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

        template = Template(DASHBOARD_HTML, autoescape=True)
        html_content = template.render(
            orders=formatted_orders,
            stats=extended_stats,
            extended_stats=extended_stats,
            active_tab=active_tab,
            selected_source=s_filter or "",
            free_only=1 if only_free_flag else 0,
            keywords=settings.KEYWORDS,
            stop_words=settings.STOP_WORDS,
            llm_provider=settings.LLM_PROVIDER,
        )
        return HTMLResponse(content=html_content)

    @app.post("/api/orders/{order_id}/generate-proposal")
    async def api_generate_proposal(order_id: int):
        """Сгенерировать отклик для заказа по требованию."""
        order_data = await repository.get_by_id(order_id)
        if not order_data:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Заказ не найден"})

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
            proposal_text = await llm_client.generate_proposal(raw_order, analysis_data)
            await repository.update_proposal(order_id, proposal_text)
            return {"ok": True, "proposal_text": proposal_text}
        except Exception as e:
            logger.error("Ошибка при генерации отклика для заказа #%d: %s", order_id, e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

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
        stats = await repository.get_extended_stats()
        return stats

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app

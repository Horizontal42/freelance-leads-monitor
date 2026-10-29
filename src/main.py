"""Main entry point for Freelance Leads Monitor."""

import argparse
import asyncio
import logging
import signal
import sys
from typing import List, Optional
import uvicorn
from src.analyzer.factory import get_llm_client
from src.bot.bot import create_bot_and_dispatcher
from src.collectors.base import BaseCollector
from src.collectors.fl_ru import FlRuCollector
from src.collectors.freelance_ru import FreelanceRuCollector
from src.collectors.habr_career import HabrCareerCollector
from src.collectors.hh_ru import HhRuCollector
from src.collectors.kwork import KworkCollector
from src.collectors.pchel_net import PchelNetCollector
from src.config import settings
from src.filters.pre_filter import HardFilter
from src.notifiers.pipeline import LeadsPipeline
from src.notifiers.telegram_notifier import TelegramNotifier
from src.storage.db import init_db
from src.storage.repository import OrderRepository
from src.web.app import create_web_app

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


async def run_single_scan(
    collectors: List[BaseCollector],
    pipeline: LeadsPipeline,
    is_cold_start: Optional[bool] = None,
) -> dict:
    """Выполнить один проход сбора со всех площадок."""
    logger.info(
        "Запуск %s сканирования бирж...",
        "глубокого (бэкфилл)" if is_cold_start else "сканирования",
    )
    all_raw_orders = []

    for col in collectors:
        try:
            orders = await col.fetch_new_orders(is_cold_start=is_cold_start)
            all_raw_orders.extend(orders)
        except Exception as e:
            logger.error("Ошибка при сборе из источника %s: %s", col.name, e)

    stats = await pipeline.process_orders(all_raw_orders)
    logger.info(
        "Итоги сканирования: получено=%d, дубликаты=%d, трэш=%d, обычные=%d, горячие_в_тг=%d, ошибки=%d",
        stats["received"],
        stats["duplicates"],
        stats["filtered_trash"],
        stats["analyzed_normal"],
        stats["hot_leads_sent"],
        stats["errors"],
    )
    return stats


async def polling_worker(
    collectors: List[BaseCollector],
    pipeline: LeadsPipeline,
    interval_seconds: Optional[int] = None,
    name: str = "Сборщик",
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Фоновый воркер периодического сбора заказов с поддержкой холодного старта."""
    interval = (
        interval_seconds
        if interval_seconds is not None
        else getattr(settings, "POLLING_INTERVAL_SECONDS", 180)
    )
    logger.info("Фоновый воркер [%s] запущен (интервал: %d сек)", name, interval)
    is_first = getattr(settings, "INITIAL_BACKFILL", True)
    while stop_event is None or not stop_event.is_set():
        try:
            await run_single_scan(collectors, pipeline, is_cold_start=is_first)
            is_first = False
        except asyncio.CancelledError:
            logger.info("Фоновый воркер [%s] остановлен.", name)
            break
        except Exception as e:
            logger.error("Непредвиденная ошибка в фоновом воркере [%s]: %s", name, e)

        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(interval)
    logger.info("Фоновый воркер [%s] завершил работу.", name)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Freelance Leads Monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Запустить один цикл сбора и анализа, после чего завершить работу",
    )
    args = parser.parse_args()

    # 1. Инициализация базы данных
    await init_db()
    repo = OrderRepository()
    hard_filter = HardFilter()
    llm_client = get_llm_client()

    # 2. Инициализация сборщиков: разделение на фриланс и вакансии
    freelance_collectors: List[BaseCollector] = [
        KworkCollector(),
        FlRuCollector(),
        FreelanceRuCollector(),
        PchelNetCollector(),
    ]
    vacancy_collectors: List[BaseCollector] = [
        HhRuCollector(repo=repo),
        HabrCareerCollector(repo=repo),
    ]
    all_collectors = freelance_collectors + vacancy_collectors

    # 3. Режим разового сканирования (--once)
    if args.once:
        tg_notifier = TelegramNotifier() if settings.BOT_TOKEN else None
        pipeline = LeadsPipeline(
            repo=repo,
            hard_filter=hard_filter,
            llm_client=llm_client,
            tg_notifier=tg_notifier,
        )
        try:
            await run_single_scan(
                all_collectors, pipeline, is_cold_start=getattr(settings, "INITIAL_BACKFILL", True)
            )
        finally:
            if tg_notifier:
                await tg_notifier.close()
        return

    # 4. Режим непрерывной работы: Веб-дашборд + Фоновый воркер + Telegram-бот
    logger.info(
        "Инициализация веб-дашборда (http://%s:%d) для jobs.3dvex.ru...",
        settings.WEB_HOST,
        settings.WEB_PORT,
    )
    web_app = create_web_app(repo)
    uvicorn_config = uvicorn.Config(
        app=web_app,
        host=settings.WEB_HOST,
        port=settings.WEB_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(uvicorn_config)

    # Настройка бота и нотификатора
    bot = None
    dp = None
    tg_notifier = None
    vacancies_notifier = None

    if settings.BOT_TOKEN and settings.ADMIN_CHAT_ID:
        bot, dp = create_bot_and_dispatcher(repo)
        tg_notifier = TelegramNotifier(bot=bot, chat_id=settings.ADMIN_CHAT_ID)

        if settings.VACANCIES_BOT_TOKEN and settings.VACANCIES_ADMIN_CHAT_ID:
            if settings.VACANCIES_BOT_TOKEN != settings.BOT_TOKEN:
                vacancies_notifier = TelegramNotifier(
                    chat_id=settings.VACANCIES_ADMIN_CHAT_ID,
                    bot_token=settings.VACANCIES_BOT_TOKEN,
                )
            else:
                vacancies_notifier = tg_notifier
        else:
            vacancies_notifier = tg_notifier

        # Регистрация команд бота в меню Telegram
        from aiogram.types import BotCommand
        from src.bot.keyboards import get_main_reply_keyboard
        try:
            await bot.set_my_commands([
                BotCommand(command="settings", description="⚙️ Настройки фильтров и бирж"),
                BotCommand(command="health", description="🩺 Проверка здоровья сервисов"),
                BotCommand(command="uptime", description="⏱️ Аптайм и статус системы"),
                BotCommand(command="stats", description="📊 Статистика базы заказов"),
                BotCommand(command="scan", description="🔍 Сканирование площадок"),
                BotCommand(command="recent", description="📋 Последние горячие лиды"),
                BotCommand(command="start", description="🤖 Главное меню и клавиатура"),
            ])
        except Exception as cmd_err:
            logger.debug("Не удалось зарегистрировать команды меню бота: %s", cmd_err)

        # Привязываем команду /scan и кнопку '🔍 Сканировать' к нашему пайплайну
        from aiogram import F
        from aiogram.filters import Command, or_f
        from aiogram.types import Message
        from src.bot.handlers import router

        pipeline_for_scan = LeadsPipeline(
            repo=repo,
            hard_filter=hard_filter,
            llm_client=llm_client,
            tg_notifier=tg_notifier,
            vacancies_notifier=vacancies_notifier,
        )

        @router.message(or_f(Command("scan"), F.text.in_({"🔍 Сканировать", "Сканировать", "/scan"})))
        async def dynamic_scan_handler(message: Message) -> None:
            await message.answer(
                "🔍 Запускаю внеочередное сканирование бирж...",
                reply_markup=get_main_reply_keyboard(),
            )
            stats = await run_single_scan(all_collectors, pipeline_for_scan)
            summary = (
                "✅ <b>Сканирование завершено:</b>\n\n"
                f"• Найдено новых заказов: <b>{stats['received']}</b>\n"
                f"• Уже были в базе (дубли): <b>{stats['duplicates']}</b>\n"
                f"• Отсеяно фильтром (трэш): <b>{stats['filtered_trash']}</b>\n"
                f"• Обычных сохранено (Tier 2): <b>{stats['analyzed_normal']}</b>\n"
                f"• 🔥 Горячих лидов отправлено (Tier 1): <b>{stats['hot_leads_sent']}</b>"
            )
            await message.answer(summary, reply_markup=get_main_reply_keyboard())
    else:
        logger.warning(
            "⚠️ BOT_TOKEN или ADMIN_CHAT_ID не настроены. "
            "Telegram-бот отключен, работает веб-дашборд и сбор в базу данных."
        )

    pipeline = LeadsPipeline(
        repo=repo,
        hard_filter=hard_filter,
        llm_client=llm_client,
        tg_notifier=tg_notifier,
        vacancies_notifier=vacancies_notifier,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    # Формируем параллельные задачи для asyncio.gather
    worker_tasks = [
        asyncio.create_task(
            polling_worker(
                collectors=freelance_collectors,
                pipeline=pipeline,
                interval_seconds=min(settings.KWORK_POLL_INTERVAL, settings.FL_POLL_INTERVAL),
                name="Фриланс",
                stop_event=stop_event,
            )
        ),
        asyncio.create_task(
            polling_worker(
                collectors=vacancy_collectors,
                pipeline=pipeline,
                interval_seconds=getattr(settings, "VACANCIES_POLL_INTERVAL", 1800),
                name="Вакансии",
                stop_event=stop_event,
            )
        ),
    ]

    tasks = [server.serve(), *worker_tasks]

    if bot and dp:
        tasks.append(dp.start_polling(bot, allowed_updates=["message", "callback_query"]))

    def _on_signal():
        logger.info("Получен сигнал завершения (SIGTERM/SIGINT), останавливаем воркеры...")
        stop_event.set()
        server.should_exit = True
        for wt in worker_tasks:
            if not wt.done():
                wt.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except (NotImplementedError, RuntimeError):
            pass

    logger.info("Запуск системы через asyncio.gather: веб-сервер, фоновый опрос и бот...")
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Получен сигнал на остановку...")
    finally:
        server.should_exit = True
        if bot:
            await bot.session.close()
        logger.info("Система корректно остановлена.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

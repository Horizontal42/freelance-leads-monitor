"""Main entry point for Freelance Leads Monitor."""

import argparse
import asyncio
import logging
import signal
import sys
from typing import List
from src.analyzer.factory import get_llm_client
from src.bot.bot import create_bot_and_dispatcher
from src.collectors.base import BaseCollector
from src.collectors.fl_ru import FlRuCollector
from src.collectors.kwork import KworkCollector
from src.config import settings
from src.filters.pre_filter import HardFilter
from src.notifiers.pipeline import LeadsPipeline
from src.notifiers.telegram_notifier import TelegramNotifier
from src.storage.db import init_db
from src.storage.repository import OrderRepository

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
) -> dict:
    """Выполнить один проход сбора со всех площадок."""
    logger.info("Запуск единовременного сканирования бирж...")
    all_raw_orders = []

    for col in collectors:
        try:
            orders = await col.fetch_new_orders()
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
    interval_seconds: int = 180,
) -> None:
    """Фоновый воркер периодического сбора заказов."""
    logger.info("Фоновый воркер запущен (интервал опроса: %d сек)", interval_seconds)
    while True:
        try:
            await run_single_scan(collectors, pipeline)
        except asyncio.CancelledError:
            logger.info("Фоновый воркер остановлен.")
            break
        except Exception as e:
            logger.error("Непредвиденная ошибка в фоновом воркере: %s", e)

        await asyncio.sleep(interval_seconds)


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

    # 2. Инициализация сборщиков
    collectors: List[BaseCollector] = [
        KworkCollector(),
        FlRuCollector(),
    ]

    # 3. Режим разового сканирования (--once)
    if args.once:
        tg_notifier = TelegramNotifier()
        pipeline = LeadsPipeline(
            repo=repo,
            hard_filter=hard_filter,
            llm_client=llm_client,
            tg_notifier=tg_notifier,
        )
        try:
            await run_single_scan(collectors, pipeline)
        finally:
            await tg_notifier.close()
        return

    # 4. Режим непрерывной работы (Telegram-бот + фоновый воркер)
    if not settings.BOT_TOKEN or not settings.ADMIN_CHAT_ID:
        logger.warning(
            "⚠️ ВНИМАНИЕ: BOT_TOKEN или ADMIN_CHAT_ID не настроены в .env! "
            "Бот не сможет отправлять уведомления в Telegram. "
            "Запустите с ключом --once для локального тестирования или укажите токены в .env."
        )

    bot, dp = create_bot_and_dispatcher(repo)
    tg_notifier = TelegramNotifier(bot=bot, chat_id=settings.ADMIN_CHAT_ID)
    pipeline = LeadsPipeline(
        repo=repo,
        hard_filter=hard_filter,
        llm_client=llm_client,
        tg_notifier=tg_notifier,
    )

    # Привязываем команду /scan к нашему пайплайну
    from aiogram.types import Message
    from aiogram.filters import Command
    from src.bot.handlers import router

    @router.message(Command("scan"))
    async def dynamic_scan_handler(message: Message) -> None:
        await message.answer("🔍 Запускаю внеочередное сканирование бирж...")
        stats = await run_single_scan(collectors, pipeline)
        summary = (
            "✅ <b>Сканирование завершено:</b>\n\n"
            f"• Найдено новых заказов: <b>{stats['received']}</b>\n"
            f"• Уже были в базе (дубли): <b>{stats['duplicates']}</b>\n"
            f"• Отсеяно фильтром (трэш): <b>{stats['filtered_trash']}</b>\n"
            f"• Обычных сохранено (Tier 2): <b>{stats['analyzed_normal']}</b>\n"
            f"• 🔥 Горячих лидов отправлено (Tier 1): <b>{stats['hot_leads_sent']}</b>"
        )
        await message.answer(summary)

    # Запуск фонового воркера опроса
    worker_task = asyncio.create_task(
        polling_worker(
            collectors=collectors,
            pipeline=pipeline,
            interval_seconds=min(settings.KWORK_POLL_INTERVAL, settings.FL_POLL_INTERVAL),
        )
    )

    logger.info("Запуск Telegram-бота и фонового мониторинга...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        worker_task.cancel()
        await bot.session.close()
        logger.info("Система корректно остановлена.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

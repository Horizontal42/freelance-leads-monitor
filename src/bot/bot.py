"""Bot initialization and dispatcher setup."""

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from src.bot.handlers import router
from src.config import settings
from src.storage.repository import OrderRepository


def create_bot_and_dispatcher(
    repo: OrderRepository,
) -> tuple[Bot, Dispatcher]:
    """Создать и настроить экземпляры Bot и Dispatcher."""
    bot = Bot(
        token=settings.BOT_TOKEN or "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
        parse_mode=ParseMode.HTML,
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Внедрение зависимостей в контекст обработчиков
    dp["repo"] = repo

    return bot, dp

"""Bot package exports."""

from src.bot.bot import create_bot_and_dispatcher
from src.bot.handlers import router
from src.bot.keyboards import get_order_inline_keyboard

__all__ = ["create_bot_and_dispatcher", "router", "get_order_inline_keyboard"]

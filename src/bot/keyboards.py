"""Inline keyboards for Telegram bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_order_inline_keyboard(order_id: int, order_url: str) -> InlineKeyboardMarkup:
    """Создать клавиатуру карточки заказа.

    3 кнопки:
    1. Скопировать отклик (присылает отклик отдельным сообщением для удобного клика)
    2. Открыть заказ (прямая ссылка на биржу)
    3. В архив (скрывает заказ)
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="📋 Скопировать отклик",
                callback_data=f"copy:{order_id}",
            ),
            InlineKeyboardButton(
                text="🔗 Открыть заказ",
                url=order_url,
            ),
        ],
        [
            InlineKeyboardButton(
                text="📦 В архив",
                callback_data=f"archive:{order_id}",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

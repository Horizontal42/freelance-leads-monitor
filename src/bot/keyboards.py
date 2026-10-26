"""Inline keyboards for Telegram bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_order_inline_keyboard(
    order_id: int, order_url: str, has_proposal: bool = False
) -> InlineKeyboardMarkup:
    """Создать клавиатуру карточки заказа.

    Кнопки:
    1. Если отклик уже есть: '📋 Скопировать отклик'
       Если отклика еще нет: '✨ Сгенерировать отклик'
    2. '🔗 Открыть заказ' (ссылка)
    3. '📦 В архив'
    """
    action_btn = (
        InlineKeyboardButton(
            text="📋 Скопировать отклик",
            callback_data=f"copy:{order_id}",
        )
        if has_proposal
        else InlineKeyboardButton(
            text="✨ Сгенерировать отклик",
            callback_data=f"gen_prop:{order_id}",
        )
    )

    buttons = [
        [
            action_btn,
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

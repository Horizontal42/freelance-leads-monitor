"""Inline keyboards for Telegram bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_order_inline_keyboard(
    order_id: int,
    order_url: str,
    has_proposal: bool = False,
    is_vacancy: bool = False,
) -> InlineKeyboardMarkup:
    """Создать клавиатуру карточки заказа или вакансии."""
    if is_vacancy:
        action_btn = (
            InlineKeyboardButton(
                text="📋 Скопировать Cover Letter",
                callback_data=f"copy:{order_id}",
            )
            if has_proposal
            else InlineKeyboardButton(
                text="✨ Составить Cover Letter",
                callback_data=f"gen_prop:{order_id}",
            )
        )
        url_btn_text = "🔗 Открыть вакансию"
    else:
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
        url_btn_text = "🔗 Открыть заказ"

    buttons = [
        [
            action_btn,
            InlineKeyboardButton(
                text=url_btn_text,
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

"""Inline and Reply keyboards for Telegram bot."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Главная постоянная клавиатура рядом с полем ввода сообщения."""
    buttons = [
        [
            KeyboardButton(text="⚙️ Настройки"),
            KeyboardButton(text="🩺 Проверка здоровья"),
        ],
        [
            KeyboardButton(text="⏱️ Аптайм и Статус"),
            KeyboardButton(text="🔍 Сканировать"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие или команду...",
    )


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


def get_settings_inline_keyboard(settings_map: dict) -> InlineKeyboardMarkup:
    """Сформировать интерактивную клавиатуру управления настройками."""
    # Статусы источников
    kwork_on = settings_map.get("platform_kwork", True)
    fl_on = settings_map.get("platform_fl_ru", True)
    freelance_on = settings_map.get("platform_freelance_ru", True)
    pchel_on = settings_map.get("platform_pchel_net", True)
    hh_on = settings_map.get("platform_hh_ru", True)
    habr_on = settings_map.get("platform_habr_career", True)

    pro_filtered = settings_map.get("filter_pro_only", False)
    min_budget = settings_map.get("min_budget", 10000)
    hot_score = settings_map.get("hot_score_threshold", 7)

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{'🟢' if kwork_on else '🔴'} Kwork",
                callback_data="set_toggle:platform_kwork",
            ),
            InlineKeyboardButton(
                text=f"{'🟢' if fl_on else '🔴'} FL.ru",
                callback_data="set_toggle:platform_fl_ru",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{'🟢' if freelance_on else '🔴'} Freelance.ru",
                callback_data="set_toggle:platform_freelance_ru",
            ),
            InlineKeyboardButton(
                text=f"{'🟢' if pchel_on else '🔴'} Pchel.net",
                callback_data="set_toggle:platform_pchel_net",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{'🟢' if hh_on else '🔴'} HeadHunter",
                callback_data="set_toggle:platform_hh_ru",
            ),
            InlineKeyboardButton(
                text=f"{'🟢' if habr_on else '🔴'} Хабр Карьера",
                callback_data="set_toggle:platform_habr_career",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{'⭐ Фильтровать PRO (только free)' if pro_filtered else '🔓 Принимать PRO заказы'}",
                callback_data="set_toggle:filter_pro_only",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"🔥 Порог Hot: {hot_score}/10 ▾",
                callback_data="set_cycle:hot_score_threshold",
            ),
            InlineKeyboardButton(
                text=f"💰 Мин. бюджет: {min_budget:,} ₽ ▾".replace(",", " "),
                callback_data="set_cycle:min_budget",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🩺 Проверить статус бирж (Health)",
                callback_data="action:health",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

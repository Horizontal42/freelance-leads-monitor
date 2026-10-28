"""Telegram bot message and callback handlers."""

import html
import logging
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, or_f
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from src.bot.keyboards import (
    get_main_reply_keyboard,
    get_order_inline_keyboard,
    get_settings_inline_keyboard,
)
from src.config import settings
from src.models.order import OrderStatus, RawOrder, SourcePlatform
from src.services.uptime import get_system_status_info
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)
router = Router(name="main_router")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Приветственное сообщение и статус системы."""
    user_id = message.from_user.id if message.from_user else 0
    is_admin = user_id == settings.ADMIN_CHAT_ID

    admin_note = (
        "✅ Вы авторизованы как администратор."
        if is_admin
        else f"⚠️ Ваш Chat ID: <code>{user_id}</code>. Укажите его в .env как ADMIN_CHAT_ID."
    )

    text = (
        "🤖 <b>Freelance Leads Monitor Bot</b>\n\n"
        "Система автоматического мониторинга бирж фриланса и вакансий, "
        "эвристической фильтрации и генерации откликов через нейросеть.\n\n"
        f"{admin_note}\n\n"
        "<b>Быстрый доступ закреплен внизу экрана рядом с полем ввода:</b>\n"
        "• ⚙️ <b>Настройки</b> - Управление источниками и фильтрами\n"
        "• 🩺 <b>Проверка здоровья</b> - Health Check доступности бирж и ИИ\n"
        "• ⏱️ <b>Аптайм и Статус</b> - Непрерывная работа и статистика базы\n"
        "• 🔍 <b>Сканировать</b> - Внеочередной сбор заказов"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_reply_keyboard())


def format_health_message(res: dict) -> str:
    """Сформировать аккуратный HTML-отчет о доступности сервисов."""
    status_icon = "🟢 Все системы в норме" if res.get("all_ok") else "⚠️ Обнаружены сбои или задержки"
    lines = [
        f"🩺 <b>Health Check: {status_icon}</b>\n",
        "<b>Биржи и площадки вакансий:</b>",
    ]
    for ex in res.get("exchanges", []):
        icon = "🟢" if ex.get("ok") else "🔴"
        st = f"{ex.get('status_code')}" if ex.get("status_code") else "ERR"
        lines.append(f"• {ex.get('name')}: {icon} {st} ({ex.get('latency_ms')} ms)")

    lines.append("\n<b>Нейросети и База данных:</b>")
    for s in res.get("services", []):
        icon = "🟢" if s.get("ok") else "🔴"
        det = f" [{s.get('details')}]" if s.get("details") else ""
        err = f" ({s.get('error')})" if s.get("error") else f" ({s.get('latency_ms')} ms)"
        lines.append(f"• {s.get('name')}: {icon}{det}{err}")

    lines.append(f"\n🕒 <i>Проверено: {res.get('checked_at')}</i>")
    return "\n".join(lines)


@router.message(
    or_f(
        Command("health"),
        F.text.in_({"🩺 Проверка здоровья", "Проверка здоровья", "/health", "🩺 Health Check", "Health Check"}),
    )
)
async def handle_health(message: Message) -> None:
    """Проверить доступность и время отклика бирж, ИИ и БД."""
    wait_msg = await message.answer(
        "⏳ Опрашиваю биржи и нейросети...",
        reply_markup=get_main_reply_keyboard(),
    )
    from src.services.health_check import HealthCheckService
    svc = HealthCheckService()
    res = await svc.run_full_check()
    text = format_health_message(res)
    await wait_msg.edit_text(text, parse_mode=ParseMode.HTML)


@router.message(or_f(Command("settings"), F.text.in_({"⚙️ Настройки", "Настройки", "/settings"})))
async def handle_settings(message: Message, repo: OrderRepository) -> None:
    """Показать интерактивную панель настроек."""
    settings_map = await repo.get_all_settings()
    keyboard = get_settings_inline_keyboard(settings_map)
    text = (
        "⚙️ <b>Панель управления настройками мониторинга:</b>\n\n"
        "Нажимайте на кнопки, чтобы включать/отключать источники и менять пороги.\n"
        "<i>Настройки сохраняются в базу данных и синхронизируются с сайтом.</i>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data.startswith("set_toggle:"))
async def handle_setting_toggle(callback: CallbackQuery, repo: OrderRepository) -> None:
    """Переключить булеву настройку."""
    key = callback.data.split(":")[1]
    cur_val = await repo.get_setting(key, False if key == "filter_pro_only" else True)
    new_val = not bool(cur_val)
    await repo.set_setting(key, new_val)
    all_settings = await repo.get_all_settings()
    keyboard = get_settings_inline_keyboard(all_settings)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer(f"Настройка сохранена: {'ВКЛ' if new_val else 'ВЫКЛ'}")


@router.callback_query(F.data.startswith("set_cycle:"))
async def handle_setting_cycle(callback: CallbackQuery, repo: OrderRepository) -> None:
    """Циклически переключить числовую настройку."""
    key = callback.data.split(":")[1]
    if key == "min_budget":
        cur_val = await repo.get_setting("min_budget", 10000)
        options = [5000, 10000, 15000, 20000, 30000, 50000]
        idx = options.index(cur_val) if cur_val in options else 1
        new_val = options[(idx + 1) % len(options)]
    elif key == "hot_score_threshold":
        cur_val = await repo.get_setting("hot_score_threshold", 7)
        options = [7, 8, 9]
        idx = options.index(cur_val) if cur_val in options else 0
        new_val = options[(idx + 1) % len(options)]
    else:
        await callback.answer()
        return

    await repo.set_setting(key, new_val)
    all_settings = await repo.get_all_settings()
    keyboard = get_settings_inline_keyboard(all_settings)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer(f"Новое значение: {new_val}")


@router.callback_query(F.data == "action:health")
async def handle_health_callback(callback: CallbackQuery) -> None:
    """Запустить проверку здоровья из клавиатуры настроек."""
    await callback.answer("Запускаю Health Check...")
    from src.services.health_check import HealthCheckService
    svc = HealthCheckService()
    res = await svc.run_full_check()
    text = format_health_message(res)
    if callback.message:
        await callback.message.reply(text, parse_mode=ParseMode.HTML)


def format_uptime_and_stats_message(status_info: dict, stats: dict) -> str:
    """Форматировать сводный отчет об аптайме и состоянии базы."""
    total = stats.get("total", 0)
    hot = stats.get("hot", 0)
    normal = stats.get("normal", 0)
    trash = stats.get("trash", 0)
    sent_to_tg = stats.get("sent_to_tg", 0)

    return (
        "⏱️ <b>Аптайм и статус системы:</b>\n\n"
        f"🟢 <b>Статус:</b> Работает стабильно\n"
        f"⏳ <b>Аптайм:</b> <code>{status_info.get('uptime', '0 мин.')}</code>\n"
        f"🚀 <b>Запущен:</b> {status_info.get('start_time')}\n"
        f"🆔 <b>PID процесса:</b> <code>{status_info.get('pid')}</code>\n\n"
        "📊 <b>Статистика базы заказов:</b>\n"
        f"• Всего заказов/вакансий: <b>{total}</b>\n"
        f"• 🔥 Горячих лидов (Tier 1): <b>{hot}</b>\n"
        f"• ⚡ Обычных заказов (Tier 2): <b>{normal}</b>\n"
        f"• 🗑 Отсеяно фильтром (Tier 3): <b>{trash}</b>\n"
        f"• 📤 Отправлено в Telegram: <b>{sent_to_tg}</b>\n\n"
        "<i>Используйте кнопки под полем ввода для быстрого перехода в Настройки или Health Check.</i>"
    )


@router.message(
    or_f(
        Command("uptime", "stats"),
        F.text.in_({"⏱️ Аптайм и Статус", "Аптайм и Статус", "⏱️ Аптайм", "Аптайм", "Статус", "/stats", "/uptime"}),
    )
)
async def handle_uptime_and_stats(message: Message, repo: OrderRepository) -> None:
    """Вывести отчет об аптайме и статистику базы."""
    stats = await repo.get_stats()
    status_info = get_system_status_info()
    text = format_uptime_and_stats_message(status_info, stats)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_reply_keyboard())


# Алиас для обратной совместимости в тестах
handle_stats = handle_uptime_and_stats


@router.message(Command("recent"))
async def handle_recent(message: Message, repo: OrderRepository) -> None:
    """Показать последние заказы."""
    orders = await repo.get_recent_orders(limit=5)
    if not orders:
        await message.answer("В базе пока нет заказов.")
        return

    lines = ["📋 <b>Последние заказы в базе:</b>\n"]
    for o in orders:
        price_str = (
            f"{int(o['price']):,} ₽".replace(",", " ")
            if o.get("price")
            else "По договоренности"
        )
        badge = "🔥" if o.get("priority") == "hot" else "⚡"
        lines.append(
            f"{badge} [{o['source'].upper()}] <a href=\"{o['url']}\">{html.escape(o['title'][:45])}</a>\n"
            f"   Бюджет: {price_str} | Статус: {o.get('status')}"
        )

    await message.answer(
        "\n\n".join(lines),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.callback_query(F.data.startswith("gen_prop:"))
async def handle_generate_proposal(callback: CallbackQuery, repo: OrderRepository) -> None:
    """Сгенерировать отклик по требованию по нажатию кнопки в боте."""
    order_id_str = callback.data.split(":")[1]
    order_id = int(order_id_str)

    order_data = await repo.get_by_id(order_id)
    if not order_data:
        await callback.answer("Заказ не найден в базе данных.", show_alert=True)
        return

    await callback.answer("⏳ Генерирую персонализированный отклик...")

    import json
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

        await repo.update_proposal(
            order_id,
            proposal_text=proposal_text,
            recommended_price=rec_price,
            price_justification=price_just,
        )

        # Обновляем кнопку в исходном сообщении на "Скопировать"
        if callback.message:
            try:
                new_kb = get_order_inline_keyboard(
                    order_id, raw_order.url, has_proposal=True
                )
                await callback.message.edit_reply_markup(reply_markup=new_kb)
            except Exception:
                pass

            price_block = ""
            if rec_price and rec_price > 0:
                price_block = f"🎯 <b>Рыночная ставка (agy):</b> <code>{int(rec_price):,} ₽</code>\n"
                if price_just:
                    price_block += f"💡 <b>Обоснование:</b> {html.escape(price_just)}\n\n"

            formatted_msg = (
                f"✍️ <b>Сгенерированный отклик на заказ #{order_id}:</b>\n\n"
                f"{price_block}"
                f"<blockquote>{html.escape(proposal_text)}</blockquote>\n\n"
                f"<i>(Нажмите и удерживайте цитату выше для быстрого копирования)</i>"
            )
            await callback.message.reply(
                text=formatted_msg,
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error("Ошибка при генерации отклика для заказа #%d: %s", order_id, e)
        if callback.message:
            await callback.message.reply(
                f"❌ Ошибка генерации отклика: {e}. Попробуйте позже."
            )


@router.callback_query(F.data.startswith("copy:"))
async def handle_copy_proposal(callback: CallbackQuery, repo: OrderRepository) -> None:
    """Прислать текст отклика отдельным сообщением для копирования в 1 клик на смартфоне."""
    order_id_str = callback.data.split(":")[1]
    order_id = int(order_id_str)

    order_data = await repo.get_by_id(order_id)
    if not order_data:
        await callback.answer("Заказ не найден в базе данных.", show_alert=True)
        return

    proposal_text = order_data.get("proposal_text")
    if not proposal_text:
        await callback.answer("Для этого заказа отклик еще не сгенерирован.", show_alert=True)
        return

    # Отправляем текст отдельным сообщением
    # Форматируем так, чтобы в Telegram можно было тапнуть и скопировать
    formatted_msg = (
        f"📋 <b>Готовый отклик на заказ #{order_id}:</b>\n\n"
        f"<blockquote>{html.escape(proposal_text)}</blockquote>\n\n"
        f"<i>(Нажмите и удерживайте цитату выше для быстрого копирования)</i>"
    )

    if callback.message:
        await callback.message.reply(
            text=formatted_msg,
            parse_mode=ParseMode.HTML,
        )

    await callback.answer("Отклик отправлен сообщением ниже!")


@router.callback_query(F.data.startswith("archive:"))
async def handle_archive_order(callback: CallbackQuery, repo: OrderRepository) -> None:
    """Переместить заказ в архив и обновить текст сообщения."""
    order_id_str = callback.data.split(":")[1]
    order_id = int(order_id_str)

    await repo.update_status(order_id, OrderStatus.ARCHIVED)

    if callback.message and callback.message.text:
        new_text = f"📦 <b>[В АРХИВЕ]</b>\n\n{callback.message.text}"
        try:
            await callback.message.edit_text(
                text=new_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None,  # Убираем кнопки
            )
        except Exception:
            pass

    await callback.answer("Заказ перемещен в архив.")

"""Telegram bot message and callback handlers."""

import html
import logging
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from src.bot.keyboards import get_order_inline_keyboard
from src.config import settings
from src.models.order import OrderStatus, RawOrder, SourcePlatform
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
        "Система автоматического мониторинга бирж фриланса (Kwork, FL.ru), "
        "эвристической фильтрации и генерации откликов через нейросеть.\n\n"
        f"{admin_note}\n\n"
        "<b>Доступные команды:</b>\n"
        "• /scan - Запустить внеочередной сбор и анализ заказов прямо сейчас\n"
        "• /stats - Показать общую статистику по базе заказов\n"
        "• /recent - Показать последние 5 найденных горячих лидов"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("stats"))
async def handle_stats(message: Message, repo: OrderRepository) -> None:
    """Вывести статистику базы данных."""
    stats = await repo.get_stats()
    text = (
        "📊 <b>Статистика мониторинга заказов:</b>\n\n"
        f"• Всего заказов в базе: <b>{stats.get('total', 0)}</b>\n"
        f"• 🔥 Горячих лидов (Tier 1): <b>{stats.get('hot', 0)}</b>\n"
        f"• ⚡ Обычных заказов (Tier 2): <b>{stats.get('normal', 0)}</b>\n"
        f"• 🗑 Отсеяно фильтром (Tier 3): <b>{stats.get('trash', 0)}</b>\n"
        f"• 📤 Отправлено в Telegram: <b>{stats.get('sent_to_tg', 0)}</b>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


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

    await message.answer("\n\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


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
        proposal_text = await llm_client.generate_proposal(raw_order, analysis_data)
        await repo.update_proposal(order_id, proposal_text)

        # Обновляем кнопку в исходном сообщении на "Скопировать"
        if callback.message:
            try:
                new_kb = get_order_inline_keyboard(
                    order_id, raw_order.url, has_proposal=True
                )
                await callback.message.edit_reply_markup(reply_markup=new_kb)
            except Exception:
                pass

            formatted_msg = (
                f"✍️ <b>Сгенерированный отклик на заказ #{order_id}:</b>\n\n"
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

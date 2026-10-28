"""Telegram bot message and callback handlers."""

import html
import logging
from typing import Optional
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
    """Циклически переключить числовую или строковую настройку."""
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
    elif key == "vacancy_city":
        cur_val = await repo.get_setting("vacancy_city", "all")
        options = ["all", "moscow", "spb", "russia"]
        idx = options.index(cur_val) if cur_val in options else 0
        new_val = options[(idx + 1) % len(options)]
    elif key == "vacancy_work_format":
        cur_val = await repo.get_setting("vacancy_work_format", "all")
        options = ["all", "remote", "hybrid", "office"]
        idx = options.index(cur_val) if cur_val in options else 0
        new_val = options[(idx + 1) % len(options)]
    elif key == "vacancy_min_salary":
        cur_val = await repo.get_setting("vacancy_min_salary", 0)
        options = [0, 80000, 120000, 150000, 200000]
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
    await callback.answer(f"Сохранено: {new_val}")


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


def split_plain_text(text: str, max_chars: int = 3400) -> list[str]:
    """Разбить текст на логические части по абзацам или строкам, не превышая max_chars."""
    if not text:
        return [""]
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    paragraphs = text.split("\n\n")
    for para in paragraphs:
        para_len = len(para) + (2 if current_chunk else 0)
        if current_len + para_len <= max_chars:
            current_chunk.append(para)
            current_len += para_len
        else:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            if len(para) > max_chars:
                lines = para.split("\n")
                sub_chunk: list[str] = []
                sub_len = 0
                for line in lines:
                    line_len = len(line) + (1 if sub_chunk else 0)
                    if sub_len + line_len <= max_chars:
                        sub_chunk.append(line)
                        sub_len += line_len
                    else:
                        if sub_chunk:
                            chunks.append("\n".join(sub_chunk))
                            sub_chunk = []
                            sub_len = 0
                        if len(line) > max_chars:
                            for i in range(0, len(line), max_chars):
                                chunks.append(line[i : i + max_chars])
                        else:
                            sub_chunk.append(line)
                            sub_len = len(line)
                if sub_chunk:
                    chunks.append("\n".join(sub_chunk))
            else:
                current_chunk.append(para)
                current_len = len(para)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c for c in chunks if c.strip()] or [text]


def split_proposal_chunks(text: str, max_chunk_escaped_len: int = 3200) -> list[str]:
    """Разбить текст отклика на части с гарантией соблюдения лимита Telegram (4096 символов)."""
    raw_chunks = split_plain_text(text, max_chars=max_chunk_escaped_len)
    final_chunks: list[str] = []
    for chunk in raw_chunks:
        escaped = html.escape(chunk)
        if len(escaped) <= max_chunk_escaped_len:
            final_chunks.append(chunk)
        else:
            step = max(500, max_chunk_escaped_len // 2)
            sub_chunks = split_plain_text(chunk, max_chars=step)
            final_chunks.extend(sub_chunks)
    return final_chunks or [text]


async def safe_reply(
    message: Message,
    html_text: str,
    plain_fallback: Optional[str] = None,
) -> None:
    """Безопасная отправка сообщения с фоллбеком на plain text и защитой от переполнения 4096 символов."""
    try:
        if len(html_text) <= 4000:
            await message.reply(text=html_text, parse_mode=ParseMode.HTML)
            return
    except Exception as e:
        logger.warning("Ошибка отправки HTML в Telegram (%s), пробуем фоллбек...", e)

    clean = plain_fallback or html_text
    if len(clean) > 4000:
        clean = clean[:3950] + "\n...[текст сокращен]"
    try:
        await message.reply(text=clean)
    except Exception as e:
        logger.error("Критическая ошибка отправки ответа в Telegram: %s", e)


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
        market_price = getattr(proposal_res, "market_price", None)

        await repo.update_proposal(
            order_id,
            proposal_text=proposal_text,
            recommended_price=rec_price,
            price_justification=price_just,
            market_price=market_price,
        )

        is_vacancy = raw_order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)

        # Обновляем кнопку в исходном сообщении на "Скопировать"
        if callback.message:
            try:
                new_kb = get_order_inline_keyboard(
                    order_id, raw_order.url, has_proposal=True, is_vacancy=is_vacancy
                )
                await callback.message.edit_reply_markup(reply_markup=new_kb)
            except Exception:
                pass

            price_block = ""
            if market_price and market_price > 0:
                price_block += f"🎯 <b>Рыночная ставка (agy):</b> <code>{int(market_price):,} ₽</code>\n".replace(",", " ")
            if rec_price and rec_price > 0:
                price_block += f"💡 <b>Рекомендуем предложить:</b> <code>{int(rec_price):,} ₽</code>\n".replace(",", " ")
            if price_just:
                price_block += f"📝 <b>Обоснование:</b> {html.escape(price_just)}\n\n"

            type_title = "сопроводительное письмо" if is_vacancy else "отклик"
            header = f"✍️ <b>Сгенерированный {type_title} на #{order_id}:</b>\n\n"
            single_msg = (
                f"{header}"
                f"{price_block}"
                f"<blockquote>{html.escape(proposal_text)}</blockquote>\n\n"
                f"<i>(Нажмите и удерживайте цитату выше для быстрого копирования)</i>"
            )

            # Если всё помещается в лимит (<= 3800 символов), отправляем одним сообщением
            if len(single_msg) <= 3800:
                await safe_reply(
                    callback.message,
                    html_text=single_msg,
                    plain_fallback=f"✍️ {type_title.capitalize()} на #{order_id}:\n\n{proposal_text}",
                )
            else:
                # Если сообщение длинное, разбиваем на логические части во избежание ошибки message is too long:
                # 1. Отправляем финансовое обоснование отдельным сообщением
                if price_block:
                    info_msg = (
                        f"📊 <b>Оценка стоимости и ставка к #{order_id}:</b>\n\n"
                        f"{price_block}"
                    )
                    await safe_reply(
                        callback.message,
                        html_text=info_msg,
                        plain_fallback=f"Оценка #{order_id}:\n{price_just or ''}",
                    )

                # 2. Отправляем текст отклика частями (каждая внутри blockquote)
                chunks = split_proposal_chunks(proposal_text, max_chunk_escaped_len=3200)
                for idx, chunk in enumerate(chunks, 1):
                    part_label = f" (часть {idx}/{len(chunks)})" if len(chunks) > 1 else ""
                    chunk_msg = (
                        f"✍️ <b>Сгенерированный {type_title} на #{order_id}{part_label}:</b>\n\n"
                        f"<blockquote>{html.escape(chunk)}</blockquote>\n\n"
                        f"<i>(Нажмите и удерживайте цитату выше для быстрого копирования)</i>"
                    )
                    await safe_reply(
                        callback.message,
                        html_text=chunk_msg,
                        plain_fallback=f"{type_title.capitalize()} #{order_id}{part_label}:\n\n{chunk}",
                    )

    except Exception as e:
        logger.error("Ошибка при генерации отклика для заказа #%d: %s", order_id, e)
        if callback.message:
            err_msg = f"❌ Ошибка генерации отклика: {e}. Попробуйте позже."
            if len(err_msg) > 3500:
                err_msg = err_msg[:3500] + "..."
            try:
                await callback.message.reply(err_msg)
            except Exception:
                pass


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

    # Разбиваем текст отклика на части, если он длинный (Telegram лимит 4096 символов)
    chunks = split_proposal_chunks(proposal_text, max_chunk_escaped_len=3200)
    if callback.message:
        for idx, chunk in enumerate(chunks, 1):
            part_label = f" (часть {idx}/{len(chunks)})" if len(chunks) > 1 else ""
            formatted_msg = (
                f"📋 <b>Готовый текст отклика на #{order_id}{part_label}:</b>\n\n"
                f"<blockquote>{html.escape(chunk)}</blockquote>\n\n"
                f"<i>(Нажмите и удерживайте цитату выше для быстрого копирования)</i>"
            )
            await safe_reply(
                callback.message,
                html_text=formatted_msg,
                plain_fallback=f"Отклик #{order_id}{part_label}:\n\n{chunk}",
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

"""Telegram notification sender via aiogram 3."""

import html
import logging
import os
from typing import Optional
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions
from src.bot.keyboards import get_order_inline_keyboard
from src.config import settings
from src.models.analysis import AnalysisResult
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Нотификатор доставки горячих лидов в Telegram."""

    def __init__(
        self,
        bot: Optional[Bot] = None,
        chat_id: Optional[int] = None,
        bot_token: Optional[str] = None,
    ) -> None:
        self.chat_id = chat_id or settings.ADMIN_CHAT_ID
        self.bot_token = bot_token or settings.BOT_TOKEN
        self._bot = bot
        self._owns_bot = bot is None

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            if not self.bot_token:
                raise ValueError("BOT_TOKEN не задан в конфигурации (.env)")
            proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            session = AiohttpSession(proxy=proxy) if proxy else None
            self._bot = Bot(
                token=self.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                session=session,
            )
        return self._bot

    def format_card(
        self,
        order: RawOrder,
        analysis: AnalysisResult,
    ) -> str:
        """Сформировать HTML-текст карточки заказа."""
        price_str = (
            f"{int(order.price):,} ₽".replace(",", " ")
            if order.price
            else ("По договоренности" if order.is_negotiable else "Не указан")
        )
        rec_price_str = (
            f"{int(analysis.recommended_price):,} ₽".replace(",", " ")
            if analysis.recommended_price and analysis.recommended_price > 0
            else "По кнопке (agy с веб-поиском)"
        )

        pub_time_str = (
            order.created_at.strftime("%d.%m.%Y %H:%M")
            if order.created_at
            else "Не указано"
        )

        is_vacancy = order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)
        if is_vacancy:
            badge = (
                f"🔥 <b>[ВАКАНСИЯ | СКОР {analysis.score}/10]</b>"
                if analysis.score >= settings.HOT_SCORE_THRESHOLD
                else f"⚡ <b>[ВАКАНСИЯ | СКОР {analysis.score}/10]</b>"
            )
            company_line = ""
            if order.attachments_text:
                for l in order.attachments_text.splitlines():
                    if "Компания:" in l:
                        comp_name = l.replace("Компания:", "").strip()
                        company_line = f"🏢 <b>Компания:</b> {html.escape(comp_name)}\n"
                        break

            match_focus = analysis.match_reason or analysis.matched_project or "Python / AI / Автоматизация"
            if len(match_focus) > 120:
                match_focus = match_focus[:117] + "..."

            card_html = (
                f"{badge}\n\n"
                f"💼 <b>Позиция:</b> <a href=\"{html.escape(order.url, quote=True)}\">{html.escape(order.title)}</a>\n"
                f"{company_line}"
                f"💰 <b>Зарплата:</b> {price_str}\n"
                f"📌 <b>Площадка:</b> {order.source.value.upper()} | 🕒 {pub_time_str}\n"
                f"🎯 <b>Фокус совпадения:</b> {html.escape(match_focus)}\n\n"
                f"🌐 <i>Полное описание, стек и Cover Letter доступны на сайте.</i>"
            )
            return card_html

        risks_list = (
            "\n".join([f"• {html.escape(r)}" for r in analysis.risks_and_pitfalls])
            if analysis.risks_and_pitfalls
            else "• Стандартные риски разработки"
        )

        badge = (
            f"🔥 <b>[ГОРЯЧИЙ ЛИД | СКОР {analysis.score}/10]</b>"
            if analysis.score >= settings.HOT_SCORE_THRESHOLD
            else f"⚡ <b>[ЗАКАЗ | СКОР {analysis.score}/10]</b>"
        )
        access_badge = "⭐ <b>Только PRO</b>" if order.is_pro_only else "🔓 <b>Для всех</b>"

        card_html = (
            f"{badge}\n\n"
            f"📌 <b>Биржа:</b> {order.source.value.upper()} | {access_badge}\n"
            f"🕒 <b>Опубликован:</b> {pub_time_str}\n"
            f"📝 <b>Заказ:</b> <a href=\"{html.escape(order.url, quote=True)}\">{html.escape(order.title)}</a>\n\n"
            f"💰 <b>Бюджет клиента:</b> {price_str}\n"
        )
        if analysis.market_price and analysis.market_price > 0:
            card_html += f"🎯 <b>Рыночная стоимость:</b> {int(analysis.market_price):,} ₽\n".replace(",", " ")
        if analysis.recommended_price and analysis.recommended_price > 0:
            card_html += f"💡 <b>Рекомендуем предложить:</b> {int(analysis.recommended_price):,} ₽\n".replace(",", " ")
        elif rec_price_str:
            card_html += f"🎯 <b>Рекомендуемая цена:</b> {rec_price_str}\n"

        card_html += (
            f"⏱ <b>Срок (PERT):</b> {analysis.realistic_days} дн. "
            f"(E={analysis.pert.expected_days:.1f} дн., σ={analysis.pert.sigma:.1f})\n"
            f"💼 <b>Кейс из досье:</b> <code>{html.escape(analysis.matched_project)}</code> "
            f"(Сложность: {analysis.complexity}/10, Время: {analysis.pure_dev_hours:.1f}ч)\n\n"
            f"⚠️ <b>Подводные камни:</b>\n{risks_list}\n\n"
            f"💡 <b>Резюме (Mistral):</b> {html.escape(analysis.executive_summary)}"
        )

        if len(card_html) > 3900:
            excess = len(card_html) - 3700
            safe_summary = (
                analysis.executive_summary[:-excess] + "..."
                if len(analysis.executive_summary) > excess
                else "См. подробнее на сайте"
            )
            card_html = (
                f"{badge}\n\n"
                f"📌 <b>Биржа:</b> {order.source.value.upper()} | {access_badge}\n"
                f"🕒 <b>Опубликован:</b> {pub_time_str}\n"
                f"📝 <b>Заказ:</b> <a href=\"{html.escape(order.url, quote=True)}\">{html.escape(order.title)}</a>\n\n"
                f"💰 <b>Бюджет клиента:</b> {price_str}\n"
            )
            if analysis.market_price and analysis.market_price > 0:
                card_html += f"🎯 <b>Рыночная стоимость:</b> {int(analysis.market_price):,} ₽\n".replace(",", " ")
            if analysis.recommended_price and analysis.recommended_price > 0:
                card_html += f"💡 <b>Рекомендуем предложить:</b> {int(analysis.recommended_price):,} ₽\n".replace(",", " ")
            elif rec_price_str:
                card_html += f"🎯 <b>Рекомендуемая цена:</b> {rec_price_str}\n"

            card_html += (
                f"⏱ <b>Срок (PERT):</b> {analysis.realistic_days} дн. "
                f"(E={analysis.pert.expected_days:.1f} дн., σ={analysis.pert.sigma:.1f})\n"
                f"💼 <b>Кейс из досье:</b> <code>{html.escape(analysis.matched_project)}</code> "
                f"(Сложность: {analysis.complexity}/10, Время: {analysis.pure_dev_hours:.1f}ч)\n\n"
                f"⚠️ <b>Подводные камни:</b>\n{risks_list}\n\n"
                f"💡 <b>Резюме (Mistral):</b> {html.escape(safe_summary)}"
            )

        return card_html

    async def send_lead(
        self,
        order: RawOrder,
        analysis: AnalysisResult,
        order_db_id: int,
    ) -> bool:
        """Отправить карточку заказа в Telegram."""
        if not self.chat_id or not self.bot_token:
            logger.warning(
                "BOT_TOKEN или ADMIN_CHAT_ID не заданы. Пропуск отправки в Telegram."
            )
            return False

        card_text = self.format_card(order, analysis)
        has_proposal = bool(analysis.proposal_text and analysis.proposal_text.strip())
        is_vacancy = order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)
        is_hh = order.source == SourcePlatform.HH_RU
        keyboard = get_order_inline_keyboard(
            order_db_id,
            order.url,
            has_proposal=has_proposal,
            is_vacancy=is_vacancy,
            is_hh=is_hh,
        )

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=card_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            logger.info(
                "Карточка заказа #%d успешно отправлена в Telegram (chat_id: %d)",
                order_db_id,
                self.chat_id,
            )
            return True
        except Exception as e:
            logger.error(
                "Ошибка отправки карточки заказа #%d в Telegram: %s",
                order_db_id,
                e,
            )
            # Если отправка полной карточки не удалась, пробуем отправить компактную версию
            try:
                short_card = (
                    f"⚡ <b>Заказ #{order_db_id} [{order.source.value.upper()}]</b>\n"
                    f"<a href=\"{html.escape(order.url, quote=True)}\">{html.escape(order.title[:120])}</a>\n"
                    f"💰 Бюджет: {price_str} | Скор: {analysis.score}/10"
                )
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=short_card,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                return True
            except Exception:
                pass
            return False

    async def close(self) -> None:
        """Закрыть сессию бота, если она создавалась внутри класса."""
        if self._owns_bot and self._bot is not None:
            await self._bot.session.close()

"""Telegram notification sender via aiogram 3."""

import html
import logging
from typing import Optional
from aiogram import Bot
from aiogram.enums import ParseMode
from src.bot.keyboards import get_order_inline_keyboard
from src.config import settings
from src.models.analysis import AnalysisResult
from src.models.order import RawOrder

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Нотификатор доставки горячих лидов в Telegram."""

    def __init__(
        self,
        bot: Optional[Bot] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        self.chat_id = chat_id or settings.ADMIN_CHAT_ID
        self._bot = bot
        self._owns_bot = bot is None

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            if not settings.BOT_TOKEN:
                raise ValueError("BOT_TOKEN не задан в конфигурации (.env)")
            self._bot = Bot(token=settings.BOT_TOKEN)
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
        rec_price_str = f"{int(analysis.recommended_price):,} ₽".replace(",", " ")

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

        card_html = (
            f"{badge}\n\n"
            f"📌 <b>Биржа:</b> {order.source.value.upper()}\n"
            f"📝 <b>Заказ:</b> <a href=\"{order.url}\">{html.escape(order.title)}</a>\n\n"
            f"💰 <b>Бюджет клиента:</b> {price_str}\n"
            f"🎯 <b>Рекомендуемая цена:</b> {rec_price_str}\n"
            f"⏱ <b>Срок (PERT):</b> {analysis.realistic_days} дн. "
            f"(E={analysis.pert.expected_days:.1f} дн., σ={analysis.pert.sigma:.1f})\n"
            f"💼 <b>Кейс из досье:</b> <code>{html.escape(analysis.matched_project)}</code> "
            f"(Сложность: {analysis.complexity}/10, Время: {analysis.pure_dev_hours:.1f}ч)\n\n"
            f"⚠️ <b>Подводные камни:</b>\n{risks_list}\n\n"
            f"💡 <b>Резюме:</b> {html.escape(analysis.executive_summary)}"
        )
        return card_html

    async def send_lead(
        self,
        order: RawOrder,
        analysis: AnalysisResult,
        order_db_id: int,
    ) -> bool:
        """Отправить карточку заказа в Telegram."""
        if not self.chat_id or not settings.BOT_TOKEN:
            logger.warning(
                "BOT_TOKEN или ADMIN_CHAT_ID не заданы. Пропуск отправки в Telegram."
            )
            return False

        card_text = self.format_card(order, analysis)
        keyboard = get_order_inline_keyboard(order_db_id, order.url)

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=card_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
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
            return False

    async def close(self) -> None:
        """Закрыть сессию бота, если она создавалась внутри класса."""
        if self._owns_bot and self._bot is not None:
            await self._bot.session.close()

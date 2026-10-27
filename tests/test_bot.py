"""Тесты инициализации Telegram-бота и обработчиков (aiogram 3.7+)."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions
from src.bot.bot import create_bot_and_dispatcher
from src.bot.handlers import handle_recent
from src.models.analysis import AnalysisResult, PertEstimate
from src.models.order import OrderPriority, RawOrder, SourcePlatform
from src.notifiers.telegram_notifier import TelegramNotifier


def test_create_bot_and_dispatcher():
    """Проверка корректной инициализации бота без устаревших аргументов (aiogram 3.7+)."""
    mock_repo = MagicMock()
    bot, dp = create_bot_and_dispatcher(mock_repo)

    assert isinstance(bot, Bot)
    assert isinstance(dp, Dispatcher)
    assert bot.default is not None
    assert bot.default.parse_mode == ParseMode.HTML
    assert dp["repo"] is mock_repo


def test_telegram_notifier_bot_init_and_default_properties(monkeypatch):
    """Проверка инициализации бота в TelegramNotifier через DefaultBotProperties."""
    from src.config import settings

    monkeypatch.setattr(settings.secrets, "BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
    notifier = TelegramNotifier(chat_id=12345)
    bot = notifier.bot

    assert isinstance(bot, Bot)
    assert bot.default is not None
    assert bot.default.parse_mode == ParseMode.HTML


@pytest.mark.asyncio
async def test_telegram_notifier_send_lead_link_preview_options(monkeypatch):
    """Проверка отправки карточки с LinkPreviewOptions(is_disabled=True)."""
    from src.config import settings

    monkeypatch.setattr(settings.secrets, "BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
    notifier = TelegramNotifier(chat_id=12345)

    mock_send = AsyncMock()
    notifier._bot = MagicMock()
    notifier._bot.send_message = mock_send

    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="101",
        title="Парсер каталога",
        description="Собрать товары",
        url="https://kwork.ru/101",
        price=15000,
    )
    analysis = AnalysisResult(
        take_order=True,
        priority=OrderPriority.HOT,
        score=9,
        is_relevant=True,
        pert=PertEstimate(
            optimistic_days=1.0,
            most_likely_days=2.0,
            pessimistic_days=4.0,
            expected_days=2.17,
            sigma=0.5,
        ),
        realistic_days=2.0,
        recommended_price=15000,
        price_justification="В рамках рынка",
        complexity=4,
        pure_dev_hours=6.0,
        matched_project="parser",
        executive_summary="Разработка парсера",
    )

    result = await notifier.send_lead(order, analysis, order_db_id=1)
    assert result is True
    assert mock_send.call_count == 1

    kwargs = mock_send.call_args.kwargs
    assert "link_preview_options" in kwargs
    assert isinstance(kwargs["link_preview_options"], LinkPreviewOptions)
    assert kwargs["link_preview_options"].is_disabled is True
    assert "disable_web_page_preview" not in kwargs


@pytest.mark.asyncio
async def test_handle_recent_uses_link_preview_options():
    """Проверка команды /recent на использование LinkPreviewOptions(is_disabled=True)."""
    mock_message = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_recent_orders.return_value = [
        {
            "id": 1,
            "source": "kwork",
            "title": "Тестовый заказ",
            "url": "https://kwork.ru/1",
            "price": 5000,
            "priority": "hot",
            "status": "new",
        }
    ]

    await handle_recent(mock_message, mock_repo)
    assert mock_message.answer.call_count == 1

    kwargs = mock_message.answer.call_args.kwargs
    assert "link_preview_options" in kwargs
    assert isinstance(kwargs["link_preview_options"], LinkPreviewOptions)
    assert kwargs["link_preview_options"].is_disabled is True
    assert "disable_web_page_preview" not in kwargs

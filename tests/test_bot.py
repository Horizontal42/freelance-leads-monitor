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


def test_main_reply_keyboard():
    """Проверка постоянной клавиатуры быстрого доступа рядом с полем ввода."""
    from aiogram.types import ReplyKeyboardMarkup
    from src.bot.keyboards import get_main_reply_keyboard

    kb = get_main_reply_keyboard()
    assert isinstance(kb, ReplyKeyboardMarkup)
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True

    # Проверяем все ключевые кнопки управления
    all_texts = [btn.text for row in kb.keyboard for btn in row]
    assert "⚙️ Настройки" in all_texts
    assert "🩺 Проверка здоровья" in all_texts
    assert "⏱️ Аптайм и Статус" in all_texts
    assert "🔍 Сканировать" in all_texts


@pytest.mark.asyncio
async def test_handle_start_includes_reply_keyboard():
    """Проверка прикрепления главной клавиатуры при команде /start."""
    from src.bot.handlers import handle_start
    from src.bot.keyboards import get_main_reply_keyboard

    mock_message = AsyncMock()
    mock_message.from_user.id = 12345
    await handle_start(mock_message)

    assert mock_message.answer.call_count == 1
    kwargs = mock_message.answer.call_args.kwargs
    assert "reply_markup" in kwargs
    kb = kwargs["reply_markup"]
    assert kb.is_persistent is True


@pytest.mark.asyncio
async def test_handle_uptime_and_stats():
    """Проверка вывода аптайма и статистики базы."""
    from src.bot.handlers import handle_uptime_and_stats

    mock_message = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_stats.return_value = {
        "total": 42,
        "hot": 10,
        "normal": 20,
        "trash": 12,
        "sent_to_tg": 10,
    }

    await handle_uptime_and_stats(mock_message, mock_repo)
    assert mock_message.answer.call_count == 1
    text = mock_message.answer.call_args.args[0]
    assert "Аптайм" in text
    assert "Всего заказов/вакансий: <b>42</b>" in text
    assert "Горячих лидов (Tier 1): <b>10</b>" in text

    kwargs = mock_message.answer.call_args.kwargs
    assert "reply_markup" in kwargs
    assert kwargs["reply_markup"].is_persistent is True


def test_uptime_service():
    """Проверка сервиса отслеживания времени непрерывной работы."""
    from src.services.uptime import get_system_status_info, get_uptime_formatted

    info = get_system_status_info()
    assert "uptime" in info
    assert "start_time" in info
    assert "pid" in info

    formatted = get_uptime_formatted()
    assert isinstance(formatted, str)
    assert len(formatted) > 0


@pytest.mark.asyncio
async def test_bot_vacancy_settings_cycling():
    """Проверка переключения настроек вакансий (город, формат, мин. зп) в боте."""
    from src.bot.handlers import handle_setting_cycle
    from src.bot.keyboards import get_settings_inline_keyboard

    mock_callback = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_setting.return_value = "all"
    mock_repo.get_all_settings.return_value = {
        "vacancy_city": "moscow",
        "vacancy_work_format": "remote",
        "vacancy_min_salary": 120000,
    }

    # 1. Цикл города
    mock_callback.data = "set_cycle:vacancy_city"
    await handle_setting_cycle(mock_callback, mock_repo)
    mock_repo.set_setting.assert_called_with("vacancy_city", "moscow")

    # 2. Проверка отображения в клавиатуре
    kb = get_settings_inline_keyboard(mock_repo.get_all_settings.return_value)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Москва" in t for t in texts)
    assert any("Удаленка" in t for t in texts)
    assert any("120 000 ₽" in t for t in texts)


def test_split_plain_text_and_chunks():
    """Проверка разбиения длинного текста на части без превышения лимитов Telegram."""
    from src.bot.handlers import split_plain_text, split_proposal_chunks

    # Короткий текст
    assert split_plain_text("Короткий текст", max_chars=100) == ["Короткий текст"]

    # Длинный текст из абзацев
    long_text = "\n\n".join([f"Параграф {i}: " + ("x" * 150) for i in range(10)])
    chunks = split_plain_text(long_text, max_chars=400)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 400

    # Один очень длинный непрерывный абзац
    huge_para = "A" * 1500
    sub = split_plain_text(huge_para, max_chars=500)
    assert len(sub) == 3
    for s in sub:
        assert len(s) <= 500

    # Проверка split_proposal_chunks
    prop_chunks = split_proposal_chunks(long_text, max_chunk_escaped_len=500)
    for pc in prop_chunks:
        assert len(pc) <= 500


@pytest.mark.asyncio
async def test_handle_generate_proposal_splits_long_message():
    """Проверка генерации отклика, превышающего лимит 4096 символов."""
    from unittest.mock import patch
    from src.bot.handlers import handle_generate_proposal
    from src.models.analysis import ProposalResult

    mock_callback = AsyncMock()
    mock_callback.data = "gen_prop:42"
    mock_callback.message = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = {
        "id": 42,
        "source": "fl_ru",
        "external_id": "ext_42",
        "title": "Сложная система с ИИ",
        "description": "Описание ТЗ",
        "url": "https://fl.ru/projects/42",
        "price": 50000,
        "is_negotiable": 0,
        "is_pro_only": 0,
        "analysis_json": "{}",
    }

    # Генерируем очень длинный отклик (6000 символов)
    long_proposal_text = "\n\n".join([f"Раздел #{i}: " + ("текст описания решения " * 25) for i in range(10)])
    long_justification = "Обоснование: " + ("детализированный расчет ставки " * 10)

    with patch("src.analyzer.factory.get_llm_client") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.generate_proposal.return_value = ProposalResult(
            long_proposal_text,
            recommended_price=65000,
            market_price=70000,
            price_justification=long_justification,
        )
        mock_get_llm.return_value = mock_llm

        await handle_generate_proposal(mock_callback, mock_repo)

        # Проверяем, что отклик сохранился в базе
        mock_repo.update_proposal.assert_called_once()

        # Проверяем, что сообщения были отправлены частями и ни одно не превысило 4000 символов
        reply_calls = mock_callback.message.reply.call_args_list
        assert len(reply_calls) >= 2
        for call in reply_calls:
            text = call.kwargs.get("text") or (call.args[0] if call.args else "")
            assert len(text) <= 4000
            assert "❌ Ошибка" not in text


@pytest.mark.asyncio
async def test_handle_generate_proposal_kwork_enforces_2000_limit():
    """Проверка жесткого ограничения отклика на Kwork в 2000 символов в боте."""
    from unittest.mock import patch
    from src.bot.handlers import handle_generate_proposal
    from src.models.analysis import ProposalResult

    mock_callback = AsyncMock()
    mock_callback.data = "gen_prop:101"
    mock_callback.message = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = {
        "id": 101,
        "source": "kwork",
        "external_id": "kw_101",
        "title": "Бот для Kwork",
        "description": "Описание ТЗ",
        "url": "https://kwork.ru/projects/101",
        "price": 30000,
        "is_negotiable": 0,
        "is_pro_only": 0,
        "analysis_json": "{}",
    }

    # Имитируем длинный ответ от модели (2800 символов)
    long_proposal_text = "\n\n".join([f"Раздел #{i}: " + ("архитектурное решение задачи " * 15) for i in range(10)])
    assert len(long_proposal_text) > 2400

    with patch("src.analyzer.factory.get_llm_client") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.generate_proposal.return_value = ProposalResult(
            long_proposal_text,
            recommended_price=30000,
            market_price=35000,
            price_justification="Бюджет адекватен",
        )
        mock_get_llm.return_value = mock_llm

        await handle_generate_proposal(mock_callback, mock_repo)

        # Проверяем аргументы вызова update_proposal
        update_args = mock_repo.update_proposal.call_args
        saved_text = update_args.kwargs.get("proposal_text")
        assert saved_text is not None
        assert len(saved_text) <= 2000



@pytest.mark.asyncio
async def test_handle_copy_proposal_splits_long_message():
    """Проверка копирования длинного отклика частями."""
    from src.bot.handlers import handle_copy_proposal

    mock_callback = AsyncMock()
    mock_callback.data = "copy:42"
    mock_callback.message = AsyncMock()

    mock_repo = AsyncMock()
    long_proposal_text = "\n\n".join([f"Часть #{i}: " + ("готовое сопроводительное письмо " * 20) for i in range(8)])
    mock_repo.get_by_id.return_value = {
        "id": 42,
        "proposal_text": long_proposal_text,
    }

    await handle_copy_proposal(mock_callback, mock_repo)

    reply_calls = mock_callback.message.reply.call_args_list
    assert len(reply_calls) >= 2
    for call in reply_calls:
        text = call.kwargs.get("text") or (call.args[0] if call.args else "")
        assert len(text) <= 4000


@pytest.mark.asyncio
async def test_handle_copy_proposal_cleans_legacy_json_and_formats_code_block():
    """Проверка, что устаревший сырой JSON в proposal_text очищается и оформляется в кликабельный pre/code."""
    from src.bot.handlers import handle_copy_proposal

    mock_callback = AsyncMock()
    mock_callback.data = "copy:1510"
    mock_callback.message = AsyncMock()

    mock_repo = AsyncMock()
    # Сырой JSON в proposal_text как в заказе 1510
    raw_json_in_db = '''```json
{
  "market_price": 45000,
  "recommended_price": 42000,
  "price_justification": "Обоснование ставки",
  "proposal_text": "Добрый день! Разрабатываю ботов на Python."
}
```'''
    mock_repo.get_by_id.return_value = {
        "id": 1510,
        "proposal_text": raw_json_in_db,
    }

    await handle_copy_proposal(mock_callback, mock_repo)

    reply_calls = mock_callback.message.reply.call_args_list
    assert len(reply_calls) == 1
    text = reply_calls[0].kwargs.get("text") or (reply_calls[0].args[0] if reply_calls[0].args else "")

    # Проверяем, что нет сырого JSON, а есть чистый отклик в pre/code
    assert '```json' not in text
    assert '"market_price"' not in text
    assert "<pre><code>Добрый день! Разрабатываю ботов на Python.</code></pre>" in text
    assert "📋" in text


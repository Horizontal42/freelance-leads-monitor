"""Configuration settings for Freelance Leads Monitor."""

from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Дефолтный черный список стоп-слов (отсекаем мусор, студенческие работы и не наш профиль)
DEFAULT_STOP_WORDS: List[str] = [
    "диплом",
    "курсов",
    "реферат",
    "контрольн",
    "студент",
    "лабораторн",
    "1с",
    "1c",
    "битрикс-сайт",
    "tilda",
    "тильда",
    "wordpress",
    "вордпресс",
    "верстка",
    "верстку",
    "дизайн",
    "дизайнер",
    "seo",
    "сео",
    "копирайт",
    "рерайт",
    "таргет",
    "smm",
    "накрутк",
    "отзыв",
    "лайк",
]

# Дефолтный белый список ключевых слов (наш стек и специфика)
DEFAULT_KEYWORDS: List[str] = [
    "python",
    "питон",
    "парсер",
    "парсинг",
    "парсить",
    "скрейпинг",
    "скрейпер",
    "бот",
    "telegram",
    "телеграм",
    "aiogram",
    "fastapi",
    "django",
    "flask",
    "crm",
    "битрикс24",
    "bitrix24",
    "api",
    "интеграци",
    "llm",
    "ии",
    "нейросет",
    "whisper",
    "автоматизац",
    "scraping",
    "selenium",
    "playwright",
    "curl_cffi",
    "opencv",
    "yolo",
    "rag",
    "qdrant",
    "tauri",
    "asyncio",
    "google sheets",
    "гугл таблиц",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    BOT_TOKEN: str = ""
    ADMIN_CHAT_ID: int = 0

    # LLM Provider
    LLM_PROVIDER: str = "antigravity"  # "antigravity" | "mistral"
    ANTIGRAVITY_BIN: str = "agy"
    ANTIGRAVITY_MODEL: str = "gemini-3.8-flash-medium"
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "ministral-8b-latest"

    # Database
    DB_PATH: Path = BASE_DIR / "data" / "jobs.db"

    # Polling Intervals (seconds)
    KWORK_POLL_INTERVAL: int = 180
    FL_POLL_INTERVAL: int = 180

    # Source Endpoints
    KWORK_BASE_URL: str = "https://kwork.ru"
    KWORK_CATEGORY_IDS: List[int] = Field(default_factory=lambda: [11, 41])
    FL_RSS_URL: str = "https://www.fl.ru/rss/all.xml"

    # Filtering & Tiering
    MIN_BUDGET: int = 10_000
    HOT_SCORE_THRESHOLD: int = 7
    STOP_WORDS: List[str] = Field(default_factory=lambda: DEFAULT_STOP_WORDS)
    KEYWORDS: List[str] = Field(default_factory=lambda: DEFAULT_KEYWORDS)


settings = Settings()

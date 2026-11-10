"""Domain models for freelance orders."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SourcePlatform(str, Enum):
    KWORK = "kwork"
    FL_RU = "fl_ru"
    FREELANCE_RU = "freelance_ru"
    PCHEL_NET = "pchel_net"
    REMOTE_JOB = "remote_job"  # Deprecated
    HH_RU = "hh_ru"
    HABR_CAREER = "habr_career"
    CUSTOM = "custom"


class OrderPriority(str, Enum):
    TRASH = "trash"      # Tier 3: отсеян фильтром
    NORMAL = "normal"    # Tier 2: прошел фильтр, но score < 7 (сохраняем в БД/сайт)
    HOT = "hot"          # Tier 1: score >= 7 (мгновенный пуш в Telegram)


class OrderStatus(str, Enum):
    NEW = "new"
    REJECTED = "rejected"
    ANALYZED = "analyzed"
    SENT_TO_TG = "sent_to_tg"
    ARCHIVED = "archived"


class RawOrder(BaseModel):
    """Сырой заказ, полученный от сборщика (коллектора)."""

    source: SourcePlatform
    external_id: str
    title: str
    description: str
    url: str
    price: Optional[float] = None
    is_negotiable: bool = False
    is_pro_only: bool = False
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    raw_payload: Optional[Dict[str, Any]] = None
    attachments_text: Optional[str] = None

    @field_validator("title", "description", "attachments_text", mode="before")
    @classmethod
    def sanitize_null_bytes(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.replace("\x00", "")
        return v

    @property
    def full_text(self) -> str:
        """Объединенный текст названия, описания и тегов для фильтрации."""
        return f"{self.title}\n{self.description}\n{' '.join(self.tags)}"

    @property
    def is_ai_first(self) -> bool:
        """Определяет, относится ли заказ или вакансия к приоритетной категории AI-First / Agentic."""
        import re
        text = f"{self.title}\n{self.description}\n{self.attachments_text or ''}\n{' '.join(self.tags)}".lower()
        patterns = [
            r"ai[- ]?first",
            r"ai[- ]?native",
            r"agentic",
            r"ai[- ]?агент",
            r"ai[- ]?agents?",
        ]
        return any(re.search(p, text) for p in patterns)


class FilterResult(BaseModel):
    """Результат работы эвристического Hard-Filter."""

    passed: bool
    reason: str
    matched_keywords: List[str] = Field(default_factory=list)
    matched_stopwords: List[str] = Field(default_factory=list)

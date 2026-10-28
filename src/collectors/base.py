"""Abstract base class for order collectors."""

from abc import ABC, abstractmethod
import logging
from typing import List, Optional
from src.models.order import RawOrder

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Базовый абстрактный класс сборщика заказов."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    async def fetch_new_orders(self, is_cold_start: Optional[bool] = None) -> List[RawOrder]:
        """Собрать свежие заказы с площадки."""
        pass

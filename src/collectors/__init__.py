"""Collectors package exports."""

from src.collectors.base import BaseCollector
from src.collectors.kwork import KworkCollector
from src.collectors.fl_ru import FlRuCollector

__all__ = ["BaseCollector", "KworkCollector", "FlRuCollector"]

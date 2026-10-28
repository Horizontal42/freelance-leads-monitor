"""System uptime and process status tracking."""

from datetime import datetime
import os
import time

START_TIME = datetime.now()
START_TIMESTAMP = time.time()


def get_uptime_seconds() -> float:
    """Вернуть количество секунд непрерывной работы приложения."""
    return time.time() - START_TIMESTAMP


def get_uptime_formatted() -> str:
    """Сформировать человекочитаемую строку аптайма."""
    total_sec = int(get_uptime_seconds())
    days, rem = divmod(total_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} дн.")
    if hours > 0 or days > 0:
        parts.append(f"{hours} ч.")
    if minutes > 0 or (days == 0 and hours == 0):
        parts.append(f"{minutes} мин.")
    if days == 0 and hours == 0 and minutes == 0:
        parts.append(f"{seconds} сек.")

    return " ".join(parts)


def get_system_status_info() -> dict:
    """Собрать информацию о статусе системы и времени непрерывной работы."""
    return {
        "start_time": START_TIME.strftime("%d.%m.%Y %H:%M:%S"),
        "uptime": get_uptime_formatted(),
        "uptime_seconds": int(get_uptime_seconds()),
        "pid": os.getpid(),
    }

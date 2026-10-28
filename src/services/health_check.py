"""Health check service for freelance exchanges, AI models, and database."""

import asyncio
from datetime import datetime
import os
from pathlib import Path
import time
from typing import Any, Dict, List
import httpx
from src.config import settings
from src.storage.db import get_db_connection


class HealthCheckService:
    """Сервис мониторинга доступности и времени отклика бирж, ИИ-моделей и базы данных."""

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }

    async def check_url(self, name: str, url: str) -> Dict[str, Any]:
        """Проверить доступность и latency внешнего веб-ресурса."""
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                is_ok = resp.status_code in (200, 301, 302, 304)
                return {
                    "name": name,
                    "url": url,
                    "ok": is_ok,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "error": None if is_ok else f"HTTP {resp.status_code}",
                }
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "name": name,
                "url": url,
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error": str(e)[:100],
            }

    async def check_mistral(self) -> Dict[str, Any]:
        """Проверить доступность Mistral API."""
        key = settings.MISTRAL_API_KEY
        if not key:
            return {
                "name": "Mistral API",
                "ok": False,
                "status_code": None,
                "latency_ms": 0,
                "error": "API ключ не настроен в .env",
            }
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {key}"},
                timeout=self.timeout,
            ) as client:
                resp = await client.get("https://api.mistral.ai/v1/models")
                latency_ms = int((time.perf_counter() - t0) * 1000)
                is_ok = resp.status_code == 200
                return {
                    "name": "Mistral API",
                    "ok": is_ok,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "error": None if is_ok else resp.text[:80],
                }
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "name": "Mistral API",
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error": str(e)[:100],
            }

    async def check_antigravity(self) -> Dict[str, Any]:
        """Проверить доступность Antigravity CLI."""
        binary = getattr(settings, "ANTIGRAVITY_BIN", None) or getattr(settings, "ANTIGRAVITY_BINARY", None) or "agy"
        t0 = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=4.0)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            version_text = stdout.decode().strip() or stderr.decode().strip()
            is_ok = proc.returncode == 0
            return {
                "name": "Antigravity CLI (agy)",
                "ok": is_ok,
                "status_code": proc.returncode,
                "latency_ms": latency_ms,
                "details": version_text if is_ok else None,
                "error": None if is_ok else f"Exit code {proc.returncode}: {version_text}",
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "name": "Antigravity CLI (agy)",
                "ok": False,
                "status_code": None,
                "latency_ms": latency_ms,
                "error": str(e)[:100],
            }

    async def check_database(self) -> Dict[str, Any]:
        """Проверить SQLite БД и режим WAL."""
        t0 = time.perf_counter()
        try:
            async with get_db_connection() as db:
                async with db.execute("PRAGMA journal_mode;") as cursor:
                    journal_mode = (await cursor.fetchone())[0]
                async with db.execute("SELECT COUNT(*) FROM orders;") as cursor:
                    orders_count = (await cursor.fetchone())[0]

            latency_ms = int((time.perf_counter() - t0) * 1000)
            db_path = Path(settings.DB_PATH)
            size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2) if db_path.exists() else 0.0
            return {
                "name": "SQLite WAL Database",
                "ok": True,
                "latency_ms": latency_ms,
                "details": f"Режим: {journal_mode.upper()}, размер: {size_mb} MB, записей: {orders_count}",
                "error": None,
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "name": "SQLite WAL Database",
                "ok": False,
                "latency_ms": latency_ms,
                "error": str(e)[:100],
            }

    async def run_full_check(self) -> Dict[str, Any]:
        """Выполнить параллельную проверку всех систем."""
        exchanges = [
            ("Kwork", "https://kwork.ru"),
            ("FL.ru (RSS)", settings.FL_RSS_URL),
            ("Freelance.ru", settings.FREELANCE_RU_BASE_URL),
            ("Pchel.net", settings.PCHEL_NET_BASE_URL),
            ("HeadHunter API", "https://api.hh.ru"),
            ("Хабр Карьера (RSS)", "https://career.habr.com/vacancies/rss"),
        ]

        # Запускаем все проверки параллельно
        tasks = [self.check_url(name, url) for name, url in exchanges]
        ai_tasks = [self.check_mistral(), self.check_antigravity(), self.check_database()]

        all_results = await asyncio.gather(*(tasks + ai_tasks))

        exchange_results = all_results[:len(exchanges)]
        ai_and_db_results = all_results[len(exchanges):]

        all_ok = all(r["ok"] for r in all_results)

        return {
            "all_ok": all_ok,
            "checked_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "exchanges": exchange_results,
            "services": ai_and_db_results,
        }

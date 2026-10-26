"""Database initialization and schema management with SQLite WAL mode."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
import aiosqlite
from src.config import settings

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    url TEXT NOT NULL,
    price REAL,
    is_negotiable INTEGER NOT NULL DEFAULT 0,
    is_pro_only INTEGER NOT NULL DEFAULT 0,
    tags TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    priority TEXT NOT NULL DEFAULT 'normal',
    filter_reason TEXT,
    score INTEGER,
    recommended_price REAL,
    realistic_days REAL,
    matched_project TEXT,
    proposal_text TEXT,
    analysis_json TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_source_ext ON orders(source, external_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_priority ON orders(priority);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);
"""


@asynccontextmanager
async def get_db_connection(
    db_path: Path | str | None = None,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Асинхронный контекстный менеджер подключения к SQLite с WAL-режимом."""
    path = Path(db_path or settings.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA busy_timeout = 5000;")
        await db.execute("PRAGMA synchronous = NORMAL;")
        await db.execute("PRAGMA foreign_keys = ON;")
        yield db


async def init_db(db_path: Path | str | None = None) -> None:
    """Инициализировать схему БД."""
    async with get_db_connection(db_path) as db:
        await db.executescript(CREATE_TABLES_SQL)
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN is_pro_only INTEGER NOT NULL DEFAULT 0;")
        except Exception:
            pass  # колонка уже существует
        await db.commit()


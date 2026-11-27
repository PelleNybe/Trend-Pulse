"""
MindSpider Database initialization（SQLAlchemy 2.x asynchronous engine）

This script creates the MindSpider extension table（Detached from TrendPulse original table）。
Supports MySQL and PostgreSQL，Requires a connectable database instance。

Data model definition location：
- MindSpider/schema/models_sa.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

mindspider_root = Path(__file__).resolve().parent.parent
repo_root = mindspider_root.parent
for p in (str(mindspider_root), str(repo_root)):
    if p not in sys.path:
        sys.path.append(p)

try:
    from .models_sa import Base
    from . import models_bigdata
except ImportError:
    from models_sa import Base
    import models_bigdata

from config import settings

def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(key)
    return v if v not in (None, "") else default


def _build_database_url() -> str:

    database_url = settings.DATABASE_URL if hasattr(settings, "DATABASE_URL") else None
    if database_url:
        return database_url

    dialect = (settings.DB_DIALECT or "mysql").lower()
    if dialect == "sqlite":
        db_name = settings.DB_NAME or "mindspider.db"
        return f"sqlite:///{db_name}"

    host = settings.DB_HOST or "localhost"
    port = str(settings.DB_PORT or ("3306" if dialect == "mysql" else "5432"))
    user = settings.DB_USER or "root"
    password = settings.DB_PASSWORD or ""
    password = quote_plus(password)
    db_name = settings.DB_NAME or "mindspider"

    if dialect in ("postgresql", "postgres"):
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"

    return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{db_name}"


async def _create_views_if_needed(engine_dialect: str, database_url: Optional[str] = None):
    engine_dialect = engine_dialect.lower()
    if engine_dialect == "sqlite":
        view_prefix_1 = "CREATE VIEW IF NOT EXISTS v_topic_crawling_stats AS\n"
        view_prefix_2 = "CREATE VIEW IF NOT EXISTS v_daily_summary AS\n"
    else:
        view_prefix_1 = "CREATE OR REPLACE VIEW v_topic_crawling_stats AS\n"
        view_prefix_2 = "CREATE OR REPLACE VIEW v_daily_summary AS\n"

    v_topic_crawling_stats = (
        view_prefix_1 +
        "SELECT dt.topic_id, dt.topic_name, dt.extract_date, dt.processing_status,\n"
        "       COUNT(DISTINCT ct.task_id) AS total_tasks,\n"
        "       SUM(CASE WHEN ct.task_status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,\n"
        "       SUM(CASE WHEN ct.task_status = 'failed' THEN 1 ELSE 0 END) AS failed_tasks,\n"
        "       SUM(COALESCE(ct.total_crawled,0)) AS total_content_crawled,\n"
        "       SUM(COALESCE(ct.success_count,0)) AS total_success_count,\n"
        "       SUM(COALESCE(ct.error_count,0)) AS total_error_count\n"
        "FROM daily_topics dt\n"
        "LEFT JOIN crawling_tasks ct ON dt.topic_id = ct.topic_id\n"
        "GROUP BY dt.topic_id, dt.topic_name, dt.extract_date, dt.processing_status"
    )

    v_daily_summary = (
        view_prefix_2 +
        "SELECT dn.crawl_date AS crawl_date,\n"
        "       COUNT(DISTINCT dn.news_id) AS total_news,\n"
        "       COUNT(DISTINCT dn.source_platform) AS platforms_covered,\n"
        "       (SELECT COUNT(*) FROM daily_topics WHERE extract_date = dn.crawl_date) AS topics_extracted,\n"
        "       (SELECT COUNT(*) FROM crawling_tasks WHERE scheduled_date = dn.crawl_date) AS tasks_created\n"
        "FROM daily_news dn\n"
        "GROUP BY dn.crawl_date\n"
        "ORDER BY dn.crawl_date DESC"
    )

    db_url = database_url or _build_database_url()
    if db_url.startswith("sqlite:///"):
        from sqlalchemy import create_engine
        sync_engine = create_engine(db_url)
        with sync_engine.begin() as conn:
            conn.execute(text(v_topic_crawling_stats))
            conn.execute(text(v_daily_summary))
        sync_engine.dispose()
        return

    from sqlalchemy.ext.asyncio import AsyncEngine
    engine: AsyncEngine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text(v_topic_crawling_stats))
        await conn.execute(text(v_daily_summary))
    await engine.dispose()


async def main(database_url: Optional[str] = None) -> None:
    db_url = database_url or _build_database_url()
    if db_url.startswith("sqlite:///"):
        from sqlalchemy import create_engine
        sync_engine = create_engine(db_url, future=True)
        Base.metadata.create_all(sync_engine)
        dialect_name = sync_engine.url.get_backend_name()
        sync_engine.dispose()
        await _create_views_if_needed(dialect_name, db_url)
        logger.info("[init_database_sa] SQLite data tables and views are created")
        return

    engine = create_async_engine(db_url, pool_pre_ping=True, pool_recycle=1800)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    dialect_name = engine.url.get_backend_name()
    await _create_views_if_needed(dialect_name, db_url)

    await engine.dispose()
    logger.info("[init_database_sa] Data tables and views are created")


if __name__ == "__main__":
    asyncio.run(main())



"""
MindSpider Financial Data & Topic Sentiment Collector.

Fetches OHLCV market data + technical indicators via yfinance and pandas_ta,
extracts daily topics and sentiment via BroadTopicExtraction and DeepSentimentCrawling,
and persists structured records to the configured SQLAlchemy database.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import pandas as pd
import pandas_ta as ta
import yfinance as yf
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Ensure both MindSpider/ and repo root are importable
_MINDSPIDER_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MINDSPIDER_DIR.parent
for _path in (str(_MINDSPIDER_DIR), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from config import settings
from MindSpider.BroadTopicExtraction import BroadTopicExtractor
from MindSpider.DeepSentimentCrawling import DeepSentimentCrawler
from MindSpider.schema.models_sa import (
    Base,
    CrawlingTask,
    DailyNews,
    DailyTopic,
    TopicNewsRelation,
)


def resolve_sync_database_url(explicit_url: Optional[str] = None) -> str:
    """Resolve synchronous SQLAlchemy database URL from argument or settings."""
    if explicit_url:
        return explicit_url.replace("+asyncpg", "+psycopg2").replace("+aiomysql", "+pymysql")

    database_url = getattr(settings, "DATABASE_URL", None)
    if database_url:
        return str(database_url).replace("+asyncpg", "+psycopg2").replace("+aiomysql", "+pymysql")

    dialect = (getattr(settings, "DB_DIALECT", None) or "sqlite").lower()
    if dialect == "sqlite":
        db_name = getattr(settings, "DB_NAME", None) or str(_MINDSPIDER_DIR / "mindspider.db")
        if not db_name.endswith(".db") and ":" not in db_name:
            db_name = str(_MINDSPIDER_DIR / f"{db_name}.db")
        return f"sqlite:///{db_name}"

    host = getattr(settings, "DB_HOST", None) or "localhost"
    user = getattr(settings, "DB_USER", None) or "root"
    password = quote_plus(getattr(settings, "DB_PASSWORD", None) or "")
    db_name = getattr(settings, "DB_NAME", None) or "mindspider"
    if dialect in ("postgresql", "postgres"):
        port = getattr(settings, "DB_PORT", None) or 5432
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
    port = getattr(settings, "DB_PORT", None) or 3306
    charset = getattr(settings, "DB_CHARSET", None) or "utf8mb4"
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}?charset={charset}"


def compute_technical_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Flatten OHLCV DataFrame and add SMA, RSI, MACD, and Bollinger Bands."""
    if data.empty:
        return data
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]

    data["SMA_20"] = ta.sma(data["Close"], length=20)
    data["SMA_50"] = ta.sma(data["Close"], length=50)
    data["SMA_200"] = ta.sma(data["Close"], length=200)
    data["RSI_14"] = ta.rsi(data["Close"], length=14)

    macd = ta.macd(data["Close"])
    if macd is not None and not macd.empty:
        data = pd.concat([data, macd], axis=1)

    bbands = ta.bbands(data["Close"])
    if bbands is not None and not bbands.empty:
        data = pd.concat([data, bbands], axis=1)

    return data


def persist_collection_results(
    db_url: str,
    ticker: str,
    news_items: List[Dict[str, Any]],
    topics: List[Dict[str, Any]],
    crawl_tasks: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Persist news, topics, topic-news relations, and task logs using SQLAlchemy."""
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)

    today = date.today()
    now_ts = int(time.time())
    counts = {"news": 0, "topics": 0, "relations": 0, "tasks": 0}

    with Session(engine) as session:
        existing_news_ids = {
            row[0]
            for row in session.query(DailyNews.news_id).filter(DailyNews.crawl_date == today).all()
        }
        for item in news_items:
            if item["news_id"] in existing_news_ids:
                continue
            session.add(
                DailyNews(
                    news_id=item["news_id"],
                    source_platform=item["source_platform"],
                    title=item["title"],
                    url=item.get("url"),
                    description=item.get("description"),
                    extra_info=item.get("extra_info") or f"ticker={ticker}",
                    crawl_date=today,
                    rank_position=item.get("rank_position"),
                    add_ts=now_ts,
                    last_modify_ts=now_ts,
                )
            )
            counts["news"] += 1

        existing_topic_ids = {
            row[0]
            for row in session.query(DailyTopic.topic_id).filter(DailyTopic.extract_date == today).all()
        }
        for topic in topics:
            if topic["topic_id"] not in existing_topic_ids:
                session.add(
                    DailyTopic(
                        topic_id=topic["topic_id"],
                        topic_name=topic["topic_name"],
                        topic_description=topic.get("topic_description"),
                        keywords=topic.get("keywords"),
                        extract_date=today,
                        relevance_score=topic.get("relevance_score"),
                        news_count=topic.get("news_count", 0),
                        processing_status="completed",
                        add_ts=now_ts,
                        last_modify_ts=now_ts,
                    )
                )
                counts["topics"] += 1

            for nid in topic.get("news_ids", []):
                session.add(
                    TopicNewsRelation(
                        topic_id=topic["topic_id"],
                        news_id=nid,
                        relation_score=topic.get("relevance_score"),
                        extract_date=today,
                        add_ts=now_ts,
                    )
                )
                counts["relations"] += 1

        for task in crawl_tasks:
            session.add(
                CrawlingTask(
                    task_id=task["task_id"],
                    topic_id=task["topic_id"],
                    platform=task["platform"],
                    search_keywords=task["search_keywords"],
                    task_status=task.get("task_status", "completed"),
                    start_time=task.get("start_time"),
                    end_time=task.get("end_time"),
                    total_crawled=task.get("total_crawled", 0),
                    success_count=task.get("success_count", 0),
                    error_count=task.get("error_count", 0),
                    config_params=f"sentiment={task.get('average_sentiment_score', 0.0)}",
                    scheduled_date=today,
                    add_ts=now_ts,
                    last_modify_ts=now_ts,
                )
            )
            counts["tasks"] += 1

        session.commit()

    engine.dispose()
    return counts


def fetch_financial_data(
    ticker: str = "SPY",
    complete: bool = False,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch OHLCV data, compute indicators, extract news/topics/sentiment, and persist to DB."""
    logger.info(f"Connecting to financial data feeds for {ticker}...")
    data = yf.download(ticker, period="max" if complete else "1y", progress=False)
    rows_fetched = len(data)
    if not data.empty:
        data = compute_technical_indicators(data)
        logger.info(f"Calculated technical indicators on {rows_fetched} OHLCV rows for {ticker}.")
    else:
        logger.warning(f"No OHLCV rows returned for {ticker}; continuing with news/topic collection.")

    extractor = BroadTopicExtractor()
    news_items = extractor.collect_news(ticker=ticker)
    topics = extractor.extract_topics(news_items)

    crawler = DeepSentimentCrawler()
    crawl_tasks = crawler.analyze_topics_sentiment(topics, news_items)

    resolved_url = resolve_sync_database_url(db_url)
    persisted = persist_collection_results(resolved_url, ticker, news_items, topics, crawl_tasks)
    logger.info(
        f"Persisted MindSpider data to database: news={persisted['news']}, "
        f"topics={persisted['topics']}, relations={persisted['relations']}, tasks={persisted['tasks']}"
    )
    return {
        "ticker": ticker,
        "ohlcv_rows": rows_fetched,
        "persisted": persisted,
        "db_url": resolved_url,
    }


def main():
    parser = argparse.ArgumentParser(description="Trend Pulse Financial Data Collector")
    parser.add_argument("--ticker", type=str, default="SPY", help="Ticker symbol to fetch data for")
    parser.add_argument("--complete", action="store_true", help="Fetch complete dataset")
    parser.add_argument("--broad-topic", action="store_true", help="Extract daily broad financial topics")
    parser.add_argument("--deep-sentiment", action="store_true", help="Run deep sentiment analysis on topics")
    parser.add_argument("--status", action="store_true", help="Show database status and statistics")
    parser.add_argument("--db-url", type=str, default=None, help="Explicit synchronous SQLAlchemy database URL")

    args = parser.parse_args()

    if args.status:
        from MindSpider.schema.db_manager import DatabaseManager
        mgr = DatabaseManager()
        try:
            mgr.show_tables()
            mgr.show_statistics()
        finally:
            mgr.close()
        return

    logger.info("Starting Trend Pulse Financial Data Collector...")
    result = fetch_financial_data(ticker=args.ticker, complete=args.complete, db_url=args.db_url)
    logger.info(f"Collection complete for {args.ticker}: {result['persisted']}")


if __name__ == "__main__":
    main()

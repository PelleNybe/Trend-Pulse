"""Unit and SQLite persistence tests for ForumEngine.llm_host and MindSpider."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_forum_host_requires_llm_and_handles_mem0_variants():
    import ForumEngine.llm_host as llm_host_mod

    host_unconfigured = llm_host_mod.FinancialCommitteeHost(llm_client=None)
    with pytest.raises(RuntimeError):
        host_unconfigured.synthesize_discussion("NVDA volatility context")

    fake_mem0 = MagicMock()
    # Mem0 sometimes returns {"results": [...]} and sometimes [...]
    fake_mem0.search.return_value = {"results": [{"memory": "Prior macro note on CPI"}]}

    fake_llm = MagicMock()
    fake_llm.stream_invoke_to_string.return_value = (
        'Preamble text {"synthesis": "Rates drive duration.", '
        '"directives": [{"agent": "Macro Researcher", "directive": "Check 10Y yields"}]} trailing'
    )

    with patch.object(llm_host_mod, "mem0_available", True), patch.object(
        llm_host_mod, "host_memory", fake_mem0
    ):
        host = llm_host_mod.FinancialCommitteeHost(llm_client=fake_llm)
        output = host.synthesize_discussion("Bond yields rose", topic="Rates")
        parsed = json.loads(output)
        assert parsed["synthesis"] == "Rates drive duration."
        assert len(parsed["directives"]) == 1
        fake_mem0.add.assert_called_once()


def test_generate_host_speech_skips_cleanly_when_unconfigured():
    import ForumEngine.llm_host as llm_host_mod

    with patch("config.settings") as mock_settings:
        mock_settings.FORUM_HOST_API_KEY = None
        mock_settings.FORUM_HOST_MODEL_NAME = None
        mock_settings.FORUM_HOST_BASE_URL = None
        assert llm_host_mod.generate_host_speech(["Agent line 1"]) is None


def test_mindspider_extraction_sentiment_and_sqlite_persistence(tmp_path):
    from MindSpider.BroadTopicExtraction import BroadTopicExtractor
    from MindSpider.DeepSentimentCrawling import DeepSentimentCrawler
    from MindSpider.main import compute_technical_indicators, persist_collection_results

    extractor = BroadTopicExtractor(feeds=[])
    sample_news = [
        {
            "news_id": "n1",
            "source_platform": "yfinance:SPY",
            "title": "Semiconductor earnings surge drives Nasdaq rally",
            "url": "https://example.com/1",
            "description": "Strong AI server shipments boost market outlook",
            "rank_position": 1,
        },
        {
            "news_id": "n2",
            "source_platform": "yfinance:SPY",
            "title": "Treasury yields climb after inflation warning",
            "url": "https://example.com/2",
            "description": "Bond volatility weighs on defensive utilities",
            "rank_position": 2,
        },
    ]

    topics = extractor.extract_topics(sample_news, max_topics=2)
    assert len(topics) == 2
    assert all(t["news_count"] >= 1 for t in topics)

    crawler = DeepSentimentCrawler()
    tasks = crawler.analyze_topics_sentiment(topics, sample_news)
    assert len(tasks) == len(topics)
    assert all(t["task_status"] == "completed" for t in tasks)

    db_path = tmp_path / "mindspider_test.db"
    db_url = f"sqlite:///{db_path}"
    counts = persist_collection_results(db_url, "SPY", sample_news, topics, tasks)
    assert counts["news"] == 2
    assert counts["topics"] == 2
    assert counts["relations"] >= 2
    assert counts["tasks"] == len(tasks)

    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    assert {"daily_news", "daily_topics", "topic_news_relation", "crawling_tasks"}.issubset(tables)
    engine.dispose()

    # Verify technical indicators computation on MultiIndex DataFrame
    idx = pd.date_range("2025-01-01", periods=40, freq="D")
    close = pd.Series([100.0 + i * 0.5 for i in range(40)], index=idx)
    df = pd.DataFrame({("Close", "SPY"): close, ("Volume", "SPY"): 1_000_000}, index=idx)
    enriched = compute_technical_indicators(df)
    assert "SMA_20" in enriched.columns
    assert "RSI_14" in enriched.columns


def test_mindspider_init_database_and_db_manager_sqlite(tmp_path):
    import asyncio
    from MindSpider.schema import init_database
    from MindSpider.schema import db_manager

    db_path = tmp_path / "schema_test.db"
    db_url = f"sqlite:///{db_path}"
    asyncio.run(init_database.main(database_url=db_url))

    with patch.object(db_manager.settings, "DATABASE_URL", db_url), patch.object(
        db_manager.settings, "DB_DIALECT", "sqlite"
    ), patch.object(db_manager.settings, "DB_NAME", str(db_path)):
        mgr = db_manager.DatabaseManager()
        try:
            tables = set(inspect(mgr.engine).get_table_names())
            assert "daily_news" in tables
            assert "daily_topics" in tables
            mgr.show_tables()
        finally:
            mgr.close()

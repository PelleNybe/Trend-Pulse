"""Unit tests for SearchNodes, InsightEngine tools/agent, TokenTracker, and WebhookAlerter."""

import builtins
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_parse_search_node_output_preserves_extra_keys():
    from InsightEngine.nodes.search_node import FirstSearchNode as InsightFirstSearchNode
    from MediaEngine.nodes.search_node import FirstSearchNode as MediaFirstSearchNode
    from QueryEngine.nodes.search_node import FirstSearchNode as QueryFirstSearchNode

    raw = json.dumps({
        "search_query": "NVDA Q3 guidance",
        "reasoning": "Check AI chip demand",
        "search_tool": "search_topic_by_date",
        "start_date": "2025-01-01",
        "end_date": "2025-03-01",
        "platform": "news",
        "time_period": "month",
    })

    for cls in (InsightFirstSearchNode, MediaFirstSearchNode, QueryFirstSearchNode):
        node = cls(llm_client=MagicMock())
        parsed = node.process_output(raw)
        assert parsed["search_query"] == "NVDA Q3 guidance"
        assert parsed["reasoning"] == "Check AI chip demand"
        assert parsed["search_tool"] == "search_topic_by_date"
        assert parsed["start_date"] == "2025-01-01"
        assert parsed["end_date"] == "2025-03-01"
        assert parsed["platform"] == "news"
        assert parsed["time_period"] == "month"


def test_financial_sentiment_analyzer_scoring_and_negation():
    from InsightEngine.tools.sentiment_analyzer import (
        FinancialSentimentAnalyzer,
        BatchSentimentResult,
        SentimentResult,
    )

    analyzer = FinancialSentimentAnalyzer()
    analyzer.initialize()

    pos = analyzer.analyze_single_text("Company profits surge to record breakout growth after upgrade")
    assert isinstance(pos, SentimentResult)
    assert pos.sentiment_label in ("Positive", "Very Positive")
    assert pos.score > 0
    assert pos.success is True

    neg = analyzer.analyze_single_text("Stock crash and plunge after fraud warning and bankruptcy risk")
    assert neg.sentiment_label in ("Negative", "Very Negative")
    assert neg.score < 0

    negated = analyzer.analyze_single_text("Shares did not surge despite earlier chatter")
    assert negated.score < pos.score

    batch = analyzer.analyze_batch([
        "Revenue growth remains strong",
        "Earnings miss triggers selloff",
        "",
    ])
    assert isinstance(batch, BatchSentimentResult)
    assert batch.total_processed == 3
    assert batch.success_count == 3
    assert batch.results[2].sentiment_label == "Neutral"


def test_query_result_post_init_and_keyword_symbol_extraction():
    from InsightEngine.tools.search import QueryResult, TrendPulseDB, extract_symbol_from_keyword

    qr = QueryResult(
        ticker="AAPL",
        asset_class="Equity",
        title_or_content="Apple launches next-gen chip",
        source="Yahoo Finance",
        publish_time=datetime(2025, 1, 10),
        engagement={"likes": 15, "comments": 5},
    )
    assert qr.platform == "Yahoo Finance"
    assert qr.hotness_score == 20.0

    assert extract_symbol_from_keyword("NVDA Q4 revenue") == "NVDA"
    assert extract_symbol_from_keyword("bitcoin price rally") == "BTC-USD"

    mock_news = [
        {"title": "NVIDIA AI momentum continues", "summary": "Strong data center growth", "link": "https://example.com"}
    ]
    with patch("InsightEngine.tools.search.get_cached_ticker_news", return_value=mock_news):
        db = TrendPulseDB()
        resp = db.search_topic_globally(topic="NVDA", limit_per_table=5)
        assert resp.results_count == 1
        assert resp.results[0].url == "https://example.com"


def test_insight_agent_clustering_tfidf_fallback_without_sentence_transformers(monkeypatch):
    import InsightEngine.agent as agent_mod
    from InsightEngine.agent import TrendPulseAgent
    from InsightEngine.tools.search import QueryResult
    from InsightEngine.tools.sentiment_analyzer import FinancialSentimentAnalyzer

    # Verify agent instantiates FinancialSentimentAnalyzer (not class reference)
    with patch.object(TrendPulseAgent, "_initialize_llm", return_value=MagicMock()), patch.object(
        TrendPulseAgent, "_initialize_nodes"
    ), patch("InsightEngine.agent.settings") as mock_settings:
        mock_settings.INSIGHT_ENGINE_API_KEY = "dummy"
        mock_settings.INSIGHT_ENGINE_MODEL_NAME = "gpt-4o"
        mock_settings.OUTPUT_DIR = "/tmp"
        agent = TrendPulseAgent()
        assert isinstance(agent.sentiment_analyzer, FinancialSentimentAnalyzer)

        monkeypatch.setattr(agent_mod, "SentenceTransformer", None)
        results = [
            QueryResult(ticker="NVDA", asset_class="Equity", title_or_content="Semiconductor demand spikes in Q1", source="news", engagement={"likes": 10}),
            QueryResult(ticker="NVDA", asset_class="Equity", title_or_content="AI GPU supply tightens across cloud providers", source="news", engagement={"likes": 20}),
            QueryResult(ticker="SPY", asset_class="ETF", title_or_content="Federal Reserve signals cautious rate policy", source="news", engagement={"likes": 15}),
            QueryResult(ticker="TLT", asset_class="ETF", title_or_content="Treasury yields rise following CPI report", source="news", engagement={"likes": 8}),
        ]
        clustered = agent._cluster_and_sample_results(results, max_results=3, results_per_cluster=1)
        assert agent._get_clustering_model() == "tfidf"
        assert 1 <= len(clustered) <= 3


def test_token_tracker_and_webhook_alerter():
    from utils.token_tracker import TokenTracker
    from utils.webhook_alerter import WebhookAlerter

    fake_pipe = MagicMock()
    fake_pipe.execute.return_value = [
        {"total_prompt_tokens": "100", "total_completion_tokens": "50", "total_estimated_cost": "0.00075"},
        ['{"agent_name": "insight", "model_name": "gpt-4o", "total_tokens": 150}'],
    ]
    fake_redis = MagicMock()
    fake_redis.pipeline.return_value = fake_pipe

    with patch("utils.token_tracker.redis.Redis", return_value=fake_redis):
        tt = TokenTracker()
        tt.log_usage("insight", "gpt-4o", 100, 50)
        stats = tt.get_stats()
        assert stats["aggregate"]["total_prompt_tokens"] == 100
        assert stats["aggregate"]["total_completion_tokens"] == 50
        assert len(stats["recent_usage"]) == 1

    mock_resp = MagicMock(status_code=200)
    with patch("utils.webhook_alerter.settings") as mock_settings, patch(
        "utils.webhook_alerter.requests.post", return_value=mock_resp
    ) as mock_post:
        mock_settings.WEBHOOK_ENDPOINTS = '["https://hooks.example.test/abc"]'
        alerter = WebhookAlerter()
        assert alerter.trigger_alert("Signal", "NVDA breakout", level="info", data={"price": 120}) is True
        mock_post.assert_called_once()

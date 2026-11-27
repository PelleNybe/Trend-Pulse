"""Deep sentiment crawling and aggregation module for MindSpider."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List
from loguru import logger

from InsightEngine.tools.sentiment_analyzer import FinancialSentimentAnalyzer


class DeepSentimentCrawler:
    """Runs financial sentiment analysis across collected market topics and news items."""

    def __init__(self) -> None:
        self.analyzer = FinancialSentimentAnalyzer()
        self.analyzer.initialize()

    def analyze_topics_sentiment(
        self,
        topics: List[Dict[str, Any]],
        news_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Score sentiment for each extracted topic across its matched articles."""
        news_by_id = {item["news_id"]: item for item in news_items if "news_id" in item}
        task_results: List[Dict[str, Any]] = []

        for topic in topics:
            started = int(time.time())
            matched_ids = topic.get("news_ids") or []
            texts = [
                f"{news_by_id[nid]['title']} {news_by_id[nid].get('description', '')}".strip()
                for nid in matched_ids
                if nid in news_by_id
            ]
            if not texts:
                texts = [topic.get("topic_name", "")]

            batch = self.analyzer.analyze_batch(texts)
            avg_score = (
                round(sum(r.score for r in batch.results) / len(batch.results), 4)
                if batch.results
                else 0.0
            )
            task_id = hashlib.sha256(
                f"sentiment:{topic['topic_id']}:{started}".encode("utf-8")
            ).hexdigest()[:24]
            finished = int(time.time())
            task_results.append(
                {
                    "task_id": task_id,
                    "topic_id": topic["topic_id"],
                    "platform": "financial_feeds",
                    "search_keywords": topic.get("keywords", topic.get("topic_name", "")),
                    "task_status": "completed",
                    "start_time": started,
                    "end_time": finished,
                    "total_crawled": len(texts),
                    "success_count": batch.success_count,
                    "error_count": batch.failed_count,
                    "average_sentiment_score": avg_score,
                    "average_confidence": batch.average_confidence,
                }
            )
            logger.info(
                f"Topic '{topic['topic_name']}' sentiment complete: "
                f"score={avg_score}, items={batch.success_count}/{len(texts)}"
            )

        return task_results


__all__ = ["DeepSentimentCrawler"]

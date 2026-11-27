"""Broad topic and market feed extraction for MindSpider."""

from __future__ import annotations

import hashlib
import time
from datetime import date
from typing import Any, Dict, List
import feedparser
import yfinance as yf
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer


DEFAULT_FINANCIAL_RSS_FEEDS = [
    ("yahoo_finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,NVDA,AAPL,MSFT&region=US&lang=en-US"),
    ("cnbc_markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"),
]


class BroadTopicExtractor:
    """Extracts daily financial news items and hot keywords from yfinance and RSS feeds."""

    def __init__(self, feeds: List[tuple[str, str]] | None = None):
        self.feeds = feeds or DEFAULT_FINANCIAL_RSS_FEEDS

    def collect_news(self, ticker: str = "SPY", max_items: int = 25) -> List[Dict[str, Any]]:
        """Collect recent news items from yfinance ticker news and financial RSS feeds."""
        items: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        try:
            yf_news = yf.Ticker(ticker).news or []
            for rank, entry in enumerate(yf_news[:max_items], start=1):
                content = entry.get("content") if isinstance(entry.get("content"), dict) else entry
                title = (content.get("title") or entry.get("title") or "").strip()
                link = (
                    (content.get("canonicalUrl") or {}).get("url")
                    or entry.get("link")
                    or ""
                )
                summary = (content.get("summary") or entry.get("summary") or "").strip()
                if not title:
                    continue
                news_id = hashlib.sha256(f"yfinance:{title}:{link}".encode("utf-8")).hexdigest()[:32]
                if news_id in seen_ids:
                    continue
                seen_ids.add(news_id)
                items.append(
                    {
                        "news_id": news_id,
                        "source_platform": f"yfinance:{ticker}",
                        "title": title[:500],
                        "url": link[:512] if link else None,
                        "description": summary,
                        "extra_info": f"ticker={ticker}",
                        "rank_position": rank,
                    }
                )
        except Exception as exc:
            logger.warning(f"yfinance news fetch failed for {ticker}: {exc}")

        for source_name, feed_url in self.feeds:
            try:
                parsed = feedparser.parse(feed_url)
                for rank, entry in enumerate(getattr(parsed, "entries", [])[:max_items], start=1):
                    title = str(entry.get("title", "") or "").strip()
                    link = str(entry.get("link", "") or "").strip()
                    summary = str(entry.get("summary", "") or "").strip()
                    if not title:
                        continue
                    news_id = hashlib.sha256(f"{source_name}:{title}:{link}".encode("utf-8")).hexdigest()[:32]
                    if news_id in seen_ids:
                        continue
                    seen_ids.add(news_id)
                    items.append(
                        {
                            "news_id": news_id,
                            "source_platform": source_name,
                            "title": title[:500],
                            "url": link[:512] if link else None,
                            "description": summary,
                            "extra_info": f"ticker={ticker}",
                            "rank_position": rank,
                        }
                    )
            except Exception as exc:
                logger.warning(f"RSS feed fetch failed for {source_name}: {exc}")

        return items[:max_items]

    def extract_topics(
        self, news_items: List[Dict[str, Any]], max_topics: int = 5
    ) -> List[Dict[str, Any]]:
        """Extract salient topics from collected news headlines via TF-IDF weighting."""
        if not news_items:
            return []

        corpus = [
            f"{item['title']}. {item.get('description', '')}".strip()
            for item in news_items
        ]
        try:
            vectorizer = TfidfVectorizer(
                stop_words="english", max_features=30, ngram_range=(1, 2)
            )
            matrix = vectorizer.fit_transform(corpus)
            terms = vectorizer.get_feature_names_out()
            scores = matrix.sum(axis=0).A1
            ranked_terms = sorted(
                zip(terms, scores), key=lambda x: float(x[1]), reverse=True
            )
        except ValueError:
            ranked_terms = [("market_overview", 1.0)]

        topics: List[Dict[str, Any]] = []
        now_date = date.today().isoformat()
        for idx, (term, score) in enumerate(ranked_terms[:max_topics], start=1):
            matching_news = [
                item["news_id"]
                for item in news_items
                if term.lower() in (item["title"] + " " + (item.get("description") or "")).lower()
            ]
            if not matching_news:
                matching_news = [item["news_id"] for item in news_items[:3]]
            topic_id = hashlib.sha256(f"{now_date}:{term}".encode("utf-8")).hexdigest()[:24]
            topics.append(
                {
                    "topic_id": topic_id,
                    "topic_name": term,
                    "topic_description": f"Automated market topic '{term}' extracted on {now_date}",
                    "keywords": term,
                    "relevance_score": round(float(score), 4),
                    "news_ids": matching_news,
                    "news_count": len(matching_news),
                    "timestamp": int(time.time()),
                }
            )
        return topics


__all__ = ["BroadTopicExtractor", "DEFAULT_FINANCIAL_RSS_FEEDS"]

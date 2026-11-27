"""
Financial Sentiment Analysis Module.

Provides multi-signal domain-weighted financial sentiment scoring (lexicon + negation +
intensity modifiers + optional HuggingFace transformers pipeline) with structured
SentimentResult and BatchSentimentResult outputs.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from loguru import logger

SENTIMENT_MAP = {
    "Very Negative": 0,
    "Negative": 1,
    "Neutral": 2,
    "Positive": 3,
    "Very Positive": 4,
}

# Domain-weighted financial lexicon (-2.0 .. +2.0 scale)
_FINANCIAL_LEXICON: Dict[str, float] = {
    # Strongly positive
    "surge": 1.6, "surged": 1.6, "surging": 1.6, "soar": 1.7, "soared": 1.7,
    "rally": 1.4, "rallied": 1.4, "breakout": 1.5, "outperform": 1.5,
    "upgrade": 1.4, "upgraded": 1.4, "beat": 1.3, "beats": 1.3,
    "bullish": 1.5, "record": 1.1, "boom": 1.5, "skyrocket": 1.8,
    "exceptional": 1.4, "blowout": 1.6, "strongest": 1.5,
    # Moderately positive
    "bull": 1.0, "gain": 0.9, "gained": 0.9, "gains": 0.9, "growth": 1.0,
    "profit": 1.0, "profitable": 1.1, "profits": 1.0, "dividend": 0.8,
    "buy": 0.8, "accumulate": 0.9, "overweight": 0.9, "upside": 1.1,
    "positive": 0.9, "optimistic": 1.0, "strong": 0.9, "resilient": 1.0,
    "recovery": 1.0, "rebound": 1.0, "rebounded": 1.0, "innovation": 0.7,
    "expansion": 0.9, "momentum": 0.7, "rose": 0.8, "rising": 0.8,
    "climbed": 0.8, "higher": 0.6, "exceed": 1.0, "exceeded": 1.0,
    "confidence": 0.8, "tailwind": 1.0, "support": 0.5,
    # Moderately negative
    "bear": -1.0, "bearish": -1.5, "loss": -1.1, "losses": -1.2,
    "decline": -1.0, "declined": -1.0, "drop": -1.0, "dropped": -1.0,
    "fall": -0.9, "fell": -0.9, "falling": -0.9, "sell": -0.9,
    "selloff": -1.4, "underperform": -1.4, "downgrade": -1.4, "downgraded": -1.4,
    "miss": -1.2, "missed": -1.2, "misses": -1.2, "weak": -1.0,
    "weaker": -1.1, "weakness": -1.0, "concern": -0.8, "concerns": -0.8,
    "risk": -0.7, "risks": -0.7, "volatile": -0.7, "volatility": -0.6,
    "headwind": -1.0, "headwinds": -1.0, "pressure": -0.7, "cut": -0.9,
    "cuts": -0.9, "slump": -1.3, "negative": -1.0, "warning": -1.2,
    "debt": -0.6, "deficit": -0.9, "slowdown": -1.1, "recession": -1.6,
    "inflation": -0.6, "uncertainty": -0.8, "lawsuit": -1.1, "probe": -1.0,
    # Strongly negative
    "crash": -1.8, "crashed": -1.8, "plunge": -1.7, "plunged": -1.7,
    "collapse": -1.8, "collapsed": -1.8, "bankrupt": -2.0, "bankruptcy": -2.0,
    "default": -1.8, "defaulted": -1.8, "fraud": -2.0, "insolvency": -2.0,
    "crisis": -1.6, "panic": -1.6, "liquidation": -1.5, "tumble": -1.4,
    "tumbled": -1.4, "plummet": -1.7, "plummeted": -1.7, "worst": -1.5,
}

_NEGATIONS = {"not", "no", "never", "neither", "nor", "without", "hardly", "barely", "n't", "dont", "doesn't", "didn't", "isn't", "wasn't", "won't"}
_INTENSIFIERS = {"very": 1.35, "strongly": 1.4, "sharply": 1.4, "significantly": 1.35, "highly": 1.3, "extremely": 1.5, "substantially": 1.35, "slightly": 0.6, "modestly": 0.7, "marginally": 0.5}
_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


@dataclass
class SentimentResult:
    """Structured result for single-text sentiment analysis."""
    text: str
    sentiment_label: str
    confidence: float
    probability_distribution: Dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    success: bool = True
    analysis_performed: bool = True
    error_message: Optional[str] = None


@dataclass
class BatchSentimentResult:
    """Structured result for batch sentiment analysis."""
    results: List[SentimentResult] = field(default_factory=list)
    total_processed: int = 0
    success_count: int = 0
    failed_count: int = 0
    average_confidence: float = 0.0
    analysis_performed: bool = True
    error_message: Optional[str] = None


class FinancialSentimentAnalyzer:
    """Financial sentiment analyzer with optional transformer backend and calibrated lexicon scoring."""

    def __init__(self, model_type: str = "financial_lexicon"):
        self.model_type = model_type
        self.is_initialized = False
        self.is_disabled = False
        self.disable_reason: Optional[str] = None
        self._hf_pipeline = None
        logger.info(f"FinancialSentimentAnalyzer initialized with model_type={model_type}")

    def initialize(self) -> bool:
        """Initialize the analyzer (optionally loading HuggingFace FinBERT if explicitly requested)."""
        if self.is_disabled:
            return False
        if self.model_type == "transformers" or os.getenv("ENABLE_FINBERT", "").lower() in ("1", "true", "yes"):
            try:
                from transformers import pipeline  # type: ignore
                self._hf_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
                self.model_type = "finbert"
                logger.info("Loaded HuggingFace ProsusAI/finbert pipeline")
            except Exception as exc:
                logger.warning(f"FinBERT transformer pipeline unavailable ({exc}); using calibrated financial lexicon scorer")
                self._hf_pipeline = None
        self.is_initialized = True
        return True

    def disable(self, reason: str = "Disabled by caller") -> None:
        self.is_disabled = True
        self.disable_reason = reason

    def enable(self) -> None:
        self.is_disabled = False
        self.disable_reason = None

    def _score_to_distribution(self, raw_score: float, matched_tokens: int) -> tuple[str, float, Dict[str, float]]:
        # Map raw score via tanh to [-1, 1]
        norm = math.tanh(raw_score / 2.2)

        centers = {
            "Very Negative": -0.85,
            "Negative": -0.40,
            "Neutral": 0.0,
            "Positive": 0.40,
            "Very Positive": 0.85,
        }
        sigma = 0.35 if matched_tokens > 0 else 0.22
        raw_weights = {
            label: math.exp(-((norm - center) ** 2) / (2 * sigma * sigma))
            for label, center in centers.items()
        }
        total = sum(raw_weights.values()) or 1.0
        dist = {label: round(val / total, 4) for label, val in raw_weights.items()}

        if norm >= 0.60:
            label = "Very Positive"
        elif norm >= 0.15:
            label = "Positive"
        elif norm <= -0.60:
            label = "Very Negative"
        elif norm <= -0.15:
            label = "Negative"
        else:
            label = "Neutral"

        confidence = round(max(dist.values()), 4)
        return label, confidence, dist

    def _analyze_with_lexicon(self, text: str) -> SentimentResult:
        tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
        score = 0.0
        matched = 0

        for idx, tok in enumerate(tokens):
            weight = _FINANCIAL_LEXICON.get(tok)
            if weight is None:
                continue
            matched += 1
            # Check negation in 3-token lookback window
            window_start = max(0, idx - 3)
            preceding = tokens[window_start:idx]
            negated = any(p in _NEGATIONS for p in preceding)
            mult = 1.0
            if idx > 0 and tokens[idx - 1] in _INTENSIFIERS:
                mult = _INTENSIFIERS[tokens[idx - 1]]
            term_score = weight * mult
            if negated:
                term_score = -0.75 * term_score
            score += term_score

        label, confidence, dist = self._score_to_distribution(score, matched)
        return SentimentResult(
            text=text,
            sentiment_label=label,
            confidence=confidence,
            probability_distribution=dist,
            score=round(math.tanh(score / 2.2), 4),
            success=True,
            analysis_performed=True,
        )

    def analyze_single_text(self, text: str) -> SentimentResult:
        """Analyze sentiment of a single text string."""
        if self.is_disabled:
            return SentimentResult(
                text=text or "",
                sentiment_label="Neutral",
                confidence=0.0,
                success=False,
                analysis_performed=False,
                error_message=self.disable_reason or "Sentiment analysis disabled",
            )
        if not self.is_initialized:
            self.initialize()

        if not text or not isinstance(text, str) or not text.strip():
            return SentimentResult(
                text=str(text or ""),
                sentiment_label="Neutral",
                confidence=0.65,
                probability_distribution={
                    "Very Negative": 0.05,
                    "Negative": 0.1,
                    "Neutral": 0.7,
                    "Positive": 0.1,
                    "Very Positive": 0.05,
                },
                score=0.0,
                success=True,
                analysis_performed=True,
            )

        if self._hf_pipeline is not None:
            try:
                out = self._hf_pipeline(text[:512])[0]
                hf_label = str(out.get("label", "neutral")).lower()
                hf_score = float(out.get("score", 0.5))
                mapped = {
                    "positive": "Very Positive" if hf_score > 0.85 else "Positive",
                    "negative": "Very Negative" if hf_score > 0.85 else "Negative",
                    "neutral": "Neutral",
                }.get(hf_label, "Neutral")
                return SentimentResult(
                    text=text,
                    sentiment_label=mapped,
                    confidence=round(hf_score, 4),
                    probability_distribution={mapped: round(hf_score, 4)},
                    score=round(hf_score if "Positive" in mapped else (-hf_score if "Negative" in mapped else 0.0), 4),
                    success=True,
                    analysis_performed=True,
                )
            except Exception as exc:
                logger.warning(f"FinBERT inference failed, falling back to lexicon scorer: {exc}")

        return self._analyze_with_lexicon(text)

    def analyze_batch(self, texts: List[str], show_progress: bool = False) -> BatchSentimentResult:
        """Analyze sentiment for a list of texts."""
        if self.is_disabled:
            return BatchSentimentResult(
                results=[],
                total_processed=0,
                success_count=0,
                failed_count=len(texts),
                average_confidence=0.0,
                analysis_performed=False,
                error_message=self.disable_reason or "Sentiment analysis disabled",
            )
        if not self.is_initialized:
            self.initialize()

        results: List[SentimentResult] = []
        success_count = 0
        failed_count = 0
        total_conf = 0.0

        for item in texts:
            try:
                res = self.analyze_single_text(str(item) if item is not None else "")
                results.append(res)
                if res.success:
                    success_count += 1
                    total_conf += res.confidence
                else:
                    failed_count += 1
            except Exception as exc:
                failed_count += 1
                results.append(
                    SentimentResult(
                        text=str(item),
                        sentiment_label="Neutral",
                        confidence=0.0,
                        success=False,
                        analysis_performed=False,
                        error_message=str(exc),
                    )
                )

        avg_conf = round(total_conf / success_count, 4) if success_count else 0.0
        return BatchSentimentResult(
            results=results,
            total_processed=len(texts),
            success_count=success_count,
            failed_count=failed_count,
            average_confidence=avg_conf,
            analysis_performed=True,
        )

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Legacy dictionary-returning single text analysis helper."""
        res = self.analyze_single_text(text)
        return {
            "sentiment": res.sentiment_label,
            "confidence": res.confidence,
            "score": res.score,
            "probability_distribution": res.probability_distribution,
        }

    def analyze_query_results(
        self,
        query_results: List[Any],
        text_field: str = "content",
        min_confidence: float = 0.5,
    ) -> Dict[str, Any]:
        """Analyze sentiment across a list of QueryResult objects or dicts."""
        if not query_results:
            return {
                "sentiment_analysis": {
                    "sentiment_distribution": {},
                    "total_analyzed": 0,
                    "overall_sentiment": "Neutral",
                    "average_confidence": 0.0,
                    "high_confidence_results": [],
                }
            }

        texts: List[str] = []
        for item in query_results:
            if isinstance(item, dict):
                txt = item.get(text_field) or item.get("title_or_content") or item.get("title") or ""
            else:
                txt = getattr(item, text_field, None) or getattr(item, "title_or_content", "") or ""
            texts.append(str(txt))

        batch = self.analyze_batch(texts)
        distribution: Dict[str, int] = {
            "Very Negative": 0,
            "Negative": 0,
            "Neutral": 0,
            "Positive": 0,
            "Very Positive": 0,
        }
        high_conf_results = []
        for item, res in zip(query_results, batch.results):
            distribution[res.sentiment_label] = distribution.get(res.sentiment_label, 0) + 1
            if res.confidence >= min_confidence:
                high_conf_results.append(
                    {
                        "text": res.text[:200],
                        "sentiment": res.sentiment_label,
                        "confidence": res.confidence,
                        "score": res.score,
                        "source": item.get("platform") if isinstance(item, dict) else getattr(item, "platform", ""),
                    }
                )

        pos = distribution["Positive"] + distribution["Very Positive"]
        neg = distribution["Negative"] + distribution["Very Negative"]
        if pos > neg and pos >= distribution["Neutral"]:
            overall = "Positive"
        elif neg > pos and neg >= distribution["Neutral"]:
            overall = "Negative"
        else:
            overall = "Neutral"

        return {
            "sentiment_analysis": {
                "sentiment_distribution": distribution,
                "total_analyzed": batch.total_processed,
                "success_count": batch.success_count,
                "overall_sentiment": overall,
                "average_confidence": batch.average_confidence,
                "high_confidence_results": high_conf_results,
            }
        }


WeiboMultilingualSentimentAnalyzer = FinancialSentimentAnalyzer
multilingual_sentiment_analyzer = FinancialSentimentAnalyzer()

import json
from loguru import logger
from typing import Dict, List, Any
import yfinance as yf
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_ticker_info(symbol: str) -> dict:
    """
    ⚡ OPTIMIZATION: Cache expensive yfinance info calls.
    Reduces redundant network requests across different tools for the same ticker,
    improving performance significantly when multiple tools query the same asset.
    """
    try:
        return yf.Ticker(symbol).info
    except Exception as e:
        logger.warning(f"Failed to fetch info for {symbol}: {e}")
        return {}

from .search import extract_symbol_from_keyword

class CustomBusinessDBTool:
    """
    Integration for a custom business database and sentiment analysis aggregation.
    Fetches real-time fundamental business data via yfinance.
    """
    def search_business_data(self, query: str, table: str) -> Dict[str, Any]:
        """
        Searches fundamental data for a given query (ticker/company).
        """
        logger.info(f"CustomBusinessDBTool: Searching '{table}' for query: '{query}'")

        try:
            symbol = extract_symbol_from_keyword(query)
            info = get_cached_ticker_info(symbol)

            data = []

            market_cap = info.get('marketCap')
            market_cap_str = f"${market_cap:,}" if isinstance(market_cap, (int, float)) else "N/A"

            pe = info.get('trailingPE')
            pe_str = f"{pe}" if pe is not None else "N/A"

            fpe = info.get('forwardPE')
            fpe_str = f"{fpe}" if fpe is not None else "N/A"

            revenue = info.get('totalRevenue')
            revenue_str = f"${revenue:,}" if isinstance(revenue, (int, float)) else "N/A"

            if table.lower() in ['financials', 'fundamentals', 'default']:
                data.append({
                    "id": 1,
                    "topic": f"{symbol} Market Cap",
                    "content": f"Market Capitalization is {market_cap_str}",
                    "score": 0.5
                })
                data.append({
                    "id": 2,
                    "topic": f"{symbol} P/E Ratio",
                    "content": f"Trailing P/E: {pe_str}, Forward P/E: {fpe_str}",
                    "score": 0.5
                })
                data.append({
                    "id": 3,
                    "topic": f"{symbol} Revenue",
                    "content": f"Total Revenue is {revenue_str}",
                    "score": 0.5
                })

            return {
                "source": "CustomBusinessDB_YFinance",
                "table": table,
                "query": query,
                "data": data
            }
        except Exception as e:
            logger.error(f"Error fetching custom business data: {e}")
            return {
                "source": "CustomBusinessDB",
                "table": table,
                "query": query,
                "data": [],
                "error": str(e)
            }

    def aggregate_sentiment(self, data_sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Combines sentiment scores from multiple sources into an aggregate market sentiment indicator.
        """
        logger.info("CustomBusinessDBTool: Aggregating sentiment from multiple sources...")

        if not data_sources:
            return {"aggregate_score": 0.0, "interpretation": "Neutral (No Data)"}

        total_score = 0.0
        weight_sum = 0.0

        for source in data_sources:
            score = source.get("score", 0.0)
            weight = source.get("weight", 1.0)
            total_score += score * weight
            weight_sum += weight

        avg_score = total_score / weight_sum if weight_sum > 0 else 0.0

        interpretation = "Neutral"
        if avg_score > 0.6:
            interpretation = "Bullish"
        elif avg_score < 0.4:
            interpretation = "Bearish"

        return {
            "aggregate_score": round(avg_score, 2),
            "interpretation": interpretation,
            "components": len(data_sources)
        }

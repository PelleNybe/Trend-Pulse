import logging
from .technical_indicators import TechnicalIndicators
from .portfolio_optimizer import PortfolioOptimizer

logger = logging.getLogger(__name__)

class TradingSignalGenerator:
    """
    Actionable Trading Signal Generator.
    Aggregates Technical Analysis (RSI, MACD) to generate a definitive BUY/SELL/HOLD signal.
    """

    @classmethod
    def generate_signal(cls, ticker: str) -> dict:
        """
        Generate a comprehensive trading signal based on TA.
        """
        ta_summary = TechnicalIndicators.get_summary(ticker)

        if ta_summary.get('error'):
            return {"ticker": ticker, "signal": "UNKNOWN", "reason": ta_summary['error']}

        rsi = ta_summary.get('rsi')
        macd = ta_summary.get('macd')
        signal_line = ta_summary.get('macd_signal')

        # Simple Logic formulation:
        # RSI < 30 -> Oversold (Bullish)
        # RSI > 70 -> Overbought (Bearish)
        # MACD > Signal -> Bullish Momentum
        # MACD < Signal -> Bearish Momentum

        score = 0
        reasons = []

        if rsi is not None:
            if rsi < 30:
                score += 2
                reasons.append(f"RSI is oversold ({rsi:.2f})")
            elif rsi > 70:
                score -= 2
                reasons.append(f"RSI is overbought ({rsi:.2f})")
            else:
                reasons.append(f"RSI is neutral ({rsi:.2f})")

        if macd is not None and signal_line is not None:
            if macd > signal_line:
                score += 1
                reasons.append("MACD is above Signal line (Bullish momentum)")
            elif macd < signal_line:
                score -= 1
                reasons.append("MACD is below Signal line (Bearish momentum)")

        # Determine final signal
        if score >= 2:
            signal = "STRONG BUY"
        elif score == 1:
            signal = "BUY"
        elif score <= -2:
            signal = "STRONG SELL"
        elif score == -1:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "ticker": ticker,
            "signal": signal,
            "confidence_score": score,
            "reasons": reasons,
            "raw_data": ta_summary
        }

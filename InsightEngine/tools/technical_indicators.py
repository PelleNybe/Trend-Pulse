import yfinance as yf
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """
    Advanced Technical Analysis Engine for TrendPulse.
    Calculates RSI, MACD, and Bollinger Bands for a given ticker.
    """

    @staticmethod
    def fetch_data(ticker: str, period: str = '1y') -> pd.DataFrame:
        try:
            data = yf.download(ticker, period=period, progress=False)
            if data.empty:
                logger.warning(f"No data found for {ticker}")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, window: int = 14) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if data.empty or 'Close' not in data:
            return pd.Series()

        close = data['Close'].squeeze() # Handle both Series and 1-col DataFrame
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        """Calculate MACD and Signal Line."""
        if data.empty or 'Close' not in data:
            return {}

        close = data['Close'].squeeze()
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line

        return {
            'macd': macd,
            'signal': signal_line,
            'histogram': histogram
        }

    @staticmethod
    def calculate_bollinger_bands(data: pd.DataFrame, window: int = 20, num_std_dev: int = 2) -> dict:
        """Calculate Bollinger Bands."""
        if data.empty or 'Close' not in data:
            return {}

        close = data['Close'].squeeze()
        sma = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()

        upper_band = sma + (std * num_std_dev)
        lower_band = sma - (std * num_std_dev)

        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        }

    @classmethod
    def get_summary(cls, ticker: str) -> dict:
        """Get a summary of the latest technical indicators."""
        data = cls.fetch_data(ticker, period='3mo')
        if data.empty:
            return {"error": f"Could not calculate indicators for {ticker}"}

        rsi = cls.calculate_rsi(data)
        macd_data = cls.calculate_macd(data)
        bb_data = cls.calculate_bollinger_bands(data)

        try:
            # Safely extract scalar values, using .values[-1] to get the last valid element, and handling possible NaNs
            rsi_clean = rsi.dropna()
            latest_rsi = float(rsi_clean.values[-1]) if not rsi_clean.empty else None

            macd_series = macd_data.get('macd', pd.Series())
            signal_series = macd_data.get('signal', pd.Series())

            macd_clean = macd_series.dropna()
            latest_macd = float(macd_clean.values[-1]) if not macd_clean.empty else None
            signal_clean = signal_series.dropna()
            latest_signal = float(signal_clean.values[-1]) if not signal_clean.empty else None

            # Use Python native types for JSON serialization
            return {
                "ticker": ticker,
                "rsi": float(latest_rsi) if latest_rsi is not None else None,
                "macd": float(latest_macd) if latest_macd is not None else None,
                "macd_signal": float(latest_signal) if latest_signal is not None else None,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error extracting summary for {ticker}: {e}")
            return {"error": str(e)}

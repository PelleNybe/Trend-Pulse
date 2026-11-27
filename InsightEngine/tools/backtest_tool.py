import pandas as pd
import numpy as np
from typing import Dict, Any, List
from loguru import logger

class PortfolioBacktester:
    """
    Simulates trading strategies over historical data to evaluate performance metrics.
    """

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital

    def run_backtest(self, prices: pd.Series, signals: pd.Series) -> Dict[str, Any]:
        """
        Runs a backtest given price data and trading signals.
        signals: 1 (buy), -1 (sell), 0 (hold)
        """
        logger.info("PortfolioBacktester: Running backtest simulation...")

        if len(prices) != len(signals):
            return {"error": "Prices and signals must have the same length."}

        # Create a DataFrame for easier vectorized calculation
        df = pd.DataFrame({'price': prices, 'signal': signals})

        # Calculate daily returns of the asset
        df['return'] = df['price'].pct_change()

        # Strategy position (1 for long, 0 for neutral, -1 for short)
        # Assuming the signal translates directly to position size (1 unit)
        # Shift the position by 1 day to simulate buying at the close of signal day
        # and getting the return of the next day.
        df['position'] = df['signal'].shift(1).fillna(0)

        # Strategy return is the asset return multiplied by the position held
        df['strategy_return'] = df['position'] * df['return']

        # Calculate cumulative returns
        df['cumulative_return'] = (1 + df['strategy_return']).cumprod()
        df['asset_cumulative_return'] = (1 + df['return']).cumprod()

        # Calculate key metrics
        # ⚡ OPTIMIZATION: Replacing df['cumulative_return'].values[-1] with df['cumulative_return'].values[-1] for faster vectorized access
        total_return = (df['cumulative_return'].values[-1] - 1) if not df.empty and not pd.isna(df['cumulative_return'].values[-1]) else 0
        # ⚡ OPTIMIZATION: Replacing df['asset_cumulative_return'].values[-1] with df['asset_cumulative_return'].values[-1] for faster vectorized access
        asset_total_return = (df['asset_cumulative_return'].values[-1] - 1) if not df.empty and not pd.isna(df['asset_cumulative_return'].values[-1]) else 0

        # Annualized return (assuming 252 trading days)
        trading_days = len(df)
        annualized_return = ((1 + total_return) ** (252 / trading_days)) - 1 if trading_days > 0 else 0

        # Volatility (annualized)
        volatility = df['strategy_return'].std() * np.sqrt(252) if not df.empty else 0

        # Sharpe Ratio (assuming 0% risk-free rate for simplicity)
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0

        # Maximum Drawdown
        df['rolling_max'] = df['cumulative_return'].cummax()
        df['drawdown'] = df['cumulative_return'] / df['rolling_max'] - 1
        max_drawdown = df['drawdown'].min() if not df.empty else 0

        return {
            "initial_capital": self.initial_capital,
            "final_value": self.initial_capital * (1 + total_return),
            "total_return": float(total_return),
            "annualized_return": float(annualized_return),
            "benchmark_return": float(asset_total_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "volatility": float(volatility)
        }

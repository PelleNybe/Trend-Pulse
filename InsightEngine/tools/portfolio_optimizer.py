import yfinance as yf
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    """
    Modern Portfolio Theory (MPT) Optimizer for TrendPulse.
    Calculates the optimal weights for a basket of assets to maximize the Sharpe Ratio.
    """

    @staticmethod
    def fetch_data(tickers: list, period: str = '1y') -> pd.DataFrame:
        try:
            data = yf.download(tickers, period=period, progress=False)['Close']
            if data.empty:
                logger.warning("No data found for portfolio optimization.")
                return pd.DataFrame()
            return data
        except Exception as e:
            logger.error(f"Error fetching data for portfolio optimization: {e}")
            return pd.DataFrame()

    @classmethod
    def optimize(cls, tickers: list, risk_free_rate: float = 0.02) -> dict:
        """
        Calculates optimal portfolio weights using Markowitz Modern Portfolio Theory (Max Sharpe Ratio).
        Uses a Monte Carlo approach to find the optimal allocation.
        """
        if not tickers or len(tickers) < 2:
            return {"error": "At least 2 tickers are required for optimization."}

        data = cls.fetch_data(tickers)
        if data.empty:
            return {"error": "Failed to retrieve historical data."}

        # Calculate daily returns
        returns = data.pct_change().dropna()

        # Calculate expected annualized returns and covariance matrix
        # Assume 252 trading days in a year
        mean_returns = returns.mean() * 252
        cov_matrix = returns.cov() * 252

        num_portfolios = 10000
        num_assets = len(tickers)

        # Arrays to store results
        results = np.zeros((3, num_portfolios))
        weights_record = []

        # Seed for reproducibility in tests
        np.random.seed(42)

        # Vectorized portfolio optimization
        weights_record = np.random.random((num_portfolios, num_assets))
        weights_record /= np.sum(weights_record, axis=1)[:, np.newaxis]

        # Expected portfolio return for all portfolios
        portfolio_returns = np.dot(weights_record, mean_returns.values)

        # Expected portfolio volatility (standard deviation) for all portfolios
        # We can calculate this as diagonal of (W * Cov * W^T)
        portfolio_std_devs = np.sqrt(np.einsum('ij,ji->i', weights_record, np.dot(cov_matrix.values, weights_record.T)))

        # Sharpe Ratios for all portfolios
        sharpe_ratios = (portfolio_returns - risk_free_rate) / portfolio_std_devs

        results[0, :] = portfolio_returns
        results[1, :] = portfolio_std_devs
        results[2, :] = sharpe_ratios

        # Find the portfolio with the maximum Sharpe Ratio
        max_sharpe_idx = np.argmax(results[2])
        optimal_weights = weights_record[max_sharpe_idx]

        # Create a clean dictionary mapping tickers to weights
        # Handle cases where yfinance returns a DataFrame with column multi-index
        if isinstance(returns.columns, pd.MultiIndex):
            ticker_names = [col[1] for col in returns.columns]
        else:
            ticker_names = returns.columns

        allocation = {str(ticker): round(float(weight) * 100, 2) for ticker, weight in zip(ticker_names, optimal_weights)}

        return {
            "status": "success",
            "optimal_allocation_percent": allocation,
            "expected_annual_return": round(float(results[0, max_sharpe_idx]) * 100, 2),
            "expected_volatility": round(float(results[1, max_sharpe_idx]) * 100, 2),
            "sharpe_ratio": round(float(results[2, max_sharpe_idx]), 2)
        }

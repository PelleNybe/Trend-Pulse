import pandas as pd
import numpy as np
from loguru import logger
from typing import Dict, Any, List, Union

class MarketAnomalyDetector:
    """
    Detects unusual market activities or price movements using statistical methods.
    """

    def __init__(self, z_score_threshold: float = 3.0):
        """
        Args:
            z_score_threshold: The number of standard deviations from the mean
                               to flag an anomaly. Default is 3.0.
        """
        self.z_score_threshold = z_score_threshold

    def detect_anomalies(self, series: pd.Series, window: int = 20) -> Dict[str, Any]:
        """
        Detects anomalies in a pandas Series of prices or returns using rolling statistics.
        """
        logger.info(f"MarketAnomalyDetector: Detecting anomalies using Z-score threshold {self.z_score_threshold}...")

        if len(series) < window:
            return {"error": f"Series length ({len(series)}) must be greater than or equal to window size ({window})."}

        # Create a DataFrame
        df = pd.DataFrame({'value': series})

        # Calculate daily returns if it looks like prices (all positive)
        # Otherwise, assume it's already returns.
        if (series > 0).all():
            df['return'] = df['value'].pct_change()
        else:
            df['return'] = df['value']

        # Calculate rolling mean and standard deviation of returns
        df['rolling_mean'] = df['return'].rolling(window=window).mean()
        df['rolling_std'] = df['return'].rolling(window=window).std()

        # Calculate Z-score
        # Suppress division by zero by filling NaN or handling 0 std dev
        df['z_score'] = (df['return'] - df['rolling_mean']) / df['rolling_std'].replace(0, np.nan)

        # Flag anomalies
        df['anomaly'] = np.abs(df['z_score']) > self.z_score_threshold

        # Identify the anomalous dates and values
        anomalies_df = df[df['anomaly']]

        # Format the result
        # ⚡ OPTIMIZATION: Replaced O(N) DataFrame.iterrows() loop with zip iteration.
        # This reduces iteration overhead significantly, making it much faster for large datasets.
        dates = [str(idx) for idx in anomalies_df.index]
        values = anomalies_df['value'].tolist()
        returns = anomalies_df['return'].tolist()
        z_scores = anomalies_df['z_score'].tolist()

        anomalies_list = [
            {
                "date": d,
                "value": float(v),
                "return": float(r) if not pd.isna(r) else None,
                "z_score": float(z) if not pd.isna(z) else None,
                "type": "spike" if z > 0 else "drop"
            }
            for d, v, r, z in zip(dates, values, returns, z_scores)
        ]

        logger.info(f"MarketAnomalyDetector: Found {len(anomalies_list)} anomalies.")

        return {
            "total_data_points": len(series),
            "anomalies_found": len(anomalies_list),
            "anomalies": anomalies_list,
            "threshold_used": self.z_score_threshold,
            "window_size": window
        }

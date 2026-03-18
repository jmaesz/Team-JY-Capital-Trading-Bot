"""
Pure pandas/numpy technical indicators used by the strategy.
All functions accept and return pd.Series unless documented otherwise.
"""

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema    = ema(series, fast)
    slow_ema    = ema(series, slow)
    macd_line   = fast_ema - slow_ema
    signal_line = ema(macd_line, signal_period)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, mid, lower)."""
    mid   = series.rolling(period).mean()
    std   = series.rolling(period).std(ddof=0)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range. df must have 'high', 'low', 'close' columns."""
    high       = df["high"]
    low        = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Current volume divided by rolling-average volume."""
    avg_vol = df["volume"].rolling(period).mean()
    return df["volume"] / avg_vol.replace(0, np.nan)

"""
Market data fetcher using the Binance public REST API (no auth required).
Provides OHLCV candlestick data for technical-indicator computation.
"""

import logging
import time
from typing import Dict, List

import pandas as pd
import requests

from config import BINANCE_BASE, LOOKBACK

logger = logging.getLogger(__name__)

_BINANCE_TIMEOUT = 10


def _binance_symbol(coin: str) -> str:
    """Convert 'BTC' → 'BTCUSDT' (Binance spot pair)."""
    return f"{coin}USDT"


def fetch_klines(coin: str, interval: str, limit: int = LOOKBACK) -> pd.DataFrame:
    """
    Download candlestick data from Binance for one coin.

    Returns a DataFrame with columns:
        open_time, open, high, low, close, volume
    All price/volume columns are float64.
    Returns empty DataFrame on failure.
    """
    symbol = _binance_symbol(coin)
    url    = BINANCE_BASE + "/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    try:
        r = requests.get(url, params=params, timeout=_BINANCE_TIMEOUT)
        r.raise_for_status()
        raw = r.json()
    except Exception as exc:
        logger.warning("Binance klines %s/%s failed: %s", coin, interval, exc)
        return pd.DataFrame()

    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df[["open_time", "open", "high", "low", "close", "volume"]].copy()


def fetch_all_klines(
    coins: List[str],
    interval: str,
    limit: int = LOOKBACK,
    sleep_between: float = 0.1,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch klines for a list of coins.
    Returns {coin: DataFrame}. Missing/failed coins are excluded.
    """
    result = {}
    for coin in coins:
        df = fetch_klines(coin, interval, limit)
        if not df.empty:
            result[coin] = df
        time.sleep(sleep_between)   # be polite to Binance rate limits
    return result

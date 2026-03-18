"""
Logging configuration.

• Console  – INFO level, clean format
• File     – DEBUG level, full format (logs/bot.log)
• Trade    – CSV file (logs/trades.csv) with one row per executed order
"""

import csv
import logging
import os
from datetime import datetime, timezone

from config import LOG_DIR, TRADE_LOG


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt_verbose = "%(asctime)s [%(levelname)-8s] %(name)s – %(message)s"
    fmt_simple  = "%(asctime)s [%(levelname)-8s] %(message)s"
    datefmt     = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(fmt_simple, datefmt=datefmt))
    root.addHandler(ch)

    # File handler
    fh = logging.FileHandler(os.path.join(LOG_DIR, "bot.log"), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt_verbose, datefmt=datefmt))
    root.addHandler(fh)


# ── Trade CSV logger ───────────────────────────────────────────────────────────

_TRADE_HEADERS = [
    "timestamp_utc",
    "coin",
    "side",
    "quantity",
    "price_usd",
    "trade_value_usd",
    "signal_score",
    "portfolio_value_usd",
    "reason",
    "api_success",
]


def _ensure_trade_log() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(TRADE_LOG):
        with open(TRADE_LOG, "w", newline="") as f:
            csv.writer(f).writerow(_TRADE_HEADERS)


def log_trade(
    coin: str,
    side: str,
    quantity: float,
    price: float,
    signal_score: float,
    portfolio_value: float,
    reason: str,
    api_success: bool,
) -> None:
    _ensure_trade_log()
    row = {
        "timestamp_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coin":               coin,
        "side":               side,
        "quantity":           quantity,
        "price_usd":          round(price, 6),
        "trade_value_usd":    round(quantity * price, 2),
        "signal_score":       round(signal_score, 4),
        "portfolio_value_usd": round(portfolio_value, 2),
        "reason":             reason,
        "api_success":        api_success,
    }
    with open(TRADE_LOG, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_TRADE_HEADERS).writerow(row)

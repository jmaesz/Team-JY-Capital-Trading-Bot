"""
Risk management module.

Responsibilities
────────────────
• Track entry prices for open positions (persisted to state.json).
• Detect hard stop-loss breaches.
• Detect portfolio drawdown and toggle defensive mode.
• Compute position quantity given a USD target and current price.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from config import (
    HARD_STOP_LOSS_PCT,
    MAX_DRAWDOWN_PCT,
    STATE_FILE,
    MIN_TRADE_USD,
)

logger = logging.getLogger(__name__)


# ── State persistence ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"entry_prices": {}, "peak_portfolio": 0.0}


def _save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        logger.error("Failed to save state: %s", exc)


# Singleton state loaded once per process
_state = _load_state()


def get_entry_price(coin: str) -> Optional[float]:
    return _state["entry_prices"].get(coin)


def record_entry(coin: str, price: float) -> None:
    _state["entry_prices"][coin] = price
    _save_state(_state)


def clear_entry(coin: str) -> None:
    _state["entry_prices"].pop(coin, None)
    _save_state(_state)


def update_peak(portfolio_value: float) -> float:
    """Update and return peak portfolio value."""
    if portfolio_value > _state.get("peak_portfolio", 0.0):
        _state["peak_portfolio"] = portfolio_value
        _save_state(_state)
    return _state["peak_portfolio"]


def get_peak() -> float:
    return _state.get("peak_portfolio", 0.0)


def reset_state(baseline: float = 0.0) -> None:
    """Clear in-memory and on-disk state. Called on dashboard reset."""
    global _state
    _state = {"entry_prices": {}, "peak_portfolio": 0.0, "baseline": baseline}
    _save_state(_state)


def get_baseline() -> float:
    return _state.get("baseline", 0.0)


# ── Risk checks ────────────────────────────────────────────────────────────────

def is_defensive_mode(current_portfolio: float) -> bool:
    """Return True if max drawdown threshold has been breached."""
    peak = get_peak()
    if peak <= 0:
        return False
    drawdown = (peak - current_portfolio) / peak
    if drawdown >= MAX_DRAWDOWN_PCT:
        logger.warning(
            "DEFENSIVE MODE: drawdown %.2f%% >= %.2f%%",
            drawdown * 100,
            MAX_DRAWDOWN_PCT * 100,
        )
        return True
    return False


def should_stop_loss(coin: str, current_price: float) -> bool:
    """Return True if the position has fallen past the hard stop-loss."""
    entry = get_entry_price(coin)
    if entry is None or entry <= 0:
        return False
    loss_pct = (entry - current_price) / entry
    if loss_pct >= HARD_STOP_LOSS_PCT:
        logger.warning(
            "STOP-LOSS triggered for %s: entry=%.6f current=%.6f loss=%.2f%%",
            coin, entry, current_price, loss_pct * 100,
        )
        return True
    return False


# ── Quantity helpers ───────────────────────────────────────────────────────────

def usd_to_qty(usd_amount: float, price: float, precision: int = 6) -> float:
    """Convert a USD amount into coin quantity, rounded to `precision` decimal places."""
    if price <= 0:
        return 0.0
    return round(usd_amount / price, precision)


def qty_to_usd(qty: float, price: float) -> float:
    return qty * price


def is_tradeable(usd_value: float) -> bool:
    return usd_value >= MIN_TRADE_USD

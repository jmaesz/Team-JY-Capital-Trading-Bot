"""
Multi-signal trading strategy.

Signal score ranges from -1.0 (strong sell) to +1.0 (strong buy).

Component weights
─────────────────
  EMA crossover  (short TF)  0.25
  RSI            (short TF)  0.25
  MACD           (short TF)  0.20
  Bollinger Band (short TF)  0.15
  Trend filter   (long  TF)  0.15
"""

import logging
from typing import Optional, Dict

import pandas as pd

from indicators import ema, rsi, macd, bollinger_bands, volume_ratio
from config import (
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    MAX_POSITION_PCT,
    HIGH_BETA_MAX_PCT,
    HIGH_BETA_COINS,
    MIN_USD_RESERVE_PCT,
    MAX_ACTIVE_POSITIONS,
)

logger = logging.getLogger(__name__)

# Minimum candles required to compute indicators reliably
MIN_CANDLES_SHORT = 50
MIN_CANDLES_LONG  = 60


def compute_signal(
    df_short: pd.DataFrame,
    df_long:  pd.DataFrame,
) -> Optional[float]:
    """
    Compute composite signal score for one coin.

    Parameters
    ----------
    df_short : OHLCV DataFrame for the short timeframe (e.g. 5 m)
    df_long  : OHLCV DataFrame for the long  timeframe (e.g. 1 h)

    Returns
    -------
    float in [-1.0, +1.0], or None if data is insufficient.
    """
    if len(df_short) < MIN_CANDLES_SHORT or len(df_long) < MIN_CANDLES_LONG:
        logger.debug("Insufficient candles for signal computation.")
        return None

    close_s = df_short["close"]
    close_l = df_long["close"]
    score   = 0.0

    # 1 ── EMA crossover on short TF (weight 0.25) ────────────────────────────
    ema12 = ema(close_s, 12).iloc[-1]
    ema26 = ema(close_s, 26).iloc[-1]
    ema_sig = 1.0 if ema12 > ema26 else -1.0
    score += 0.25 * ema_sig

    # 2 ── RSI on short TF (weight 0.25) ──────────────────────────────────────
    rsi_val = rsi(close_s, 14).iloc[-1]
    if pd.isna(rsi_val):
        rsi_sig = 0.0
    elif rsi_val < 30:
        rsi_sig = 1.0
    elif rsi_val > 70:
        rsi_sig = -1.0
    else:
        # linear: 0 at 50, +1 at 30, -1 at 70
        rsi_sig = -(rsi_val - 50.0) / 20.0
    score += 0.25 * rsi_sig

    # 3 ── MACD on short TF (weight 0.20) ─────────────────────────────────────
    macd_line, sig_line, hist = macd(close_s, 12, 26, 9)
    macd_cross = 1.0 if macd_line.iloc[-1] > sig_line.iloc[-1] else -1.0
    # reward accelerating histogram
    hist_momentum = 0.0
    if len(hist) >= 2 and not pd.isna(hist.iloc[-1]) and not pd.isna(hist.iloc[-2]):
        hist_momentum = 0.5 if hist.iloc[-1] > hist.iloc[-2] else -0.5
    macd_sig = (macd_cross + hist_momentum) / 1.5   # normalise ≈ [-1, +1]
    score += 0.20 * macd_sig

    # 4 ── Bollinger Band position on short TF (weight 0.15) ──────────────────
    upper, mid, lower = bollinger_bands(close_s, 20, 2.0)
    bb_range = upper.iloc[-1] - lower.iloc[-1]
    if bb_range > 0:
        bb_pos = (close_s.iloc[-1] - lower.iloc[-1]) / bb_range  # 0→1
        bb_sig = 1.0 - 2.0 * bb_pos   # +1 at lower band, -1 at upper band
    else:
        bb_sig = 0.0
    score += 0.15 * bb_sig

    # 5 ── Long-TF trend filter — HARD GATE (weight 0.15) ────────────────────
    ema20_l = ema(close_l, 20).iloc[-1]
    ema50_l = ema(close_l, 50).iloc[-1]
    if ema20_l <= ema50_l:
        # Bearish 1h trend: hard block – no bullish trade allowed.
        # Return a strongly negative score to prevent any buy signal.
        logger.debug("Hard trend gate: 1h bearish – forcing negative score.")
        return float(max(-1.0, min(1.0, score - 0.60)))
    score += 0.15 * 1.0   # uptrend confirmed

    # 6 ── Volume confirmation (bonus/penalty, ±0.05) ──────────────────────────
    vol_r = volume_ratio(df_short, 20).iloc[-1]
    if not pd.isna(vol_r) and vol_r > 1.5 and score > 0:
        score += 0.05   # high-volume confirms bullish move
    elif not pd.isna(vol_r) and vol_r > 1.5 and score < 0:
        score -= 0.05   # high-volume confirms bearish move

    return float(max(-1.0, min(1.0, score)))


def compute_all_signals(
    klines_short: Dict[str, pd.DataFrame],
    klines_long:  Dict[str, pd.DataFrame],
) -> Dict[str, float]:
    """
    Returns {coin: signal_score} for every coin with sufficient data.
    """
    signals = {}
    for coin in klines_short:
        if coin not in klines_long:
            continue
        sig = compute_signal(klines_short[coin], klines_long[coin])
        if sig is not None:
            signals[coin] = sig
            logger.debug("Signal %s = %.3f", coin, sig)
    return signals


def compute_target_allocations(
    signals:          Dict[str, float],
    portfolio_value:  float,
    current_prices:   Dict[str, float],
    current_holdings: Dict[str, float],   # {coin: usd_value_held}
    defensive_mode:   bool,
) -> Dict[str, float]:
    """
    Convert signal scores into target USD allocations per coin.

    Rules
    ─────
    • In defensive mode: target = 0 for all (hold USD only).
    • Only coins with score > BUY_THRESHOLD are allocated.
    • Top MAX_ACTIVE_POSITIONS coins (by score) are selected.
    • Max allocation per coin = MAX_POSITION_PCT * portfolio_value.
    • Minimum USD reserve = MIN_USD_RESERVE_PCT * portfolio_value.
    • Allocation proportional to signal score among selected coins.
    """
    if defensive_mode:
        return {coin: 0.0 for coin in signals}

    targets: Dict[str, float] = {}

    # Filter coins with a bullish signal above threshold
    candidates = {
        coin: score
        for coin, score in signals.items()
        if score > BUY_THRESHOLD
    }

    # Pick top N by score
    top_coins = sorted(candidates, key=candidates.get, reverse=True)[:MAX_ACTIVE_POSITIONS]

    if not top_coins:
        return {coin: 0.0 for coin in signals}

    investable_usd   = portfolio_value * (1.0 - MIN_USD_RESERVE_PCT)

    # Weight by signal score (scores are all positive here)
    total_score = sum(candidates[c] for c in top_coins)
    if total_score <= 0:
        return {coin: 0.0 for coin in signals}

    for coin in signals:
        if coin in top_coins:
            # High-beta alts get a tighter position cap
            cap_pct = HIGH_BETA_MAX_PCT if coin in HIGH_BETA_COINS else MAX_POSITION_PCT
            max_per_coin_usd = portfolio_value * cap_pct
            weight = candidates[coin] / total_score
            targets[coin] = min(investable_usd * weight, max_per_coin_usd)
        else:
            targets[coin] = 0.0

    # Scale down proportionally if total exceeds investable
    total_target = sum(targets.values())
    if total_target > investable_usd:
        scale = investable_usd / total_target
        targets = {c: v * scale for c, v in targets.items()}

    return targets

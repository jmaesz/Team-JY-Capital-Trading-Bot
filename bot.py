"""
Team JY Capital – Roostoo Trading Bot
======================================
Autonomous trading bot for the SG vs HK University Web3 Quant Hackathon.

Strategy: Multi-signal momentum + trend-following with dynamic portfolio
          allocation and strict risk management (stop-loss, max drawdown).

Data sources
────────────
• Binance public OHLCV API  – historical candlesticks for indicators
• Roostoo mock-exchange API – live prices, balance, order execution

Run
───
    python bot.py

The bot loops indefinitely every TRADE_INTERVAL_SECONDS seconds.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

import api
import data as mkt
from config import (
    TRADE_INTERVAL_SECONDS,
    WATCHLIST,
    SHORT_TF,
    LONG_TF,
    LOOKBACK,
    SELL_THRESHOLD,
    MIN_TRADE_USD,
    MIN_HOLD_SECONDS,
    COMMISSION_RATE,
)
from logger_setup import setup_logging, log_trade
from risk import (
    is_defensive_mode,
    should_stop_loss,
    record_entry,
    clear_entry,
    update_peak,
    update_position_peak,
    usd_to_qty,
    qty_to_usd,
    is_tradeable,
    get_entry_price,
    get_mode,
)
from strategy import compute_all_signals, compute_target_allocations

setup_logging()
logger = logging.getLogger("bot")

# In-memory entry time tracker {coin: timestamp}
_entry_times: Dict[str, float] = {}


def record_entry_time(coin: str) -> None:
    _entry_times[coin] = time.time()


def held_long_enough(coin: str) -> bool:
    """Return True if position has been held for at least MIN_HOLD_SECONDS."""
    entry_time = _entry_times.get(coin)
    if entry_time is None:
        return True  # unknown entry time, allow reduce
    return (time.time() - entry_time) >= MIN_HOLD_SECONDS


# ── Portfolio helpers ──────────────────────────────────────────────────────────

def parse_balance(balance_resp: dict) -> dict[str, float]:
    """
    Parse the Roostoo /v3/balance response.
    Shape: {"SpotWallet": {"USD": {"Free": 50000, "Lock": 0}, "BTC": {...}}}
    Returns {asset: free_amount}.
    """
    holdings: dict[str, float] = {}
    wallet = balance_resp.get("SpotWallet") or {}
    for asset, info in wallet.items():
        free = float(info.get("Free") or info.get("free") or 0)
        if free > 0:
            holdings[asset] = free
    return holdings


def parse_tickers(ticker_resp: dict) -> dict[str, float]:
    """
    Parse the Roostoo /v3/ticker response.
    Shape: {"Data": {"BTC/USD": {"LastPrice": 73998.68, ...}}}
    Returns {coin: last_price_usd}.
    """
    prices: dict[str, float] = {}
    data = ticker_resp.get("Data") or {}
    for pair, info in data.items():
        if "/" in pair:
            coin  = pair.split("/")[0]
            price = float(info.get("LastPrice") or info.get("lastPrice") or 0)
            if price > 0:
                prices[coin] = price
    return prices


def compute_portfolio_value(
    holdings: dict[str, float],
    prices:   dict[str, float],
) -> tuple[float, dict[str, float]]:
    """
    Returns (total_usd, {coin: usd_value_held}).
    USD held is assumed to be the 'USD' key in holdings.
    """
    usd_cash = holdings.get("USD", 0.0)
    coin_values: dict[str, float] = {}

    for coin, qty in holdings.items():
        if coin == "USD":
            continue
        price = prices.get(coin, 0.0)
        if price > 0:
            coin_values[coin] = qty_to_usd(qty, price)

    total = usd_cash + sum(coin_values.values())
    return total, coin_values


def get_active_coins(watchlist: List[str], available_pairs: Set[str]) -> List[str]:
    return [c for c in watchlist if c in available_pairs]


# ── Commission filter ──────────────────────────────────────────────────────────

def covers_commission(coin: str, qty: float, current_price: float) -> bool:
    """Return True if gross profit on this sell exceeds total round-trip commission."""
    entry = get_entry_price(coin)
    if entry is None:
        return True  # no entry tracked, allow sell
    gross_profit = (current_price - entry) * qty
    total_commission = (entry + current_price) * qty * COMMISSION_RATE
    return gross_profit > total_commission


# ── Order execution ────────────────────────────────────────────────────────────

def execute_sell(
    coin: str,
    qty: float,
    price: float,
    signal_score: float,
    portfolio_value: float,
    reason: str,
) -> bool:
    logger.info(
        "SELL %s  qty=%.6f  ~$%.2f  reason=%s",
        coin, qty, qty_to_usd(qty, price), reason,
    )
    resp = api.place_order(f"{coin}/USD", "SELL", qty)
    success = bool(resp.get("Success") or resp.get("success"))
    log_trade(coin, "SELL", qty, price, signal_score, portfolio_value, reason, success)
    if success:
        clear_entry(coin)
    else:
        logger.error("SELL %s failed: %s", coin, resp)
    return success


def execute_buy(
    coin: str,
    qty: float,
    price: float,
    signal_score: float,
    portfolio_value: float,
    reason: str,
) -> bool:
    logger.info(
        "BUY  %s  qty=%.6f  ~$%.2f  reason=%s",
        coin, qty, qty_to_usd(qty, price), reason,
    )
    resp = api.place_order(f"{coin}/USD", "BUY", qty)
    success = bool(resp.get("Success") or resp.get("success"))
    log_trade(coin, "BUY", qty, price, signal_score, portfolio_value, reason, success)
    if success:
        record_entry(coin, price)
        record_entry_time(coin)
    else:
        logger.error("BUY %s failed: %s", coin, resp)
    return success


# ── Main trading cycle ─────────────────────────────────────────────────────────

def run_cycle(tradeable_coins: List[str], precisions: Dict[str, int]) -> None:
    logger.info("─── Cycle start %s ───", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # 1. Balance & prices
    balance_resp = api.get_balance()
    if not balance_resp:
        logger.warning("Could not fetch balance – skipping cycle.")
        return

    ticker_resp = api.get_ticker()
    if not ticker_resp:
        logger.warning("Could not fetch ticker – skipping cycle.")
        return

    holdings = parse_balance(balance_resp)
    prices   = parse_tickers(ticker_resp)

    # Filter to coins we have prices for
    active = [c for c in tradeable_coins if c in prices]
    if not active:
        logger.warning("No price data available for watchlist coins.")
        return

    portfolio_value, coin_usd_values = compute_portfolio_value(holdings, prices)

    if portfolio_value <= 0:
        logger.error("Portfolio value is zero or unreadable. Check API keys.")
        return

    peak = update_peak(portfolio_value)
    drawdown = (peak - portfolio_value) / peak if peak > 0 else 0.0
    logger.info(
        "Portfolio: $%.2f  Peak: $%.2f  Drawdown: %.2f%%",
        portfolio_value, peak, drawdown * 100,
    )

    # 2. Market data & signals
    klines_short = mkt.fetch_all_klines(active, SHORT_TF, LOOKBACK)
    klines_long  = mkt.fetch_all_klines(active, LONG_TF,  LOOKBACK)

    signals = compute_all_signals(klines_short, klines_long)

    if not signals:
        logger.warning("No signals computed – skipping rebalance.")
        return

    logger.info("Signals: %s", {c: f"{s:.3f}" for c, s in signals.items()})

    # 3. Risk checks
    mode      = get_mode()
    defensive = is_defensive_mode(portfolio_value)

    # 4. Stop-loss / manual-stop exits (always run)
    for coin, qty in list(holdings.items()):
        if coin == "USD":
            continue
        price = prices.get(coin, 0.0)
        if price > 0:
            update_position_peak(coin, price)

        if mode == "manual":
            # Manual mode: sell immediately once position is up 5% then starts to drop
            entry = get_entry_price(coin)
            if entry and entry > 0 and price > 0:
                gain_pct = (price - entry) / entry
                from risk import _state as _rs
                peak_price = _rs.get("peak_prices", {}).get(coin, entry)
                if gain_pct >= 0.05 and price < peak_price:
                    qty_rounded = round(qty, precisions.get(coin, 6))
                    logger.info("MANUAL STOP %s – was up ≥5%%, now dropping. Selling.", coin)
                    execute_sell(coin, qty_rounded, price, signals.get(coin, 0.0), portfolio_value, "manual_stop")
        else:
            if price > 0 and should_stop_loss(coin, price):
                qty_rounded = round(qty, precisions.get(coin, 6))
                execute_sell(coin, qty_rounded, price, signals.get(coin, -1.0), portfolio_value, "stop_loss")

    # Refresh balance after stop/manual sells
    holdings = parse_balance(api.get_balance() or {})
    portfolio_value, coin_usd_values = compute_portfolio_value(holdings, prices)

    # In manual mode: no automatic buys or rebalancing — user trades manually
    if mode == "manual":
        logger.info("Manual mode – skipping auto rebalance.")
        logger.info("─── Cycle complete ───\n")
        return

    # 5. Target allocations
    targets = compute_target_allocations(
        signals          = signals,
        portfolio_value  = portfolio_value,
        current_prices   = prices,
        current_holdings = coin_usd_values,
        defensive_mode   = defensive,
    )

    # 6. Execute rebalance
    sells = []
    buys  = []

    for coin in active:
        target_usd  = targets.get(coin, 0.0)
        current_usd = coin_usd_values.get(coin, 0.0)
        price       = prices[coin]
        score       = signals.get(coin, 0.0)
        delta_usd   = target_usd - current_usd

        # Force sell if signal is bearish regardless of target
        if score < SELL_THRESHOLD and current_usd > MIN_TRADE_USD:
            sell_qty = holdings.get(coin, 0.0)
            if covers_commission(coin, sell_qty, price):
                sells.append((coin, sell_qty, price, score, "bearish_signal"))
            else:
                logger.info("SKIP SELL %s – profit would not cover commission.", coin)
            continue

        prec = precisions.get(coin, 6)

        if delta_usd < -MIN_TRADE_USD:
            # Reduce position — skip if profitable or not held long enough
            entry = get_entry_price(coin)
            if entry is not None and price > entry:
                logger.info("SKIP rebalance_reduce %s – position is profitable, letting it run.", coin)
            elif not held_long_enough(coin):
                logger.info("SKIP rebalance_reduce %s – minimum hold time not reached.", coin)
            else:
                sell_usd = abs(delta_usd)
                sell_qty = usd_to_qty(sell_usd, price, prec)
                if sell_qty > 0 and is_tradeable(sell_usd) and covers_commission(coin, sell_qty, price):
                    sells.append((coin, sell_qty, price, score, "rebalance_reduce"))

        elif delta_usd > MIN_TRADE_USD:
            buy_usd = delta_usd
            buy_qty = usd_to_qty(buy_usd, price, prec)
            if buy_qty > 0 and is_tradeable(buy_usd):
                buys.append((coin, buy_qty, price, score, "rebalance_increase"))

    # Execute sells
    for coin, qty, price, score, reason in sells:
        execute_sell(coin, qty, price, score, portfolio_value, reason)
        time.sleep(0.3)   # small gap between orders

    # Re-read USD balance before buying
    time.sleep(1)
    fresh_balance = parse_balance(api.get_balance() or {})
    usd_available = fresh_balance.get("USD", 0.0)

    # Execute buys (only if we have USD)
    for coin, qty, price, score, reason in buys:
        needed_usd = qty_to_usd(qty, price)
        if usd_available < needed_usd:
            logger.info("Insufficient USD ($%.2f) to buy %s ($%.2f) – skipping.", usd_available, coin, needed_usd)
            continue
        if execute_buy(coin, qty, price, score, portfolio_value, reason):
            usd_available -= needed_usd
        time.sleep(0.3)

    if not sells and not buys:
        logger.info("No trades this cycle – portfolio is on target.")

    logger.info("─── Cycle complete ───\n")


# ── Bootstrap ──────────────────────────────────────────────────────────────────

def get_available_pairs() -> set[str]:
    """
    Fetch supported pairs from Roostoo and return set of base coins.
    Exchange info shape: {"TradePairs": {"BTC/USD": {"CanTrade": true, ...}}}
    """
    info = api.get_exchange_info()
    coins: set[str] = set()
    trade_pairs = info.get("TradePairs") or {}
    for pair, meta in trade_pairs.items():
        if "/" in pair and meta.get("CanTrade", True):
            coins.add(pair.split("/")[0])
    if not coins:
        logger.warning("Could not parse exchange info – using full watchlist.")
        coins = set(WATCHLIST)
    return coins


def get_pair_precisions() -> dict[str, int]:
    """
    Return {coin: amount_precision} from exchange info.
    Used to round order quantities correctly per coin.
    """
    info = api.get_exchange_info()
    precisions: dict[str, int] = {}
    for pair, meta in (info.get("TradePairs") or {}).items():
        if "/" in pair:
            coin = pair.split("/")[0]
            precisions[coin] = int(meta.get("AmountPrecision", 6))
    return precisions


def main() -> None:
    logger.info("=" * 60)
    logger.info("Team JY Capital Trading Bot – starting up")
    logger.info("=" * 60)

    # Verify connectivity
    server_time = api.get_server_time()
    logger.info("Roostoo server time: %s", server_time)

    available_pairs = get_available_pairs()
    precisions      = get_pair_precisions()
    tradeable = [c for c in WATCHLIST if c in available_pairs]
    logger.info("Tradeable coins: %s", tradeable)

    if not tradeable:
        logger.error("No tradeable coins found. Check API keys and exchange info.")
        return

    logger.info(
        "Bot running. Interval = %ds. Ctrl+C to stop.",
        TRADE_INTERVAL_SECONDS,
    )

    while True:
        try:
            run_cycle(tradeable, precisions)
        except KeyboardInterrupt:
            logger.info("Interrupted by user – shutting down.")
            break
        except Exception as exc:
            logger.exception("Unexpected error in cycle: %s", exc)
            logger.info("Waiting 60 s before retry…")
            time.sleep(60)
            continue

        time.sleep(TRADE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

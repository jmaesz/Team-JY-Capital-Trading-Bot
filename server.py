"""
Dashboard API server for Team JY Capital Trading Bot.

Endpoints
---------
GET  /api/portfolio         Live balance + holdings
GET  /api/trades            Full trade history (newest first)
GET  /api/portfolio/history Portfolio value snapshots for chart
GET  /api/metrics           Sharpe, Sortino, Calmar, Max Drawdown
GET  /api/status            Bot running state
POST /api/bot/start         Spawn bot.py subprocess
POST /api/bot/stop          Terminate bot.py subprocess

Run:
    python server.py
"""

import csv
import math
import os
import subprocess
import sys
from typing import Optional, List, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
import api as roostoo
import bot as trading_bot
from config import TRADE_LOG, STATE_FILE
from risk import get_peak, reset_state, get_baseline, usd_to_qty, get_entry_price, get_mode, set_mode

app = FastAPI(title="JY Capital Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INITIAL_WALLET = 1_000_000.0
_bot_process: Optional[subprocess.Popen] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_trades() -> List[dict]:
    if not os.path.exists(TRADE_LOG):
        return []
    with open(TRADE_LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _portfolio_series() -> List[float]:
    """Return portfolio values from trade log, oldest first."""
    rows = _read_trades()
    if not rows:
        return [INITIAL_WALLET]
    vals = []
    for r in rows:
        try:
            vals.append(float(r["portfolio_value_usd"]))
        except (KeyError, ValueError):
            pass
    return vals or [INITIAL_WALLET]


def _compute_metrics() -> dict:
    series = _portfolio_series()

    # Need at least 2 points to compute returns
    if len(series) < 2:
        return {"sharpe": None, "sortino": None, "calmar": None, "max_drawdown_pct": 0.0}

    returns = [(series[i] - series[i - 1]) / series[i - 1] for i in range(1, len(series))]

    n       = len(returns)
    mean_r  = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std_r   = math.sqrt(variance) if variance > 0 else 0

    # Downside deviation (for Sortino)
    neg_returns   = [r for r in returns if r < 0]
    if neg_returns:
        down_var = sum(r ** 2 for r in neg_returns) / len(neg_returns)
        down_std = math.sqrt(down_var)
    else:
        down_std = 0

    # Annualise assuming one trade every ~5 min  -> 105120 trades/year
    # Use sqrt(n_per_year) scaling; cap to avoid huge numbers in early trading
    ann_factor = math.sqrt(min(105120, 105120))

    sharpe  = (mean_r / std_r  * ann_factor) if std_r  > 0 else None
    sortino = (mean_r / down_std * ann_factor) if down_std > 0 else None

    # Max drawdown
    peak      = series[0]
    max_dd    = 0.0
    for v in series[1:]:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    calmar = (mean_r * ann_factor / max_dd) if max_dd > 0 else None

    return {
        "sharpe":          round(sharpe,  4) if sharpe  is not None else None,
        "sortino":         round(sortino, 4) if sortino is not None else None,
        "calmar":          round(calmar,  4) if calmar  is not None else None,
        "max_drawdown_pct": round(max_dd * 100, 4),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/portfolio")
def get_portfolio():
    bal  = roostoo.get_balance()
    tick = roostoo.get_ticker()

    holdings_raw = trading_bot.parse_balance(bal)
    prices       = trading_bot.parse_tickers(tick)
    total, coin_values = trading_bot.compute_portfolio_value(holdings_raw, prices)

    peak     = get_peak() or total
    drawdown = max(0.0, (peak - total) / peak * 100) if peak > 0 else 0.0
    baseline = get_baseline() or INITIAL_WALLET
    pnl      = total - baseline
    pnl_pct  = pnl / baseline * 100

    holdings = []
    for coin, usd_val in sorted(coin_values.items(), key=lambda x: -x[1]):
        qty        = holdings_raw.get(coin, 0.0)
        price      = prices.get(coin, 0.0)
        entry      = get_entry_price(coin)
        if entry and entry > 0 and qty > 0:
            position_pnl     = (price - entry) * qty
            position_pnl_pct = (price - entry) / entry * 100
        else:
            position_pnl     = None
            position_pnl_pct = None
        holdings.append({
            "coin":            coin,
            "qty":             qty,
            "value":           usd_val,
            "price":           price,
            "entry_price":     entry,
            "position_pnl":    round(position_pnl, 2)     if position_pnl     is not None else None,
            "position_pnl_pct": round(position_pnl_pct, 2) if position_pnl_pct is not None else None,
        })

    return {
        "total":         round(total, 2),
        "cash":          round(holdings_raw.get("USD", 0.0), 2),
        "pnl":           round(pnl, 2),
        "pnl_pct":       round(pnl_pct, 4),
        "drawdown_pct":  round(drawdown, 4),
        "peak":          round(peak, 2),
        "holdings":      holdings,
        "initial_wallet": INITIAL_WALLET,
    }


@app.get("/api/trades")
def get_trades():
    return list(reversed(_read_trades()))


@app.get("/api/portfolio/history")
def get_portfolio_history():
    rows = _read_trades()
    baseline = get_baseline() or INITIAL_WALLET
    if not rows:
        return [{"time": "Start", "value": baseline}]

    points = [{"time": "Start", "value": baseline}]
    seen_times: set[str] = set()

    for r in rows:
        ts  = r.get("timestamp_utc", "")
        val = r.get("portfolio_value_usd", "")
        try:
            val_f = float(val)
        except ValueError:
            continue
        # Use short time label
        label = ts[11:16] if len(ts) >= 16 else ts
        # Avoid duplicate labels by appending index
        if label in seen_times:
            label = f"{label}*"
        seen_times.add(label)
        points.append({"time": label, "value": round(val_f, 2)})

    return points


@app.get("/api/metrics")
def get_metrics():
    return _compute_metrics()


@app.get("/api/status")
def get_status():
    global _bot_process
    running = _bot_process is not None and _bot_process.poll() is None

    last_cycle = None
    rows = _read_trades()
    if rows:
        last_cycle = rows[-1].get("timestamp_utc")

    return {"running": running, "last_cycle": last_cycle, "mode": get_mode()}


@app.post("/api/mode/{mode}")
def set_trading_mode(mode: str):
    if mode not in ("auto", "manual"):
        raise HTTPException(status_code=400, detail="mode must be 'auto' or 'manual'")
    set_mode(mode)
    return {"ok": True, "mode": mode}


@app.post("/api/bot/start")
def start_bot():
    global _bot_process
    if _bot_process is not None and _bot_process.poll() is None:
        return {"ok": True, "message": "Bot already running", "pid": _bot_process.pid}

    bot_path = os.path.join(os.path.dirname(__file__), "bot.py")
    _bot_process = subprocess.Popen(
        [sys.executable, bot_path],
        cwd=os.path.dirname(__file__),
    )
    return {"ok": True, "message": "Bot started", "pid": _bot_process.pid}


@app.post("/api/bot/stop")
def stop_bot():
    global _bot_process
    if _bot_process is None or _bot_process.poll() is not None:
        return {"ok": True, "message": "Bot is not running"}

    _bot_process.terminate()
    try:
        _bot_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _bot_process.kill()
    _bot_process = None
    return {"ok": True, "message": "Bot stopped"}


class ManualTradeRequest(BaseModel):
    coin: str
    side: str        # "BUY" or "SELL"
    usd_amount: float


@app.post("/api/trade/manual")
def manual_trade(req: ManualTradeRequest):
    coin = req.coin.upper()
    side = req.side.upper()

    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")
    if req.usd_amount <= 0:
        raise HTTPException(status_code=400, detail="usd_amount must be positive")

    tick   = roostoo.get_ticker()
    prices = trading_bot.parse_tickers(tick)
    price  = prices.get(coin)
    if not price:
        raise HTTPException(status_code=400, detail=f"No price found for {coin}")

    info = roostoo.get_exchange_info()
    precisions = {
        pair.split("/")[0]: int(meta.get("AmountPrecision", 6))
        for pair, meta in (info.get("TradePairs") or {}).items()
        if "/" in pair
    }
    prec = precisions.get(coin, 6)

    if side == "BUY":
        qty = usd_to_qty(req.usd_amount, price, prec)
    else:
        bal      = roostoo.get_balance()
        holdings = trading_bot.parse_balance(bal)
        available = holdings.get(coin, 0.0)
        qty = min(round(req.usd_amount / price, prec), round(available, prec))

    if qty <= 0:
        raise HTTPException(status_code=400, detail="Quantity too small or insufficient balance")

    resp    = roostoo.place_order(f"{coin}/USD", side, qty)
    success = bool(resp.get("Success") or resp.get("success"))

    if not success:
        raise HTTPException(status_code=400, detail=f"Order rejected by exchange: {resp}")

    return {"ok": success, "coin": coin, "side": side, "qty": qty, "price": price}


@app.post("/api/bot/reset")
def reset_bot():
    global _bot_process

    # 1. Stop bot if running
    if _bot_process is not None and _bot_process.poll() is None:
        _bot_process.terminate()
        try:
            _bot_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _bot_process.kill()
        _bot_process = None

    # 2. Sell all coin holdings at market price
    bal      = roostoo.get_balance()
    tick     = roostoo.get_ticker()
    holdings = trading_bot.parse_balance(bal)
    prices   = trading_bot.parse_tickers(tick)

    info       = roostoo.get_exchange_info()
    precisions = {
        pair.split("/")[0]: int(meta.get("AmountPrecision", 6))
        for pair, meta in (info.get("TradePairs") or {}).items()
        if "/" in pair
    }

    sold = []
    for coin, qty in holdings.items():
        if coin == "USD":
            continue
        price = prices.get(coin, 0.0)
        prec  = precisions.get(coin, 6)
        qty_r = round(qty, prec)
        if qty_r > 0 and price > 0:
            roostoo.place_order(f"{coin}/USD", "SELL", qty_r)
            sold.append(coin)

    # 3. Get current total to use as new baseline
    bal2     = roostoo.get_balance()
    tick2    = roostoo.get_ticker()
    hold2    = trading_bot.parse_balance(bal2)
    prices2  = trading_bot.parse_tickers(tick2)
    new_total, _ = trading_bot.compute_portfolio_value(hold2, prices2)

    # Reset in-memory AND on-disk state, setting new baseline
    reset_state(baseline=new_total)

    # 4. Clear trade log
    if os.path.exists(TRADE_LOG):
        os.remove(TRADE_LOG)

    return {"ok": True, "message": "Reset complete", "sold": sold}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

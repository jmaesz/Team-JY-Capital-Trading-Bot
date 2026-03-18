# Team JY Capital — Roostoo Trading Bot

> Autonomous AI-driven trading bot for the **SG vs HK University Web3 Quant Hackathon**
> Built on the Roostoo mock exchange · Targets strong Sortino, Sharpe & Calmar ratios

---

## Strategy

Multi-signal **momentum + trend-following** with dynamic portfolio allocation and strict risk management.

A composite score (−1 to +1) is computed for each coin every 5 minutes across five independent signals:

| # | Component | Timeframe | Weight | Signal Logic |
|---|-----------|-----------|--------|--------------|
| 1 | EMA Crossover | 5 m | 25% | EMA-12 > EMA-26 → bullish |
| 2 | RSI | 5 m | 25% | < 35 → buy · > 65 → sell · linear between |
| 3 | MACD | 5 m | 20% | MACD vs signal line + histogram momentum |
| 4 | Bollinger Bands | 5 m | 15% | Near lower band → buy · near upper → sell |
| 5 | Trend Filter | 1 h | 15% | EMA-20 vs EMA-50 for long-term direction |
| + | Volume Bonus | 5 m | ±5% | High-volume confirmation of direction |

---

## Portfolio Rules

| Rule | Value |
|------|-------|
| Max position per coin | 28% of portfolio |
| Minimum USD reserve | 10% always in cash |
| Max simultaneous positions | 5 coins |
| Minimum order size | $100 |

---

## Risk Controls

| Trigger | Action |
|---------|--------|
| Position drops **7%** from entry | Hard stop-loss — full exit |
| Portfolio drawdown exceeds **15%** from peak | Defensive mode — sell all, hold USD |
| Composite signal score falls below **−0.10** | Signal exit — close position |

---

## Data Sources

| Source | Use |
|--------|-----|
| **Binance Public API** | Historical OHLCV (5 m + 1 h) for all indicators — no API key needed |
| **Roostoo Mock Exchange API** | Live prices, portfolio balance, order execution |

---

## Project Structure

```
Team-JY-Capital-Trading-Bot/
│
├── bot.py            Main loop — runs every 5 min, orchestrates all logic
├── strategy.py       Signal computation & target portfolio allocations
├── api.py            Roostoo REST API client (HMAC-SHA256 signed)
├── data.py           Binance public OHLCV fetcher
├── indicators.py     EMA, RSI, MACD, Bollinger Bands, ATR, volume ratio
├── risk.py           Stop-loss, drawdown guard, per-coin quantity precision
├── logger_setup.py   Console + file logging + trades.csv audit trail
├── config.py         All tuneable parameters in one place
└── requirements.txt
```

---

## Watchlist (15 coins)

```
BTC  ETH  BNB  SOL  XRP  ADA  AVAX  LINK  DOT  UNI  DOGE  PEPE  SUI  TON  NEAR
```

---

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add credentials to .env
API_KEY = "YOUR_KEY"
SECRET  = "YOUR_SECRET"

# 3. Start the bot
python bot.py
```

All trades are logged to `logs/trades.csv` · Full debug output in `logs/bot.log`

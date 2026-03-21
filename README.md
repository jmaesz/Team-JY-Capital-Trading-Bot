# Team JY Capital — Roostoo Trading Bot

> Crypto Trading Bot (NUS Investment Society Web3 Quant Trading Hackathon) built on the Roostoo mock exchange, using multi-signal strategies across 15 crypto pairs to maximise risk-adjusted returns.


---

## How It Works

Every 5 minutes, the bot wakes up and runs a full cycle:

**1. Read the current state**
- Fetches your live portfolio balance from Roostoo (how much USD + how much of each coin you hold)
- Fetches current prices for all coins from Roostoo

**2. Collect market data**
- Downloads the last 120 candles of 5-minute and 1-hour price history for each coin from Binance's free public API

**3. Score every coin**

Each coin gets a composite signal score from -1 (strong sell) to +1 (strong buy) based on 5 technical indicators:

| # | Component | Timeframe | Weight | Signal Logic |
|---|-----------|-----------|--------|--------------|
| 1 | EMA Crossover | 5 m | 25% | EMA-12 > EMA-26 means bullish |
| 2 | RSI | 5 m | 25% | < 30 means buy · > 70 means sell · linear between |
| 3 | MACD | 5 m | 20% | MACD vs signal line + histogram momentum |
| 4 | Bollinger Bands | 5 m | 15% | Near lower band means buy · near upper means sell |
| 5 | Trend Filter | 1 h | 15% | EMA-20 vs EMA-50 for long-term direction |
| + | Volume Bonus | 5 m | +/-5% | High-volume confirmation of direction |

**4. Decide target allocations**

Using the scores, it picks the top 3 coins with positive signals (score > 0.20) and assigns each a USD allocation proportional to how strong their signal is, capped at 25% of the portfolio per coin (10% for high-beta alts), always keeping 10% in USD cash.

**5. Risk checks**

Before trading, it checks:
- Has any open position dropped **7%** from where it was bought? Triggers a force sell (stop-loss)
- Has the overall portfolio dropped **35%** from its peak? Sells everything and sits in cash (defensive mode)
- Would selling this position generate less profit than the round-trip commission (0.1% buy + 0.1% sell)? Skips the sell to avoid fee-eating trades

**6. Execute trades**
- Sells first to free up USD: any coin whose signal turned bearish, or whose position needs to be reduced
- Then buys: opens or increases positions in the top-scoring coins with the freed-up USD
- Uses market orders for guaranteed fills

**7. Log everything**

Every trade is written to `logs/trades.csv` with timestamp, coin, quantity, price, signal score, and reason, creating a full audit trail for the judges. Then it sleeps for 5 minutes and repeats.

---

## Portfolio Rules

| Rule | Value |
|------|-------|
| Max position per coin | 25% of portfolio (10% for high-beta alts) |
| High-beta coins | DOGE, SUI, TON, NEAR |
| Minimum USD reserve | 10% always in cash |
| Max simultaneous positions | 3 coins |
| Minimum order size | $100 |

---

## Risk Controls

| Trigger | Action |
|---------|--------|
| Position drops **7%** from entry | Hard stop-loss, full exit |
| Position rises **5%** from entry | Trailing stop activates |
| Trailing stop trails **4%** below peak price | Locks in profits on the way down |
| Portfolio drawdown exceeds **35%** from peak | Defensive mode, sell all and hold USD |
| Composite signal score falls below **-0.20** | Signal exit, close position |
| Sell profit ≤ round-trip commission (0.2% total) | Skip sell, hold until profitable to exit |

---

## Data Sources

| Source | Use |
|--------|-----|
| **Binance Public API** | Historical OHLCV (5 m + 1 h) for all indicators, no API key needed |
| **Roostoo Mock Exchange API** | Live prices, portfolio balance, order execution |

---

## Project Structure

```
Team-JY-Capital-Trading-Bot/
│
├── bot.py            Main loop, runs every 5 min, orchestrates all logic
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

## Watchlist (14 coins)

```
BTC  ETH  BNB  SOL  XRP  ADA  AVAX  LINK  DOT  UNI  DOGE  SUI  TON  NEAR
```

---

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add credentials to .env (no spaces, no quotes)
API_KEY=YOUR_KEY
SECRET=YOUR_SECRET

# 3. Start the bot
py bot.py
```

All trades are logged to `logs/trades.csv` · Full debug output in `logs/bot.log`

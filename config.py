import os
from dotenv import load_dotenv

load_dotenv()

# ── Roostoo credentials ────────────────────────────────────────────────────────
API_KEY  = os.getenv("API_KEY", "").strip()
SECRET   = os.getenv("SECRET",  "").strip()
BASE_URL = "https://mock-api.roostoo.com"

# ── Bot behaviour ──────────────────────────────────────────────────────────────
TRADE_INTERVAL_SECONDS = 300        # main loop cadence: every 5 minutes

# ── Position / allocation limits ──────────────────────────────────────────────
MAX_POSITION_PCT       = 0.25       # max 25 % of portfolio in any single coin
HIGH_BETA_MAX_PCT      = 0.10       # max 10 % for high-volatility alts
HIGH_BETA_COINS        = {"DOGE", "SUI", "TON", "NEAR"}   # reduced-size coins
MIN_USD_RESERVE_PCT    = 0.10       # always keep ≥ 10 % in USD cash
MIN_TRADE_USD          = 100        # ignore rebalance deltas below $100

# ── Risk controls ──────────────────────────────────────────────────────────────
HARD_STOP_LOSS_PCT          = 0.07   # sell if position drops 7 % from entry
MAX_DRAWDOWN_PCT             = 0.35  # go fully defensive at 35 % portfolio drawdown
TRAILING_STOP_ACTIVATE_PCT  = 0.05  # start trailing once position is up 5 %
TRAILING_STOP_PCT            = 0.04  # trail 4 % below running peak price

# ── Strategy signal thresholds ─────────────────────────────────────────────────
BUY_THRESHOLD          = 0.45       # composite score > 0.45 → eligible to hold
SELL_THRESHOLD         = -0.10      # composite score < -0.10 → exit position
MAX_ACTIVE_POSITIONS   = 3          # keep at most 3 coins at once

# ── Data sources ───────────────────────────────────────────────────────────────
BINANCE_BASE  = "https://api.binance.com"
SHORT_TF      = "5m"                # signal timeframe
LONG_TF       = "1h"                # trend filter timeframe
LOOKBACK      = 120                 # number of candles to fetch

# ── Coins to monitor (confirmed available on Roostoo, ranked by liquidity) ────
WATCHLIST = [
    # Large-caps (stable, liquid)
    "BTC", "ETH", "BNB", "SOL", "XRP",
    # Mid-caps (higher momentum potential)
    "ADA", "AVAX", "LINK", "DOT", "UNI",
    # High-beta altcoins (reduced position size – see HIGH_BETA_MAX_PCT)
    "DOGE", "SUI", "TON", "NEAR",
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR    = "logs"
TRADE_LOG  = "logs/trades.csv"
STATE_FILE = "state.json"

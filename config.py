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
MAX_POSITION_PCT       = 0.28       # max 28 % of portfolio in any single coin
MIN_USD_RESERVE_PCT    = 0.10       # always keep ≥ 10 % in USD cash
MIN_TRADE_USD          = 100        # ignore rebalance deltas below $100

# ── Risk controls ──────────────────────────────────────────────────────────────
HARD_STOP_LOSS_PCT     = 0.07       # sell if position drops 7 % from entry
MAX_DRAWDOWN_PCT       = 0.15       # go fully defensive at 15 % portfolio drawdown

# ── Strategy signal thresholds ─────────────────────────────────────────────────
BUY_THRESHOLD          = 0.15       # composite score > 0.15 → eligible to hold
SELL_THRESHOLD         = -0.10      # composite score < -0.10 → exit position
MAX_ACTIVE_POSITIONS   = 5          # keep at most 5 coins at once

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
    # High-beta altcoins (selective use)
    "DOGE", "PEPE", "SUI", "TON", "NEAR",
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR    = "logs"
TRADE_LOG  = "logs/trades.csv"
STATE_FILE = "state.json"

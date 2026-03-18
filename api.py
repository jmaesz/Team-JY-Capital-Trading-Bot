"""
Roostoo mock-exchange API client (Python 3).
All signed endpoints attach RST-API-KEY + MSG-SIGNATURE headers.
"""

import hashlib
import hmac
import logging
import time

import requests

from config import API_KEY, SECRET, BASE_URL

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10   # seconds


# ── Helpers ────────────────────────────────────────────────────────────────────

def _timestamp() -> int:
    """Return current time as 13-digit millisecond timestamp."""
    return int(time.time() * 1000)


def _sign(params: dict) -> str:
    """HMAC-SHA256 signature over sorted key=value pairs."""
    query_string = "&".join(
        f"{k}={params[k]}" for k in sorted(params.keys())
    )
    return hmac.new(
        SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _auth_headers(params: dict) -> dict:
    return {
        "RST-API-KEY":     API_KEY,
        "MSG-SIGNATURE":   _sign(params),
        "Content-Type":    "application/x-www-form-urlencoded",
    }


def _get(path: str, params: dict = None, signed: bool = False) -> dict:
    params = params or {}
    if signed:
        params["timestamp"] = _timestamp()
        headers = _auth_headers(params)
    else:
        headers = {}
    try:
        r = requests.get(
            BASE_URL + path,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("GET %s failed: %s", path, exc)
        return {}


def _post(path: str, payload: dict) -> dict:
    payload["timestamp"] = _timestamp()
    try:
        r = requests.post(
            BASE_URL + path,
            data=payload,
            headers=_auth_headers(payload),
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("POST %s failed: %s", path, exc)
        return {}


# ── Public endpoints ───────────────────────────────────────────────────────────

def get_server_time() -> dict:
    return _get("/v3/serverTime")


def get_exchange_info() -> dict:
    return _get("/v3/exchangeInfo")


def get_ticker(pair: str = None) -> dict:
    """
    pair: e.g. 'BTC/USD'. If None, returns all tickers.
    Requires timestamp param but no auth headers.
    Response: {"Success": true, "Data": {"BTC/USD": {"LastPrice": ..., ...}}}
    """
    params = {"timestamp": _timestamp()}
    if pair:
        params["pair"] = pair
    return _get("/v3/ticker", params=params)


# ── Private / signed endpoints ─────────────────────────────────────────────────

def get_balance() -> dict:
    return _get("/v3/balance", signed=True)


def place_order(pair: str, side: str, quantity: float, price: float = None) -> dict:
    """
    pair     : e.g. 'BTC/USD'
    side     : 'BUY' or 'SELL'
    quantity : amount of the base asset (e.g. 0.01 for 0.01 BTC)
    price    : if provided → LIMIT order; otherwise MARKET
    """
    payload = {
        "pair":     pair,
        "side":     side,
        "quantity": quantity,
    }
    if price is not None:
        payload["type"]  = "LIMIT"
        payload["price"] = price
    else:
        payload["type"] = "MARKET"
    return _post("/v3/place_order", payload)


def cancel_order(pair: str, order_id: int = None) -> dict:
    payload = {"pair": pair}
    if order_id is not None:
        payload["order_id"] = order_id
    return _post("/v3/cancel_order", payload)


def query_orders(pair: str = None, pending_only: bool = False) -> dict:
    payload = {}
    if pair:
        payload["pair"] = pair
    if pending_only:
        payload["pending_only"] = True
    return _post("/v3/query_order", payload)


def get_pending_count() -> dict:
    return _get("/v3/pending_count", signed=True)

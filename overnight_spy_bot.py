#!/usr/bin/env python3
"""
Long-only 'close→open' drift in SPY.
 ▪︎ Buys ~all available cash 1 min before the 16:00 ET close
 ▪︎ Sells entire position 1 min after the 09:30 ET open
 ▪︎ Works in paper or live mode depending on ALPACA_PAPER env var
"""

import os, pytz, datetime as dt, sys
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

API_KEY    = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET")
PAPER      = os.getenv("ALPACA_PAPER", "True").lower() == "true"
CAPITAL    = float(os.getenv("CAPITAL_USD", "330"))     # soft cap

if not API_KEY or not API_SECRET:
    sys.exit("⚠️  Missing Alpaca creds; set env vars or SSM Parameter Store.")

client = TradingClient(API_KEY, API_SECRET, paper=PAPER)

# ---- Decide whether we should trade right now ----
ny_tz  = pytz.timezone("America/New_York")
now_ny = dt.datetime.now(ny_tz).replace(second=0, microsecond=0)

# Market calendar: Monday-Friday only
if now_ny.weekday() >= 5:
    sys.exit("Weekend – no trading")

is_buy_time  = now_ny.hour == 15 and now_ny.minute == 59  # 15:59 ET
is_sell_time = now_ny.hour == 9  and now_ny.minute == 31  # 09:31 ET

if not (is_buy_time or is_sell_time):
    sys.exit("Not a scheduled trade minute")

# ---- Helper: submit a market order ----
def trade(side: OrderSide, qty: str = None, notional: float = None):
    req = MarketOrderRequest(
        symbol     = "SPY",
        side       = side,
        time_in_force = TimeInForce.DAY,
        qty        = qty,
        notional   = notional,
    )
    client.submit_order(req)

# ---- BUY ----
if is_buy_time:
    acct = client.get_account()
    buying_power = float(acct.buying_power)
    cash_to_use  = min(CAPITAL, buying_power)
    if cash_to_use < 1:
        sys.exit("No cash available to buy.")
    trade(OrderSide.BUY, notional=cash_to_use)
    print(f"[{now_ny}] Bought about ${cash_to_use:.2f} SPY")

# ---- SELL ----
if is_sell_time:
    try:
        pos = client.get_open_position("SPY")
    except Exception:
        sys.exit("No SPY position to sell.")
    trade(OrderSide.SELL, qty=pos.qty)
    print(f"[{now_ny}] Sold {pos.qty} SPY")
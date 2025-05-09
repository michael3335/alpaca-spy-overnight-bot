#!/usr/bin/env python3
"""
Long-only S&P 500 addition drift
 ▪︎ Detects new-constituent PDF, stores tickers
 ▪︎ Buys at next open, holds until index inclusion Friday close
"""

import os, re, datetime as dt, tempfile, requests, pytz, csv, sys
import dateutil.parser as dp
from bs4 import BeautifulSoup
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

API_KEY, API_SECRET = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
PAPER = os.getenv("ALPACA_PAPER", "True").lower() == "true"
CAPITAL = float(os.getenv("CAPITAL_USD", "330"))
DATA_FILE = "/home/alpaca/additions.csv"

client = TradingClient(API_KEY, API_SECRET, paper=PAPER)

NY = pytz.timezone("America/New_York")
today = dt.datetime.now(NY).date()

def fetch_pdf_url():
    r = requests.get("https://press.spglobal.com/press-releases")
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if re.search(r"S&P 500.*Addition", a.text, re.I):
            return "https://press.spglobal.com" + a["href"]
    return None

def parse_additions(pdf_url):
    import camelot
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(requests.get(pdf_url).content)
        f.flush()
        tables = camelot.read_pdf(f.name, pages="all")
    adds = []
    for t in tables:
        for row in t.df.values:
            if "Addition" in row[0]:
                adds.append(row[2].strip())
    return list(dict.fromkeys(adds))

def save_additions(tickers, eff_date):
    with open(DATA_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([eff_date])
        for t in tickers:
            w.writerow([t])

def load_additions():
    if not os.path.exists(DATA_FILE):
        return None, []
    with open(DATA_FILE) as f:
        r = list(csv.reader(f))
    eff = dp.parse(r[0][0]).date()
    tickers = [row[0] for row in r[1:]]
    return eff, tickers

# ------- logic ladder -------
pdf = fetch_pdf_url()
if pdf:
    tickers = parse_additions(pdf)
    # S&P effective date is always next Monday after 2nd Friday?  safer: read date in PDF title
    m = re.search(r"effective (.+)$", pdf, re.I)
    eff_date = dp.parse(m.group(1)).date() if m else today + dt.timedelta(days=10)
    save_additions(tickers, eff_date)
    print("Captured additions:", tickers)

eff, adds = load_additions()
if not adds:
    sys.exit("No pending list—exit.")

if today == eff - dt.timedelta(days=3):          # Friday before inclusion
    # SELL everything
    for sym in adds:
        try:
            pos = client.get_open_position(sym)
            trade = MarketOrderRequest(symbol=sym, side=OrderSide.SELL,
                                       qty=pos.qty, time_in_force=TimeInForce.DAY)
            client.submit_order(trade)
            print("Sold", sym)
        except Exception:
            continue
    os.remove(DATA_FILE)

elif today == eff - dt.timedelta(days=10):       # first Monday after announce
    # BUY equal-notional
    acct = client.get_account()
    cash = min(float(acct.buying_power), CAPITAL)
    each = cash / len(adds)
    for sym in adds:
        trade = MarketOrderRequest(symbol=sym, side=OrderSide.BUY,
                                   notional=each, time_in_force=TimeInForce.DAY)
        client.submit_order(trade)
        print("Bought", sym, "≈$", each)
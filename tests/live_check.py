#!/usr/bin/env python3
"""Live data doctor: hit every real data source once and report what came back.

  python3 tests/live_check.py [SYMBOL]      (default RELIANCE)

Run it on your own machine; paste the output into an issue if something fails.
Does not write anything except NSE's cookie in memory.
"""
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "skills" / "_dalal"))

from core import IST  # noqa: E402
import data  # noqa: E402

SYM = (sys.argv[1] if len(sys.argv) > 1 else "RELIANCE").upper()
results = []


def check(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        status = "OK  "
    except Exception as e:  # noqa: BLE001 - a doctor reports everything
        detail = f"{type(e).__name__}: {str(e)[:160]}"
        status = "FAIL"
    results.append(status)
    print(f"[{status}] {name:<34} {time.time() - t0:5.1f}s  {detail}")


def csv_rows(name):
    rows = data.nse_csv(name)
    first = rows[0] if rows else {}
    return f"{len(rows)} rows; columns: {', '.join(list(first)[:6])}"


def bars(interval, rng):
    c = data.chart(SYM, interval, rng)
    b = c["bars"]
    if not b:
        return "0 bars"
    days = sorted({x["dt"].date() for x in b})
    return f"{len(b)} bars over {len(days)} days; last {b[-1]['dt']:%a %d %b %H:%M} close {b[-1]['c']}"


def daily_tail():
    b = data.daily(SYM, "1mo")[-3:]
    return "; ".join(f"{x['dt']:%a %d %b} close {x['c']:.2f}" + (" (rebuilt from 5-min bars)" if x.get("patched") else "")
                     for x in b)


def pit():
    t = dt.datetime.now(IST)
    frm = (t - dt.timedelta(days=7)).strftime("%d-%m-%Y")
    j = data.nse_json(f"/api/corporates-pit?index=equities&from_date={frm}&to_date={t:%d-%m-%Y}", "nse_pit.json")
    if isinstance(j, dict):
        rows = j.get("data") or []
        keys = ", ".join(list(j)[:6])
        first = ", ".join(list(rows[0])[:10]) if rows else "-"
        return f"dict keys [{keys}], {len(rows)} rows; row fields: {first}"
    return f"{type(j).__name__} of {len(j)}"


def nse_list(path):
    j = data.nse_json(path, "x.json")
    rows = j if isinstance(j, list) else (j.get("data") or [])
    return f"{len(rows)} rows" + (f"; first: {json.dumps(rows[0])[:120]}" if rows else "")


def reddit(kind):
    q = urllib.parse.quote(SYM)
    url = f"https://www.reddit.com/r/IndianStreetBets+StockMarketIndia/search.{kind}?q={q}&restrict_sr=1&sort=new&t=week"
    hdr = {"User-Agent": "indian-market-trader/0.1 (research; open source)"} if kind == "json" else None
    raw = data.http_get(url, headers=hdr, retries=0)
    items = data._reddit_json(json.loads(raw)) if kind == "json" else data._reddit_rss(raw)
    return f"{len(items)} posts" + (f"; newest {items[0]['time']:%d %b %H:%M}: {items[0]['title'][:60]}" if items else "")


print(f"Live data check for {SYM} at {dt.datetime.now(IST):%a %d %b %Y %H:%M} IST\n")
check("NSE Nifty 500 list", lambda: csv_rows("nifty500.csv"))
check("NSE security list (bands)", lambda: csv_rows("sec_list.csv"))
check("NSE bulk deals file", lambda: csv_rows("bulk.csv"))
check("Yahoo 5-minute bars (60d)", lambda: bars("5m", "60d"))
check("Yahoo 1-minute bars (1d)", lambda: bars("1m", "1d"))
check("Daily bars, last 3", daily_tail)
check("Yahoo news", lambda: f"{len(data.yahoo_news(SYM))} items")
check("Google News India", lambda: f"{len(data.google_news(SYM + ' share', 1))} items")
check("NSE announcements", lambda: nse_list(f"/api/corporate-announcements?index=equities&symbol={urllib.parse.quote(SYM)}"))
check("NSE board meetings", lambda: nse_list(f"/api/corporate-board-meetings?index=equities&symbol={urllib.parse.quote(SYM)}"))
check("NSE insider (PIT), 7 days", pit)
check("NSE insider (PIT), undated", lambda: nse_list("/api/corporates-pit?index=equities"))
check("Reddit JSON", lambda: reddit("json"))
check("Reddit RSS", lambda: reddit("rss"))
for s in ("TATAMOTORS", "TMPV"):
    check(f"Yahoo symbol {s}", lambda s=s: f"{len(data.chart(s, '1d', '5d')['bars'])} daily bars")

ok = results.count("OK  ")
print(f"\n{ok}/{len(results)} sources OK.")

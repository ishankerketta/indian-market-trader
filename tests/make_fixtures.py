"""Deterministic SYNTHETIC fixtures in the exact shapes Yahoo, NSE, Google News and Reddit return.

These are not real market data. They exist so the whole pipeline can be tested offline
with known answers. TESTCO is built to break out of its opening range at 09:35 on the
test day; FLATCO never breaks out.

  python3 tests/make_fixtures.py OUT_DIR
"""
import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TEST_DAY = dt.date(2026, 11, 2)   # a Monday
SESSIONS = 60


def weekdays_back(end, n):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def ts(d, h, m):
    return int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=IST).timestamp())


def yahoo(symbol, rows, prev_close):
    return {"chart": {"result": [{
        "meta": {"currency": "INR", "symbol": symbol, "chartPreviousClose": prev_close,
                 "regularMarketPrice": rows[-1][4] if rows else None},
        "timestamp": [r[0] for r in rows],
        "indicators": {"quote": [{"open": [r[1] for r in rows], "high": [r[2] for r in rows],
                                  "low": [r[3] for r in rows], "close": [r[4] for r in rows],
                                  "volume": [r[5] for r in rows]}]}}], "error": None}}


def bar(rng, px, vol_scale, drift=0.0, sigma=0.0015):
    o = px
    c = o * (1 + drift + rng.gauss(0, sigma))
    h = max(o, c) * (1 + abs(rng.gauss(0, sigma / 2)))
    l = min(o, c) * (1 - abs(rng.gauss(0, sigma / 2)))
    v = int(vol_scale * (0.6 + rng.random()))
    return round(o, 2), round(h, 2), round(l, 2), round(c, 2), v


def session_5m(rng, d, start_px, breakout=False):
    rows, px = [], start_px
    t = dt.datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST)
    for i in range(75):  # 09:15 .. 15:25
        vs = 40000 if i < 6 or i > 68 else 15000
        if breakout and i < 3:              # tight opening range 09:15-09:30
            o, h, l, c, v = bar(rng, px, vs, 0.0, 0.0008)
            h = min(h, start_px * 1.004)
            l = max(l, start_px * 0.996)
            c = min(max(c, l), h)
            o = min(max(o, l), h)
        elif breakout and i == 4:           # 09:35 bar closes clearly above the range
            o = px
            c = start_px * 1.0075
            h, l, v = c * 1.001, o * 0.999, 90000
            o, h, l, c = round(o, 2), round(h, 2), round(l, 2), round(c, 2)
        elif breakout and i > 4:
            o, h, l, c, v = bar(rng, px, vs, 0.0004, 0.0012)
        else:
            o, h, l, c, v = bar(rng, px, vs)
        rows.append((int(t.timestamp()), o, h, l, c, v))
        px = c
        t += dt.timedelta(minutes=5)
    return rows


def make(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    days = weekdays_back(TEST_DAY, SESSIONS)
    for sym, base, seed, bo in (("TESTCO", 1000.0, 7, True), ("FLATCO", 500.0, 11, False)):
        rng = random.Random(seed)
        rows, daily, px = [], [], base
        prev = None
        for d in days:
            gap = 1 + rng.gauss(0, 0.004)
            s = session_5m(rng, d, round(px * gap, 2), breakout=(bo and d == TEST_DAY) or (bo and rng.random() < 0.35))
            rows += s
            daily.append((ts(d, 9, 15), s[0][1], max(r[2] for r in s), min(r[3] for r in s), s[-1][4],
                          sum(r[5] for r in s)))
            prev = px
            px = s[-1][4]
        Path(out, f"chart_{sym}_5m.json").write_text(json.dumps(yahoo(sym + ".NS", rows, round(prev, 2))))
        # 15-minute bars: every three 5-minute bars combined
        r15 = []
        for i in range(0, len(rows), 3):
            g = rows[i:i + 3]
            r15.append((g[0][0], g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)))
        Path(out, f"chart_{sym}_15m.json").write_text(json.dumps(yahoo(sym + ".NS", r15, round(prev, 2))))
        # Daily: 190 earlier synthetic days + the 60 above
        rng2 = random.Random(seed + 100)
        early, p = [], daily[0][1] * 0.9
        for d in weekdays_back(days[0] - dt.timedelta(days=1), 190):
            o = p
            c = o * (1 + rng2.gauss(0.0005, 0.012))
            early.append((ts(d, 9, 15), round(o, 2), round(max(o, c) * 1.005, 2), round(min(o, c) * 0.995, 2),
                          round(c, 2), int(2.5e6 * (0.6 + rng2.random()))))
            p = c
        drows = early + daily
        Path(out, f"chart_{sym}_1d.json").write_text(json.dumps(yahoo(sym + ".NS", drows, drows[-2][4])))
        # 1m bars for the test day: expand each 5m bar into 5 one-minute bars
        today = [r for r in rows if dt.datetime.fromtimestamp(r[0], IST).date() == TEST_DAY]
        m1 = []
        for r in today:
            t0, o, h, l, c, v = r
            path = [o, (o + h) / 2, h, l, c] if c >= o else [o, (o + l) / 2, l, h, c]
            for k in range(5):
                a, b = path[k], path[min(k + 1, 4)]
                m1.append((t0 + 60 * k, round(a, 2), round(max(a, b), 2), round(min(a, b), 2), round(b, 2), v // 5))
        Path(out, f"chart_{sym}_1m.json").write_text(json.dumps(yahoo(sym + ".NS", m1, round(prev, 2))))

    csv_uni = ("Company Name,Industry,Symbol,Series,ISIN Code\n"
               "Test Company Ltd.,Capital Goods,TESTCO,EQ,INE000T01011\n"
               "Flat Company Ltd.,Chemicals,FLATCO,EQ,INE000F01011\n"
               "Trade To Trade Ltd.,Chemicals,T2TCO,BE,INE000B01011\n")
    Path(out, "nifty500.csv").write_text(csv_uni)
    Path(out, "nifty100.csv").write_text(csv_uni)
    Path(out, "equity_list.csv").write_text(
        "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
        "TESTCO,Test Company Limited,EQ,01-JAN-2010,10,1,INE000T01011,10\n"
        "FLATCO,Flat Company Limited,EQ,01-JAN-2012,10,1,INE000F01011,10\n"
        "T2TCO,Trade To Trade Limited,BE,01-JAN-2015,10,1,INE000B01011,10\n")
    Path(out, "sec_list.csv").write_text(
        "Symbol,Series,Security Name,Band,Remarks\n"
        "TESTCO,EQ,Test Company Limited,20,-\n"
        "FLATCO,EQ,Flat Company Limited,No Band,-\n"
        "T2TCO,BE,Trade To Trade Limited,5,-\n")
    Path(out, "bulk.csv").write_text(
        "Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks\n"
        "02-NOV-2026,TESTCO,Test Company Limited,ALPHA FUND LP,BUY,\"5,00,000\",1004.20,-\n"
        "02-NOV-2026,TESTCO,Test Company Limited,RETAIL TRADER X,SELL,120000,1003.10,-\n"
        "02-NOV-2026,FLATCO,Flat Company Limited,BETA SECURITIES,SELL,300000,498.50,-\n")
    Path(out, "block.csv").write_text(
        "Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price\n"
        "02-NOV-2026,FLATCO,Flat Company Limited,GAMMA INSURANCE,BUY,1000000,497.00\n")
    t_news = int(dt.datetime(2026, 11, 2, 8, 30, tzinfo=IST).timestamp())
    Path(out, "news_TESTCO.json").write_text(json.dumps({"news": [
        {"title": "Test Company bags Rs 1,200 crore order from railways", "publisher": "Moneycontrol",
         "link": "https://example.com/a", "providerPublishTime": t_news},
        {"title": "Test Company shares surge on strong Q2 results, profit jumps 40%", "publisher": "ET Markets",
         "link": "https://example.com/b", "providerPublishTime": t_news - 3600},
        {"title": "Old story about Test Company", "publisher": "Mint",
         "link": "https://example.com/old", "providerPublishTime": t_news - 9 * 86400}]}))
    Path(out, "news_FLATCO.json").write_text(json.dumps({"news": []}))
    rss = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>
<item><title>Test Company stock hits 52-week high after order win - Business Standard</title>
<link>https://example.com/c</link><pubDate>Mon, 02 Nov 2026 03:10:00 GMT</pubDate>
<source url="https://www.business-standard.com">Business Standard</source></item>
<item><title>SEBI not planning probe into Test Company, says official - Livemint</title>
<link>https://example.com/d</link><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate>
<source url="https://www.livemint.com">Livemint</source></item>
</channel></rss>"""
    Path(out, "gnews_TESTCO.xml").write_text(rss)
    Path(out, "gnews_FLATCO.xml").write_text('<?xml version="1.0"?><rss><channel></channel></rss>')
    base = dt.datetime(2026, 11, 2, 9, 0, tzinfo=IST).timestamp()
    posts = []
    for i in range(8):   # 8 posts in the last day
        posts.append({"data": {"title": f"TESTCO to the moon, 10x multibagger, load up now #{i}",
                               "selftext": "Telegram group says target 2000 in 10 days", "subreddit": "IndianStreetBets",
                               "score": 50 + i, "num_comments": 10, "permalink": f"/r/x/{i}",
                               "created_utc": base - i * 3600}})
    for i in range(3):   # 3 posts across the previous 6 days
        posts.append({"data": {"title": f"Thoughts on Test Company results? {i}", "selftext": "Decent quarter.",
                               "subreddit": "StockMarketIndia", "score": 5, "num_comments": 2,
                               "permalink": f"/r/y/{i}", "created_utc": base - (2 + i * 2) * 86400}})
    Path(out, "reddit_TESTCO.json").write_text(json.dumps({"data": {"children": posts}}))
    Path(out, "reddit_FLATCO.json").write_text(json.dumps({"data": {"children": []}}))
    Path(out, "nse_pit.json").write_text(json.dumps({"data": [
        {"symbol": "TESTCO", "company": "Test Company Limited", "acqName": "Promoter Holdings Pvt Ltd",
         "personCategory": "Promoter Group", "secAcq": "100000", "secVal": "100400000",
         "tdpTransactionType": "Buy", "acqMode": "Market Purchase", "acqfromDt": "30-Oct-2026",
         "acqtoDt": "30-Oct-2026", "intimDt": "01-Nov-2026"},
        {"symbol": "FLATCO", "company": "Flat Company Limited", "acqName": "A Director",
         "personCategory": "Director", "secAcq": "5000", "secVal": "2500000",
         "tdpTransactionType": "Sell", "acqMode": "Market Sale", "acqfromDt": "29-Oct-2026",
         "acqtoDt": "29-Oct-2026", "intimDt": "31-Oct-2026"}]}))
    return out


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/generated")
    print("fixtures written")

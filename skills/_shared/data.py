"""Free public data for Indian markets: Yahoo Finance (.NS bars, news), NSE archives,
NSE JSON endpoints (cookie session), Google News India RSS and Reddit.

None of these are official APIs. They can lag, change shape or rate-limit you.
Every fetch can be served from a fixtures folder instead (IMT_FIXTURES=dir),
which is how the test suite runs offline and how you can replay a past day.
"""
import csv
import datetime as dt
import gzip
import html
import http.cookiejar
import re
import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from collections import OrderedDict
from email.utils import parsedate_to_datetime
from pathlib import Path

from core import IST, norm_symbol

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

INDEX_MAP = {"NIFTY": "^NSEI", "NIFTY50": "^NSEI", "BANKNIFTY": "^NSEBANK",
             "SENSEX": "^BSESN", "FINNIFTY": "NIFTY_FIN_SERVICE.NS", "INDIAVIX": "^INDIAVIX"}

CSV_SOURCES = {
    "equity_list.csv": ["https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
                        "https://archives.nseindia.com/content/equities/EQUITY_L.csv"],
    "nifty500.csv": ["https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
                     "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"],
    "nifty100.csv": ["https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
                     "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv"],
    "sec_list.csv": ["https://nsearchives.nseindia.com/content/equities/sec_list.csv",
                     "https://archives.nseindia.com/content/equities/sec_list.csv"],
    "bulk.csv": ["https://nsearchives.nseindia.com/content/equities/bulk.csv",
                 "https://archives.nseindia.com/content/equities/bulk.csv"],
    "block.csv": ["https://nsearchives.nseindia.com/content/equities/block.csv",
                  "https://archives.nseindia.com/content/equities/block.csv"],
}


class DataError(Exception):
    pass


def _fixtures():
    d = os.environ.get("IMT_FIXTURES")
    return Path(d) if d else None


def _fixture_key(s):
    return (s.replace("^", "idx_").replace("&", "_and_").replace("/", "_")
             .replace(" ", "_").replace(":", "_"))


def _decode(resp, raw):
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw)
    return raw


_last_call = {}
_lock = threading.Lock()


def _polite(host, gap=0.2):
    """Space out requests to one host, across threads."""
    with _lock:
        t = _last_call.get(host, 0)
        slot = max(time.time(), t + gap)
        _last_call[host] = slot
    wait = slot - time.time()
    if wait > 0:
        time.sleep(wait)


def http_get(url, headers=None, opener=None, timeout=20, retries=2, fixture=None):
    """GET a URL and return bytes. With IMT_FIXTURES set, read the named fixture instead."""
    fx = _fixtures()
    if fx is not None:
        if not fixture:
            raise DataError(f"no fixture name for {url}")
        p = fx / fixture
        if not p.exists():
            raise DataError(f"fixture missing: {p.name}")
        return p.read_bytes()
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate",
         "Accept-Language": "en-IN,en;q=0.9"}
    h.update(headers or {})
    host = urllib.parse.urlparse(url).netloc
    last = None
    for attempt in range(retries + 1):
        _polite(host)
        try:
            req = urllib.request.Request(url, headers=h)
            op = opener.open if opener else urllib.request.urlopen
            with op(req, timeout=timeout) as resp:
                return _decode(resp, resp.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 404):
                break
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise DataError(f"GET failed {url}: {last}")


# ---------------------------------------------------------------- Yahoo bars

def to_yahoo(symbol):
    s = symbol.strip().upper()
    if s in INDEX_MAP:
        return INDEX_MAP[s]
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def chart(symbol, interval="5m", range_="5d"):
    """OHLCV bars, oldest first: [{t, dt (IST datetime), o, h, l, c, v}].

    Yahoo limits: 1m bars ~7 days, 5m/15m bars ~60 days, daily for years.
    """
    ysym = to_yahoo(symbol)
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ysym)}?interval={interval}&range={range_}&includePrePost=false")
    raw = http_get(url, fixture=f"chart_{_fixture_key(norm_symbol(symbol))}_{interval}.json")
    return parse_chart(json.loads(raw))


def parse_chart(j):
    try:
        res = j["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        err = (j.get("chart") or {}).get("error") if isinstance(j, dict) else None
        raise DataError(f"no chart data ({err})")
    ts = res.get("timestamp") or []
    q = (res.get("indicators") or {}).get("quote", [{}])[0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c = (q.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close"))
        v = (q.get("volume") or [0] * len(ts))[i] or 0
        if None in (o, h, l, c):
            continue
        bars.append({"t": int(t), "dt": dt.datetime.fromtimestamp(int(t), IST),
                     "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": int(v)})
    meta = res.get("meta") or {}
    return {"bars": bars, "prev_close": meta.get("chartPreviousClose") or meta.get("previousClose"),
            "price": meta.get("regularMarketPrice"), "currency": meta.get("currency"),
            "symbol": meta.get("symbol")}


def daily(symbol, range_="1y"):
    """Daily bars with any session Yahoo's daily series is missing rebuilt from 5-minute bars.

    Yahoo's NSE daily bars can lag a session (seen live: daily stopped at Friday while
    5-minute bars had Monday's +11.6% day). Patched bars carry "patched": True.
    """
    bars = chart(symbol, "1d", range_)["bars"]
    last = bars[-1]["dt"].date() if bars else None
    try:
        intraday = chart(symbol, "5m", "5d")["bars"]
    except DataError:
        return bars
    for d, day in by_day(intraday).items():
        day = session_bars(day)
        if not day or (last and d <= last):
            continue
        bars.append({"t": day[0]["t"], "dt": day[0]["dt"].replace(hour=9, minute=15), "o": day[0]["o"],
                     "h": max(b["h"] for b in day), "l": min(b["l"] for b in day), "c": day[-1]["c"],
                     "v": sum(b["v"] for b in day), "patched": True})
    return bars


def by_day(bars):
    days = OrderedDict()
    for b in bars:
        days.setdefault(b["dt"].date(), []).append(b)
    return days


def session_bars(day_bars):
    """Drop anything outside 09:15-15:30 IST (Yahoo sometimes adds a 15:30 stub)."""
    return [b for b in day_bars if dt.time(9, 15) <= b["dt"].time() < dt.time(15, 30)]


# ---------------------------------------------------------------- NSE CSVs

def nse_csv(name):
    """Rows (dicts) of an NSE archive CSV: equity_list, nifty500, nifty100, sec_list, bulk, block."""
    urls = CSV_SOURCES[name]
    last = None
    for u in urls:
        try:
            raw = http_get(u, headers={"Referer": "https://www.nseindia.com/"}, fixture=name)
            text = raw.decode("utf-8-sig", errors="replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows]
        except DataError as e:
            last = e
            if _fixtures() is not None:
                break
    raise DataError(f"could not load {name}: {last}")


def col(row, *names):
    """Pick a column by any of several header spellings (NSE changes them)."""
    low = {k.lower().strip(): v for k, v in row.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return ""


# ---------------------------------------------------------------- NSE JSON (cookie session)

_nse_opener = None


def nse_json(path, fixture):
    """NSE website JSON endpoints need a cookie from the home page first. Best effort."""
    global _nse_opener
    if _fixtures() is None and _nse_opener is None:
        jar = http.cookiejar.CookieJar()
        _nse_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        try:
            http_get("https://www.nseindia.com/", opener=_nse_opener, retries=0)
        except DataError:
            pass
    raw = http_get("https://www.nseindia.com" + path, opener=_nse_opener,
                   headers={"Referer": "https://www.nseindia.com/", "Accept": "application/json"},
                   fixture=fixture)
    return json.loads(raw)


def nse_quote(symbol):
    """Live NSE quote: price, circuit limits, price band, series, surveillance (ASM/GSM).

    Returns {} when NSE refuses; callers fall back to sec_list.csv bands.
    """
    try:
        j = nse_json(f"/api/quote-equity?symbol={urllib.parse.quote(symbol)}", f"nse_quote_{_fixture_key(symbol)}.json")
    except (DataError, ValueError):
        return {}
    pi = j.get("priceInfo") or {}
    si = j.get("securityInfo") or {}
    md = j.get("metadata") or {}
    surv = si.get("surveillance") or {}

    def num(x):
        try:
            return float(str(x).replace(",", ""))
        except (TypeError, ValueError):
            return None
    return {"last": num(pi.get("lastPrice")), "prev_close": num(pi.get("previousClose")),
            "upper_circuit": num(pi.get("upperCP")), "lower_circuit": num(pi.get("lowerCP")),
            "band": pi.get("pPriceBand"), "series": md.get("series") or si.get("series") or "",
            "surveillance": surv.get("surv") or None, "surveillance_desc": surv.get("desc") or "",
            "status": md.get("status") or ""}


def nse_holidays(year=None):
    """NSE equity trading holidays as {date: description}, cached per year in trader/holidays.json."""
    from core import read_state, write_state
    year = year or dt.date.today().year
    cache = read_state("holidays.json") or {}
    if str(year) in cache:
        return {dt.date.fromisoformat(k): v for k, v in cache[str(year)].items()}
    out = {}
    try:
        j = nse_json("/api/holiday-master?type=trading", "nse_holidays.json")
        for h in (j.get("CM") or []):
            try:
                d = dt.datetime.strptime(h.get("tradingDate", ""), "%d-%b-%Y").date()
            except ValueError:
                continue
            out[d] = h.get("description", "holiday")
    except (DataError, ValueError, AttributeError):
        return {}
    if out:
        cache[str(year)] = {d.isoformat(): v for d, v in out.items() if d.year == year}
        write_state("holidays.json", cache)
    return out


def market_day(d):
    """(is_trading_day, reason). Weekends and NSE holidays; unknown holidays count as trading days."""
    if d.weekday() >= 5:
        return False, d.strftime("%A")
    hol = nse_holidays(d.year)
    if d in hol:
        return False, f"NSE holiday: {hol[d]}"
    return True, ""


def all_indices():
    """NSE index snapshot: last, % change, and advances/declines where NSE gives them."""
    j = nse_json("/api/allIndices", "nse_allindices.json")
    out = []
    for r in j.get("data", []):
        out.append({"index": r.get("index") or r.get("indexSymbol"), "last": r.get("last"),
                    "change_pct": r.get("percentChange"), "advances": r.get("advances"),
                    "declines": r.get("declines"), "key": r.get("key", "")})
    return out


def fii_dii():
    """Latest FII/FPI and DII cash-market net buy/sell (INR crore) from NSE."""
    j = nse_json("/api/fiidiiTradeReact", "nse_fiidii.json")
    rows = j if isinstance(j, list) else j.get("data", [])
    out = []
    for r in rows:
        def num(x):
            try:
                return float(str(x).replace(",", ""))
            except (TypeError, ValueError):
                return None
        out.append({"category": r.get("category", ""), "date": r.get("date", ""),
                    "buy": num(r.get("buyValue")), "sell": num(r.get("sellValue")), "net": num(r.get("netValue"))})
    return out


def preopen(key="NIFTY"):
    """NSE pre-open session (09:00-09:08): indicative open vs previous close for an index's stocks."""
    j = nse_json(f"/api/market-data-pre-open?key={key}", f"nse_preopen_{key}.json")
    out = []
    for r in j.get("data", []):
        m = r.get("metadata") or {}
        out.append({"symbol": m.get("symbol"), "iep": m.get("iep") or m.get("lastPrice"),
                    "change_pct": m.get("pChange"), "prev_close": m.get("previousClose"),
                    "value_cr": (m.get("finalQuantity") or 0) * (m.get("iep") or 0) / 1e7})
    return out


# ---------------------------------------------------------------- News and social

def yahoo_news(symbol, count=20):
    ysym = to_yahoo(symbol)
    url = ("https://query1.finance.yahoo.com/v1/finance/search?"
           f"q={urllib.parse.quote(ysym)}&quotesCount=0&newsCount={count}")
    j = json.loads(http_get(url, fixture=f"news_{_fixture_key(norm_symbol(symbol))}.json"))
    out = []
    for n in j.get("news", []) or []:
        ts = n.get("providerPublishTime")
        out.append({"title": n.get("title", ""), "source": n.get("publisher", "Yahoo"),
                    "url": n.get("link", ""), "via": "yahoo",
                    "time": dt.datetime.fromtimestamp(ts, IST) if ts else None})
    return out


def google_news(query, days=1, fixture_key=None):
    q = urllib.parse.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    raw = http_get(url, fixture=f"gnews_{_fixture_key(fixture_key or query)}.xml")
    root = ET.fromstring(raw)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        src = item.find("source")
        source = src.text.strip() if src is not None and src.text else ""
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)]
        when = None
        pd = item.findtext("pubDate")
        if pd:
            try:
                when = parsedate_to_datetime(pd).astimezone(IST)
            except (TypeError, ValueError):
                pass
        out.append({"title": title, "source": source or "Google News", "url": item.findtext("link") or "",
                    "via": "google_news", "time": when})
    return out


REDDIT_SUBS = ["IndianStreetBets", "StockMarketIndia", "IndiaInvestments", "DalalStreetTalks"]


def reddit_search(query, subs=None, window="week", limit=100, fixture_key=None):
    """Public Reddit search: JSON first, then the RSS feed, which Reddit blocks less often.

    Unauthenticated access is rate-limited and sometimes refused outright; raises DataError
    with both reasons when neither works.
    """
    subs = subs or REDDIT_SUBS
    key = _fixture_key(fixture_key or query)
    q = (f"q={urllib.parse.quote(query)}&restrict_sr=1&sort=new&t={window}&limit={limit}")
    base = f"https://www.reddit.com/r/{'+'.join(subs)}/search"
    hdr = {"User-Agent": "indian-market-trader/0.1 (research; open source)"}
    try:
        raw = http_get(f"{base}.json?{q}", headers=hdr, fixture=f"reddit_{key}.json", retries=0)
        return _reddit_json(json.loads(raw))
    except (DataError, ValueError) as e_json:
        try:
            raw = http_get(f"{base}.rss?{q}", headers={"User-Agent": UA}, fixture=f"reddit_{key}.xml", retries=0)
            return _reddit_rss(raw)
        except (DataError, ET.ParseError) as e_rss:
            raise DataError(f"json: {_short(e_json)}; rss: {_short(e_rss)}")


def _short(e):
    s = str(e)
    for code in ("403", "429", "401", "404", "fixture missing"):
        if code in s:
            return {"fixture missing": "no fixture"}.get(code, f"HTTP {code}")
    return s[:60]


def _reddit_rss(raw):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    out = []
    for e in root.findall("a:entry", ns):
        when = None
        up = e.findtext("a:updated", default="", namespaces=ns) or e.findtext("a:published", default="", namespaces=ns)
        try:
            when = dt.datetime.fromisoformat(up.replace("Z", "+00:00")).astimezone(IST)
        except ValueError:
            pass
        link = e.find("a:link", ns)
        cat = e.find("a:category", ns)
        body = re.sub(r"<[^>]+>", " ", html.unescape(e.findtext("a:content", default="", namespaces=ns)))
        out.append({"title": e.findtext("a:title", default="", namespaces=ns), "text": " ".join(body.split())[:500],
                    "sub": cat.get("term", "") if cat is not None else "", "upvotes": None, "comments": None,
                    "url": link.get("href", "") if link is not None else "", "time": when})
    return [p for p in out if p["time"]]


def _reddit_json(j):
    out = []
    for ch in (j.get("data") or {}).get("children", []):
        d = ch.get("data") or {}
        out.append({"title": d.get("title", ""), "text": (d.get("selftext") or "")[:500],
                    "sub": d.get("subreddit", ""), "upvotes": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "url": "https://www.reddit.com" + d.get("permalink", ""),
                    "time": dt.datetime.fromtimestamp(d.get("created_utc", 0), IST)})
    return out

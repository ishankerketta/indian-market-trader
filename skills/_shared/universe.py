"""Stock universe, series and circuit-band lookups, cached in trader/."""
from core import now, read_state, write_state, norm_symbol
from data import DataError, col, nse_csv
from indicators import parse_band

UNIVERSE_FILES = {"nifty500": "nifty500.csv", "nifty100": "nifty100.csv", "all": "equity_list.csv"}


def build_universe(source="nifty500"):
    if source not in UNIVERSE_FILES:
        raise ValueError(f"universe must be one of {', '.join(UNIVERSE_FILES)}")
    rows = nse_csv(UNIVERSE_FILES[source])
    out = []
    for r in rows:
        sym = col(r, "Symbol", "SYMBOL")
        if not sym:
            continue
        out.append({"symbol": norm_symbol(sym),
                    "name": col(r, "Company Name", "NAME OF COMPANY", "Security Name"),
                    "series": col(r, "Series", "SERIES") or "EQ",
                    "industry": col(r, "Industry")})
    uni = {"source": source, "updated": now().isoformat(timespec="minutes"), "symbols": out}
    write_state("universe.json", uni)
    return uni


def load_universe(source=None):
    uni = read_state("universe.json")
    if uni and (source is None or uni.get("source") == source):
        return uni
    return build_universe(source or "nifty500")


def names():
    uni = read_state("universe.json") or {"symbols": []}
    return {s["symbol"]: s.get("name", "") for s in uni["symbols"]}


def load_bands(refresh=False):
    """{SYMBOL: {"series": "EQ", "band": 20.0 or None}} from NSE's sec_list.csv."""
    cached = read_state("bands.json")
    today = now().date().isoformat()
    if cached and cached.get("date") == today and not refresh:
        return cached["bands"]
    try:
        rows = nse_csv("sec_list.csv")
    except DataError:
        return (cached or {}).get("bands", {})
    bands = {}
    for r in rows:
        sym = norm_symbol(col(r, "Symbol", "SYMBOL"))
        if not sym:
            continue
        series = col(r, "Series", "SERIES") or "EQ"
        # Keep the EQ row when a symbol is listed in several series
        if sym in bands and bands[sym]["series"] == "EQ":
            continue
        bands[sym] = {"series": series, "band": parse_band(col(r, "Band", "Price Band", "BAND"))}
    write_state("bands.json", {"date": today, "bands": bands})
    return bands

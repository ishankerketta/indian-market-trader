"""Indicators, setup rules and NSE market rules shared by the skills."""
import datetime as dt
import math


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def ema(xs, n):
    if len(xs) < n:
        return None
    k = 2 / (n + 1)
    e = sum(xs[:n]) / n
    for x in xs[n:]:
        e = x * k + e * (1 - k)
    return e


def rsi(closes, n=14):
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def atr(bars, n=14):
    if len(bars) <= n:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


def vwap(day_bars):
    pv = vol = 0.0
    for b in day_bars:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        pv += tp * b["v"]
        vol += b["v"]
    return pv / vol if vol else None


# ---------------------------------------------------------------- bar timing

def bar_minutes(bars):
    """The bar size in minutes: the most common gap between bars.

    Not the smallest gap: during the session Yahoo adds a still-forming bar stamped at the
    current minute (say 11:42 after the 11:40 bar), which would make the smallest gap 2 minutes.
    """
    gaps = [round((bars[i + 1]["t"] - bars[i]["t"]) / 60) for i in range(len(bars) - 1)
            if bars[i + 1]["t"] > bars[i]["t"]]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return 5
    counts = {}
    for g in gaps:
        counts[g] = counts.get(g, 0) + 1
    best = max(counts.values())
    return min(g for g, c in counts.items() if c == best)


def completed(day_bars, at, minutes=None):
    """Bars whose interval has fully closed by `at` (an aware datetime)."""
    m = minutes or bar_minutes(day_bars)
    return [b for b in day_bars if b["dt"] + dt.timedelta(minutes=m) <= at]


# ---------------------------------------------------------------- opening range breakout

def opening_range(day_bars, orb_minutes=15):
    if not day_bars:
        return None
    start = day_bars[0]["dt"].replace(hour=9, minute=15, second=0, microsecond=0)
    end = start + dt.timedelta(minutes=orb_minutes)
    rng = [b for b in day_bars if start <= b["dt"] < end]
    m = bar_minutes(day_bars)
    if not rng or rng[-1]["dt"] + dt.timedelta(minutes=m) < end:
        return None
    return {"high": max(b["h"] for b in rng), "low": min(b["l"] for b in rng),
            "end": end, "bars": len(rng)}


def orb_trigger(day_bars, orb_minutes=15, side="long", window=("09:30", "14:30"), at=None):
    """First completed bar after the range that CLOSES beyond it, inside the entry window.

    Returns (or, trigger_bar or None). `at` limits to bars closed by then.
    """
    orr = opening_range(day_bars, orb_minutes)
    if orr is None:
        return None, None
    m = bar_minutes(day_bars)
    bars = completed(day_bars, at, m) if at else day_bars
    w0 = dt.time(*map(int, window[0].split(":")))
    w1 = dt.time(*map(int, window[1].split(":")))
    for b in bars:
        if b["dt"] < orr["end"]:
            continue
        close_time = (b["dt"] + dt.timedelta(minutes=m)).time()
        if close_time < w0:
            continue
        if close_time > w1:
            break
        if side == "long" and b["c"] > orr["high"]:
            return orr, b
        if side == "short" and b["c"] < orr["low"]:
            return orr, b
    return orr, None


def stop_price(rule, side, entry, orr, atr_value=None):
    """Stop rules: or-mid, or-low (or-high for shorts), atr:K, pct:P."""
    long_ = side == "long"
    if rule == "or-mid":
        return (orr["high"] + orr["low"]) / 2
    if rule in ("or-low", "or-high", "or-far"):
        return orr["low"] if long_ else orr["high"]
    if rule.startswith("atr:"):
        if not atr_value:
            raise ValueError("atr stop needs an ATR value")
        k = float(rule.split(":")[1])
        return entry - k * atr_value if long_ else entry + k * atr_value
    if rule.startswith("pct:"):
        p = float(rule.split(":")[1]) / 100
        return entry * (1 - p) if long_ else entry * (1 + p)
    raise ValueError(f"unknown stop rule {rule!r}")


def target_price(rule, side, entry, stop):
    """Target rules: 1R, 1.5R, 2R ..., or pct:P."""
    risk = abs(entry - stop)
    long_ = side == "long"
    if rule.upper().endswith("R"):
        k = float(rule[:-1])
        return entry + k * risk if long_ else entry - k * risk
    if rule.startswith("pct:"):
        p = float(rule.split(":")[1]) / 100
        return entry * (1 + p) if long_ else entry * (1 - p)
    raise ValueError(f"unknown target rule {rule!r}")


# ---------------------------------------------------------------- NSE market rules

# NSE equity tick sizes by price (revised 2025). Verify with your broker;
# override with "tick_size" in config to force one value.
TICK_BANDS = [(250, 0.01), (1000, 0.05), (5000, 0.10), (10000, 0.50), (20000, 1.00), (math.inf, 5.00)]


def tick_size(price, override=None):
    if override:
        return float(override)
    for limit, tick in TICK_BANDS:
        if price < limit:
            return tick
    return 0.05


def round_tick(price, direction="nearest", override=None):
    t = tick_size(price, override)
    n = price / t
    if direction == "up":
        n = math.ceil(n - 1e-9)
    elif direction == "down":
        n = math.floor(n + 1e-9)
    else:
        n = round(n)
    return round(n * t, 2)


def band_limits(prev_close, band_pct):
    """Upper/lower circuit for a stock's price band (2, 5, 10, 20). None = no band (F&O stocks)."""
    if not band_pct or not prev_close:
        return None, None
    return prev_close * (1 + band_pct / 100), prev_close * (1 - band_pct / 100)


def parse_band(s):
    s = (s or "").strip().upper()
    if s in ("", "NO BAND", "NO_BAND", "NOBAND", "-"):
        return None
    try:
        return float(s.replace("%", ""))
    except ValueError:
        return None

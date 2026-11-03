"""Intraday equity (NSE, MIS) charges model.

Statutory rates as published by Indian brokers in 2026 for equity intraday:
  STT            0.025% of sell value
  NSE txn charge 0.00297% of turnover (both sides)
  IPFT (NSE)     0.0001% of turnover
  SEBI fee       Rs 10 / crore = 0.0001% of turnover
  Stamp duty     0.003% of buy value
  GST            18% on (brokerage + exchange txn + SEBI fee + IPFT)
Brokers add their own brokerage, and some quote a slightly higher exchange
charge that bundles clearing. Rates change with budgets and circulars: override
any of them in trader/config.json under "rates". Verify against your broker's
contract note before trusting a rupee figure here.
"""

DEFAULT_RATES = {
    "stt_sell": 0.00025,
    "exchange_txn": 0.0000297,
    "ipft": 0.000001,
    "sebi": 0.000001,
    "stamp_buy": 0.00003,
    "gst": 0.18,
}

# Brokerage per executed order
PROFILES = {
    "discount": {"pct": 0.0003, "cap": 20.0},   # 0.03% or Rs 20, whichever is lower
    "flat20": {"pct": None, "flat": 20.0},
    "zero": {"pct": None, "flat": 0.0},
    "full_service": {"pct": 0.0005, "cap": None},
}


def brokerage(value, profile="discount"):
    p = PROFILES.get(profile)
    if p is None:
        raise ValueError(f"unknown broker_profile {profile!r}; use one of {', '.join(PROFILES)}")
    if p.get("pct") is None:
        return p.get("flat", 0.0) if value > 0 else 0.0
    b = value * p["pct"]
    return min(b, p["cap"]) if p.get("cap") is not None else b


def intraday_charges(buy_price, sell_price, qty, profile="discount", rates=None):
    """Full charge breakdown for one round trip (one buy order + one sell order)."""
    r = dict(DEFAULT_RATES)
    r.update(rates or {})
    buy_v = buy_price * qty
    sell_v = sell_price * qty
    turnover = buy_v + sell_v
    brk = brokerage(buy_v, profile) + brokerage(sell_v, profile)
    stt = sell_v * r["stt_sell"]
    exch = turnover * r["exchange_txn"]
    ipft = turnover * r["ipft"]
    sebi = turnover * r["sebi"]
    stamp = buy_v * r["stamp_buy"]
    gst = (brk + exch + sebi + ipft) * r["gst"]
    total = brk + stt + exch + ipft + sebi + stamp + gst
    gross = (sell_v - buy_v)
    return {
        "buy_value": round(buy_v, 2), "sell_value": round(sell_v, 2), "turnover": round(turnover, 2),
        "brokerage": round(brk, 2), "stt": round(stt, 2), "exchange": round(exch, 2),
        "ipft": round(ipft, 2), "sebi": round(sebi, 2), "stamp": round(stamp, 2), "gst": round(gst, 2),
        "total": round(total, 2), "gross_pnl": round(gross, 2), "net_pnl": round(gross - total, 2),
    }


def per_share_cost(price, qty, profile="discount", rates=None):
    """Approximate round-trip charges per share at roughly this price."""
    if qty <= 0:
        return 0.0
    return intraday_charges(price, price, qty, profile, rates)["total"] / qty


def breakeven_sell(buy_price, qty, profile="discount", rates=None):
    """Lowest sell price at which a long round trip nets >= 0, to the paisa."""
    lo, hi = buy_price, buy_price * 1.05
    for _ in range(60):
        mid = (lo + hi) / 2
        if intraday_charges(buy_price, mid, qty, profile, rates)["net_pnl"] >= 0:
            hi = mid
        else:
            lo = mid
    return round(hi + 0.005, 2)

"""Shared plumbing for the Indian Market Traders: config, state files, IST clock.

Standard library only. Every tool reads and writes JSON in a `trader/` folder in
the current directory (override with IMT_DIR), so each skill can pick up
what the previous one wrote.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

# Windows consoles often use a legacy encoding that cannot print the rupee sign.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")

MARKET_OPEN = dt.time(9, 15)
MARKET_CLOSE = dt.time(15, 30)

DEFAULT_CONFIG = {
    # Safety
    "paper": True,                 # paper trading is the default; live needs an explicit false
    "allow_short": False,          # intraday shorting off unless you turn it on
    "use_leverage": False,         # MIS leverage off unless you turn it on
    "mis_leverage": 5,             # only used when use_leverage is true

    # Money
    "capital": 100000,             # INR
    "max_loss_per_trade": 500,     # INR, including charges
    "daily_loss_limit": 1500,      # INR
    "max_trades_per_day": 3,
    "max_position_pct": 50,        # % of capital (x leverage if on) in one position
    "min_reward_risk": 1.5,        # net of charges

    # Session (IST)
    "orb_minutes": 15,             # opening range 09:15-09:30
    "entry_window": ["09:30", "14:30"],
    "flat_by": "15:10",            # brokers auto-square MIS ~15:15-15:20; be out first
    "max_chase_pct": 1.0,          # do not enter if price ran > this % past the trigger

    # Universe and filters
    "universe": "nifty500",        # nifty500 | nifty100 | all
    "min_price": 50,
    "min_avg_turnover_cr": 5,      # 20-day average daily turnover, INR crore
    "allow_series": ["EQ"],        # BE/BZ (trade-to-trade) cannot be traded intraday
    "min_band_pct": 10,            # block stocks in a 2% or 5% circuit band
    "circuit_buffer_pct": 1.0,     # block if entry/target within this % of the band

    # Orders
    "entry_buffer_pct": 0.10,      # limit price = trigger + this %
    "order_type": "LIMIT",         # many brokers block market orders via API

    # Charges: see costs.py. zerodha | angelone | dhan | upstox | groww | fyers | discount (0.03%/Rs 20)
    "broker_profile": "discount",

    # SEBI insider-trading guard: companies where you are a designated person or hold UPSI.
    # The Risk Manager always blocks these. Keep this list current.
    "pit_restricted": [],
    "rates": {},                   # override any statutory rate here, e.g. {"stt_sell": 0.00025}

    # Sentiment
    "buzz_spike_ratio": 3.0,       # mentions vs baseline that counts as a spike
}


def state_dir():
    d = Path(os.environ.get("IMT_DIR", "trader"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(name):
    return state_dir() / name


def read_state(name, default=None):
    p = state_path(name)
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_state(name, data):
    p = state_path(name)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, p)
    return p


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    user = read_state("config.json", {}) or {}
    for k, v in user.items():
        if k == "rates" and isinstance(v, dict):
            cfg["rates"].update(v)
        else:
            cfg[k] = v
    return cfg


def now():
    """Current time in IST. IMT_NOW=YYYY-MM-DDTHH:MM replays a moment (tests, post-mortems)."""
    fake = os.environ.get("IMT_NOW")
    if fake:
        t = dt.datetime.fromisoformat(fake)
        return t if t.tzinfo else t.replace(tzinfo=IST)
    return dt.datetime.now(IST)


def parse_ts(s):
    """ISO timestamp -> aware datetime; a timestamp without a zone (e.g. hand-edited) is read as IST."""
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=IST)


def parse_hhmm(s):
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def at_today(hhmm, ref=None):
    ref = ref or now()
    t = parse_hhmm(hhmm) if isinstance(hhmm, str) else hhmm
    return dt.datetime.combine(ref.date(), t, tzinfo=IST)


def fmt_inr(x):
    """Rs 1,23,456.78 in Indian digit grouping."""
    neg = x < 0
    x = abs(round(x, 2))
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + "₹" + whole + "." + frac


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def norm_symbol(s):
    return s.strip().upper().replace(".NS", "").replace(".BO", "")

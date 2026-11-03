#!/usr/bin/env python3
"""Entry Timer: watch a setup bar by bar and say waiting / triggered / expired.

  entry.py check SYMBOL [--setup orb] [--side long|short] [--at HH:MM]
  entry.py watch SYMBOL [--every 30] [--side long]      loop until triggered or expired
"""
import argparse
import datetime as dt
import os
import pathlib
import sys
import time

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "_shared" if (_HERE / "_shared").is_dir() else _HERE.parent / "_shared"))

from core import at_today, die, load_config, now, write_state, norm_symbol  # noqa: E402
from data import DataError, by_day, chart, market_day, session_bars  # noqa: E402
from indicators import bar_minutes, completed, opening_range, orb_trigger  # noqa: E402


def check(symbol, side, cfg, at):
    data = chart(symbol, "5m", "5d")
    days = by_day(data["bars"])
    today = at.date()
    tb = session_bars(days.get(today, []))
    base = {"symbol": symbol, "setup": "orb", "side": side, "checked_at": at.isoformat(timespec="minutes"),
            "orb_minutes": cfg["orb_minutes"], "entry_window": cfg["entry_window"]}
    if not tb:
        trading, why = market_day(today)
        if not trading:
            return {**base, "status": "expired", "reason": f"market closed today ({why})"}
        return {**base, "status": "waiting", "reason": "no bars for today yet (pre-open or data lag)"}
    m = bar_minutes(tb)
    done = completed(tb, at, m)
    orr = opening_range(done, cfg["orb_minutes"]) if done else None
    w_end = at_today(cfg["entry_window"][1], at)
    if orr is None:
        return {**base, "status": "waiting", "reason": f"opening range ({cfg['orb_minutes']} min) still forming"}
    orr, trig = orb_trigger(tb, cfg["orb_minutes"], side, cfg["entry_window"], at)
    last = done[-1]
    base.update({"or_high": round(orr["high"], 2), "or_low": round(orr["low"], 2), "last": round(last["c"], 2),
                 "last_bar": last["dt"].strftime("%H:%M")})
    if trig is None:
        if at >= w_end:
            return {**base, "status": "expired", "reason": f"no breakout before {cfg['entry_window'][1]}"}
        forming = [b for b in tb if b not in done]
        note = f" (the {forming[0]['dt']:%H:%M} bar is still forming)" if forming else ""
        return {**base, "status": "waiting", "reason": f"no 5-minute close beyond the range yet{note}"}
    long_ = side == "long"
    trig_close = trig["c"]
    base.update({"trigger_bar": trig["dt"].strftime("%H:%M"),
                 "trigger_time": (trig["dt"] + dt.timedelta(minutes=m)).strftime("%H:%M"),
                 "trigger_price": round(trig_close, 2)})
    chase = (last["c"] / trig_close - 1) * 100 * (1 if long_ else -1)
    failed = last["c"] < orr["low"] if long_ else last["c"] > orr["high"]
    if failed:
        return {**base, "status": "expired", "reason": "breakout failed: price is back through the other side of the range"}
    if chase > cfg["max_chase_pct"]:
        return {**base, "status": "expired",
                "reason": f"price ran {chase:.2f}% past the trigger (limit {cfg['max_chase_pct']}%); do not chase"}
    if at >= w_end:
        return {**base, "status": "expired", "reason": "entry window closed"}
    return {**base, "status": "triggered",
            "reason": f"first 5-minute close {'above' if long_ else 'below'} the range at {base['trigger_time']}",
            "chase_pct": round(chase, 2)}


def show(r):
    line = f"{r['symbol']} {r['side']} ORB @ {r['checked_at'][11:16]}: {r['status'].upper()} - {r['reason']}"
    print(line)
    if "or_high" in r:
        print(f"  range {r['or_low']} - {r['or_high']}, last {r['last']} ({r['last_bar']} bar)")
    if r.get("trigger_price"):
        print(f"  trigger close {r['trigger_price']} at {r['trigger_time']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "watch"])
    ap.add_argument("symbol")
    ap.add_argument("--setup", default="orb", choices=["orb"])
    ap.add_argument("--side", default="long", choices=["long", "short"])
    ap.add_argument("--at", help="HH:MM IST (check only)")
    ap.add_argument("--every", type=int, default=30, help="seconds between checks (watch)")
    args = ap.parse_args()
    cfg = load_config()
    if args.side == "short" and not cfg["allow_short"]:
        die("shorts are off. Set \"allow_short\": true in trader/config.json if you mean it.")
    sym = norm_symbol(args.symbol)
    try:
        if args.cmd == "check":
            r = check(sym, args.side, cfg, at_today(args.at) if args.at else now())
            write_state("entry.json", r)
            show(r)
            return
        while True:
            r = check(sym, args.side, cfg, now())
            write_state("entry.json", r)
            show(r)
            if r["status"] != "waiting" or os.environ.get("IMT_NOW"):
                break
            time.sleep(max(10, args.every))
    except DataError as e:
        die(str(e))


if __name__ == "__main__":
    main()

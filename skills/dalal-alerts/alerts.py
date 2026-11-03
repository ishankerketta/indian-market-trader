#!/usr/bin/env python3
"""Price Alerts: ring when a price, a stop, a target or a time hits. Each alert rings once.

  alerts.py add --from-plan                         stop, target and flat-by from dalal/plan.json
  alerts.py add SYMBOL --above 2500 [--note ...]
  alerts.py add SYMBOL --below 2400
  alerts.py add --at 15:10 [--note "flatten everything"]
  alerts.py check                                   ring what hit since the last check
  alerts.py watch [--every 60]                      check in a loop until 15:30
  alerts.py list | clear [--fired]
"""
import argparse
import datetime as dt
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_dalal"))

from core import at_today, die, now, read_state, write_state, norm_symbol  # noqa: E402
from data import DataError, by_day, chart, session_bars  # noqa: E402


def load():
    return read_state("alerts.json") or {"alerts": []}


def new_alert(kind, symbol=None, level=None, at=None, note=""):
    t = now()
    return {"id": f"a{int(t.timestamp() * 1000) % 10**9}{kind[0]}", "kind": kind, "symbol": symbol,
            "level": level, "at": at, "note": note, "created": t.isoformat(timespec="seconds"),
            "fired": None}


def cmd_add(args, store):
    added = []
    if args.from_plan:
        p = read_state("plan.json") or die("no dalal/plan.json")
        long_ = p["side"] == "long"
        added.append(new_alert("below" if long_ else "above", p["symbol"], p["stop"],
                               note=f"STOP hit on {p['symbol']} - exit now"))
        added.append(new_alert("above" if long_ else "below", p["symbol"], p["target"],
                               note=f"TARGET hit on {p['symbol']} - take profit"))
        added.append(new_alert("time", at=p.get("flat_by", "15:10"),
                               note=f"FLAT-BY: close {p['symbol']} and anything else still open"))
    elif args.at:
        added.append(new_alert("time", at=args.at, note=args.note or f"it is {args.at}"))
    else:
        if not args.symbol or (args.above is None and args.below is None):
            die("give SYMBOL with --above or --below, or --at HH:MM, or --from-plan")
        sym = norm_symbol(args.symbol)
        if args.above is not None:
            added.append(new_alert("above", sym, args.above, note=args.note or f"{sym} above {args.above}"))
        if args.below is not None:
            added.append(new_alert("below", sym, args.below, note=args.note or f"{sym} below {args.below}"))
    store["alerts"].extend(added)
    write_state("alerts.json", store)
    for a in added:
        print(f"added {a['id']}: {describe(a)}")


def describe(a):
    if a["kind"] == "time":
        return f"at {a['at']} IST - {a['note']}"
    return f"{a['symbol']} {a['kind']} {a['level']} - {a['note']}"


def cmd_check(store, quiet=False):
    t = now()
    pending = [a for a in store["alerts"] if not a["fired"]]
    rang = []
    cache = {}
    for a in pending:
        if a["kind"] == "time":
            if t >= at_today(a["at"], t):
                rang.append((a, f"{t:%H:%M}"))
            continue
        sym = a["symbol"]
        if sym not in cache:
            try:
                bars = session_bars(by_day(chart(sym, "1m", "1d")["bars"]).get(t.date(), []))
                cache[sym] = [b for b in bars if b["dt"] <= t]
            except DataError as e:
                print(f"{sym}: no data ({e})")
                cache[sym] = []
        created = dt.datetime.fromisoformat(a["created"])
        since = [b for b in cache[sym] if b["dt"] + dt.timedelta(minutes=1) > created]
        for b in since:
            if (a["kind"] == "above" and b["h"] >= a["level"]) or (a["kind"] == "below" and b["l"] <= a["level"]):
                rang.append((a, f"{b['dt']:%H:%M} (bar {b['l']:.2f}-{b['h']:.2f})"))
                break
    for a, when in rang:
        a["fired"] = t.isoformat(timespec="seconds")
        print(f"\a*** RING *** {describe(a)}  [{when}]")
    if rang:
        write_state("alerts.json", store)
    elif not quiet:
        left = len(pending)
        print(f"{t:%H:%M}: nothing hit. {left} alert{'s' if left != 1 else ''} armed.")
    return rang


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["add", "check", "watch", "list", "clear"])
    ap.add_argument("symbol", nargs="?")
    ap.add_argument("--above", type=float)
    ap.add_argument("--below", type=float)
    ap.add_argument("--at")
    ap.add_argument("--note", default="")
    ap.add_argument("--from-plan", action="store_true")
    ap.add_argument("--fired", action="store_true", help="clear only alerts that already rang")
    ap.add_argument("--every", type=int, default=60)
    args = ap.parse_args()
    store = load()
    if args.cmd == "add":
        cmd_add(args, store)
    elif args.cmd == "check":
        cmd_check(store)
    elif args.cmd == "watch":
        while True:
            cmd_check(store, quiet=True)
            armed = [a for a in store["alerts"] if not a["fired"]]
            if not armed or now() >= at_today("15:30") or os.environ.get("DALAL_NOW"):
                print("watch done:", "all alerts rang" if not armed else "market closed")
                break
            time.sleep(max(15, args.every))
    elif args.cmd == "list":
        if not store["alerts"]:
            print("no alerts")
        for a in store["alerts"]:
            print(f"{a['id']} [{'rang ' + a['fired'][11:16] if a['fired'] else 'armed'}] {describe(a)}")
    else:
        store["alerts"] = [a for a in store["alerts"] if not a["fired"]] if args.fired else []
        write_state("alerts.json", store)
        print("cleared")


if __name__ == "__main__":
    main()

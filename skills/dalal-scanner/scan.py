#!/usr/bin/env python3
"""Chart Scanner: scan NSE stocks for intraday setups.

  scan.py universe [--source nifty500|nifty100|all]   build dalal/universe.json
  scan.py daily [--top 25] [--symbols A,B]             end-of-day / pre-market setups -> watchlist
  scan.py orb [--at HH:MM] [--side long|short|both]    opening-range breakouts so far today
"""
import argparse
import datetime as dt
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_dalal"))

from core import at_today, die, load_config, now, read_state, write_state, norm_symbol  # noqa: E402
from data import DataError, by_day, chart, session_bars  # noqa: E402
from indicators import orb_trigger, rsi, bar_minutes, completed  # noqa: E402
from universe import build_universe, load_universe  # noqa: E402

WORKERS = 6


def pick_symbols(args, cfg, prefer_watchlist=False):
    if args.symbols:
        return [norm_symbol(s) for s in args.symbols.split(",") if s.strip()]
    if prefer_watchlist:
        wl = read_state("watchlist.json")
        if wl and wl.get("symbols"):
            return wl["symbols"]
    uni = load_universe(cfg["universe"])
    allowed = set(cfg["allow_series"])
    return [s["symbol"] for s in uni["symbols"] if s.get("series", "EQ") in allowed]


def run_pool(fn, symbols):
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fn, s): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                r = f.result()
                if r:
                    results.append(r)
            except (DataError, ValueError, KeyError, IndexError, ZeroDivisionError) as e:
                errors.append(f"{s}: {e}")
    return results, errors


# ---------------------------------------------------------------- daily

def daily_one(sym, cfg):
    bars = chart(sym, "1d", "1y")["bars"]
    if len(bars) < 30:
        return None
    closes = [b["c"] for b in bars]
    last, prev = bars[-1], bars[-2]
    turnover_cr = sum(b["c"] * b["v"] for b in bars[-21:-1]) / 20 / 1e7
    if last["c"] < cfg["min_price"] or turnover_cr < cfg["min_avg_turnover_cr"]:
        return None
    avg_vol = sum(b["v"] for b in bars[-21:-1]) / 20 or 1
    setups = []
    hi20 = max(b["h"] for b in bars[-21:-1])
    if last["c"] > hi20:
        setups.append("breakout_20d")
    hi52 = max(b["h"] for b in bars[-252:])
    if last["c"] >= 0.97 * hi52:
        setups.append("near_52w_high")
    r_now, r_prev = rsi(closes), rsi(closes[:-1])
    if r_prev is not None and r_prev < 32 and last["c"] > prev["c"]:
        setups.append("oversold_bounce")
    if last["v"] > 2 * avg_vol:
        setups.append("volume_spike")
    if last["h"] < prev["h"] and last["l"] > prev["l"]:
        setups.append("inside_day")
    ranges = [b["h"] - b["l"] for b in bars[-7:]]
    if ranges[-1] == min(ranges):
        setups.append("nr7")
    gap = (last["o"] / prev["c"] - 1) * 100
    if abs(gap) >= 2:
        setups.append("gap_up" if gap > 0 else "gap_down")
    if not setups:
        return None
    return {"symbol": sym, "close": round(last["c"], 2), "change_pct": round((last["c"] / prev["c"] - 1) * 100, 2),
            "gap_pct": round(gap, 2), "rsi": round(r_now, 1) if r_now else None,
            "vol_ratio": round(last["v"] / avg_vol, 2), "turnover_cr": round(turnover_cr, 1),
            "setups": setups, "score": len(setups) + (1 if "volume_spike" in setups else 0)}


def cmd_daily(args, cfg):
    syms = pick_symbols(args, cfg)
    res, errs = run_pool(lambda s: daily_one(s, cfg), syms)
    res.sort(key=lambda r: (-r["score"], -r["turnover_cr"]))
    top = res[: args.top]
    out = {"mode": "daily", "time": now().isoformat(timespec="minutes"), "scanned": len(syms),
           "matched": len(res), "errors": len(errs), "candidates": top}
    write_state("scan_daily.json", out)
    write_state("watchlist.json", {"time": out["time"], "source": "scan daily",
                                   "symbols": [r["symbol"] for r in top]})
    print(f"Scanned {len(syms)} stocks, {len(res)} with setups ({len(errs)} fetch errors). Top {len(top)}:")
    print(f"{'symbol':<14}{'close':>10}{'chg%':>7}{'gap%':>7}{'rsi':>6}{'vol x':>7}{'turn Cr':>9}  setups")
    for r in top:
        print(f"{r['symbol']:<14}{r['close']:>10.2f}{r['change_pct']:>7.2f}{r['gap_pct']:>7.2f}"
              f"{(r['rsi'] or 0):>6.1f}{r['vol_ratio']:>7.2f}{r['turnover_cr']:>9.1f}  {', '.join(r['setups'])}")
    print("Watchlist saved to dalal/watchlist.json for the ORB scan.")
    if errs and args.verbose:
        print("\n".join(errs[:20]), file=sys.stderr)


# ---------------------------------------------------------------- orb

def orb_one(sym, cfg, at, sides):
    data = chart(sym, "5m", "5d")
    days = by_day(data["bars"])
    if not days:
        return None
    today = at.date()
    if today not in days:
        return None
    tb = session_bars(days[today])
    m = bar_minutes(tb)
    done = completed(tb, at, m)
    if not done:
        return None
    prior = [session_bars(v) for d, v in days.items() if d < today]
    prev_close = prior[-1][-1]["c"] if prior and prior[-1] else data.get("prev_close")
    found = None
    for side in sides:
        orr, trig = orb_trigger(tb, cfg["orb_minutes"], side, cfg["entry_window"], at)
        if orr and trig:
            found = (side, orr, trig)
            break
    if not found:
        return None
    side, orr, trig = found
    edge = orr["high"] if side == "long" else orr["low"]
    beyond = (trig["c"] / edge - 1) * 100 * (1 if side == "long" else -1)
    # Relative volume: today's volume to the trigger vs the same window on prior days
    cut = (trig["dt"] + dt.timedelta(minutes=m)).time()
    vol_today = sum(b["v"] for b in tb if (b["dt"] + dt.timedelta(minutes=m)).time() <= cut)
    past = [sum(b["v"] for b in d if (b["dt"] + dt.timedelta(minutes=m)).time() <= cut) for d in prior if d]
    rvol = vol_today / (sum(past) / len(past)) if past and sum(past) else None
    last = done[-1]["c"]
    return {"symbol": sym, "side": side, "or_high": round(orr["high"], 2), "or_low": round(orr["low"], 2),
            "trigger_time": (trig["dt"] + dt.timedelta(minutes=m)).strftime("%H:%M"),  # when the bar closed
            "trigger_close": round(trig["c"], 2), "pct_beyond": round(beyond, 2),
            "last": round(last, 2), "or_width_pct": round((orr["high"] / orr["low"] - 1) * 100, 2),
            "day_change_pct": round((last / prev_close - 1) * 100, 2) if prev_close else None,
            "rvol": round(rvol, 2) if rvol else None}


def cmd_orb(args, cfg):
    at = at_today(args.at) if args.at else now()
    if at.time() < (dt.datetime.combine(at.date(), dt.time(9, 15)) +
                    dt.timedelta(minutes=cfg["orb_minutes"])).time():
        die(f"the {cfg['orb_minutes']}-minute opening range is not complete yet at {at:%H:%M}")
    sides = {"long": ["long"], "short": ["short"], "both": ["long", "short"]}[args.side]
    if "short" in sides and not cfg["allow_short"]:
        print("note: shorts are off (allow_short=false in config); scanning longs only.")
        sides = ["long"]
    syms = pick_symbols(args, cfg, prefer_watchlist=not args.all)
    res, errs = run_pool(lambda s: orb_one(s, cfg, at, sides), syms)
    res.sort(key=lambda r: (-(r["rvol"] or 0), -r["pct_beyond"]))
    out = {"mode": "orb", "at": at.isoformat(timespec="minutes"), "orb_minutes": cfg["orb_minutes"],
           "scanned": len(syms), "errors": len(errs), "candidates": res}
    write_state("scan.json", out)
    print(f"{at:%a %d %b %Y %H:%M} IST: {len(res)} of {len(syms)} stocks have closed a 5-minute bar beyond "
          f"their {cfg['orb_minutes']}-minute opening range ({len(errs)} fetch errors).")
    if res:
        print(f"{'symbol':<14}{'side':<6}{'OR low':>10}{'OR high':>10}{'trigger':>9}{'close':>10}"
              f"{'beyond%':>9}{'rvol':>6}{'day%':>7}")
    for r in res[: args.top]:
        print(f"{r['symbol']:<14}{r['side']:<6}{r['or_low']:>10.2f}{r['or_high']:>10.2f}{r['trigger_time']:>9}"
              f"{r['trigger_close']:>10.2f}{r['pct_beyond']:>9.2f}{(r['rvol'] or 0):>6.2f}"
              f"{(r['day_change_pct'] or 0):>7.2f}")
    if errs and args.verbose:
        print("\n".join(errs[:20]), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("universe")
    u.add_argument("--source", default=None, choices=["nifty500", "nifty100", "all"])
    d = sub.add_parser("daily")
    d.add_argument("--top", type=int, default=25)
    d.add_argument("--symbols")
    d.add_argument("-v", "--verbose", action="store_true")
    o = sub.add_parser("orb")
    o.add_argument("--at", help="HH:MM IST (default: now)")
    o.add_argument("--side", default="long", choices=["long", "short", "both"])
    o.add_argument("--symbols")
    o.add_argument("--all", action="store_true", help="scan the whole universe, not the watchlist")
    o.add_argument("--top", type=int, default=30)
    o.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    try:
        if args.cmd == "universe":
            uni = build_universe(args.source or cfg["universe"])
            print(f"{len(uni['symbols'])} symbols from {uni['source']} saved to dalal/universe.json")
        elif args.cmd == "daily":
            cmd_daily(args, cfg)
        else:
            cmd_orb(args, cfg)
    except DataError as e:
        die(str(e))


if __name__ == "__main__":
    main()

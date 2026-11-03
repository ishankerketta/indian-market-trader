#!/usr/bin/env python3
"""Exit Planner: set the stop, the target and the flat-by time before you enter.

  exit.py plan [--stop or-mid|or-low|atr:1.5|pct:0.8|level] [--target 1.5R|2R|pct:1.2|level]
               [--entry PRICE] [--write]

Reads trader/entry.json (from the Entry Timer). Writes trader/plan.json with --write.
"""
import argparse
import math
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "_shared" if (_HERE / "_shared").is_dir() else _HERE.parent / "_shared"))

from core import die, load_config, now, read_state, write_state  # noqa: E402
from costs import per_share_cost  # noqa: E402
from data import DataError, chart  # noqa: E402
from indicators import atr, round_tick, stop_price, target_price  # noqa: E402
from sr import all_lines, nearest  # noqa: E402


def build_plan(entry, cfg, stop_rule, target_rule, entry_price=None):
    side = entry["side"]
    long_ = side == "long"
    # Plan from where the stock is now (the Entry Timer already refused it if it ran past the
    # chase limit), not from the trigger close it may have left behind.
    if entry_price:
        px = float(entry_price)
    elif long_:
        px = max(float(entry["trigger_price"]), float(entry.get("last") or 0))
    else:
        px = min(float(entry["trigger_price"]), float(entry.get("last") or entry["trigger_price"]))
    orr = {"high": entry["or_high"], "low": entry["or_low"]}
    a = None
    if stop_rule.startswith("atr:"):
        bars = chart(entry["symbol"], "5m", "5d")["bars"]
        a = atr(bars[-80:], 14)
    tick = cfg.get("tick_size")
    lv_note = []
    if stop_rule == "level" or target_rule == "level":
        lines, tol = level_lines(entry["symbol"])
        sup, res = nearest(lines, px)
    if stop_rule == "level":
        lvl = sup if long_ else res
        if not lvl:
            raise ValueError(f"no level {'below' if long_ else 'above'} {px} in today's levels.json")
        raw_stop = lvl["price"] - tol if long_ else lvl["price"] + tol   # just beyond the band
        lv_note.append(f"stop beyond {lvl['tier']} {lvl['price']}")
    else:
        raw_stop = stop_price(stop_rule, side, px, orr, a)
    stop = round_tick(raw_stop, "down" if long_ else "up", tick)
    if (long_ and stop >= px) or (not long_ and stop <= px):
        raise ValueError(f"stop {stop} is on the wrong side of entry {px}; pick another stop rule")
    if target_rule == "level":
        lvl = res if long_ else sup
        if not lvl:
            raise ValueError(f"no {'resistance above' if long_ else 'support below'} {px}: price is beyond every "
                             f"line (a 4-week {'high' if long_ else 'low'}). Use an R-multiple target instead.")
        raw_target = lvl["price"] - 0.5 * tol if long_ else lvl["price"] + 0.5 * tol   # get out before the wall
        lv_note.append(f"target in front of {lvl['tier']} {lvl['price']}")
    else:
        raw_target = target_price(target_rule, side, px, stop)
    target = round_tick(raw_target, "down" if long_ else "up", tick)
    if (long_ and target <= px) or (not long_ and target >= px):
        raise ValueError(f"target {target} is not beyond entry {px}; the nearest level is too close")
    risk = abs(px - stop)
    reward = abs(target - px)
    est_qty = max(1, math.floor(cfg["max_loss_per_trade"] / risk)) if risk else 1
    cps = per_share_cost(px, est_qty, cfg["broker_profile"], cfg["rates"])
    rr_net = (reward - cps) / (risk + cps) if risk + cps else 0
    return {
        "symbol": entry["symbol"], "side": side, "setup": entry.get("setup", "orb"),
        "entry": round(px, 2), "trigger_price": entry["trigger_price"], "stop": stop, "target": target,
        "stop_rule": stop_rule, "target_rule": target_rule,
        "risk_per_share": round(risk, 2), "reward_per_share": round(reward, 2),
        "cost_per_share_est": round(cps, 3),
        "rr_gross": round(reward / risk, 2) if risk else None, "rr_net": round(rr_net, 2),
        "or_high": entry["or_high"], "or_low": entry["or_low"], "orb_minutes": entry.get("orb_minutes", 15),
        "trigger_time": entry.get("trigger_time"), "flat_by": cfg["flat_by"],
        "atr_5m": round(a, 2) if a else None, "planned_at": now().isoformat(timespec="minutes"),
        # Rules the Time Machine can replay on past days (levels are today's, so use the same distances)
        "hist_stop_rule": f"pct:{risk / px * 100:.4f}" if stop_rule == "level" else stop_rule,
        "hist_target_rule": f"{reward / risk:.3f}R" if target_rule == "level" and risk else target_rule,
        "level_notes": lv_note,
    }


def level_lines(symbol):
    """Today's lines for this symbol from /india-levels, with the major tolerance band."""
    store = read_state("levels.json") or {}
    lv = store.get(symbol)
    if not lv or lv.get("time", "")[:10] != now().date().isoformat():
        raise ValueError(f"no levels for {symbol} today: run /india-levels {symbol} first")
    return all_lines(lv), lv.get("tolerance", 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "show"])
    ap.add_argument("--stop", default="or-mid")
    ap.add_argument("--target", default="1.5R")
    ap.add_argument("--entry", type=float, help="override the entry price")
    ap.add_argument("--force", action="store_true", help="plan even if the entry is not triggered")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    if args.cmd == "show":
        p = read_state("plan.json") or die("no trader/plan.json yet")
        print_plan(p)
        return
    entry = read_state("entry.json") or die("no trader/entry.json - run the Entry Timer first")
    if entry.get("status") != "triggered" and not args.force:
        die(f"{entry['symbol']} is {entry.get('status')}, not triggered ({entry.get('reason')}). "
            "Use --force to plan anyway.")
    if "or_high" not in entry:
        die("entry.json has no opening range yet")
    try:
        plan = build_plan(entry, cfg, args.stop, args.target, args.entry)
    except (ValueError, DataError) as e:
        die(str(e))
    print_plan(plan)
    if args.write:
        write_state("plan.json", plan)
        print("Saved trader/plan.json")


def print_plan(p):
    long_ = p["side"] == "long"
    print(f"{p['symbol']} {p['side'].upper()} plan")
    print(f"  entry  {p['entry']:>10.2f}")
    print(f"  stop   {p['stop']:>10.2f}  ({p['stop_rule']}, {p['risk_per_share']:.2f}/share at risk)")
    print(f"  target {p['target']:>10.2f}  ({p['target_rule']}, {p['reward_per_share']:.2f}/share)")
    print(f"  flat by {p['flat_by']} IST either way")
    for n in p.get("level_notes", []):
        print(f"  levels: {n}")
    print(f"  reward:risk {p['rr_gross']} gross, {p['rr_net']} after ~{p['cost_per_share_est']:.2f}/share charges")
    if p["risk_per_share"] and p["cost_per_share_est"] > 0.25 * p["risk_per_share"]:
        share = 100 * p["cost_per_share_est"] / p["risk_per_share"]
        print(f"  !! charges are {share:.0f}% of the risk per share: this stop is too tight for intraday "
              "costs. Consider a wider stop (or-low, atr:1.5) and a smaller position.")
    if not long_:
        print("  (short: stop is above entry, target below)")


if __name__ == "__main__":
    main()

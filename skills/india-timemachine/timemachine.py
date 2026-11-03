#!/usr/bin/env python3
"""Time Machine: replay the rest of the session thousands of times before you risk a rupee.

  timemachine.py run [--sims 10000] [--seed 42] [--lookback 59] [--write]

Reads trader/plan.json. Two checks, both net of charges:
 1. Simulation: each remaining 5-minute candle is drawn from the stock's own
    candles at that time of day over the last N sessions, stacked from the entry.
 2. History: the same rule (opening-range breakout, same stop and target rules)
    re-run on each of those N real sessions.
"""
import argparse
import datetime as dt
import math
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_shared"))

from core import at_today, die, load_config, now, read_state, write_state, parse_hhmm  # noqa: E402
from costs import per_share_cost  # noqa: E402
from data import DataError, by_day, chart, session_bars  # noqa: E402
from indicators import bar_minutes, orb_trigger, stop_price, target_price  # noqa: E402


def walk(bars_iter, side, entry, stop, target):
    """Exit logic shared by the simulation and the history test.

    bars_iter yields (o, h, l, c). Returns (outcome, exit_price). Gaps through a level
    fill at the open. If one bar touches both levels, assume the stop came first.
    """
    long_ = side == "long"
    last_c = entry
    for o, h, l, c in bars_iter:
        if long_:
            if o <= stop:
                return "stop", o
            if o >= target:
                return "target", o
            hit_s, hit_t = l <= stop, h >= target
        else:
            if o >= stop:
                return "stop", o
            if o <= target:
                return "target", o
            hit_s, hit_t = h >= stop, l <= target
        if hit_s:
            return "stop", stop
        if hit_t:
            return "target", target
        last_c = c
    return "flat", last_c


def slot_key(b):
    return b["dt"].strftime("%H:%M")


def build_pools(hist_days):
    """slot 'HH:MM' -> list of (gap, h/o, l/o, c/o) from each historical day."""
    pools = {}
    for bars in hist_days:
        prev_c = None
        for b in bars:
            if prev_c is None:
                prev_c = b["o"]
            o = b["o"]
            if o <= 0 or prev_c <= 0:
                continue
            pools.setdefault(slot_key(b), []).append((o / prev_c, b["h"] / o, b["l"] / o, b["c"] / o))
            prev_c = b["c"]
    return pools


def remaining_slots(start_after, flat_by, minutes):
    """Bar start times from the entry until the last bar that closes by flat_by."""
    slots = []
    t = start_after
    while t + dt.timedelta(minutes=minutes) <= flat_by:
        slots.append(t.strftime("%H:%M"))
        t += dt.timedelta(minutes=minutes)
    return slots


def vol_ratio(today_bars, pools, lo=0.5, hi=4.0):
    """How fast today is moving vs normal: today's average candle range so far divided by the
    historical average range for the same time slots. Clamped to [0.5, 4]. 1.0 if too early to tell.

    Seen live: on RELIANCE's results day, unscaled replays from normal sessions gave a 2R target
    0% odds; the stock closed beyond it.
    """
    pairs = []
    for b in today_bars:
        hist = pools.get(slot_key(b))
        if not hist or b["o"] <= 0:
            continue
        normal = statistics.fmean(hr - lr for _, hr, lr, _ in hist)
        if normal > 0:
            pairs.append(((b["h"] - b["l"]) / b["o"], normal))
    if len(pairs) < 3:
        return 1.0
    r = sum(p[0] for p in pairs) / sum(p[1] for p in pairs)
    return max(lo, min(hi, r))


def simulate(plan, pools, slots, sims, seed, scale=1.0):
    rng = random.Random(seed)
    side, entry, stop, target = plan["side"], plan["entry"], plan["stop"], plan["target"]
    usable = [s for s in slots if pools.get(s)]
    counts = {"target": 0, "stop": 0, "flat": 0}
    pnls = []
    long_ = side == "long"
    k = scale
    for _ in range(sims):
        def gen():
            px = entry
            for s in usable:
                g, hr, lr, cr = rng.choice(pools[s])
                # Stretch each candle's moves by today's volatility ratio
                o = px * (1 + (g - 1) * k)
                yield o, o * (1 + (hr - 1) * k), o * (1 + (lr - 1) * k), o * (1 + (cr - 1) * k)
                px = o * (1 + (cr - 1) * k)
        outcome, exit_px = walk(gen(), side, entry, stop, target)
        counts[outcome] += 1
        pnls.append((exit_px - entry) if long_ else (entry - exit_px))
    return counts, pnls, len(usable)


def history(plan, cfg, hist_days, flat_by_t, atr_value):
    side = plan["side"]
    out = []
    for bars in hist_days:
        orr, trig = orb_trigger(bars, plan.get("orb_minutes", cfg["orb_minutes"]), side, cfg["entry_window"])
        if not trig:
            continue
        e = trig["c"]
        try:
            s = stop_price(plan.get("hist_stop_rule", plan["stop_rule"]), side, e, orr, atr_value)
            t = target_price(plan.get("hist_target_rule", plan["target_rule"]), side, e, s)
        except ValueError:
            continue
        if (side == "long" and s >= e) or (side == "short" and s <= e):
            continue
        m = bar_minutes(bars)
        after = [b for b in bars if b["dt"] > trig["dt"] and (b["dt"] + dt.timedelta(minutes=m)).time() <= flat_by_t]
        outcome, x = walk(((b["o"], b["h"], b["l"], b["c"]) for b in after), side, e, s, t)
        risk = abs(e - s)
        pnl = (x - e) if side == "long" else (e - x)
        out.append({"date": bars[0]["dt"].date().isoformat(), "entry": round(e, 2), "stop": round(s, 2),
                    "target": round(t, 2), "outcome": outcome, "exit": round(x, 2),
                    "pnl_ps": round(pnl, 2), "risk_ps": round(risk, 2)})
    return out


def verdict(exp_r, n_hist, hist_exp_r):
    if exp_r is None:
        return "not enough data"
    basis = exp_r if hist_exp_r is None or n_hist < 10 else (exp_r + hist_exp_r) / 2
    if basis < -0.1:
        v = "negative edge after charges: the odds say skip it"
    elif basis < 0.1:
        v = "close to a coin flip after charges"
    elif basis < 0.3:
        v = "a slight edge on paper, thin enough that slippage could erase it"
    else:
        v = "positive on paper, but 60 sessions is a small sample and the future need not repeat them"
    if n_hist < 10:
        v += f" (history has only {n_hist} past signals, so lean on it lightly)"
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--lookback", type=int, default=59)
    ap.add_argument("--no-vol-scale", action="store_true", help="replay normal-day candles unscaled")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    plan = read_state("plan.json") or die("no trader/plan.json - run the Exit Planner with --write first")
    try:
        data = chart(plan["symbol"], "5m", "60d")
    except DataError as e:
        die(str(e))
    days = by_day(data["bars"])
    today = now().date()
    hist = [session_bars(v) for d, v in days.items() if d < today][-args.lookback:]
    hist = [h for h in hist if len(h) >= 20]
    if len(hist) < 10:
        die(f"only {len(hist)} past sessions of 5-minute bars available; need at least 10")
    minutes = bar_minutes(hist[-1])
    flat_by = at_today(plan.get("flat_by", cfg["flat_by"]))
    trig = plan.get("trigger_time")
    start = at_today(trig) if trig else now()
    slots = remaining_slots(start, flat_by, minutes)
    if not slots:
        die("no time left before flat-by for the trade to play out")
    pools = build_pools(hist)
    today_done = [b for b in session_bars(days.get(today, [])) if b["dt"] + dt.timedelta(minutes=minutes) <= start]
    vr = 1.0 if args.no_vol_scale else vol_ratio(today_done, pools)
    counts, pnls, used = simulate(plan, pools, slots, args.sims, args.seed, vr)
    plain = None
    if abs(vr - 1) >= 0.25:
        pc, _, _ = simulate(plan, pools, slots, min(args.sims, 3000), args.seed, 1.0)
        plain = {k: round(100 * v / min(args.sims, 3000), 1) for k, v in pc.items()}
    risk = plan["risk_per_share"]
    est_qty = max(1, math.floor(cfg["max_loss_per_trade"] / risk)) if risk else 1
    cps = per_share_cost(plan["entry"], est_qty, cfg["broker_profile"], cfg["rates"])
    net = [p - cps for p in pnls]
    exp_ps = statistics.fmean(net)
    exp_r = exp_ps / risk if risk else None
    pct = {k: round(100 * v / args.sims, 1) for k, v in counts.items()}
    q = statistics.quantiles(net, n=20)
    hist_rows = history(plan, cfg, hist, flat_by.time(), plan.get("atr_5m"))
    h_counts = {k: sum(1 for r in hist_rows if r["outcome"] == k) for k in ("target", "stop", "flat")}
    h_net_r = [(r["pnl_ps"] - cps) / r["risk_ps"] for r in hist_rows if r["risk_ps"]]
    h_exp_r = statistics.fmean(h_net_r) if h_net_r else None
    v = verdict(exp_r, len(hist_rows), h_exp_r)
    if vr >= 2:
        v += (f"; today is moving at {vr:.1f}x its normal pace (an event day?), so 60 ordinary "
              "sessions are a weak guide and both targets and stops come faster")
    out = {
        "symbol": plan["symbol"], "side": plan["side"], "entry": plan["entry"], "stop": plan["stop"],
        "target": plan["target"], "flat_by": plan.get("flat_by"), "sims": args.sims, "seed": args.seed,
        "sessions": len(hist), "slots": used, "cost_per_share": round(cps, 3), "vol_ratio": round(vr, 2),
        "sim_pct_unscaled": plain,
        "sim_pct": pct, "sim_exp_per_share_net": round(exp_ps, 3),
        "sim_exp_R_net": round(exp_r, 3) if exp_r is not None else None,
        "sim_p5_p95_per_share": [round(q[0], 2), round(q[-1], 2)],
        "history_signals": len(hist_rows), "history_counts": h_counts,
        "history_exp_R_net": round(h_exp_r, 3) if h_exp_r is not None else None,
        "history": hist_rows, "verdict": v, "ran_at": now().isoformat(timespec="minutes"),
    }
    print(f"Time Machine: {plan['symbol']} {plan['side']} from {plan['entry']} "
          f"(stop {plan['stop']}, target {plan['target']}, flat by {plan.get('flat_by')})")
    print(f"  {args.sims:,} replays of the remaining {used} candles, drawn from {len(hist)} past sessions (seed {args.seed}):")
    if vr != 1.0:
        print(f"    today is moving at {vr:.2f}x its normal pace for this time of day; replayed candles are scaled to match")
    print(f"    target first {pct['target']}%, stop first {pct['stop']}%, still open at flat-by {pct['flat']}%")
    if plain:
        print(f"    (unscaled normal-day candles would say: target {plain['target']}%, stop {plain['stop']}%, "
              f"open {plain['flat']}%)")
    print(f"    average result {exp_ps:+.2f}/share after ~{cps:.2f}/share charges = {exp_r:+.2f}R")
    print(f"    90% of replays land between {q[0]:+.2f} and {q[-1]:+.2f} per share")
    print(f"  History: the same rule fired on {len(hist_rows)} of {len(hist)} past sessions: "
          f"{h_counts['target']} target, {h_counts['stop']} stop, {h_counts['flat']} neither"
          + (f"; average {h_exp_r:+.2f}R net" if h_exp_r is not None else ""))
    print(f"  Verdict: {v}.")
    print("  A simulation built from the last 60 days, scaled to today's pace, not a prediction: results, halts and "
          "news can do what those days never did.")
    if args.write:
        write_state("sim.json", out)
        print("Saved trader/sim.json")


if __name__ == "__main__":
    main()

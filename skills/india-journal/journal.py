#!/usr/bin/env python3
"""Trading Journal: what your paper (and logged live) trades actually say, net of charges.

  journal.py [--source paper|live|all]

Win rate, average win and loss, profit factor, expectancy in rupees and in R, charges as a share of
gross profit, max drawdown, losing streaks, results by outcome, weekday and entry hour, rule
breaks, and a go-live readiness check on the paper record. Writes trader/journal.json.

Idea from claude-trading-skills-india's trading-discipline (MIT); written fresh for this pack.
"""
import argparse
import datetime as dt
import pathlib
import statistics
import sys
from collections import defaultdict

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "_shared" if (_HERE / "_shared").is_dir() else _HERE.parent / "_shared"))

from core import fmt_inr, load_config, now, read_state, write_state  # noqa: E402


def enrich(trades, orders):
    """Attach risk per share (for R) and the entry hour from the original ticket."""
    by_id = {o["id"]: o for o in orders}
    for t in trades:
        o = by_id.get(t["id"], {})
        risk = t.get("risk_ps") or (abs(o["limit"] - o["stop"]) if o.get("limit") and o.get("stop") else None)
        t["risk_rs"] = risk * t["qty"] if risk else None
        t["r"] = t["net_pnl"] / t["risk_rs"] if t.get("risk_rs") else None
        created = o.get("created") or ""
        t["hour"] = created[11:13] or "?"
        t["setup"] = t.get("setup") or o.get("setup") or "orb"
    return trades


def stats(trades, cfg):
    if not trades:
        return None
    net = [t["net_pnl"] for t in trades]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    gross_profit = sum(t["gross_pnl"] for t in trades if t["gross_pnl"] > 0)
    charges = sum(t["charges"] for t in trades)
    eq, peak, mdd = 0.0, 0.0, 0.0
    streak = worst = 0
    for x in net:
        eq += x
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
        streak = streak + 1 if x <= 0 else 0
        worst = max(worst, streak)
    rs = [t["r"] for t in trades if t.get("r") is not None]
    days = defaultdict(list)
    for t in trades:
        days[t["date"]].append(t)
    over_count = [d for d, ts in days.items() if len(ts) > cfg["max_trades_per_day"]]
    over_loss = [d for d, ts in days.items() if -sum(x["net_pnl"] for x in ts) > cfg["daily_loss_limit"]]

    def group(key):
        g = defaultdict(list)
        for t in trades:
            g[key(t)].append(t["net_pnl"])
        return {k: {"n": len(v), "net": round(sum(v), 2), "win_rate": round(100 * sum(1 for x in v if x > 0) / len(v))}
                for k, v in sorted(g.items())}
    return {
        "trades": len(trades), "days": len(days), "net": round(sum(net), 2),
        "win_rate": round(100 * len(wins) / len(net), 1),
        "avg_win": round(statistics.fmean(wins), 2) if wins else 0.0,
        "avg_loss": round(statistics.fmean(losses), 2) if losses else 0.0,
        "profit_factor": (round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses)
                          else ("no losses yet" if wins else None)),
        "expectancy": round(statistics.fmean(net), 2),
        "expectancy_r": round(statistics.fmean(rs), 3) if rs else None,
        "charges": round(charges, 2),
        "charges_pct_of_gross_profit": round(100 * charges / gross_profit, 1) if gross_profit else None,
        "max_drawdown": round(mdd, 2), "worst_losing_streak": worst,
        "by_outcome": group(lambda t: t.get("outcome", "?")),
        "by_weekday": group(lambda t: dt.date.fromisoformat(t["date"]).strftime("%a")),
        "by_hour": group(lambda t: t["hour"] + ":00"),
        "by_setup": group(lambda t: t["setup"]),
        "days_over_trade_limit": over_count, "days_over_loss_limit": over_loss,
    }


def readiness(s, cfg):
    if not s:
        return [("paper trades recorded", False, "none yet")], False
    checks = [
        ("at least 20 paper trades", s["trades"] >= 20, f"{s['trades']}"),
        ("across at least 10 trading days", s["days"] >= 10, f"{s['days']}"),
        ("positive expectancy after charges", (s["expectancy"] or 0) > 0, f"{fmt_inr(s['expectancy'])} per trade"
         + (f", {s['expectancy_r']:+.2f}R" if s.get("expectancy_r") is not None else "")),
        ("profit factor at least 1.2", s["profit_factor"] == "no losses yet" or
         (isinstance(s["profit_factor"], float) and s["profit_factor"] >= 1.2), f"{s['profit_factor']}"),
        ("max drawdown within 2x the daily loss limit", s["max_drawdown"] <= 2 * cfg["daily_loss_limit"],
         f"{fmt_inr(s['max_drawdown'])} vs {fmt_inr(2 * cfg['daily_loss_limit'])}"),
        ("no days over the trade-count limit", not s["days_over_trade_limit"], f"{len(s['days_over_trade_limit'])} day(s)"),
        ("no days over the daily loss limit", not s["days_over_loss_limit"], f"{len(s['days_over_loss_limit'])} day(s)"),
    ]
    return checks, all(c[1] for c in checks)


def show(title, s):
    print(f"\n{title}: {s['trades']} trades over {s['days']} days, net {fmt_inr(s['net'])}")
    print(f"  win rate {s['win_rate']}%  avg win {fmt_inr(s['avg_win'])}  avg loss {fmt_inr(s['avg_loss'])}  "
          f"profit factor {s['profit_factor']}")
    print(f"  expectancy {fmt_inr(s['expectancy'])} per trade"
          + (f" ({s['expectancy_r']:+.2f}R)" if s.get("expectancy_r") is not None else ""))
    print(f"  charges {fmt_inr(s['charges'])}"
          + (f" = {s['charges_pct_of_gross_profit']}% of gross profit" if s.get("charges_pct_of_gross_profit") else ""))
    print(f"  max drawdown {fmt_inr(s['max_drawdown'])}, worst losing streak {s['worst_losing_streak']}")
    for name in ("by_outcome", "by_weekday", "by_hour"):
        parts = ", ".join(f"{k} {v['n']}x {fmt_inr(v['net'])}" for k, v in s[name].items())
        print(f"  {name.replace('by_', 'by ')}: {parts}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="all", choices=["paper", "live", "all"])
    args = ap.parse_args()
    cfg = load_config()
    orders = (read_state("orders.json") or {}).get("orders", [])
    paper = enrich(list((read_state("paper_ledger.json") or {}).get("closed", [])), orders)
    live = enrich(list((read_state("live_ledger.json") or {}).get("closed", [])), orders)
    out = {"time": now().isoformat(timespec="minutes")}
    sp = stats(paper, cfg) if args.source in ("paper", "all") else None
    sl = stats(live, cfg) if args.source in ("live", "all") else None
    if not sp and not sl:
        print("No closed trades yet. Paper trade with /india-broker (approve, then sync), or log live trades "
              "with `ticket.py record-exit`.")
    if sp:
        show("Paper", sp)
        out["paper"] = sp
    if sl:
        show("Live", sl)
        out["live"] = sl
    if args.source in ("paper", "all"):
        checks, ready = readiness(sp, cfg)
        out["readiness"] = {"ready": ready, "checks": [{"check": c, "ok": ok, "detail": d} for c, ok, d in checks]}
        print("\nGo-live readiness (paper record)")
        for c, ok, d in checks:
            print(f"  [{' ok ' if ok else 'FAIL'}] {c}: {d}")
        print("  Verdict: " + ("meets the minimum bar. Still a small sample: start live with the smallest size."
                               if ready else "not ready for live money yet. Keep paper trading."))
    write_state("journal.json", out)
    print("\nSaved trader/journal.json")


if __name__ == "__main__":
    main()

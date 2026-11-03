#!/usr/bin/env python3
"""Charges Calculator: what an intraday round trip really costs on NSE.

  charges.py --buy 2450 --sell 2470 --qty 40 [--profile discount|flat20|zero|full_service]
  charges.py --buy 2450 --qty 40 --breakeven      lowest sell price that covers all charges
  charges.py --from-plan                           costs at the plan's stop and target
"""
import argparse
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_shared"))

from core import die, fmt_inr, load_config, read_state  # noqa: E402
from costs import PROFILES, breakeven_sell, intraday_charges  # noqa: E402

ROWS = [("brokerage", "Brokerage"), ("stt", "STT (0.025% sell)"), ("exchange", "NSE transaction"),
        ("ipft", "IPFT"), ("sebi", "SEBI fee"), ("stamp", "Stamp duty (buy)"), ("gst", "GST 18%")]


def table(c, title):
    print(title)
    for k, label in ROWS:
        print(f"  {label:<20}{fmt_inr(c[k]):>14}")
    print(f"  {'Total charges':<20}{fmt_inr(c['total']):>14}")
    print(f"  {'Gross P&L':<20}{fmt_inr(c['gross_pnl']):>14}")
    print(f"  {'Net P&L':<20}{fmt_inr(c['net_pnl']):>14}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--buy", type=float)
    ap.add_argument("--sell", type=float)
    ap.add_argument("--qty", type=int)
    ap.add_argument("--profile", choices=list(PROFILES))
    ap.add_argument("--breakeven", action="store_true")
    ap.add_argument("--from-plan", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    profile = args.profile or cfg["broker_profile"]
    rates = cfg["rates"]
    if args.from_plan:
        p = read_state("plan.json") or die("no trader/plan.json")
        orders = read_state("orders.json") or {}
        qty = args.qty or next((o["qty"] for o in orders.get("orders", []) if o["symbol"] == p["symbol"]), None) \
            or max(1, math.floor(cfg["max_loss_per_trade"] / p["risk_per_share"]))
        long_ = p["side"] == "long"
        for name, px in (("at the target", p["target"]), ("at the stop", p["stop"])):
            b, s = (p["entry"], px) if long_ else (px, p["entry"])
            table(intraday_charges(b, s, qty, profile, rates), f"{p['symbol']} x {qty} exit {name} ({px}):")
        be = breakeven_sell(p["entry"], qty, profile, rates)
        print(f"Breakeven sell price for a long from {p['entry']}: {be} "
              f"({(be / p['entry'] - 1) * 100:.3f}% move just to cover charges)")
        return
    if args.buy is None or not args.qty:
        die("give --buy and --qty (and --sell, or --breakeven)")
    if args.breakeven or args.sell is None:
        be = breakeven_sell(args.buy, args.qty, profile, rates)
        print(f"Buy {args.qty} at {args.buy}: breakeven sell {be} "
              f"(+{be - args.buy:.2f}/share, {(be / args.buy - 1) * 100:.3f}%) on the {profile} profile")
        if args.sell is None:
            return
    table(intraday_charges(args.buy, args.sell, args.qty, profile, rates),
          f"Buy {args.qty} at {args.buy}, sell at {args.sell} ({profile} brokerage):")
    print("Rates are 2026 statutory figures; check your contract note and set overrides in trader/config.json.")


if __name__ == "__main__":
    main()

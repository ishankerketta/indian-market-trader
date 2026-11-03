#!/usr/bin/env python3
"""Budget Manager: size the position to your capital and your max loss per trade, charges included.

  size.py [--capital 100000] [--max-loss 500] [--write]

Reads trader/plan.json and trader/config.json. Writes one bracket order to trader/orders.json.
"""
import argparse
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_shared"))

from core import die, fmt_inr, load_config, now, read_state, write_state  # noqa: E402
from costs import intraday_charges  # noqa: E402
from indicators import round_tick  # noqa: E402


def loss_at_stop(side, entry, stop, qty, cfg):
    b, s = (entry, stop) if side == "long" else (stop, entry)
    return -intraday_charges(b, s, qty, cfg["broker_profile"], cfg["rates"])["net_pnl"]


def size(plan, cfg, capital, max_loss, cash=None):
    side = plan["side"]
    long_ = side == "long"
    buf = cfg["entry_buffer_pct"] / 100
    limit = round_tick(plan["entry"] * (1 + buf if long_ else 1 - buf), "up" if long_ else "down",
                       cfg.get("tick_size"))
    risk = abs(limit - plan["stop"])
    if risk <= 0:
        raise ValueError("limit price is at or beyond the stop")
    qty = math.floor(max_loss / risk)
    while qty > 0 and loss_at_stop(side, limit, plan["stop"], qty, cfg) > max_loss:
        qty -= 1
    lev = cfg["mis_leverage"] if cfg["use_leverage"] else 1
    cap_value = capital * cfg["max_position_pct"] / 100 * lev
    notes = []
    if qty * limit > cap_value:
        qty = math.floor(cap_value / limit)
        notes.append(f"capped by max_position_pct ({cfg['max_position_pct']}% of capital"
                     + (f" x {lev} leverage" if lev > 1 else "") + ")")
    margin = qty * limit / lev
    if cash is not None and margin > cash:
        qty = math.floor(cash * lev / limit)
        margin = qty * limit / lev
        notes.append("capped by available cash")
    if qty <= 0:
        raise ValueError(f"budget too small: one share risks {fmt_inr(risk)} plus charges against a "
                         f"{fmt_inr(max_loss)} limit, or the price is above your position cap")
    b, s = (limit, plan["target"]) if long_ else (plan["target"], limit)
    win = intraday_charges(b, s, qty, cfg["broker_profile"], cfg["rates"])
    loss = loss_at_stop(side, limit, plan["stop"], qty, cfg)
    ts = now()
    return {
        "id": f"{plan['symbol']}-{ts:%Y%m%d-%H%M}", "symbol": plan["symbol"], "exchange": "NSE",
        "side": "BUY" if long_ else "SELL", "direction": side, "qty": qty, "product": "MIS",
        "order_type": cfg["order_type"], "limit": limit, "stop": plan["stop"], "target": plan["target"],
        "flat_by": plan.get("flat_by", cfg["flat_by"]), "value": round(qty * limit, 2),
        "margin_needed": round(margin, 2), "leverage": lev,
        "est_loss_at_stop": round(loss, 2), "est_profit_at_target": win["net_pnl"],
        "charges_at_target": win["total"],
        "rr_net": round(win["net_pnl"] / loss, 2) if loss > 0 else None,
        "notes": notes, "status": "DRAFT", "created": ts.isoformat(timespec="minutes"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capital", type=float)
    ap.add_argument("--max-loss", type=float)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    plan = read_state("plan.json") or die("no trader/plan.json - run the Exit Planner with --write first")
    ledger = read_state("paper_ledger.json")
    cash = ledger.get("cash") if (ledger and cfg["paper"]) else None
    capital = args.capital or cfg["capital"]
    max_loss = args.max_loss or cfg["max_loss_per_trade"]
    try:
        o = size(plan, cfg, capital, max_loss, cash)
    except ValueError as e:
        die(str(e))
    verb = "Buy" if o["side"] == "BUY" else "Sell short"
    print(f"Capital {fmt_inr(capital)}, max loss {fmt_inr(max_loss)} per trade (charges included):")
    print(f"  {verb} {o['qty']} {o['symbol']} {o['product']} {o['order_type']} at {o['limit']} "
          f"= {fmt_inr(o['value'])} (margin {fmt_inr(o['margin_needed'])})")
    print(f"  stop {o['stop']}: lose about {fmt_inr(o['est_loss_at_stop'])}")
    print(f"  target {o['target']}: make about {fmt_inr(o['est_profit_at_target'])} after {fmt_inr(o['charges_at_target'])} charges")
    print(f"  net reward:risk {o['rr_net']}; flat by {o['flat_by']}")
    for n in o["notes"]:
        print(f"  note: {n}")
    if args.write:
        book = read_state("orders.json") or {"orders": []}
        book["orders"] = [x for x in book["orders"] if x["status"] in ("FILLED", "OPEN", "CLOSED")] + [o]
        write_state("orders.json", book)
        print(f"Saved order {o['id']} to trader/orders.json (status DRAFT, not sent anywhere)")


if __name__ == "__main__":
    main()

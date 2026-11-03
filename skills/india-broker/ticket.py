#!/usr/bin/env python3
"""Order Executor: paper trading by default; never sends anything without your yes.

  ticket.py show                       the tickets in plain words, READY or not
  ticket.py approve ORDER_ID --yes     paper: book it in the paper ledger
                                       live: print the exact broker order(s) for you / Claude to place
  ticket.py sync                       paper: fill, stop, target or flatten from the latest bars
  ticket.py ledger                     paper cash, open positions and today's P&L
  ticket.py cancel ORDER_ID
  ticket.py mark-sent ORDER_ID --broker-id X   live: record that the broker accepted it
  ticket.py reset-paper [--cash 100000]
"""
import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_shared"))

from core import IST, at_today, die, fmt_inr, load_config, now, read_state, write_state  # noqa: E402
from costs import intraday_charges  # noqa: E402
from data import DataError, by_day, chart, session_bars  # noqa: E402
from indicators import bar_minutes  # noqa: E402


def load_book():
    return read_state("orders.json") or {"orders": []}


def find(book, oid):
    for o in book["orders"]:
        if o["id"] == oid:
            return o
    die(f"no order {oid} in trader/orders.json")


def ledger(cfg):
    led = read_state("paper_ledger.json")
    if not led:
        led = {"cash": cfg["capital"], "start_cash": cfg["capital"], "open": [], "closed": []}
        write_state("paper_ledger.json", led)
    return led


def ticket_text(o):
    verb = "BUY" if o["side"] == "BUY" else "SELL (short)"
    exit_verb = "sell" if o["side"] == "BUY" else "buy back"
    return (f"{verb} {o['qty']} {o['symbol']} on NSE, intraday (MIS), {o['order_type']} at {o['limit']}.\n"
            f"    Then {exit_verb} at {o['stop']} if it goes against you (stop-loss), or at {o['target']} "
            f"(target), or at market by {o['flat_by']} IST, whichever comes first.\n"
            f"    Worst case at the stop about {fmt_inr(o['est_loss_at_stop'])}; at the target about "
            f"+{fmt_inr(o['est_profit_at_target'])} after charges.")


def broker_params(o):
    """Generic parameters most Indian broker APIs / MCP servers accept (Kite, Upstox, Angel, Dhan)."""
    exit_side = "SELL" if o["side"] == "BUY" else "BUY"
    return [
        {"leg": "entry", "exchange": "NSE", "tradingsymbol": o["symbol"], "transaction_type": o["side"],
         "quantity": o["qty"], "product": "MIS", "order_type": "LIMIT", "price": o["limit"], "validity": "DAY"},
        {"leg": "stop-loss (place after the entry fills)", "exchange": "NSE", "tradingsymbol": o["symbol"],
         "transaction_type": exit_side, "quantity": o["qty"], "product": "MIS", "order_type": "SL",
         "trigger_price": o["stop"],
         "price": round(o["stop"] * (0.995 if exit_side == "SELL" else 1.005), 2), "validity": "DAY"},
        {"leg": "target (manage with an alert, or a LIMIT if your broker cancels the other leg for you)",
         "exchange": "NSE", "tradingsymbol": o["symbol"], "transaction_type": exit_side, "quantity": o["qty"],
         "product": "MIS", "order_type": "LIMIT", "price": o["target"], "validity": "DAY"},
    ]


def cmd_show(book, cfg):
    if not book["orders"]:
        print("No tickets. Run the Budget Manager and the Risk Manager first.")
        return
    print(f"Mode: {'PAPER' if cfg['paper'] else 'LIVE'}")
    for o in book["orders"]:
        print(f"\n[{o['status']}] {o['id']}")
        print("    " + ticket_text(o))
        if o["status"] == "DRAFT":
            print("    Not risk-checked yet: run the Risk Manager.")
        elif o["status"] == "BLOCKED":
            print("    Blocked by the Risk Manager; see trader/risk.json.")


def cmd_approve(book, cfg, oid, yes):
    o = find(book, oid)
    if o["status"] != "READY":
        die(f"{oid} is {o['status']}; only READY orders (passed the Risk Manager) can be approved")
    checked = dt.datetime.fromisoformat(o["risk_checked"])
    if (now() - checked).total_seconds() > 15 * 60:
        die("the risk check is more than 15 minutes old; run the Risk Manager again")
    if not yes:
        print("Ticket:\n    " + ticket_text(o))
        die("add --yes only after the person has typed yes for this exact ticket", 2)
    if cfg["paper"]:
        led = ledger(cfg)
        o["status"] = "APPROVED"
        o["approved"] = now().isoformat(timespec="minutes")
        o["mode"] = "paper"
        led["cash"] = round(led["cash"] - o["margin_needed"], 2)
        led["open"].append({"id": o["id"], "symbol": o["symbol"], "state": "pending", "approved": o["approved"]})
        write_state("paper_ledger.json", led)
        write_state("orders.json", book)
        print(f"PAPER: {o['id']} booked. Margin {fmt_inr(o['margin_needed'])} reserved; "
              f"cash now {fmt_inr(led['cash'])}. Run `ticket.py sync` to fill and manage it from live bars.")
        return
    o["status"] = "APPROVED_LIVE"
    o["approved"] = now().isoformat(timespec="minutes")
    o["mode"] = "live"
    write_state("orders.json", book)
    print("LIVE: nothing has been sent by this script. Place these with your broker app or connector:")
    for leg in broker_params(o):
        print("   ", leg)
    print("Then record the broker's order id: ticket.py mark-sent", o["id"], "--broker-id <id>")


def walk_bars(bars, o):
    long_ = o["side"] == "BUY"
    stop, target = o["stop"], o["target"]
    for b in bars:
        if long_:
            if b["o"] <= stop:
                return "stop", b["o"], b
            if b["o"] >= target:
                return "target", b["o"], b
            if b["l"] <= stop:
                return "stop", stop, b
            if b["h"] >= target:
                return "target", target, b
        else:
            if b["o"] >= stop:
                return "stop", b["o"], b
            if b["o"] <= target:
                return "target", b["o"], b
            if b["h"] >= stop:
                return "stop", stop, b
            if b["l"] <= target:
                return "target", target, b
    return None, None, None


def cmd_sync(book, cfg):
    led = ledger(cfg)
    t = now()
    changed = False
    for pos in list(led["open"]):
        o = find(book, pos["id"])
        try:
            bars = session_bars(by_day(chart(o["symbol"], "5m", "5d")["bars"]).get(t.date(), []))
        except DataError as e:
            print(f"{o['id']}: no data ({e})")
            continue
        m = bar_minutes(bars)
        approved = dt.datetime.fromisoformat(o["approved"])
        live = [b for b in bars if b["dt"] + dt.timedelta(minutes=m) > approved
                and b["dt"] + dt.timedelta(minutes=m) <= t]
        long_ = o["side"] == "BUY"
        flat = at_today(o["flat_by"], t)
        if pos["state"] == "pending":
            fill = None
            for i, b in enumerate(live):
                if (long_ and b["l"] <= o["limit"]) or (not long_ and b["h"] >= o["limit"]):
                    if b["dt"] < approved:
                        # Bar was already trading when you approved: assume the worst, your limit
                        px = o["limit"]
                    else:
                        px = min(b["o"], o["limit"]) if long_ else max(b["o"], o["limit"])
                    fill = (i, px, b)
                    break
            if fill is None:
                if t >= flat or t >= at_today(cfg["entry_window"][1], t):
                    led["open"].remove(pos)
                    led["cash"] = round(led["cash"] + o["margin_needed"], 2)
                    o["status"] = "EXPIRED"
                    print(f"{o['id']}: limit {o['limit']} never filled; expired, margin released.")
                    changed = True
                else:
                    print(f"{o['id']}: waiting for a fill at {o['limit']}")
                continue
            i, px, b = fill
            pos.update({"state": "open", "fill_price": round(px, 2), "fill_time": b["dt"].strftime("%H:%M")})
            o["status"] = "OPEN"
            print(f"{o['id']}: PAPER FILL {o['qty']} at {px:.2f} ({b['dt']:%H:%M} bar)")
            live = live[i + 1:]
            changed = True
        before_flat = [b for b in live if b["dt"] + dt.timedelta(minutes=m) <= flat]
        if pos.get("fill_time"):
            ft = pos["fill_time"]
            before_flat = [b for b in before_flat if b["dt"].strftime("%H:%M") > ft]
        outcome, px, b = walk_bars(before_flat, o)
        if outcome is None and t >= flat and before_flat:
            outcome, px, b = "flat", before_flat[-1]["c"], before_flat[-1]
        if outcome is None:
            last = live[-1]["c"] if live else pos["fill_price"]
            mtm = (last - pos["fill_price"]) * o["qty"] * (1 if long_ else -1)
            print(f"{o['id']}: open at {pos['fill_price']}, last {last:.2f}, unrealised {fmt_inr(mtm)} (before charges)")
            continue
        entry = pos["fill_price"]
        buy, sell = (entry, px) if long_ else (px, entry)
        ch = intraday_charges(buy, sell, o["qty"], cfg["broker_profile"], cfg["rates"])
        led["open"].remove(pos)
        led["cash"] = round(led["cash"] + o["margin_needed"] + ch["net_pnl"], 2)
        led["closed"].append({"id": o["id"], "symbol": o["symbol"], "date": t.date().isoformat(),
                              "side": o["direction"], "qty": o["qty"], "entry": entry, "exit": round(px, 2),
                              "outcome": outcome, "exit_time": b["dt"].strftime("%H:%M"),
                              "gross_pnl": ch["gross_pnl"], "charges": ch["total"], "net_pnl": ch["net_pnl"]})
        o["status"] = "CLOSED"
        print(f"{o['id']}: PAPER EXIT at {px:.2f} ({outcome}, {b['dt']:%H:%M}): net {fmt_inr(ch['net_pnl'])} "
              f"after {fmt_inr(ch['total'])} charges")
        changed = True
    if changed:
        write_state("paper_ledger.json", led)
        write_state("orders.json", book)
    if not led["open"]:
        print("No open paper positions.")


def cmd_ledger(cfg):
    led = ledger(cfg)
    today = now().date().isoformat()
    td = [c for c in led["closed"] if c["date"] == today]
    print(f"Paper cash {fmt_inr(led['cash'])} (started {fmt_inr(led['start_cash'])}); "
          f"all-time net {fmt_inr(sum(c['net_pnl'] for c in led['closed']))} over {len(led['closed'])} trades")
    print(f"Today: {len(td)} closed, net {fmt_inr(sum(c['net_pnl'] for c in td))}; {len(led['open'])} open")
    for c in led["closed"][-10:]:
        print(f"  {c['date']} {c['symbol']:<12} {c['side']:<5} {c['qty']:>5} {c['entry']:>9.2f} -> {c['exit']:>9.2f} "
              f"{c['outcome']:<6} net {fmt_inr(c['net_pnl'])}")
    if led["closed"]:
        wins = sum(1 for c in led["closed"] if c["net_pnl"] > 0)
        print(f"Win rate {100 * wins / len(led['closed']):.0f}% (net of charges)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["show", "approve", "sync", "ledger", "cancel", "mark-sent", "reset-paper"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--broker-id")
    ap.add_argument("--cash", type=float)
    args = ap.parse_args()
    cfg = load_config()
    book = load_book()
    if args.cmd == "show":
        cmd_show(book, cfg)
    elif args.cmd == "approve":
        cmd_approve(book, cfg, args.id or die("give an order id"), args.yes)
    elif args.cmd == "sync":
        cmd_sync(book, cfg)
    elif args.cmd == "ledger":
        cmd_ledger(cfg)
    elif args.cmd == "cancel":
        o = find(book, args.id or die("give an order id"))
        if o["status"] == "APPROVED" and o.get("mode") == "paper":
            led = ledger(cfg)
            led["open"] = [p for p in led["open"] if p["id"] != o["id"]]
            led["cash"] = round(led["cash"] + o["margin_needed"], 2)
            write_state("paper_ledger.json", led)
        elif o["status"] == "OPEN":
            die("the paper position is already filled; let sync manage the exit")
        o["status"] = "CANCELLED"
        write_state("orders.json", book)
        print(f"{o['id']} cancelled")
    elif args.cmd == "mark-sent":
        o = find(book, args.id or die("give an order id"))
        o["status"] = "SENT"
        o["broker_id"] = args.broker_id
        write_state("orders.json", book)
        print(f"{o['id']} recorded as sent (broker id {args.broker_id})")
    else:
        cash = args.cash or cfg["capital"]
        write_state("paper_ledger.json", {"cash": cash, "start_cash": cash, "open": [], "closed": []})
        print(f"Paper ledger reset to {fmt_inr(cash)}")


if __name__ == "__main__":
    main()

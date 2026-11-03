#!/usr/bin/env python3
"""Smart Money Tracker: NSE bulk deals, block deals and insider (SEBI PIT) disclosures.

  deals.py bulk  [--symbols A,B | --watchlist] [--min-value-cr 1]
  deals.py block [--symbols A,B | --watchlist]
  deals.py insider [--days 7] [--symbols A,B | --watchlist]

Bulk deals: a client trading > 0.5% of a company's shares in a day. Block deals: large
trades in the block window. Insider trades: promoters, directors and designated persons
disclosing under SEBI's insider trading rules. All public. None of it is a signal by itself.
"""
import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_dalal"))

from core import die, fmt_inr, now, read_state, write_state, norm_symbol  # noqa: E402
from data import DataError, col, nse_csv, nse_json  # noqa: E402


def num(s):
    try:
        return float(str(s).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def filter_syms(args):
    if args.symbols:
        return {norm_symbol(s) for s in args.symbols.split(",") if s.strip()}
    if args.watchlist:
        wl = read_state("watchlist.json") or die("no dalal/watchlist.json")
        return set(wl["symbols"])
    return None


def cmd_deals(kind, args):
    rows = nse_csv(f"{kind}.csv")
    want = filter_syms(args)
    deals = []
    for r in rows:
        sym = norm_symbol(col(r, "Symbol"))
        if not sym or (want and sym not in want):
            continue
        qty = num(col(r, "Quantity Traded", "Quantity"))
        px = num(col(r, "Trade Price / Wght. Avg. Price", "Trade Price/Wght. Avg. Price", "Trade Price", "Price"))
        deals.append({"date": col(r, "Date"), "symbol": sym, "name": col(r, "Security Name"),
                      "client": col(r, "Client Name"), "side": col(r, "Buy/Sell", "Buy / Sell").upper(),
                      "qty": int(qty), "price": px, "value_cr": round(qty * px / 1e7, 2),
                      "remarks": col(r, "Remarks")})
    deals = [d for d in deals if d["value_cr"] >= args.min_value_cr]
    agg = {}
    for d in deals:
        a = agg.setdefault(d["symbol"], {"symbol": d["symbol"], "name": d["name"], "buy_qty": 0, "sell_qty": 0,
                                         "buy_cr": 0.0, "sell_cr": 0.0, "clients": set()})
        if d["side"].startswith("B"):
            a["buy_qty"] += d["qty"]
            a["buy_cr"] += d["value_cr"]
        else:
            a["sell_qty"] += d["qty"]
            a["sell_cr"] += d["value_cr"]
        a["clients"].add(d["client"])
    summary = []
    for a in agg.values():
        a["net_cr"] = round(a["buy_cr"] - a["sell_cr"], 2)
        a["buy_cr"], a["sell_cr"] = round(a["buy_cr"], 2), round(a["sell_cr"], 2)
        a["clients"] = sorted(a["clients"])
        summary.append(a)
    summary.sort(key=lambda a: -abs(a["net_cr"]))
    date = deals[0]["date"] if deals else "today"
    print(f"NSE {kind} deals ({date}): {len(deals)} trades in {len(summary)} stocks"
          + (f" (filtered to {len(want)} symbols)" if want else ""))
    for a in summary[:25]:
        print(f"  {a['symbol']:<14} net {a['net_cr']:+9.2f} Cr  (buy {a['buy_cr']:.2f}, sell {a['sell_cr']:.2f})  "
              f"{len(a['clients'])} client(s): {', '.join(a['clients'][:3])}")
    return {"kind": kind, "date": date, "deals": deals, "by_symbol": summary}


def cmd_insider(args):
    t = now()
    frm = (t - dt.timedelta(days=args.days)).strftime("%d-%m-%Y")
    to = t.strftime("%d-%m-%Y")
    j = nse_json(f"/api/corporates-pit?index=equities&from_date={frm}&to_date={to}", "nse_pit.json")
    if isinstance(j, dict):
        rows = j.get("data") or j.get("Data") or j.get("rows") or []
    else:
        rows = j or []
    if not rows:
        shape = f"keys: {', '.join(list(j)[:8])}" if isinstance(j, dict) else f"type {type(j).__name__}"
        print(f"NSE returned no insider rows for {frm} to {to} ({shape}). That is unusual for a working day: "
              "NSE may have refused the request or changed the endpoint. Check "
              "nseindia.com > Companies > Insider Trading to compare.")
    want = filter_syms(args)
    out = []
    for r in rows:
        sym = norm_symbol(r.get("symbol", ""))
        if not sym or (want and sym not in want):
            continue
        qty = num(r.get("secAcq"))
        val = num(r.get("secVal"))
        out.append({"symbol": sym, "company": r.get("company", ""), "person": r.get("acqName", ""),
                    "category": r.get("personCategory", ""), "type": r.get("tdpTransactionType", ""),
                    "mode": r.get("acqMode", ""), "qty": int(qty), "value": val,
                    "from": r.get("acqfromDt", ""), "to": r.get("acqtoDt", ""),
                    "filed": r.get("intimDt", "") or r.get("date", "")})
    buys = [o for o in out if str(o["type"]).lower().startswith("buy")]
    sells = [o for o in out if str(o["type"]).lower().startswith("sell")]
    print(f"Insider disclosures {frm} to {to}: {len(out)} ({len(buys)} buys, {len(sells)} sells)")
    for o in sorted(out, key=lambda o: -o["value"])[:25]:
        print(f"  {o['symbol']:<12} {o['type']:<5} {fmt_inr(o['value']):>16}  {o['category'][:22]:<22} "
              f"{o['person'][:30]} ({o['mode']})")
    return {"kind": "insider", "from": frm, "to": to, "trades": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["bulk", "block", "insider"])
    ap.add_argument("--symbols")
    ap.add_argument("--watchlist", action="store_true")
    ap.add_argument("--min-value-cr", type=float, default=0.0)
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    try:
        res = cmd_insider(args) if args.cmd == "insider" else cmd_deals(args.cmd, args)
    except DataError as e:
        die(f"{e}. NSE sometimes blocks scripted access; try again in a minute or open nseindia.com once.")
    store = read_state("deals.json") or {}
    store[args.cmd] = res
    store["time"] = now().isoformat(timespec="minutes")
    write_state("deals.json", store)
    print("Saved dalal/deals.json")


if __name__ == "__main__":
    main()

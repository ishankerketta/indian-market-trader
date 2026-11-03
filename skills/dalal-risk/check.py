#!/usr/bin/env python3
"""Risk Manager: check every draft order against your limits and NSE rules. PASS or BLOCK.

  check.py [--id ORDER_ID]

Reads dalal/orders.json, config.json, paper_ledger.json, news.json, sentiment.json.
Marks each checked order READY or BLOCKED and writes dalal/risk.json.
"""
import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_dalal"))

from core import at_today, die, fmt_inr, load_config, now, read_state, write_state  # noqa: E402
from data import DataError, daily  # noqa: E402
from indicators import band_limits  # noqa: E402
from sr import all_lines  # noqa: E402
from universe import load_bands  # noqa: E402


def today_stats(ledger, orders, today):
    realized, trades, open_risk = 0.0, 0, 0.0
    for t in (ledger or {}).get("closed", []):
        if t.get("date") == today:
            realized += t.get("net_pnl", 0)
            trades += 1
    for o in orders:
        if o.get("status") in ("APPROVED", "OPEN", "FILLED") and o.get("created", "")[:10] == today:
            trades += 1
            open_risk += o.get("est_loss_at_stop", 0)
    return realized, trades, open_risk


def check_order(o, cfg, ctx):
    res = []

    def add(name, ok, detail, level="block"):
        res.append({"check": name, "result": "PASS" if ok else ("WARN" if level == "warn" else "BLOCK"),
                    "detail": detail})

    t = ctx["now"]
    long_ = o["direction"] == "long"
    add("max loss per trade", o["est_loss_at_stop"] <= cfg["max_loss_per_trade"] + 0.01,
        f"{fmt_inr(o['est_loss_at_stop'])} at the stop vs limit {fmt_inr(cfg['max_loss_per_trade'])}")
    realized, trades, open_risk = ctx["stats"]
    worst = -realized + open_risk + o["est_loss_at_stop"]  # gains today offset, losses add
    add("daily loss limit", worst <= cfg["daily_loss_limit"] + 0.01,
        f"today's P&L {fmt_inr(realized)}, open risk {fmt_inr(open_risk)}, this trade {fmt_inr(o['est_loss_at_stop'])}: "
        f"worst case {fmt_inr(-worst)} vs limit -{fmt_inr(cfg['daily_loss_limit'])}")
    add("trades per day", trades < cfg["max_trades_per_day"],
        f"{trades} taken today, max {cfg['max_trades_per_day']}")
    rr = o.get("rr_net") or 0
    add("reward to risk (net)", rr >= cfg["min_reward_risk"], f"{rr} vs minimum {cfg['min_reward_risk']}")
    w0, w1 = at_today(cfg["entry_window"][0], t), at_today(cfg["entry_window"][1], t)
    add("entry window", w0 <= t <= w1, f"now {t:%H:%M}, window {cfg['entry_window'][0]}-{cfg['entry_window'][1]}")
    flat = at_today(o["flat_by"], t)
    mins = (flat - t).total_seconds() / 60
    add("time before flat-by", mins >= 20, f"{mins:.0f} min until {o['flat_by']}")
    lev = cfg["mis_leverage"] if cfg["use_leverage"] else 1
    cap = cfg["capital"] * cfg["max_position_pct"] / 100 * lev
    add("position size", o["value"] <= cap + 0.01, f"{fmt_inr(o['value'])} vs cap {fmt_inr(cap)}")
    cash = ctx["cash"]
    if cash is not None:
        add("cash / margin", o["margin_needed"] <= cash + 0.01,
            f"needs {fmt_inr(o['margin_needed'])}, available {fmt_inr(cash)}")
    if not long_:
        add("shorting allowed", cfg["allow_short"], "allow_short is " + str(cfg["allow_short"]).lower())
    if o.get("leverage", 1) > 1:
        add("leverage allowed", cfg["use_leverage"], f"order uses {o['leverage']}x")

    info = ctx["bands"].get(o["symbol"])
    if info is None:
        add("series and circuit band", True, "not found in NSE's security list today; check the band yourself", "warn")
        res[-1]["result"] = "WARN"
    else:
        add("series", info["series"] in cfg["allow_series"],
            f"{info['series']} (allowed: {', '.join(cfg['allow_series'])}; BE/BZ are trade-to-trade, no intraday)")
        band = info["band"]
        add("circuit band", band is None or band >= cfg["min_band_pct"],
            f"{'no band (F&O stock)' if band is None else str(band) + '% band'}; minimum {cfg['min_band_pct']}%")
        pc = ctx["prev_close"]
        if band and pc:
            up, dn = band_limits(pc, band)
            buf = cfg["circuit_buffer_pct"] / 100
            if long_:
                ok = o["target"] < up * (1 - buf) and o["limit"] < up * (1 - buf)
                add("room below upper circuit", ok, f"upper circuit {up:.2f} (prev close {pc:.2f}); target {o['target']}")
            else:
                ok = o["target"] > dn * (1 + buf) and o["limit"] > dn * (1 + buf)
                add("room above lower circuit", ok, f"lower circuit {dn:.2f} (prev close {pc:.2f}); target {o['target']}")

    lv = ctx.get("levels", {}).get(o["symbol"])
    if lv and lv.get("time", "")[:10] == t.date().isoformat():
        lines = all_lines(lv)
        if long_:
            walls = sorted((l for l in lines if o["limit"] < l["price"] < o["target"]), key=lambda l: l["price"])
        else:
            walls = sorted((l for l in lines if o["target"] < l["price"] < o["limit"]), key=lambda l: -l["price"])
        if walls:
            w = walls[0]
            tx = f", {w['touches']} touches" if "touches" in w else ""
            add("levels in the way", False,
                f"target {o['target']} is beyond {w['tier']} {w['price']}{tx}; price often stalls there "
                f"(consider --target level)", "warn")
        else:
            add("levels in the way", True, "no support/resistance line between entry and target")

    news = ctx["news"].get(o["symbol"], {})
    if news.get("results_soon"):
        add("results / board meeting", False, news.get("results_note", "results due soon"), "warn")
    sent = ctx["sentiment"].get(o["symbol"], {})
    if sent.get("pump_risk") in ("high", "elevated"):
        add("social buzz / pump risk", False,
            f"{sent['pump_risk']} - {sent.get('pump_note', 'unusual promotional chatter')}", "warn")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id")
    args = ap.parse_args()
    cfg = load_config()
    book = read_state("orders.json") or die("no dalal/orders.json - run the Budget Manager with --write first")
    orders = book["orders"]
    targets = [o for o in orders if (o["id"] == args.id if args.id else o["status"] in ("DRAFT", "BLOCKED", "READY"))]
    if not targets:
        die("no draft orders to check")
    t = now()
    ledger = read_state("paper_ledger.json")
    news = {r["symbol"]: r for r in (read_state("news.json") or {}).get("stocks", [])}
    sentiment = {r["symbol"]: r for r in (read_state("sentiment.json") or {}).get("stocks", [])}
    bands = load_bands()
    report = {"time": t.isoformat(timespec="minutes"), "orders": []}
    for o in targets:
        prev_close = None
        try:
            dbars = daily(o["symbol"], "1mo")
            past = [b for b in dbars if b["dt"].date() < t.date()]
            prev_close = past[-1]["c"] if past else None
        except DataError:
            pass
        ctx = {"now": t, "stats": today_stats(ledger, [x for x in orders if x is not o], t.date().isoformat()),
               "cash": ledger.get("cash") if (ledger and cfg["paper"]) else None,
               "bands": bands, "prev_close": prev_close, "news": news, "sentiment": sentiment,
               "levels": read_state("levels.json") or {}}
        checks = check_order(o, cfg, ctx)
        blocked = [c for c in checks if c["result"] == "BLOCK"]
        o["status"] = "BLOCKED" if blocked else "READY"
        o["risk_checked"] = t.isoformat(timespec="minutes")
        report["orders"].append({"id": o["id"], "symbol": o["symbol"], "verdict": "BLOCK" if blocked else "PASS",
                                 "checks": checks})
        print(f"{o['id']}: {'BLOCK' if blocked else 'PASS'}")
        for c in checks:
            mark = {"PASS": "  ok  ", "WARN": " warn ", "BLOCK": "BLOCK "}[c["result"]]
            print(f"  [{mark}] {c['check']}: {c['detail']}")
    write_state("orders.json", book)
    write_state("risk.json", report)


if __name__ == "__main__":
    main()

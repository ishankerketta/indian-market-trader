#!/usr/bin/env python3
"""Market Pulse: a one-screen brief on the Indian market before (or during) the session.

  pulse.py [--preopen]

NIFTY, BANKNIFTY, SENSEX and India VIX; NIFTY's trend against its 20/50-day averages; a simple
regime label; FII/DII cash flows; sector leaders and laggards; NIFTY 500 breadth; the pre-open
session's biggest gaps (09:00-09:15); today's trading status and the next NSE holiday.
Each section degrades on its own when a source refuses. Writes trader/pulse.json.

Idea from claude-trading-skills-india's market-pulse (MIT); written fresh for this pack.
"""
import argparse
import datetime as dt
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "_shared" if (_HERE / "_shared").is_dir() else _HERE.parent / "_shared"))

from core import now, write_state  # noqa: E402
from data import DataError, all_indices, daily, fii_dii, market_day, nse_holidays, preopen  # noqa: E402
from indicators import sma  # noqa: E402

INDICES = [("NIFTY", "NIFTY 50"), ("BANKNIFTY", "NIFTY BANK"), ("SENSEX", "SENSEX"), ("INDIAVIX", "India VIX")]


def index_row(sym):
    bars = daily(sym, "1y")
    if len(bars) < 2:
        raise DataError("not enough bars")
    closes = [b["c"] for b in bars]
    last, prev = bars[-1], bars[-2]
    return {"last": round(last["c"], 2), "change_pct": round((last["c"] / prev["c"] - 1) * 100, 2),
            "date": last["dt"].date().isoformat(), "sma20": sma(closes, 20), "sma50": sma(closes, 50),
            "high_52w": max(b["h"] for b in bars[-252:])}


def regime(nifty, vix):
    if not nifty or nifty.get("sma20") is None or nifty.get("sma50") is None:
        return "unknown", "not enough NIFTY history"
    c, s20, s50 = nifty["last"], nifty["sma20"], nifty["sma50"]
    trend = "uptrend" if c > s20 > s50 else ("downtrend" if c < s20 < s50 else "range")
    v = vix["last"] if vix else None
    vol = ("calm" if v < 13 else "normal" if v < 18 else "elevated" if v < 24 else "high") if v else "unknown"
    if trend == "downtrend" or vol == "high":
        label = "risk-off"
    elif trend == "uptrend" and vol in ("calm", "normal"):
        label = "risk-on"
    else:
        label = "mixed"
    note = (f"NIFTY {c:,.0f} vs 20-day {s20:,.0f} and 50-day {s50:,.0f} ({trend}); "
            f"India VIX {v:.1f} ({vol})" if v else f"NIFTY {trend}; VIX unavailable")
    return label, note


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preopen", action="store_true", help="show the pre-open gaps even outside 09:00-09:15")
    args = ap.parse_args()
    t = now()
    out = {"time": t.isoformat(timespec="minutes"), "sections": {}}
    trading, why = market_day(t.date())
    status = ("closed today (" + why + ")" if not trading else
              "pre-open" if dt.time(9, 0) <= t.time() < dt.time(9, 15) else
              "before the open" if t.time() < dt.time(9, 0) else
              "open" if t.time() < dt.time(15, 30) else "closed for the day")
    print(f"Market pulse, {t:%a %d %b %Y %H:%M} IST: NSE is {status}.")
    out["status"] = status

    rows = {}
    print("\nIndices (last session close, or live if trading)")
    for sym, label in INDICES:
        try:
            r = index_row(sym)
            rows[sym] = r
            print(f"  {label:<11}{r['last']:>12,.2f}  {r['change_pct']:+6.2f}%   ({r['date']})")
        except DataError as e:
            print(f"  {label:<11} unavailable ({e})")
    out["sections"]["indices"] = rows
    label, note = regime(rows.get("NIFTY"), rows.get("INDIAVIX"))
    out["sections"]["regime"] = {"label": label, "note": note}
    print(f"\nRegime: {label.upper()} - {note}")
    n = rows.get("NIFTY")
    if n:
        print(f"  NIFTY is {(n['last'] / n['high_52w'] - 1) * 100:+.2f}% from its 52-week high")
    v = rows.get("INDIAVIX")
    if v:
        daily_move = v["last"] / (252 ** 0.5)
        print(f"  VIX {v['last']:.1f} implies a typical NIFTY day of about +/-{daily_move:.2f}%")

    try:
        flows = fii_dii()
        out["sections"]["fii_dii"] = flows
        if flows:
            print("\nInstitutional cash flows (INR crore, latest day NSE published)")
            for f in flows:
                print(f"  {f['category']:<12}{f['date']:>14}  net {f['net']:+,.0f}" if f["net"] is not None
                      else f"  {f['category']}: n/a")
    except (DataError, ValueError) as e:
        print(f"\nFII/DII flows unavailable ({str(e)[:60]})")

    try:
        idx = all_indices()
        sect = [r for r in idx if "SECTORAL" in (r.get("key") or "").upper() and r.get("change_pct") is not None]
        sect.sort(key=lambda r: -float(r["change_pct"]))
        b500 = next((r for r in idx if (r.get("index") or "").upper() == "NIFTY 500"), None)
        out["sections"]["sectors"] = sect
        if sect:
            k = min(3, len(sect) // 2) or 1   # leaders and laggards never overlap
            fmt = lambda rs: ", ".join(f"{r['index'].replace('NIFTY ', '')} {float(r['change_pct']):+.2f}%" for r in rs)
            lead, lag = fmt(sect[:k]), fmt(sect[-k:] if len(sect) > k else [])
            print(f"\nSectors  leading: {lead}\n         lagging: {lag}")
        if b500 and b500.get("advances") is not None:
            a, d = int(b500["advances"]), int(b500["declines"] or 0)
            out["sections"]["breadth"] = {"advances": a, "declines": d}
            print(f"Breadth (NIFTY 500): {a} up, {d} down, A/D {a / max(d, 1):.2f}")
    except (DataError, ValueError) as e:
        print(f"\nSectors and breadth unavailable ({str(e)[:60]})")

    if args.preopen or status == "pre-open":
        try:
            po = [p for p in preopen("NIFTY") if p["change_pct"] is not None]
            po.sort(key=lambda p: -float(p["change_pct"]))
            out["sections"]["preopen"] = po
            if po:
                print("\nPre-open gaps (NIFTY 50, indicative open vs previous close)")
                k = min(5, len(po) // 2) or len(po)
                for p in (po[:k] + po[-k:] if len(po) > 2 * k else po):
                    print(f"  {p['symbol']:<12}{float(p['change_pct']):+6.2f}%  IEP {p['iep']}")
        except (DataError, ValueError) as e:
            print(f"\nPre-open data unavailable ({str(e)[:60]})")

    hol = nse_holidays(t.year)
    nxt = min((d for d in hol if d > t.date()), default=None)
    if nxt:
        print(f"\nNext NSE holiday: {nxt:%a %d %b} ({hol[nxt]})")
    write_state("pulse.json", out)
    print("\nSaved trader/pulse.json. Context, not a signal: a regime label describes the backdrop, it does not pick trades.")


if __name__ == "__main__":
    main()

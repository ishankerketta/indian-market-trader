#!/usr/bin/env python3
"""News Monitor: headlines, NSE filings and today's move for the stocks you watch.

  news.py --tickers RELIANCE,TCS [--hours 12]
  news.py --from-scan            the ORB scan's candidates (trader/scan.json)
  news.py                        the watchlist (trader/watchlist.json)

Sources: Yahoo Finance, Google News India (Moneycontrol, ET, Business Standard, Mint ...),
NSE corporate announcements and board meetings (best effort; NSE blocks scripted access at times).
"""
import argparse
import datetime as dt
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_shared"))

from core import IST, die, now, read_state, write_state, norm_symbol  # noqa: E402
from data import DataError, daily, google_news, nse_json, yahoo_news  # noqa: E402
from text import label, mentions, results_upcoming, score, stock_aliases, tag  # noqa: E402
from universe import names  # noqa: E402


def pick(args):
    if args.tickers:
        return [norm_symbol(s) for s in args.tickers.split(",") if s.strip()]
    if args.from_scan:
        sc = read_state("scan.json") or die("no trader/scan.json - run the ORB scan first")
        return [c["symbol"] for c in sc["candidates"]][: args.limit]
    wl = read_state("watchlist.json")
    if wl and wl.get("symbols"):
        return wl["symbols"][: args.limit]
    die("give --tickers, --from-scan, or build a watchlist with the scanner")


def _norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:80]


def nse_filings(sym, t):
    items, results_soon, note = [], False, ""
    try:
        ann = nse_json(f"/api/corporate-announcements?index=equities&symbol={sym}", f"nse_ann_{sym}.json")
        for a in (ann if isinstance(ann, list) else ann.get("data", []))[:15]:
            when = None
            for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
                try:
                    when = dt.datetime.strptime(a.get("an_dt", ""), fmt).replace(tzinfo=IST)
                    break
                except ValueError:
                    pass
            title = (a.get("desc") or "") + (": " + a["attchmntText"][:160] if a.get("attchmntText") else "")
            items.append({"title": title.strip(), "source": "NSE filing", "url": a.get("attchmntFile", ""),
                          "via": "nse", "time": when})
    except (DataError, ValueError, AttributeError):
        pass
    try:
        bm = nse_json(f"/api/corporate-board-meetings?index=equities&symbol={sym}", f"nse_bm_{sym}.json")
        for m in (bm if isinstance(bm, list) else bm.get("data", []))[:10]:
            purpose = (m.get("bm_purpose") or "") + " " + (m.get("bm_desc") or "")
            try:
                d = dt.datetime.strptime(m.get("bm_date", ""), "%d-%b-%Y").date()
            except ValueError:
                continue
            days = (d - t.date()).days
            if 0 <= days <= 3 and re.search(r"result", purpose, re.I):
                results_soon = True
                note = f"board meeting on {d:%d %b} to consider results ({'today' if days == 0 else f'in {days} day(s)'})"
    except (DataError, ValueError, AttributeError):
        pass
    return items, results_soon, note


def one(sym, hours, t, nm):
    items = []
    errs = []
    for fetch in (lambda: yahoo_news(sym), lambda: google_news(f"{nm or sym} share", days=max(1, hours // 24 + 1),
                                                                 fixture_key=sym)):
        try:
            items += fetch()
        except (DataError, ValueError) as e:
            errs.append(str(e))
    filings, results_soon, note = nse_filings(sym, t)
    items += filings
    aliases = stock_aliases(sym, nm)
    cutoff = t - dt.timedelta(hours=hours)
    seen, kept, dropped = set(), [], 0
    for it in sorted(items, key=lambda x: x["time"] or t, reverse=True):
        k = _norm_title(it["title"])
        if not k or k in seen:
            continue
        seen.add(k)
        if it["time"] and it["time"] < cutoff:
            continue
        # Google News matches loosely; keep only headlines that name the company
        if it["via"] == "google_news" and not mentions(it["title"], sym, aliases):
            dropped += 1
            continue
        s = score(it["title"])
        it.update({"tags": tag(it["title"]), "score": round(s, 2), "label": label(s),
                   "time": it["time"].isoformat(timespec="minutes") if it["time"] else None})
        kept.append(it)
    if not results_soon:
        recent = [it for it in kept if it["time"] and t - dt.datetime.fromisoformat(it["time"]) <= dt.timedelta(hours=36)]
        hit = next((it for it in recent if "results" in it["tags"] and results_upcoming(it["title"])), None)
        if hit:
            results_soon, note = True, f"headline suggests results are due: \"{hit['title'][:80]}\""
    move, move_day = None, None
    try:
        d = daily(sym, "5d")
        if len(d) >= 2:
            move = round((d[-1]["c"] / d[-2]["c"] - 1) * 100, 2)
            move_day = d[-1]["dt"].date()
    except DataError:
        pass
    tags = {}
    for it in kept:
        for tg in it["tags"]:
            tags[tg] = tags.get(tg, 0) + 1
    avg = round(sum(i["score"] for i in kept) / len(kept), 2) if kept else 0.0
    return {"symbol": sym, "name": nm, "move_pct": move,
            "move_label": ("today" if move_day == t.date() else f"last session ({move_day:%a %d %b})") if move_day else "",
            "count": len(kept), "off_topic_dropped": dropped, "avg_score": avg,
            "tone": label(avg), "tag_counts": tags, "results_soon": results_soon, "results_note": note,
            "items": kept[:25], "errors": errs}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers")
    ap.add_argument("--from-scan", action="store_true")
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()
    t = now()
    nmap = names()
    out = {"time": t.isoformat(timespec="minutes"), "hours": args.hours, "stocks": []}
    for sym in pick(args):
        r = one(sym, args.hours, t, nmap.get(sym, ""))
        out["stocks"].append(r)
        mv = f"{r['move_pct']:+.2f}%" if r["move_pct"] is not None else "n/a"
        print(f"\n{sym} {('(' + r['name'] + ') ') if r['name'] else ''}{r['move_label'] or 'move'} {mv}; "
              f"{r['count']} items in {args.hours}h (dropped {r['off_topic_dropped']} off-topic), "
              f"tone {r['tone']} ({r['avg_score']:+.2f})")
        if r["results_soon"]:
            print(f"  !! {r['results_note']} - a day trade must be flat before the announcement")
        for it in r["items"][:8]:
            tm = it["time"][11:16] if it["time"] else "--:--"
            tg = f" [{', '.join(it['tags'])}]" if it["tags"] else ""
            print(f"  {tm} {it['label'][:3]} {it['title'][:110]} ({it['source']}){tg}")
        if not r["items"] and r["errors"]:
            print("  no items: " + "; ".join(r["errors"][:2]))
    write_state("news.json", out)
    print("\nSaved trader/news.json. Tone is a word-list first pass; read the headlines before trusting it.")


if __name__ == "__main__":
    main()

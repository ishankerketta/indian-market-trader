#!/usr/bin/env python3
"""Sentiment & Buzz: what the news and Indian market social media are saying, and how loudly.

  sentiment.py --tickers RELIANCE,IREDA [--days 7]
  sentiment.py --from-scan | (watchlist by default)

News: Yahoo Finance + Google News India. Social: Reddit (r/IndianStreetBets,
r/StockMarketIndia, r/IndiaInvestments, r/DalalStreetTalks) via public JSON, best effort.
Scores are a lexicon first pass; the skill asks Claude to read the actual text.

A sudden spike in chatter is treated as a RISK flag, not a buy signal: social-media
pump-and-dump schemes in small caps are a known problem SEBI acts against.
"""
import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_dalal"))

from core import die, load_config, now, read_state, write_state, norm_symbol  # noqa: E402
from data import DataError, daily, google_news, reddit_search, yahoo_news  # noqa: E402
from text import label, mentions, pump_flags, score, stock_aliases  # noqa: E402
from universe import names  # noqa: E402


def pick(args):
    if args.tickers:
        return [norm_symbol(s) for s in args.tickers.split(",") if s.strip()]
    if args.from_scan:
        sc = read_state("scan.json") or die("no dalal/scan.json")
        return [c["symbol"] for c in sc["candidates"]][: args.limit]
    wl = read_state("watchlist.json")
    if wl and wl.get("symbols"):
        return wl["symbols"][: args.limit]
    die("give --tickers, --from-scan, or build a watchlist with the scanner")


def window_stats(items, t, days):
    """Count and mean score in the last 24h vs the average day before that."""
    recent = [i for i in items if i["time"] and t - i["time"] <= dt.timedelta(hours=24)]
    older = [i for i in items if i["time"] and dt.timedelta(hours=24) < t - i["time"] <= dt.timedelta(days=days)]
    base = len(older) / max(1, days - 1)
    ratio = len(recent) / max(base, 0.5)
    s_recent = sum(i["score"] for i in recent) / len(recent) if recent else 0.0
    s_all = sum(i["score"] for i in items) / len(items) if items else 0.0
    return {"count_24h": len(recent), "per_day_before": round(base, 2), "buzz_ratio": round(ratio, 2),
            "score_24h": round(s_recent, 2), "score_window": round(s_all, 2)}


def one(sym, nm, days, cfg, t):
    errs = []
    news = []
    for fetch in (lambda: yahoo_news(sym, 30), lambda: google_news(f"{nm or sym} share", days, fixture_key=sym)):
        try:
            news += fetch()
        except (DataError, ValueError) as e:
            errs.append(str(e))
    aliases = stock_aliases(sym, nm)
    seen, nclean = set(), []
    for it in news:
        k = it["title"].lower()[:70]
        if k in seen:
            continue
        seen.add(k)
        if it.get("via") == "google_news" and not mentions(it["title"], sym, aliases):
            continue
        it["score"] = score(it["title"])
        nclean.append(it)
    social = []
    social_ok = True
    query = " OR ".join([sym] + [f"\"{a}\"" if " " in a else a for a in aliases[:2] if a.upper() != sym])
    try:
        for p in reddit_search(query, fixture_key=sym):
            txt = p["title"] + " " + p["text"]
            if not mentions(txt, sym, aliases):
                continue
            p["score"] = score(txt)
            p["pump"] = pump_flags(txt)
            social.append(p)
    except (DataError, ValueError) as e:
        social_ok = False
        errs.append(f"reddit: {e}")
    ns = window_stats(nclean, t, days)
    ss = window_stats(social, t, days) if social_ok else None
    if ss and (social):
        combined = 0.6 * ns["score_window"] + 0.4 * ss["score_window"]
    else:
        combined = ns["score_window"]
    pump_hits = sum(len(p["pump"]) for p in social)
    turnover_cr = None
    try:
        d = daily(sym, "1mo")
        if len(d) >= 5:
            turnover_cr = sum(b["c"] * b["v"] for b in d[-20:]) / len(d[-20:]) / 1e7
    except DataError:
        pass
    small = turnover_cr is not None and turnover_cr < 25
    spike = cfg["buzz_spike_ratio"]
    social_spike = ss is not None and ss["buzz_ratio"] >= spike and ss["count_24h"] >= 3
    news_quiet = ns["count_24h"] <= 1
    if social_spike and (pump_hits >= 2 or (small and news_quiet)):
        risk, note = "high", "social chatter spiking with promotional language or no news to explain it"
    elif social_spike or (pump_hits >= 2 and small):
        risk, note = "elevated", "chatter is unusually loud; check for a real catalyst before trusting the move"
    else:
        risk, note = "normal", ""
    top_news = sorted(nclean, key=lambda i: i["time"] or t, reverse=True)[:8]
    top_social = sorted(social, key=lambda p: (p["time"], p["score"]), reverse=True)[:8]
    return {
        "symbol": sym, "name": nm, "sentiment": round(combined, 2), "tone": label(combined),
        "news": ns, "social": ss, "social_available": social_ok,
        "pump_phrases": pump_hits, "avg_turnover_cr": round(turnover_cr, 1) if turnover_cr else None,
        "pump_risk": risk, "pump_note": note,
        "headlines": [{"time": i["time"].isoformat(timespec="minutes") if i["time"] else None,
                       "title": i["title"], "source": i["source"], "score": round(i["score"], 2)} for i in top_news],
        "posts": [{"time": p["time"].isoformat(timespec="minutes"), "sub": p["sub"], "title": p["title"],
                   "upvotes": p.get("upvotes"), "comments": p["comments"],
                   "score": round(p["score"], 2), "pump": p["pump"], "url": p["url"]} for p in top_social],
        "errors": errs,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers")
    ap.add_argument("--from-scan", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()
    cfg = load_config()
    t = now()
    nmap = names()
    out = {"time": t.isoformat(timespec="minutes"), "days": args.days, "stocks": []}
    for sym in pick(args):
        r = one(sym, nmap.get(sym, ""), args.days, cfg, t)
        out["stocks"].append(r)
        n = r["news"]
        print(f"\n{sym}: tone {r['tone']} ({r['sentiment']:+.2f})  pump risk {r['pump_risk'].upper()}")
        print(f"  news: {n['count_24h']} in 24h vs {n['per_day_before']}/day before (x{n['buzz_ratio']}), "
              f"score {n['score_24h']:+.2f}")
        if r["social"]:
            s = r["social"]
            print(f"  reddit: {s['count_24h']} posts in 24h vs {s['per_day_before']}/day before (x{s['buzz_ratio']}), "
                  f"score {s['score_24h']:+.2f}, promo phrases {r['pump_phrases']}")
        elif not r["social_available"]:
            why = next((e for e in r["errors"] if e.startswith("reddit:")), "reddit: unknown")
            print(f"  reddit: unavailable right now ({why[8:]}); news only")
        if r["pump_note"]:
            print(f"  !! {r['pump_note']}")
        for h in r["headlines"][:4]:
            print(f"  news  {h['score']:+.2f} {h['title'][:100]} ({h['source']})")
        for p in r["posts"][:3]:
            print(f"  r/{p['sub']:<17}{p['score']:+.2f} {p['title'][:90]}")
    write_state("sentiment.json", out)
    print("\nSaved dalal/sentiment.json. Lexicon scores are rough; read the text before acting on tone.")


if __name__ == "__main__":
    main()

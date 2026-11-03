#!/usr/bin/env python3
"""Levels: the few support/resistance lines that matter, drawn on a clean chart.

  levels.py SYMBOL [--weeks 4] [--major 3] [--short 5] [--short-days 3] [--no-chart]
  levels.py NIFTY | BANKNIFTY | SENSEX            indices work too

Per stock or index:
  - the highest high and lowest low of the last 4 weeks (2 lines)
  - up to 3 MAJOR lines where the most swing peaks and troughs line up over those 4 weeks
  - 3-5 SHORT-TERM lines from the last 3 sessions, with a lower bar for touches
Lines closer than two tolerance bands are merged away, so the chart stays readable.
Writes dalal/levels.json (all symbols) and dalal/levels_SYMBOL.html (the chart).
"""
import argparse
import datetime as dt
import html
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_dalal"))

from core import die, now, read_state, state_path, write_state, norm_symbol, fmt_inr  # noqa: E402
from data import DataError, by_day, chart, session_bars  # noqa: E402
from sr import nearest, all_lines, pick_levels, swing_points, tolerance  # noqa: E402


def sessions(symbol, interval, rng, n):
    # Only bars that had closed by now: no peeking at later bars when replaying a past moment
    minutes = {"5m": 5, "15m": 15, "30m": 30}.get(interval, 5)
    t = now()
    bars = [b for b in chart(symbol, interval, rng)["bars"] if b["dt"] + dt.timedelta(minutes=minutes) <= t]
    days = by_day(bars)
    out = [session_bars(v) for v in days.values()]
    out = [s for s in out if s][-n:]
    return out


def resample(day_bars, minutes):
    """Combine bars into `minutes`-wide candles anchored at 09:15 for display."""
    out = {}
    for b in day_bars:
        start = b["dt"].replace(hour=9, minute=15, second=0, microsecond=0)
        k = int((b["dt"] - start).total_seconds() // 60 // minutes)
        if k not in out:
            out[k] = dict(b)
        else:
            c = out[k]
            c["h"], c["l"], c["c"], c["v"] = max(c["h"], b["h"]), min(c["l"], b["l"]), b["c"], c["v"] + b["v"]
    return [out[k] for k in sorted(out)]


def compute(symbol, weeks=4, n_major=3, n_short=5, short_days=3):
    n_sess = weeks * 5
    long_s = sessions(symbol, "15m", "60d", n_sess)
    if len(long_s) < 5:
        raise DataError(f"only {len(long_s)} sessions of 15-minute bars for {symbol}")
    short_s = sessions(symbol, "5m", "5d", short_days)
    b15 = [b for s in long_s for b in s]
    b5 = [b for s in short_s for b in s]
    price = (b5 or b15)[-1]["c"]
    tol = tolerance(b15, price)
    hi = max(b15 + b5, key=lambda b: b["h"])   # include today's newest 5-minute bars
    lo = min(b15 + b5, key=lambda b: b["l"])
    range_high = {"price": round(hi["h"], 2), "when": hi["dt"].isoformat(timespec="minutes")}
    range_low = {"price": round(lo["l"], 2), "when": lo["dt"].isoformat(timespec="minutes")}
    # Lines must be at least 4% of the chart's height apart (and two bands), so they never bunch up
    span = hi["h"] - lo["l"]
    major = pick_levels(swing_points(b15, 4), tol, n_major, 3, avoid=[hi["h"], lo["l"]],
                        gap=max(2 * tol, 0.04 * span))
    short = []
    tol_s = tol
    if b5:
        tol_s = tolerance(b5, price, floor_pct=0.08)
        span3 = max(b["h"] for b in b5) - min(b["l"] for b in b5)
        short = pick_levels(swing_points(b5, 3), tol_s, n_short, 2,
                            avoid=[hi["h"], lo["l"]] + [m["price"] for m in major],
                            gap=max(2 * tol_s, 1.5 * tol, 0.06 * span3))
    lv = {"symbol": symbol, "time": now().isoformat(timespec="minutes"), "price": round(price, 2),
          "tolerance": round(tol, 2), "short_tolerance": round(tol_s, 2), "sessions": len(long_s),
          "short_sessions": len(short_s),
          "short_from": short_s[0][0]["dt"].isoformat(timespec="minutes") if short_s else None,
          "range_high": range_high, "range_low": range_low, "major": major, "short_term": short}
    return lv, long_s, short_s


# ---------------------------------------------------------------- chart

CSS = """
:root{--bg:#ffffff;--fg:#1d2327;--muted:#6b7280;--grid:#eceef1;--up:#16a34a;--down:#dc2626;
--rng:#d97706;--maj:#2563eb;--st:#7c3aed;--now:#6b7280;--card:#f8f9fb}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--fg:#e6e8eb;--muted:#9aa3ad;--grid:#232830;
--up:#22c55e;--down:#f87171;--rng:#f59e0b;--maj:#60a5fa;--st:#a78bfa;--now:#9aa3ad;--card:#171b21}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",
Roboto,sans-serif}main{max-width:1180px;margin:0 auto;padding:20px 16px 40px}h1{font-size:20px;margin:0 0 2px}
.sub{color:var(--muted);margin:0 0 16px}svg{width:100%;height:auto;display:block;margin:0 0 18px}
.up{fill:var(--up);stroke:var(--up)}.down{fill:var(--down);stroke:var(--down)}.grid{stroke:var(--grid)}
.ax{fill:var(--muted);font-size:11px}.ttl{fill:var(--fg);font-size:13px;font-weight:600}
.rng{stroke:var(--rng);stroke-width:1.6;stroke-dasharray:6 4}.maj{stroke:var(--maj);stroke-width:2.2}
.st{stroke:var(--st);stroke-width:1.5}.faint{opacity:.35}.now{stroke:var(--now);stroke-width:1;stroke-dasharray:2 3}
.lrng{fill:var(--rng)}.lmaj{fill:var(--maj)}.lst{fill:var(--st)}.lnow{fill:var(--now)}.lbl{font-size:11px}
table{border-collapse:collapse;width:100%;max-width:760px;background:var(--card);border-radius:8px;overflow:hidden}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--grid)}th{color:var(--muted);font-weight:500}
td.n{text-align:right;font-variant-numeric:tabular-nums}.sw{display:inline-block;width:18px;height:0;
border-top:3px solid;vertical-align:middle;margin-right:6px}.note{color:var(--muted);font-size:12px;margin-top:14px}
"""


def panel(bars_by_session, lines, title, width=1180, height=380, label_w=170):
    """One candlestick panel. lines: [{"price", "cls", "lcls", "label", "x0frac"}]."""
    pad_t, pad_b, pad_l = 28, 26, 62
    plot_w = width - label_w - pad_l
    bars = [b for s in bars_by_session for b in s]
    if not bars:
        return ""
    lo = min(b["l"] for b in bars)
    hi = max(b["h"] for b in bars)
    for ln in lines:
        lo, hi = min(lo, ln["price"]), max(hi, ln["price"])
    span = (hi - lo) or 1
    lo, hi = lo - span * 0.04, hi + span * 0.04

    def y(p):
        return pad_t + (hi - p) / (hi - lo) * (height - pad_t - pad_b)

    n = len(bars)
    step = plot_w / n
    cw = max(1.0, min(9.0, step * 0.65))
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
             f'<text class="ttl" x="8" y="17">{html.escape(title)}</text>']
    # price grid
    for i in range(5):
        p = lo + (hi - lo) * (i + 0.5) / 5
        parts.append(f'<line class="grid" x1="{pad_l}" x2="{pad_l + plot_w}" y1="{y(p):.1f}" y2="{y(p):.1f}"/>')
        parts.append(f'<text class="ax" x="{pad_l - 6}" y="{y(p) + 4:.1f}" text-anchor="end">{p:,.2f}</text>')
    # session separators and dates
    idx = 0
    every = max(1, len(bars_by_session) // 10)
    for si, s in enumerate(bars_by_session):
        x = pad_l + idx * step
        if si:
            parts.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{pad_t}" y2="{height - pad_b}"/>')
        if si % every == 0:
            parts.append(f'<text class="ax" x="{x + 2:.1f}" y="{height - 8}">{s[0]["dt"]:%d %b}</text>')
        idx += len(s)
    # candles
    for i, b in enumerate(bars):
        cx = pad_l + (i + 0.5) * step
        cls = "up" if b["c"] >= b["o"] else "down"
        top, bot = y(max(b["o"], b["c"])), y(min(b["o"], b["c"]))
        parts.append(f'<line class="{cls}" x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(b["h"]):.1f}" y2="{y(b["l"]):.1f}"/>')
        parts.append(f'<rect class="{cls}" x="{cx - cw / 2:.1f}" y="{top:.1f}" width="{cw:.1f}" '
                     f'height="{max(0.8, bot - top):.1f}"/>')
    # level lines, then labels nudged apart so they never overlap
    labels = []
    for ln in lines:
        x0 = pad_l + plot_w * ln.get("x0frac", 0)
        yy = y(ln["price"])
        parts.append(f'<line class="{ln["cls"]}" x1="{x0:.1f}" x2="{pad_l + plot_w:.1f}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        labels.append([yy, ln])
    labels.sort(key=lambda t: t[0])
    for i in range(1, len(labels)):
        if labels[i][0] - labels[i - 1][0] < 14:
            labels[i][0] = labels[i - 1][0] + 14
    for yy, ln in labels:
        parts.append(f'<text class="lbl {ln["lcls"]}" x="{pad_l + plot_w + 6}" y="{yy + 4:.1f}">'
                     f'{html.escape(ln["label"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def render(lv, long_s, short_s):
    sym, price = lv["symbol"], lv["price"]
    now_line = {"price": price, "cls": "now", "lcls": "lnow", "label": f"now {price:,.2f}"}
    rng = [{"price": lv["range_high"]["price"], "cls": "rng", "lcls": "lrng",
            "label": f"4-wk high {lv['range_high']['price']:,.2f}"},
           {"price": lv["range_low"]["price"], "cls": "rng", "lcls": "lrng",
            "label": f"4-wk low {lv['range_low']['price']:,.2f}"}]
    maj = [{"price": m["price"], "cls": "maj", "lcls": "lmaj", "label": f"major {m['price']:,.2f} ({m['touches']}x)"}
           for m in lv["major"]]
    # 4-week panel: 30-minute candles; the 3-day lines start where the last 3 sessions begin
    long_disp = [resample(s, 30) for s in long_s]
    total = sum(len(s) for s in long_disp)
    tail = sum(len(s) for s in long_disp[-lv["short_sessions"]:]) if lv["short_sessions"] else 0
    frac = (total - tail) / total if total else 0
    st_long = [{"price": s["price"], "cls": "st", "lcls": "lst", "label": f"3-day {s['price']:,.2f} ({s['touches']}x)",
                "x0frac": frac} for s in lv["short_term"]]
    # The 3-day lines get their own panel below; drawing them here too would crowd the corner
    p1 = panel(long_disp, rng + maj + [now_line],
               f"{sym} - last {lv['sessions']} sessions (30-minute candles): range and major levels")
    # 3-day panel: 5-minute candles, short-term lines in full, majors shown faintly if in view
    p2 = ""
    if short_s:
        lo = min(b["l"] for s in short_s for b in s)
        hi = max(b["h"] for s in short_s for b in s)
        pad = (hi - lo) * 0.15
        near = [dict(m, cls=m["cls"] + " faint") for m in maj + rng if lo - pad <= m["price"] <= hi + pad]
        st = [dict(s, x0frac=0) for s in st_long]
        p2 = panel(short_s, near + st + [now_line],
                   f"{sym} - last {lv['short_sessions']} sessions (5-minute candles): 3-day levels")
    rows = sorted(all_lines(lv), key=lambda l: -l["price"])
    sw = {"4-week high": "var(--rng)", "4-week low": "var(--rng)", "major": "var(--maj)", "3-day": "var(--st)"}
    trs = []
    for l in rows:
        d = (l["price"] / price - 1) * 100
        touches = f'{l["touches"]} ({l["peaks"]} peaks, {l["troughs"]} troughs)' if "touches" in l else "-"
        trs.append(f'<tr><td><span class="sw" style="border-color:{sw[l["tier"]]}"></span>{l["tier"]}</td>'
                   f'<td class="n">{l["price"]:,.2f}</td><td class="n">{d:+.2f}%</td><td>{touches}</td>'
                   f'<td>{html.escape(l.get("role", ""))}</td></tr>')
    sup, res = nearest([l for l in all_lines(lv)], price)
    summary = (f"Price {price:,.2f}. Nearest support {sup['price']:,.2f} ({sup['tier']}), "
               f"nearest resistance {res['price']:,.2f} ({res['tier']})." if sup and res else f"Price {price:,.2f}.")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(sym)} Levels</title>
<style>{CSS}</style></head><body><main>
<h1>{html.escape(sym)} levels</h1><p class="sub">{html.escape(summary)} Updated {lv['time'][:16].replace('T', ' ')} IST.</p>
{p1}
{p2}
<table><thead><tr><th>Line</th><th>Price</th><th>From price</th><th>Touches</th><th>Acted as</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table>
<p class="note">Levels are where swing highs and lows clustered within &plusmn;{lv['tolerance']:,.2f} over the last
{lv['sessions']} sessions (major) and &plusmn;{lv['short_tolerance']:,.2f} over the last {lv['short_sessions']} (3-day).
They describe where price reacted before, not where it must react again. Not investment advice.</p>
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument("--major", type=int, default=3, help="max major lines (default 3)")
    ap.add_argument("--short", type=int, default=5, help="max 3-day lines (default 5)")
    ap.add_argument("--short-days", type=int, default=3)
    ap.add_argument("--no-chart", action="store_true")
    args = ap.parse_args()
    sym = norm_symbol(args.symbol)
    try:
        lv, long_s, short_s = compute(sym, args.weeks, min(args.major, 5), min(args.short, 5), args.short_days)
    except DataError as e:
        die(str(e))
    store = read_state("levels.json") or {}
    store[sym] = lv
    write_state("levels.json", store)
    price = lv["price"]
    print(f"{sym} levels at {price:,.2f} (last {lv['sessions']} sessions; tolerance +/-{lv['tolerance']:,.2f})")
    for l in sorted(all_lines(lv), key=lambda l: -l["price"]):
        extra = f"{l['touches']} touches ({l['peaks']}P/{l['troughs']}T), {l['role']}" if "touches" in l else l["when"][:16]
        print(f"  {l['tier']:<12}{l['price']:>12,.2f}  {(l['price'] / price - 1) * 100:+6.2f}%  {extra}")
    if len(lv["short_term"]) < 3:
        print(f"  (only {len(lv['short_term'])} 3-day level(s) had 2+ touches; not padding the chart with weak ones)")
    sup, res = nearest(all_lines(lv), price)
    if sup:
        print(f"Nearest support {sup['price']:,.2f} ({sup['tier']}), {(1 - sup['price'] / price) * 100:.2f}% below")
    if res:
        print(f"Nearest resistance {res['price']:,.2f} ({res['tier']}), {(res['price'] / price - 1) * 100:.2f}% above")
    else:
        print("No resistance above: price is at or above its 4-week high (no overhead levels to aim for).")
    if not sup:
        print("No support below: price is at or below its 4-week low.")
    if not args.no_chart:
        p = state_path(f"levels_{sym.replace('&', 'and')}.html")
        p.write_text(render(lv, long_s, short_s), encoding="utf-8")
        print(f"Chart: {p}")


if __name__ == "__main__":
    main()

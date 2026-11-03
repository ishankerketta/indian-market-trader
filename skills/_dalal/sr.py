"""Support and resistance levels from swing points, kept deliberately sparse.

A level is a price where several swing highs and swing lows line up (within a
tolerance band). Levels are picked greedily by score, each pick removes its
touch points, and nothing is placed within two bands of an existing line, so
the chart never fills with near-duplicate lines.
"""
import statistics


def swing_points(bars, k):
    """Swing highs/lows: a bar whose high (low) is the extreme of the k bars either side.

    Strict on the left and non-strict on the right, so a flat top counts once.
    """
    pts = []
    for i in range(k, len(bars) - k):
        b = bars[i]
        left, right = bars[i - k:i], bars[i + 1:i + k + 1]
        if all(b["h"] > x["h"] for x in left) and all(b["h"] >= x["h"] for x in right):
            pts.append({"kind": "peak", "price": b["h"], "dt": b["dt"]})
        if all(b["l"] < x["l"] for x in left) and all(b["l"] <= x["l"] for x in right):
            pts.append({"kind": "trough", "price": b["l"], "dt": b["dt"]})
    return pts


def tolerance(bars, price, floor_pct=0.12, range_mult=0.35):
    """Band within which two swing points count as the same level."""
    rngs = [b["h"] - b["l"] for b in bars if b["h"] > b["l"]]
    med = statistics.median(rngs) if rngs else 0
    return max(price * floor_pct / 100, med * range_mult)


def pick_levels(points, tol, max_lines, min_touches, avoid=(), gap=None):
    """Greedy clustering. Score = touches, plus half a point per extra session it held,
    plus half a point if it acted as both support and resistance.

    `gap` is the minimum distance between any two lines (default 2 x tol)."""
    gap = gap if gap is not None else 2 * tol
    remaining = list(points)
    chosen = []
    blocked = list(avoid)
    while len(chosen) < max_lines and remaining:
        cands = []
        for p in remaining:
            members = [q for q in remaining if abs(q["price"] - p["price"]) <= tol]
            if len(members) < min_touches:
                continue
            center = statistics.median(q["price"] for q in members)
            members = [q for q in remaining if abs(q["price"] - center) <= tol]
            sessions = {q["dt"].date() for q in members}
            kinds = {q["kind"] for q in members}
            score = len(members) + 0.5 * (len(sessions) - 1) + (0.5 if len(kinds) == 2 else 0)
            last = max(q["dt"] for q in members)
            cands.append((score, last, center, members, sessions, kinds))
        if not cands:
            break
        cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
        pick = next((c for c in cands if all(abs(c[2] - a) >= gap for a in blocked)), None)
        if pick is None:
            break
        score, last, center, members, sessions, kinds = pick
        chosen.append({
            "price": round(center, 2), "touches": len(members),
            "peaks": sum(1 for q in members if q["kind"] == "peak"),
            "troughs": sum(1 for q in members if q["kind"] == "trough"),
            "sessions": len(sessions), "score": round(score, 1),
            "first_touch": min(q["dt"] for q in members).isoformat(timespec="minutes"),
            "last_touch": last.isoformat(timespec="minutes"),
            "role": "support & resistance" if len(kinds) == 2 else ("resistance" if "peak" in kinds else "support"),
        })
        blocked.append(center)
        ids = {id(q) for q in members}
        remaining = [q for q in remaining if id(q) not in ids]
    return chosen


def nearest(levels, price):
    """Closest level below and above a price, from a flat list of {"price", ...}."""
    below = [l for l in levels if l["price"] < price]
    above = [l for l in levels if l["price"] > price]
    return (max(below, key=lambda l: l["price"]) if below else None,
            min(above, key=lambda l: l["price"]) if above else None)


def all_lines(lv):
    """Flatten a levels.json entry into one list with a 'tier' on each line."""
    out = []
    if lv.get("range_high"):
        out.append({**lv["range_high"], "tier": "4-week high"})
    if lv.get("range_low"):
        out.append({**lv["range_low"], "tier": "4-week low"})
    out += [{**l, "tier": "major"} for l in lv.get("major", [])]
    out += [{**l, "tier": "3-day"} for l in lv.get("short_term", [])]
    return out

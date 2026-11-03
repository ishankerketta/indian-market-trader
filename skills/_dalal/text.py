"""Headline tagging and a small finance sentiment lexicon tuned for Indian markets.

This is a first pass, not a verdict: word lists miss sarcasm, negation and
context. The skills hand the scored headlines to Claude to read properly.
"""
import re

TAGS = {
    "results": r"\b(q[1-4]|quarter(ly)?|results?|earnings|profit|revenue|ebitda|margin|net income|pat)\b",
    "dividend": r"\b(dividend|bonus|split|buyback|record date)\b",
    "order_win": r"\b(order|contract|bags|wins|loi|letter of intent|tender)\b",
    "deal": r"\b(acqui\w*|merger|stake|takeover|amalgamation|demerger|jv|joint venture)\b",
    "fundraise": r"\b(qip|rights issue|fund ?rais\w*|ofs|offer for sale|preferential|ncd)\b",
    "block_deal": r"\b(block deal|bulk deal|large trade)\b",
    "promoter": r"\b(promoter|pledge|insider)\b",
    "rating": r"\b(upgrade|downgrade|target price|rating|overweight|underweight|buy call|sell call)\b",
    "regulatory": r"\b(sebi|rbi|penalty|probe|show cause|ban|raid|ed |income tax|gst notice|nclt|insolvency)\b",
    "management": r"\b(ceo|cfo|md|resign\w*|appoint\w*|steps down|board)\b",
    "circuit": r"\b(upper circuit|lower circuit|circuit|hits 52.week|52.week (high|low)|record high)\b",
}

POS = {
    "beat": 2, "beats": 2, "surge": 2, "surges": 2, "soar": 2, "soars": 2, "jump": 1.5, "jumps": 1.5,
    "rally": 1.5, "rallies": 1.5, "gain": 1, "gains": 1, "rise": 1, "rises": 1, "up": 0.5,
    "record": 1, "high": 0.5, "strong": 1.5, "robust": 1.5, "growth": 1, "upgrade": 2, "upgrades": 2,
    "bags": 1.5, "wins": 1.5, "win": 1, "order": 0.5, "approval": 1.5, "approves": 1, "outperform": 1.5,
    "bullish": 2, "buy": 1, "accumulate": 1, "dividend": 0.5, "bonus": 1, "buyback": 1.5,
    "expansion": 1, "profit": 0.5, "turnaround": 2, "breakout": 1.5, "upper": 1, "rocket": 2,
    "multibagger": 2, "moon": 1, "undervalued": 1,
}

NEG = {
    "miss": 2, "misses": 2, "plunge": 2, "plunges": 2, "crash": 2.5, "crashes": 2.5, "tank": 2,
    "tanks": 2, "fall": 1, "falls": 1, "drop": 1, "drops": 1, "slump": 2, "slumps": 2, "down": 0.5,
    "low": 0.5, "weak": 1.5, "loss": 1.5, "losses": 1.5, "decline": 1, "declines": 1,
    "downgrade": 2, "downgrades": 2, "penalty": 2, "probe": 2, "fraud": 3, "default": 2.5,
    "pledge": 1, "resigns": 1.5, "resignation": 1.5, "ban": 2, "raid": 2, "notice": 1, "lower": 0.5,
    "bearish": 2, "sell": 1, "underperform": 1.5, "insolvency": 3, "nclt": 2, "writeoff": 2,
    "write-off": 2, "dilution": 1.5, "overvalued": 1, "scam": 3, "dump": 2, "bagholder": 1.5,
}

NEGATORS = {"not", "no", "never", "without", "fails", "failed", "despite"}

# Phrases common in pump-and-dump promotion
PUMP_PHRASES = [
    r"\b(\d+x|10x|100x)\b", r"multibagger", r"target \d+ in \d+ (days|weeks)", r"sure ?shot",
    r"jackpot", r"operator", r"telegram", r"whatsapp group", r"guaranteed", r"don'?t miss",
    r"next (adani|suzlon|irfc)", r"to the moon", r"\bload(ed)? up\b",
]

_word = re.compile(r"[a-z][a-z\-']*")


def tag(text):
    t = (text or "").lower()
    return [k for k, rx in TAGS.items() if re.search(rx, t)]


def score(text):
    """Lexicon score in [-1, 1]. Flips the next 3 words after a negator."""
    words = _word.findall((text or "").lower())
    s = 0.0
    flip = 0
    hits = 0
    for w in words:
        if w in NEGATORS:
            flip = 3
            continue
        v = POS.get(w, 0) - NEG.get(w, 0)
        if v:
            hits += 1
            s += -v if flip else v
        if flip:
            flip -= 1
    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, s / (2.0 + abs(s))))


def label(x):
    if x >= 0.25:
        return "positive"
    if x <= -0.25:
        return "negative"
    return "neutral"


def pump_flags(text):
    t = (text or "").lower()
    return [p for p in PUMP_PHRASES if re.search(p, t)]


def mentions(text, symbol, aliases=()):
    """Does this text mention the stock? Matches the symbol as a word or any alias."""
    t = (text or "").lower()
    keys = [symbol.lower()] + [a.lower() for a in aliases if a]
    for k in keys:
        if len(k) <= 3:
            if re.search(r"(?<![a-z])\$?" + re.escape(k) + r"(?![a-z])", t):
                return True
        elif k in t:
            return True
    return False

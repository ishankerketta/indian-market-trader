---
name: dalal-sentiment
description: Sentiment and buzz for Indian stocks from news (Yahoo, Google News India) and Indian market social media (Reddit r/IndianStreetBets, r/StockMarketIndia, r/IndiaInvestments, r/DalalStreetTalks) - tone, mention volume vs normal, and a pump-and-dump risk flag. Use when the user asks what people are saying about a stock, whether a move is hype, or for social sentiment before a trade.
---

# Sentiment & Buzz

```bash
python3 <skill-dir>/sentiment.py --tickers IREDA,SUZLON [--days 7]
python3 <skill-dir>/sentiment.py --from-scan | (no flags: the watchlist)
```

Writes `dalal/sentiment.json`: per stock a combined tone (news 60%, social 40%), news and Reddit counts in the last 24h vs the average day before (`buzz_ratio`), promotional-phrase hits, and `pump_risk` (normal / elevated / high), plus the top headlines and posts.

## How to present it

1. **Read the headlines and posts in the JSON yourself** and give your own one-paragraph reading of the mood: what people are excited or worried about, and whether it is grounded in a real event. The lexicon score misses sarcasm, memes and context; your reading is the useful part.
2. Report buzz as a number ("8 Reddit posts in 24h vs about 0.5 a day before").
3. **Treat a spike as a risk, never as a reason to buy.** If `pump_risk` is elevated or high, say so first: loud, promotional chatter ("10x", "multibagger", "target in N days", Telegram/WhatsApp groups) with no news to explain it is the pattern of social-media pump-and-dump schemes that SEBI acts against, and late buyers are usually the exit liquidity. `/dalal-risk` carries this as a warning.
4. Positive sentiment is not an edge. Crowds are often most bullish near the top of a move.

## Limits

Reddit rate-limits unauthenticated access; when it fails the skill says "news only". X/Twitter and Telegram are not covered (paid or closed APIs). Indian retail chatter skews toward small caps, so large caps may show little social data.

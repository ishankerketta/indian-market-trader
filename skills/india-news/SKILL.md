---
name: india-news
description: Track breaking news and NSE filings for Indian stocks - Yahoo Finance, Google News India (Moneycontrol, ET, Business Standard, Mint), NSE corporate announcements and board meetings - tagged (results, order wins, deals, fundraise, regulatory) with today's move. Flags results due soon. Use when the user asks what is moving a stock, for news on a watchlist, or before entering a day trade.
---

# News Monitor (India)

```bash
python3 <skill-dir>/news.py --tickers RELIANCE,TCS [--hours 12]
python3 <skill-dir>/news.py --from-scan          # candidates from trader/scan.json
python3 <skill-dir>/news.py                      # the watchlist
```

Writes `trader/news.json`. Times are IST.

## What to do with it

- Read the headlines yourself; the tone score is a word list, a first pass only. Summarise what actually moved the stock in one or two lines per name.
- If `results_soon` is set (board meeting for results within 3 days, or headlines say so), say it plainly: a day trade must be flat before the announcement, and many traders skip results days entirely. `/india-risk` repeats this as a warning.
- Distinguish news that explains a breakout (order win, results beat) from a breakout with no news at all. The second is worth pairing with `/india-sentiment` to check for social-media promotion.
- Regulatory tags (SEBI, penalty, probe, NCLT, insolvency) deserve a clear mention even when the tone looks positive.

## Limits

NSE's website blocks scripted access at times; filings then come back empty and only Yahoo and Google News remain. Google News RSS times are approximate. Nothing here is investment advice.

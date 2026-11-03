---
name: dalal-deals
description: Track "smart money" disclosures on NSE - today's bulk deals and block deals, and insider trades by promoters and directors filed under SEBI's insider trading rules - aggregated by stock with net buy/sell value in crore. Use when the user asks who is buying or selling a stock, about bulk/block deals, promoter buying, or insider activity.
---

# Smart Money Tracker

```bash
python3 <skill-dir>/deals.py bulk  [--symbols A,B | --watchlist] [--min-value-cr 1]
python3 <skill-dir>/deals.py block [--symbols A,B | --watchlist]
python3 <skill-dir>/deals.py insider [--days 7] [--symbols A,B | --watchlist]
```

Writes `dalal/deals.json`.

- **Bulk deal**: one client trading more than 0.5% of a company's listed shares in a day (disclosed the same evening).
- **Block deal**: a large trade done in the exchange's block-deal window.
- **Insider (PIT)**: promoters, directors and designated persons disclosing their trades under SEBI's Prohibition of Insider Trading rules, usually within a few days.

## How to present it

Lead with the stocks with the largest net value, name the clients, and note the context: a fund buying in a bulk deal is different from a promoter selling, and a pledge-related or inter-se promoter transfer (see `mode`) is not a market view at all. Promoter buying in the open market is the disclosure people watch most.

These are public filings, often days old by the time they matter, and often one side of a negotiated trade. They are context, not a signal: never present them as a reason to buy or sell.

Run bulk and block after about 17:00 IST, when NSE publishes the day's file. NSE's website sometimes blocks scripted access; if a fetch fails, try again later.

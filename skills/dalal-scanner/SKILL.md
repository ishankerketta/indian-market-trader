---
name: dalal-scanner
description: Scan NSE stocks (Nifty 500 by default) for intraday setups - opening-range breakouts during the session, and end-of-day/pre-market setups (20-day breakouts, 52-week highs, oversold bounces, volume spikes, gaps, NR7). Use when the user asks what is breaking out, what to watch today, or to build a watchlist for Indian stocks.
---

# Chart Scanner (NSE)

Scans charts with free Yahoo Finance data (`.NS` tickers) and NSE's index lists. Standard-library Python, nothing to install. Scripts sit next to this file; run them from the user's project folder (state goes to `./dalal/`).

## Commands

```bash
python3 <skill-dir>/scan.py universe [--source nifty500|nifty100|all]   # once a day, or when stale
python3 <skill-dir>/scan.py daily [--top 25]          # after 15:30 or before 09:15: setups -> dalal/watchlist.json
python3 <skill-dir>/scan.py orb [--at HH:MM]          # after 09:30: opening-range breakouts on the watchlist
python3 <skill-dir>/scan.py orb --all                 # the whole universe (slower: one request per stock)
```

`<skill-dir>` is the folder containing this SKILL.md.

## How to use it

1. Before the open (or the evening before): `universe`, then `daily`. Present the top names and their setups in a short table, then the watchlist that was saved.
2. After 09:30 IST: `orb`. A candidate has CLOSED a 5-minute bar beyond its 15-minute opening range (09:15-09:30). Rank by `rvol` (volume so far vs the same window on prior days) and how far past the range it closed.
3. Hand the best one or two to `/dalal-news` and `/dalal-sentiment`, then `/dalal-entry`.

## Reading the output

- `beyond%` tiny (under ~0.1%) means a marginal break; wide ranges (`or_width_pct` > 2%) make the stop expensive.
- `rvol` above 1.5 means unusual participation; below 1 is a weak breakout.
- Longs only by default. Shorts need `"allow_short": true` in `dalal/config.json`.
- Trade-to-trade stocks (BE/BZ series) are excluded because they cannot be traded intraday.

## Limits to say out loud

Yahoo's chart endpoint is unofficial and can lag a minute or two, rate-limit, or miss bars. Bars are 5-minute, not ticks. A scan is a list of charts that match a rule, not a recommendation. Never call a candidate a buy.

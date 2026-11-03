---
name: dalal-timemachine
description: Before risking a rupee, replay the rest of the trading session 10,000 times from the stock's own recent 5-minute candles and re-run the same rule on ~60 past NSE sessions, giving honest odds of target vs stop and expected result after charges. Use when the user asks for the odds of a trade, a backtest of an opening-range breakout, or whether a setup has an edge.
---

# Time Machine

```bash
python3 <skill-dir>/timemachine.py run [--sims 10000] [--seed 42] [--lookback 59] [--write]
```

Reads `dalal/plan.json`. Two checks, both net of charges:

1. **Simulation**: each remaining 5-minute candle until flat-by is drawn from that stock's candles at the same time of day over the last N sessions, chained from the entry. Gaps through a level fill at the open; a candle that touches both stop and target counts as the stop (conservative).
   Candles are **scaled to today's pace**: today's average candle range so far divided by the normal range at the same times (clamped 0.5x-4x). On an event day (results, big news) unscaled normal-day candles badly understate how far price can travel; this was seen live on RELIANCE's results day. The unscaled odds are shown alongside whenever the ratio is far from 1, and `--no-vol-scale` turns it off.
2. **History**: the same rule (same opening range, entry window, stop rule and R target) re-run on each of those real sessions.

Report: target-first %, stop-first %, still-open-at-flat-by %, the average result per share and in R after charges, the 5th-95th percentile range, the history tally, the seed (so anyone can repeat it) and the verdict.

**Be honest about what it is.** Built from the last ~60 days of 5-minute bars, it cannot know about tomorrow's results, a halt, a circuit, a block deal or a headline. Resampling candles independently also ignores intraday momentum. If the verdict says coin flip or negative, say so plainly and do not talk the user into the trade. A positive result on 60 sessions is weak evidence, not proof of an edge.

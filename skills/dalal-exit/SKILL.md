---
name: dalal-exit
description: Set the stop-loss, target and flat-by time for an intraday NSE trade before entering, with reward-to-risk shown after Indian trading charges. Use when the user asks where to put a stop or target, or to plan the exit of a day trade.
---

# Exit Planner

```bash
python3 <skill-dir>/exit.py plan [--stop or-mid|or-low|atr:1.5|pct:0.8] [--target 1.5R|2R|pct:1.2] [--write]
python3 <skill-dir>/exit.py show
```

Reads `dalal/entry.json` (must be `triggered`, or pass `--force`). With `--write` saves `dalal/plan.json`.

- Entry is the current price when the setup is still inside the chase limit (not a stale trigger close).
- Stops: `or-mid` (middle of the opening range, tight), `or-low` (bottom of the range, wider), `atr:K` (K x 5-minute ATR), `pct:P`.
- Targets: multiples of risk (`2R`) or a percentage.
- Flat-by defaults to 15:10 IST, before brokers auto-square MIS positions (around 15:15-15:20).
- Prices are rounded to NSE tick sizes.

Show the plan and the net reward:risk. **If the script warns that charges are a large share of the risk per share, explain it**: a tight stop on a cheap stock can mean STT, brokerage and fees eat a big part of every win. Suggest a wider stop with a smaller position rather than ignoring it.

The plan is a plan, not a guarantee: in a fast market or a gap a stop can fill well past its price.

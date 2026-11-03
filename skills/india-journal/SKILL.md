---
name: india-journal
description: Review paper and logged live intraday trades net of charges - win rate, average win/loss, profit factor, expectancy in rupees and R, charges as a share of profit, max drawdown, losing streaks, results by outcome, weekday and hour, rule breaks - plus a go-live readiness check on the paper record. Use when the user asks how their trading is going, for a weekly review, or whether they are ready to trade real money.
---

# Trading Journal

```bash
python3 <skill-dir>/journal.py [--source paper|live|all]
```

Reads `trader/paper_ledger.json` (from `/india-broker` sync) and `trader/live_ledger.json` (from `ticket.py record-exit`). Writes `trader/journal.json`.

## Go-live readiness (paper record)

At least 20 trades across 10+ trading days, positive expectancy after charges, profit factor of at least 1.2, max drawdown within twice the daily loss limit, and no days over the trade-count or daily-loss limits. All must pass.

## How to present it

- Start with the honest headline: net result after charges and the expectancy per trade.
- Point out the one or two patterns that matter (for example "all the losses came after 13:00" or "charges ate 40% of gross profit"), but with fewer than ~30 trades, call patterns tentative.
- If readiness fails, say which checks failed and what would fix them. **Do not help the user talk themselves past a failed check.** Switching `"paper": false` is their decision, made deliberately in the config file, not in the middle of a session.
- If live results diverge from paper, look first at slippage (fills worse than the limit), skipped stops and trades taken outside the plan.

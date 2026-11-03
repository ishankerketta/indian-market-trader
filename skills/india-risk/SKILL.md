---
name: india-risk
description: Check every draft intraday order against the user's limits and NSE rules - max loss per trade, daily loss limit, trades per day, net reward-to-risk, entry window, position size, cash, trade-to-trade series, circuit bands and room below the circuit - plus warnings for results days and social-media pump risk. PASS or BLOCK with reasons. Use before any order is approved.
---

# Risk Manager

```bash
python3 <skill-dir>/check.py [--id ORDER_ID]
```

Marks each checked order `READY` or `BLOCKED` in `trader/orders.json` and writes `trader/risk.json`.

**Blocks**: loss at the stop over `max_loss_per_trade`; today's losses plus open risk plus this trade over `daily_loss_limit`; `max_trades_per_day` reached; net reward:risk under `min_reward_risk`; outside the entry window; under 20 minutes to flat-by; position over `max_position_pct`; not enough cash; BE/BZ (trade-to-trade) series; circuit band tighter than `min_band_pct` (2% and 5% band stocks); target or entry within `circuit_buffer_pct` of the circuit limit; shorts or leverage when they are switched off.

**Warnings** (shown, not blocking): results or a board meeting within 3 days (`/india-news`), elevated or high pump risk (`/india-sentiment`), a support/resistance line between entry and target (`/india-levels`), stock not found in NSE's security list.

Report every BLOCK with its reason. **Never suggest loosening a limit just to get a trade through.** If the user wants to change a limit, they edit `trader/config.json` themselves, deliberately, outside the heat of a trade. Treat warnings seriously: say what they mean in one sentence each.

Only `READY` orders can move to `/india-broker`, and the check expires after 15 minutes.

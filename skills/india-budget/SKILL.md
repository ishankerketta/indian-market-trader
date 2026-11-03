---
name: india-budget
description: Size an intraday NSE position to the user's capital and maximum loss per trade, charges included, and write one bracket order ticket (entry limit, stop, target, flat-by). Use when the user asks how many shares to buy, how much to risk, or to prepare an order.
---

# Budget Manager

```bash
python3 <skill-dir>/size.py [--capital 100000] [--max-loss 500] [--write]
```

Reads `trader/plan.json` and `trader/config.json`. With `--write` adds a DRAFT order to `trader/orders.json`. Nothing is sent anywhere.

- Quantity is the largest number of shares whose loss at the stop, including round-trip charges, stays within `max_loss_per_trade`.
- Then capped by `max_position_pct` of capital and by available paper cash.
- Entry is a LIMIT at the plan price plus a small buffer (`entry_buffer_pct`, default 0.1%); many brokers block market orders sent through APIs.
- Leverage (MIS margin) is off by default. With `"use_leverage": true` the position cap is multiplied by `mis_leverage`. Say clearly that leverage multiplies losses as well as gains.

First run: if `trader/config.json` does not exist, ask the user for their capital and the most they are willing to lose on one trade and in one day, and write the file (start from `config.example.json` in this folder). Suggest keeping the per-trade loss to about 0.5-1% of trading capital. Also ask which broker they use (for `"broker_profile"`) and whether they are a designated person at any listed company: those symbols go in `"pit_restricted"` so the Risk Manager blocks them.

Show quantity, value, margin, loss at the stop and profit at the target in rupees after charges.

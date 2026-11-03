---
name: india-charges
description: Calculate the real cost of an Indian intraday equity trade - brokerage, STT, NSE transaction charges, SEBI fee, stamp duty, GST - with net P&L and the breakeven price. Use when the user asks about charges, brokerage, breakeven, or why their P&L is lower than expected.
---

# Charges Calculator

```bash
python3 <skill-dir>/charges.py --buy 2450 --sell 2470 --qty 40 [--profile discount|flat20|zero|full_service]
python3 <skill-dir>/charges.py --buy 2450 --qty 40 --breakeven
python3 <skill-dir>/charges.py --from-plan        # the current plan at its stop and its target
```

Statutory rates built in (equity intraday, NSE, 2026): STT 0.025% on the sell side; NSE transaction 0.00297%; IPFT 0.0001%; SEBI Rs 10/crore; stamp duty 0.003% on the buy side; GST 18% on brokerage + exchange + SEBI + IPFT. Brokerage profiles: `discount` (0.03% or Rs 20 per order, whichever is lower), `flat20`, `zero`, `full_service` (0.05%).

Rates change with budgets and exchange circulars, and some brokers bundle clearing into a higher exchange charge. Tell the user to compare one real contract note and put any differences in `trader/config.json` under `"rates"` (for example `{"exchange_txn": 0.0000322}`) and `"broker_profile"`.

Useful framing: charges are a fixed tax on every round trip. On small, frequent trades they can turn a strategy that wins slightly more often than it loses into a losing one.

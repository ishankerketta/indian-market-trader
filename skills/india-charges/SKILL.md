---
name: india-charges
description: Calculate the real cost of an Indian intraday equity trade - brokerage, STT, NSE transaction charges, SEBI fee, stamp duty, GST - with net P&L and the breakeven price. Use when the user asks about charges, brokerage, breakeven, or why their P&L is lower than expected.
---

# Charges Calculator

```bash
python3 <skill-dir>/charges.py --buy 2450 --sell 2470 --qty 40 [--profile discount|flat20|zero|full_service]
python3 <skill-dir>/charges.py --buy 2450 --qty 40 --breakeven
python3 <skill-dir>/charges.py --from-plan        # the current plan at its stop and its target
python3 <skill-dir>/charges.py --buy 300 --sell 306 --qty 30 --compare   # Zerodha, Angel One, Dhan, Upstox, Groww, FYERS
```

Statutory rates built in (equity intraday, NSE, 2026): STT 0.025% on the sell side; NSE transaction 0.00297%; IPFT 0.0001%; SEBI Rs 10/crore; stamp duty 0.003% on the buy side; GST 18% on brokerage + exchange + SEBI + IPFT. Broker profiles (equity intraday, per order): `zerodha`, `dhan`, `fyers` 0.03% or Rs 20; `angelone`, `groww` 0.1% or Rs 20 with a Rs 5 minimum; `upstox` 0.1% or Rs 20; plus generic `discount`, `flat20`, `zero`, `full_service`. Exchanges cap cash brokerage at 2.5% of order value. On large orders every broker hits its Rs 20 cap; the differences show on small orders. Set the user's broker as `"broker_profile"` in `trader/config.json`. The script warns when its rates are more than 120 days old.

Rates change with budgets and exchange circulars, and some brokers bundle clearing into a higher exchange charge. Tell the user to compare one real contract note and put any differences in `trader/config.json` under `"rates"` (for example `{"exchange_txn": 0.0000322}`) and `"broker_profile"`.

Useful framing: charges are a fixed tax on every round trip. On small, frequent trades they can turn a strategy that wins slightly more often than it loses into a losing one.

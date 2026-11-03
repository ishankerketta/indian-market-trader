---
name: india-alerts
description: Price and time alerts for NSE stocks - ring once when a stop, target or price level is touched, or at a set time such as the 15:10 flat-by. Use when the user wants to be told when a stock hits a price, or reminded to close intraday positions.
---

# Price Alerts

```bash
python3 <skill-dir>/alerts.py add --from-plan              # stop, target and flat-by from trader/plan.json
python3 <skill-dir>/alerts.py add SYMBOL --above 2500 [--note "..."]
python3 <skill-dir>/alerts.py add SYMBOL --below 2400
python3 <skill-dir>/alerts.py add --at 15:10 --note "flatten everything"
python3 <skill-dir>/alerts.py check                        # ring anything touched since it was set
python3 <skill-dir>/alerts.py watch [--every 60]           # loop until all rang or 15:30
python3 <skill-dir>/alerts.py list | clear [--fired]
```

A price alert rings if any 1-minute bar since it was created traded through the level, so a quick touch between checks is not missed. Each alert rings once.

For hands-off monitoring, offer to set up a scheduled task that runs `check` every few minutes during market hours (09:15-15:30 IST, Monday to Friday) and notifies the user, rather than holding a long loop open. Market holidays have no bars, so nothing will ring.

When the flat-by alert rings, remind the user that brokers auto-square MIS positions shortly after and may charge for it.

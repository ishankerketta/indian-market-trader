---
name: dalal-entry
description: Watch an NSE opening-range-breakout setup bar by bar and say waiting, triggered or expired - including refusing to chase a stock that ran too far past the trigger. Use when the user wants to know if it is time to enter a stock, or to wait for a breakout.
---

# Entry Timer

```bash
python3 <skill-dir>/entry.py check SYMBOL [--side long] [--at HH:MM]
python3 <skill-dir>/entry.py watch SYMBOL [--every 30]     # loops until triggered or expired
```

Writes `dalal/entry.json`, which `/dalal-exit` reads.

## Rules it applies

- **waiting**: the 15-minute opening range (09:15-09:30 IST) is still forming, or no 5-minute bar has CLOSED beyond it yet. A bar that is still forming does not count.
- **triggered**: the first 5-minute close beyond the range, inside the entry window (default 09:30-14:30), and price is still within `max_chase_pct` (default 1%) of the trigger.
- **expired**: the window closed, price ran more than 1% past the trigger (do not chase), or the breakout failed back through the far side of the range.

Report the status in one line with the range, the trigger close and the time. If expired for chasing, say why waiting for the next setup beats paying up.

For `watch`, prefer a scheduled check or the user re-asking over a long blocking loop; the script sleeps between checks.

---
name: india-pulse
description: One-screen brief on the Indian market - NIFTY, BANKNIFTY, SENSEX and India VIX, NIFTY's trend vs its 20/50-day averages, a risk-on/mixed/risk-off regime label, FII/DII cash flows, sector leaders and laggards, NIFTY 500 breadth, pre-open gaps, today's trading status and the next NSE holiday. Use for "pre-market brief", "how is the market today", "what are FIIs doing", or before a trading session. Works for Hindi/Hinglish questions too.
---

# Market Pulse

```bash
python3 <skill-dir>/pulse.py              # any time
python3 <skill-dir>/pulse.py --preopen    # force the 09:00-09:15 pre-open gaps section
```

Writes `trader/pulse.json`. Each section fails on its own (NSE sometimes refuses scripted access), so report what came back and say plainly what was unavailable.

## Presenting it

Lead with one sentence of context: the regime label and why (trend plus VIX). Then the numbers in a compact list. Translate VIX into plain terms: the script prints the typical daily NIFTY move it implies (VIX / sqrt(252)), and a high VIX means stops get hit more often and positions should be smaller.

- FII selling and DII buying on the same day is common; one day of flows says little, so describe streaks only if the user has several days of data.
- Breadth (advances vs declines across the NIFTY 500) shows whether a move is broad or carried by a few heavyweights.
- If NSE is closed today (weekend or holiday), say so first and offer the daily scan for the next session.

The regime label describes the backdrop. It does not pick trades and is not a forecast.

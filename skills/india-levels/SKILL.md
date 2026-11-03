---
name: india-levels
description: Draw the few support and resistance levels that matter on a clean chart of an NSE stock or index (NIFTY, BANKNIFTY, SENSEX) - the 4-week high and low, up to 3 major lines where the most swing peaks and troughs line up over 4 weeks, and 3-5 short-term lines from the last 3 sessions. Use when the user asks for levels, support/resistance, key prices, or a chart with lines.
---

# Levels

```bash
python3 <skill-dir>/levels.py SYMBOL            # e.g. TCS, NIFTY, BANKNIFTY
python3 <skill-dir>/levels.py SYMBOL [--weeks 4] [--major 3] [--short 5] [--short-days 3] [--no-chart]
```

Writes `trader/levels.json` (one entry per symbol) and `trader/levels_SYMBOL.html`, a self-contained chart with two panels: the last 4 weeks in 30-minute candles with the range and major lines, and the last 3 sessions in 5-minute candles with the short-term lines (majors shown faintly if in view).

## How the lines are chosen

- **Range**: the highest high and lowest low of the last 20 sessions, up to the latest bar.
- **Major (max 3)**: swing highs and lows on 15-minute bars (the extreme of an hour either side) are grouped when they fall within a tolerance band (about 0.12% of price or a third of a typical bar, whichever is wider). A line needs at least 3 touches. Lines that held across several sessions, or acted as both support and resistance, rank higher.
- **3-day (3-5)**: the same on 5-minute bars of the last 3 sessions, needing 2 touches.
- **Kept sparse on purpose**: each line removes its touch points, and no line may sit within two bands of another, or within 6% (major) / 9% (3-day) of the chart's height. If fewer than 3 short-term levels qualify, it shows fewer rather than padding with weak ones.

## Presenting it

Show the chart to the user (publish the HTML file as an artifact, or send the file). Then summarise in a few lines: where price is, the nearest support and resistance and how far away they are, and which line has the most touches. If price is above the 4-week high or below the 4-week low, say there is no level beyond it rather than inventing one.

Levels connect to the rest of the pack: `/india-exit` accepts `--stop level` (just beyond the nearest support) and `--target level` (just in front of the nearest resistance), and `/india-risk` warns when a target sits beyond a level.

Levels describe where price reacted before, not where it must react again. Lines drawn from 4 weeks of data say nothing about a results announcement or a news shock.

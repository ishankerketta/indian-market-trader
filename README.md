# Indian Market Trader

12 Claude skills for intraday trading on NSE India: scan Nifty 500 charts for breakouts, read the news and the social-media mood, time every entry and exit, replay the odds after charges before you risk a rupee, then size, risk-check and paper trade the order.

Free, MIT, no signup, no API key. Plain standard-library Python reading free public data: Yahoo Finance (`.NS` bars), NSE's archives and website, Google News India and Reddit.

**No trade goes through until you say yes.** Nothing in this pack can place an order on its own. Paper trading is the default, and the paper ledger counts every rupee of STT, brokerage and GST.

## Install

Paste this into Claude:

```
https://github.com/ishankerketta/indian-market-trader

install skill
```

Or as a plugin in Claude Code:

```
/plugin marketplace add ishankerketta/indian-market-trader
/plugin install indian-market-trader@indian-market-trader
```

Or copy the folders (keep `_dalal`, the shared library, next to the skills):

```
git clone https://github.com/ishankerketta/indian-market-trader.git
cp -r indian-market-trader/skills/* ~/.claude/skills/
```

Needs Python 3.8+. Nothing to pip install. The first time you size a trade, Claude asks for your capital and loss limits and writes `dalal/config.json` (see `skills/dalal-budget/config.example.json`).

## The twelve

| command | job | what it does |
|---|---|---|
| `/dalal-scanner` | Chart Scanner | Scans Nifty 500 (or all NSE) for opening-range breakouts, 20-day breakouts, 52-week highs, oversold bounces, volume spikes, gaps |
| `/dalal-news` | News Monitor | Yahoo, Google News India, NSE filings and board meetings; tags results, order wins, deals, regulatory news; flags results days |
| `/dalal-sentiment` | Sentiment & Buzz | News and Reddit (r/IndianStreetBets and friends) tone, mention spikes vs normal, and a pump-and-dump risk flag |
| `/dalal-entry` | Entry Timer | Watches the setup bar by bar: waiting, triggered, or expired (and refuses to chase) |
| `/dalal-exit` | Exit Planner | Stop, target and a 15:10 flat-by before you enter, rounded to NSE ticks, reward:risk after charges |
| `/dalal-timemachine` | Time Machine | 10,000 replays of the rest of the session from the stock's own candles, plus the same rule on ~60 past sessions, net of charges |
| `/dalal-costs` | Charges Calculator | STT, NSE fees, SEBI fee, stamp duty, GST and brokerage, net P&L and breakeven |
| `/dalal-budget` | Budget Manager | Sizes the position so the loss at the stop, charges included, stays within your limit |
| `/dalal-risk` | Risk Manager | Daily loss limit, trades per day, entry window, T2T series, circuit bands, results days, pump risk: PASS or BLOCK |
| `/dalal-broker` | Order Executor | Paper ledger by default; live mode prepares exact orders for your broker, never without your yes |
| `/dalal-alerts` | Price Alerts | Rings on the stop, the target, any level, and at flat-by |
| `/dalal-deals` | Smart Money Tracker | NSE bulk and block deals, and promoter/director trades filed under SEBI's insider rules |

## How a trade flows

Everything lands in a `dalal/` folder in your project, and each skill reads what the last one wrote:

```
scanner -> news -> sentiment -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by 15:10                                                       (while it is open)
scanner daily / deals / sentiment                                                         (before the open, after the close)
```

A walkthrough on the **synthetic test data** in `tests/` (made-up company TESTCO, not a real stock), so you can see each step's job:

1. **`/dalal-scanner`** at 09:41 IST: TESTCO closed the 09:35 five-minute bar at 1707.63, above its 09:15-09:30 range of 1704.78-1707.31.
2. **`/dalal-news`**: an order win and strong results headlines in the last 12 hours.
3. **`/dalal-sentiment`**: Reddit mentions at 16x their normal rate, full of "10x multibagger" and "Telegram group" talk. Pump risk: **high**.
4. **`/dalal-entry`**: triggered, last price 1718.72, still inside the 1% chase limit. (At 12:30 the same check says expired: it ran away, do not chase.)
5. **`/dalal-exit`**: entry 1718.72, stop at the range low 1704.70, target 2.5R 1753.70, flat by 15:10. Reward:risk 2.5 gross, 2.09 after charges.
6. **`/dalal-timemachine`** (seed 42, so anyone can repeat it): in 10,000 replays the target came first 28.1% of the time, the stop 23.5%, and 48.3% were still open at flat-by. On the 59 past sessions the same rule fired 54 times: 19 targets, 26 stops, 9 neither.
7. **`/dalal-budget`** with ₹1,00,000 capital and ₹500 max loss: 28 shares, loss at the stop about ₹493 including charges.
8. **`/dalal-risk`**: PASS, with a loud warning about the pump risk.
9. **`/dalal-broker`**: the ticket in plain words; you type yes; the paper ledger fills 28 at the 1720.50 limit and exits at the target at 12:55, net ₹877.80 after ₹51.80 of charges.

With a 2R target instead of 2.5R, the same trade was **blocked**: after the limit-price buffer and charges, net reward:risk came to 1.38, under the 1.5 minimum. That's the point: look before you risk a rupee.

## The tools

```
python3 skills/dalal-scanner/scan.py universe                  # Nifty 500 from NSE
python3 skills/dalal-scanner/scan.py daily                     # setups -> watchlist
python3 skills/dalal-scanner/scan.py orb                       # opening-range breakouts so far
python3 skills/dalal-news/news.py --from-scan                  # headlines, filings, today's move
python3 skills/dalal-sentiment/sentiment.py --from-scan        # tone, buzz, pump risk
python3 skills/dalal-entry/entry.py check TCS                  # waiting / triggered / expired
python3 skills/dalal-exit/exit.py plan --stop or-low --target 2R --write
python3 skills/dalal-timemachine/timemachine.py run --write    # 10,000 replays + history
python3 skills/dalal-costs/charges.py --from-plan              # charges at stop and target
python3 skills/dalal-budget/size.py --write                    # -> dalal/orders.json
python3 skills/dalal-risk/check.py                             # PASS / BLOCK
python3 skills/dalal-broker/ticket.py show | approve ID --yes | sync | ledger
python3 skills/dalal-alerts/alerts.py add --from-plan ; alerts.py check
python3 skills/dalal-deals/deals.py bulk | block | insider
```

Tests run offline on synthetic fixtures in the exact shapes the data sources return:

```
python3 -m unittest discover -s tests -v
```

Check every live data source in one go (run it on your own machine; paste the output into an issue if something fails):

```
python3 tests/live_check.py RELIANCE
```

Replay any moment with `DALAL_NOW=2026-11-02T09:41`. Point the tools at saved data with `DALAL_FIXTURES=folder`.

## Fine print

**Not investment advice.** This is software that reads public data and does arithmetic on rules you choose. It does not know your situation and cannot see the future. It is not a SEBI-registered investment adviser or research analyst, and nothing it prints is a recommendation to buy or sell.

**Most intraday traders lose money.** SEBI's own study of the cash segment found about seven in ten individual intraday traders made losses in FY2022-23, and its F&O study found about nine in ten lost money. Charges are a big part of why. Paper trade first, for weeks, and judge the ledger's net numbers.

**No trade without your yes.** Only `/dalal-broker` can lead to an order, only for a ticket that passed `/dalal-risk` in the last 15 minutes, and only after you type yes for that exact ticket. In live mode the script itself sends nothing; if you connect a broker MCP (Zerodha Kite, Upstox, Angel One), set its order tools to "needs approval" so Claude's approval card is a second check. Shorts and leverage are off unless you turn them on.

**SEBI's retail algo rules.** Since 1 April 2026, orders sent through a broker API must come through the broker's compliant setup (registered static IP, exchange-tagged orders). One human-approved order at a time is far below the 10-orders-a-second line where formal algo registration starts, but your broker's API rules still apply.

**The Time Machine is a simulation, not a prediction.** It is built from the last ~60 sessions of 5-minute bars. Results, circuits, halts, block deals and headlines can do what those days never did.

**A stop is a plan, not a guarantee.** In a fast market, a gap or a circuit, a stop can fill far past its price, or not at all at a lower circuit.

**The data is free and unofficial.** Yahoo's chart endpoint and NSE's website are not official APIs: they lag, change and rate-limit. NSE blocks scripted access at times. Bars are 1- and 5-minute, not ticks. Check anything that matters in your broker's terminal. This tool is for personal use of public data; it does not redistribute market data.

**Charges change.** Rates are 2026 statutory figures for NSE equity intraday. Compare one real contract note and override them in `dalal/config.json`.

**Taxes.** Intraday equity profits are generally speculative business income in India, taxed at your slab rate, and speculative losses can only be set off against speculative gains. Nothing here is tax advice.

**Social media is not a signal.** A spike in chatter is flagged as risk. Pump-and-dump schemes run through Telegram, WhatsApp and social media, and late buyers are usually the exit liquidity.

## Roadmap

- `/dalal-analyst`: quarterly results summaries from NSE XBRL filings
- First-class broker connectors (Kite, Upstox) for live order placement behind the approval protocol
- Index options (Nifty, Bank Nifty) as a separate, clearly fenced pack

## Credit

Inspired by Jake Schincariol's [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) for US markets (MIT). This is an independent rewrite for NSE: Indian data sources, IST sessions, charges, circuit bands, trade-to-trade series, SEBI rules and social sentiment.

MIT. Made by [Ishan Savio Kerketta](https://ishansavio.com).

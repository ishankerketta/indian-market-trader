# Indian Market Trader

15 Claude skills for intraday trading on NSE India: a pre-market pulse, a Nifty 500 breakout scanner, the support and resistance levels that matter, news and social-media sentiment, entry and exit timing, a Time Machine that replays the odds after charges, sizing, a SEBI-aware risk check, paper trading, a journal that tells you honestly whether you're ready for real money, and connections to **Angel One, Dhan, Zerodha, Upstox, FYERS and Groww** (plus about 40 more brokers through OpenAlgo).

Free, MIT, no signup. Plain standard-library Python reading free public data: Yahoo Finance (`.NS` bars), NSE's archives and website, Google News India and Reddit.

**No trade goes through until you say yes.** Paper trading is the default. Live orders need you to switch paper off yourself, a fresh risk PASS, and your typed yes for that exact ticket. Every rupee of STT, brokerage and GST is counted.

**Status: beta (v0.3, November 2026).** Market data, scanning, levels, sentiment, the Time Machine, charges, sizing, risk checks and paper trading have been run against live NSE data. Broker connections: Angel One login and read-only calls (positions, orders) are verified on a real account. Placing orders, and the Dhan, Zerodha, Upstox, FYERS and Groww adapters, are built from each broker's public API docs and not yet tested with real money: start on paper, then one share. Tested on macOS. Windows should work (type `py` instead of `python3`, and log in to brokers from PowerShell) but is not yet tested. If something breaks, please open an issue with the output.

Not investment advice, and most intraday traders lose money: read the fine print at the end before using real money.

Ask in English, Hindi or Hinglish ("aaj market kaisa hai?", "RELIANCE ke levels dikhao").

## Install

**Claude Code (recommended):**

```
/plugin marketplace add ishankerketta/indian-market-trader
/plugin install indian-market-trader@indian-market-trader
```

Commands then appear as `/indian-market-trader:india-scanner` and so on. Or copy the folders, keeping `_shared` next to the skills:

```
git clone https://github.com/ishankerketta/indian-market-trader.git
cp -r indian-market-trader/skills/* ~/.claude/skills/
```

**Claude app (web/desktop):** run `python3 tools/build_app_zips.py` and upload each ZIP under Customize > Skills > + > Upload a skill, with code execution switched on. The scripts fetch Yahoo, NSE, Google News and Reddit, so allow those domains in your Claude settings or the sandbox will refuse them. Claude Code on your own machine has no such limit.

Needs Python 3.8+ and nothing else. The first time you size a trade, Claude asks for your capital, loss limits, broker and any companies you're an insider at, and writes `trader/config.json` (see `skills/india-budget/config.example.json`).

## The fifteen

| command | job | what it does |
|---|---|---|
| `/india-pulse` | Market Pulse | NIFTY, BANKNIFTY, SENSEX, India VIX, trend and regime, FII/DII flows, sectors, breadth, pre-open gaps, holidays |
| `/india-scanner` | Chart Scanner | Nifty 500 opening-range breakouts during the session; 20-day breakouts, 52-week highs, oversold bounces, volume spikes and gaps for the watchlist |
| `/india-news` | News Monitor | Yahoo, Google News India, NSE filings and board meetings; tags results, order wins, deals and regulatory news; flags results days |
| `/india-sentiment` | Sentiment & Buzz | News and Reddit (r/IndianStreetBets and friends) tone, mention spikes vs normal, and a pump-and-dump risk flag |
| `/india-levels` | Levels | The 4-week high and low, up to 3 major support/resistance lines and 3-5 three-day lines on a clean chart of any stock or index |
| `/india-entry` | Entry Timer | Watches the setup bar by bar: waiting, triggered, or expired (and refuses to chase) |
| `/india-exit` | Exit Planner | Stop, target and a 15:10 flat-by, on NSE ticks or at levels, with reward:risk after charges |
| `/india-timemachine` | Time Machine | 10,000 replays of the rest of the session from the stock's own candles, scaled to today's pace, plus the same rule on ~60 past sessions |
| `/india-charges` | Charges Calculator | STT, NSE fees, SEBI fee, stamp duty, GST and brokerage for six brokers side by side, net P&L and breakeven |
| `/india-budget` | Budget Manager | Sizes the position so the loss at the stop, charges included, stays within your limit |
| `/india-risk` | Risk Manager | Daily loss limit, trades per day, entry window, SEBI insider guard, holidays, ASM/GSM, T2T series, live circuit limits, results days, pump risk, levels in the way: PASS or BLOCK |
| `/india-broker` | Order Executor | Paper ledger by default; live orders via Angel One, Dhan, Zerodha, Upstox, FYERS, Groww or OpenAlgo, never without your yes |
| `/india-alerts` | Price Alerts | Rings on the stop, the target, any level, and at flat-by |
| `/india-deals` | Smart Money Tracker | NSE bulk and block deals; promoter/director trades under SEBI's insider rules (experimental: NSE's endpoint currently returns no rows) |
| `/india-journal` | Trading Journal | Win rate, expectancy in rupees and R, charges, drawdown and streaks, plus a go-live readiness check |

## How a trade flows

Everything lands in a `trader/` folder in your project, and each skill reads what the last one wrote:

```
before the open:  pulse -> scanner daily -> news / sentiment / deals
one trade:        scanner orb -> levels -> entry -> exit -> timemachine -> budget -> risk -> broker
while it's open:  alerts (stop, target, flat by 15:10), broker sync
after the close:  journal
```

A walkthrough on the **synthetic test data** in `tests/` (made-up company TESTCO, not a real stock), so you can see each step's job:

1. **`/india-scanner`** at 09:41 IST: TESTCO closed the 09:35 five-minute bar at 1707.63, above its 09:15-09:30 range of 1704.78-1707.31.
2. **`/india-news`**: an order win and strong results headlines in the last 12 hours.
3. **`/india-sentiment`**: Reddit mentions at 16x their normal rate, full of "10x multibagger" and "Telegram group" talk. Pump risk: **high**.
4. **`/india-entry`**: triggered, last price 1718.72, still inside the 1% chase limit. (At 12:30 the same check says expired: it ran away, do not chase.)
5. **`/india-exit`**: entry 1718.72, stop at the range low 1704.70, target 2.5R 1753.70, flat by 15:10. Reward:risk 2.5 gross, 2.09 after charges.
6. **`/india-timemachine`** (seed 42, so anyone can repeat it): TESTCO had been moving at 0.68x its normal pace that morning, so the replayed candles were scaled down to match. In 10,000 replays the target came first 7.5% of the time, the stop 11.1%, and 81.4% were still open at flat-by. On the 59 past sessions the same rule fired 54 times: 19 targets, 26 stops, 9 neither.

   Why the scaling matters, from a real replay: on RELIANCE's results day (2 Nov 2026), unscaled replays drawn from 59 normal sessions gave a 2R target at 1289.30 a 0% chance. The stock closed at 1300. With scaling, the Time Machine measured RELIANCE moving at 2.48x its normal pace and flagged it as an event day.
7. **`/india-budget`** with ₹1,00,000 capital and ₹500 max loss: 28 shares, loss at the stop about ₹493 including charges.
8. **`/india-risk`**: PASS on every rule, including the SEBI insider guard, the holiday calendar and NSE's live circuit limit (2050.05), with a loud warning about the pump risk.
9. **`/india-broker`**: the ticket in plain words; you type yes; the paper ledger fills 28 at the 1720.50 limit and exits at the target at 12:55, net ₹877.80 after ₹51.80 of charges.
10. **`/india-journal`**: one trade is not a record. Readiness: not yet (needs 20 trades over 10 days).

With a 2R target instead of 2.5R, the same trade was **blocked**: after the limit-price buffer and charges, net reward:risk came to 1.38, under the 1.5 minimum. That's the point: look before you risk a rupee.

## Brokers

| Broker | Direct API in this pack | Official MCP connector for Claude |
|---|---|---|
| **Angel One** | entry, then stop-loss | none (use this pack or OpenAlgo) |
| **Dhan** | one Super Order: entry + target + stop-loss | `https://mcp.dhan.co/mcp` (orders incl. Super Orders) |
| **Zerodha** | Kite Connect (your own app), entry then stop | `https://mcp.kite.trade/mcp` (hosted: GTT orders only) |
| **Upstox** | entry, then stop-loss | `https://mcp.upstox.com/mcp` (read-only) |
| **FYERS** | entry, then stop-loss | `https://mcp.fyers.in/mcp` |
| **Groww** | entry, then stop-loss | `https://mcp.groww.in/mcp` (buy, limit, SL; sells need DDPI) |
| **OpenAlgo** | ~40 brokers through your own [OpenAlgo](https://github.com/marketcalls/openalgo) server | its own MCP |

MCP capabilities as published by the brokers, checked Oct-Nov 2026. They change, so Claude lists a connector's tools before using them.

**Logging in is done by you, in your own terminal:**

```
python3 skills/india-broker/connect.py login angelone      # or dhan, zerodha, upstox, fyers, groww, openalgo
```

It asks for what that broker needs (Angel One: API key, client code, PIN and a fresh TOTP from your authenticator) with hidden input and saves only the day's session token, readable only by you. It refuses to run without a real terminal, so an assistant can't log in for you, and you never paste a password or secret into the chat.

**Then, for each live order:**

```
python3 skills/india-broker/ticket.py preview ORDER_ID --broker angelone              # the exact request, secrets hidden; sends nothing
python3 skills/india-broker/ticket.py send ORDER_ID --broker angelone --live --yes      # after you typed yes
python3 skills/india-broker/ticket.py send-stop ORDER_ID --broker angelone --live --yes # once the entry fills
python3 skills/india-broker/ticket.py record-exit ORDER_ID --entry 1240.5 --exit 1262   # for the journal
```

**Static IP.** Under SEBI's retail algo framework (since 1 April 2026), brokers accept API orders only from a static IP registered with them. Read-only calls work from anywhere. Many Indian ISPs sell a static IP add-on; a small cloud server is the other route.

**The adapters are new.** They are written from each broker's public API documentation and tested offline, not yet against live accounts. Run `preview` first, start with one share, and please open an issue with the (redacted) error if a broker rejects a field.

## The tools

```
python3 skills/india-pulse/pulse.py                            # pre-market brief
python3 skills/india-scanner/scan.py universe | daily | orb     # Nifty 500, watchlist, breakouts
python3 skills/india-news/news.py --from-scan                  # headlines, filings, move
python3 skills/india-sentiment/sentiment.py --from-scan        # tone, buzz, pump risk
python3 skills/india-levels/levels.py NIFTY                    # levels + chart -> trader/levels_NIFTY.html
python3 skills/india-entry/entry.py check TCS                  # waiting / triggered / expired
python3 skills/india-exit/exit.py plan --stop or-low --target 2R --write   # or --stop level / --target level
python3 skills/india-timemachine/timemachine.py run --write    # 10,000 replays + history
python3 skills/india-charges/charges.py --buy 300 --sell 306 --qty 30 --compare   # six brokers side by side
python3 skills/india-budget/size.py --write                    # -> trader/orders.json
python3 skills/india-risk/check.py                             # PASS / BLOCK
python3 skills/india-broker/ticket.py show | approve ID --yes | sync | ledger
python3 skills/india-broker/connect.py brokers | status | orders BROKER | positions BROKER
python3 skills/india-alerts/alerts.py add --from-plan ; alerts.py check
python3 skills/india-deals/deals.py bulk | block | insider
python3 skills/india-journal/journal.py
```

Tests run offline on synthetic fixtures in the exact shapes the data sources return (40 tests):

```
python3 -m unittest discover -s tests -v
```

Check every live data source in one go on your own machine:

```
python3 tests/live_check.py RELIANCE
```

Replay any past moment with `IMT_NOW=2026-11-02T10:15` (and `IMT_DIR=trader-replay` to keep it separate).

## Fine print

**Not investment advice.** This is software that reads public data and does arithmetic on rules you choose. It is not a SEBI-registered investment adviser or research analyst, and nothing it prints is a recommendation to buy or sell.

**Most intraday traders lose money.** SEBI's own study of the cash segment found about seven in ten individual intraday traders made losses in FY2022-23, and its F&O study found about nine in ten lost money. Charges are a big part of why. Paper trade for weeks, and let `/india-journal` judge the record.

**No trade without your yes.** Only `/india-broker` can lead to an order, only for a ticket that passed `/india-risk` in the last 15 minutes, and only after you type yes for that exact ticket. Shorts and leverage are off unless you turn them on. If you use a broker's MCP connector, set its order tools to "needs approval".

**SEBI insider rules.** Put every company where you are a designated person or hold unpublished price-sensitive information in `pit_restricted`. The risk check blocks them, always.

**The Time Machine is a simulation, not a prediction.** It is built from the last ~60 sessions of 5-minute bars, scaled to today's pace. Results, circuits, halts and headlines can do what those days never did.

**A stop is a plan, not a guarantee.** In a fast market, a gap or a circuit, a stop can fill far past its price, or not at all at a lower circuit. With direct APIs other than Dhan's Super Order, the stop-loss is a separate order you must place promptly after the entry fills.

**The data is free and unofficial.** Yahoo's chart endpoint and NSE's website are not official APIs: they lag, change and rate-limit, and NSE blocks scripted access at times. Bars are 1- and 5-minute, not ticks. Check anything that matters in your broker's terminal. This is for personal use of public data; it does not redistribute market data.

**Charges change.** Rates and broker profiles are as of 3 Nov 2026 (`RATES_AS_OF` in `skills/_shared/costs.py`); the calculator warns when they are more than 120 days old. Compare one real contract note and override them in `trader/config.json`.

**Taxes.** Intraday equity profits are generally speculative business income in India, taxed at your slab rate, and speculative losses can only be set off against speculative gains. Nothing here is tax advice.

**Social media is not a signal.** A spike in chatter is flagged as risk. Pump-and-dump schemes run through Telegram, WhatsApp and social media, and late buyers are usually the exit liquidity.

## Similar projects, and what we learned from them

Indian-market Claude packs appeared fast in late 2026. These are the ones we studied (all MIT unless noted). Ideas were re-implemented here in our own code, with credit:

| Project | What it does well | What we took |
|---|---|---|
| [claude-trading-skills-india](https://github.com/Shubhamkumartrichy/claude-trading-skills-india) | 29 skills incl. F&O, Indian tax, five-broker charges, broker MCP table | Broker brokerage profiles, the market-pulse and trading-discipline ideas, the MCP endpoint table, rate staleness warnings |
| [nse-day-trader-skill](https://github.com/parinshahAIbuilder/nse-day-trader-skill) | Daily multi-setup scan with back-tests, NSE exchange data layer | SEBI insider (PIT) guard, NSE holiday calendar, ASM/GSM and live circuit checks |
| [nse-trader-skills](https://github.com/Vatsa10/nse-trader-skills) | Long-term investing, backtester, multi-agent thesis panel, data doctor | Confirmation that a live-source doctor (our `live_check.py`) is worth having |
| [indian-day-trader](https://github.com/iamsanaur/indian-day-trader), [day-trader-skill-india](https://github.com/bhardwajaditya/day-trader-skill-india), [day-trader-india](https://github.com/Fantastic792/day-trader-india) | Other India ports of the US day-trader pack (options, Kite/Upstox/Dhan tickets) | - |
| [OpenAlgo](https://github.com/marketcalls/openalgo) (AGPL-3.0) | Self-hosted unified API for ~40 Indian brokers | An optional adapter that calls its HTTP API. None of its code is included |
| [Tapetide NSE/BSE MCP](https://github.com/Tapetide-hq/nse-bse-indian-stock-market-data-mcp) | Market data MCP: quotes, financials, screener, FII/DII, option chains | Nothing directly; a good companion for fundamentals |

What this pack adds that we didn't find elsewhere: the Time Machine scaled to today's pace (and shown failing without it on a real results day), sparse support/resistance levels with a two-panel chart, social-media buzz treated as pump risk rather than a signal, Yahoo's lagging daily bars rebuilt from intraday data, terminal-only broker login with request previews, and a journal that gates going live.

## Roadmap

- Live verification of each broker adapter with community help
- Contract-note reconciliation to calibrate charges
- `/india-analyst`: quarterly results summaries from NSE filings
- Index options (Nifty, Bank Nifty) as a separate, clearly fenced pack

## Credit

Inspired by Jake Schincariol's [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) for US markets (MIT). This is an independent rewrite for NSE. Broker pricing via Shubham Kumar's claude-trading-skills-india (MIT).

MIT. Made by [Ishan Savio Kerketta](https://ishansavio.com).

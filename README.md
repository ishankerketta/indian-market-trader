# Indian Market Trader

**A free AI assistant for intraday trading on the Indian stock market (NSE).**

You ask Claude a question in plain English, Hindi or Hinglish, like *"aaj market kaisa hai?"* or *"show me RELIANCE's levels"*, and it does the homework a careful trader would do: it checks the market, finds stocks that are breaking out, reads the news, works out where to get in and out, counts every rupee of charges, and tells you honestly whether the trade is worth it.

It practises with pretend money (paper trading) by default. **It never places a real order unless you say yes.**

> **Beta.** Tested on live NSE data on a Mac. Angel One login works on a real account. Placing real orders, the other brokers, and Windows are not tested yet. Start with pretend money. Not investment advice: see [Please read](#please-read).

---

## What it does

- **Morning check:** how the market is doing, which sectors are strong, and whether big investors are buying or selling.
- **Find stocks:** scans the Nifty 500 for stocks breaking out of their morning range.
- **Levels:** draws a clean chart with the few price lines that matter.
- **News and buzz:** results, orders and filings, plus what Reddit is saying, with a warning if it smells like a pump-and-dump.
- **Plan the trade:** when to enter, where to put the stop-loss and target, and how many shares to buy so you can't lose more than your limit.
- **Odds check:** replays the rest of the day 10,000 times to show how often the target or the stop gets hit first.
- **Safety check:** blocks the trade if it breaks your rules (daily loss limit, too many trades, a holiday, a stock under watch, insider rules).
- **Place the order** with your broker, only after you say yes.
- **Journal:** keeps score and tells you when your record is good enough for real money.

## Get started

Three steps: install Python, add the skills to Claude (or ChatGPT), then ask a question.

### Step 1: Install Python (free, one time)

**Mac**
1. Download Python from [python.org/downloads](https://www.python.org/downloads/) and open the installer.
2. When it finishes, open **Applications → Python 3.x** and double-click **Install Certificates.command**. (Without this, the market data downloads fail.)

**Windows**
1. Download Python from [python.org/downloads](https://www.python.org/downloads/) and open the installer.
2. On the first screen, tick **"Add python.exe to PATH"**, then click **Install Now**.
3. Check it worked: open **PowerShell** (Start menu → type "PowerShell") and type `py --version`. You should see a version number.

### Step 2: Add the skills

Pick one:

| Where | How easy | What works |
|---|---|---|
| **A. Claude Code** (recommended) | Easy, a few commands | Everything, including your broker |
| **A2. Claude desktop app** | Easiest, a few clicks | Same plugin, no commands |
| **B. Claude app** (claude.ai or desktop) | Easiest, no commands | Analysis and paper trading. No broker connection |
| **C. ChatGPT or Codex** | Easy | Should work, not tested yet |

#### A. Claude Code (recommended)

Claude Code needs a paid Claude plan (Pro, Max, Team or Enterprise).

1. **Install Claude Code.**
   - **Mac:** open **Terminal** (Applications → Utilities → Terminal) and paste:
     ```
     curl -fsSL https://claude.ai/install.sh | bash
     ```
   - **Windows:** open **PowerShell** and paste:
     ```
     irm https://claude.ai/install.ps1 | iex
     ```
2. **Start it.** Close the window, open a new Terminal (Mac) or PowerShell (Windows), type `claude` and press Enter. The first time, it opens your browser to log in.
3. **Add the skills.** Inside Claude Code, paste these two lines, one at a time:
   ```
   /plugin marketplace add ishankerketta/indian-market-trader
   /plugin install indian-market-trader@indian-market-trader
   ```
4. **Done.** Ask your first question (see Step 3).

#### A2. Claude desktop app (Mac or Windows): no commands needed

1. Open **Settings → Customize → Plugins**.
2. Click **+ Add** (top right) → **Add marketplace**.
3. Paste `ishankerketta/indian-market-trader` and confirm.
4. The plugin **Indian market trader** appears. Add it. It says "installed and ready to use".
5. Open a **New** session and ask: "How's the market looking today?"

Tested on the Mac desktop app.

#### B. Claude app (claude.ai, or the desktop app)

1. **Download the skills:** go to the [latest release](https://github.com/ishankerketta/indian-market-trader/releases/latest) and download the ZIP files. Start with `india-pulse.zip`, `india-scanner.zip`, `india-levels.zip` and `india-charges.zip`, and add more later.
2. **Allow the data:** in Claude, go to **Settings → Capabilities**. Turn on **code execution**, and allow network access to these sites (or to all sites):
   `query1.finance.yahoo.com`, `www.nseindia.com`, `nsearchives.nseindia.com`, `archives.nseindia.com`, `niftyindices.com`, `news.google.com`, `www.reddit.com`
3. **Upload:** go to **Customize → Skills → + → Upload a skill**, and pick a ZIP (don't unzip it). Repeat for each one.

Broker connections need your own computer, so they don't work in the app. Use option A for those.

#### C. ChatGPT or Codex (not tested yet)

The skills use the open `SKILL.md` format, which OpenAI also supports.

- **ChatGPT app** (paid plans): download the ZIPs as in option B, then open **Skills** (in the sidebar or under Plugins) → **Create → Upload from your computer**, and pick a ZIP. ChatGPT may block the market-data downloads. If you see network errors, use Codex or Claude Code instead.
- **Codex** (OpenAI's coding agent): download this project (green **Code** button → **Download ZIP**) and unzip it. Then copy the `skills` folder's contents into your Codex skills folder:
  - **Mac:** `mkdir -p ~/.agents/skills && cp -r skills/* ~/.agents/skills/`
  - **Windows (PowerShell):** `New-Item -ItemType Directory -Force $HOME\.agents\skills; Copy-Item -Recurse skills\* $HOME\.agents\skills\`

If you try it, please [tell us](https://github.com/ishankerketta/indian-market-trader/issues) whether it worked.

### Step 3: Ask

Type in plain English, Hindi or Hinglish:

- "How's the market looking today?"
- "Find breakouts after 9:30"
- "Show me the levels for TCS"
- "Plan a trade in RELIANCE with ₹500 maximum loss"

The first time you plan a trade, Claude asks for your capital, your loss limits and your broker, and saves them. Everything starts in **paper trading** (pretend money).

---

## A typical trading day

| When | What you ask | What happens |
|---|---|---|
| Before 9:15 | "How's the market?" | Market mood, sector leaders, holidays |
| Before 9:15 | "Make my watchlist" | Shortlist of stocks with strong charts |
| After 9:30 | "Any breakouts?" | Stocks breaking their 9:15–9:30 range |
| Picking a trade | "Plan a trade in TCS" | Levels, news, entry, stop, target, odds, shares to buy, safety check |
| You decide | "Yes" | Order placed (pretend money unless you switch it off) |
| During the trade | "Watch it" | Alerts at the stop, the target and 3:10 pm |
| After 3:30 | "How did I do?" | Journal: wins, losses, charges, and whether you're ready for real money |

## The 15 skills

| Skill | In plain words |
|---|---|
| `india-pulse` | How's the market today? |
| `india-scanner` | Which stocks are breaking out? |
| `india-levels` | Where are the important price lines? |
| `india-news` | What's the news on this stock? |
| `india-sentiment` | What's social media saying, and is it a pump? |
| `india-deals` | Are big investors buying or selling? (bulk and block deals) |
| `india-entry` | Is it time to buy, or too late? |
| `india-exit` | Where should the stop-loss and target go? |
| `india-timemachine` | What are the odds this works today? |
| `india-charges` | How much will STT, brokerage and GST cost? |
| `india-budget` | How many shares should I buy? |
| `india-risk` | Is this trade allowed by my rules? PASS or BLOCK |
| `india-broker` | Place the order (only after your yes) |
| `india-alerts` | Tell me when the price hits my stop or target |
| `india-journal` | How am I doing, and am I ready for real money? |

---

## Connect your broker

| Broker | Works with this pack | Also has its own Claude connector |
|---|---|---|
| **Angel One** | Yes, login tested | No |
| **Dhan** | Yes, not tested yet | Yes, can place orders |
| **Zerodha** | Yes, not tested yet | Yes, GTT orders only |
| **Upstox** | Yes, not tested yet | Yes, view only |
| **FYERS** | Yes, not tested yet | Yes |
| **Groww** | Yes, not tested yet | Yes, buy orders; sells need DDPI |
| **About 40 more** | Through [OpenAlgo](https://github.com/marketcalls/openalgo) | |

This needs option A (Claude Code) on your own computer.

**1. Get the project folder** (one time): on this page, click the green **Code** button → **Download ZIP**, and unzip it. Then open a terminal in that folder:
  - **Mac:** open Terminal, type `cd ` (with a space), drag the unzipped folder into the Terminal window, and press Enter.
  - **Windows:** open the unzipped folder in File Explorer, click the address bar, type `powershell`, and press Enter.

**2. Log in yourself.** Your password and keys never go into the chat:

- **Mac:** `python3 skills/india-broker/connect.py login angelone`
- **Windows:** `py skills\india-broker\connect.py login angelone`

Use `dhan`, `zerodha`, `upstox`, `fyers` or `groww` instead of `angelone` for other brokers. It asks for what your broker needs, and nothing shows on screen while you type secrets. You log in again each trading day.

- **Angel One:** an API key from [smartapi.angelone.in](https://smartapi.angelone.in) (Add App), your client code, your PIN, and the 6-digit code from an authenticator app (set it up under Enable TOTP on the same site).
- **Dhan:** your Client ID and an access token from web.dhan.co → My Profile → DhanHQ Trading APIs.

**3. Check it worked** (this only reads, it can't trade):

- **Mac:** `python3 skills/india-broker/connect.py positions angelone`
- **Windows:** `py skills\india-broker\connect.py positions angelone`

**Static IP for real orders.** Since April 2026, SEBI rules say brokers accept API orders only from an internet address (IP) you've registered with them. Viewing your account works from anywhere. Ask your internet provider for a static IP, or use a small cloud server.

---

## Please read

- **This is not investment advice.** It is software that reads public data and does arithmetic on rules you choose. It is not a SEBI-registered adviser or research analyst.
- **Most intraday traders lose money.** SEBI found about 7 in 10 individual intraday traders lost money in FY2022-23. Practise with pretend money for weeks first, and let the journal judge your record.
- **Nothing happens without your yes.** Real orders need you to switch off paper trading, a fresh safety PASS, and your yes for that exact order.
- **Insider rules.** List any company where you're an insider in your settings (`pit_restricted`), and the pack will always block it.
- **The odds are a simulation, not a promise.** Results days, circuits and big news can move a stock in ways the past never did.
- **A stop-loss can slip.** In a fast market or a circuit, it can fill far from your price, or not at all.
- **The data is free and unofficial.** Yahoo and the NSE website can be late, change or block access. Check anything important in your broker's app.
- **Charges change.** Rates are as of 3 Nov 2026. Compare against one of your real contract notes.
- **Taxes.** Intraday profit is usually taxed as speculative business income at your slab rate. Ask a tax professional.
- **Social media buzz is a warning, not a tip.** Pump-and-dump groups use Telegram and WhatsApp, and late buyers are usually the ones left holding.

---

<details>
<summary><b>For developers: the scripts behind each skill</b></summary>

Every skill is a plain Python script (standard library only). They share a `trader/` folder in your project, and each step reads what the last one wrote.

```
python3 skills/india-pulse/pulse.py                            # pre-market brief
python3 skills/india-scanner/scan.py universe | daily | orb     # Nifty 500, watchlist, breakouts
python3 skills/india-news/news.py --from-scan                  # headlines, filings, move
python3 skills/india-sentiment/sentiment.py --from-scan        # tone, buzz, pump risk
python3 skills/india-levels/levels.py NIFTY                    # levels + chart -> trader/levels_NIFTY.html
python3 skills/india-entry/entry.py check TCS                  # waiting / triggered / expired
python3 skills/india-exit/exit.py plan --stop or-low --target 2R --write
python3 skills/india-timemachine/timemachine.py run --write    # 10,000 replays + history
python3 skills/india-charges/charges.py --buy 300 --sell 306 --qty 30 --compare
python3 skills/india-budget/size.py --write                    # -> trader/orders.json
python3 skills/india-risk/check.py                             # PASS / BLOCK
python3 skills/india-broker/ticket.py show | approve ID --yes | sync | ledger
python3 skills/india-broker/ticket.py preview ID --broker angelone             # shows the exact request, sends nothing
python3 skills/india-broker/ticket.py send ID --broker angelone --live --yes
python3 skills/india-broker/connect.py brokers | status | orders BROKER | positions BROKER
python3 skills/india-alerts/alerts.py add --from-plan ; alerts.py check
python3 skills/india-deals/deals.py bulk | block | insider
python3 skills/india-journal/journal.py
```

- Offline tests (40, on made-up data): `python3 -m unittest discover -s tests -v`
- Check every live data source: `python3 tests/live_check.py RELIANCE`
- Replay a past moment: set `IMT_NOW=2026-11-02T10:15` (and `IMT_DIR=trader-replay` to keep it separate).
- Data sources: Yahoo Finance (`.NS`), NSE archives and website, Google News India, Reddit.
- Known gaps: NSE's live quote and insider-trading pages often refuse scripts, so the pack falls back to NSE's daily files.

</details>

<details>
<summary><b>Similar projects and credits</b></summary>

Inspired by Jake Schincariol's [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) for US markets (MIT). This is an independent rewrite for NSE.

Ideas re-implemented here, with thanks:
- [claude-trading-skills-india](https://github.com/Shubhamkumartrichy/claude-trading-skills-india) (MIT): broker brokerage profiles, market pulse, broker connector table.
- [nse-day-trader-skill](https://github.com/parinshahAIbuilder/nse-day-trader-skill) (MIT): SEBI insider guard, holiday calendar, ASM/GSM and circuit checks.
- [nse-trader-skills](https://github.com/Vatsa10/nse-trader-skills) (MIT): the idea of a live data check.
- [OpenAlgo](https://github.com/marketcalls/openalgo) (AGPL-3.0): an optional adapter calls its API. None of its code is included.
- Also worth a look: [Tapetide NSE/BSE MCP](https://github.com/Tapetide-hq/nse-bse-indian-stock-market-data-mcp) for fundamentals, and other India ports: [indian-day-trader](https://github.com/iamsanaur/indian-day-trader), [day-trader-skill-india](https://github.com/bhardwajaditya/day-trader-skill-india), [day-trader-india](https://github.com/Fantastic792/day-trader-india).

</details>

**Coming next:** testing each broker with real accounts, Windows testing, checking charges against real contract notes, and results summaries from NSE filings.

Found a problem? [Open an issue](https://github.com/ishankerketta/indian-market-trader/issues) and paste what you saw (remove any personal details).

MIT licence. Made by [Ishan Savio Kerketta](https://ishansavio.com).

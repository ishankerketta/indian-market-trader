"""Offline tests. Run from the repo root:  python3 -m unittest discover -s tests -v

Fixtures are SYNTHETIC (tests/make_fixtures.py), generated fresh into a temp folder,
in the same shapes Yahoo, NSE, Google News and Reddit return.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / "skills"
sys.path.insert(0, str(SK / "_shared"))
sys.path.insert(0, str(ROOT / "tests"))

import costs  # noqa: E402
import indicators  # noqa: E402
import text  # noqa: E402
from core import fmt_inr  # noqa: E402
import make_fixtures  # noqa: E402


class Units(unittest.TestCase):
    def test_charges_match_hand_calculation(self):
        c = costs.intraday_charges(2450, 2470, 40, "discount")
        # buy 98,000 / sell 98,800: brokerage 20 + 20 (0.03% caps at Rs 20 above 66,667)
        self.assertEqual(c["brokerage"], 40.0)
        self.assertAlmostEqual(c["stt"], 98800 * 0.00025, places=2)
        self.assertAlmostEqual(c["stamp"], 98000 * 0.00003, places=2)
        exch = 196800 * 0.0000297
        sebi = ipft = 196800 * 0.000001
        self.assertAlmostEqual(c["gst"], round((40 + exch + sebi + ipft) * 0.18, 2), places=2)
        self.assertAlmostEqual(c["net_pnl"], 800 - c["total"], places=2)

    def test_small_order_brokerage_is_percentage(self):
        self.assertAlmostEqual(costs.brokerage(10000, "discount"), 3.0)

    def test_breakeven_covers_charges(self):
        be = costs.breakeven_sell(1000, 50)
        self.assertGreaterEqual(costs.intraday_charges(1000, be, 50)["net_pnl"], 0)
        self.assertLess(costs.intraday_charges(1000, be - 0.02, 50)["net_pnl"], 0)

    def test_rate_override(self):
        a = costs.intraday_charges(1000, 1010, 100)
        b = costs.intraday_charges(1000, 1010, 100, rates={"stt_sell": 0.0})
        self.assertAlmostEqual(a["total"] - b["total"], 101000 * 0.00025, places=2)

    def test_tick_rounding(self):
        self.assertEqual(indicators.tick_size(180), 0.01)
        self.assertEqual(indicators.round_tick(1706.045, "down"), 1706.0)
        self.assertEqual(indicators.round_tick(712.33, "up"), 712.35)

    def test_rsi_bounds(self):
        up = list(range(1, 40))
        self.assertEqual(indicators.rsi(up), 100.0)
        self.assertLess(indicators.rsi(list(range(40, 1, -1))), 1)

    def test_band_parsing(self):
        self.assertIsNone(indicators.parse_band("No Band"))
        self.assertEqual(indicators.parse_band("20"), 20.0)
        up, dn = indicators.band_limits(100, 5)
        self.assertAlmostEqual(up, 105)
        self.assertAlmostEqual(dn, 95)

    def test_sentiment_lexicon_and_negation(self):
        self.assertGreater(text.score("Shares surge after strong results"), 0.25)
        self.assertLess(text.score("Stock crashes on fraud probe"), -0.25)
        self.assertGreater(text.score("SEBI not planning probe"), 0)
        self.assertIn("order_win", text.tag("Company bags Rs 500 crore order"))
        self.assertTrue(text.pump_flags("10x multibagger, join telegram"))
        self.assertTrue(text.mentions("bought $IEX today", "IEX"))
        self.assertFalse(text.mentions("flexible pricing", "IEX"))

    def test_aliases_and_relevance(self):
        a = text.stock_aliases("SBIN", "State Bank of India")
        self.assertIn("SBI", a)
        self.assertTrue(text.mentions("SBI, NSE and 7 other stocks set to announce Q2 results today", "SBIN", a))
        self.assertFalse(text.mentions("IPO fundraising rises 30% to record", "SBIN", a))
        self.assertFalse(text.mentions("Updated estimates", "SBIN", a))

    def test_results_upcoming_is_forward_looking(self):
        self.assertTrue(text.results_upcoming("SBI set to announce Q2 results today"))
        self.assertTrue(text.results_upcoming("Board meeting to consider results on Nov 5"))
        self.assertFalse(text.results_upcoming("Consensus has updated its estimates after results"))
        self.assertFalse(text.results_upcoming("Shares surge 12% after strong Q2 results"))

    def test_reddit_rss_parsing(self):
        import data
        rss = b"""<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><category term="IndianStreetBets" label="r/IndianStreetBets"/><title>SBIN results play?</title>
<content type="html">&lt;p&gt;Holding into results&lt;/p&gt;</content><link href="https://www.reddit.com/r/x/1"/>
<updated>2026-11-02T10:00:00+00:00</updated></entry></feed>"""
        p = data._reddit_rss(rss)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["sub"], "IndianStreetBets")
        self.assertIn("Holding into results", p[0]["text"])
        self.assertEqual(p[0]["time"].utcoffset(), dt.timedelta(hours=5, minutes=30))

    def test_levels_are_sparse_and_ranked(self):
        import sr
        t0 = dt.datetime(2026, 11, 2, 9, 15, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        pts = []
        # 5 touches at 100, 3 at 110, 2 at 100.3 (should merge into 100), 3 at 110.4 (too close to 110)
        for i, p in enumerate([100, 100.1, 99.9, 100.05, 99.95, 110, 110.1, 109.9, 100.3, 100.25, 110.4, 110.5, 110.45]):
            pts.append({"kind": "peak" if i % 2 else "trough", "price": p, "dt": t0 + dt.timedelta(days=i)})
        lv = sr.pick_levels(pts, tol=0.4, max_lines=3, min_touches=3)
        self.assertEqual(round(lv[0]["price"]), 100)
        self.assertGreaterEqual(lv[0]["touches"], 6)
        self.assertTrue(all(abs(a["price"] - b["price"]) >= 0.8 for a in lv for b in lv if a is not b))
        self.assertLessEqual(len(lv), 3)

    def test_vol_ratio_scales_to_todays_pace(self):
        sys.path.insert(0, str(SK / "india-timemachine"))
        import timemachine as tm
        t0 = dt.datetime(2026, 11, 2, 9, 15, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
        pools = {f"09:{15 + 5 * i:02d}": [(1.0, 1.002, 0.998, 1.0)] * 10 for i in range(6)}   # normal range 0.4%
        fast = [{"dt": t0 + dt.timedelta(minutes=5 * i), "o": 100, "h": 101.0, "l": 99.8, "c": 100.5} for i in range(4)]
        self.assertAlmostEqual(tm.vol_ratio(fast, pools), 3.0, places=2)        # 1.2% vs 0.4%
        self.assertEqual(tm.vol_ratio(fast[:2], pools), 1.0)                   # too early to tell
        wild = [dict(b, h=110, l=90) for b in fast]
        self.assertEqual(tm.vol_ratio(wild, pools), 4.0)                       # clamped

    def test_indian_number_format(self):
        self.assertEqual(fmt_inr(1234567.5), "₹12,34,567.50")
        self.assertEqual(fmt_inr(-500), "-₹500.00")


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.fx = make_fixtures.make(base / "fx")
        cls.state = base / "trader"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tool(self, rel, *args, when="2026-11-02T09:41", ok=True):
        env = dict(os.environ, IMT_FIXTURES=str(self.fx), IMT_DIR=str(self.state), IMT_NOW=when)
        p = subprocess.run([sys.executable, str(SK / rel), *args], capture_output=True, text=True, env=env,
                           cwd=self.tmp.name, timeout=120)
        if ok:
            self.assertEqual(p.returncode, 0, f"{rel} {args} failed:\n{p.stdout}\n{p.stderr}")
        return p

    def state_json(self, name):
        return json.loads((self.state / name).read_text())

    def test_full_trade(self):
        self.run_tool("india-scanner/scan.py", "universe")
        uni = self.state_json("universe.json")
        self.assertEqual({s["symbol"] for s in uni["symbols"]}, {"TESTCO", "FLATCO", "T2TCO"})

        self.run_tool("india-scanner/scan.py", "daily", "--symbols", "TESTCO,FLATCO", "--save-watchlist")
        self.assertTrue(self.state_json("watchlist.json")["symbols"])

        out = self.run_tool("india-scanner/scan.py", "orb", "--symbols", "TESTCO,FLATCO").stdout
        scan = self.state_json("scan.json")
        self.assertEqual([c["symbol"] for c in scan["candidates"]], ["TESTCO"], out)
        cand = scan["candidates"][0]
        self.assertGreater(cand["trigger_close"], cand["or_high"])

        # Before the range completes the timer must wait
        self.run_tool("india-entry/entry.py", "check", "TESTCO", when="2026-11-02T09:25")
        self.assertEqual(self.state_json("entry.json")["status"], "waiting")
        self.run_tool("india-entry/entry.py", "check", "TESTCO")
        entry = self.state_json("entry.json")
        self.assertEqual(entry["status"], "triggered")
        self.assertEqual(entry["trigger_time"], cand["trigger_time"])
        # Much later the price has run away: do not chase
        self.run_tool("india-entry/entry.py", "check", "TESTCO", when="2026-11-02T12:30")
        self.assertEqual(self.state_json("entry.json")["status"], "expired")
        self.run_tool("india-entry/entry.py", "check", "TESTCO")

        self.run_tool("india-exit/exit.py", "plan", "--stop", "or-low", "--target", "2.5R", "--write")
        plan = self.state_json("plan.json")
        self.assertLess(plan["stop"], plan["entry"])
        self.assertAlmostEqual(plan["target"] - plan["entry"], 2.5 * (plan["entry"] - plan["stop"]), delta=0.2)

        self.run_tool("india-timemachine/timemachine.py", "run", "--sims", "2000", "--seed", "19", "--write")
        sim = self.state_json("sim.json")
        self.assertAlmostEqual(sum(sim["sim_pct"].values()), 100.0, delta=0.2)
        self.assertGreater(sim["history_signals"], 10)
        # Same seed, same answer
        self.run_tool("india-timemachine/timemachine.py", "run", "--sims", "2000", "--seed", "19", "--write")
        self.assertEqual(self.state_json("sim.json")["sim_pct"], sim["sim_pct"])

        self.run_tool("india-budget/size.py", "--write")
        order = self.state_json("orders.json")["orders"][-1]
        self.assertLessEqual(order["est_loss_at_stop"], 500)
        self.assertLessEqual(order["value"], 50000)
        self.assertEqual(order["status"], "DRAFT")

        self.run_tool("india-sentiment/sentiment.py", "--tickers", "TESTCO,FLATCO")
        sent = {s["symbol"]: s for s in self.state_json("sentiment.json")["stocks"]}
        self.assertEqual(sent["TESTCO"]["pump_risk"], "high")
        self.assertEqual(sent["FLATCO"]["pump_risk"], "normal")

        out = self.run_tool("india-risk/check.py").stdout
        self.assertIn("PASS", out)
        self.assertIn("pump risk", out)  # warned, not blocked
        order = self.state_json("orders.json")["orders"][-1]
        self.assertEqual(order["status"], "READY")

        # Approval needs the explicit --yes
        p = self.run_tool("india-broker/ticket.py", "approve", order["id"], ok=False)
        self.assertNotEqual(p.returncode, 0)
        self.run_tool("india-broker/ticket.py", "approve", order["id"], "--yes")
        self.run_tool("india-alerts/alerts.py", "add", "--from-plan")
        self.run_tool("india-broker/ticket.py", "sync", when="2026-11-02T10:00")
        self.assertEqual(self.state_json("orders.json")["orders"][-1]["status"], "OPEN")
        self.run_tool("india-broker/ticket.py", "sync", when="2026-11-02T15:20")
        led = self.state_json("paper_ledger.json")
        self.assertEqual(len(led["closed"]), 1)
        trade = led["closed"][0]
        self.assertIn(trade["outcome"], ("target", "stop", "flat"))
        self.assertAlmostEqual(led["cash"], 100000 + trade["net_pnl"], places=2)
        out = self.run_tool("india-alerts/alerts.py", "check", when="2026-11-02T15:20").stdout
        self.assertIn("RING", out)
        self.assertEqual(self.state_json("risk.json")["orders"][0]["verdict"], "PASS")

    def test_symbols_run_keeps_watchlist_and_dummy_skipped(self):
        self.run_tool("india-scanner/scan.py", "universe")
        self.run_tool("india-scanner/scan.py", "daily", "--symbols", "TESTCO,FLATCO", "--save-watchlist")
        saved = self.state_json("watchlist.json")["symbols"]
        p = self.run_tool("india-scanner/scan.py", "daily", "--symbols", "FLATCO")
        self.assertIn("Watchlist not changed", p.stdout)
        self.assertEqual(self.state_json("watchlist.json")["symbols"], saved)
        import importlib.util
        spec = importlib.util.spec_from_file_location("scan", SK / "india-scanner" / "scan.py")
        sys.path.insert(0, str(SK / "_shared"))
        scan = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan)
        self.assertTrue(callable(scan.pick_symbols))

    def test_live_forming_bar_does_not_break_bar_size_or_orb(self):
        """Yahoo adds a still-forming bar mid-session (e.g. 11:42 after 11:40). It must not change the
        bar size, and a breakout above the 09:15-09:30 range must still be found."""
        import datetime as _dt
        sys.path.insert(0, str(SK / "_shared"))
        import indicators as ind
        ist = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
        day = _dt.datetime(2026, 11, 3, 9, 15, tzinfo=ist)
        bars = []
        price = 100.0
        for i in range(30):                                  # 09:15 .. 11:40, 5-minute bars
            t = day + _dt.timedelta(minutes=5 * i)
            price += 0.0 if i < 3 else 0.3                   # flat opening range, then a climb
            bars.append({"dt": t, "t": int(t.timestamp()), "o": price, "h": price + 0.2, "l": price - 0.2, "c": price, "v": 1000})
        t = day + _dt.timedelta(minutes=147)                 # 11:42, the forming bar
        bars.append({"dt": t, "t": int(t.timestamp()), "o": price, "h": price + 0.1, "l": price - 0.1, "c": price, "v": 10})
        self.assertEqual(ind.bar_minutes(bars), 5)
        at = day + _dt.timedelta(minutes=147)
        orr, trig = ind.orb_trigger(bars, 15, "long", ("09:30", "14:30"), at)
        self.assertIsNotNone(orr)
        self.assertIsNotNone(trig)
        self.assertEqual(trig["dt"].strftime("%H:%M"), "09:30")

    def test_orb_marks_failed_breakout_and_explains_skips(self):
        """A stock that broke out and then fell back inside its range must be flagged, and a stock with no
        bars today must be counted as such, not silently dropped."""
        import datetime as _dt
        import importlib.util
        sys.path.insert(0, str(SK / "_shared"))
        spec = importlib.util.spec_from_file_location("scan_mod", SK / "india-scanner" / "scan.py")
        scan = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan)
        ist = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
        day = _dt.datetime(2026, 11, 3, 9, 15, tzinfo=ist)

        def bars_for(closes):
            out = []
            for i, c in enumerate(closes):
                t = day + _dt.timedelta(minutes=5 * i)
                out.append({"dt": t, "t": int(t.timestamp()), "o": c, "h": c + 0.2, "l": c - 0.2, "c": c, "v": 1000})
            return out

        # 3 bars of range around 100, a close at 101 (breakout), then back to 99.5 (failed)
        failed = bars_for([100, 100, 100, 101, 100.5, 99.5, 99.5])
        holding = bars_for([100, 100, 100, 101, 101.5, 102, 102])
        quiet = bars_for([100, 100, 100, 100, 100.1, 100, 100])
        yesterday = [dict(b, dt=b["dt"] - _dt.timedelta(days=1), t=b["t"] - 86400) for b in quiet]
        feeds = {"FAIL": failed, "HOLD": holding, "QUIET": quiet, "NOTODAY": yesterday}
        scan.chart = lambda sym, interval, rng: {"bars": feeds[sym], "prev_close": 100.0}
        at = day + _dt.timedelta(minutes=35)
        cfg = {"orb_minutes": 15, "entry_window": ["09:30", "14:30"]}
        r = {s_: scan.orb_one(s_, cfg, at, ["long"]) for s_ in feeds}
        self.assertFalse(r["FAIL"]["holding"])
        self.assertTrue(r["HOLD"]["holding"])
        self.assertEqual(r["QUIET"], {"_skip": "no_breakout"})
        self.assertEqual(r["NOTODAY"], {"_skip": "no_bars_today"})

    def test_daily_bars_patched_from_intraday(self):
        import data
        os.environ["IMT_FIXTURES"] = str(self.fx)
        try:
            raw = data.chart("FLATCO", "1d", "1y")["bars"]
            patched = data.daily("FLATCO", "1y")
        finally:
            os.environ.pop("IMT_FIXTURES")
        self.assertEqual(raw[-1]["dt"].date(), dt.date(2026, 10, 30))      # Yahoo lags a session
        self.assertEqual(patched[-1]["dt"].date(), dt.date(2026, 11, 2))   # rebuilt from 5-minute bars
        self.assertTrue(patched[-1]["patched"])

    def test_levels_chart(self):
        self.run_tool("india-scanner/scan.py", "universe")
        out = self.run_tool("india-levels/levels.py", "FLATCO", when="2026-11-02T15:30").stdout
        lv = self.state_json("levels.json")["FLATCO"]
        self.assertLessEqual(len(lv["major"]), 3)
        self.assertLessEqual(len(lv["short_term"]), 5)
        self.assertTrue(all(m["touches"] >= 3 for m in lv["major"]))
        self.assertTrue(all(s["touches"] >= 2 for s in lv["short_term"]))
        lines = sorted(l["price"] for l in lv["major"] + lv["short_term"])
        span = lv["range_high"]["price"] - lv["range_low"]["price"]
        self.assertTrue(all(b - a >= 0.04 * span * 0.3 for a, b in zip(lines, lines[1:])), lines)
        html = (self.state / "levels_FLATCO.html").read_text()
        self.assertIn("<svg", html)
        self.assertIn("Nearest support", out)
        # Replaying a morning must not see that afternoon's bars
        self.run_tool("india-levels/levels.py", "TESTCO", "--no-chart", when="2026-11-02T09:41")
        lv = self.state_json("levels.json")["TESTCO"]
        self.assertLess(lv["range_high"]["when"], "2026-11-02T09:41")

    def test_risk_blocks_trade_to_trade_late_entries_and_circuits(self):
        import check
        from core import DEFAULT_CONFIG, IST
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        order = {"symbol": "T2TCO", "direction": "long", "side": "BUY", "qty": 10, "limit": 104.0,
                 "stop": 102.0, "target": 109.0, "flat_by": "15:10", "value": 1040.0, "margin_needed": 1040.0,
                 "est_loss_at_stop": 30.0, "rr_net": 2.0, "leverage": 1}
        ctx = {"now": dt.datetime(2026, 11, 2, 14, 50, tzinfo=IST), "stats": (0.0, 0, 0.0), "cash": 100000,
               "bands": {"T2TCO": {"series": "BE", "band": 5.0}}, "prev_close": 100.0,
               "news": {}, "sentiment": {}}
        res = {c["check"]: c["result"] for c in check.check_order(order, cfg, ctx)}
        self.assertEqual(res["series"], "BLOCK")
        self.assertEqual(res["circuit band"], "BLOCK")
        self.assertEqual(res["entry window"], "BLOCK")
        self.assertEqual(res["room below upper circuit"], "BLOCK")   # target 109 > 105 * 0.99
        self.assertEqual(res["max loss per trade"], "PASS")
        ctx["levels"] = {"T2TCO": {"time": "2026-11-02T09:30", "range_high": {"price": 120, "when": "x"},
                                   "range_low": {"price": 90, "when": "y"},
                                   "major": [{"price": 106.5, "touches": 5, "peaks": 3, "troughs": 2}],
                                   "short_term": []}}
        warn = next(c for c in check.check_order(order, cfg, ctx) if c["check"] == "levels in the way")
        self.assertEqual(warn["result"], "WARN")
        self.assertIn("106.5", warn["detail"])
        ctx["levels"] = {}
        ctx["stats"] = (-1480.0, 3, 0.0)   # 1,480 lost + 30 at risk > 1,500 limit
        res = {c["check"]: c["result"] for c in check.check_order(order, cfg, ctx)}
        self.assertEqual(res["trades per day"], "BLOCK")
        self.assertEqual(res["daily loss limit"], "BLOCK")

    def test_deals_and_news(self):
        self.run_tool("india-scanner/scan.py", "universe")
        self.run_tool("india-deals/deals.py", "bulk")
        d = self.state_json("deals.json")["bulk"]
        t = next(a for a in d["by_symbol"] if a["symbol"] == "TESTCO")
        self.assertAlmostEqual(t["buy_cr"], 500000 * 1004.20 / 1e7, places=1)
        self.run_tool("india-deals/deals.py", "insider", "--symbols", "TESTCO")
        self.assertEqual(len(self.state_json("deals.json")["insider"]["trades"]), 1)
        self.run_tool("india-news/news.py", "--tickers", "TESTCO", "--hours", "24")
        n = self.state_json("news.json")["stocks"][0]
        titles = [i["title"] for i in n["items"]]
        self.assertTrue(any("order" in t for t in titles))
        self.assertFalse(any("Old story" in t for t in titles))   # 9 days old, outside the window
        self.assertEqual(n["tone"], "positive")


sys.path.insert(0, str(SK / "india-risk"))

if __name__ == "__main__":
    unittest.main()

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
sys.path.insert(0, str(SK / "_dalal"))
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

    def test_indian_number_format(self):
        self.assertEqual(fmt_inr(1234567.5), "₹12,34,567.50")
        self.assertEqual(fmt_inr(-500), "-₹500.00")


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.fx = make_fixtures.make(base / "fx")
        cls.state = base / "dalal"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tool(self, rel, *args, when="2026-11-02T09:41", ok=True):
        env = dict(os.environ, DALAL_FIXTURES=str(self.fx), DALAL_DIR=str(self.state), DALAL_NOW=when)
        p = subprocess.run([sys.executable, str(SK / rel), *args], capture_output=True, text=True, env=env,
                           cwd=self.tmp.name, timeout=120)
        if ok:
            self.assertEqual(p.returncode, 0, f"{rel} {args} failed:\n{p.stdout}\n{p.stderr}")
        return p

    def state_json(self, name):
        return json.loads((self.state / name).read_text())

    def test_full_trade(self):
        self.run_tool("dalal-scanner/scan.py", "universe")
        uni = self.state_json("universe.json")
        self.assertEqual({s["symbol"] for s in uni["symbols"]}, {"TESTCO", "FLATCO", "T2TCO"})

        self.run_tool("dalal-scanner/scan.py", "daily", "--symbols", "TESTCO,FLATCO")
        self.assertTrue(self.state_json("watchlist.json")["symbols"])

        out = self.run_tool("dalal-scanner/scan.py", "orb", "--symbols", "TESTCO,FLATCO").stdout
        scan = self.state_json("scan.json")
        self.assertEqual([c["symbol"] for c in scan["candidates"]], ["TESTCO"], out)
        cand = scan["candidates"][0]
        self.assertGreater(cand["trigger_close"], cand["or_high"])

        # Before the range completes the timer must wait
        self.run_tool("dalal-entry/entry.py", "check", "TESTCO", when="2026-11-02T09:25")
        self.assertEqual(self.state_json("entry.json")["status"], "waiting")
        self.run_tool("dalal-entry/entry.py", "check", "TESTCO")
        entry = self.state_json("entry.json")
        self.assertEqual(entry["status"], "triggered")
        self.assertEqual(entry["trigger_time"], cand["trigger_time"])
        # Much later the price has run away: do not chase
        self.run_tool("dalal-entry/entry.py", "check", "TESTCO", when="2026-11-02T12:30")
        self.assertEqual(self.state_json("entry.json")["status"], "expired")
        self.run_tool("dalal-entry/entry.py", "check", "TESTCO")

        self.run_tool("dalal-exit/exit.py", "plan", "--stop", "or-low", "--target", "2.5R", "--write")
        plan = self.state_json("plan.json")
        self.assertLess(plan["stop"], plan["entry"])
        self.assertAlmostEqual(plan["target"] - plan["entry"], 2.5 * (plan["entry"] - plan["stop"]), delta=0.2)

        self.run_tool("dalal-timemachine/timemachine.py", "run", "--sims", "2000", "--seed", "19", "--write")
        sim = self.state_json("sim.json")
        self.assertAlmostEqual(sum(sim["sim_pct"].values()), 100.0, delta=0.2)
        self.assertGreater(sim["history_signals"], 10)
        # Same seed, same answer
        self.run_tool("dalal-timemachine/timemachine.py", "run", "--sims", "2000", "--seed", "19", "--write")
        self.assertEqual(self.state_json("sim.json")["sim_pct"], sim["sim_pct"])

        self.run_tool("dalal-budget/size.py", "--write")
        order = self.state_json("orders.json")["orders"][-1]
        self.assertLessEqual(order["est_loss_at_stop"], 500)
        self.assertLessEqual(order["value"], 50000)
        self.assertEqual(order["status"], "DRAFT")

        self.run_tool("dalal-sentiment/sentiment.py", "--tickers", "TESTCO,FLATCO")
        sent = {s["symbol"]: s for s in self.state_json("sentiment.json")["stocks"]}
        self.assertEqual(sent["TESTCO"]["pump_risk"], "high")
        self.assertEqual(sent["FLATCO"]["pump_risk"], "normal")

        out = self.run_tool("dalal-risk/check.py").stdout
        self.assertIn("PASS", out)
        self.assertIn("pump risk", out)  # warned, not blocked
        order = self.state_json("orders.json")["orders"][-1]
        self.assertEqual(order["status"], "READY")

        # Approval needs the explicit --yes
        p = self.run_tool("dalal-broker/ticket.py", "approve", order["id"], ok=False)
        self.assertNotEqual(p.returncode, 0)
        self.run_tool("dalal-broker/ticket.py", "approve", order["id"], "--yes")
        self.run_tool("dalal-alerts/alerts.py", "add", "--from-plan")
        self.run_tool("dalal-broker/ticket.py", "sync", when="2026-11-02T10:00")
        self.assertEqual(self.state_json("orders.json")["orders"][-1]["status"], "OPEN")
        self.run_tool("dalal-broker/ticket.py", "sync", when="2026-11-02T15:20")
        led = self.state_json("paper_ledger.json")
        self.assertEqual(len(led["closed"]), 1)
        trade = led["closed"][0]
        self.assertIn(trade["outcome"], ("target", "stop", "flat"))
        self.assertAlmostEqual(led["cash"], 100000 + trade["net_pnl"], places=2)
        out = self.run_tool("dalal-alerts/alerts.py", "check", when="2026-11-02T15:20").stdout
        self.assertIn("RING", out)
        self.assertEqual(self.state_json("risk.json")["orders"][0]["verdict"], "PASS")

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
        ctx["stats"] = (-1480.0, 3, 0.0)   # 1,480 lost + 30 at risk > 1,500 limit
        res = {c["check"]: c["result"] for c in check.check_order(order, cfg, ctx)}
        self.assertEqual(res["trades per day"], "BLOCK")
        self.assertEqual(res["daily loss limit"], "BLOCK")

    def test_deals_and_news(self):
        self.run_tool("dalal-scanner/scan.py", "universe")
        self.run_tool("dalal-deals/deals.py", "bulk")
        d = self.state_json("deals.json")["bulk"]
        t = next(a for a in d["by_symbol"] if a["symbol"] == "TESTCO")
        self.assertAlmostEqual(t["buy_cr"], 500000 * 1004.20 / 1e7, places=1)
        self.run_tool("dalal-deals/deals.py", "insider", "--symbols", "TESTCO")
        self.assertEqual(len(self.state_json("deals.json")["insider"]["trades"]), 1)
        self.run_tool("dalal-news/news.py", "--tickers", "TESTCO", "--hours", "24")
        n = self.state_json("news.json")["stocks"][0]
        titles = [i["title"] for i in n["items"]]
        self.assertTrue(any("order" in t for t in titles))
        self.assertFalse(any("Old story" in t for t in titles))   # 9 days old, outside the window
        self.assertEqual(n["tone"], "positive")


sys.path.insert(0, str(SK / "dalal-risk"))

if __name__ == "__main__":
    unittest.main()

"""v0.3 tests: broker adapters and safety gates, broker charges, SEBI insider guard, holidays,
live circuit / ASM checks, market pulse and the journal. Offline, on synthetic fixtures."""
import datetime as dt
import hashlib
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
sys.path.insert(0, str(SK / "india-risk"))
sys.path.insert(0, str(ROOT / "tests"))

import brokers as B  # noqa: E402
import costs  # noqa: E402
import make_fixtures  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TICKET = {"id": "SBIN-20261102-0941", "symbol": "SBIN", "side": "BUY", "direction": "long", "qty": 10,
          "limit": 962.5, "stop": 955.0, "target": 978.0, "flat_by": "15:10"}
FAKE = {"api_key": "K", "jwt": "J", "client_id": "C1", "token": "T", "access_token": "A", "app_id": "APP-100",
        "host": "http://127.0.0.1:5000"}


class Adapters(unittest.TestCase):
    def legs(self):
        return B.ticket_to_legs(TICKET)

    def test_legs(self):
        e, s = self.legs()
        self.assertEqual((e["side"], e["order_type"], e["price"]), ("BUY", "LIMIT", 962.5))
        self.assertEqual((s["side"], s["order_type"], s["trigger"]), ("SELL", "SL", 955.0))
        self.assertLess(s["price"], s["trigger"])          # sell stop-limit sits below its trigger

    def test_angelone(self):
        e, s = self.legs()
        a = B.get("angel", session=FAKE)
        r = a.place(e, token={"token": "3045", "tradingsymbol": "SBIN-EQ"})
        b = r["body"]
        self.assertTrue(r["url"].endswith("/order/v1/placeOrder"))
        self.assertEqual((b["variety"], b["ordertype"], b["producttype"], b["symboltoken"]),
                         ("NORMAL", "LIMIT", "INTRADAY", "3045"))
        self.assertEqual((b["quantity"], b["price"]), ("10", "962.50"))   # SmartAPI wants strings
        r = a.place(s, token={"token": "3045", "tradingsymbol": "SBIN-EQ"})
        self.assertEqual((r["body"]["variety"], r["body"]["ordertype"]), ("STOPLOSS", "STOPLOSS_LIMIT"))
        self.assertEqual(B.AngelOne.order_id({"data": {"orderid": "X1"}}), "X1")

    def test_dhan_super_order(self):
        a = B.get("dhan", session=FAKE)
        self.assertTrue(a.places_bracket)
        r = a.bracket(TICKET, security_id="3045")
        b = r["body"]
        self.assertTrue(r["url"].endswith("/v2/super/orders"))
        self.assertEqual((b["targetPrice"], b["stopLossPrice"], b["exchangeSegment"], b["productType"]),
                         (978.0, 955.0, "NSE_EQ", "INTRADAY"))
        self.assertEqual(B.Dhan.order_id({"orderId": "D9", "orderStatus": "PENDING"}), "D9")

    def test_zerodha(self):
        e, s = self.legs()
        r = B.get("kite", session=FAKE).place(s)
        self.assertTrue(r["form"])
        self.assertEqual((r["body"]["order_type"], r["body"]["trigger_price"], r["body"]["product"]), ("SL", 955.0, "MIS"))
        req = B.Zerodha.session_request("key", "rt", "sec")
        self.assertEqual(req["body"]["checksum"], hashlib.sha256(b"keyrtsec").hexdigest())

    def test_upstox_fyers_groww_openalgo(self):
        e, s = self.legs()
        u = B.get("upstox", session=FAKE).place(e, isin="INE062A01020")["body"]
        self.assertEqual((u["instrument_token"], u["product"]), ("NSE_EQ|INE062A01020", "I"))
        f = B.get("fyers", session=FAKE).place(s)["body"]
        self.assertEqual((f["symbol"], f["type"], f["side"], f["stopPrice"]), ("NSE:SBIN-EQ", 4, -1, 955.0))
        self.assertEqual(B.Fyers.token_request("APP-100", "sec", "c")["body"]["appIdHash"],
                         hashlib.sha256(b"APP-100:sec").hexdigest())
        g = B.get("groww", session=FAKE).place(s)["body"]
        self.assertEqual((g["order_type"], g["segment"], g["trigger_price"]), ("SL", "CASH", 955.0))
        self.assertLessEqual(len(g["order_reference_id"]), 20)
        o = B.get("openalgo", session=FAKE).place(e)
        self.assertEqual(o["url"], "http://127.0.0.1:5000/api/v1/placeorder")
        self.assertEqual(o["body"]["pricetype"], "LIMIT")

    def test_redaction_hides_secrets(self):
        e, _ = self.legs()
        for name in B.ADAPTERS:
            a = B.get(name, session=FAKE)
            kw = {"angelone": {"token": {"token": "1", "tradingsymbol": "SBIN-EQ"}}, "dhan": {"security_id": "1"},
                  "upstox": {"isin": "X"}}.get(name, {})
            shown = json.dumps(B.redact(a.place(e, **kw)))
            for secret in ('"J"', '"T"', '"A"', '"K"', '"C1"', "APP-100:A", "token K:A", "Bearer J", "Bearer A"):
                self.assertNotIn(secret, shown, f"{name} leaked {secret}")

    def test_unknown_broker(self):
        with self.assertRaises(B.BrokerError):
            B.get("robinhood", session=FAKE)


class Gates(unittest.TestCase):
    """ticket.py preview/send safety gates, run as the user would."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "trader"
        self.dir.mkdir()
        t = dict(TICKET, status="READY", order_type="LIMIT", product="MIS", est_loss_at_stop=80.0,
                 est_profit_at_target=150.0, margin_needed=9625.0, value=9625.0,
                 risk_checked="2026-11-02T09:41", created="2026-11-02T09:41")
        (self.dir / "orders.json").write_text(json.dumps({"orders": [t]}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_ticket(self, *args, paper=True):
        (self.dir / "config.json").write_text(json.dumps({"paper": paper}))
        env = dict(os.environ, IMT_DIR=str(self.dir), IMT_NOW="2026-11-02T09:45")
        env.pop("IMT_FIXTURES", None)
        return subprocess.run([sys.executable, str(SK / "india-broker/ticket.py"), *args], capture_output=True,
                              text=True, env=env, timeout=60)

    def test_preview_sends_nothing_and_works_logged_out(self):
        p = self.run_ticket("preview", TICKET["id"], "--broker", "dhan")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("/v2/super/orders", p.stdout)
        self.assertIn("nothing is sent", p.stdout)

    def test_send_blocked_in_paper_mode(self):
        p = self.run_ticket("send", TICKET["id"], "--broker", "dhan", "--live", "--yes")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("paper mode is on", p.stderr)

    def test_send_needs_live_and_yes(self):
        p = self.run_ticket("send", TICKET["id"], "--broker", "dhan", "--yes", paper=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("nothing sent", p.stderr)

    def test_send_needs_session(self):
        p = self.run_ticket("send", TICKET["id"], "--broker", "dhan", "--live", "--yes", paper=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not logged in", p.stderr)

    def test_stop_needs_sent_entry(self):
        p = self.run_ticket("send-stop", TICKET["id"], "--broker", "angelone", "--live", "--yes", paper=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("needs to be SENT", p.stderr)

    def test_login_refuses_without_a_terminal(self):
        env = dict(os.environ, IMT_DIR=str(self.dir))
        p = subprocess.run([sys.executable, str(SK / "india-broker/connect.py"), "login", "angelone"],
                           input="", capture_output=True, text=True, env=env, timeout=30)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("your own terminal", p.stderr)

    def test_session_file_is_private_and_expires(self):
        os.environ["IMT_DIR"] = str(self.dir)
        os.environ["IMT_NOW"] = "2026-11-02T09:00"
        try:
            p = B.save_session("dhan", {"client_id": "C", "token": "T"})
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            self.assertEqual(B.load_session("dhan")["client_id"], "C")
            os.environ["IMT_NOW"] = "2026-11-03T09:00"
            with self.assertRaises(B.BrokerError):
                B.load_session("dhan")
        finally:
            os.environ.pop("IMT_DIR")
            os.environ.pop("IMT_NOW")

    def test_send_records_order_id(self):
        sys.path.insert(0, str(SK / "india-broker"))
        os.environ["IMT_DIR"] = str(self.dir)
        os.environ["IMT_NOW"] = "2026-11-02T09:45"
        import importlib
        import ticket
        importlib.reload(ticket)
        try:
            B.save_session("dhan", {"client_id": "C", "token": "T"})
            sent = []
            orig_http, orig_map = B.http, B.Dhan.symbol_map
            B.http = lambda req, timeout=20: sent.append(req) or {"orderId": "D123", "orderStatus": "PENDING"}
            B.Dhan.symbol_map = staticmethod(lambda: {"SBIN": "3045"})
            cfg = {"paper": False}
            book = json.loads((self.dir / "orders.json").read_text())
            ticket.cmd_send(book, cfg, TICKET["id"], "dhan", True, True, "entry")
            o = json.loads((self.dir / "orders.json").read_text())["orders"][0]
            self.assertEqual((o["status"], o["broker_id"], o["bracket"]), ("SENT", "D123", True))
            self.assertTrue(sent[0]["url"].endswith("/super/orders"))
        finally:
            B.http, B.Dhan.symbol_map = orig_http, orig_map
            os.environ.pop("IMT_DIR")
            os.environ.pop("IMT_NOW")


class ChargesAndRisk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fx = make_fixtures.make(Path(cls.tmp.name) / "fx")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_broker_brokerage(self):
        self.assertAlmostEqual(costs.brokerage(10000, "zerodha"), 3.0)          # 0.03%
        self.assertAlmostEqual(costs.brokerage(10000, "angelone"), 10.0)        # 0.1%
        self.assertAlmostEqual(costs.brokerage(2000, "groww"), 5.0)             # Rs 5 minimum
        self.assertAlmostEqual(costs.brokerage(200, "groww"), 5.0)              # min still applies...
        self.assertAlmostEqual(costs.brokerage(100, "flat20"), 2.5)             # ...but never above 2.5% of value
        self.assertAlmostEqual(costs.brokerage(500000, "upstox"), 20.0)         # Rs 20 cap
        self.assertTrue(all(b in costs.PROFILES for b in costs.BROKERS))
        self.assertGreaterEqual(dt.date.fromisoformat(costs.RATES_AS_OF), dt.date(2026, 11, 1))

    def test_pit_guard_surveillance_and_holiday(self):
        import check
        from core import DEFAULT_CONFIG
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        cfg["pit_restricted"] = ["tcs"]
        order = {"symbol": "TCS", "direction": "long", "side": "BUY", "qty": 5, "limit": 2500.0, "stop": 2480.0,
                 "target": 2550.0, "flat_by": "15:10", "value": 12500.0, "margin_needed": 12500.0,
                 "est_loss_at_stop": 110.0, "rr_net": 2.2, "leverage": 1}
        ctx = {"now": dt.datetime(2026, 11, 2, 10, 0, tzinfo=IST), "stats": (0.0, 0, 0.0), "cash": 100000,
               "bands": {"TCS": {"series": "EQ", "band": None}}, "prev_close": 2490.0, "news": {}, "sentiment": {},
               "quote": {"series": "EQ", "band": "No Band", "surveillance": "ASM Stage I", "surveillance_desc": "",
                         "upper_circuit": None}, "market_day": (False, "NSE holiday: Diwali")}
        res = {c["check"]: c["result"] for c in check.check_order(order, cfg, ctx)}
        self.assertEqual(res["SEBI insider guard"], "BLOCK")
        self.assertEqual(res["ASM/GSM surveillance"], "BLOCK")
        self.assertEqual(res["market open today"], "BLOCK")
        cfg["pit_restricted"] = []
        ctx["quote"], ctx["market_day"] = {}, (True, "")
        res = {c["check"]: c["result"] for c in check.check_order(order, cfg, ctx)}
        self.assertEqual((res["SEBI insider guard"], res["market open today"]), ("PASS", "PASS"))
        self.assertNotIn("ASM/GSM surveillance", res)

    def test_quote_and_holidays_from_nse_shapes(self):
        import data
        os.environ["IMT_FIXTURES"] = str(self.fx)
        os.environ["IMT_DIR"] = str(Path(self.tmp.name) / "trader")
        try:
            q = data.nse_quote("T2TCO")
            self.assertEqual((q["series"], q["surveillance"], q["upper_circuit"]), ("BE", "ASM Stage I", 105.0))
            self.assertEqual(data.market_day(dt.date(2026, 11, 10))[0], False)     # holiday in fixture
            self.assertEqual(data.market_day(dt.date(2026, 11, 7))[0], False)      # Saturday
            self.assertEqual(data.market_day(dt.date(2026, 11, 2)), (True, ""))
            self.assertEqual(data.nse_quote("NOSUCH"), {})                          # refused -> empty, not a crash
        finally:
            os.environ.pop("IMT_FIXTURES")
            os.environ.pop("IMT_DIR")

    def run_tool(self, rel, *args, when="2026-11-02T09:05"):
        env = dict(os.environ, IMT_FIXTURES=str(self.fx), IMT_DIR=str(Path(self.tmp.name) / "trader2"), IMT_NOW=when)
        return subprocess.run([sys.executable, str(SK / rel), *args], capture_output=True, text=True, env=env,
                              timeout=120)

    def test_pulse(self):
        p = self.run_tool("india-pulse/pulse.py")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("pre-open", p.stdout)
        self.assertIn("Regime:", p.stdout)
        self.assertIn("FII/FPI", p.stdout)
        self.assertIn("Next NSE holiday: Tue 10 Nov", p.stdout)
        out = json.loads((Path(self.tmp.name) / "trader2" / "pulse.json").read_text())
        self.assertIn(out["sections"]["regime"]["label"], ("risk-on", "mixed", "risk-off"))

    def test_scanner_refuses_on_holiday(self):
        p = self.run_tool("india-scanner/scan.py", "orb", "--symbols", "TESTCO", when="2026-11-10T10:00")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("NSE holiday", p.stderr)

    def test_journal_readiness(self):
        d = Path(self.tmp.name) / "trader3"
        d.mkdir(exist_ok=True)
        closed = []
        for i in range(24):
            day = (dt.date(2026, 9, 1) + dt.timedelta(days=i * 2)).isoformat()
            net = 300.0 if i % 3 else -180.0
            closed.append({"id": f"X{i}", "symbol": "SBIN", "date": day, "side": "long", "qty": 10, "entry": 100,
                           "exit": 101, "outcome": "target" if net > 0 else "stop", "gross_pnl": net + 40,
                           "charges": 40.0, "net_pnl": net, "risk_ps": 20})
        (d / "paper_ledger.json").write_text(json.dumps({"cash": 0, "start_cash": 0, "open": [], "closed": closed}))
        env = dict(os.environ, IMT_DIR=str(d), IMT_NOW="2026-11-02T16:00")
        p = subprocess.run([sys.executable, str(SK / "india-journal/journal.py")], capture_output=True, text=True,
                           env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        j = json.loads((d / "journal.json").read_text())
        self.assertEqual(j["paper"]["trades"], 24)
        self.assertAlmostEqual(j["paper"]["win_rate"], 66.7, places=1)
        self.assertTrue(j["readiness"]["ready"], j["readiness"])
        self.assertIn("meets the minimum bar", p.stdout)


if __name__ == "__main__":
    unittest.main()

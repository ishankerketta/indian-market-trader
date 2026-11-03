"""Direct broker adapters for Indian brokers: Angel One, Dhan, Zerodha, Upstox, Fyers, Groww,
plus OpenAlgo (a self-hosted gateway to ~40 brokers).

Safety model
  * Logging in happens only in the user's own terminal (connect.py refuses to run without a TTY),
    so passwords, PINs, TOTP codes and API secrets never pass through Claude. Only the session
    token (and the non-secret API key / client id the requests need) is saved, chmod 600.
  * build() turns a ticket into the exact HTTP request without sending anything. send() is only
    reached through ticket.py with paper=false, a fresh risk PASS, --live and --yes.
  * Every adapter is written from the broker's public API documentation (links below). Field
    names and endpoints change; preview a request and test with one share before trusting it.

SEBI's retail algo framework (in force since 1 Apr 2026): brokers accept API orders only from a
static IP registered with them. Read-only calls usually work from any IP.
"""
import csv
import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from core import now, state_dir, norm_symbol

DOCS = {
    "angelone": "https://smartapi.angelone.in/docs",
    "dhan": "https://dhanhq.co/docs/v2/",
    "zerodha": "https://kite.trade/docs/connect/v3/",
    "upstox": "https://upstox.com/developer/api-documentation/",
    "fyers": "https://myapi.fyers.in/docsv3",
    "groww": "https://groww.in/trade-api/docs",
    "openalgo": "https://docs.openalgo.in/",
}

# Official MCP servers we know of (checked Oct-Nov 2026; capabilities change, verify in Claude)
MCP = {
    "dhan": ("https://mcp.dhan.co/mcp", "orders incl. Super Orders"),
    "groww": ("https://mcp.groww.in/mcp", "buy, limit and SL orders; sells need DDPI"),
    "zerodha": ("https://mcp.kite.trade/mcp", "hosted server: GTT orders only; self-host the open-source server for full orders"),
    "upstox": ("https://mcp.upstox.com/mcp", "read-only; Upstox's separate agent skill can trade"),
    "fyers": ("https://mcp.fyers.in/mcp", "FYERS docs list order tools; confirm in your connector"),
    "angelone": (None, "no official MCP; use this adapter or OpenAlgo"),
}


class BrokerError(Exception):
    pass


# ---------------------------------------------------------------- sessions

def broker_dir():
    d = state_dir() / "brokers"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def save_session(name, data):
    p = broker_dir() / f"{name}.json"
    data = dict(data, saved=now().isoformat(timespec="minutes"))
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    return p


def load_session(name):
    p = broker_dir() / f"{name}.json"
    if not p.exists():
        raise BrokerError(f"not logged in to {name}: run `python3 connect.py login {name}` in your own terminal")
    with open(p) as f:
        s = json.load(f)
    # Most Indian broker sessions expire daily (Zerodha ~6 AM next day, Angel at midnight)
    if s.get("saved", "")[:10] != now().date().isoformat() and name not in ("openalgo",):
        raise BrokerError(f"{name} session is from {s.get('saved', '?')[:10]}; broker tokens expire daily. "
                          f"Log in again: `python3 connect.py login {name}`")
    return s


REDACT = ("authorization", "access-token", "x-privatekey", "apikey", "api_key", "x-api-key")


def redact(req):
    """Copy of a request safe to print: secrets replaced with ***."""
    r = json.loads(json.dumps(req))
    for k in list(r.get("headers", {})):
        if k.lower() in REDACT:
            r["headers"][k] = "***"
    body = r.get("body")
    if isinstance(body, dict):
        for k in list(body):
            if k.lower() in REDACT or k in ("dhanClientId",):
                body[k] = "***"
    return r


def http(req, timeout=20):
    """Send a built request. Returns parsed JSON (or text)."""
    data = None
    headers = dict(req.get("headers", {}))
    if req.get("body") is not None:
        if req.get("form"):
            data = urllib.parse.urlencode(req["body"]).encode()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            data = json.dumps(req["body"]).encode()
            headers.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(req["url"], data=data, headers=headers, method=req["method"])
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise BrokerError(f"HTTP {e.code} from {req['url']}: {raw[:300]}")
    except urllib.error.URLError as e:
        raise BrokerError(f"could not reach {req['url']}: {e.reason}")
    try:
        return json.loads(raw)
    except ValueError:
        return raw


# ---------------------------------------------------------------- the common order

ORDER_TYPES = ("LIMIT", "MARKET", "SL", "SL-M")


def ticket_to_legs(t):
    """Our ticket (from india-budget) -> entry leg and stop-loss leg in a broker-neutral form."""
    exit_side = "SELL" if t["side"] == "BUY" else "BUY"
    entry = {"symbol": t["symbol"], "exchange": "NSE", "side": t["side"], "qty": int(t["qty"]),
             "product": "MIS", "order_type": "LIMIT", "price": float(t["limit"]), "trigger": 0.0,
             "tag": t["id"][-20:]}
    slip = 0.005 if exit_side == "SELL" else -0.005
    stop = {"symbol": t["symbol"], "exchange": "NSE", "side": exit_side, "qty": int(t["qty"]),
            "product": "MIS", "order_type": "SL", "trigger": float(t["stop"]),
            "price": round(float(t["stop"]) * (1 - slip), 2), "tag": (t["id"] + "S")[-20:]}
    return entry, stop


def _isin(symbol):
    """ISIN from the cached NSE universe (needed by Upstox instrument keys)."""
    from core import read_state
    uni = read_state("universe.json") or {}
    for s in uni.get("symbols", []):
        if s["symbol"] == symbol and s.get("isin"):
            return s["isin"]
    try:
        from data import col, nse_csv
        for r in nse_csv("equity_list.csv"):
            if norm_symbol(col(r, "SYMBOL")) == symbol:
                return col(r, "ISIN NUMBER", "ISIN")
    except Exception:  # noqa: BLE001
        pass
    raise BrokerError(f"no ISIN for {symbol}; run `scan.py universe --source all` first")


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cached_map(name, builder):
    """Daily-cached symbol -> broker token map (scrip masters are large; filter once a day)."""
    p = broker_dir() / f"{name}_symbols.json"
    today = now().date().isoformat()
    if p.exists():
        with open(p) as f:
            c = json.load(f)
        if c.get("date") == today:
            return c["map"]
    m = builder()
    with open(p, "w") as f:
        json.dump({"date": today, "map": m}, f)
    return m


# ---------------------------------------------------------------- adapters

class Adapter:
    name = "base"
    places_bracket = False      # one order carries entry + stop + target

    def __init__(self, session=None):
        self.s = session

    def place(self, leg):
        raise NotImplementedError

    def bracket(self, ticket):
        raise NotImplementedError

    def orders(self):
        raise NotImplementedError

    def positions(self):
        raise NotImplementedError

    @staticmethod
    def order_id(resp):
        raise NotImplementedError


class AngelOne(Adapter):
    """Angel One SmartAPI. Login: API key + client code + PIN + a fresh TOTP, typed by you."""
    name = "angelone"
    BASE = "https://apiconnect.angelone.in"

    def headers(self):
        return {"Authorization": f"Bearer {self.s['jwt']}", "X-PrivateKey": self.s["api_key"],
                "Content-Type": "application/json", "Accept": "application/json",
                "X-UserType": "USER", "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1",
                "X-ClientPublicIP": self.s.get("public_ip", "127.0.0.1"), "X-MACAddress": "00:00:00:00:00:00"}

    @classmethod
    def login_request(cls, api_key, client_code, pin, totp):
        return {"method": "POST", "url": cls.BASE + "/rest/auth/angelbroking/user/v1/loginByPassword",
                "headers": {"X-PrivateKey": api_key, "Accept": "application/json", "X-UserType": "USER",
                            "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
                            "X-MACAddress": "00:00:00:00:00:00"},
                "body": {"clientcode": client_code, "password": pin, "totp": totp}}

    @staticmethod
    def symbol_map():
        def build():
            raw = _fetch("https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json", 120)
            out = {}
            for r in json.loads(raw):
                if r.get("exch_seg") == "NSE" and str(r.get("symbol", "")).endswith("-EQ"):
                    out[r["symbol"][:-3]] = {"token": r["token"], "tradingsymbol": r["symbol"]}
            return out
        return _cached_map("angelone", build)

    def place(self, leg, token=None):
        info = token or self.symbol_map().get(leg["symbol"])
        if not info:
            raise BrokerError(f"{leg['symbol']} not in Angel One's NSE equity scrip master")
        ot = {"LIMIT": "LIMIT", "MARKET": "MARKET", "SL": "STOPLOSS_LIMIT", "SL-M": "STOPLOSS_MARKET"}[leg["order_type"]]
        body = {"variety": "STOPLOSS" if leg["order_type"] in ("SL", "SL-M") else "NORMAL",
                "tradingsymbol": info["tradingsymbol"], "symboltoken": str(info["token"]),
                "transactiontype": leg["side"], "exchange": "NSE", "ordertype": ot, "producttype": "INTRADAY",
                "duration": "DAY", "price": f"{leg['price']:.2f}", "triggerprice": f"{leg['trigger']:.2f}",
                "squareoff": "0", "stoploss": "0", "quantity": str(leg["qty"]), "ordertag": leg["tag"]}
        return {"method": "POST", "url": self.BASE + "/rest/secure/angelbroking/order/v1/placeOrder",
                "headers": self.headers(), "body": body}

    def orders(self):
        return {"method": "GET", "url": self.BASE + "/rest/secure/angelbroking/order/v1/getOrderBook",
                "headers": self.headers()}

    def positions(self):
        return {"method": "GET", "url": self.BASE + "/rest/secure/angelbroking/order/v1/getPosition",
                "headers": self.headers()}

    @staticmethod
    def order_id(resp):
        return ((resp or {}).get("data") or {}).get("orderid")


class Dhan(Adapter):
    """DhanHQ v2. Login: paste your Client ID and an access token generated on web.dhan.co.
    Uses a Super Order (entry + target + stop-loss in one) for brackets."""
    name = "dhan"
    BASE = "https://api.dhan.co/v2"
    places_bracket = True

    def headers(self):
        return {"access-token": self.s["token"], "Content-Type": "application/json", "Accept": "application/json"}

    @staticmethod
    def symbol_map():
        def build():
            raw = _fetch("https://images.dhan.co/api-data/api-scrip-master.csv", 120).decode("utf-8", "replace")
            out = {}
            for r in csv.DictReader(io.StringIO(raw)):
                if r.get("SEM_EXM_EXCH_ID") == "NSE" and r.get("SEM_SEGMENT") == "E" and \
                        r.get("SEM_SERIES", "EQ") in ("EQ", ""):
                    out[r.get("SEM_TRADING_SYMBOL", "").upper()] = r.get("SEM_SMST_SECURITY_ID")
            return out
        return _cached_map("dhan", build)

    def _sec(self, symbol, security_id=None):
        sid = security_id or self.symbol_map().get(symbol)
        if not sid:
            raise BrokerError(f"{symbol} not in Dhan's NSE equity scrip master")
        return str(sid)

    def place(self, leg, security_id=None):
        ot = {"LIMIT": "LIMIT", "MARKET": "MARKET", "SL": "STOP_LOSS", "SL-M": "STOP_LOSS_MARKET"}[leg["order_type"]]
        body = {"dhanClientId": self.s["client_id"], "correlationId": leg["tag"], "transactionType": leg["side"],
                "exchangeSegment": "NSE_EQ", "productType": "INTRADAY", "orderType": ot, "validity": "DAY",
                "securityId": self._sec(leg["symbol"], security_id), "quantity": leg["qty"],
                "price": round(leg["price"], 2), "triggerPrice": round(leg["trigger"], 2)}
        return {"method": "POST", "url": self.BASE + "/orders", "headers": self.headers(), "body": body}

    def bracket(self, t, security_id=None):
        body = {"dhanClientId": self.s["client_id"], "correlationId": t["id"][-20:], "transactionType": t["side"],
                "exchangeSegment": "NSE_EQ", "productType": "INTRADAY", "orderType": "LIMIT",
                "securityId": self._sec(t["symbol"], security_id), "quantity": int(t["qty"]),
                "price": round(float(t["limit"]), 2), "targetPrice": round(float(t["target"]), 2),
                "stopLossPrice": round(float(t["stop"]), 2), "trailingJump": 0}
        return {"method": "POST", "url": self.BASE + "/super/orders", "headers": self.headers(), "body": body}

    def orders(self):
        return {"method": "GET", "url": self.BASE + "/orders", "headers": self.headers()}

    def positions(self):
        return {"method": "GET", "url": self.BASE + "/positions", "headers": self.headers()}

    @staticmethod
    def order_id(resp):
        return (resp or {}).get("orderId")


class Zerodha(Adapter):
    """Kite Connect v3 (needs your own Kite Connect app). Login: API key + secret, then the
    request_token from the redirect URL after you sign in to Kite in the browser."""
    name = "zerodha"
    BASE = "https://api.kite.trade"

    def headers(self):
        return {"X-Kite-Version": "3", "Authorization": f"token {self.s['api_key']}:{self.s['access_token']}"}

    @staticmethod
    def login_url(api_key):
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={urllib.parse.quote(api_key)}"

    @classmethod
    def session_request(cls, api_key, request_token, api_secret):
        checksum = hashlib.sha256((api_key + request_token + api_secret).encode()).hexdigest()
        return {"method": "POST", "url": cls.BASE + "/session/token", "form": True,
                "headers": {"X-Kite-Version": "3"},
                "body": {"api_key": api_key, "request_token": request_token, "checksum": checksum}}

    def place(self, leg):
        body = {"tradingsymbol": leg["symbol"], "exchange": "NSE", "transaction_type": leg["side"],
                "order_type": leg["order_type"], "quantity": leg["qty"], "product": "MIS", "validity": "DAY",
                "price": round(leg["price"], 2) if leg["order_type"] in ("LIMIT", "SL") else 0,
                "trigger_price": round(leg["trigger"], 2) if leg["order_type"] in ("SL", "SL-M") else 0,
                "tag": leg["tag"][:20]}
        return {"method": "POST", "url": self.BASE + "/orders/regular", "form": True,
                "headers": self.headers(), "body": body}

    def orders(self):
        return {"method": "GET", "url": self.BASE + "/orders", "headers": self.headers()}

    def positions(self):
        return {"method": "GET", "url": self.BASE + "/portfolio/positions", "headers": self.headers()}

    @staticmethod
    def order_id(resp):
        return ((resp or {}).get("data") or {}).get("order_id")


class Upstox(Adapter):
    """Upstox API v2. Login: API key + secret + redirect URI, then the `code` from the redirect URL."""
    name = "upstox"
    BASE = "https://api.upstox.com/v2"

    def headers(self):
        return {"Authorization": f"Bearer {self.s['access_token']}", "Accept": "application/json",
                "Content-Type": "application/json"}

    @staticmethod
    def login_url(api_key, redirect):
        q = urllib.parse.urlencode({"response_type": "code", "client_id": api_key, "redirect_uri": redirect})
        return f"https://api.upstox.com/v2/login/authorization/dialog?{q}"

    @classmethod
    def token_request(cls, code, api_key, api_secret, redirect):
        return {"method": "POST", "url": cls.BASE + "/login/authorization/token", "form": True,
                "headers": {"Accept": "application/json"},
                "body": {"code": code, "client_id": api_key, "client_secret": api_secret,
                         "redirect_uri": redirect, "grant_type": "authorization_code"}}

    def place(self, leg, isin=None):
        body = {"quantity": leg["qty"], "product": "I", "validity": "DAY",
                "price": round(leg["price"], 2) if leg["order_type"] in ("LIMIT", "SL") else 0,
                "tag": leg["tag"][:20], "instrument_token": f"NSE_EQ|{isin or _isin(leg['symbol'])}",
                "order_type": leg["order_type"], "transaction_type": leg["side"], "disclosed_quantity": 0,
                "trigger_price": round(leg["trigger"], 2) if leg["order_type"] in ("SL", "SL-M") else 0,
                "is_amo": False}
        return {"method": "POST", "url": self.BASE + "/order/place", "headers": self.headers(), "body": body}

    def orders(self):
        return {"method": "GET", "url": self.BASE + "/order/retrieve-all", "headers": self.headers()}

    def positions(self):
        return {"method": "GET", "url": self.BASE + "/portfolio/short-term-positions", "headers": self.headers()}

    @staticmethod
    def order_id(resp):
        return ((resp or {}).get("data") or {}).get("order_id")


class Fyers(Adapter):
    """FYERS API v3. Login: App ID (e.g. XXXX-100) + secret + redirect URI, then the auth_code."""
    name = "fyers"
    BASE = "https://api-t1.fyers.in/api/v3"

    def headers(self):
        return {"Authorization": f"{self.s['app_id']}:{self.s['access_token']}", "Content-Type": "application/json"}

    @staticmethod
    def login_url(app_id, redirect):
        q = urllib.parse.urlencode({"client_id": app_id, "redirect_uri": redirect, "response_type": "code",
                                    "state": "imt"})
        return f"https://api-t1.fyers.in/api/v3/generate-authcode?{q}"

    @classmethod
    def token_request(cls, app_id, secret, code):
        h = hashlib.sha256(f"{app_id}:{secret}".encode()).hexdigest()
        return {"method": "POST", "url": cls.BASE + "/validate-authcode", "headers": {},
                "body": {"grant_type": "authorization_code", "appIdHash": h, "code": code}}

    def place(self, leg):
        typ = {"LIMIT": 1, "MARKET": 2, "SL-M": 3, "SL": 4}[leg["order_type"]]
        body = {"symbol": f"NSE:{leg['symbol']}-EQ", "qty": leg["qty"], "type": typ,
                "side": 1 if leg["side"] == "BUY" else -1, "productType": "INTRADAY",
                "limitPrice": round(leg["price"], 2) if typ in (1, 4) else 0,
                "stopPrice": round(leg["trigger"], 2) if typ in (3, 4) else 0,
                "validity": "DAY", "disclosedQty": 0, "offlineOrder": False, "stopLoss": 0, "takeProfit": 0,
                "orderTag": "".join(ch for ch in leg["tag"] if ch.isalnum())[:20]}
        return {"method": "POST", "url": self.BASE + "/orders/sync", "headers": self.headers(), "body": body}

    def orders(self):
        return {"method": "GET", "url": self.BASE + "/orders", "headers": self.headers()}

    def positions(self):
        return {"method": "GET", "url": self.BASE + "/positions", "headers": self.headers()}

    @staticmethod
    def order_id(resp):
        return (resp or {}).get("id")


class Groww(Adapter):
    """Groww Trade API. Login: paste an access token generated from your Groww Trade API page."""
    name = "groww"
    BASE = "https://api.groww.in/v1"

    def headers(self):
        return {"Authorization": f"Bearer {self.s['access_token']}", "Accept": "application/json",
                "X-API-VERSION": "1.0", "Content-Type": "application/json"}

    def place(self, leg):
        ot = {"LIMIT": "LIMIT", "MARKET": "MARKET", "SL": "SL", "SL-M": "SL_M"}[leg["order_type"]]
        ref = ("imt" + "".join(ch for ch in leg["tag"] if ch.isalnum()))[:20]
        body = {"trading_symbol": leg["symbol"], "quantity": leg["qty"],
                "price": round(leg["price"], 2) if ot in ("LIMIT", "SL") else 0,
                "trigger_price": round(leg["trigger"], 2) if ot in ("SL", "SL_M") else None,
                "validity": "DAY", "exchange": "NSE", "segment": "CASH", "product": "MIS",
                "order_type": ot, "transaction_type": leg["side"], "order_reference_id": ref}
        if body["trigger_price"] is None:
            del body["trigger_price"]
        return {"method": "POST", "url": self.BASE + "/order/create", "headers": self.headers(), "body": body}

    def orders(self):
        return {"method": "GET", "url": self.BASE + "/order/list?segment=CASH", "headers": self.headers()}

    def positions(self):
        return {"method": "GET", "url": self.BASE + "/positions/user?segment=CASH", "headers": self.headers()}

    @staticmethod
    def order_id(resp):
        p = (resp or {}).get("payload") or {}
        return p.get("groww_order_id") or p.get("order_id")


class OpenAlgo(Adapter):
    """OpenAlgo (github.com/marketcalls/openalgo, AGPL-3.0, run separately by you): one API for
    ~40 Indian brokers. We only call its HTTP API; none of its code is included here.
    Its Analyzer mode is a broker-side sandbox, handy for testing."""
    name = "openalgo"

    def _url(self, path):
        return self.s.get("host", "http://127.0.0.1:5000").rstrip("/") + path

    def place(self, leg):
        body = {"apikey": self.s["api_key"], "strategy": "indian-market-trader", "symbol": leg["symbol"],
                "action": leg["side"], "exchange": "NSE", "pricetype": leg["order_type"], "product": "MIS",
                "quantity": str(leg["qty"]), "price": f"{leg['price']:.2f}", "trigger_price": f"{leg['trigger']:.2f}",
                "disclosed_quantity": "0"}
        return {"method": "POST", "url": self._url("/api/v1/placeorder"), "headers": {}, "body": body}

    def orders(self):
        return {"method": "POST", "url": self._url("/api/v1/orderbook"), "headers": {}, "body": {"apikey": self.s["api_key"]}}

    def positions(self):
        return {"method": "POST", "url": self._url("/api/v1/positionbook"), "headers": {},
                "body": {"apikey": self.s["api_key"]}}

    @staticmethod
    def order_id(resp):
        return (resp or {}).get("orderid")


ADAPTERS = {a.name: a for a in (AngelOne, Dhan, Zerodha, Upstox, Fyers, Groww, OpenAlgo)}
ALIASES = {"angel": "angelone", "angel-one": "angelone", "kite": "zerodha", "dhanhq": "dhan"}


def get(name, session=None, needs_session=True):
    key = ALIASES.get(name.lower(), name.lower())
    if key not in ADAPTERS:
        raise BrokerError(f"unknown broker {name!r}; choose from {', '.join(ADAPTERS)}")
    s = session if session is not None else (load_session(key) if needs_session else {})
    return ADAPTERS[key](s)

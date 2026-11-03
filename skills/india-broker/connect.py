#!/usr/bin/env python3
"""Broker connections for Angel One, Dhan, Zerodha, Upstox, Fyers, Groww and OpenAlgo.

  connect.py brokers                    supported brokers, routes and what each needs
  connect.py login BROKER               YOU run this in your own terminal (it refuses otherwise)
  connect.py status                     which sessions exist and whether they are fresh
  connect.py orders BROKER              today's order book (read-only)
  connect.py positions BROKER           open positions (read-only)
  connect.py logout BROKER              forget the saved session

Login prompts for secrets with hidden input and saves only the day's session token,
in trader/brokers/BROKER.json, readable only by your user. Nothing secret is printed.
"""
import argparse
import getpass
import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "_shared" if (_HERE / "_shared").is_dir() else _HERE.parent / "_shared"))

import brokers as B  # noqa: E402
from core import die, now  # noqa: E402

NEEDS = {
    "angelone": "SmartAPI app API key, client code, login PIN, and a fresh 6-digit TOTP from your authenticator",
    "dhan": "Client ID and an access token generated on web.dhan.co > My Profile > DhanHQ Trading APIs",
    "zerodha": "Kite Connect app API key and secret (developers.kite.trade), then a browser login",
    "upstox": "Upstox developer app API key, secret and redirect URI, then a browser login",
    "fyers": "FYERS API app ID (XXXX-100), secret and redirect URI, then a browser login",
    "groww": "an access token generated on your Groww Trade API page",
    "openalgo": "your OpenAlgo host (default http://127.0.0.1:5000) and its API key",
}


def ask(prompt, secret=False, default=None):
    q = f"{prompt}{f' [{default}]' if default else ''}: "
    v = getpass.getpass(q) if secret else input(q)
    v = v.strip() or (default or "")
    if not v:
        die(f"{prompt} is required")
    return v


def login(name):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        die("login must be run by you in your own terminal, not by an assistant or a script. "
            f"Open Terminal and run: python3 {pathlib.Path(__file__).name} login {name}")
    key = B.ALIASES.get(name.lower(), name.lower())
    if key not in B.ADAPTERS:
        die(f"unknown broker {name!r}; choose from {', '.join(B.ADAPTERS)}")
    print(f"Logging in to {key}. You need: {NEEDS[key]}.")
    print("Secrets are read with hidden input and are not saved; only today's session token is.\n")
    try:
        if key == "angelone":
            api_key = ask("SmartAPI API key", secret=True)
            client = ask("Client code")
            pin = ask("Login PIN", secret=True)
            totp = ask("TOTP (6 digits, from your authenticator app)")
            r = B.http(B.AngelOne.login_request(api_key, client, pin, totp))
            data = (r or {}).get("data") or {}
            if not data.get("jwtToken"):
                die(f"Angel One login failed: {(r or {}).get('message', r)}")
            B.save_session(key, {"api_key": api_key, "client_code": client, "jwt": data["jwtToken"]})
        elif key == "dhan":
            cid = ask("Dhan Client ID")
            tok = ask("Access token", secret=True)
            B.save_session(key, {"client_id": cid, "token": tok})
        elif key == "zerodha":
            api_key = ask("Kite Connect API key")
            secret = ask("API secret", secret=True)
            print(f"\nOpen this, sign in, then copy request_token=... from the address bar it redirects to:\n"
                  f"  {B.Zerodha.login_url(api_key)}\n")
            rt = ask("request_token")
            r = B.http(B.Zerodha.session_request(api_key, rt, secret))
            tok = ((r or {}).get("data") or {}).get("access_token")
            if not tok:
                die(f"Kite login failed: {(r or {}).get('message', r)}")
            B.save_session(key, {"api_key": api_key, "access_token": tok})
        elif key == "upstox":
            api_key = ask("Upstox API key")
            secret = ask("API secret", secret=True)
            redirect = ask("Redirect URI (as set in your Upstox app)")
            print(f"\nOpen this, sign in, then copy code=... from the redirect URL:\n  {B.Upstox.login_url(api_key, redirect)}\n")
            code = ask("code")
            r = B.http(B.Upstox.token_request(code, api_key, secret, redirect))
            tok = (r or {}).get("access_token")
            if not tok:
                die(f"Upstox login failed: {r}")
            B.save_session(key, {"access_token": tok})
        elif key == "fyers":
            app_id = ask("FYERS App ID (e.g. ABCD1234-100)")
            secret = ask("App secret", secret=True)
            redirect = ask("Redirect URI (as set in your FYERS app)")
            print(f"\nOpen this, sign in, then copy auth_code=... from the redirect URL:\n  {B.Fyers.login_url(app_id, redirect)}\n")
            code = ask("auth_code")
            r = B.http(B.Fyers.token_request(app_id, secret, code))
            tok = (r or {}).get("access_token")
            if not tok:
                die(f"FYERS login failed: {(r or {}).get('message', r)}")
            B.save_session(key, {"app_id": app_id, "access_token": tok})
        elif key == "groww":
            tok = ask("Groww access token", secret=True)
            B.save_session(key, {"access_token": tok})
        elif key == "openalgo":
            host = ask("OpenAlgo host", default="http://127.0.0.1:5000")
            api_key = ask("OpenAlgo API key", secret=True)
            B.save_session(key, {"host": host, "api_key": api_key})
    except B.BrokerError as e:
        die(str(e))
    print(f"\nSaved a {key} session for today in trader/brokers/{key}.json (readable only by you).")
    print("Orders still need: \"paper\": false in trader/config.json, a risk PASS, and your yes for each ticket.")


def cmd_brokers():
    print(f"{'broker':<10}{'direct API (this pack)':<26}{'official MCP for Claude':<34}notes")
    for k in ("angelone", "dhan", "zerodha", "upstox", "fyers", "groww", "openalgo"):
        url, note = B.MCP.get(k, (None, "self-hosted gateway to ~40 brokers (AGPL, run separately)"))
        bracket = "bracket via Super Order" if k == "dhan" else "entry, then stop-loss"
        print(f"{k:<10}{bracket:<26}{(url or '-'):<34}{note}")
    print("\nDirect API orders need a static IP registered with your broker (SEBI retail algo framework, "
          "Apr 2026). Read-only calls work from any IP.")


def cmd_status():
    d = B.broker_dir()
    found = False
    for p in sorted(d.glob("*.json")):
        if p.name.endswith("_symbols.json"):
            continue
        found = True
        s = json.loads(p.read_text())
        fresh = s.get("saved", "")[:10] == now().date().isoformat()
        print(f"{p.stem:<10} saved {s.get('saved', '?')}  {'fresh' if fresh else 'EXPIRED: log in again'}")
    if not found:
        print("No broker sessions. Run `python3 connect.py login BROKER` in your own terminal.")


def cmd_read(name, what):
    try:
        a = B.get(name)
        resp = B.http(getattr(a, what)())
    except B.BrokerError as e:
        die(str(e))
    print(json.dumps(resp, indent=2)[:6000])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["brokers", "login", "status", "orders", "positions", "logout"])
    ap.add_argument("broker", nargs="?")
    args = ap.parse_args()
    if args.cmd == "brokers":
        cmd_brokers()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "login":
        login(args.broker or die("which broker?"))
    elif args.cmd in ("orders", "positions"):
        cmd_read(args.broker or die("which broker?"), args.cmd)
    else:
        key = B.ALIASES.get((args.broker or "").lower(), (args.broker or "").lower())
        p = B.broker_dir() / f"{key}.json"
        if p.exists():
            p.unlink()
            print(f"Forgot the {key} session.")
        else:
            print(f"No {key} session saved.")


if __name__ == "__main__":
    main()

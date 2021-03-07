#!/bin/python3

SANDBOX = True
if SANDBOX:
    OUTF = "sandbox-trade-data.log"
else:
    OUTF = "trade-data.log"

import base64
import hashlib
import hmac
import json
import math
import os.path
import requests
import sys

from decimal import *
from enum import Enum, unique
from datetime import datetime, timezone, timedelta
from pprint import pp

if SANDBOX:
    print("== running in Sandbox Mode ==")
else:
    print("== NOT RUNNING IN SANDBOX MODE! ==")


# see https://www.gemini.com/fees/api-fee-schedule#section-api-fee-schedule
USD_PER_YEAR = 100_000
USD_PER_DAY = round(USD_PER_YEAR / 365, 2)
ALLOWED_DEV_MKT = 1 / 500 # i.e. will pay up to 1/500th USD more than market price

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

if SANDBOX:
    KEY    = "account-XXXXXXXXXXXXXXXXXXXX"
    SECRET = "XXXXXXXXXXXXXXXXXXXXXXXXXXXX".encode()
else:
    KEY    = open("/hdd-mirror0/E/gemini-api-key").readline()
    SECRET = open("/hdd-mirror0/E/gemini-api-secret").readline().encode()

# api routes
VERSION         = "v1"
BASEURL         = "https://api.gemini.com"
SANDBOX_BASEURL = "https://api.sandbox.gemini.com"

@unique
class Pair(Enum):
    BTCUSD = None

# see documentation for pair tick sizes
TICKSIZES = {
    Pair.BTCUSD.name: 1e-8
}

class Url:
    def __init__(self, suffix, sandbox=SANDBOX):
        """Suffix should neither begin nor end with \ """
        if sandbox:
            self.pfix = SANDBOX_BASEURL
        else:
            self.pfix = BASEURL
        self.v = VERSION
        self.sfix = suffix

    def full(self):
        return f"{self.pfix}/{self.v}/{self.sfix}"

    def payload_request(self):
        """route used in a payload's REQUEST param"""
        return f"/{self.v}/{self.sfix}"

GET_PAIR_DATA_URL  = Url("symbols/details")
PRICE_FEED_URL     = Url("pricefeed")
NEW_ORDER_URL      = Url("order/new")
ORDER_STATUS_URL   = Url("order/status")
NOTIONAL_VOL_URL   = Url("notionalvolume")
MYTRADES_URL       = Url("mytrades")


# assistance funcs
def y_or_n_p(prompt) -> bool:
    """True if user inputs y or yes (case-insensitive). False otherwise"""
    x = input(f"{prompt}\ny or n: ")
    return x.upper() == "Y" or x.upper() == "YES"

def get_time_ms() -> int:
    """Used as a nonce"""
    now = datetime.now(timezone.utc)
    ptime_ms = (now - EPOCH) // timedelta(microseconds=1)
    return ptime_ms // 1000

def round_pair(pair: Pair, amt: float) -> float:
    """Round the given pair to its most precise purchasable amount"""
    def ticksize_to_nth(ticksize: float) -> float:
        return math.floor(math.log10(1 / ticksize))
    return round(amt, ticksize_to_nth(TICKSIZES[pair.name]))

def priv_api_headers(payload: str, sig: str, api_key: str) -> dict:
    return {
        "Content-Type"       : "text/plain",
        "Content-Length"     : "0",
        "X-GEMINI-APIKEY"    : api_key,
        "X-GEMINI-PAYLOAD"   : payload,
        "X-GEMINI-SIGNATURE" : sig,
        "Cache-Control"      : "no-cache",
    }

def bpstof(bps) -> float:
    """Convert basis point to float"""
    return 0.0001 * bps

def encrypt(payload):
    return base64.b64encode(json.dumps(payload).encode())

def sign(enc_payload):
    return hmac.new(SECRET, enc_payload, hashlib.sha384).hexdigest()


# api calling funcs
def get_info(pair: Pair) -> dict:
    url = f"{GET_PAIR_DATA_URL.full()}/{pair.name}"
    resp = requests.get(url)
    return resp.json()

def get_price(pair: Pair) -> float:
    url = f"{PRICE_FEED_URL.full()}"
    resp = requests.get(url)
    price_objects = resp.json()
    for o in price_objects:
        if o["pair"] == pair.name:
            return float(o["price"])

# new order api: https://docs.gemini.com/rest-api/?python#new-order
def make_daily_order(pair: Pair, amt_usd: float, options: list) -> dict:
    """purchase amount of PAIR eq to AMT_USD. Returns dict returned by api"""
    fee = bpstof(get_fee_and_vol()["api_taker_fee_bps"])
    if not SANDBOX:
        typical = 0.0035
        assert fee == typical, f"fee has deviated from what is typical ({typical}). Do something."

    url = NEW_ORDER_URL
    purchase_amt = round_pair(pair, amt_usd / get_price(pair))
    min_order_size = float(get_info(pair)["min_order_size"])
    assert min_order_size <= purchase_amt, f"Purchase amount {purchase_amt} {pair.name} is insufficient. {min_order_size} is lowest purchasable amount."
    curr_price = get_price(pair)
    price_with_dev = round(curr_price + (curr_price * ALLOWED_DEV_MKT), 2)
    est_cost = round(curr_price * purchase_amt, 2)
    est_cost_max_dev = round(purchase_amt * price_with_dev, 2)

    payload = {
        "request" : url.payload_request(),
        "nonce"   : str(get_time_ms()),
        "symbol"  : pair.name,
        "amount"  : str(purchase_amt),
        "price"   : str(price_with_dev),
        "side"    : "buy",
        "type"    : "exchange limit",
        "options" : options,
    }
    enc_payload = encrypt(payload)
    sig = sign(enc_payload)
    headers = priv_api_headers(enc_payload, sig, KEY)

    if y_or_n_p(f"""
Quoted market price      : {curr_price:,.2f} USD / BTC
Allowed deviation        : +{round(price_with_dev - curr_price, 2):,.2f} USD / BTC
Fee                      : {fee}
                           w/out fee\twith fee
Estimated total cost     : {est_cost:,.2f} USD\t{round(est_cost * (1 + fee), 2):,.2f} USD
Total Cost assm. max dev : {est_cost_max_dev:,.2f} USD\t{round(est_cost_max_dev * (1 + fee), 2):,.2f} USD
===
Limit buy {purchase_amt} BTC @ {price_with_dev:,.2f} USD?"""):
        return requests.post(url.full(), data=None, headers=headers).json()


def get_order_status(id: int) -> dict:
    url = ORDER_STATUS_URL
    payload = {
        "request"  : url.payload_request(),
        "nonce"    : str(get_time_ms()),
        "order_id" : id,
    }
    enc_payload = encrypt(payload)
    sig = sign(enc_payload)
    headers = priv_api_headers(enc_payload, sig, KEY)
    return requests.post(url.full(), data=None, headers=headers).json()

def get_fee_and_vol() -> dict:
    url = NOTIONAL_VOL_URL
    payload = {
        "nonce"  : str(get_time_ms()),
        "request": url.payload_request(),
    }
    enc_payload = encrypt(payload)
    sig = sign(enc_payload)
    headers = priv_api_headers(enc_payload, sig, KEY)
    return requests.post(url.full(), data=None, headers=headers).json()

def get_past_trades_after_timestamp(pair: Pair, ts: str) -> list:
    url = MYTRADES_URL
    payload = {
        "nonce"     : str(get_time_ms()),
        "request"   : url.payload_request(),
        "symbol"    : pair.name,
        "timestamp" : ts,
    }
    enc_payload = encrypt(payload)
    sig = sign(enc_payload)
    headers = priv_api_headers(enc_payload, sig, KEY)
    return requests.post(url.full(), data=None, headers=headers).json()



# main =======================================================================

PAIR = Pair.BTCUSD

RESP = make_daily_order(PAIR, USD_PER_DAY, ["fill-or-kill"])
assert RESP, "No response"
print("==order response")
pp(RESP)
assert not RESP["is_cancelled"], "Order was cancelled"

TRADES = get_past_trades_after_timestamp(PAIR, RESP["timestampms"])
STATS = TRADES[0] # should only be one trade in stats, ie the one just execed

print("==trade stats")
pp(STATS)


# logging ====================================================================

if not os.path.isfile(OUTF):
    with open(OUTF, "w+") as f:
        f.writelines([
            # transactionid orderid, timestamp, timestamp(ms), type(buy, sell), pair(BTCUSD, etc.)
            # price, amount, fee_currency (USD), fee_amount, cost_basis(amount * price + fee_amount)
            "tid\torderid\tts\ttsms\ttype\tpair\tprice\tamount\tfee_currency\tfee_amount\tcost_basis\n"
        ])

with open(OUTF, "a") as f:
    sep = "\t"
    cost_basis = Decimal(STATS["fee_amount"]) + Decimal(STATS["price"]) * Decimal(STATS["amount"])
    f.writelines([
        sep.join([
            str(STATS["tid"])
            ,STATS["order_id"]
            ,str(STATS["timestamp"])
            ,str(STATS["timestampms"])
            ,STATS["type"]
            ,PAIR.name
            ,STATS["price"]
            ,STATS["amount"]
            ,STATS["fee_currency"]
            ,STATS["fee_amount"]
            ,str(cost_basis)
            ,"\n"])
    ])
    print("Wrote to log file")


# todo
"""
consider not doing make-or-kill MOK for lower fees.
"""

# sandbox: https://exchange.sandbox.gemini.com/trade/BTCUSD

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
from collections import OrderedDict
from itertools import accumulate


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

#### ===========================================================================
####                                Trade pair info
# TODO in another file. Maybe a config file

@unique
class Pair(Enum):
    # 1INCHUSD = 0        # python likes vars to be named with non-number first :(
    AAVEUSD = 1
    ALCXUSD = 2
    AMPUSD = 3
    ANKRUSD = 4
    AXSUSD = 5
    BALUSD = 6
    BATUSD = 7
    BCHUSD = 8
    BNTUSD = 9
    BONDUSD = 10
    BTCGUSD = 11
    BTCUSD = 12
    COMPUSD = 13
    CRVUSD = 14
    CTXUSD = 15
    CUBEUSD = 16
    DAIUSD = 17
    DOGEUSD = 18
    ENJUSD = 19
    ETHGUSD = 20
    ETHUSD = 21
    FILUSD = 22
    FTMUSD = 23
    GRTUSD = 24
    INJUSD = 25
    KNCUSD = 26
    LINKUSD = 27
    LPTUSD = 28
    LRCUSD = 29
    LTCUSD = 30
    LUNAUSD = 31
    MANAUSD = 32
    MATICUSD = 33
    MCO2USD = 34
    MIRUSD = 35
    MKRUSD = 36
    OXTUSD = 37
    PAXGUSD = 38
    RENUSD = 39
    SANDUSD = 40
    SKLUSD = 41
    SLPUSD = 42
    SNXUSD = 43
    STORJUSD = 44
    SUSHIUSD = 45
    UMAUSD = 46
    UNIUSD = 47
    USTUSD = 48
    XTZUSD = 49
    YFIUSD = 50
    ZECUSD = 51
    ZRXUSD = 52

# see documentation for pair tick sizes
TICKSIZES = {
    # Pair.1INCHUSD.name: 1e-6,
    Pair.AAVEUSD.name: 1e-6,
    Pair.ALCXUSD.name: 1e-6,
    Pair.AMPUSD.name: 1e-6,
    Pair.ANKRUSD.name: 1e-6,
    Pair.AXSUSD.name: 1e-6,
    Pair.BALUSD.name: 1e-6,
    Pair.BATUSD.name: 1e-6,
    Pair.BCHUSD.name: 1e-6,
    Pair.BNTUSD.name: 1e-6,
    Pair.BONDUSD.name: 1e-6,
    Pair.BTCGUSD.name: 1e-8,
    Pair.BTCUSD.name: 1e-8,
    Pair.COMPUSD.name: 1e-6,
    Pair.CRVUSD.name: 1e-6,
    Pair.CTXUSD.name: 1e-6,
    Pair.CUBEUSD.name: 1e-6,
    Pair.DAIUSD.name: 1e-6,
    Pair.DOGEUSD.name: 1e-6,
    Pair.ENJUSD.name: 1e-6,
    Pair.ETHGUSD.name: 1e-6,
    Pair.ETHUSD.name: 1e-6,
    Pair.FILUSD.name: 1e-6,
    Pair.FTMUSD.name: 1e-6,
    Pair.GRTUSD.name: 1e-6,
    Pair.INJUSD.name: 1e-6,
    Pair.KNCUSD.name: 1e-6,
    Pair.LINKUSD.name: 1e-6,
    Pair.LPTUSD.name: 1e-6,
    Pair.LRCUSD.name: 1e-6,
    Pair.LTCUSD.name: 1e-5,
    Pair.LUNAUSD.name: 1e-6,
    Pair.MANAUSD.name: 1e-6,
    Pair.MATICUSD.name: 1e-6,
    Pair.MCO2USD.name: 1e-6,
    Pair.MIRUSD.name: 1e-6,
    Pair.MKRUSD.name: 1e-6,
    Pair.OXTUSD.name: 1e-6,
    Pair.PAXGUSD.name: 1e-8,
    Pair.RENUSD.name: 1e-6,
    Pair.SANDUSD.name: 1e-6,
    Pair.SKLUSD.name: 1e-6,
    Pair.SLPUSD.name: 1e-6,
    Pair.SNXUSD.name: 1e-6,
    Pair.STORJUSD.name: 1e-6,
    Pair.SUSHIUSD.name: 1e-6,
    Pair.UMAUSD.name: 1e-6,
    Pair.UNIUSD.name: 1e-6,
    Pair.USTUSD.name: 1e-6,
    Pair.XTZUSD.name: 1e-6,
    Pair.YFIUSD.name: 1e-6,
    Pair.ZECUSD.name: 1e-6,
    Pair.ZRXUSD.name: 1e-6,
}

MINSIZES = {
    # Pair.1INCHUSD.name: 1e-2,
    Pair.AAVEUSD.name: 1e-3,
    Pair.ALCXUSD.name: 1e-5,
    Pair.AMPUSD.name: 1e1,
    Pair.ANKRUSD.name: 1e-1,
    Pair.AXSUSD.name: 3e-3,
    Pair.BALUSD.name: 1e-2,
    Pair.BATUSD.name: 1e0,
    Pair.BCHUSD.name: 1e-3,
    Pair.BNTUSD.name: 1e-2,
    Pair.BONDUSD.name: 1e-3,
    Pair.BTCGUSD.name: 1e-5,
    Pair.BTCUSD.name: 1e-5,
    Pair.COMPUSD.name: 1e-3,
    Pair.CRVUSD.name: 1e-1,
    Pair.CTXUSD.name: 2e-3,
    Pair.CUBEUSD.name: 1e-2,
    Pair.DAIUSD.name: 1e-1,
    Pair.DOGEUSD.name: 1e-1,
    Pair.ENJUSD.name: 1e-1,
    Pair.ETHGUSD.name: 1e-3,
    Pair.ETHUSD.name: 1e-3,
    Pair.FILUSD.name: 1e-1,
    Pair.FTMUSD.name: 3e-2,
    Pair.GRTUSD.name: 1e-1,
    Pair.INJUSD.name: 1e-2,
    Pair.KNCUSD.name: 1e-1,
    Pair.LINKUSD.name: 1e-1,
    Pair.LPTUSD.name: 1e-3,
    Pair.LRCUSD.name: 1e-1,
    Pair.LTCUSD.name: 1e-2,
    Pair.LUNAUSD.name: 5e-3,
    Pair.MANAUSD.name: 1e0,
    Pair.MATICUSD.name: 1e-1,
    Pair.MCO2USD.name: 2e-2,
    Pair.MIRUSD.name: 1e-3,
    Pair.MKRUSD.name: 1e-3,
    Pair.OXTUSD.name: 1e0,
    Pair.PAXGUSD.name: 1e-4,
    Pair.RENUSD.name: 1e-2,
    Pair.SANDUSD.name: 1e-1,
    Pair.SKLUSD.name: 1e-1,
    Pair.SLPUSD.name: 5e-1,
    Pair.SNXUSD.name: 1e-2,
    Pair.STORJUSD.name: 1e-1,
    Pair.SUSHIUSD.name: 1e-2,
    Pair.UMAUSD.name: 1e-2,
    Pair.UNIUSD.name: 1e-2,
    Pair.USTUSD.name: 1e-1,
    Pair.XTZUSD.name: 2e-2,
    Pair.YFIUSD.name: 1e-5,
    Pair.ZECUSD.name: 1e-3,
    Pair.ZRXUSD.name: 1e-1,
}



#### ===========================================================================
####                                   util funcs
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



#### ===========================================================================
####                               api calling funcs
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
def buy(pair: Pair, amt_usd: float, options: list) -> dict:
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
Quoted market price      : {curr_price:,.2f} USD / {pair.name}
Allowed deviation        : +{round(price_with_dev - curr_price, 2):,.2f} USD / {pair.name}
Fee                      : {fee}
                           w/out fee\twith fee
Estimated total cost     : {est_cost:,.2f} USD\t{round(est_cost * (1 + fee), 2):,.2f} USD
Total Cost assm. max dev : {est_cost_max_dev:,.2f} USD\t{round(est_cost_max_dev * (1 + fee), 2):,.2f} USD
===
Limit buy {purchase_amt} {pair.name} @ {price_with_dev:,.2f} USD?"""):
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
        "limit_trades": 500,
    }
    enc_payload = encrypt(payload)
    sig = sign(enc_payload)
    headers = priv_api_headers(enc_payload, sig, KEY)
    return requests.post(url.full(), data=None, headers=headers).json()

def log_trades(trades: list[dict], path: str) -> bool:
    """Writes a line to file at path for each trade"""
    sep = "\t"
    # write header
    if not os.path.isfile(path):
        with open(path, "w+") as f:
            f.writelines([
                # transactionid orderid, timestamp, timestamp(ms), type(buy, sell), pair(BTCUSD, etc.)
                # price, amount, fee_currency (USD), fee_amount, cost_basis(amount * price + fee_amount)
                sep.join([
                    "tid", "orderid", "ts", "tsms",
                    "type", "pair", "price", "amount",
                    "fee_currency", "fee_amount", "cost_basis",
                    "\n"])
            ])

    with open(path, "a") as f:
        for trade in trades:
            cost_basis = Decimal(trade["fee_amount"]) + Decimal(trade["price"]) * Decimal(trade["amount"])
            f.writelines([
                sep.join([
                    str(trade["tid"])
                    ,trade["order_id"]
                    ,str(trade["timestamp"])
                    ,str(trade["timestampms"])
                    ,trade["type"]
                    ,trade["symbol"]
                    ,trade["price"]
                    ,trade["amount"]
                    ,trade["fee_currency"]
                    ,trade["fee_amount"]
                    ,str(cost_basis)
                    ,"\n"])
            ])

#### ===========================================================================
####                                      main

Bag = OrderedDict()
Bag[Pair.BTCUSD] = 1/1

# sum to 1
assert accumulate(Bag.values(), lambda a, b: a+b, initial=0)

if __name__ == "__main__":
    if SANDBOX:
        print("== running in Sandbox Mode ==")
    else:
        print("== NOT RUNNING IN SANDBOX MODE! ==")

    # TODO validate against min sizes
    for pair, amt in Bag.items():
        resp = buy(pair, USD_PER_DAY * amt, ["fill-or-kill"])
        if not resp:
            print ("==skipping")
            continue
        # assert resp, "No response"
        print("==order response")
        pp(resp)
        assert not resp["is_cancelled"], "Order was cancelled"

        trades = get_past_trades_after_timestamp(pair, resp["timestampms"])
        print("==trade stats")
        for trade in trades:
            pp(trade)
        log_trades(trades, OUTF)




# todo
#### ===========================================================================
####                                      TODO
"""
1. consider not doing make-or-kill MOK for lower fees.

2. It would be nice to place daily limit orders. For those that go unfilled, a
market order at EOD.

3. If this increases further in complexity, refactor and also consider rate
limits. Specifically the recommended 'don't exceed more than 1 request per
second`. Handle where we want faster and where it doesn't matter (e.g. logging -
do this after order completions. Or in between pairs. who cares if btc is bought
5 seconds before eth. But we do care about the delay between get_price and buy)

"""

# sandbox: https://exchange.sandbox.gemini.com/trade/BTCUSD


# the sandbox api returns 0 for various currency pairs, which breaks the script,
# so the get_price funcall should be mocked when in sandbox mode

# [{'pair': 'ZECBTC', 'price': '0', 'percentChange24h': '0.0000'}, {'pair':
# 'GUSDUSD', 'price': '1', 'percentChange24h': '0.0000'}, {'pair': 'AXSUSD',
# 'price': '0', 'percentChange24h': '0.0000'}, {'pair': 'LTCETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'SANDUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ETHSGD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'RENUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'AMPUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': '1INCHUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'UMAUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ETHUSD', 'price': '4604',
# 'percentChange24h': '-0.0254'}, {'pair': 'ETHBTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'COMPUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LINKBTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'FTMUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'OXTBTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ZRXUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LINKUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'DOGEETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ENJUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BATUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ETHGUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'CUBEUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ZECLTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BCHBTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BCHETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LTCBCH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BTCUSD', 'price': '64545.83',
# 'percentChange24h': '-0.0304'}, {'pair': 'BTCEUR', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'AAVEUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'USDCUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'DOGEUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'DOGEBTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'SLPUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BCHUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BALUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'FILUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'MCO2USD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'YFIUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ETHGBP', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'UNIUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'SNXUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'CRVUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BTCDAI', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ETHEUR', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LUNAUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ETHDAI', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LTCUSD', 'price': '254.91',
# 'percentChange24h': '-0.0071'}, {'pair': 'SKLUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BONDUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ZECBCH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BTCGUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LRCUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BTCSGD', 'price': '87725.02',
# 'percentChange24h': '-0.0250'}, {'pair': 'ZECETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'MKRUSD', 'price': '2412.93',
# 'percentChange24h': '0.0000'}, {'pair': 'DAIUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BNTUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'OXTETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'XTZUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'KNCUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ANKRUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ALCXUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'CTXUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'PAXGUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'STORJUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'LINKETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BTCGBP', 'price': '48099.4',
# 'percentChange24h': '-0.0190'}, {'pair': 'SUSHIUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BATBTC', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'BATETH', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'OXTUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'USTUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'MANAUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'MIRUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'GRTUSD', 'price': '0',
# 'percentChange24h': '0.0000'}, {'pair': 'ZECUSD', 'price': '153.23',
# 'percentChange24h': '-0.0350'}, {'pair': 'LTCBTC', 'price': '0',
# 'percentChange24h': '0.0000'}]

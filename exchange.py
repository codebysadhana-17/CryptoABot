import ccxt
import time
from datetime import datetime
import sys
import os
import urllib.request
import json
import concurrent.futures

import config
from config import SYMBOL
from database import get_api_key


# ============================================================
# ENSURE WINDOWS STDOUT HANDLES UTF-8
# ============================================================

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ============================================================
# PROXY CONFIGURATION
# ============================================================

proxy_url = (
    os.environ.get("EXCHANGE_PROXY")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("HTTP_PROXY")
)

if proxy_url:
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url


# ============================================================
# EXCHANGE OPTIONS
# ============================================================

REQUEST_TIMEOUT = getattr(
    config,
    "REQUEST_TIMEOUT_MS",
    20000,
)


# ============================================================
# BINANCE PUBLIC OPTIONS
# ============================================================

binance_opts = {
    "enableRateLimit": True,
    "timeout": REQUEST_TIMEOUT,
    "options": {
        "recvWindow": 60000,
        "adjustForTimeDifference": True,
        "defaultType": "spot",
    },
}


# ============================================================
# BYBIT PUBLIC OPTIONS
# ============================================================
#
# IMPORTANT:
# Bybit was successfully tested with:
#
# defaultType = spot
# recvWindow = 20000
# adjustForTimeDifference = False
# accountType = UNIFIED
#
# Do NOT enable automatic time synchronization for Bybit.
#
# ============================================================

bybit_opts = {
    "enableRateLimit": True,
    "timeout": REQUEST_TIMEOUT,
    "options": {
        "defaultType": "spot",
        "recvWindow": 20000,
        "adjustForTimeDifference": False,
        "accountType": "UNIFIED",
    },
}


# ============================================================
# APPLY PROXY TO PUBLIC OPTIONS
# ============================================================

if proxy_url:

    for opts in (
        binance_opts,
        bybit_opts,
    ):

        if "socks" in proxy_url.lower():

            opts["socksProxy"] = proxy_url

        else:

            opts["httpsProxy"] = proxy_url


# ============================================================
# PUBLIC EXCHANGE INSTANCES
# ============================================================

exchanges = {
    "Binance": ccxt.binance(binance_opts),
    "Bybit": ccxt.bybit(bybit_opts),
}


# ============================================================
# APPLY PROXY TO PUBLIC SESSIONS
# ============================================================

if proxy_url:

    for ex in exchanges.values():

        try:

            ex.session.proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }

        except Exception:
            pass


# ============================================================
# HELPER: GET API AUTHENTICATED EXCHANGE
# ============================================================

def get_authenticated_exchange(name):

    key_info = get_api_key(name)

    if (
        not key_info
        or not key_info.get("api_key")
        or not key_info.get("api_secret")
    ):

        return None, (
            f"No API keys configured for {name}."
        )

    exchange_class = getattr(
        ccxt,
        name.lower(),
        None,
    )

    if not exchange_class:

        return None, (
            f"Unsupported exchange: {name}"
        )

    try:

        # ====================================================
        # COMMON AUTH CONFIG
        # ====================================================

        config_opts = {
            "apiKey": key_info["api_key"],
            "secret": key_info["api_secret"],
            "enableRateLimit": True,
            "timeout": REQUEST_TIMEOUT,
            "options": {
                "defaultType": "spot",
                "recvWindow": 20000,
            },
        }


        # ====================================================
        # BINANCE
        # ====================================================

        if name.lower() == "binance":

            config_opts["options"].update({
                "defaultType": "spot",
                "adjustForTimeDifference": True,
            })


        # ====================================================
        # BYBIT
        # ====================================================
        #
        # IMPORTANT:
        # This configuration is based on the working
        # test_bybit_balance.py.
        #
        # DO NOT call:
        #     load_time_difference()
        #
        # DO NOT use:
        #     adjustForTimeDifference = True
        #
        # ====================================================

        elif name.lower() == "bybit":

            config_opts["options"].update({
                "defaultType": "spot",
                "adjustForTimeDifference": False,
                "recvWindow": 20000,
                "accountType": "UNIFIED",
            })


        # ====================================================
        # PROXY
        # ====================================================

        if proxy_url:

            if "socks" in proxy_url.lower():

                config_opts["socksProxy"] = proxy_url

            else:

                config_opts["httpsProxy"] = proxy_url


        # ====================================================
        # CREATE AUTHENTICATED INSTANCE
        # ====================================================

        ex_instance = exchange_class(
            config_opts
        )


        # ====================================================
        # APPLY PROXY TO SESSION
        # ====================================================

        if (
            proxy_url
            and hasattr(
                ex_instance,
                "session",
            )
        ):

            try:

                ex_instance.session.proxies = {
                    "http": proxy_url,
                    "https": proxy_url,
                }

            except Exception:
                pass


        # ====================================================
        # IMPORTANT
        # ====================================================
        #
        # DO NOT load_markets() here.
        #
        # Authentication / balance checking should not
        # require market loading.
        #
        # execute_live_real_trade() will load markets
        # only when actually preparing an order.
        #
        # ====================================================


        # ====================================================
        # BINANCE TIME SYNC ONLY
        # ====================================================

        if name.lower() == "binance":

            try:

                if hasattr(
                    ex_instance,
                    "load_time_difference",
                ):

                    ex_instance.load_time_difference()

            except Exception as e:

                print(
                    f"⚠️ Binance time sync warning: {e}",
                    flush=True,
                )


        # ====================================================
        # RETURN
        # ====================================================

        return ex_instance, None


    # ========================================================
    # AUTHENTICATION ERROR
    # ========================================================

    except ccxt.AuthenticationError as e:

        return None, (
            f"{name} authentication failed: "
            f"{str(e)}"
        )


    # ========================================================
    # PERMISSION ERROR
    # ========================================================

    except ccxt.PermissionDenied as e:

        return None, (
            f"{name} permission denied: "
            f"{str(e)}"
        )


    # ========================================================
    # NETWORK ERROR
    # ========================================================

    except ccxt.NetworkError as e:

        return None, (
            f"{name} network error: "
            f"{str(e)}"
        )


    # ========================================================
    # OTHER ERROR
    # ========================================================

    except Exception as e:

        return None, (
            f"Failed to initialize {name}: "
            f"{type(e).__name__}: {str(e)}"
        )


# ============================================================
# ACTUAL WALLET BALANCES
# ============================================================

def get_actual_wallet_balances():

    balances = {}

    exchange_names = [
        "Binance",
        "Bybit",
    ]

    for exchange_name in exchange_names:

        try:

            exchange, error = (
                get_authenticated_exchange(
                    exchange_name
                )
            )

            if error or exchange is None:

                balances[exchange_name] = {
                    "connected": False,
                    "usdt": 0.0,
                    "total_usdt": 0.0,
                    "btc": 0.0,
                    "total_btc": 0.0,
                    "error": (
                        error
                        or "Unable to connect."
                    ),
                }

                continue


            # =================================================
            # FETCH BALANCE
            # =================================================

            balance = exchange.fetch_balance()


            free = (
                balance.get("free", {})
                or {}
            )

            used = (
                balance.get("used", {})
                or {}
            )

            total = (
                balance.get("total", {})
                or {}
            )


            # =================================================
            # USDT
            # =================================================

            usdt_free = float(
                free.get("USDT", 0.0)
                or 0.0
            )

            usdt_used = float(
                used.get("USDT", 0.0)
                or 0.0
            )

            usdt_total = float(
                total.get("USDT", 0.0)
                or (
                    usdt_free
                    + usdt_used
                )
                or 0.0
            )


            # =================================================
            # BTC
            # =================================================

            btc_free = float(
                free.get("BTC", 0.0)
                or 0.0
            )

            btc_used = float(
                used.get("BTC", 0.0)
                or 0.0
            )

            btc_total = float(
                total.get("BTC", 0.0)
                or (
                    btc_free
                    + btc_used
                )
                or 0.0
            )


            # =================================================
            # SAVE BALANCE
            # =================================================

            balances[exchange_name] = {

                "connected": True,

                "usdt": round(
                    usdt_free,
                    8,
                ),

                "total_usdt": round(
                    usdt_total,
                    8,
                ),

                "btc": round(
                    btc_free,
                    8,
                ),

                "total_btc": round(
                    btc_total,
                    8,
                ),

                "error": None,
            }


            print(
                f"💰 {exchange_name} Wallet | "
                f"USDT: {usdt_total:.8f} | "
                f"BTC: {btc_total:.8f}",
                flush=True,
            )


        except ccxt.AuthenticationError:

            balances[exchange_name] = {
                "connected": False,
                "usdt": 0.0,
                "total_usdt": 0.0,
                "btc": 0.0,
                "total_btc": 0.0,
                "error": (
                    "Invalid API key or secret."
                ),
            }


        except ccxt.PermissionDenied:

            balances[exchange_name] = {
                "connected": False,
                "usdt": 0.0,
                "total_usdt": 0.0,
                "btc": 0.0,
                "total_btc": 0.0,
                "error": (
                    "API key does not have "
                    "balance permission."
                ),
            }


        except ccxt.NetworkError as e:

            balances[exchange_name] = {
                "connected": False,
                "usdt": 0.0,
                "total_usdt": 0.0,
                "btc": 0.0,
                "total_btc": 0.0,
                "error": (
                    f"Network error: {str(e)}"
                ),
            }


        except Exception as e:

            balances[exchange_name] = {
                "connected": False,
                "usdt": 0.0,
                "total_usdt": 0.0,
                "btc": 0.0,
                "total_btc": 0.0,
                "error": (
                    f"{type(e).__name__}: "
                    f"{str(e)}"
                ),
            }


    return balances


# ============================================================
# TEST API CONNECTION
# ============================================================

def test_exchange_connection(name):

    ex_instance, err = (
        get_authenticated_exchange(name)
    )

    if err:

        return {
            "success": False,
            "message": err,
        }


    try:

        balance = (
            ex_instance.fetch_balance()
        )

        free = (
            balance.get("free", {})
            or {}
        )

        total = (
            balance.get("total", {})
            or {}
        )


        # =====================================================
        # USDT
        # =====================================================

        usdt_free = float(
            free.get("USDT", 0.0)
            or 0.0
        )

        usdt_total = float(
            total.get("USDT", 0.0)
            or usdt_free
        )


        # =====================================================
        # BTC
        # =====================================================

        btc_free = float(
            free.get("BTC", 0.0)
            or 0.0
        )

        btc_total = float(
            total.get("BTC", 0.0)
            or btc_free
        )


        return {

            "success": True,

            "message": (
                f"Successfully connected "
                f"to {name}!"
            ),

            "usdt_balance": round(
                usdt_free,
                8,
            ),

            "usdt_total": round(
                usdt_total,
                8,
            ),

            "btc_balance": round(
                btc_free,
                8,
            ),

            "btc_total": round(
                btc_total,
                8,
            ),
        }


    except ccxt.AuthenticationError:

        return {
            "success": False,
            "message": (
                "Authentication Error: "
                "Invalid API Key or Secret "
                f"for {name}."
            ),
        }


    except ccxt.PermissionDenied:

        return {
            "success": False,
            "message": (
                "Permission Error: "
                "API Key lacks balance "
                f"permission on {name}."
            ),
        }


    except Exception as e:

        print(
            f"\n❌ {name} ERROR"
        )

        print(
            "Exception Type:",
            type(e).__name__,
        )

        print(
            "Exception:",
            repr(e),
        )

        return {
            "success": False,
            "message": (
                f"{type(e).__name__}: "
                f"{repr(e)}"
            ),
        }


# ============================================================
# DIRECT PRICE FETCH
# ============================================================

def get_direct_price(
    name,
    symbol=SYMBOL,
):

    clean_sym = symbol.replace(
        "/",
        "",
    )


    # ========================================================
    # SSL
    # ========================================================

    import ssl

    ctx = ssl.create_default_context()


    # ========================================================
    # BINANCE
    # ========================================================

    if name.lower() == "binance":

        urls = [

            (
                "https://data-api.binance.vision/"
                "api/v3/ticker/price?"
                f"symbol={clean_sym}"
            ),

            (
                "https://api.binance.com/"
                "api/v3/ticker/price?"
                f"symbol={clean_sym}"
            ),
        ]


        for url in urls:

            try:

                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent":
                            "Mozilla/5.0",
                    },
                )

                response = (
                    urllib.request.urlopen(
                        req,
                        context=ctx,
                        timeout=6,
                    )
                )

                res = json.loads(
                    response.read()
                )

                price = float(
                    res.get(
                        "price",
                        0,
                    )
                )

                if price > 0:

                    return price

            except Exception:

                continue


    # ========================================================
    # BYBIT
    # ========================================================

    elif name.lower() == "bybit":

        base_url = (
            "https://api.bybit.com"
        )

        try:

            url = (
                f"{base_url}/v5/market/tickers"
                f"?category=spot"
                f"&symbol={clean_sym}"
            )

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent":
                        "Mozilla/5.0",
                },
            )

            response = (
                urllib.request.urlopen(
                    req,
                    context=ctx,
                    timeout=6,
                )
            )

            res = json.loads(
                response.read()
            )

            tickers = (
                res.get(
                    "result",
                    {},
                )
                .get(
                    "list",
                    [],
                )
            )

            if tickers:

                price = float(
                    tickers[0].get(
                        "lastPrice",
                        0,
                    )
                )

                if price > 0:

                    return price

        except Exception:

            pass


    return None


# ============================================================
# FETCH SINGLE EXCHANGE PRICE
# ============================================================

def fetch_single_exchange_price(
    name_and_exchange,
):

    name, exchange = name_and_exchange


    fetched_price = (
        get_direct_price(
            name,
            SYMBOL,
        )
    )


    # ========================================================
    # CCXT FALLBACK
    # ========================================================

    if fetched_price is None:

        try:

            ticker = (
                exchange.fetch_ticker(
                    SYMBOL
                )
            )

            last_price = ticker.get(
                "last"
            )

            if (
                last_price is not None
                and float(last_price) > 0
            ):

                fetched_price = float(
                    last_price
                )

        except Exception:

            pass


    return (
        name,
        fetched_price,
    )


# ============================================================
# GET LIVE PRICES
# ============================================================

def get_live_prices():

    prices = {}


    with concurrent.futures.ThreadPoolExecutor(
        max_workers=2
    ) as executor:

        results = list(
            executor.map(
                fetch_single_exchange_price,
                exchanges.items(),
            )
        )


    for name, fetched_price in results:

        if (
            fetched_price is not None
            and fetched_price > 0
        ):

            prices[name] = float(
                fetched_price
            )

            print(
                f"{name}: "
                f"{fetched_price:.2f} USDT"
            )

        else:

            print(
                f"Price unavailable: "
                f"{name}"
            )


    return prices


# ============================================================
# HELPER: GET BASE / QUOTE CURRENCY
# ============================================================

def get_symbol_currencies(symbol):

    base, quote = symbol.split("/")

    return base, quote


# ============================================================
# HELPER: VALIDATE ORDER LIMITS
# ============================================================

def validate_order_limits(
    exchange,
    symbol,
    amount,
    price,
):

    try:

        market = exchange.market(
            symbol
        )

        limits = (
            market.get(
                "limits",
                {},
            )
            or {}
        )


        amount_limits = (
            limits.get(
                "amount",
                {},
            )
            or {}
        )

        cost_limits = (
            limits.get(
                "cost",
                {},
            )
            or {}
        )


        min_amount = (
            amount_limits.get("min")
        )

        max_amount = (
            amount_limits.get("max")
        )

        min_cost = (
            cost_limits.get("min")
        )

        max_cost = (
            cost_limits.get("max")
        )


        order_cost = (
            amount * price
        )


        # =====================================================
        # MIN AMOUNT
        # =====================================================

        if (
            min_amount is not None
            and amount < float(min_amount)
        ):

            return (
                False,
                (
                    f"Order amount "
                    f"{amount:.12f} is below "
                    f"exchange minimum "
                    f"{float(min_amount):.12f}"
                ),
            )


        # =====================================================
        # MAX AMOUNT
        # =====================================================

        if (
            max_amount is not None
            and amount > float(max_amount)
        ):

            return (
                False,
                (
                    f"Order amount "
                    f"{amount:.12f} exceeds "
                    f"exchange maximum "
                    f"{float(max_amount):.12f}"
                ),
            )


        # =====================================================
        # MIN COST
        # =====================================================

        if (
            min_cost is not None
            and order_cost < float(min_cost)
        ):

            return (
                False,
                (
                    f"Order value "
                    f"${order_cost:.8f} is below "
                    f"exchange minimum "
                    f"${float(min_cost):.8f}"
                ),
            )


        # =====================================================
        # MAX COST
        # =====================================================

        if (
            max_cost is not None
            and order_cost > float(max_cost)
        ):

            return (
                False,
                (
                    f"Order value "
                    f"${order_cost:.8f} exceeds "
                    f"exchange maximum "
                    f"${float(max_cost):.8f}"
                ),
            )


        return True, "OK"


    except Exception as e:

        return (
            False,
            (
                "Unable to validate "
                f"market limits: "
                f"{type(e).__name__}: {str(e)}"
            ),
        )


# ============================================================
# HELPER: SAFE FLOAT
# ============================================================

def safe_float(
    value,
    default=0.0,
):

    try:

        if value is None:

            return default

        return float(value)

    except Exception:

        return default


# ============================================================
# HELPER: GET ACTUAL FILLED AMOUNT
# ============================================================

def get_filled_amount(
    exchange,
    symbol,
    order,
    fallback_amount,
):

    filled = safe_float(
        order.get("filled"),
        0.0,
    )

    if filled > 0:

        return filled


    # ========================================================
    # FETCH ORDER STATUS
    # ========================================================

    order_id = order.get("id")

    if order_id:

        try:

            time.sleep(1)

            updated = (
                exchange.fetch_order(
                    order_id,
                    symbol,
                )
            )

            filled = safe_float(
                updated.get("filled"),
                0.0,
            )

            if filled > 0:

                return filled

        except Exception:

            pass


    return fallback_amount


# ============================================================
# HELPER: GET ACTUAL FEE FROM ORDER
# ============================================================

def get_order_fee(
    order,
    fallback_cost,
    fee_pct,
):

    # ========================================================
    # CCXT UNIFIED FEE
    # ========================================================

    fee = order.get("fee")

    if isinstance(
        fee,
        dict,
    ):

        cost = safe_float(
            fee.get("cost"),
            0.0,
        )

        if cost > 0:

            return cost


    # ========================================================
    # CCXT FEES LIST
    # ========================================================

    fees = order.get("fees")

    if isinstance(
        fees,
        list,
    ):

        total = 0.0

        for item in fees:

            if isinstance(
                item,
                dict,
            ):

                total += safe_float(
                    item.get("cost"),
                    0.0,
                )

        if total > 0:

            return total


    # ========================================================
    # FALLBACK
    # ========================================================

    return (
        fallback_cost * fee_pct
    )


# ============================================================
# HELPER: MARKET BUY
# ============================================================

def submit_market_buy(
    exchange,
    symbol,
    amount,
    reference_price,
):

    try:

        requires_price = (
            exchange.options.get(
                "createMarketBuyOrderRequiresPrice",
                False,
            )
        )


        if requires_price:

            return exchange.create_order(
                symbol,
                "market",
                "buy",
                amount,
                reference_price,
            )


        return (
            exchange.create_market_buy_order(
                symbol,
                amount,
            )
        )


    except ccxt.InvalidOrder:

        raise


# ============================================================
# EXECUTE LIVE REAL TRADE
# ============================================================

def execute_live_real_trade(
    buy_exchange_name,
    sell_exchange_name,
    buy_price,
    sell_price,
    trade_amount=None,
):

    print(
        "\n=================================================="
    )

    print(
        "LIVE TRADE VALIDATION / EXECUTION"
    )

    print(
        "=================================================="
    )


    # ========================================================
    # 0. BASIC VALIDATION
    # ========================================================

    if (
        buy_exchange_name
        == sell_exchange_name
    ):

        return {
            "success": False,
            "message": (
                "BUY and SELL exchanges "
                "must be different."
            ),
        }


    supported_exchanges = getattr(
        config,
        "SUPPORTED_EXCHANGES",
        [
            "Binance",
            "Bybit",
        ],
    )


    if (
        buy_exchange_name
        not in supported_exchanges
    ):

        return {
            "success": False,
            "message": (
                f"Unsupported BUY exchange: "
                f"{buy_exchange_name}"
            ),
        }


    if (
        sell_exchange_name
        not in supported_exchanges
    ):

        return {
            "success": False,
            "message": (
                f"Unsupported SELL exchange: "
                f"{sell_exchange_name}"
            ),
        }


    buy_price = safe_float(
        buy_price,
        0.0,
    )

    sell_price = safe_float(
        sell_price,
        0.0,
    )


    if (
        buy_price <= 0
        or sell_price <= 0
    ):

        return {
            "success": False,
            "message": (
                "Invalid BUY/SELL price."
            ),
        }


    # ========================================================
    # 1. LIVE TRADING ARM CHECK
    # ========================================================

    live_armed = bool(
        getattr(
            config,
            "LIVE_TRADING_ARMED",
            False,
        )
    )

    auto_trade = bool(
        getattr(
            config,
            "AUTO_TRADE_ENABLED",
            False,
        )
    )


    print(
        f"LIVE_TRADING_ARMED = "
        f"{live_armed}"
    )

    print(
        f"AUTO_TRADE_ENABLED = "
        f"{auto_trade}"
    )


    # ========================================================
    # SAFETY
    # ========================================================

    if not live_armed:

        return {
            "success": False,
            "armed": False,
            "message": (
                "REAL ORDER BLOCKED. "
                "LIVE_TRADING_ARMED is False. "
                "No order was submitted."
            ),
        }


    # ========================================================
    # 2. LOAD BUY EXCHANGE
    # ========================================================

    buy_ex, buy_err = (
        get_authenticated_exchange(
            buy_exchange_name
        )
    )


    if buy_err:

        return {
            "success": False,
            "message": (
                f"BUY exchange error: "
                f"{buy_err}"
            ),
        }


    # ========================================================
    # 3. LOAD SELL EXCHANGE
    # ========================================================

    sell_ex, sell_err = (
        get_authenticated_exchange(
            sell_exchange_name
        )
    )


    if sell_err:

        return {
            "success": False,
            "message": (
                f"SELL exchange error: "
                f"{sell_err}"
            ),
        }


    # ========================================================
    # 4. VERIFY / LOAD MARKETS
    # ========================================================

    try:

        # ----------------------------------------------------
        # BUY EXCHANGE MARKETS
        # ----------------------------------------------------

        if not getattr(
            buy_ex,
            "markets",
            None,
        ):

            print(
                f"Loading markets for "
                f"{buy_exchange_name}...",
                flush=True,
            )

            buy_ex.load_markets()


        # ----------------------------------------------------
        # SELL EXCHANGE MARKETS
        # ----------------------------------------------------

        if not getattr(
            sell_ex,
            "markets",
            None,
        ):

            print(
                f"Loading markets for "
                f"{sell_exchange_name}...",
                flush=True,
            )

            sell_ex.load_markets()


        # ----------------------------------------------------
        # CHECK BUY SYMBOL
        # ----------------------------------------------------

        if SYMBOL not in buy_ex.markets:

            return {
                "success": False,
                "message": (
                    f"{SYMBOL} is not available "
                    f"on {buy_exchange_name}."
                ),
            }


        # ----------------------------------------------------
        # CHECK SELL SYMBOL
        # ----------------------------------------------------

        if SYMBOL not in sell_ex.markets:

            return {
                "success": False,
                "message": (
                    f"{SYMBOL} is not available "
                    f"on {sell_exchange_name}."
                ),
            }


    except ccxt.NetworkError as e:

        return {
            "success": False,
            "message": (
                f"Unable to load markets: "
                f"{type(e).__name__}: {str(e)}"
            ),
        }


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"Market verification failed: "
                f"{type(e).__name__}: {str(e)}"
            ),
        }


    # ========================================================
    # 5. CURRENCIES
    # ========================================================

    try:

        (
            base_currency,
            quote_currency,
        ) = get_symbol_currencies(
            SYMBOL
        )

    except Exception as e:

        return {
            "success": False,
            "message": (
                f"Invalid symbol {SYMBOL}: "
                f"{str(e)}"
            ),
        }


    # ========================================================
    # 6. FETCH REAL BALANCES
    # ========================================================

    try:

        buy_balance = (
            buy_ex.fetch_balance()
        )

        sell_balance = (
            sell_ex.fetch_balance()
        )


        buy_free = (
            buy_balance.get(
                "free",
                {},
            )
            or {}
        )

        sell_free = (
            sell_balance.get(
                "free",
                {},
            )
            or {}
        )


        free_usdt = safe_float(
            buy_free.get(
                quote_currency,
                0.0,
            ),
            0.0,
        )


        free_btc = safe_float(
            sell_free.get(
                base_currency,
                0.0,
            ),
            0.0,
        )


    except ccxt.AuthenticationError as e:

        return {
            "success": False,
            "message": (
                f"Authentication failed: "
                f"{str(e)}"
            ),
        }


    except ccxt.PermissionDenied as e:

        return {
            "success": False,
            "message": (
                f"Permission denied: "
                f"{str(e)}"
            ),
        }


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"Unable to verify balances: "
                f"{type(e).__name__}: "
                f"{str(e)}"
            ),
        }


    print(
        f"BUY EXCHANGE "
        f"{buy_exchange_name}: "
        f"{free_usdt:.8f} "
        f"{quote_currency}"
    )


    print(
        f"SELL EXCHANGE "
        f"{sell_exchange_name}: "
        f"{free_btc:.8f} "
        f"{base_currency}"
    )


    # ========================================================
    # 7. MINIMUM TRADE CONFIG
    # ========================================================

    min_trade = float(
        getattr(
            config,
            "MIN_TRADE_USDT",
            5.0,
        )
    )


    max_trade = float(
        getattr(
            config,
            "MAX_TRADE_AMOUNT_USDT",
            5.0,
        )
    )


    default_trade = float(
        getattr(
            config,
            "DEFAULT_TRADE_AMOUNT",
            5.0,
        )
    )


    if trade_amount is None:

        trade_amount = default_trade


    trade_amount = safe_float(
        trade_amount,
        default_trade,
    )


    # Never exceed configured maximum.

    trade_amount = min(
        trade_amount,
        max_trade,
    )


    # ========================================================
    # 8. BUY USDT BALANCE CHECK
    # ========================================================

    if free_usdt < min_trade:

        return {
            "success": False,
            "message": (
                f"Insufficient "
                f"{quote_currency} "
                f"on {buy_exchange_name}. "
                f"Minimum required: "
                f"${min_trade:.4f}. "
                f"Available: "
                f"${free_usdt:.8f}."
            ),
        }


    # ========================================================
    # 9. DYNAMIC BALANCE TRADING
    # ========================================================

    dynamic_balance = bool(
        getattr(
            config,
            "DYNAMIC_BALANCE_TRADING",
            True,
        )
    )


    if dynamic_balance:

        max_usage = float(
            getattr(
                config,
                "MAX_BALANCE_USAGE",
                0.90,
            )
        )


        max_from_balance = (
            free_usdt
            * max_usage
        )


        trade_amount = min(
            trade_amount,
            max_from_balance,
        )


    # Never exceed free balance.

    trade_amount = min(
        trade_amount,
        free_usdt,
    )


    # ========================================================
    # 10. ROUND TRADE AMOUNT
    # ========================================================

    try:

        trade_amount = float(
            buy_ex.cost_to_precision(
                SYMBOL,
                trade_amount,
            )
        )

    except Exception:

        trade_amount = round(
            trade_amount,
            8,
        )


    if trade_amount < min_trade:

        return {
            "success": False,
            "message": (
                f"Final trade amount "
                f"${trade_amount:.8f} is below "
                f"configured minimum "
                f"${min_trade:.8f}. "
                f"Available balance: "
                f"${free_usdt:.8f}."
            ),
        }


    print(
        f"TRADE AMOUNT: "
        f"${trade_amount:.8f} "
        f"{quote_currency}"
    )


    # ========================================================
    # 11. CALCULATE BASE QUANTITY
    # ========================================================

    raw_amount = (
        trade_amount
        / buy_price
    )


    try:

        btc_amount_str = (
            buy_ex.amount_to_precision(
                SYMBOL,
                raw_amount,
            )
        )


        btc_amount = float(
            btc_amount_str
        )


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"Unable to calculate "
                f"order quantity: "
                f"{type(e).__name__}: "
                f"{str(e)}"
            ),
        }


    if btc_amount <= 0:

        return {
            "success": False,
            "message": (
                "Calculated BTC quantity "
                "is zero."
            ),
        }


    print(
        f"CALCULATED BTC: "
        f"{btc_amount:.12f}"
    )


    # ========================================================
    # 12. SELL-SIDE BTC BALANCE CHECK
    # ========================================================
    #
    # Cross-exchange arbitrage does NOT automatically
    # transfer BTC between exchanges.
    #
    # BTC must already exist on SELL exchange.
    #
    # ========================================================

    if free_btc <= 0:

        return {
            "success": False,
            "message": (
                f"TRADE BLOCKED. "
                f"{sell_exchange_name} has "
                f"0 available "
                f"{base_currency}. "
                f"BTC must already be present "
                f"on the SELL exchange."
            ),
        }


    if free_btc < btc_amount:

        return {
            "success": False,
            "message": (
                f"TRADE BLOCKED. "
                f"SELL exchange has only "
                f"{free_btc:.12f} BTC, "
                f"but approximately "
                f"{btc_amount:.12f} BTC "
                f"is required."
            ),
        }


    # ========================================================
    # 13. SELL AMOUNT PRECISION
    # ========================================================

    try:

        sell_btc_amount = float(
            sell_ex.amount_to_precision(
                SYMBOL,
                btc_amount,
            )
        )


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"SELL quantity precision "
                f"failed: {str(e)}"
            ),
        }


    if sell_btc_amount <= 0:

        return {
            "success": False,
            "message": (
                "SELL BTC quantity became "
                "zero after exchange "
                "precision."
            ),
        }


    if free_btc < sell_btc_amount:

        return {
            "success": False,
            "message": (
                f"Insufficient BTC on "
                f"{sell_exchange_name} after "
                f"precision adjustment."
            ),
        }


    # ========================================================
    # 14. ORDER LIMIT CHECK - BUY
    # ========================================================

    buy_valid, buy_message = (
        validate_order_limits(
            buy_ex,
            SYMBOL,
            btc_amount,
            buy_price,
        )
    )


    if not buy_valid:

        return {
            "success": False,
            "message": (
                f"BUY BLOCKED: "
                f"{buy_message}"
            ),
        }


    # ========================================================
    # 15. ORDER LIMIT CHECK - SELL
    # ========================================================

    sell_valid, sell_message = (
        validate_order_limits(
            sell_ex,
            SYMBOL,
            sell_btc_amount,
            sell_price,
        )
    )


    if not sell_valid:

        return {
            "success": False,
            "message": (
                f"SELL BLOCKED: "
                f"{sell_message}"
            ),
        }


    # ========================================================
    # 16. PROFIT CALCULATION
    # ========================================================

    fee_pct = float(
        getattr(
            config,
            "ESTIMATED_FEE_PERCENT",
            getattr(
                config,
                "MAKER_TAKER_FEE_PCT",
                0.10,
            ),
        )
    ) / 100.0


    slippage_pct = float(
        getattr(
            config,
            "SLIPPAGE_PCT",
            0.0,
        )
    ) / 100.0


    # Conservative estimate.

    estimated_buy_price = (
        buy_price
        * (1.0 + slippage_pct)
    )


    estimated_sell_price = (
        sell_price
        * (1.0 - slippage_pct)
    )


    estimated_buy_cost = (
        btc_amount
        * estimated_buy_price
    )


    estimated_sell_value = (
        sell_btc_amount
        * estimated_sell_price
    )


    estimated_buy_fee = (
        estimated_buy_cost
        * fee_pct
    )


    estimated_sell_fee = (
        estimated_sell_value
        * fee_pct
    )


    estimated_net_profit = (
        estimated_sell_value
        - estimated_buy_cost
        - estimated_buy_fee
        - estimated_sell_fee
    )


    estimated_profit_percent = 0.0


    if estimated_buy_cost > 0:

        estimated_profit_percent = (
            estimated_net_profit
            / estimated_buy_cost
        ) * 100.0


    min_profit = float(
        getattr(
            config,
            "MIN_PROFIT",
            0.05,
        )
    )


    min_profit_percent = float(
        getattr(
            config,
            "MIN_PROFIT_PERCENT",
            0.20,
        )
    )


    print(
        f"Estimated Net Profit: "
        f"${estimated_net_profit:.8f}"
    )


    print(
        f"Estimated Profit %: "
        f"{estimated_profit_percent:.4f}%"
    )


    # ========================================================
    # 17. PROFIT CHECK
    # ========================================================

    if estimated_net_profit < min_profit:

        return {
            "success": False,
            "message": (
                f"TRADE BLOCKED. "
                f"Estimated net profit "
                f"${estimated_net_profit:.8f} "
                f"is below minimum "
                f"${min_profit:.8f}."
            ),
        }


    if (
        estimated_profit_percent
        < min_profit_percent
    ):

        return {
            "success": False,
            "message": (
                f"TRADE BLOCKED. "
                f"Estimated profit "
                f"{estimated_profit_percent:.4f}% "
                f"is below minimum "
                f"{min_profit_percent:.4f}%."
            ),
        }


    # ========================================================
    # 18. FINAL PRE-ORDER SAFETY
    # ========================================================

    print(
        "\n⚠️ FINAL LIVE ORDER CHECK"
    )

    print(
        f"BUY  : {buy_exchange_name}"
    )

    print(
        f"SELL : {sell_exchange_name}"
    )

    print(
        f"SYMBOL: {SYMBOL}"
    )

    print(
        f"BUY PRICE: {buy_price:.8f}"
    )

    print(
        f"SELL PRICE: {sell_price:.8f}"
    )

    print(
        f"TRADE VALUE: "
        f"${trade_amount:.8f}"
    )

    print(
        f"BTC: {btc_amount:.12f}"
    )

    print(
        f"EST. PROFIT: "
        f"${estimated_net_profit:.8f}"
    )


    # ========================================================
    # 19. LIVE BUY
    # ========================================================

    buy_order = None
    buy_order_id = None


    try:

        print(
            "\n🚨 SUBMITTING LIVE BUY..."
        )


        buy_order = submit_market_buy(
            buy_ex,
            SYMBOL,
            btc_amount,
            buy_price,
        )


        buy_order_id = (
            buy_order.get("id")
            or
            f"LIVE-BUY-{int(time.time())}"
        )


        print(
            "✅ BUY ORDER SUBMITTED"
        )

        print(
            f"BUY ORDER ID: "
            f"{buy_order_id}"
        )


    except ccxt.InsufficientFunds as e:

        return {
            "success": False,
            "message": (
                f"BUY FAILED: "
                f"Insufficient funds on "
                f"{buy_exchange_name}: "
                f"{str(e)}"
            ),
        }


    except ccxt.InvalidOrder as e:

        return {
            "success": False,
            "message": (
                f"BUY FAILED: Invalid order "
                f"on {buy_exchange_name}: "
                f"{str(e)}"
            ),
        }


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"BUY FAILED on "
                f"{buy_exchange_name}: "
                f"{type(e).__name__}: "
                f"{str(e)}"
            ),
        }


    # ========================================================
    # 20. GET ACTUAL BUY FILL
    # ========================================================

    actual_bought_btc = (
        get_filled_amount(
            buy_ex,
            SYMBOL,
            buy_order,
            btc_amount,
        )
    )


    if actual_bought_btc <= 0:

        return {
            "success": False,
            "message": (
                f"BUY order "
                f"{buy_order_id} "
                f"was submitted, but filled "
                f"quantity could not be "
                f"confirmed. "
                f"DO NOT submit another BUY "
                f"manually without checking "
                f"the exchange order."
            ),
            "buy_order_id":
                buy_order_id,
        }


    # ========================================================
    # 21. SELL ACTUAL FILLED QUANTITY
    # ========================================================

    try:

        sell_amount_str = (
            sell_ex.amount_to_precision(
                SYMBOL,
                actual_bought_btc,
            )
        )


        actual_sell_amount = float(
            sell_amount_str
        )


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"BUY succeeded "
                f"(ID: {buy_order_id}) but "
                f"SELL quantity formatting "
                f"failed: {str(e)}. "
                f"Manual position review "
                f"required."
            ),
            "buy_order_id":
                buy_order_id,
            "btc_amount":
                actual_bought_btc,
        }


    if actual_sell_amount <= 0:

        return {
            "success": False,
            "message": (
                f"BUY succeeded "
                f"(ID: {buy_order_id}) but "
                f"SELL quantity became zero. "
                f"Manual position review "
                f"required."
            ),
            "buy_order_id":
                buy_order_id,
            "btc_amount":
                actual_bought_btc,
        }


    # ========================================================
    # RE-CHECK SELL WALLET
    # ========================================================

    try:

        latest_sell_balance = (
            sell_ex.fetch_balance()
        )


        latest_sell_free = (
            latest_sell_balance
            .get(
                "free",
                {},
            )
            or {}
        )


        latest_free_btc = safe_float(
            latest_sell_free.get(
                base_currency,
                0.0,
            ),
            0.0,
        )


    except Exception as e:

        return {
            "success": False,
            "message": (
                f"BUY succeeded "
                f"(ID: {buy_order_id}) but "
                f"SELL balance re-check "
                f"failed: {str(e)}. "
                f"SELL was NOT submitted."
            ),
            "buy_order_id":
                buy_order_id,
            "btc_amount":
                actual_bought_btc,
        }


    if (
        latest_free_btc
        < actual_sell_amount
    ):

        return {
            "success": False,
            "message": (
                f"BUY succeeded "
                f"(ID: {buy_order_id}) but "
                f"SELL exchange has "
                f"insufficient BTC. "
                f"Required: "
                f"{actual_sell_amount:.12f}, "
                f"Available: "
                f"{latest_free_btc:.12f}. "
                f"SELL was NOT submitted."
            ),
            "buy_order_id":
                buy_order_id,
            "btc_amount":
                actual_bought_btc,
        }


    # ========================================================
    # 22. LIVE SELL
    # ========================================================

    sell_order = None
    sell_order_id = None


    try:

        print(
            "\n🚨 SUBMITTING LIVE SELL..."
        )


        print(
            f"SELL QUANTITY: "
            f"{actual_sell_amount:.12f} BTC"
        )


        sell_order = (
            sell_ex.create_market_sell_order(
                SYMBOL,
                actual_sell_amount,
            )
        )


        sell_order_id = (
            sell_order.get("id")
            or
            f"LIVE-SELL-{int(time.time())}"
        )


        print(
            "✅ SELL ORDER SUBMITTED"
        )


        print(
            f"SELL ORDER ID: "
            f"{sell_order_id}"
        )


    except Exception as e:

        return {
            "success": False,
            "message": (
                "🚨 CRITICAL: BUY ORDER "
                f"SUCCEEDED on "
                f"{buy_exchange_name} "
                f"(ID: {buy_order_id}), "
                "but SELL FAILED on "
                f"{sell_exchange_name}. "
                f"Error: "
                f"{type(e).__name__}: "
                f"{str(e)}. "
                "Manual position review "
                "required."
            ),
            "buy_order_id":
                buy_order_id,
            "btc_amount":
                actual_bought_btc,
        }


    # ========================================================
    # 23. ACTUAL ORDER VALUES
    # ========================================================

    effective_buy_price = safe_float(
        buy_order.get("average"),
        0.0,
    )


    if effective_buy_price <= 0:

        effective_buy_price = safe_float(
            buy_order.get("price"),
            buy_price,
        )


    effective_sell_price = safe_float(
        sell_order.get("average"),
        0.0,
    )


    if effective_sell_price <= 0:

        effective_sell_price = safe_float(
            sell_order.get("price"),
            sell_price,
        )


    actual_buy_cost = safe_float(
        buy_order.get("cost"),
        0.0,
    )


    if actual_buy_cost <= 0:

        actual_buy_cost = (
            actual_bought_btc
            * effective_buy_price
        )


    actual_sell_value = safe_float(
        sell_order.get("cost"),
        0.0,
    )


    if actual_sell_value <= 0:

        actual_sell_value = (
            actual_sell_amount
            * effective_sell_price
        )


    # ========================================================
    # 24. ACTUAL FEES
    # ========================================================

    buy_fee = get_order_fee(
        buy_order,
        actual_buy_cost,
        fee_pct,
    )


    sell_fee = get_order_fee(
        sell_order,
        actual_sell_value,
        fee_pct,
    )


    total_fees = (
        buy_fee
        + sell_fee
    )


    # ========================================================
    # 25. NET PROFIT
    # ========================================================

    net_profit = (
        actual_sell_value
        - actual_buy_cost
        - total_fees
    )


    actual_profit_percent = 0.0


    if actual_buy_cost > 0:

        actual_profit_percent = (
            net_profit
            / actual_buy_cost
        ) * 100.0


    print(
        "\n=================================================="
    )

    print(
        "✅ LIVE TRADE COMPLETED"
    )

    print(
        f"BUY  : {buy_exchange_name}"
    )

    print(
        f"SELL : {sell_exchange_name}"
    )

    print(
        f"BUY COST: "
        f"${actual_buy_cost:.8f}"
    )

    print(
        f"SELL VALUE: "
        f"${actual_sell_value:.8f}"
    )

    print(
        f"FEES: "
        f"${total_fees:.8f}"
    )

    print(
        f"NET PROFIT: "
        f"${net_profit:.8f}"
    )

    print(
        f"NET PROFIT %: "
        f"{actual_profit_percent:.6f}%"
    )

    print(
        "=================================================="
    )


    # ========================================================
    # 26. SUCCESS RESPONSE
    # ========================================================

    return {

        "success": True,

        "armed": True,

        "message": (
            "LIVE TRADE EXECUTED "
            "SUCCESSFULLY. "
            f"BUY: {buy_exchange_name} | "
            f"SELL: {sell_exchange_name}"
        ),

        "trade": {

            "buy":
                buy_exchange_name,

            "sell":
                sell_exchange_name,

            "buy_exchange":
                buy_exchange_name,

            "sell_exchange":
                sell_exchange_name,

            "symbol":
                SYMBOL,

            "buy_price":
                float(buy_price),

            "sell_price":
                float(sell_price),

            "effective_buy_price":
                effective_buy_price,

            "effective_sell_price":
                effective_sell_price,

            "actual_buy_cost":
                round(
                    actual_buy_cost,
                    8,
                ),

            "actual_sell_value":
                round(
                    actual_sell_value,
                    8,
                ),

            "buy_fee":
                round(
                    buy_fee,
                    8,
                ),

            "sell_fee":
                round(
                    sell_fee,
                    8,
                ),

            "fees":
                round(
                    total_fees,
                    8,
                ),

            "profit":
                round(
                    net_profit,
                    8,
                ),

            "profit_percent":
                round(
                    actual_profit_percent,
                    8,
                ),

            "estimated_profit":
                round(
                    estimated_net_profit,
                    8,
                ),

            "estimated_profit_percent":
                round(
                    estimated_profit_percent,
                    8,
                ),

            "buy_order_id":
                buy_order_id,

            "sell_order_id":
                sell_order_id,

            "btc_amount":
                actual_bought_btc,

            "sell_btc_amount":
                actual_sell_amount,

            "trade_amount":
                trade_amount,

            "created_at":
                datetime.now()
                .astimezone()
                .isoformat(),

            "mode":
                "LIVE",
        },
    }


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    print(
        "\n=============================================="
    )

    print(
        "LIVE EXCHANGE PRICES"
    )

    print(
        "==============================================\n"
    )


    # ========================================================
    # LIVE PRICES
    # ========================================================

    prices = get_live_prices()


    if not prices:

        print(
            "No exchange prices available."
        )


    # ========================================================
    # API CONNECTION TEST
    # ========================================================

    print(
        "\n=============================================="
    )

    print(
        "===== API CONNECTION TEST ====="
    )

    print(
        "=============================================="
    )


    print(
        "\nBinance:"
    )


    print(
        test_exchange_connection(
            "Binance"
        )
    )


    print(
        "\nBybit:"
    )


    print(
        test_exchange_connection(
            "Bybit"
        )
    )


    # ========================================================
    # ACTUAL WALLET BALANCES
    # ========================================================

    print(
        "\n=============================================="
    )

    print(
        "===== ACTUAL WALLET BALANCES ====="
    )

    print(
        "=============================================="
    )


    wallet_balances = (
        get_actual_wallet_balances()
    )


    for (
        exchange_name,
        data,
    ) in wallet_balances.items():

        print(
            f"{exchange_name}: "
            f"{data}"
        )


    # ========================================================
    # SAFETY STATUS
    # ========================================================

    print(
        "\n=============================================="
    )

    print(
        "===== LIVE TRADING SAFETY STATUS ====="
    )

    print(
        "=============================================="
    )


    print(
    f"LIVE_TRADING_ARMED: "
    f"{getattr(config, 'LIVE_TRADING_ARMED', False)}"
)

print(
    f"AUTO_TRADE_ENABLED: "
    f"{getattr(config, 'AUTO_TRADE_ENABLED', False)}"
)

print("\nNo trade is executed by this test.")
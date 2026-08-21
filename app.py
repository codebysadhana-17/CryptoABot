import os
import sys
import threading
import time

from flask import Flask, jsonify, render_template, request

import config
from arbitrage import analyze_market, execute_paper_trade
from database import (
    create_database,
    get_all_trades,
    get_latest_trade,
    get_portfolio,
    get_total_profit,
    get_total_trades,
    reset_portfolio,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = Flask(__name__)
create_database()

last_background_trade_result = None


def start_background_auto_trader():
    def auto_trader_loop():
        global last_background_trade_result

        print("Background Auto-Trader Thread Started...", flush=True)

        while True:
            try:
                if getattr(config, "AUTO_TRADE_ENABLED", False):
                    data = analyze_market()

                    if (
                        data
                        and data.get("net_profit", 0)
                        >= getattr(config, "MIN_PROFIT", 0.01)
                    ):
                        result = execute_paper_trade(data)

                        if result and result.get("success"):
                            last_background_trade_result = result
                            trade = result.get("trade", {})

                            print(
                                "Background trade executed: "
                                f"{trade.get('buy_exchange')} -> "
                                f"{trade.get('sell_exchange')} | "
                                f"Profit: +${trade.get('profit', 0):.2f} USDT",
                                flush=True,
                            )

            except Exception as error:
                print(f"Background Auto-Trader error: {error}", flush=True)

            time.sleep(getattr(config, "REFRESH_INTERVAL", 3))

    threading.Thread(target=auto_trader_loop, daemon=True).start()


start_background_auto_trader()


@app.route("/")
@app.route("/prices")
@app.route("/arbitrage")
@app.route("/trades")
@app.route("/settings")
def home():
    return render_template("index.html")


# =====================================================
# PAPER PORTFOLIO API
# Kept for paper-trade history only.
# =====================================================

@app.route("/api/portfolio", methods=["GET"])
def get_portfolio_api():
    portfolio = get_portfolio()

    return jsonify({
        "success": True,
        "portfolio": portfolio,
        "total_profit": get_total_profit(),
        "total_trades": get_total_trades(),
    })


# =====================================================
# REAL EXCHANGE WALLET BALANCES
# =====================================================

def get_real_wallet_balances():
    """
    Reads real balances only. It never executes trades and
    never exposes exchange API keys to the browser.
    """
    try:
        from exchange import get_actual_wallet_balances
        return get_actual_wallet_balances() or {}
    except Exception as error:
        print(f"Live wallet balance error: {error}", flush=True)
        return {}


@app.route("/api/live-balances", methods=["GET"])
def get_live_balances_api():
    balances = get_real_wallet_balances()

    if not balances:
        return jsonify({
            "success": False,
            "message": "Unable to fetch live exchange balances.",
            "balances": {},
        }), 503

    return jsonify({
        "success": True,
        "balances": balances,
    })


@app.route("/api/live-balance-summary", methods=["GET"])
def get_live_balance_summary():
    balances = get_real_wallet_balances()

    if not balances:
        return jsonify({
            "success": False,
            "message": "No live balances available.",
            "total_usdt": 0.0,
            "balances": {},
        }), 503

    total_usdt = 0.0

    for exchange_data in balances.values():
        if not isinstance(exchange_data, dict):
            continue

        try:
            total_usdt += float(exchange_data.get("total_usdt", 0) or 0)
        except (TypeError, ValueError):
            pass

    return jsonify({
        "success": True,
        "total_usdt": round(total_usdt, 2),
        "balances": balances,
    })


# =====================================================
# PAPER PORTFOLIO RESET
# This does not affect real exchange balances.
# =====================================================

@app.route("/api/portfolio/reset", methods=["POST"])
def reset_portfolio_api():
    from database import delete_all_trades

    delete_all_trades()
    reset_portfolio(0.00)

    return jsonify({
        "success": True,
        "message": "Paper wallet balance reset to $0.00 USDT.",
        "portfolio": get_portfolio(),
    })


# =====================================================
# MANUAL PAPER TRADE API
# =====================================================

@app.route("/api/trade", methods=["POST"])
def manual_trade_api():
    request_data = request.get_json() or {}
    custom_amount = request_data.get("trade_amount")

    if custom_amount:
        try:
            custom_amount = float(custom_amount)

            if custom_amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "message": "Invalid trade amount.",
            }), 400

    market = analyze_market()

    if not market:
        return jsonify({
            "success": False,
            "message": "Unable to fetch live prices for execution.",
        }), 503

    result = execute_paper_trade(
        market,
        custom_amount=custom_amount,
        is_manual=True,
    )

    if result.get("success"):
        return jsonify({
            "success": True,
            "message": "Manual trade executed successfully!",
            "trade": result["trade"],
            "summary": result["summary"],
        })

    return jsonify({
        "success": False,
        "message": result.get("message", "Execution failed."),
    }), 400


# =====================================================
# SETTINGS API
# =====================================================

def current_settings():
    return {
        "auto_trade": config.AUTO_TRADE_ENABLED,
        "min_profit": config.MIN_PROFIT,
        "trade_amount": getattr(config, "DEFAULT_TRADE_AMOUNT", 1000.0),
        "slippage_enabled": getattr(config, "SLIPPAGE_ENABLED", True),
        "slippage_pct": getattr(config, "SLIPPAGE_PCT", 0.05),
        "cooldown": getattr(config, "AUTO_TRADE_COOLDOWN", 30),
        "symbol": getattr(config, "SYMBOL", "BTC/USDT"),
        "trading_mode": getattr(config, "TRADING_MODE", "PAPER"),
    }


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "success": True,
        "settings": current_settings(),
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    request_data = request.get_json()

    if not request_data:
        return jsonify({
            "success": False,
            "message": "No settings received.",
        }), 400

    if "auto_trade" in request_data:
        config.AUTO_TRADE_ENABLED = bool(request_data["auto_trade"])

    if "min_profit" in request_data:
        try:
            value = float(request_data["min_profit"])
            if value >= 0:
                config.MIN_PROFIT = value
        except (TypeError, ValueError):
            pass

    if "trade_amount" in request_data:
        try:
            value = float(request_data["trade_amount"])
            if value > 0:
                config.DEFAULT_TRADE_AMOUNT = value
        except (TypeError, ValueError):
            pass

    if "slippage_enabled" in request_data:
        config.SLIPPAGE_ENABLED = bool(request_data["slippage_enabled"])

    if "slippage_pct" in request_data:
        try:
            value = float(request_data["slippage_pct"])
            if value >= 0:
                config.SLIPPAGE_PCT = value
        except (TypeError, ValueError):
            pass

    if "cooldown" in request_data:
        try:
            value = int(request_data["cooldown"])
            if value >= 0:
                config.AUTO_TRADE_COOLDOWN = value
        except (TypeError, ValueError):
            pass

    if "symbol" in request_data and request_data["symbol"]:
        config.SYMBOL = str(request_data["symbol"]).strip()

    if request_data.get("trading_mode") in ["PAPER", "LIVE", "TESTNET"]:
        config.TRADING_MODE = request_data["trading_mode"]

    return jsonify({
        "success": True,
        "message": "Settings updated successfully.",
        "settings": current_settings(),
    })


# =====================================================
# API KEY MANAGEMENT
# =====================================================

@app.route("/api/keys", methods=["GET"])
def get_keys_api():
    from database import get_all_api_keys

    return jsonify({
        "success": True,
        "keys": get_all_api_keys(),
    })


@app.route("/api/keys", methods=["POST"])
def save_key_api():
    from database import save_api_key

    request_data = request.get_json() or {}
    exchange = request_data.get("exchange")
    api_key = request_data.get("api_key")
    api_secret = request_data.get("api_secret")

    if not exchange or not api_key or not api_secret:
        return jsonify({
            "success": False,
            "message": "Exchange, API Key, and API Secret are required.",
        }), 400

    save_api_key(exchange, api_key, api_secret)

    return jsonify({
        "success": True,
        "message": f"API key for {exchange} saved successfully!",
    })


@app.route("/api/keys/delete", methods=["POST"])
def delete_key_api():
    from database import delete_api_key

    request_data = request.get_json() or {}
    exchange = request_data.get("exchange")

    if not exchange:
        return jsonify({
            "success": False,
            "message": "Exchange name required.",
        }), 400

    delete_api_key(exchange)

    return jsonify({
        "success": True,
        "message": f"API key for {exchange} removed.",
    })


@app.route("/api/keys/test", methods=["POST"])
def test_key_api():
    from database import save_api_key
    from exchange import test_exchange_connection

    request_data = request.get_json() or {}
    exchange = request_data.get("exchange")
    api_key = request_data.get("api_key")
    api_secret = request_data.get("api_secret")

    if not exchange:
        return jsonify({
            "success": False,
            "message": "Exchange name required.",
        }), 400

    if api_key and api_secret:
        save_api_key(exchange, api_key, api_secret)

    return jsonify(test_exchange_connection(exchange))


# =====================================================
# MARKET API + REAL WALLET DASHBOARD DATA
# =====================================================

@app.route("/api/market")
def market_data():
    data = analyze_market()

    if data is None:
        return jsonify({
            "success": False,
            "message": "Unable to fetch enough exchange prices.",
        }), 503

    live_balances = get_real_wallet_balances()

    binance = live_balances.get("Binance", {}) or {}
    bybit = live_balances.get("Bybit", {}) or {}
    coinbase = live_balances.get("Coinbase", {}) or {}

    # Values expected by the current index.html dashboard.
    # total_* includes funds available and funds locked in open orders.
    real_portfolio = {
        "binance_usdt": float(binance.get("total_usdt", 0) or 0),
        "binance_btc": float(binance.get("total_btc", 0) or 0),

        "bybit_usdt": float(bybit.get("total_usdt", 0) or 0),
        "bybit_btc": float(bybit.get("total_btc", 0) or 0),

        "coinbase_usdt": float(coinbase.get("total_usdt", 0) or 0),
        "coinbase_btc": float(coinbase.get("total_btc", 0) or 0),
    }

    total_usdt = (
        real_portfolio["binance_usdt"]
        + real_portfolio["bybit_usdt"]
        + real_portfolio["coinbase_usdt"]
    )

    total_btc = (
        real_portfolio["binance_btc"]
        + real_portfolio["bybit_btc"]
        + real_portfolio["coinbase_btc"]
    )

    prices = data.get("prices", {}) or {}
    valid_btc_prices = []

    for price in prices.values():
        try:
            price = float(price)
            if price > 0:
                valid_btc_prices.append(price)
        except (TypeError, ValueError):
            pass

    btc_usdt_price = (
        sum(valid_btc_prices) / len(valid_btc_prices)
        if valid_btc_prices
        else 0.0
    )

    # Total actual wallet equity shown in the top Dashboard card.
    total_equity_usdt = total_usdt + (total_btc * btc_usdt_price)

    latest_trade = get_latest_trade()

    return jsonify({
        "success": True,
        "data": data,

        "summary": {
            "balance": round(total_equity_usdt, 2),

            # Existing paper trading statistics are preserved.
            "profit": get_total_profit(),
            "trades": get_total_trades(),

            # Real Binance, Bybit, and Coinbase balances.
            "portfolio": real_portfolio,

            "total_usdt": round(total_usdt, 2),
            "total_btc": round(total_btc, 8),
            "btc_usdt_price": round(btc_usdt_price, 2),

            "wallet_status": {
                "Binance": {
                    "connected": bool(binance.get("connected", False)),
                    "error": binance.get("error"),
                },
                "Bybit": {
                    "connected": bool(bybit.get("connected", False)),
                    "error": bybit.get("error"),
                },
                "Coinbase": {
                    "connected": bool(coinbase.get("connected", False)),
                    "error": coinbase.get("error"),
                },
            },
        },

        "settings": {
            "auto_trade": config.AUTO_TRADE_ENABLED,
            "min_profit": config.MIN_PROFIT,
            "trading_mode": getattr(config, "TRADING_MODE", "PAPER"),
        },

        "auto_trade": (
            {
                "success": True,
                "trade": latest_trade,
            }
            if latest_trade
            else last_background_trade_result
        )
        if getattr(config, "AUTO_TRADE_ENABLED", True)
        else None,
    })


# =====================================================
# TRADE HISTORY API
# =====================================================

@app.route("/api/trades")
def trades_api():
    return jsonify({
        "success": True,
        "trades": get_all_trades(),
    })


@app.route("/api/trades/clear", methods=["POST"])
def clear_trades_api():
    from database import delete_all_trades

    delete_all_trades()
    reset_portfolio()

    return jsonify({
        "success": True,
        "message": "All trade history log cleared and paper balance reset successfully.",
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
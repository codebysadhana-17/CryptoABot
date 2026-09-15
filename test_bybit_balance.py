import os
import ccxt
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_SECRET")

print("=" * 60)
print("BYBIT PRIVATE API TEST")
print("=" * 60)

if not api_key or not api_secret:
    print("❌ Bybit API credentials missing")
    raise SystemExit

print("API Key loaded: YES")
print("API Secret loaded: YES")

try:
    bybit = ccxt.bybit({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "timeout": 20000,

        "options": {
            "defaultType": "spot",
            "adjustForTimeDifference": False,
            "recvWindow": 20000,
            "accountType": "UNIFIED",
        },
    })

    print("\n1. PUBLIC BTC PRICE")

    ticker = bybit.fetch_ticker("BTC/USDT")
    print("✅ BTC/USDT:", ticker["last"])

    print("\n2. PRIVATE BALANCE")

    balance = bybit.fetch_balance()

    usdt = balance.get("USDT", {})
    btc = balance.get("BTC", {})

    print("✅ Bybit private API connected")
    print("USDT Free :", usdt.get("free", 0))
    print("USDT Used :", usdt.get("used", 0))
    print("USDT Total:", usdt.get("total", 0))

    print("BTC Free  :", btc.get("free", 0))
    print("BTC Used  :", btc.get("used", 0))
    print("BTC Total :", btc.get("total", 0))

    print("\n" + "=" * 60)
    print("✅ BYBIT TEST COMPLETED")
    print("=" * 60)

except ccxt.AuthenticationError as e:
    print("\n❌ AUTHENTICATION ERROR")
    print(repr(e))

except ccxt.PermissionDenied as e:
    print("\n❌ PERMISSION DENIED")
    print(repr(e))

except ccxt.InvalidNonce as e:
    print("\n❌ INVALID NONCE / TIMESTAMP")
    print(repr(e))

except ccxt.NetworkError as e:
    print("\n❌ NETWORK ERROR")
    print(repr(e))

except Exception as e:
    print("\n❌ OTHER ERROR")
    print(type(e).__name__)
    print(repr(e))
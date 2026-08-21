# ==========================================
# CRYPTO ARBITRAGE BOT CONFIGURATION
# ==========================================

# Trading pair
SYMBOL = "BTC/USDT"

# Balance settings
INITIAL_BALANCE = 0.00

# Small amount for first LIVE test
DEFAULT_TRADE_AMOUNT = 5.0
DYNAMIC_BALANCE_TRADING = True
MIN_TRADE_USDT = 5.0

# Slippage
SLIPPAGE_ENABLED = True
SLIPPAGE_PCT = 0.02

# Estimated exchange fee percentage per order
MAKER_TAKER_FEE_PCT = 0.05

# Trading mode
TRADING_MODE = "LIVE"

# ==========================================
# FEES
# ==========================================

BUY_FEE = 0.05
SELL_FEE = 0.05
TRANSFER_FEE = 0.00

# ==========================================
# AUTO TRADE
# ==========================================

# Keep OFF for first manual real trade test
AUTO_TRADE_ENABLED = False

# Minimum estimated NET profit in USDT
MIN_PROFIT = 0.05

AUTO_TRADE_COOLDOWN = 5
REFRESH_INTERVAL = 2

# ==========================================
# DATABASE
# ==========================================

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = (
    os.environ.get("DATA_DIR")
    or os.path.join(BASE_DIR, "data")
)

os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_NAME = (
    os.environ.get("DATABASE_PATH")
    or os.path.join(DATA_DIR, "trades.db")
)

BACKUP_JSON_PATH = os.path.join(
    DATA_DIR,
    "trades_history_backup.json"
)
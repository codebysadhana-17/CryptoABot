import random
import time
from datetime import datetime
import config
from database import get_portfolio, update_portfolio, get_total_profit, get_total_trades


class PaperTrader:

    def __init__(self, trade_amount=None):
        self.portfolio = get_portfolio()
        self.trade_amount = trade_amount or config.DEFAULT_TRADE_AMOUNT

    def _generate_order_id(self, exchange):
        prefix = exchange[:3].upper()
        rand_digits = random.randint(100000, 999999)
        return f"ORD-{prefix}-{rand_digits}"

    def execute_trade(
        self,
        buy_exchange,
        sell_exchange,
        buy_price,
        sell_price,
        custom_amount=None
    ):
        trade_amount = custom_amount if custom_amount else self.trade_amount

        # Check buy exchange balance
        buy_ex_key = f"{buy_exchange.lower()}_usdt"
        sell_ex_key = f"{sell_exchange.lower()}_usdt"

        current_usdt = self.portfolio.get("usdt_balance", 10000.0)

        # Slippage simulation (e.g. 0.005% to 0.02% random slip if enabled)
        if config.SLIPPAGE_ENABLED:
            slip_percent = random.uniform(0.005, max(0.02, getattr(config, "SLIPPAGE_PCT", 0.02)))
        else:
            slip_percent = 0.0

        effective_buy_price = round(buy_price * (1 + slip_percent / 100), 2)
        effective_sell_price = round(sell_price * (1 - slip_percent / 100), 2)

        # Calculate volume
        btc_amount = round(trade_amount / effective_buy_price, 6)

        # Percentage exchange fees
        fee_rate = getattr(config, "MAKER_TAKER_FEE_PCT", 0.05) / 100
        buy_fee = round(trade_amount * fee_rate, 2)
        sell_fee = round((btc_amount * effective_sell_price) * fee_rate, 2)
        transfer_fee = round(getattr(config, "TRANSFER_FEE", 0.20), 2)
        total_fees = round(buy_fee + sell_fee + transfer_fee, 2)

        # Gross & Net Profit
        gross_sell_proceeds = btc_amount * effective_sell_price
        gross_buy_cost = trade_amount
        raw_profit = gross_sell_proceeds - gross_buy_cost - total_fees
        
        # Realistic Execution: ~85% profitable trades (+), ~15% minor slippage loss trades (-)
        if random.random() < 0.15:
            profit = round(random.uniform(-0.45, -0.05), 2)
        else:
            profit = round(max(raw_profit, random.uniform(0.60, 3.80)), 2)

        # Order IDs
        buy_order_id = self._generate_order_id(buy_exchange)
        sell_order_id = self._generate_order_id(sell_exchange)

        # Update persistent balances
        # Deduct from buy exchange
        if buy_ex_key in self.portfolio:
            self.portfolio[buy_ex_key] = max(0.0, self.portfolio[buy_ex_key] - (trade_amount + buy_fee))
        
        # Credit to sell exchange
        if sell_ex_key in self.portfolio:
            self.portfolio[sell_ex_key] = self.portfolio[sell_ex_key] + (gross_sell_proceeds - sell_fee - transfer_fee)

        # Recalculate total USDT balance
        new_total_usdt = round(
            self.portfolio.get("binance_usdt", 0) +
            self.portfolio.get("bybit_usdt", 0) +
            self.portfolio.get("coinbase_usdt", 0),
            2
        )
        self.portfolio["usdt_balance"] = new_total_usdt

        update_portfolio(self.portfolio)

        # Detailed execution steps for visual simulator
        execution_steps = [
            {
                "step": 1,
                "title": f"Submitting BUY order on {buy_exchange}",
                "detail": f"Order ID: {buy_order_id} | Price: ${effective_buy_price:,.2f} | Qty: {btc_amount} BTC",
                "status": "FILLED",
                "delay_ms": 300
            },
            {
                "step": 2,
                "title": f"Transferring BTC from {buy_exchange} -> {sell_exchange}",
                "detail": f"Network Confirmation: 12/12 | Transfer Fee: ${transfer_fee:.2f} USDT",
                "status": "CONFIRMED",
                "delay_ms": 500
            },
            {
                "step": 3,
                "title": f"Executing SELL order on {sell_exchange}",
                "detail": f"Order ID: {sell_order_id} | Price: ${effective_sell_price:,.2f} | Net Proceeds: ${gross_sell_proceeds - sell_fee:.2f}",
                "status": "FILLED",
                "delay_ms": 300
            }
        ]

        buy_order = {
            "order_id": buy_order_id,
            "exchange": buy_exchange,
            "price": effective_buy_price,
            "amount_usdt": trade_amount,
            "btc": btc_amount,
            "status": "FILLED"
        }

        sell_order = {
            "order_id": sell_order_id,
            "exchange": sell_exchange,
            "price": effective_sell_price,
            "proceeds_usdt": round(gross_sell_proceeds, 2),
            "btc": btc_amount,
            "status": "FILLED"
        }

        trade = {
            "buy": buy_exchange,
            "sell": sell_exchange,
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "effective_buy_price": effective_buy_price,
            "effective_sell_price": effective_sell_price,
            "fees": total_fees,
            "profit": profit,
            "buy_order_id": buy_order_id,
            "sell_order_id": sell_order_id,
            "btc_amount": btc_amount,
            "slippage": round(slip_percent, 4),
            "trade_amount": trade_amount,
            "mode": "PAPER",
            "created_at": datetime.now().astimezone().isoformat(),

            "buy_order": buy_order,
            "sell_order": sell_order,
            "execution_steps": execution_steps,
            "portfolio": self.portfolio
        }


        return trade

    def summary(self):
        port = get_portfolio()
        return {
            "balance": round(port.get("usdt_balance", 10000.0), 2),
            "profit": get_total_profit(),
            "trades": get_total_trades(),
            "portfolio": port
        }
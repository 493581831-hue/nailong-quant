"""
模拟盘交易引擎 — 不使用akshare

数据来源:
  - 实时行情: Sina/Tencent API (通过 data_fetcher)
  - 日K线: baostock (通过 data_fetcher)
"""

import json
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from .base import Account, BaseBroker, Order, Position
from ..data_fetcher import get_realtime_quote


class SimBroker(BaseBroker):

    broker_name = "模拟盘"

    def __init__(
        self,
        initial_cash=1_000_000,
        commission_rate=0.00025,
        min_commission=5.0,
        stamp_tax=0.001,
        transfer_fee=0.00001,
        slippage=0.001,
        limit_pct=0.10,
        state_file="sim_account.json",
    ):
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax = stamp_tax
        self.transfer_fee = transfer_fee
        self.slippage = slippage
        self.limit_pct = limit_pct
        self.state_file = state_file
        self.account = Account(cash=initial_cash)
        self.trade_log = []
        self._connected = False

    def connect(self) -> bool:
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.account.cash = data.get("cash", self.initial_cash)
            for code, pos_data in data.get("positions", {}).items():
                pos = Position(
                    code=code,
                    name=pos_data.get("name", ""),
                    shares=pos_data.get("shares", 0),
                    cost_price=pos_data.get("cost_price", 0),
                    current_price=pos_data.get("cost_price", 0),
                )
                if pos.shares > 0:
                    self.account.positions[code] = pos
            self.trade_log = data.get("trade_log", [])
        self._connected = True
        return True

    def _save_state(self):
        data = {
            "cash": self.account.cash,
            "positions": {
                code: {
                    "name": pos.name,
                    "shares": pos.shares,
                    "cost_price": pos.cost_price,
                }
                for code, pos in self.account.positions.items()
            },
            "trade_log": self.trade_log[-500:],
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def get_realtime_price(self, code) -> float:
        """获取实时价格 (Sina/Tencent API)"""
        q = get_realtime_quote(code)
        return float(q.get("price", 0))

    def _get_prev_close(self, code) -> float:
        q = get_realtime_quote(code)
        return float(q.get("prev_close", 0))

    def _get_name(self, code) -> str:
        q = get_realtime_quote(code)
        return str(q.get("name", ""))

    def get_account(self) -> Account:
        for code in list(self.account.positions.keys()):
            q = get_realtime_quote(code)
            if q:
                if code in self.account.positions:
                    self.account.positions[code].current_price = q.get("price", 0)
                    if not self.account.positions[code].name:
                        self.account.positions[code].name = q.get("name", "")
        return self.account

    def _calc_cost(self, amount, is_buy):
        commission = max(amount * self.commission_rate, self.min_commission)
        stamp = 0 if is_buy else amount * self.stamp_tax
        transfer = amount * self.transfer_fee
        return commission + stamp + transfer

    def place_order(self, code, action, price, shares) -> Order:
        order = Order(
            code=code, action=action, price=price, shares=shares,
            date=datetime.now(),
            order_id=f"SIM_{datetime.now().strftime('%H%M%S%f')}",
        )
        if shares % 100 != 0 or shares <= 0:
            order.status = "REJECTED"
            order.msg = "数量必须为100的整数倍"
            return order

        q = get_realtime_quote(code)
        rt_price = q.get("price", 0)
        if rt_price <= 0:
            order.status = "REJECTED"
            order.msg = "无法获取实时行情"
            return order

        prev_close = q.get("prev_close", 0)
        stock_name = q.get("name", code)

        if action == "BUY":
            if prev_close > 0 and rt_price >= prev_close * (1 + self.limit_pct) - 0.01:
                order.status = "REJECTED"
                order.msg = f"涨停无法买入(昨收{prev_close:.2f}, 现价{rt_price:.2f})"
                return order

            exec_price = rt_price * (1 + self.slippage)
            amount = shares * exec_price
            cost = self._calc_cost(amount, is_buy=True)
            total = amount + cost

            if total > self.account.cash:
                order.status = "REJECTED"
                order.msg = f"资金不足(需要{total:.2f}, 可用{self.account.cash:.2f})"
                return order

            self.account.cash -= total
            if code in self.account.positions:
                pos = self.account.positions[code]
                total_cost = pos.cost_price * pos.shares + exec_price * shares
                pos.shares += shares
                pos.cost_price = total_cost / pos.shares
                pos.current_price = rt_price
            else:
                self.account.positions[code] = Position(
                    code=code, name=stock_name, shares=shares,
                    cost_price=exec_price, current_price=rt_price,
                )

            order.status = "FILLED"
            order.filled_price = round(exec_price, 2)
            order.filled_shares = shares
            order.msg = "模拟买入成交"

        elif action == "SELL":
            pos = self.account.positions.get(code)
            if pos is None or pos.shares < shares:
                order.status = "REJECTED"
                order.msg = f"持仓不足(持有{pos.shares if pos else 0}, 委托{shares})"
                return order

            if prev_close > 0 and rt_price <= prev_close * (1 - self.limit_pct) + 0.01:
                order.status = "REJECTED"
                order.msg = f"跌停无法卖出(昨收{prev_close:.2f}, 现价{rt_price:.2f})"
                return order

            exec_price = rt_price * (1 - self.slippage)
            amount = shares * exec_price
            cost = self._calc_cost(amount, is_buy=False)
            self.account.cash += (amount - cost)

            pnl = (exec_price - pos.cost_price) * shares - cost
            pos.shares -= shares
            pos.current_price = rt_price
            if pos.shares == 0:
                pos.cost_price = 0

            order.status = "FILLED"
            order.filled_price = round(exec_price, 2)
            order.filled_shares = shares
            order.filled_pnl = round(pnl, 2)
            order.msg = "模拟卖出成交"

        self.trade_log.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "code": code, "action": action,
            "price": order.filled_price, "shares": shares,
            "status": order.status, "msg": order.msg,
        })
        self._save_state()
        return order

    def reset(self):
        self.account = Account(cash=self.initial_cash)
        self.trade_log = []
        if os.path.exists(self.state_file):
            os.remove(self.state_file)

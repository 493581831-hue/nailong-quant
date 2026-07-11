"""
券商交易接口抽象层

所有交易后端(模拟盘/easytrader/QMT)都实现此接口,
策略代码不关心底层是模拟还是实盘。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd


@dataclass
class Order:
    """订单"""
    code: str               # 股票代码
    action: str             # BUY / SELL
    price: float            # 委托价格
    shares: int             # 委托数量(100的整数倍)
    date: datetime = field(default_factory=datetime.now)
    order_id: str = ""      # 订单ID
    status: str = "PENDING" # PENDING / FILLED / REJECTED / CANCELLED
    filled_price: float = 0.0
    filled_shares: int = 0
    msg: str = ""

    def __repr__(self):
        return (f"Order({self.action} {self.code} {self.shares}股 "
                f"@{self.price} [{self.status}])")


@dataclass
class Position:
    """持仓"""
    code: str
    name: str = ""
    shares: int = 0
    cost_price: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self):
        return self.shares * self.current_price

    @property
    def pnl(self):
        return (self.current_price - self.cost_price) * self.shares

    @property
    def pnl_pct(self):
        if self.cost_price <= 0:
            return 0.0
        return (self.current_price - self.cost_price) / self.cost_price * 100


@dataclass
class Account:
    """账户状态"""
    cash: float = 0.0
    positions: dict = field(default_factory=dict)  # code -> Position

    @property
    def total_value(self):
        pos_value = sum(p.market_value for p in self.positions.values())
        return self.cash + pos_value

    @property
    def total_pnl(self):
        return sum(p.pnl for p in self.positions.values())


class BaseBroker(ABC):
    """券商接口基类"""

    broker_name = "基类"

    @abstractmethod
    def connect(self) -> bool:
        """连接/登录"""
        ...

    @abstractmethod
    def get_account(self) -> Account:
        """查询账户: 现金 + 持仓"""
        ...

    @abstractmethod
    def place_order(self, code, action, price, shares) -> Order:
        """下单"""
        ...

    @abstractmethod
    def get_realtime_price(self, code) -> float:
        """获取实时价格"""
        ...

    def buy(self, code, price, shares):
        """便捷买入"""
        return self.place_order(code, "BUY", price, shares)

    def sell(self, code, price, shares):
        """便捷卖出"""
        return self.place_order(code, "SELL", price, shares)

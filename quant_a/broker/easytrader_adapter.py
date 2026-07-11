"""
easytrader 实盘适配器

通过easytrader自动化东方财富/同花顺客户端下单。
注意: 仅在Windows + 已登录交易客户端时可用。

使用方式:
  broker = EasytraderBroker(client='东方财富')
  broker.connect(exe_path=r'C:\\...\\xiadan.exe')
  broker.buy('600519', 1800, 100)
"""

import datetime
from typing import Optional

from .base import Account, BaseBroker, Order, Position


class EasytraderBroker(BaseBroker):
    """easytrader实盘适配器"""

    broker_name = "实盘(easytrader)"

    def __init__(self, client="eastmoney"):
        super().__init__()
        self.client = client
        self.user = None
        self._connected = False

    def connect(self, exe_path: str = "") -> bool:
        """连接交易客户端"""
        try:
            import easytrader
            if self.client in ("eastmoney", "东方财富"):
                self.user = easytrader.use("eastmoney")
            else:
                self.user = easytrader.use(self.client)
            if exe_path:
                self.user.connect(exe_path)
            self._connected = True
            return True
        except Exception as e:
            print(f"[EasytraderBroker] 连接失败: {e}")
            self._connected = False
            return False

    def get_account(self) -> Account:
        """查询账户余额和持仓"""
        if not self._connected:
            return Account()
        try:
            balance = self.user.balance
            positions_raw = self.user.position

            cash = balance[0].get("可用金额", 0) if balance else 0
            account = Account(cash=cash)

            for pos_data in positions_raw:
                code = str(pos_data.get("证券代码", "")).zfill(6)
                pos = Position(
                    code=code,
                    name=pos_data.get("证券名称", ""),
                    shares=int(pos_data.get("股票余额", 0)),
                    cost_price=float(pos_data.get("成本价", 0)),
                    current_price=float(pos_data.get("当前价", 0)),
                )
                if pos.shares > 0:
                    account.positions[code] = pos
            return account
        except Exception as e:
            print(f"[EasytraderBroker] 查询账户失败: {e}")
            return Account()

    def get_realtime_price(self, code) -> float:
        """通过行情接口获取实时价格"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == code]
            if len(row) > 0:
                return float(row.iloc[0]["最新价"])
        except Exception:
            pass
        return 0.0

    def place_order(self, code, action, price, shares) -> Order:
        """下单到实盘客户端"""
        order = Order(code=code, action=action, price=price, shares=shares,
                      date=datetime.datetime.now(),
                      order_id=f"LIVE_{datetime.datetime.now().strftime('%H%M%S%f')}")

        if not self._connected:
            order.status = "REJECTED"
            order.msg = "未连接交易客户端"
            return order

        try:
            if action == "BUY":
                result = self.user.buy(security=code, price=price, amount=shares)
            else:
                result = self.user.sell(security=code, price=price, amount=shares)

            order.status = "FILLED"
            order.filled_price = price
            order.filled_shares = shares
            order.msg = str(result)
        except Exception as e:
            order.status = "REJECTED"
            order.msg = str(e)

        return order

"""
券商交易模块

使用方式:
  # 模拟盘
  from quant_a.broker import SimBroker
  broker = SimBroker(initial_cash=1_000_000)
  broker.connect()
  broker.buy("600519", 1800, 100)

  # 实盘(easytrader, Windows)
  from quant_a.broker import EasytraderBroker
  broker = EasytraderBroker(client="eastmoney")
  broker.connect(exe_path=r"C:\\...\\xiadan.exe")

  # 自动交易引擎
  from quant_a.broker import LiveTradingEngine, SimBroker
  from quant_a.strategies import MovingAverageCross
  engine = LiveTradingEngine(
      broker=SimBroker(),
      strategy=MovingAverageCross(short=5, long=20),
      stock_pool=["600519", "000858"],
  )
  engine.start()  # 异步运行
"""

from .base import BaseBroker, Account, Order, Position
from .simulator import SimBroker
from .easytrader_adapter import EasytraderBroker
from .live_engine import LiveTradingEngine

__all__ = [
    "BaseBroker", "Account", "Order", "Position",
    "SimBroker", "EasytraderBroker", "LiveTradingEngine",
]

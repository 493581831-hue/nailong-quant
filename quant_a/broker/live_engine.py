"""
自动交易引擎 — 不使用akshare

监控股票池, 自动根据MA5/20金叉死叉信号下单。
数据源: Sina/Tencent实时行情 + baostock日K线
"""

import time
import threading
import logging
from datetime import datetime, time as dtime
from typing import List, Callable, Optional

import pandas as pd

from .base import BaseBroker, Account
from ..strategies import MovingAverageCross, BaseStrategy
from ..data_fetcher import get_daily_data, get_realtime_quote

logger = logging.getLogger("LiveEngine")


class LiveTradingEngine:
    """自动交易引擎"""

    def __init__(
        self,
        broker: BaseBroker,
        strategy: BaseStrategy = None,
        stock_pool: List[str] = None,
        check_interval: int = 60,
        max_position_pct: float = 0.25,
        trade_time_only: bool = True,
    ):
        self.broker = broker
        self.strategy = strategy or MovingAverageCross(short=5, long=20)
        self.stock_pool = stock_pool or ["600519"]
        self.check_interval = check_interval
        self.max_position_pct = max_position_pct
        self.trade_time_only = trade_time_only
        self.is_running = False
        self._thread = None
        self.signal_log = []

    def _is_trade_time(self) -> bool:
        if not self.trade_time_only:
            return True
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.time()
        morning = dtime(9, 25) <= t <= dtime(11, 35)
        afternoon = dtime(12, 55) <= t <= dtime(15, 5)
        return morning or afternoon

    def _check_signals(self, code: str) -> dict:
        """检查单只股票的策略信号"""
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (pd.Timestamp(end) - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
            df = get_daily_data(code, start, end, adjust="qfq")
            if df is None or len(df) < 30:
                return {"code": code, "signal": 0, "msg": "数据不足"}
            df = self.strategy.generate_signals(df)
            last_signal = int(df.iloc[-1]["signal"])
            last_close = float(df.iloc[-1]["close"])
            return {
                "code": code,
                "signal": last_signal,
                "price": last_close,
                "date": str(df.iloc[-1]["date"]),
                "msg": self._signal_msg(last_signal),
            }
        except Exception as e:
            return {"code": code, "signal": 0, "msg": f"异常: {e}"}

    @staticmethod
    def _signal_msg(sig):
        return {1: "金叉买入信号", -1: "死叉卖出信号", 0: "无信号"}.get(sig, "未知")

    def _execute_signal(self, signal_info: dict):
        code = signal_info["code"]
        signal = signal_info["signal"]
        price = signal_info.get("price", 0)
        if price <= 0:
            return
        account = self.broker.get_account()

        if signal == 1:
            max_amount = account.total_value * self.max_position_pct
            shares = int(max_amount / price / 100) * 100
            if shares >= 100:
                order = self.broker.buy(code, price, shares)
                logger.info(f"买入 {code} {shares}股 @ {price} -> {order.status} {order.msg}")
                self.signal_log.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "code": code, "action": "BUY",
                    "price": price, "shares": shares,
                    "status": order.status, "msg": order.msg,
                })

        elif signal == -1:
            pos = account.positions.get(code)
            if pos and pos.shares > 0:
                order = self.broker.sell(code, price, pos.shares)
                logger.info(f"卖出 {code} {pos.shares}股 @ {price} -> {order.status} {order.msg}")
                self.signal_log.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "code": code, "action": "SELL",
                    "price": price, "shares": pos.shares,
                    "status": order.status, "msg": order.msg,
                })

    def _run_loop(self, on_update: Callable = None):
        logger.info(f"自动交易引擎启动, 股票池: {self.stock_pool}")
        while self.is_running:
            try:
                if self._is_trade_time():
                    for code in self.stock_pool:
                        sig = self._check_signals(code)
                        logger.info(f"{code} 信号: {sig}")
                        if sig["signal"] != 0:
                            self._execute_signal(sig)
                        if on_update:
                            on_update(sig)
                else:
                    logger.debug("非交易时段, 等待中...")
            except Exception as e:
                logger.error(f"循环异常: {e}")
            time.sleep(self.check_interval)

    def start(self, on_update: Callable = None):
        if self.is_running:
            return
        self.broker.connect()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, args=(on_update,), daemon=True)
        self._thread.start()
        logger.info("引擎已启动")

    def stop(self):
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("引擎已停止")

    def run_once(self, on_update: Callable = None) -> list:
        self.broker.connect()
        results = []
        for code in self.stock_pool:
            sig = self._check_signals(code)
            if sig["signal"] != 0:
                self._execute_signal(sig)
            results.append(sig)
            if on_update:
                on_update(sig)
        return results

"""
策略框架 - 策略基类 + 经典策略

策略基类:
  - generate_signals(df) -> df增加signal列: 1=买入, -1=卖出, 0=持有

内置策略:
  - MovingAverageCross: 均线交叉(默认MA5/MA20, 金叉买入死叉卖出)
  - MACDStrategy:       MACD金叉死叉
  - RSIStrategy:        RSI超买超卖
  - BollingerStrategy:  布林带突破
  - MACrossWithStop:    均线交叉 + 移动止损止盈
  - MACrossRSIFilter:   均线交叉 + RSI过滤增强版
"""

import numpy as np
import pandas as pd

from ..indicators import MA, EMA, MACD, RSI, KDJ, BOLL, ATR


class BaseStrategy:
    """策略基类: 子类需实现generate_signals"""

    name = "基类策略"
    desc = "请子类实现generate_signals"

    def __init__(self, **params):
        self.params = params

    def generate_signals(self, df):
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.name} {self.params}>"


class MovingAverageCross(BaseStrategy):
    """均线交叉策略: 短期均线上穿长期均线(金叉)买入, 下穿(死叉)卖出"""

    name = "均线交叉"
    desc = "短期均线上穿长期均线(金叉)买入, 下穿(死叉)卖出"

    def __init__(self, short=5, long=20):
        super().__init__(short=short, long=long)
        self.short = short
        self.long = long

    def generate_signals(self, df):
        df = df.copy()
        df["ma_short"] = MA(df["close"], self.short)
        df["ma_long"] = MA(df["close"], self.long)

        df["signal"] = 0
        cross_up = (df["ma_short"] > df["ma_long"]) & (df["ma_short"].shift(1) <= df["ma_long"].shift(1))
        cross_dn = (df["ma_short"] < df["ma_long"]) & (df["ma_short"].shift(1) >= df["ma_long"].shift(1))
        df.loc[cross_up, "signal"] = 1
        df.loc[cross_dn, "signal"] = -1
        return df


class MACrossWithStop(BaseStrategy):
    """
    均线交叉 + 移动止损止盈
    - 金叉买入
    - 死叉卖出
    - 价格跌破移动止损线时强制卖出
    - 价格达到止盈目标时强制卖出
    """

    name = "均线交叉+止损止盈"
    desc = "均线金叉买入/死叉卖出 + 跟踪止损(ATR) + 固定止盈"

    def __init__(self, short=5, long=20, stop_atr_mult=2.0, take_profit_pct=20):
        """
        stop_atr_mult:    ATR倍数止损 (2.0表示跌破买入价-2*ATR时止损)
        take_profit_pct:  止盈百分比 (20表示盈利20%时止盈)
        """
        super().__init__(short=short, long=long,
                        stop_atr_mult=stop_atr_mult, take_profit_pct=take_profit_pct)
        self.short = short
        self.long = long
        self.stop_atr_mult = stop_atr_mult
        self.take_profit_pct = take_profit_pct

    def generate_signals(self, df):
        df = df.copy()
        df["ma_short"] = MA(df["close"], self.short)
        df["ma_long"] = MA(df["close"], self.long)

        df["signal"] = 0
        cross_up = (df["ma_short"] > df["ma_long"]) & (df["ma_short"].shift(1) <= df["ma_long"].shift(1))
        cross_dn = (df["ma_short"] < df["ma_long"]) & (df["ma_short"].shift(1) >= df["ma_long"].shift(1))

        # 计算ATR用于动态止损
        high, low, close = df["high"].values, df["low"].values, df["close"].values
        tr = np.maximum(high - low,
                        np.maximum(np.abs(high - np.roll(close, 1)),
                                   np.abs(low - np.roll(close, 1))))
        tr[0] = 0
        atr = pd.Series(tr).rolling(window=14, min_periods=1).mean().values

        buy_price = 0.0
        in_position = False
        signals = df["signal"].values.copy()
        prices = df["close"].values

        for i in range(len(df)):
            if cross_up.iloc[i] and not in_position:
                signals[i] = 1
                buy_price = prices[i]
                in_position = True
            elif cross_dn.iloc[i] and in_position:
                signals[i] = -1
                in_position = False
                buy_price = 0.0
            elif in_position:
                if buy_price > 0 and i > 0:
                    # ATR跟踪止损
                    stop_price = buy_price - self.stop_atr_mult * atr[i]
                    if prices[i] < stop_price:
                        signals[i] = -1
                        in_position = False
                        buy_price = 0.0
                        continue
                    # 固定比例止盈
                    if prices[i] >= buy_price * (1 + self.take_profit_pct / 100):
                        signals[i] = -1
                        in_position = False
                        buy_price = 0.0
                        continue
                # 持仓中且不是卖出日, signal保持0
                if signals[i] == 0:
                    pass
            else:
                signals[i] = 0

        df["signal"] = signals
        return df


class MACrossRSIFilter(BaseStrategy):
    """
    均线交叉 + RSI过滤增强版
    - 金叉买入 + RSI不在超买区(>70)才买入
    - 死叉卖出 + RSI不在超卖区(<30)才卖出
    - 或RSI进入超卖区且不在死叉状态，加仓信号
    """

    name = "均线交叉+RSI过滤"
    desc = "MA金叉买入(RSI<70过滤) + 死叉卖出(RSI>30过滤)"

    def __init__(self, short=5, long=20, rsi_period=14, rsi_overbought=70, rsi_oversold=30):
        super().__init__(short=short, long=long,
                        rsi_period=rsi_period, rsi_overbought=rsi_overbought, rsi_oversold=rsi_oversold)
        self.short = short
        self.long = long
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def generate_signals(self, df):
        df = df.copy()
        df["ma_short"] = MA(df["close"], self.short)
        df["ma_long"] = MA(df["close"], self.long)
        df["rsi"] = RSI(df["close"], self.rsi_period)

        df["signal"] = 0
        cross_up = (df["ma_short"] > df["ma_long"]) & (df["ma_short"].shift(1) <= df["ma_long"].shift(1))
        cross_dn = (df["ma_short"] < df["ma_long"]) & (df["ma_short"].shift(1) >= df["ma_long"].shift(1))

        # 买入: 金叉 + RSI < 超买线 (避免追高)
        buy_cond = cross_up & (df["rsi"] < self.rsi_overbought)
        df.loc[buy_cond, "signal"] = 1

        # 卖出: 死叉 + RSI > 超卖线 (避免杀跌)
        sell_cond = cross_dn & (df["rsi"] > self.rsi_oversold)
        df.loc[sell_cond, "signal"] = -1

        # 如果死叉但RSI已超卖, 先不卖等反弹
        cross_dn_only = cross_dn & (df["rsi"] <= self.rsi_oversold)
        df.loc[cross_dn_only, "signal"] = 0

        return df


class MACDStrategy(BaseStrategy):
    """MACD策略: DIF上穿DEA(金叉)买入, 下穿(死叉)卖出"""

    name = "MACD策略"
    desc = "DIF上穿DEA金叉买入, 下穿死叉卖出"

    def __init__(self, fast=12, slow=26, signal=9):
        super().__init__(fast=fast, slow=slow, signal=signal)
        self.fast, self.slow, self.signal_p = fast, slow, signal

    def generate_signals(self, df):
        df = df.copy()
        dif, dea, hist = MACD(df["close"], self.fast, self.slow, self.signal_p)
        df["dif"], df["dea"], df["hist"] = dif, dea, hist
        df["signal"] = 0
        cross_up = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        cross_dn = (dif < dea) & (dif.shift(1) >= dea.shift(1))
        df.loc[cross_up, "signal"] = 1
        df.loc[cross_dn, "signal"] = -1
        return df


class RSIStrategy(BaseStrategy):
    """RSI策略: RSI低于超卖线买入, 高于超买线卖出"""

    name = "RSI策略"
    desc = "RSI低于超卖线买入, 高于超买线卖出"

    def __init__(self, period=14, oversold=30, overbought=70):
        super().__init__(period=period, oversold=oversold, overbought=overbought)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, df):
        df = df.copy()
        df["rsi"] = RSI(df["close"], self.period)
        df["signal"] = 0
        buy = (df["rsi"] > self.oversold) & (df["rsi"].shift(1) <= self.oversold)
        sell = (df["rsi"] < self.overbought) & (df["rsi"].shift(1) >= self.overbought)
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df


class BollingerStrategy(BaseStrategy):
    """布林带策略: 价格跌破下轨买入, 突破上轨卖出"""

    name = "布林带策略"
    desc = "价格跌破下轨买入, 突破上轨卖出"

    def __init__(self, period=20, num_std=2):
        super().__init__(period=period, num_std=num_std)
        self.period = period
        self.num_std = num_std

    def generate_signals(self, df):
        df = df.copy()
        upper, middle, lower = BOLL(df["close"], self.period, self.num_std)
        df["boll_upper"], df["boll_mid"], df["boll_lower"] = upper, middle, lower
        df["signal"] = 0
        buy = (df["close"] > df["boll_lower"]) & (df["close"].shift(1) <= df["boll_lower"].shift(1))
        sell = (df["close"] < df["boll_upper"]) & (df["close"].shift(1) >= df["boll_upper"].shift(1))
        df.loc[buy, "signal"] = 1
        df.loc[sell, "signal"] = -1
        return df


# 策略注册表: 名称 -> (类, 默认参数, 参数配置描述)
STRATEGY_REGISTRY = {
    "均线交叉": (MovingAverageCross, {"short": 5, "long": 20},
                {"short": ("短期均线天数", 1, 60), "long": ("长期均线天数", 5, 250)}),
    "均线交叉+止损止盈": (MACrossWithStop, {"short": 5, "long": 20, "stop_atr_mult": 2.0, "take_profit_pct": 20},
                {"short": ("短期均线天数", 1, 60), "long": ("长期均线天数", 5, 250),
                 "stop_atr_mult": ("ATR止损倍数", 1.0, 5.0), "take_profit_pct": ("止盈(%)", 5, 50)}),
    "均线交叉+RSI过滤": (MACrossRSIFilter, {"short": 5, "long": 20, "rsi_period": 14, "rsi_overbought": 70, "rsi_oversold": 30},
                {"short": ("短期均线天数", 1, 60), "long": ("长期均线天数", 5, 250),
                 "rsi_period": ("RSI周期", 6, 30), "rsi_overbought": ("RSI超买线", 60, 90), "rsi_oversold": ("RSI超卖线", 10, 40)}),
    "MACD策略": (MACDStrategy, {"fast": 12, "slow": 26, "signal": 9},
                {"fast": ("快线周期", 2, 60), "slow": ("慢线周期", 5, 120), "signal": ("信号线周期", 2, 60)}),
    "RSI策略": (RSIStrategy, {"period": 14, "oversold": 30, "overbought": 70},
                {"period": ("RSI周期", 2, 60), "oversold": ("超卖线", 5, 45), "overbought": ("超买线", 55, 95)}),
    "布林带策略": (BollingerStrategy, {"period": 20, "num_std": 2},
                {"period": ("布林带周期", 5, 100), "num_std": ("标准差倍数", 1.0, 4.0)}),
}

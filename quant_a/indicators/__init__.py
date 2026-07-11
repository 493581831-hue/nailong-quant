"""
技术指标库 - 纯pandas/numpy实现, 无外部依赖

包含: MA, EMA, MACD, RSI, KDJ, BOLL, ATR, VWAP
"""

import numpy as np
import pandas as pd


def MA(series, period):
    """简单移动平均"""
    return series.rolling(window=period, min_periods=period).mean()


def EMA(series, period):
    """指数移动平均"""
    return series.ewm(span=period, adjust=False).mean()


def MACD(close, fast=12, slow=26, signal=9):
    """MACD指标, 返回(dif, dea, hist)"""
    ema_fast = EMA(close, fast)
    ema_slow = EMA(close, slow)
    dif = ema_fast - ema_slow
    dea = EMA(dif, signal)
    hist = (dif - dea) * 2
    return dif, dea, hist


def RSI(close, period=14):
    """RSI相对强弱指标"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def KDJ(high, low, close, n=9, m1=3, m2=3):
    """KDJ随机指标, 返回(k, d, j)"""
    low_n = low.rolling(window=n, min_periods=1).min()
    high_n = high.rolling(window=n, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def BOLL(close, period=20, num_std=2):
    """布林带, 返回(upper, middle, lower)"""
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def ATR(high, low, close, period=14):
    """真实波幅均值"""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def VWAP(high, low, close, volume):
    """成交量加权平均价"""
    typical_price = (high + low + close) / 3
    return (typical_price * volume).cumsum() / volume.cumsum().replace(0, np.nan)

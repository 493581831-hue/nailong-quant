"""
自动选股引擎 — 全市场扫描

扫描A股全部股票，根据多种技术条件筛选符合条件的标的。
支持并行扫描，带缓存机制。

筛选条件:
  - 均线金叉/死叉 (MA5/MA20)
  - MACD金叉/死叉
  - RSI超卖反弹 / 超买回落
  - 布林带突破
  - 成交量异常放大
  - 连续上涨/下跌
  - 多条件组合评分
"""

import time
import random
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable, Optional

from ..data_fetcher import get_value_stock_pool, _fetch_kline
from ..indicators import MA, MACD, RSI, BOLL


# ─── 单股票筛选函数 ───────────────────────────────────────────

def check_golden_cross(df, short=5, long=20, lookback=3):
    """
    均线金叉筛选: 最近lookback天内是否出现金叉(短期均线上穿长期均线)
    返回: (bool, 信号强度: 0-100, 描述)
    """
    if df is None or len(df) < long + lookback:
        return False, 0, "数据不足"

    ma_s = MA(df["close"], short).values
    ma_l = MA(df["close"], long).values

    # 检查最近lookback天是否有金叉
    for i in range(max(long, len(df) - lookback), len(df)):
        if i > 0 and ma_s[i] > ma_l[i] and ma_s[i-1] <= ma_l[i-1]:
            # 信号强度: 均线距离越大越好
            strength = min(100, (ma_s[i] / ma_l[i] - 1) * 1000)
            return True, strength, f"金叉(MA{short}/{long})"

    return False, 0, ""


def check_death_cross(df, short=5, long=20, lookback=3):
    """
    均线死叉筛选: 最近lookback天内是否出现死叉
    """
    if df is None or len(df) < long + lookback:
        return False, 0, "数据不足"

    ma_s = MA(df["close"], short).values
    ma_l = MA(df["close"], long).values

    for i in range(max(long, len(df) - lookback), len(df)):
        if i > 0 and ma_s[i] < ma_l[i] and ma_s[i-1] >= ma_l[i-1]:
            strength = min(100, (ma_l[i] / ma_s[i] - 1) * 1000)
            return True, strength, f"死叉(MA{short}/{long})"

    return False, 0, ""


def check_macd_golden(df, fast=12, slow=26, signal=9, lookback=5):
    """
    MACD金叉筛选: DIF上穿DEA
    """
    if df is None or len(df) < slow + signal + lookback:
        return False, 0, "数据不足"

    dif, dea, hist = MACD(df["close"], fast, slow, signal)
    dif_v = dif.values
    dea_v = dea.values

    for i in range(max(slow + signal, len(df) - lookback), len(df)):
        if i > 0 and dif_v[i] > dea_v[i] and dif_v[i-1] <= dea_v[i-1]:
            strength = min(100, abs(hist.values[i]) * 10)
            return True, strength, "MACD金叉"

    return False, 0, ""


def check_rsi_oversold_rebound(df, period=14, oversold=30, lookback=5):
    """
    RSI超卖反弹: RSI从超卖区(<oversold)回升
    """
    if df is None or len(df) < period + lookback:
        return False, 0, "数据不足"

    rsi = RSI(df["close"], period).values
    for i in range(max(period, len(df) - lookback), len(df)):
        if i > 0 and rsi[i] > oversold and rsi[i-1] <= oversold:
            strength = min(100, (oversold - rsi[i]) * 2 + 50)
            return True, strength, "RSI超卖反弹"

    return False, 0, ""


def check_bollinger_bounce(df, period=20, num_std=2, lookback=5):
    """
    布林带下轨反弹: 价格触及下轨后回升
    """
    if df is None or len(df) < period + lookback:
        return False, 0, "数据不足"

    upper, middle, lower = BOLL(df["close"], period, num_std)
    close = df["close"].values
    lower_v = lower.values

    for i in range(max(period, len(df) - lookback), len(df)):
        if i > 0 and close[i] > lower_v[i] and close[i-1] <= lower_v[i-1]:
            strength = min(100, (close[i] / lower_v[i] - 1) * 500)
            return True, strength, "布林下轨反弹"

    return False, 0, ""


def check_volume_surge(df, lookback=5, multiplier=2.0):
    """
    成交量放量: 成交量超过前20日均量的multiplier倍
    """
    if df is None or len(df) < 25:
        return False, 0, "数据不足"

    vol = df["volume"].values
    avg_vol = pd.Series(vol).rolling(20).mean().values

    for i in range(max(20, len(df) - lookback), len(df)):
        if avg_vol[i] > 0 and vol[i] > avg_vol[i] * multiplier:
            ratio = vol[i] / avg_vol[i]
            strength = min(100, (ratio - 1) * 30)
            return True, strength, f"放量{ratio:.1f}倍"

    return False, 0, ""


def check_price_trend(df, lookback=5, min_pct=3.0):
    """
    连续上涨筛选: 最近lookback天累计涨幅超过min_pct%
    """
    if df is None or len(df) < lookback + 1:
        return False, 0, "数据不足"

    close = df["close"].values
    pct = (close[-1] / close[-lookback-1] - 1) * 100
    if pct >= min_pct:
        return True, min(100, pct * 3), f"涨{pct:.1f}%"

    return False, 0, ""


def check_consecutive_up(df, days=3):
    """连续上涨N天"""
    if df is None or len(df) < days + 1:
        return False, 0, "数据不足"

    close = df["close"].values[-days-1:]
    up_count = sum(1 for i in range(1, len(close)) if close[i] > close[i-1])
    if up_count >= days:
        total_pct = (close[-1] / close[0] - 1) * 100
        return True, min(100, total_pct * 5), f"连涨{days}天({total_pct:.1f}%)"

    return False, 0, ""


# ─── 综合评分 ───────────────────────────────────────────────

def score_stock(df) -> dict:
    """
    对单只股票进行综合评分 (0-100)
    评分维度: 趋势、动量、成交量、波动率
    """
    if df is None or len(df) < 30:
        return {"score": 0, "details": "数据不足"}

    close = df["close"].values
    vol = df["volume"].values
    n = len(close)

    score = 50  # 基准分

    # 1. 趋势得分 (30分): 均线多头排列 + 价格在MA20之上
    ma5 = MA(df["close"], 5).values
    ma20 = MA(df["close"], 20).values
    ma60 = MA(df["close"], 60).values if len(df) >= 60 else None

    trend_score = 0
    if close[-1] > ma20[-1]:
        trend_score += 10
    if ma5[-1] > ma20[-1]:
        trend_score += 10  # 多头排列
    if ma60 is not None and close[-1] > ma60[-1]:
        trend_score += 10
    score += trend_score

    # 2. 动量得分 (25分): 近期涨幅 + RSI
    mom_score = 0
    if n > 10:
        ret_5d = (close[-1] / close[-6] - 1) * 100 if n > 5 else 0
        ret_10d = (close[-1] / close[-11] - 1) * 100 if n > 10 else 0
        if 0 < ret_5d < 20:
            mom_score += 8
        if 0 < ret_10d < 30:
            mom_score += 7
    rsi = RSI(df["close"], 14).values[-1]
    if 30 <= rsi <= 70:
        mom_score += 10
    elif rsi < 30:
        mom_score += 5  # 超卖可能反弹
    score += mom_score

    # 3. 成交量得分 (20分)
    vol_score = 0
    if n > 20:
        avg_vol = pd.Series(vol).rolling(20).mean().values
        if avg_vol[-1] > 0 and vol[-1] > avg_vol[-1]:
            vol_score += 10
        # 成交量趋势: 最近比之前放量
        if n > 40:
            avg_vol_20 = pd.Series(vol).rolling(20).mean().values
            if avg_vol_20[-1] > avg_vol_20[-20]:
                vol_score += 10
    score += vol_score

    # 4. 稳定性 (25分): 低波动 + MACD正向
    stability_score = 0
    if n > 20:
        daily_ret = pd.Series(close).pct_change().dropna()
        volatility = daily_ret.std() * 100
        if volatility < 3:
            stability_score += 10
        elif volatility < 5:
            stability_score += 5
    dif, dea, hist = MACD(df["close"])
    if hist.values[-1] > 0:
        stability_score += 10
    if dif.values[-1] > dea.values[-1]:
        stability_score += 5
    score += stability_score

    return {
        "score": min(100, max(0, score)),
        "趋势": trend_score,
        "动量": mom_score,
        "成交量": vol_score,
        "稳定性": stability_score,
    }


# ─── 选股调度引擎 ────────────────────────────────────────────

# 选股策略注册表
SCREENER_STRATEGIES = {
    "均线金叉": {
        "func": lambda df: check_golden_cross(df, 5, 20, 3),
        "desc": "MA5上穿MA20(近3天)",
    },
    "均线死叉🔻": {
        "func": lambda df: check_death_cross(df, 5, 20, 3),
        "desc": "MA5下穿MA20(近3天)",
    },
    "MACD金叉": {
        "func": lambda df: check_macd_golden(df, 12, 26, 9, 5),
        "desc": "DIF上穿DEA(近5天)",
    },
    "RSI超卖反弹": {
        "func": lambda df: check_rsi_oversold_rebound(df, 14, 30, 5),
        "desc": "RSI从30以下回升",
    },
    "布林下轨反弹": {
        "func": lambda df: check_bollinger_bounce(df, 20, 2, 5),
        "desc": "价格触及下轨后回升",
    },
    "成交量放量": {
        "func": lambda df: check_volume_surge(df, 5, 2.0),
        "desc": "量>20日均量2倍",
    },
    "连续上涨": {
        "func": lambda df: check_consecutive_up(df, 3),
        "desc": "连续3天上涨",
    },
}


def run_screener(
    conditions: List[str] = None,
    price_min: float = 0,
    price_max: float = 9999,
    max_stocks: int = 50,
    sort_by: str = "综合评分",
    max_workers: int = 6,
    progress_callback: Callable = None,
    lookback_days: int = 180,
) -> pd.DataFrame:
    """
    在精选 500 基础池中执行信号选股。

    参数:
      conditions: 筛选条件列表, 如 ["均线金叉", "MACD金叉"]
                  为None则使用所有条件
      price_min:  最低股价
      price_max:  最高股价
      max_stocks: 最多返回股票数
      sort_by:    排序方式: "综合评分" / "信号强度"
      max_workers: 并行线程数
      progress_callback: 进度回调 function(current, total)
      lookback_days: 最近多少个自然日K线数据参与扫描

    返回: DataFrame
    """
    if conditions is None:
        conditions = [k for k in SCREENER_STRATEGIES if not k.endswith("🔻")]

    # 中证 A500 为主的精选基础池，避免对 5,000+ 只标的盲扫。
    all_stocks = get_value_stock_pool(limit=500)
    if all_stocks is None or len(all_stocks) == 0:
        return pd.DataFrame()

    codes = all_stocks["code"].astype(str).str.zfill(6).tolist()
    name_map = dict(zip(codes, all_stocks["name"].astype(str)))
    universe_attrs = dict(all_stocks.attrs)
    total = len(codes)
    results = []

    # 获取最近一段时间数据，既保证信号可靠，又避免过慢
    lookback_days = int(max(60, min(365, lookback_days)))
    end = pd.Timestamp("today").strftime("%Y-%m-%d")
    start = (pd.Timestamp("today") - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    def _scan_one(code):
        try:
            df = _fetch_kline(code, start, end, "qfq")
            if df is None or len(df) < 30:
                return None

            # 价格过滤
            current_price = float(df["close"].iloc[-1])
            if current_price < price_min or current_price > price_max:
                return None

            # 检查各条件
            matched = []
            total_strength = 0
            for cond in conditions:
                if cond in SCREENER_STRATEGIES:
                    ok, s, desc = SCREENER_STRATEGIES[cond]["func"](df)
                    if ok:
                        matched.append(desc)
                        total_strength += s

            if not matched:
                return None

            # 综合评分
            scoring = score_stock(df)
            comp_score = scoring["score"]

            # 获取股票名称
            name = name_map.get(code, "")

            return {
                "代码": code,
                "名称": name,
                "现价": round(current_price, 2),
                "信号": " | ".join(matched),
                "信号强度": round(total_strength / len(matched), 1) if matched else 0,
                "综合评分": comp_score,
                "趋势": scoring.get("趋势", 0),
                "动量": scoring.get("动量", 0),
                "成交量分": scoring.get("成交量", 0),
                "稳定性": scoring.get("稳定性", 0),
            }
        except Exception:
            return None

    # 并行扫描
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_scan_one, code): code for code in codes}
        for future in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done, total)
            result = future.result()
            if result is not None:
                results.append(result)

    if not results:
        return pd.DataFrame()

    df_result = pd.DataFrame(results)

    # 排序
    sort_col = "综合评分" if sort_by == "综合评分" else "信号强度"
    df_result = df_result.sort_values(sort_col, ascending=False).head(max_stocks)
    df_result = df_result.reset_index(drop=True)
    df_result.index = df_result.index + 1  # 序号从1开始
    df_result.index.name = "序号"
    df_result.attrs.update(universe_attrs)

    return df_result


def run_screener_simple(condition: str = "均线金叉", top_n: int = 30) -> pd.DataFrame:
    """
    快速选股 — 仅用一个条件筛选

    参数:
      condition: 筛选条件
      top_n:     返回前N只

    返回: DataFrame
    """
    return run_screener(
        conditions=[condition],
        max_stocks=top_n,
    )


# ─── 离线测试选股 ───────────────────────────────────────

def run_screener_on_test_data(
    conditions: List[str] = None,
    n_stocks: int = 20,
    days: int = 200,
    max_stocks: int = 30,
    sort_by: str = "综合评分",
    progress_callback: Callable = None,
) -> pd.DataFrame:
    """
    使用模拟数据测试选股功能

    参数:
      conditions: 筛选条件
      n_stocks:   生成多少只模拟股票
      days:       每只股票多少天数据
      max_stocks: 最多返回多少只
      sort_by:    排序方式
      progress_callback: 进度回调

    返回: DataFrame
    """
    from ..data_fetcher import get_test_data

    if conditions is None:
        conditions = [k for k in SCREENER_STRATEGIES.keys() if not k.endswith("🔻")]

    stock_names = [
        "测试-A股1号", "测试-科技龙头", "测试-医药生物", "测试-新能源",
        "测试-消费蓝筹", "测试-金融地产", "测试-半导体", "测试-军工航天",
        "测试-人工智能", "测试-通信5G", "测试-新能源汽车", "测试-光伏产业",
        "测试-白酒食品", "测试-家电制造", "测试-医疗器械", "测试-芯片设计",
        "测试-云计算", "测试-机器人", "测试-储能", "测试-量化精选",
    ]
    results = []
    total = min(n_stocks, len(stock_names))

    for i in range(total):
        # 每只股票不同参数，产生不同走势
        seed = 42 + i * 7
        vol = 0.015 + (i % 5) * 0.005
        start_p = 30.0 + i * 5

        df = get_test_data(days=days, volatility=vol, start_price=start_p, code=f"T{i:04d}", seed=seed)

        code = f"T{i:04d}"
        name = stock_names[i]

        # 检测各种条件 (全数据范围, 不限最后几天)
        matched = []
        total_strength = 0
        for cond in conditions:
            # 扩展lookback来检测全数据中出现的信号
            _ok, _s, _desc = False, 0, ""
            if cond in SCREENER_STRATEGIES:
                orig_func = SCREENER_STRATEGIES[cond]["func"]
                # 尝试多次增加lookback
                for lb in [5, 10, 20, 50, 100, 999]:
                    params = {}
                    # 重新创建带更大lookback的检测函数
                    func = orig_func.__wrapped__ if hasattr(orig_func, '__wrapped__') else orig_func
                    try:
                        import inspect
                        sig = inspect.signature(check_golden_cross)
                        if 'lookback' in sig.parameters:
                            _ok, _s, _desc = check_golden_cross(df, 5, 20, lb)
                        else:
                            _ok, _s, _desc = orig_func(df)
                    except:
                        _ok, _s, _desc = orig_func(df)
                    if _ok:
                        break
                if _ok:
                    matched.append(_desc)
                    total_strength += _s
                else:
                    # 直接用原始函数再试一次(可能不是lookback类函数)
                    try:
                        _ok2, _s2, _desc2 = orig_func(df)
                        if _ok2:
                            matched.append(_desc2)
                            total_strength += _s2
                    except:
                        pass

        # 评分
        scoring = score_stock(df)
        comp_score = scoring["score"]
        current_price = round(float(df["close"].iloc[-1]), 2)

        results.append({
            "代码": code,
            "名称": name,
            "现价": current_price,
            "信号": " | ".join(matched) if matched else "无信号",
            "信号强度": round(total_strength / len(matched), 1) if matched else 0,
            "综合评分": comp_score,
            "趋势": scoring.get("趋势", 0),
            "动量": scoring.get("动量", 0),
            "成交量分": scoring.get("成交量", 0),
            "稳定性": scoring.get("稳定性", 0),
        })

        if progress_callback:
            progress_callback(i + 1, total)

    if not results:
        return pd.DataFrame()

    df_result = pd.DataFrame(results)
    sort_col = "综合评分" if sort_by == "综合评分" else "信号强度"
    df_result = df_result.sort_values(sort_col, ascending=False).head(max_stocks)
    df_result = df_result.reset_index(drop=True)
    df_result.index = df_result.index + 1
    df_result.index.name = "序号"
    return df_result

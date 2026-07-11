"""
回测引擎 - 模拟A股交易规则

A股特色规则:
  - T+1: 当日买入次日才能卖出
  - 涨跌停: 普通股10%, ST股5%, 创业板/科创板20%
  - 手续费: 佣金(默认万2.5, 最低5元), 印花税(卖出千1), 过户费(沪市万0.1)
  - 交易单位: 100股一手
  - 滑点: 可配置

支持:
  - 单股票回测
  - 组合回测(等权配置)
  - 基准对比(沪深300)
"""

import numpy as np
import pandas as pd


class BacktestEngine:
    """A股回测引擎 - 支持单股票和组合回测"""

    def __init__(
        self,
        initial_cash=1_000_000,
        commission_rate=0.00025,
        min_commission=5.0,
        stamp_tax=0.001,
        transfer_fee=0.00001,
        slippage=0.001,
        limit_pct=0.10,
    ):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax = stamp_tax          # 印花税: 卖出时收取
        self.transfer_fee = transfer_fee    # 过户费: 双向
        self.slippage = slippage            # 滑点: 0.1%
        self.limit_pct = limit_pct          # 涨跌停幅度

        self.position = 0        # 当前持仓股数
        self.buy_price = 0       # 持仓成本价
        self.buy_date = None     # 买入日期(用于T+1)
        self.trades = []         # 交易记录
        self.equity_curve = []   # 每日权益

    def _calc_cost(self, amount, is_buy):
        """计算交易成本"""
        commission = max(amount * self.commission_rate, self.min_commission)
        stamp = 0 if is_buy else amount * self.stamp_tax
        transfer = amount * self.transfer_fee
        return commission + stamp + transfer

    def _is_limit_up(self, prev_close, price):
        """判断是否涨停(无法买入)"""
        if prev_close <= 0:
            return False
        return price >= prev_close * (1 + self.limit_pct) - 0.001

    def _is_limit_down(self, prev_close, price):
        """判断是否跌停(无法卖出)"""
        if prev_close <= 0:
            return False
        return price <= prev_close * (1 - self.limit_pct) + 0.001

    def run(self, df):
        """
        执行单股票回测

        参数:
          df: 带有signal列的DataFrame, 必须包含 date, open, close, high, low

        返回:
          equity_df: 每日权益曲线 DataFrame
          trades_df: 交易明细 DataFrame
        """
        df = df.reset_index(drop=True).copy()
        n = len(df)

        for i in range(n):
            row = df.iloc[i]
            date = row["date"]
            close = row["close"]
            prev_close = df.iloc[i - 1]["close"] if i > 0 else close

            # --- 信号执行 ---
            signal = int(row.get("signal", 0))

            # 买入信号
            if signal == 1 and self.position == 0:
                if self._is_limit_up(prev_close, close):
                    pass
                else:
                    exec_price = close * (1 + self.slippage)
                    max_shares = int(self.cash / (exec_price * 100)) * 100
                    if max_shares >= 100:
                        amount = max_shares * exec_price
                        cost = self._calc_cost(amount, is_buy=True)
                        self.cash -= (amount + cost)
                        self.position = max_shares
                        self.buy_price = exec_price
                        self.buy_date = date
                        self.trades.append({
                            "date": date, "action": "BUY",
                            "price": round(exec_price, 2),
                            "shares": max_shares,
                            "amount": round(amount, 2),
                            "cost": round(cost, 2),
                            "cash": round(self.cash, 2),
                        })

            # 卖出信号
            elif signal == -1 and self.position > 0:
                if self.buy_date == date:
                    pass  # T+1
                elif self._is_limit_down(prev_close, close):
                    pass
                else:
                    exec_price = close * (1 - self.slippage)
                    shares = self.position
                    amount = shares * exec_price
                    cost = self._calc_cost(amount, is_buy=False)
                    self.cash += (amount - cost)
                    pnl = (exec_price - self.buy_price) * shares - \
                          self._calc_cost(self.buy_price * shares, True) - cost
                    self.trades.append({
                        "date": date, "action": "SELL",
                        "price": round(exec_price, 2),
                        "shares": shares,
                        "amount": round(amount, 2),
                        "cost": round(cost, 2),
                        "cash": round(self.cash, 2),
                        "pnl": round(pnl, 2),
                    })
                    self.position = 0
                    self.buy_price = 0
                    self.buy_date = None

            # --- 记录每日权益 ---
            equity = self.cash + self.position * close
            self.equity_curve.append({
                "date": date,
                "close": close,
                "cash": round(self.cash, 2),
                "position": self.position,
                "equity": round(equity, 2),
            })

        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades)
        return equity_df, trades_df


def run_portfolio_backtest(
    data_dict: dict,
    strategy,
    initial_cash=1_000_000,
    commission_rate=0.00025,
    stamp_tax=0.001,
    slippage=0.001,
    limit_pct=0.10,
    allocation="equal",
) -> tuple:
    """
    组合回测: 同时回测多只股票, 等权或按比例分配资金

    参数:
      data_dict:    {code: DataFrame} 各股票日K数据
      strategy:     策略实例
      initial_cash: 初始总资金
      allocation:   "equal" 等权 / dict(code -> 比例)

    返回:
      combined_equity_df: 组合每日权益
      all_trades:         所有交易明细
      individual_results: 各股票独立回测结果
    """
    import copy
    from . import BacktestEngine

    codes = list(data_dict.keys())
    n_stocks = len(codes)

    if n_stocks == 0:
        return pd.DataFrame(), pd.DataFrame(), {}

    # 分配资金
    if allocation == "equal":
        per_cash = initial_cash / n_stocks
        alloc = {c: per_cash for c in codes}
    elif isinstance(allocation, dict):
        alloc = allocation
    else:
        per_cash = initial_cash / n_stocks
        alloc = {c: per_cash for c in codes}

    individual_results = {}
    all_trades_list = []

    for code in codes:
        df = data_dict[code].copy()
        df = strategy.generate_signals(df)

        engine = BacktestEngine(
            initial_cash=alloc.get(code, initial_cash / n_stocks),
            commission_rate=commission_rate,
            stamp_tax=stamp_tax,
            slippage=slippage,
            limit_pct=limit_pct,
        )
        eq_df, tr_df = engine.run(df)
        individual_results[code] = {
            "equity": eq_df,
            "trades": tr_df,
            "engine": engine,
        }
        if tr_df is not None and len(tr_df) > 0:
            tr_df["code"] = code
            all_trades_list.append(tr_df)

    # 合并权益曲线: 按日期对齐各股票权益求和
    combined = None
    for code, res in individual_results.items():
        eq = res["equity"][["date", "equity"]].copy()
        eq = eq.rename(columns={"equity": f"equity_{code}"})
        if combined is None:
            combined = eq
        else:
            combined = pd.merge(combined, eq, on="date", how="outer")

    if combined is None:
        return pd.DataFrame(), pd.DataFrame(), individual_results

    combined = combined.sort_values("date").ffill().fillna(0)
    eq_cols = [c for c in combined.columns if c.startswith("equity_")]
    combined["equity"] = combined[eq_cols].sum(axis=1)

    # 组合资金曲线
    result_equity = combined[["date", "equity"]].copy()

    # 合并交易记录
    all_trades = pd.concat(all_trades_list, ignore_index=True) if all_trades_list else pd.DataFrame()

    return result_equity, all_trades, individual_results

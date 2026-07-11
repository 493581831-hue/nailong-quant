"""
绩效分析模块

计算回测的核心绩效指标:
  - 总收益率 / 年化收益率
  - 夏普比率 / 索提诺比率 / 卡玛比率
  - 最大回撤 / 最大回撤持续天数
  - 胜率 / 盈亏比 / 平均持仓天数
  - 交易频次 / 连续盈亏
  - 基准对比(沪深300)
"""

import numpy as np
import pandas as pd


def calc_performance(equity_df, trades_df, initial_cash=1_000_000, benchmark_ret=None):
    """
    计算回测绩效指标

    参数:
      equity_df:   回测引擎返回的每日权益DataFrame
      trades_df:   回测引擎返回的交易明细DataFrame
      initial_cash: 初始资金
      benchmark_ret: 基准日收益率序列(可选), 用于alpha/beta计算

    返回dict
    """
    if equity_df is None or len(equity_df) == 0:
        return {}

    equity = equity_df["equity"].values
    dates = equity_df["date"].values
    n_days = len(equity)
    n_years = n_days / 252

    # --- 收益率 ---
    total_return = (equity[-1] / initial_cash - 1) * 100
    annual_return = ((equity[-1] / initial_cash) ** (1 / max(n_years, 0.01)) - 1) * 100

    # --- 日收益率 ---
    daily_returns = pd.Series(equity).pct_change().dropna()

    # --- 夏普比率 (无风险利率2.5%) ---
    rf_daily = 0.025 / 252
    if daily_returns.std() > 0:
        sharpe = (daily_returns.mean() - rf_daily) / daily_returns.std() * np.sqrt(252)
    else:
        sharpe = 0.0

    # --- 索提诺比率 ---
    downside = daily_returns[daily_returns < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino = (daily_returns.mean() - rf_daily) / downside.std() * np.sqrt(252)
    else:
        sortino = 0.0

    # --- 最大回撤 ---
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = drawdown.min() * 100

    # 最大回撤持续天数
    dd_duration = 0
    cur_dd = 0
    for dd in drawdown:
        if dd < 0:
            cur_dd += 1
            dd_duration = max(dd_duration, cur_dd)
        else:
            cur_dd = 0

    # --- 卡玛比率 (Calmar Ratio) ---
    calmar = abs(annual_return / max_drawdown) if max_drawdown != 0 else 0

    # --- 交易统计 ---
    n_trades = 0
    win_count = 0
    loss_count = 0
    total_profit = 0.0
    total_loss = 0.0
    hold_days_list = []
    pnl_list = []  # 连续盈亏用

    if trades_df is not None and len(trades_df) > 0:
        trades = trades_df.to_dict("records")
        i = 0
        while i < len(trades) - 1:
            if trades[i]["action"] == "BUY" and i + 1 < len(trades) and trades[i + 1]["action"] == "SELL":
                n_trades += 1
                pnl = trades[i + 1].get("pnl", 0)
                pnl_list.append(pnl)
                if pnl > 0:
                    win_count += 1
                    total_profit += pnl
                else:
                    loss_count += 1
                    total_loss += abs(pnl)
                try:
                    buy_date = pd.to_datetime(trades[i]["date"])
                    sell_date = pd.to_datetime(trades[i + 1]["date"])
                    hold_days_list.append((sell_date - buy_date).days)
                except Exception:
                    pass
                i += 2
            else:
                i += 1

    win_rate = (win_count / n_trades * 100) if n_trades > 0 else 0
    avg_profit = (total_profit / win_count) if win_count > 0 else 0
    avg_loss = (total_loss / loss_count) if loss_count > 0 else 0
    profit_loss_ratio = (avg_profit / avg_loss) if avg_loss > 0 else 0
    avg_hold_days = (np.mean(hold_days_list) if hold_days_list else 0)
    avg_pnl_per_trade = (np.mean(pnl_list) if pnl_list else 0)

    # 连续盈利/亏损
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    cur_wins = 0
    cur_losses = 0
    for pnl in pnl_list:
        if pnl > 0:
            cur_wins += 1
            cur_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, cur_wins)
        elif pnl < 0:
            cur_losses += 1
            cur_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, cur_losses)

    # --- Alpha / Beta (如果提供了benchmark) ---
    alpha = None
    beta = None
    if benchmark_ret is not None and len(benchmark_ret) > 0:
        strat_ret = daily_returns.values
        bench_ret = benchmark_ret.values[:len(strat_ret)]
        if len(bench_ret) >= len(strat_ret):
            bench_ret = bench_ret[:len(strat_ret)]
            if np.std(bench_ret) > 0:
                beta = np.cov(strat_ret, bench_ret)[0, 1] / np.var(bench_ret)
                alpha = (strat_ret.mean() - rf_daily - beta * (bench_ret.mean() - rf_daily)) * 252 * 100

    result = {
        "初始资金": f"¥{initial_cash:,.0f}",
        "最终资产": f"¥{equity[-1]:,.0f}",
        "总收益率": f"{total_return:.2f}%",
        "年化收益率": f"{annual_return:.2f}%",
        "夏普比率": f"{sharpe:.2f}",
        "索提诺比率": f"{sortino:.2f}",
        "卡玛比率": f"{calmar:.2f}",
        "最大回撤": f"{max_drawdown:.2f}%",
        "回撤持续天数": f"{dd_duration}天",
        "交易次数": f"{n_trades}次",
        "盈利次数": f"{win_count}次",
        "亏损次数": f"{loss_count}次",
        "胜率": f"{win_rate:.1f}%",
        "盈亏比": f"{profit_loss_ratio:.2f}",
        "平均盈利率": f"¥{avg_profit:,.0f}" if win_count > 0 else "-",
        "平均亏损率": f"¥{avg_loss:,.0f}" if loss_count > 0 else "-",
        "平均单笔盈亏": f"¥{avg_pnl_per_trade:,.0f}",
        "平均持仓天数": f"{avg_hold_days:.1f}天",
        "最大连续盈利": f"{max_consecutive_wins}次",
        "最大连续亏损": f"{max_consecutive_losses}次",
        "日均收益率": f"{daily_returns.mean()*100:.4f}%",
        "日收益率标准差": f"{daily_returns.std()*100:.4f}%",
    }

    if alpha is not None:
        result["Alpha(年化)"] = f"{alpha:.2f}%"
    if beta is not None:
        result["Beta"] = f"{beta:.2f}"

    return result


def calc_drawdown_series(equity_df):
    """计算回撤序列, 用于绘图"""
    equity = equity_df["equity"].values
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak * 100
    result = equity_df[["date"]].copy()
    result["drawdown"] = drawdown
    return result


def monthly_returns(equity_df) -> pd.DataFrame:
    """计算月度收益率热力图数据"""
    df = equity_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["return"] = df["equity"].pct_change()

    monthly = df.groupby(["year", "month"])["return"].apply(
        lambda x: (1 + x).prod() - 1
    ).reset_index()
    monthly["return_pct"] = monthly["return"] * 100
    pivot = monthly.pivot(index="year", columns="month", values="return_pct")
    pivot = pivot.round(2)
    return pivot.rename(columns={
        1: "1月", 2: "2月", 3: "3月", 4: "4月", 5: "5月", 6: "6月",
        7: "7月", 8: "8月", 9: "9月", 10: "10月", 11: "11月", 12: "12月",
    })

"""
可视化模块 - 基于 Plotly（机构研究报告风格）
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

PAPER_BG = "#FFFFFF"
PLOT_BG = "#FFFFFF"
GRID = "rgba(23,40,57,0.10)"
GRID_SOFT = "rgba(23,40,57,0.055)"
INK = "#172839"
MUTED = "#6E7B87"
BRONZE = "#B79A62"
GOLD = "#C7AC78"
BLUE = "#163A5A"
TEAL = "#1B6B59"
RED = "#9F3D3D"
OLIVE = "#66734B"
PURPLE = "#66577A"


def _base_layout(fig, title=None, height=420, x_title="日期", y_title=""):
    fig.update_layout(
        template=None,
        title=dict(text=title or "", x=0.0, xanchor="left", font=dict(size=19, color=INK, family="Iowan Old Style, Songti SC, Georgia, serif")),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        height=height,
        hovermode="x unified",
        margin=dict(l=56, r=28, t=64, b=42),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            bgcolor="rgba(255,255,255,0)", font=dict(size=11, color=MUTED)
        ),
        font=dict(family="Inter, PingFang SC, Microsoft YaHei, Arial", size=12, color=INK),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="rgba(23,40,57,.18)", font=dict(color=INK)),
    )
    fig.update_xaxes(
        title_text=x_title,
        showgrid=True,
        gridcolor=GRID_SOFT,
        linecolor=GRID,
        tickfont=dict(color=MUTED),
        title_font=dict(size=12, color=MUTED),
        zeroline=False,
        showline=True,
        ticks="outside",
    )
    fig.update_yaxes(
        title_text=y_title,
        showgrid=True,
        gridcolor=GRID,
        linecolor=GRID,
        tickfont=dict(color=MUTED),
        title_font=dict(size=12, color=MUTED),
        zeroline=False,
        showline=True,
        ticks="outside",
    )
    return fig


def style_figure(fig, title=None, height=None, x_title=None, y_title=None):
    if height is None:
        height = fig.layout.height or 420
    _base_layout(fig, title=title or fig.layout.title.text if fig.layout.title else "", height=height,
                 x_title=x_title or (fig.layout.xaxis.title.text if fig.layout.xaxis.title else "日期"),
                 y_title=y_title or (fig.layout.yaxis.title.text if fig.layout.yaxis.title else ""))
    return fig


def plot_kline_with_signals(df, strategy_name="策略", show_ma=True):
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.08,
        subplot_titles=(f"{strategy_name} · 价格与交易信号", "成交量"),
    )
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="K线",
        increasing_line_color=RED, decreasing_line_color=TEAL,
        increasing_fillcolor="rgba(180,84,76,.85)", decreasing_fillcolor="rgba(47,125,115,.85)",
    ), row=1, col=1)

    ma_cols = {}
    if "ma_short" in df.columns:
        ma_cols["ma_short"] = GOLD
    if "ma_long" in df.columns:
        ma_cols["ma_long"] = BLUE
    for col, color in ma_cols.items():
        fig.add_trace(go.Scatter(
            x=df["date"], y=df[col], mode="lines", name=col.upper(),
            line=dict(color=color, width=2),
        ), row=1, col=1)

    extra_lines = {"rsi": ("RSI", PURPLE), "boll_upper": ("上轨", OLIVE),
                   "boll_mid": ("中轨", GOLD), "boll_lower": ("下轨", OLIVE)}
    for col, (label, color) in extra_lines.items():
        if col in df.columns and col not in ma_cols:
            fig.add_trace(go.Scatter(
                x=df["date"], y=df[col], mode="lines", name=label,
                line=dict(color=color, width=1.4, dash="dot"), opacity=0.8,
            ), row=1, col=1)

    buys = df[df["signal"] == 1]
    if len(buys) > 0:
        fig.add_trace(go.Scatter(
            x=buys["date"], y=buys["low"] * 0.985, mode="markers",
            marker=dict(symbol="triangle-up", size=12, color=TEAL, line=dict(color="#FFFFFF", width=1.2)),
            name="买入", text="买入",
        ), row=1, col=1)

    sells = df[df["signal"] == -1]
    if len(sells) > 0:
        fig.add_trace(go.Scatter(
            x=sells["date"], y=sells["high"] * 1.015, mode="markers",
            marker=dict(symbol="triangle-down", size=12, color=RED, line=dict(color="#FFFFFF", width=1.2)),
            name="卖出", text="卖出",
        ), row=1, col=1)

    if "volume" in df.columns:
        colors = np.where(df["close"] >= df["open"], RED, TEAL)
        fig.add_trace(go.Bar(
            x=df["date"], y=df["volume"], name="成交量",
            marker_color=colors, showlegend=False, opacity=0.85,
        ), row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False)
    _base_layout(fig, title=f"{strategy_name} · K线与买卖信号", height=620, x_title="日期", y_title="价格")
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1, gridcolor=GRID_SOFT)
    return fig


def plot_equity_curve(equity_df, benchmark_df=None, initial_cash=1_000_000, title="资金曲线"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df["date"], y=equity_df["equity"], mode="lines", name="策略收益",
        line=dict(color=BLUE, width=2.6), fill="tozeroy", fillcolor="rgba(53,106,149,0.10)",
    ))
    if benchmark_df is not None and len(benchmark_df) > 0:
        bench = benchmark_df.copy()
        bench = bench[bench["date"] >= equity_df["date"].min()]
        bench = bench[bench["date"] <= equity_df["date"].max()]
        if len(bench) > 0:
            bench_start = bench["close"].iloc[0]
            bench_equity = initial_cash * bench["close"].values / bench_start
            fig.add_trace(go.Scatter(
                x=bench["date"], y=bench_equity, mode="lines", name="沪深300",
                line=dict(color=BRONZE, width=2, dash="dash"),
            ))
    fig.add_hline(y=initial_cash, line_dash="dot", line_color="rgba(23,40,57,.38)", annotation_text=f"初始 ¥{initial_cash/10000:.0f}万", annotation_position="top left")
    _base_layout(fig, title=title, height=420, x_title="日期", y_title="资产(¥)")
    return fig


def plot_drawdown(drawdown_df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown_df["date"], y=drawdown_df["drawdown"], mode="lines", name="回撤",
        line=dict(color=RED, width=2), fill="tozeroy", fillcolor="rgba(180,84,76,0.18)",
    ))
    _base_layout(fig, title="回撤曲线", height=300, x_title="日期", y_title="回撤(%)")
    return fig


def plot_trade_pnl(trades_df):
    if trades_df is None or len(trades_df) == 0:
        return None
    sells = trades_df[trades_df["action"] == "SELL"].copy()
    if len(sells) == 0:
        return None
    if "code" in sells.columns:
        sells["label"] = sells["code"] + " " + sells["date"].astype(str)
    else:
        sells["label"] = sells["date"].astype(str)
    colors = np.where(sells["pnl"] > 0, TEAL, RED)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sells["label"], y=sells["pnl"], marker_color=colors, name="单笔盈亏",
        text=sells["pnl"].round(0).astype(int), textposition="outside",
    ))
    _base_layout(fig, title="每笔交易盈亏", height=360, x_title="交易", y_title="盈亏(¥)")
    fig.update_layout(margin=dict(l=56, r=28, t=64, b=92))
    fig.update_xaxes(tickangle=-42)
    return fig


def plot_portfolio_comparison(individual_results: dict, combined_equity: pd.DataFrame, initial_cash=1_000_000):
    fig = go.Figure()
    colors = [BLUE, RED, TEAL, BRONZE, PURPLE, OLIVE, "#A96A54", "#7B8794", "#4F7F64", "#46698C"]
    fig.add_trace(go.Scatter(
        x=combined_equity["date"], y=combined_equity["equity"], mode="lines", name="组合收益",
        line=dict(color=BRONZE, width=3),
    ))
    for idx, (code, res) in enumerate(individual_results.items()):
        eq = res["equity"]
        color = colors[idx % len(colors)]
        fig.add_trace(go.Scatter(
            x=eq["date"], y=eq["equity"], mode="lines", name=code,
            line=dict(color=color, width=1.6, dash="dot"), opacity=0.78,
        ))
    fig.add_hline(y=initial_cash, line_dash="dot", line_color="rgba(23,40,57,.38)")
    _base_layout(fig, title="组合回测对比", height=460, x_title="日期", y_title="资产(¥)")
    return fig


def plot_monthly_heatmap(monthly_df: pd.DataFrame):
    if monthly_df is None or monthly_df.empty:
        return None
    years = monthly_df.index.tolist()
    months = [f"{m}月" for m in range(1, 13)]
    months_avail = [c for c in months if c in monthly_df.columns]
    z = monthly_df[months_avail].values
    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=months_avail,
        y=years,
        text=[[f"{v:.1f}%" if not pd.isna(v) else "" for v in row] for row in z],
        texttemplate="%{text}",
        textfont=dict(size=11, color=INK),
        colorscale=[[0, "#9F3D3D"], [0.5, "#F2F1ED"], [1, "#1B6B59"]],
        zmid=0, zmin=-15, zmax=15,
        hovertemplate="%{y}年 %{x}<br>收益率: %{z:.2f}%<extra></extra>",
        colorbar=dict(title="%", thickness=12, tickfont=dict(color=MUTED), titlefont=dict(color=MUTED))
    ))
    _base_layout(fig, title="月度收益率热力图", height=320 + len(years) * 28, x_title="月份", y_title="年份")
    return fig

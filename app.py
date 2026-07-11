"""
大A股量化交易系统 v2.0 - Streamlit Web界面

运行方式:
  streamlit run app.py
"""

import sys
import os
import time
import json
import base64
from html import escape
from textwrap import dedent
import pandas as pd
import numpy as np
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant_a.data_fetcher import get_stock_list, get_daily_data, get_batch_data, get_index_data
from quant_a.strategies import STRATEGY_REGISTRY, MovingAverageCross
from quant_a.backtest import BacktestEngine, run_portfolio_backtest
from quant_a.analysis import calc_performance, calc_drawdown_series, monthly_returns
from quant_a.visualization import (
    plot_kline_with_signals, plot_equity_curve, plot_drawdown, plot_trade_pnl,
    plot_portfolio_comparison, plot_monthly_heatmap, style_figure,
)
from quant_a.broker import SimBroker, EasytraderBroker, LiveTradingEngine
from quant_a.screener import run_screener, SCREENER_STRATEGIES
from quant_a.data_fetcher import get_daily_data_efinance
from quant_a.research_workspace import ResearchWorkspace
from quant_a.cta import NailongCTA, run_cta_backtest
from quant_a.alpha2_single import discover_single_asset_alphas, backtest_single_asset_alpha


def asset_data_uri(relative_path: str) -> str:
    """Embed local visual assets so Streamlit can render them inside custom HTML."""
    asset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
    with open(asset_path, "rb") as asset_file:
        encoded = base64.b64encode(asset_file.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


NAILONG_IMAGE_URI = asset_data_uri("assets/nailong.png")
PROFILE_IMAGE_URI = asset_data_uri("assets/profile.png")
NAILONG_STICKERS = {
    "backtest": asset_data_uri("assets/stickers_hd/backtest.png"),
    "portfolio": asset_data_uri("assets/stickers_hd/portfolio.png"),
    "screener": asset_data_uri("assets/stickers_hd/screener.png"),
    "paper": asset_data_uri("assets/stickers_hd/paper.png"),
    "engine": asset_data_uri("assets/stickers_hd/engine.png"),
    "guide": asset_data_uri("assets/stickers_hd/guide.png"),
    "about": asset_data_uri("assets/stickers_hd/about.png"),
    "cta": asset_data_uri("assets/stickers_hd/cta.png"),
}

# === 页面配置 ===
st.set_page_config(
    page_title="Nailong Capital | Quantitative Research",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# === 自定义样式 ===
st.markdown("""
<style>
    
    /* ═══════════════════════════════════════════════════════
       大A量化交易系统 — Premium Design v3.0
       风格: 高级深色 · 玻璃拟态 · 精致极简
       配色: 深海蓝 + 渐变紫 + 暖金
       ═══════════════════════════════════════════════════════ */

    /* ── 基础 ── */
    /* ═══════════════════════════════════════════════════════════
       字体渲染增强 — Apple 设计风格 (系统原生)
       中文字体: PingFang SC (原生) → Hiragino Sans GB
       西文字体: -apple-system → Helvetica Neue
       等宽字体: SF Mono → Menlo
       ═══════════════════════════════════════════════════════════ */

    /* 全局字体平滑 — macOS 级 */
    * {
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        font-kerning: normal;
        text-rendering: optimizeLegibility;
    }
    
    /* ═══════════════════════════════════════════════════════════
       排版优化 — Apple HIG 设计语言
       层级: 标题 (H1-H6) → 正文 → 辅助文字
       原则: 字重节奏感 · 字号级数比 · 宽松字距
       ═══════════════════════════════════════════════════════════ */
    
    /* 正文 — 清晰 · 松弛 · 静谧 */
    body, p, .stMarkdown, li, span {
        font-weight: 400 !important;
        line-height: 1.85 !important;
        font-size: 0.9375rem !important;  /* 15px — Apple 标准正文 */
        letter-spacing: 0.022em !important;
        color: #d1d4e0 !important;
    }
    
    /* 标题 — 夸张字重对比，营造景深感 */
    h1 {
        font-weight: 700 !important;
        letter-spacing: -0.028em !important;
        line-height: 1.1 !important;
        font-size: 2.25rem !important;  /* 36px */
        margin-bottom: 0.15em !important;
        color: #f5f7fc !important;
    }
    h2 {
        font-weight: 650 !important;
        letter-spacing: -0.022em !important;
        line-height: 1.2 !important;
        font-size: 1.625rem !important;  /* 26px */
        color: #eceff6 !important;
        margin-bottom: 0.4em !important;
    }
    h3 {
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
        line-height: 1.25 !important;
        font-size: 1.25rem !important;  /* 20px */
        color: #e3e6f0 !important;
    }
    h4 {
        font-weight: 550 !important;
        letter-spacing: -0.01em !important;
        line-height: 1.3 !important;
        font-size: 1.0625rem !important;  /* 17px */
        color: #dce0ec !important;
    }
    h5, h6 {
        font-weight: 500 !important;
        letter-spacing: -0.006em !important;
        color: #d5d9e8 !important;
    }
    
    /* 小字/标注 */
    .stCaption, caption, .caption-text {
        font-size: 0.8125rem !important;
        font-weight: 450 !important;
        letter-spacing: 0.03em !important;
        color: #888ba0 !important;
    }
    
    /* 表单输入 — 更清晰的字体 */
    input, textarea, select, .stTextInput input, .stSelectbox div, .stMultiSelect div {
        font-weight: 450 !important;
        letter-spacing: 0.01em !important;
    }
    
    /* 数字/数据 — 等宽字体 */
    .data-value, .metric-value, .stMetricValue, .numeric-display {
        font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }

    html, body, [class*="css"], .stApp, .stMarkdown, .element-container, .stText, p, span, div:not([class*="st-"]):not([class*="metric"]) {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
        color: #e4e6f0;
    }

    .stApp {
        background: #07080d;
        background-image:
            radial-gradient(ellipse at 20% 50%, rgba(108, 92, 231, 0.05) 0%, transparent 60%),
            radial-gradient(ellipse at 80% 20%, rgba(0, 184, 216, 0.04) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 80%, rgba(118, 75, 162, 0.03) 0%, transparent 50%);
        background-attachment: fixed;
    }

    .main > div { background: transparent; }

    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1280px !important;
    }

    /* ── 侧边栏 ── */
    section[data-testid="stSidebar"] {
        background: rgba(10, 12, 24, 0.96) !important;
        border-right: 1px solid rgba(255,255,255,0.04) !important;
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] > div:first-child > div:first-child {
        padding: 1rem 0.6rem !important;
    }

    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding: 0.15rem 0.5rem;
        margin-bottom: 0.25rem;
    }
    .sidebar-logo {
        width: 34px; height: 34px;
        border-radius: 10px;
        background: linear-gradient(135deg, #6c5ce7, #a855f7);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        box-shadow: 0 4px 12px rgba(108,92,231,0.25);
    }
    .sidebar-title { display: flex; flex-direction: column; gap: 1px; }
    .sidebar-name { font-size: 0.95rem; font-weight: 700; color: #e4e6f0; letter-spacing: 0; line-height: 1.2; }
    .sidebar-version { font-size: 0.6rem; color: #6c5ce7; font-weight: 500; letter-spacing: 0.05em; }
    .sidebar-footer { font-size: 0.6rem; color: rgba(255,255,255,0.15); text-align: center; padding: 0 0.5rem; margin-top: 0.3rem; letter-spacing: 0.02em; }

    .nav-container {
        padding: 0.15rem 0;
    }

    /* 侧边栏按钮 — 纯文字导航 */
    section[data-testid="stSidebar"] .stButton button {
        background: transparent !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 0.75rem !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #6b7280 !important;
        text-align: left !important;
        transition: all 0.15s ease !important;
        box-shadow: none !important;
        width: 100% !important;
        position: relative !important;
        padding-left: 1rem !important;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: rgba(255,255,255,0.04) !important;
        color: #c4c6d0 !important;
    }
    /* 活跃状态 (primary) */
    section[data-testid="stSidebar"] .stButton button[kind="primary"] {
        background: rgba(108,92,231,0.12) !important;
        color: #c4c6d0 !important;
        font-weight: 600 !important;
        box-shadow: inset 3px 0 0 #6c5ce7 !important;
    }
    section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {
        background: rgba(108,92,231,0.15) !important;
        box-shadow: inset 3px 0 0 #a855f7 !important;
    }

    /* ── Metric 卡片 ── */
    div[data-testid="metric-container"] {
        background: rgba(255,255,255,0.03);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 0.8rem 1.1rem;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }
    div[data-testid="metric-container"]:hover {
        border-color: rgba(108,92,231,0.2);
        background: rgba(255,255,255,0.05);
        transform: translateY(-2px);
    }
    div[data-testid="metric-container"] label {
        font-size: 0.62rem !important;
        color: #636678 !important;
        font-weight: 600 !important;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        color: #e4e6f0 !important;
        letter-spacing: -0.03em;
        font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace !important;
    }
    /* Positive/negative delta colors */
    div[data-testid="metric-container"] [data-testid="stMetricDelta"] svg { display: none; }

    /* ── Stat 卡片 ── */
    .stat-card {
        background: rgba(255,255,255,0.03);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 0.9rem 1.2rem;
        margin-bottom: 0.8rem;
        font-size: 0.82rem;
        color: #8e92a8;
        line-height: 1.7;
    }
    .stat-card strong { color: #e4e6f0; font-weight: 600; }

    /* ── 信号颜色 ── */
    .signal-buy { color: #10b981; font-weight: 600; font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace; }
    .signal-sell { color: #ef4444; font-weight: 600; font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace; }
    .signal-hold { color: #4b5563; font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace; }

    /* ── 按钮 ── */
    .stButton button {
        border-radius: 10px !important;
        font-weight: 500 !important;
        font-size: 0.82rem !important;
        transition: all 0.2s ease !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        background: rgba(255,255,255,0.04) !important;
        color: #c4c6d0 !important;
        padding: 0.4rem 1.2rem !important;
        box-shadow: none !important;
    }
    .stButton button:hover {
        background: rgba(255,255,255,0.08) !important;
        border-color: rgba(255,255,255,0.12) !important;
        color: #e4e6f0 !important;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #6c5ce7, #a855f7) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 4px 14px rgba(108,92,231,0.25) !important;
    }
    .stButton button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(108,92,231,0.35) !important;
        transform: translateY(-1px) !important;
        background: linear-gradient(135deg, #7c6df7, #b855f7) !important;
    }

    /* ── 展开器 ── */
    div[data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,0.02) !important;
        backdrop-filter: blur(8px);
        overflow: hidden;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 600 !important;
        color: #c4c6d0 !important;
        padding: 0.6rem 1rem !important;
        font-size: 0.82rem;
    }

    /* ── 数据表格 ── */
    div[data-testid="stDataFrame"] {
        font-size: 0.75rem !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
    }
    div[data-testid="stDataFrame"] thead tr th {
        background: rgba(255,255,255,0.03) !important;
        font-size: 0.65rem !important;
        font-weight: 600 !important;
        color: #636678 !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 0.5rem 0.7rem !important;
        border-bottom: 1px solid rgba(255,255,255,0.06) !important;
    }
    div[data-testid="stDataFrame"] tbody tr {
        border-bottom: 1px solid rgba(255,255,255,0.03) !important;
    }
    div[data-testid="stDataFrame"] tbody tr:hover {
        background: rgba(108,92,231,0.04) !important;
    }
    div[data-testid="stDataFrame"] tbody td {
        padding: 0.35rem 0.7rem !important;
        color: #8e92a8 !important;
    }

    /* ── 输入框 ── */
    .stTextInput input, .stNumberInput input,
    .stSelectbox select, .stTextArea textarea {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 10px !important;
        color: #e4e6f0 !important;
        font-size: 0.82rem !important;
        padding: 0.35rem 0.7rem !important;
        transition: all 0.2s ease !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #6c5ce7 !important;
        box-shadow: 0 0 0 3px rgba(108,92,231,0.1) !important;
    }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {
        color: #4b5563 !important;
    }

    /* ── 滑块 ── */
    .stSlider > div > div > div {
        background: linear-gradient(90deg, #6c5ce7, #a855f7) !important;
        height: 3px !important;
    }
    .stSlider [role="slider"] {
        background: #6c5ce7 !important;
        border: 2px solid #a855f7 !important;
        width: 16px !important;
        height: 16px !important;
        box-shadow: 0 2px 8px rgba(108,92,231,0.3) !important;
    }
    .stSlider label {
        color: #8e92a8 !important;
        font-size: 0.78rem !important;
    }

    /* ── 复选框 ── */
    .stCheckbox label {
        font-size: 0.82rem !important;
        color: #8e92a8 !important;
    }
    .stCheckbox [role="checkbox"] {
        border-color: rgba(255,255,255,0.2) !important;
    }
    .stCheckbox [role="checkbox"]:checked {
        background: #6c5ce7 !important;
        border-color: #6c5ce7 !important;
    }

    /* ── 选择框 ── */
    .stSelectbox > div > div {
        background: rgba(255,255,255,0.04) !important;
        border-color: rgba(255,255,255,0.08) !important;
    }
    div[role="listbox"] ul {
        background: #0f1120 !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 10px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4) !important;
    }
    div[role="listbox"] ul li {
        color: #8e92a8 !important;
    }
    div[role="listbox"] ul li:hover {
        background: rgba(108,92,231,0.1) !important;
    }
    div[role="listbox"] ul li[aria-selected="true"] {
        background: rgba(108,92,231,0.15) !important;
        color: #e4e6f0 !important;
    }

    /* ── 进度条 ── */
    div[data-testid="stProgress"] > div {
        background: rgba(255,255,255,0.06) !important;
        border-radius: 4px !important;
        height: 4px !important;
    }
    div[data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #6c5ce7, #a855f7) !important;
        border-radius: 4px !important;
    }

    /* ── 分隔线 ── */
    hr {
        border-color: rgba(255,255,255,0.06) !important;
        margin: 1.2rem 0 !important;
    }

    /* ── 警告/信息条 ── */
    .stAlert {
        border-radius: 10px !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        background: rgba(255,255,255,0.02) !important;
    }
    div[data-testid="stInfoBox"] {
        background: rgba(108,92,231,0.08) !important;
        border: 1px solid rgba(108,92,231,0.15) !important;
    }
    div[data-testid="stInfoBox"] svg { fill: #6c5ce7 !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important;
        border-bottom: 1px solid rgba(255,255,255,0.06) !important;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1.4rem !important;
        font-size: 0.8125rem !important;
        font-weight: 500 !important;
        color: #636678 !important;
        transition: all 0.2s ease !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #8e92a8 !important;
        background: rgba(255,255,255,0.02) !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #c4c6d0 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #6c5ce7 !important;
    }

    /* ── Radio inline ── */
    div[role="radiogroup"] {
        gap: 4px !important;
    }
    div[role="radiogroup"] label {
        padding: 0.3rem 0.8rem !important;
        border-radius: 8px !important;
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        font-size: 0.78rem !important;
        color: #8e92a8 !important;
        transition: all 0.15s ease !important;
    }
    div[role="radiogroup"] label:hover {
        background: rgba(255,255,255,0.06) !important;
    }
    div[role="radiogroup"] label[data-selected="true"] {
        background: rgba(108,92,231,0.12) !important;
        border-color: #6c5ce7 !important;
        color: #c4c6d0 !important;
        font-weight: 600 !important;
    }

    /* ── 多选 ── */
    .stMultiSelect div[data-baseweb="select"] {
        border-color: rgba(255,255,255,0.08) !important;
        background: rgba(255,255,255,0.04) !important;
    }
    .stMultiSelect div[data-baseweb="select"]:focus-within {
        border-color: #6c5ce7 !important;
        box-shadow: 0 0 0 3px rgba(108,92,231,0.1) !important;
    }

    /* ── 日期输入 ── */
    div[data-testid="stDateInput"] input {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 10px !important;
        color: #e4e6f0 !important;
    }

    /* ── 滚动条 ── */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,0.08);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.12); }

    /* ── 应用背景微光 ── */
    .stApp::before {
        content: '';
        position: fixed;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background:
            radial-gradient(ellipse at 20% 30%, rgba(108,92,231,0.03) 0%, transparent 50%),
            radial-gradient(ellipse at 80% 70%, rgba(168,85,247,0.02) 0%, transparent 50%);
        pointer-events: none;
        z-index: 0;
    }

    /* ── Plotly 图表深色适配 ── */
    .js-plotly-plot .plotly .main-svg {
        background: transparent !important;
    }
    .js-plotly-plot .plotly .svg-container {
        background: transparent !important;
    }

    /* ── 字体增强: Streamlit 底层覆盖 ── */
    .stText, .stTextInput, .stSelectbox, .stMultiSelect, .stSlider, .stNumberInput {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
    }
    .stButton button, .stDownloadButton button {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.8125rem !important;
        letter-spacing: 0.01em !important;
    }
    .stDataFrame {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        font-size: 0.8rem !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.8125rem !important;
    }
    .stCheckbox label, .stRadio label {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        font-weight: 400 !important;
        font-size: 0.8125rem !important;
    }
    .stExpander summary {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.8125rem !important;
    }
    .st-dn, .st-el, .st-em {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
    }
    /* Metric labels and values */
    div[data-testid="metric-container"] label {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.6rem !important;
        letter-spacing: 0.08em;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace !important;
        font-weight: 700 !important;
        font-size: 1.4rem !important;
    }


    /* ═══ 🔧 V3: 全面修复 — slider key 标签隐藏 + 中文乱码 ═══ */
    /* ── 暴力清除 slider 内的 key=... 标签 ── */
    /* Streamlit 在 column 中的 slider 会在标签旁渲染一个 <code> 元素显示 key 名 */
    .stSlider [data-testid="stWidgetLabel"] code,
    .stSlider [data-testid="stWidgetLabel"] small,
    .stSlider [data-testid="stWidgetLabel"] span[style*="font-size"],
    .stSlider [data-testid="stWidgetLabel"] span[style*="font-size:"],
    .stSlider [data-testid="stWidgetLabel"] span.font-size,
    .stNumberInput [data-testid="stWidgetLabel"] code,
    .stNumberInput [data-testid="stWidgetLabel"] small,
    .stSelectbox [data-testid="stWidgetLabel"] code,
    .stSelectbox [data-testid="stWidgetLabel"] small,
    [data-testid="stWidgetLabel"] code,
    [data-testid="stWidgetLabel"] small {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        width: 0 !important;
        overflow: hidden !important;
        position: absolute !important;
        pointer-events: none !important;
    }
    /* ── 深度覆盖：所有带 key_ 前缀的 label 内容直接隐藏 ── */
    .stSlider [data-testid="stWidgetLabel"] > *:nth-child(n+2) {
        display: none !important;
    }
    /* ── 标签文字优化 ── */
    .stSlider label[data-testid="stWidgetLabel"],
    .stNumberInput label[data-testid="stWidgetLabel"],
    .stSelectbox label[data-testid="stWidgetLabel"] {
        font-size: 0.80rem !important;
        overflow: visible !important;
        white-space: normal !important;
        line-height: 1.3 !important;
        color: #c8cae0 !important;
        display: inline-block !important;
    }
    /* ── 中文显示深度修复（解决所有乱码） ── */
    /* 1. 全局中文字体堆栈 — 覆盖所有元素 */
    html, body, .stApp, .main, .block-container,
    *:lang(zh), *:lang(zh-CN), *:lang(zh-TW),
    [class*="css"], .stMarkdown, .stText, .stWidgetLabel,
    label, span, p, div, h1, h2, h3, h4, h5, h6,
    input, textarea, select, button, a, li, td, th,
    .st-bq, .st-br, .st-bs, .st-bt, .st-bu, .st-bv, .st-bw,
    .st-dg, .st-dh, .st-di, .st-dj, .st-dk,
    .st-emotion-cache-*,
    [data-testid="stWidgetLabel"],
    [data-testid="stMetricValue"],
    [data-testid="metric-container"] * {
        font-family: 'PingFang SC', 'Heiti SC', 'Microsoft YaHei', 'Hiragino Sans GB',
                     'STHeiti', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei',
                     -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    /* 2. Plotly 图表 — 强制中文字体（hover label、坐标轴文字、图例等） */
    .js-plotly-plot .plotly .user-select-none,
    .js-plotly-plot .plotly .infolayer,
    .js-plotly-plot .plotly .legendtext,
    .js-plotly-plot .plotly .xtick text,
    .js-plotly-plot .plotly .ytick text,
    .js-plotly-plot .plotly .annotation-text,
    .js-plotly-plot .plotly .hovertext text,
    .js-plotly-plot .plotly .hoverlayer text,
    .js-plotly-plot .plotly .slicetext,
    .js-plotly-plot .plotly .gtitle,
    .js-plotly-plot .plotly .xtitle,
    .js-plotly-plot .plotly .ytitle {
        font-family: 'PingFang SC', 'Microsoft YaHei', 'Heiti SC', 'Hiragino Sans GB', sans-serif !important;
    }
    /* 3. 数据表格 — 中文列名和内容 */
    .stDataFrame *,
    [data-testid="stDataFrame"] *,
    [data-testid="StyledDataFrame"] *,
    .stTable * {
        font-family: 'PingFang SC', 'Heiti SC', 'Microsoft YaHei', sans-serif !important;
    }


    /* ═══ 🐛 More robust label fixes for sliders in columns ═══ */
    /* Prevent slider label text from wrapping into key area */
    .stSlider [data-testid="stWidgetLabel"] p {
        font-size: 0.75rem !important;
        line-height: 1.2 !important;
        margin-bottom: 0 !important;
        overflow: visible !important;
        white-space: normal !important;
    }
    /* Ensure columns containing sliders have adequate min-width */
    .stHorizontalBlock > div {
        min-width: 150px !important;
    }
    /* Fix for the key label text that sometimes leaks into view */
    .stSlider .st-bp code, 
    .stSlider code,
    .stSlider small,
    .stSlider .st-emotion-cache-* code {
        display: none !important;
    }
    /* Better font fallback for ALL Chinese characters */
    *:lang(zh), *:lang(zh-CN), *:lang(zh-TW),
    .stMarkdown, .stText, .stWidgetLabel, label, span, p, div, h1, h2, h3, h4, h5, h6 {
        font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Heiti SC', 'STHeiti', 'Microsoft YaHei', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', sans-serif !important;
    }
</style>
""", unsafe_allow_html=True)

# === Premium UI 组件与页面辅助函数 ===
st.markdown(dedent("""
<style>
    /* ═══════════════════════════════════════════════════════
       QuantA Institutional UI v4.0
       目标: 顶级投行终端质感 · 深色玻璃 · 香槟金高光 · 无乱码渲染
       ═══════════════════════════════════════════════════════ */
    :root {
        --qa-bg: #05070c;
        --qa-panel: rgba(12, 16, 27, 0.76);
        --qa-panel-soft: rgba(255,255,255,0.035);
        --qa-border: rgba(236, 226, 198, 0.13);
        --qa-border-soft: rgba(255,255,255,0.075);
        --qa-text: #f4f0e8;
        --qa-muted: #9298ab;
        --qa-dim: #626b82;
        --qa-gold: #d7b56d;
        --qa-gold-2: #f1d89a;
        --qa-blue: #55b7ff;
        --qa-green: #38d6a2;
        --qa-red: #ff6b7a;
    }

    .block-container {
        max-width: 1360px !important;
        padding-top: 1.35rem !important;
    }

    .qa-hero {
        position: relative;
        overflow: hidden;
        padding: 2.65rem 2.85rem 2.35rem 2.85rem;
        border-radius: 30px;
        border: 1px solid var(--qa-border);
        background:
            linear-gradient(135deg, rgba(215,181,109,0.18), rgba(85,183,255,0.055) 42%, rgba(6,9,17,0.95) 74%),
            radial-gradient(circle at 12% 12%, rgba(255,255,255,0.13), transparent 24%),
            radial-gradient(circle at 80% 4%, rgba(215,181,109,0.12), transparent 26%),
            rgba(8,11,20,0.92);
        box-shadow:
            0 32px 90px rgba(0,0,0,0.42),
            inset 0 1px 0 rgba(255,255,255,0.10),
            inset 0 -1px 0 rgba(215,181,109,0.04);
        margin-bottom: 1.25rem;
    }
    .qa-hero::before {
        content: '';
        position: absolute;
        inset: 0;
        background-image:
            linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.028) 1px, transparent 1px);
        background-size: 54px 54px;
        mask-image: linear-gradient(120deg, rgba(0,0,0,.55), transparent 70%);
        pointer-events: none;
    }
    .qa-hero::after {
        content: '';
        position: absolute;
        width: 520px; height: 520px;
        right: -210px; top: -220px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(215,181,109,0.22), transparent 62%);
        pointer-events: none;
    }
    .qa-hero > * { position: relative; z-index: 1; }

    .qa-kicker {
        display: inline-flex;
        align-items: center;
        gap: .48rem;
        padding: .3rem .72rem;
        border: 1px solid rgba(215,181,109,0.28);
        border-radius: 999px;
        color: #f2d99c !important;
        background: rgba(215,181,109,0.075);
        font-size: .70rem !important;
        font-weight: 720 !important;
        letter-spacing: .13em !important;
        text-transform: uppercase;
        margin-bottom: 1.05rem;
        line-height: 1 !important;
    }
    .qa-title {
        font-size: clamp(2.25rem, 5vw, 4.15rem) !important;
        line-height: .98 !important;
        letter-spacing: -0.062em !important;
        margin: 0 0 .86rem 0 !important;
        color: #fffaf1 !important;
        max-width: 960px;
        text-wrap: balance;
        text-shadow: 0 24px 80px rgba(0,0,0,0.42);
    }
    .qa-subtitle {
        color: #bfc5d6 !important;
        max-width: 820px;
        font-size: 1.02rem !important;
        line-height: 1.92 !important;
        margin: 0 0 1.15rem 0 !important;
        letter-spacing: .015em !important;
    }
    .qa-badges { display: flex; flex-wrap: wrap; gap: .58rem; margin-top: 1rem; }
    .qa-badge {
        border: 1px solid rgba(255,255,255,0.11);
        background: linear-gradient(180deg, rgba(255,255,255,0.075), rgba(255,255,255,0.032));
        border-radius: 999px;
        padding: .38rem .76rem;
        color: #dce2ef !important;
        font-size: .78rem !important;
        font-weight: 560 !important;
        line-height: 1.2 !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
    }
    .qa-badge strong { color: var(--qa-gold-2) !important; }

    .qa-section-title {
        display: flex;
        align-items: baseline;
        gap: .72rem;
        margin: 1.45rem 0 .9rem 0;
    }
    .qa-section-title h2 {
        margin: 0 !important;
        font-size: 1.55rem !important;
        color: #f4f0e8 !important;
        letter-spacing: -0.035em !important;
    }
    .qa-section-title span {
        color: #7f879a !important;
        font-size: .82rem !important;
        letter-spacing: .03em !important;
    }

    .qa-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: .9rem 0 1.1rem 0; }
    .qa-grid-4 { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .92rem; margin: .9rem 0 1.1rem 0; }
    .qa-card {
        position: relative;
        overflow: hidden;
        border-radius: 22px;
        border: 1px solid var(--qa-border-soft);
        background:
            linear-gradient(180deg, rgba(255,255,255,0.067), rgba(255,255,255,0.022)),
            rgba(10,14,24,0.72);
        box-shadow: 0 18px 52px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.07);
        padding: 1.18rem 1.18rem 1.25rem 1.18rem;
        min-height: 150px;
        transition: transform .22s ease, border-color .22s ease, background .22s ease, box-shadow .22s ease;
    }
    .qa-card::before {
        content: '';
        position: absolute;
        left: 0; right: 0; top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(215,181,109,0.72), transparent);
        opacity: .58;
    }
    .qa-card:hover {
        transform: translateY(-3px);
        border-color: rgba(215,181,109,0.30);
        background:
            linear-gradient(180deg, rgba(215,181,109,0.085), rgba(255,255,255,0.026)),
            rgba(10,14,24,0.78);
        box-shadow: 0 22px 68px rgba(0,0,0,0.32), 0 0 0 1px rgba(215,181,109,0.06) inset;
    }
    .qa-card-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 2.05rem;
        height: 2.05rem;
        padding: 0 .48rem;
        border-radius: 999px;
        border: 1px solid rgba(215,181,109,0.22);
        background: rgba(215,181,109,0.075);
        color: #f1d89a !important;
        font-size: .82rem !important;
        font-weight: 760 !important;
        letter-spacing: .05em !important;
        margin-bottom: .78rem;
        line-height: 1 !important;
    }
    .qa-card-title {
        font-size: 1.02rem !important;
        font-weight: 760 !important;
        color: #f3f4f8 !important;
        margin-bottom:.42rem;
        line-height: 1.35 !important;
        letter-spacing: -0.015em !important;
    }
    .qa-card-body {
        color: #9aa2b7 !important;
        font-size: .83rem !important;
        line-height: 1.78 !important;
        letter-spacing: .015em !important;
    }

    .qa-page-header {
        position: relative;
        overflow: hidden;
        padding: 1.35rem 1.52rem;
        border-radius: 24px;
        border: 1px solid rgba(215,181,109,0.13);
        background:
            linear-gradient(135deg, rgba(215,181,109,0.105), rgba(85,183,255,0.025) 42%, rgba(255,255,255,0.025)),
            rgba(8,11,19,0.78);
        box-shadow: 0 16px 50px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.06);
        margin-bottom: 1.05rem;
    }
    .qa-page-header::after {
        content:'';
        position:absolute;
        right:-80px; top:-110px;
        width:260px; height:260px;
        border-radius:50%;
        background: radial-gradient(circle, rgba(215,181,109,.15), transparent 66%);
    }
    .qa-page-header > * { position: relative; z-index: 1; }
    .qa-page-header h2 { margin: .2rem 0 .42rem 0 !important; color: #fffaf1 !important; }
    .qa-page-header p { color: #9ca4b8 !important; margin: 0 !important; font-size: .92rem !important; }

    .qa-callout, .stat-card {
        border: 1px solid rgba(215,181,109,0.14) !important;
        border-left: 3px solid var(--qa-gold) !important;
        border-radius: 16px !important;
        padding: .95rem 1.08rem !important;
        background: linear-gradient(90deg, rgba(215,181,109,0.09), rgba(255,255,255,0.025)) !important;
        color: #d7dbe8 !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
        margin: .86rem 0 !important;
    }

    /* 更稳妥地隐藏 Streamlit 自动展示的 key 文本，避免误伤中文 */
    [data-testid="stWidgetLabel"] code,
    [data-testid="stWidgetLabel"] small {
        display: none !important;
    }

    /* 顶投级数据终端细节 */
    div[data-testid="metric-container"] {
        border-color: rgba(215,181,109,0.13) !important;
        background: linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.022)) !important;
        border-radius: 18px !important;
        padding: 1rem 1.12rem !important;
        box-shadow: 0 16px 42px rgba(0,0,0,.20), inset 0 1px 0 rgba(255,255,255,.06) !important;
    }
    div[data-testid="metric-container"] label {
        color: #8a8f9f !important;
        font-size: .66rem !important;
        letter-spacing: .10em !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #fff7e8 !important;
        font-size: 1.46rem !important;
    }

    section[data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, rgba(9,12,22,0.98), rgba(5,7,12,0.98)) !important;
        border-right: 1px solid rgba(215,181,109,0.10) !important;
    }
    .sidebar-logo {
        background: linear-gradient(135deg, #9d7c38, #d7b56d 48%, #6b4f1d) !important;
        box-shadow: 0 8px 24px rgba(215,181,109,0.20) !important;
    }
    .sidebar-version { color: #d7b56d !important; }
    section[data-testid="stSidebar"] .stButton button[kind="primary"] {
        background: linear-gradient(90deg, rgba(215,181,109,0.16), rgba(255,255,255,0.035)) !important;
        color: #f2efe8 !important;
        box-shadow: inset 3px 0 0 #d7b56d !important;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #c79f4a, #f1d89a 48%, #9b742e) !important;
        color: #0d1019 !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        box-shadow: 0 10px 28px rgba(215,181,109,0.22) !important;
    }
    .stButton button[kind="primary"]:hover {
        background: linear-gradient(135deg, #d8b462, #ffe3a3 48%, #ad8235) !important;
        box-shadow: 0 12px 34px rgba(215,181,109,0.30) !important;
    }

    @media (max-width: 980px) {
        .qa-grid, .qa-grid-4 { grid-template-columns: 1fr; }
        .qa-hero { padding: 1.65rem; border-radius: 24px; }
        .qa-section-title { flex-direction: column; gap: .18rem; align-items: flex-start; }
    }
</style>
""").strip(), unsafe_allow_html=True)




st.markdown(dedent("""
<style>
    :root { --qa-display: "SF Pro Display", "Avenir Next", "Inter", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; --qa-body: "SF Pro Text", "Inter", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; --qa-mono: "SF Mono", "JetBrains Mono", Menlo, Monaco, monospace; }
    html, body, .stApp, .block-container, [data-testid="stSidebar"], [data-testid="stWidgetLabel"], .stMarkdown, .stText, .stCaption, .stTabs, .stCodeBlock, .stDataFrame, .stAlert, label, p, span, div, li, td, th, a, button, input, textarea, select { font-family: var(--qa-body) !important; }
    h1, h2, h3, h4, h5, h6, .qa-title, .qa-card-title, .qa-section-title h2, .qa-page-header h2 { font-family: var(--qa-display) !important; letter-spacing: -0.035em !important; }
    .stApp { background: radial-gradient(circle at 15% 10%, rgba(215,181,109,.07), transparent 26%), radial-gradient(circle at 85% 0%, rgba(89,151,255,.08), transparent 24%), linear-gradient(180deg, #05070d 0%, #060910 36%, #04060b 100%) !important; }
    .block-container { max-width: 1420px !important; padding-top: 1.1rem !important; padding-bottom: 2.6rem !important; }
    [data-testid="stWidgetLabel"] code, [data-testid="stWidgetLabel"] small, div[data-testid="stExpander"] summary code, div[data-testid="stExpander"] summary small { display:none !important; }
    div[data-testid="stExpander"] summary { font-family: var(--qa-display) !important; font-size: .88rem !important; color: #edf1fb !important; letter-spacing: -.01em !important; line-height: 1.35 !important; padding: .72rem 1rem !important; }
    div[data-testid="stExpander"] summary p { margin: 0 !important; }
    .qa-hero-pro { display:grid; grid-template-columns: minmax(0,1.25fr) minmax(320px,.95fr); gap: 1.25rem; align-items: stretch; }
    .qa-hero-copy {padding-right: .4rem;}
    .qa-hero-visual { position: relative; min-height: 360px; border-radius: 26px; overflow: hidden; border: 1px solid rgba(215,181,109,.16); background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.018)), radial-gradient(circle at 20% 20%, rgba(215,181,109,.12), transparent 30%), rgba(6,8,14,.84); box-shadow: inset 0 1px 0 rgba(255,255,255,.07), 0 24px 72px rgba(0,0,0,.28); }
    .qa-hero-visual::before { content:""; position:absolute; inset:0; background-image: linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px); background-size: 42px 42px; opacity: .34; mask-image: linear-gradient(180deg, rgba(0,0,0,.85), transparent 98%); }
    .qa-hero-svg, .qa-visual-svg { position:relative; z-index:1; width:100%; height:100%; display:block; }
    .qa-visual-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin-top: .95rem; }
    .qa-visual-card { position:relative; overflow:hidden; min-height: 330px; border-radius: 24px; padding: 1rem; border: 1px solid rgba(215,181,109,.13); background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02)), rgba(8,11,18,.76); box-shadow: 0 18px 60px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.06); }
    .qa-visual-head {display:flex; align-items:flex-start; gap:.75rem; margin-bottom:.8rem; position:relative; z-index:1;}
    .qa-visual-kicker { display:inline-flex; padding:.28rem .62rem; border-radius:999px; border:1px solid rgba(215,181,109,.2); background: rgba(215,181,109,.08); color:#f4dfad !important; font-size:.68rem !important; font-weight:700 !important; letter-spacing:.10em !important; text-transform:uppercase; }
    .qa-visual-title {font-size:1.02rem !important; color:#f9fbff !important; font-weight:720 !important; margin-top:.55rem;}
    .qa-visual-body {font-size:.82rem !important; color:#97a0b7 !important; line-height:1.78 !important; margin-top:.18rem;}
    .qa-visual-frame { position:relative; overflow:hidden; border-radius:20px; min-height: 208px; border:1px solid rgba(255,255,255,.075); background: rgba(5,8,14,.92); }
    .qa-code-panel { position:relative; overflow:hidden; margin-top: 1rem; border-radius: 24px; padding: 1.18rem 1.22rem; border:1px solid rgba(215,181,109,.13); background: linear-gradient(135deg, rgba(215,181,109,.08), rgba(255,255,255,.02)), rgba(8,11,18,.76); box-shadow: 0 18px 60px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.06); }
    .qa-code-panel h3 { margin: 0 0 .4rem 0 !important; color:#fff8ea !important; font-size:1.08rem !important; }
    .qa-code-panel p { color:#aab2c6 !important; margin:0 0 .9rem 0 !important; }
    .qa-code-box { border-radius: 18px; padding: .95rem 1rem; background: rgba(3,6,10,.84); border: 1px solid rgba(255,255,255,.06); font-family: var(--qa-mono) !important; color:#f2e0ad !important; line-height:1.8 !important; font-size:.85rem !important; white-space:pre-wrap; }
    .qa-mini-points { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:.8rem; margin-top: .95rem; }
    .qa-mini-point { border-radius:18px; border:1px solid rgba(255,255,255,.08); padding:.86rem .92rem; background: rgba(255,255,255,.03); }
    .qa-mini-point b { display:block; color:#f4efdf !important; margin-bottom:.18rem; }
    .qa-mini-point span { color:#95a0b7 !important; font-size:.79rem !important; line-height:1.7 !important; }
    .qa-guide-panel { border-radius: 24px; padding: 1.1rem 1.15rem; border:1px solid rgba(215,181,109,.12); background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02)), rgba(8,11,18,.72); box-shadow: 0 18px 56px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.05); height: 100%; }
    @media (max-width: 1100px) { .qa-hero-pro, .qa-visual-grid, .qa-mini-points { grid-template-columns: 1fr; } .qa-hero-visual { min-height: 290px; } }
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
    .qa-premium-shell {
        display:grid; grid-template-columns: minmax(0,1.1fr) minmax(320px,.9fr); gap:1rem;
        margin:.2rem 0 1rem 0;
    }
    .qa-premium-copy, .qa-premium-visual-wrap, .qa-story-card {
        border-radius:24px; border:1px solid rgba(215,181,109,.12);
        background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02)), rgba(8,11,18,.76);
        box-shadow:0 18px 56px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.05);
    }
    .qa-premium-copy { padding:1.2rem 1.25rem; }
    .qa-premium-eyebrow { display:inline-flex; padding:.26rem .62rem; border-radius:999px; border:1px solid rgba(215,181,109,.18); background:rgba(215,181,109,.08); color:#f3ddac; font-size:.68rem; font-weight:700; letter-spacing:.11em; text-transform:uppercase; }
    .qa-premium-title { color:#fbf8f1; font-size:1.34rem; font-weight:760; margin:.7rem 0 .35rem 0; letter-spacing:-.03em; }
    .qa-premium-body { color:#9ca7bf; font-size:.88rem; line-height:1.78; margin:0; }
    .qa-premium-stats { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; margin-top:1rem; }
    .qa-premium-stat { border-radius:18px; padding:.88rem .92rem; background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.07); }
    .qa-premium-stat b { display:block; color:#fff3d5; font-size:1rem; margin-bottom:.16rem; }
    .qa-premium-stat span { color:#8f9bb4; font-size:.75rem; letter-spacing:.02em; }
    .qa-premium-visual-wrap { overflow:hidden; min-height:214px; position:relative; }
    .qa-premium-visual-wrap::before { content:""; position:absolute; inset:0; background-image:linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.022) 1px, transparent 1px); background-size:34px 34px; opacity:.35; }
    .qa-premium-visual { width:100%; height:100%; display:block; position:relative; z-index:1; }
    .qa-story-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.9rem; margin:.9rem 0 1rem 0; }
    .qa-story-card { padding:1rem 1rem 1.05rem 1rem; position:relative; overflow:hidden; }
    .qa-story-card::after { content:""; position:absolute; width:160px; height:160px; border-radius:50%; right:-70px; bottom:-75px; background:radial-gradient(circle, rgba(215,181,109,.12), transparent 72%); }
    .qa-story-tag { display:inline-block; color:#f3ddac; font-size:.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.1em; margin-bottom:.45rem; }
    .qa-story-title { color:#fbf8f1; font-size:1rem; font-weight:720; margin:0 0 .25rem 0; }
    .qa-story-text { color:#97a1b7; font-size:.82rem; line-height:1.76; margin:0; }
    .qa-note-banner { border-radius:20px; padding:.9rem 1rem; border:1px solid rgba(106,198,255,.12); background:linear-gradient(90deg, rgba(106,198,255,.08), rgba(215,181,109,.06)); color:#d9e4f7; margin:.35rem 0 1rem 0; }
    @media (max-width: 1100px) { .qa-premium-shell, .qa-premium-stats, .qa-story-grid { grid-template-columns:1fr; } }
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
    @keyframes qaFloatSoft {
        0%, 100% { transform: translate3d(0,0,0) scale(1); }
        50% { transform: translate3d(0,-10px,0) scale(1.015); }
    }
    @keyframes qaDrift {
        0% { transform: translate3d(0,0,0) rotate(0deg); }
        50% { transform: translate3d(10px,-8px,0) rotate(3deg); }
        100% { transform: translate3d(-4px,2px,0) rotate(-2deg); }
    }
    @keyframes qaShimmer {
        0% { background-position: 0% 50%; opacity: .55; }
        50% { background-position: 100% 50%; opacity: .95; }
        100% { background-position: 0% 50%; opacity: .55; }
    }

    .qa-page-header,
    .qa-premium-copy,
    .qa-premium-visual-wrap,
    .qa-story-card,
    .qa-note-banner,
    .stat-card,
    .qa-callout,
    div[data-testid="metric-container"],
    div[data-testid="stExpander"] {
        position: relative;
        overflow: hidden;
        isolation: isolate;
    }

    .qa-page-header {
        border-radius: 34px 22px 40px 24px / 26px 42px 22px 38px !important;
        padding: 1.45rem 1.6rem 1.42rem 1.6rem !important;
        background:
            radial-gradient(circle at 14% 18%, rgba(255,255,255,.08), transparent 22%),
            radial-gradient(circle at 86% 12%, rgba(106,198,255,.11), transparent 24%),
            linear-gradient(135deg, rgba(215,181,109,.14), rgba(255,255,255,.04) 42%, rgba(92,124,250,.07) 100%),
            rgba(8,11,19,.77) !important;
        box-shadow: 0 22px 70px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06) !important;
    }
    .qa-page-header::before {
        content:'';
        position:absolute;
        left:-5%; bottom:-40px;
        width:52%; height:120px;
        background: radial-gradient(circle at left center, rgba(255,255,255,.08), transparent 62%);
        filter: blur(10px);
        animation: qaFloatSoft 8s ease-in-out infinite;
        pointer-events:none;
    }
    .qa-page-header::after {
        width: 320px !important; height: 320px !important;
        right: -110px !important; top: -130px !important;
        background: radial-gradient(circle, rgba(215,181,109,.20), rgba(106,198,255,.10) 34%, transparent 68%) !important;
        animation: qaDrift 10s ease-in-out infinite alternate;
    }

    .qa-premium-shell {
        grid-template-columns: minmax(0, 1.12fr) minmax(320px, .88fr) !important;
        align-items: stretch;
        gap: 1.15rem !important;
    }
    .qa-premium-copy {
        border-radius: 34px 22px 42px 24px / 24px 40px 22px 38px !important;
        padding: 1.24rem 1.3rem 1.2rem 1.3rem !important;
        background:
            radial-gradient(circle at 15% 20%, rgba(255,255,255,.065), transparent 18%),
            linear-gradient(135deg, rgba(255,255,255,.065), rgba(255,255,255,.018) 36%, rgba(215,181,109,.05) 100%),
            rgba(8,11,18,.80) !important;
        animation: qaFloatSoft 9s ease-in-out infinite;
    }
    .qa-premium-copy::before,
    .qa-premium-visual-wrap::before,
    .qa-story-card::before,
    .stat-card::before,
    .qa-note-banner::before,
    .qa-callout::before {
        content:'';
        position:absolute;
        left:-10%; top:-10%;
        width:46%; height:70%;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255,255,255,.08), transparent 64%);
        filter: blur(12px);
        opacity:.55;
        pointer-events:none;
    }
    .qa-premium-visual-wrap {
        min-height: 228px !important;
        border-radius: 24px 38px 22px 42px / 36px 26px 38px 24px !important;
        background:
            radial-gradient(circle at 85% 20%, rgba(215,181,109,.13), transparent 22%),
            linear-gradient(140deg, rgba(255,255,255,.055), rgba(255,255,255,.018) 44%, rgba(106,198,255,.05)),
            rgba(8,11,18,.74) !important;
        animation: qaFloatSoft 11s ease-in-out infinite reverse;
    }
    .qa-premium-visual-wrap::before {
        inset: 0 !important;
        width: auto !important; height: auto !important;
        left: 0 !important; top: 0 !important;
        border-radius: inherit !important;
        background-image:
            linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px) !important;
        background-size: 34px 34px !important;
        filter:none !important;
        opacity:.42 !important;
    }
    .qa-premium-visual-wrap::after {
        content:'';
        position:absolute;
        inset: auto 8% 12% auto;
        width: 110px; height: 110px;
        border-radius: 42% 58% 57% 43% / 52% 37% 63% 48%;
        background: radial-gradient(circle, rgba(215,181,109,.16), transparent 70%);
        animation: qaDrift 12s ease-in-out infinite;
        pointer-events:none;
    }

    .qa-premium-eyebrow {
        border-radius: 999px !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.12);
    }
    .qa-premium-title {
        font-size: 1.42rem !important;
        line-height: 1.15 !important;
    }
    .qa-premium-stats {
        gap: .8rem !important;
    }
    .qa-premium-stat {
        border-radius: 24px 16px 26px 18px / 18px 24px 16px 26px !important;
        background: linear-gradient(135deg, rgba(255,255,255,.055), rgba(255,255,255,.02)) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.06);
        transition: transform .25s ease, border-color .25s ease;
    }
    .qa-premium-stat:hover {
        transform: translateY(-3px);
        border-color: rgba(215,181,109,.24) !important;
    }

    .qa-story-grid {
        gap: 1rem !important;
        align-items: stretch;
    }
    .qa-story-card {
        border-radius: 30px 18px 34px 20px / 22px 34px 18px 30px !important;
        padding: 1.08rem 1.05rem 1.1rem 1.05rem !important;
        background:
            linear-gradient(140deg, rgba(255,255,255,.06), rgba(255,255,255,.018) 42%, rgba(215,181,109,.045)),
            rgba(8,11,18,.78) !important;
        transition: transform .28s ease, box-shadow .28s ease, border-color .28s ease;
    }
    .qa-story-card:nth-child(3n+1) { transform: translateY(-5px) rotate(-0.45deg); }
    .qa-story-card:nth-child(3n+2) { transform: translateY(7px) rotate(0.35deg); }
    .qa-story-card:nth-child(3n+3) { transform: translateY(1px) rotate(-0.15deg); }
    .qa-story-card:hover {
        transform: translateY(-8px) scale(1.012) !important;
        box-shadow: 0 24px 60px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06) !important;
        border-color: rgba(215,181,109,.24) !important;
    }
    .qa-story-card::after {
        width: 190px !important; height: 190px !important;
        right: -85px !important; bottom: -95px !important;
        border-radius: 54% 46% 65% 35% / 43% 59% 41% 57% !important;
        background: radial-gradient(circle, rgba(215,181,109,.15), transparent 70%) !important;
        animation: qaDrift 9s ease-in-out infinite alternate;
    }

    .qa-note-banner,
    .stat-card,
    .qa-callout {
        border-left: 0 !important;
        border-radius: 28px 18px 30px 20px / 18px 28px 18px 32px !important;
        padding: 1rem 1.12rem !important;
        background:
            linear-gradient(120deg, rgba(106,198,255,.08), rgba(255,255,255,.025) 34%, rgba(215,181,109,.06) 100%),
            rgba(9,12,20,.74) !important;
        box-shadow: 0 16px 48px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.05) !important;
    }
    .qa-note-banner::after,
    .stat-card::after,
    .qa-callout::after {
        content:'';
        position:absolute;
        left: 1rem; bottom: 0.7rem;
        width: 130px; height: 2px;
        border-radius: 999px;
        background: linear-gradient(90deg, rgba(215,181,109,.78), rgba(106,198,255,.08));
        background-size: 200% 200%;
        animation: qaShimmer 4.2s linear infinite;
        pointer-events:none;
    }

    div[data-testid="metric-container"] {
        border-radius: 26px 16px 30px 18px / 18px 28px 18px 30px !important;
        background:
            radial-gradient(circle at 18% 18%, rgba(255,255,255,.08), transparent 20%),
            linear-gradient(135deg, rgba(255,255,255,.06), rgba(255,255,255,.02) 44%, rgba(215,181,109,.05)),
            rgba(8,11,18,.78) !important;
        transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease !important;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px) scale(1.01) !important;
        box-shadow: 0 22px 48px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.06) !important;
        border-color: rgba(215,181,109,.24) !important;
    }

    div[data-testid="stExpander"] {
        border-radius: 26px 18px 30px 18px / 18px 28px 18px 30px !important;
        background: linear-gradient(140deg, rgba(255,255,255,.05), rgba(255,255,255,.02)), rgba(8,11,18,.72) !important;
    }
    .stButton button {
        border-radius: 999px !important;
        padding: .52rem 1.24rem !important;
        letter-spacing: .01em !important;
    }
    .stButton button[kind="primary"] {
        background-size: 200% 200% !important;
        animation: qaShimmer 6s linear infinite !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: .5rem !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 999px !important;
        padding: .48rem .95rem !important;
        background: rgba(255,255,255,.035) !important;
        border: 1px solid rgba(255,255,255,.06) !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(215,181,109,.18), rgba(255,255,255,.04)) !important;
        border-color: rgba(215,181,109,.26) !important;
    }

    [data-testid="stDataFrame"],
    div[data-testid="stTable"] {
        border-radius: 28px 18px 30px 18px !important;
        overflow: hidden !important;
        border: 1px solid rgba(215,181,109,.10) !important;
        box-shadow: 0 18px 44px rgba(0,0,0,.18) !important;
    }

    @media (max-width: 1100px) {
        .qa-story-card:nth-child(3n+1),
        .qa-story-card:nth-child(3n+2),
        .qa-story-card:nth-child(3n+3) { transform: none !important; }
    }
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
    /* =========================================================
       JPM Editorial Refinement — light institutional website feel
       ========================================================= */
    :root {
        --jpm-ink: #21170f;
        --jpm-ink-2: #4a392c;
        --jpm-muted: #796e65;
        --jpm-paper: #f7f2ea;
        --jpm-paper-2: #fffaf2;
        --jpm-line: rgba(58,34,6,.16);
        --jpm-bronze: #9b6a2f;
        --jpm-bronze-2: #c99a55;
        --jpm-blue: #0f3557;
        --jpm-cream: #efe4d1;
        --jpm-shadow: 0 24px 70px rgba(58,34,6,.10);
        --qa-display: "Georgia", "Times New Roman", "Songti SC", "STSong", "Noto Serif CJK SC", serif;
        --qa-body: "Inter", "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at 8% 0%, rgba(201,154,85,.18), transparent 32%),
            linear-gradient(180deg, #fbf7ef 0%, #f6efe3 52%, #fbf8f2 100%) !important;
        color: var(--jpm-ink) !important;
    }
    .block-container {
        max-width: 1500px !important;
        padding-top: 1.4rem !important;
    }
    p, li, span, div, label, input, textarea, select, button {
        color: inherit;
    }
    h1, h2, h3, .qa-title, .qa-page-header h2, .qa-premium-title {
        font-family: var(--qa-display) !important;
        color: var(--jpm-ink) !important;
        letter-spacing: -0.055em !important;
        font-weight: 540 !important;
    }

    /* Sidebar becomes a restrained private-banking rail */
    section[data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, #21170f 0%, #2f1e0d 48%, #170f09 100%) !important;
        border-right: 1px solid rgba(255,255,255,.10) !important;
        box-shadow: 12px 0 42px rgba(58,34,6,.16);
    }
    section[data-testid="stSidebar"] * { color: #f6efe3 !important; }
    .sidebar-logo {
        background: #f7f2ea !important;
        color: #21170f !important;
        box-shadow: none !important;
    }
    .sidebar-logo svg { stroke: #21170f !important; }
    .sidebar-version { color: #d9bd91 !important; }
    section[data-testid="stSidebar"] .stButton button {
        border-radius: 0 !important;
        border: 0 !important;
        border-bottom: 1px solid rgba(255,255,255,.08) !important;
        background: transparent !important;
        box-shadow: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: .78rem .68rem !important;
        letter-spacing: .02em !important;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: rgba(255,255,255,.06) !important;
        transform: none !important;
    }
    section[data-testid="stSidebar"] .stButton button[kind="primary"] {
        background: linear-gradient(90deg, rgba(255,250,242,.16), rgba(255,255,255,.03)) !important;
        box-shadow: inset 4px 0 0 #d6b06b !important;
        color: #fffaf2 !important;
    }

    /* Editorial hero: fewer boxes, more magazine spacing */
    .qa-hero {
        min-height: 520px;
        border: 1px solid var(--jpm-line) !important;
        border-radius: 0 !important;
        background:
            linear-gradient(90deg, rgba(255,250,242,.94) 0%, rgba(255,250,242,.80) 48%, rgba(33,23,15,.92) 48%, rgba(33,23,15,.98) 100%) !important;
        box-shadow: var(--jpm-shadow) !important;
        overflow: hidden;
        padding: 0 !important;
        position: relative;
    }
    .qa-hero::before {
        content: "";
        position: absolute;
        inset: 0;
        background:
            linear-gradient(90deg, transparent 0 47.95%, rgba(201,154,85,.55) 48%, transparent 48.12%),
            radial-gradient(circle at 73% 26%, rgba(201,154,85,.24), transparent 24%);
        pointer-events: none;
    }
    .qa-hero-pro {
        grid-template-columns: minmax(0, .95fr) minmax(420px, 1.05fr) !important;
        gap: 0 !important;
    }
    .qa-hero-copy {
        padding: clamp(2.8rem, 5vw, 5.8rem) clamp(2rem, 5vw, 4.8rem) !important;
    }
    .qa-kicker, .qa-premium-eyebrow, .qa-story-tag, .qa-visual-kicker {
        color: var(--jpm-bronze) !important;
        background: transparent !important;
        border: 0 !important;
        border-radius: 0 !important;
        padding: 0 !important;
        text-transform: uppercase !important;
        letter-spacing: .18em !important;
        font-weight: 700 !important;
        font-family: var(--qa-body) !important;
    }
    .qa-title {
        font-size: clamp(3rem, 6.2vw, 6.8rem) !important;
        line-height: .92 !important;
        max-width: 820px;
        margin: 1.1rem 0 1.2rem 0 !important;
    }
    .qa-subtitle {
        color: var(--jpm-ink-2) !important;
        font-size: 1.02rem !important;
        line-height: 1.9 !important;
        max-width: 650px;
    }
    .qa-badges {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0,1fr));
        gap: .35rem 1.3rem !important;
        margin-top: 2rem !important;
        max-width: 680px;
    }
    .qa-badge {
        background: transparent !important;
        border: 0 !important;
        border-top: 1px solid var(--jpm-line) !important;
        border-radius: 0 !important;
        padding: .72rem 0 !important;
        color: var(--jpm-ink-2) !important;
        font-size: .82rem !important;
    }
    .qa-badge strong { color: var(--jpm-bronze) !important; }
    .qa-hero-visual {
        min-height: 520px !important;
        border: 0 !important;
        border-radius: 0 !important;
        background:
            radial-gradient(circle at 62% 30%, rgba(201,154,85,.22), transparent 26%),
            linear-gradient(180deg, #2a1b0d 0%, #21170f 100%) !important;
        box-shadow: none !important;
    }
    .qa-hero-visual::before {
        opacity: .12 !important;
        background-size: 54px 54px !important;
    }

    /* Page headers: editorial section title, no card boxes */
    .qa-page-header {
        border: 0 !important;
        border-radius: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: 2.1rem 0 1.1rem 0 !important;
        margin: 0 0 1.1rem 0 !important;
        border-bottom: 1px solid var(--jpm-line) !important;
    }
    .qa-page-header::before, .qa-page-header::after { display: none !important; }
    .qa-page-header h2 {
        color: var(--jpm-ink) !important;
        font-size: clamp(2.2rem, 4.2vw, 4.8rem) !important;
        line-height: .98 !important;
        margin: .3rem 0 .65rem 0 !important;
        max-width: 920px;
    }
    .qa-page-header p {
        color: var(--jpm-muted) !important;
        font-size: 1.02rem !important;
        max-width: 820px;
        line-height: 1.75 !important;
    }

    /* Premium shell becomes split editorial feature, not symmetric cards */
    .qa-premium-shell {
        display: grid !important;
        grid-template-columns: minmax(0, .92fr) minmax(420px, 1.08fr) !important;
        gap: clamp(1.8rem, 4vw, 4.2rem) !important;
        align-items: center !important;
        margin: 1.4rem 0 2.2rem 0 !important;
        border-bottom: 1px solid var(--jpm-line);
        padding-bottom: 2.3rem;
    }
    .qa-premium-copy, .qa-premium-visual-wrap {
        border: 0 !important;
        border-radius: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
        animation: none !important;
        padding: 0 !important;
    }
    .qa-premium-copy::before, .qa-premium-visual-wrap::before, .qa-premium-visual-wrap::after { display:none !important; }
    .qa-premium-title {
        font-size: clamp(2rem, 3.2vw, 4.2rem) !important;
        line-height: 1 !important;
        color: var(--jpm-ink) !important;
        margin: .75rem 0 .8rem !important;
    }
    .qa-premium-body {
        color: var(--jpm-muted) !important;
        max-width: 660px;
        font-size: 1rem !important;
        line-height: 1.9 !important;
    }
    .qa-premium-stats {
        display: grid !important;
        grid-template-columns: repeat(3, minmax(0,1fr)) !important;
        gap: 1rem !important;
        margin-top: 2rem !important;
    }
    .qa-premium-stat {
        border-radius: 0 !important;
        border: 0 !important;
        border-top: 2px solid rgba(155,106,47,.45) !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: .8rem 0 0 0 !important;
    }
    .qa-premium-stat b {
        color: var(--jpm-ink) !important;
        font-family: var(--qa-display) !important;
        font-size: 1.38rem !important;
        font-weight: 500 !important;
    }
    .qa-premium-stat span { color: var(--jpm-muted) !important; }
    .qa-premium-visual-wrap {
        min-height: 330px !important;
        background:
            linear-gradient(135deg, #21170f, #3a2206 60%, #6b4d25) !important;
        position: relative;
        overflow: hidden !important;
    }
    .qa-premium-visual-wrap::after {
        display: block !important;
        content: "";
        position: absolute;
        inset: 1.15rem;
        border: 1px solid rgba(255,250,242,.18);
        pointer-events: none;
    }

    /* Story blocks as JPM-style editorial links */
    .qa-story-grid {
        display: grid !important;
        grid-template-columns: repeat(3, minmax(0,1fr)) !important;
        gap: clamp(1.4rem, 3vw, 3.2rem) !important;
        margin: 1.2rem 0 2.2rem 0 !important;
    }
    .qa-story-card, .qa-card, .qa-visual-card {
        border-radius: 0 !important;
        border: 0 !important;
        border-top: 1px solid var(--jpm-line) !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: 1.2rem 0 1.5rem 0 !important;
        transform: none !important;
    }
    .qa-story-card::before, .qa-story-card::after, .qa-card::before, .qa-card::after { display: none !important; }
    .qa-story-card:hover, .qa-card:hover {
        transform: translateY(-3px) !important;
        border-color: rgba(155,106,47,.45) !important;
    }
    .qa-story-title, .qa-card-title, .qa-visual-title {
        color: var(--jpm-ink) !important;
        font-family: var(--qa-display) !important;
        font-size: 1.45rem !important;
        font-weight: 520 !important;
        line-height: 1.12 !important;
    }
    .qa-story-text, .qa-card-body, .qa-visual-body {
        color: var(--jpm-muted) !important;
        font-size: .95rem !important;
        line-height: 1.8 !important;
    }
    .qa-card-icon {
        color: var(--jpm-bronze) !important;
        background: transparent !important;
        margin-bottom: .6rem !important;
    }
    .qa-grid, .qa-grid-4, .qa-visual-grid {
        gap: clamp(1.4rem, 3vw, 3rem) !important;
    }

    /* Soft editorial notes */
    .qa-note-banner, .qa-callout, .stat-card {
        border: 0 !important;
        border-radius: 0 !important;
        border-left: 4px solid var(--jpm-bronze) !important;
        background: rgba(255,250,242,.58) !important;
        color: var(--jpm-ink-2) !important;
        box-shadow: none !important;
        padding: 1rem 1.2rem !important;
    }
    .qa-note-banner::before, .qa-note-banner::after, .qa-callout::before, .qa-callout::after, .stat-card::before, .stat-card::after { display: none !important; }

    /* Form and metrics: lighter, less widget-like */
    div[data-testid="metric-container"] {
        border-radius: 0 !important;
        border: 0 !important;
        border-top: 1px solid var(--jpm-line) !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: .95rem 0 !important;
    }
    div[data-testid="metric-container"] label {
        color: var(--jpm-muted) !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: var(--jpm-ink) !important;
        font-family: var(--qa-display) !important;
        font-weight: 520 !important;
    }
    .stButton button {
        border-radius: 0 !important;
        background: transparent !important;
        color: var(--jpm-ink) !important;
        border: 1px solid var(--jpm-ink) !important;
        box-shadow: none !important;
        padding: .62rem 1.4rem !important;
    }
    .stButton button:hover {
        background: var(--jpm-ink) !important;
        color: #fffaf2 !important;
        transform: none !important;
    }
    .stButton button[kind="primary"] {
        background: var(--jpm-ink) !important;
        color: #fffaf2 !important;
        border: 1px solid var(--jpm-ink) !important;
        box-shadow: none !important;
        animation: none !important;
    }
    .stButton button[kind="primary"]:hover {
        background: #3a2206 !important;
    }
    div[data-testid="stExpander"] {
        border-radius: 0 !important;
        border: 1px solid var(--jpm-line) !important;
        background: rgba(255,250,242,.60) !important;
        box-shadow: none !important;
    }
    [data-testid="stDataFrame"], div[data-testid="stTable"] {
        border-radius: 0 !important;
        border: 1px solid var(--jpm-line) !important;
        box-shadow: none !important;
    }

    /* Streamlit tab pills are restrained editorial chips */
    .stTabs [data-baseweb="tab"] {
        border-radius: 0 !important;
        border: 0 !important;
        border-bottom: 1px solid var(--jpm-line) !important;
        background: transparent !important;
        color: var(--jpm-ink-2) !important;
    }
    .stTabs [aria-selected="true"] {
        border-bottom: 2px solid var(--jpm-bronze) !important;
        color: var(--jpm-ink) !important;
        background: transparent !important;
    }

    @media (max-width: 1100px) {
        .qa-hero { min-height: auto; background: #fffaf2 !important; }
        .qa-hero-pro, .qa-premium-shell { grid-template-columns: 1fr !important; }
        .qa-hero-copy { padding: 2rem !important; }
        .qa-hero-visual { min-height: 320px !important; }
        .qa-badges, .qa-story-grid, .qa-premium-stats { grid-template-columns: 1fr !important; }
    }
</style>
"""), unsafe_allow_html=True)


st.markdown(dedent("""
<style>
/* JPM Layout Refinement v2: clear typography + real editorial structure */
:root{
  --jpm-ink:#17110b;--jpm-ink-2:#3f3329;--jpm-muted:#665a50;--jpm-paper:#fbf7ef;--jpm-line:rgba(61,42,24,.22);--jpm-line-strong:rgba(61,42,24,.36);--jpm-bronze:#8b5d28;--jpm-bronze-2:#b48343;--jpm-dark:#21170f;--jpm-focus:rgba(139,93,40,.28);
  --qa-display:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Noto Sans CJK SC","Microsoft YaHei","Hiragino Sans GB",Arial,sans-serif;
  --qa-body:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Noto Sans CJK SC","Microsoft YaHei","Hiragino Sans GB",Arial,sans-serif;
  --qa-mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}
html,body,.stApp,.block-container,.stMarkdown,.stText,.stCaption,.stTabs,.stAlert,label,p,span,div,li,td,th,a,button,input,textarea,select,[data-testid="stWidgetLabel"],[data-testid="stMetricLabel"],[data-testid="stMetricValue"]{font-family:var(--qa-body)!important;-webkit-font-smoothing:antialiased!important;-moz-osx-font-smoothing:grayscale!important;text-rendering:geometricPrecision!important;font-kerning:normal!important;}
h1,h2,h3,h4,h5,h6,.qa-title,.qa-page-header h2,.qa-premium-title,.qa-section-title h2,.qa-story-title,.qa-card-title,.qa-visual-title{font-family:var(--qa-display)!important;color:var(--jpm-ink)!important;letter-spacing:-.045em!important;font-weight:680!important;}
.stApp{background:radial-gradient(circle at 9% 0%,rgba(180,131,67,.13),transparent 32%),radial-gradient(circle at 90% 6%,rgba(20,58,90,.06),transparent 30%),linear-gradient(180deg,#fbf7ef 0%,#f5eddf 44%,#fbf8f2 100%)!important;color:var(--jpm-ink)!important;}
.block-container{max-width:1480px!important;padding:1.15rem clamp(1.2rem,2.2vw,2.2rem) 3rem!important;}

/* True JPM-like top nav + split hero */
.qa-global-nav{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:1.2rem;border-bottom:1px solid rgba(255,255,255,.20);padding:1.05rem clamp(1.2rem,2.8vw,2.6rem);color:#fffaf2!important;position:relative;z-index:3;}
.qa-global-brand{font-weight:760;letter-spacing:.08em;text-transform:uppercase;font-size:.86rem;color:#fffaf2!important;}.qa-global-links{display:flex;gap:clamp(.8rem,2vw,2rem);justify-content:center;color:rgba(255,250,242,.78)!important;font-size:.82rem;letter-spacing:.04em;text-transform:uppercase;}.qa-global-action{color:#fffaf2!important;border:1px solid rgba(255,250,242,.55);padding:.48rem .82rem;font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;}
.qa-hero{min-height:620px!important;margin:0 0 2.2rem!important;border:1px solid var(--jpm-line)!important;border-radius:0!important;box-shadow:0 30px 90px rgba(61,42,24,.12)!important;background:linear-gradient(90deg,rgba(255,253,248,.97) 0%,rgba(255,253,248,.93) 50%,rgba(33,23,15,.98) 50%,rgba(33,23,15,1) 100%)!important;padding:0!important;overflow:hidden!important;}
.qa-hero::before{content:""!important;position:absolute!important;inset:0!important;background:linear-gradient(90deg,transparent 0 49.92%,rgba(180,131,67,.52) 50%,transparent 50.13%),radial-gradient(circle at 73% 23%,rgba(180,131,67,.22),transparent 28%)!important;opacity:1!important;pointer-events:none}.qa-hero::after{display:none!important}.qa-hero-pro{display:grid!important;grid-template-columns:minmax(0,.98fr) minmax(460px,1.02fr)!important;gap:0!important;min-height:555px}.qa-hero-copy{padding:clamp(3.2rem,5vw,5.8rem) clamp(2.1rem,5vw,5.2rem)!important;align-self:center}.qa-hero-visual{min-height:555px!important;border:0!important;border-radius:0!important;background:radial-gradient(circle at 66% 24%,rgba(180,131,67,.28),transparent 28%),linear-gradient(180deg,#32200f 0%,#21170f 54%,#17110b 100%)!important;box-shadow:none!important}.qa-hero-visual::before{opacity:.10!important;background-size:56px 56px!important}
.qa-kicker,.qa-premium-eyebrow,.qa-story-tag,.qa-visual-kicker{display:inline-flex!important;font-family:var(--qa-body)!important;color:var(--jpm-bronze)!important;background:transparent!important;border:0!important;border-radius:0!important;padding:0!important;text-transform:uppercase!important;letter-spacing:.18em!important;font-size:.72rem!important;line-height:1.25!important;font-weight:760!important}.qa-title{color:var(--jpm-ink)!important;font-size:clamp(3.2rem,6vw,6.4rem)!important;line-height:.92!important;max-width:860px!important;margin:1rem 0 1.2rem!important;text-wrap:balance}.qa-subtitle{color:var(--jpm-ink-2)!important;font-size:clamp(1.02rem,1.15vw,1.16rem)!important;line-height:1.95!important;max-width:690px!important;letter-spacing:.005em!important}.qa-badges{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:.25rem 1.55rem!important;max-width:720px!important;margin-top:2.1rem!important}.qa-badge{border:0!important;border-top:1px solid var(--jpm-line)!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;color:var(--jpm-ink-2)!important;padding:.8rem 0 .55rem!important;font-size:.88rem!important;line-height:1.5!important}.qa-badge strong{color:var(--jpm-bronze)!important;margin-right:.4rem}

/* Editorial mastheads and section rhythm */
.qa-page-header{display:grid!important;grid-template-columns:minmax(0,.72fr) minmax(280px,.28fr)!important;gap:clamp(1.6rem,4vw,4.8rem)!important;align-items:end!important;padding:2.4rem 0 1.8rem!important;margin:.2rem 0 1.8rem!important;border:0!important;border-bottom:1px solid var(--jpm-line-strong)!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;overflow:visible!important}.qa-page-header::before,.qa-page-header::after{display:none!important}.qa-page-header h2{font-size:clamp(2.65rem,5.2vw,5.8rem)!important;line-height:.94!important;max-width:980px!important;margin:.75rem 0 .9rem!important}.qa-page-header p{color:var(--jpm-muted)!important;font-size:1.06rem!important;line-height:1.9!important;max-width:820px!important}.qa-page-aside{border-left:1px solid var(--jpm-line);padding-left:1.25rem;color:var(--jpm-muted)!important;font-size:.92rem;line-height:1.78}.qa-page-aside b{display:block;color:var(--jpm-ink);font-size:.82rem;letter-spacing:.16em;text-transform:uppercase;margin-bottom:.55rem}
.qa-section-title{display:grid!important;grid-template-columns:minmax(260px,.42fr) minmax(0,.58fr)!important;gap:clamp(1.4rem,3vw,3.6rem)!important;align-items:end!important;border-top:1px solid var(--jpm-line-strong)!important;padding-top:1.35rem!important;margin:2.4rem 0 1.2rem!important}.qa-section-title h2{font-size:clamp(1.85rem,3.2vw,3.25rem)!important;line-height:1.02!important;margin:0!important;color:var(--jpm-ink)!important}.qa-section-title span{color:var(--jpm-muted)!important;font-size:.98rem!important;line-height:1.75!important;letter-spacing:0!important;max-width:720px}

/* Cards -> insight indexes, not dashboard boxes */
.qa-grid,.qa-grid-4,.qa-story-grid,.qa-visual-grid{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:0!important;border-top:1px solid var(--jpm-line)!important;margin:.8rem 0 2.2rem!important}.qa-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}.qa-card,.qa-story-card,.qa-visual-card{border:0!important;border-right:1px solid var(--jpm-line)!important;border-bottom:1px solid var(--jpm-line)!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;min-height:210px!important;padding:clamp(1.2rem,2vw,1.8rem) clamp(1rem,1.8vw,1.55rem)!important;transform:none!important;transition:background .18s ease,transform .18s ease!important}.qa-card:nth-child(4n),.qa-story-card:nth-child(3n),.qa-visual-card:nth-child(3n){border-right:0!important}.qa-card::before,.qa-card::after,.qa-story-card::before,.qa-story-card::after,.qa-visual-card::before,.qa-visual-card::after{display:none!important}.qa-card:hover,.qa-story-card:hover,.qa-visual-card:hover{background:rgba(255,253,248,.62)!important;transform:translateY(-2px)!important}.qa-card-icon{color:var(--jpm-bronze)!important;background:transparent!important;border:0!important;padding:0!important;min-width:0!important;height:auto!important;font-size:.84rem!important;letter-spacing:.18em!important;margin-bottom:1.4rem!important}.qa-card-title,.qa-story-title,.qa-visual-title{font-size:clamp(1.28rem,1.7vw,1.82rem)!important;line-height:1.13!important;color:var(--jpm-ink)!important;margin-bottom:.72rem!important;font-weight:680!important}.qa-card-title::after,.qa-story-title::after{content:" →";color:var(--jpm-bronze);font-family:var(--qa-body);font-weight:650;letter-spacing:0}.qa-card-body,.qa-story-text,.qa-visual-body{color:var(--jpm-muted)!important;font-size:.96rem!important;line-height:1.82!important;letter-spacing:0!important}

/* Split feature blocks */
.qa-premium-shell{display:grid!important;grid-template-columns:minmax(0,.48fr) minmax(430px,.52fr)!important;gap:clamp(2rem,4vw,4.8rem)!important;align-items:center!important;padding:0 0 2.4rem!important;margin:.6rem 0 2.3rem!important;border-bottom:1px solid var(--jpm-line)!important}.qa-premium-copy,.qa-premium-visual-wrap{border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;padding:0!important;animation:none!important}.qa-premium-title{font-size:clamp(2.05rem,3.4vw,4.15rem)!important;line-height:.98!important;margin:.82rem 0 1rem!important;color:var(--jpm-ink)!important}.qa-premium-body{color:var(--jpm-muted)!important;font-size:1.02rem!important;line-height:1.9!important;max-width:680px!important}.qa-premium-stats{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:1.1rem!important;margin-top:2.1rem!important}.qa-premium-stat{border:0!important;border-top:2px solid rgba(139,93,40,.45)!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;padding:.85rem 0 0!important}.qa-premium-stat b{color:var(--jpm-ink)!important;font-size:1.32rem!important;font-weight:680!important;font-family:var(--qa-display)!important}.qa-premium-stat span{color:var(--jpm-muted)!important;font-size:.82rem!important}.qa-premium-visual-wrap{min-height:360px!important;background:linear-gradient(135deg,#21170f,#3b260f 60%,#72562d)!important;position:relative!important;overflow:hidden!important}.qa-premium-visual-wrap::before{display:block!important;content:""!important;position:absolute!important;inset:0!important;background-image:linear-gradient(rgba(255,250,242,.09) 1px,transparent 1px),linear-gradient(90deg,rgba(255,250,242,.06) 1px,transparent 1px)!important;background-size:44px 44px!important;opacity:.22!important;filter:none!important}.qa-premium-visual-wrap::after{display:block!important;content:""!important;position:absolute!important;inset:1.25rem!important;border:1px solid rgba(255,250,242,.18)!important;pointer-events:none}.qa-premium-visual *{font-family:var(--qa-body)!important}

/* Forms, metrics, tables: clearer and less boxed */
.qa-note-banner,.qa-callout,.stat-card,.qa-code-panel,.qa-guide-panel,.qa-mini-point{border:0!important;border-radius:0!important;border-left:4px solid var(--jpm-bronze)!important;background:rgba(255,253,248,.58)!important;color:var(--jpm-ink-2)!important;box-shadow:none!important;padding:1.05rem 1.25rem!important}.qa-note-banner::before,.qa-note-banner::after,.qa-callout::before,.qa-callout::after,.stat-card::before,.stat-card::after,.qa-code-panel::before{display:none!important}div[data-testid="metric-container"]{border:0!important;border-top:1px solid var(--jpm-line)!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;padding:1rem 0!important}div[data-testid="metric-container"] [data-testid="stMetricValue"]{color:var(--jpm-ink)!important;font-family:var(--qa-display)!important;font-weight:680!important;font-size:1.85rem!important}div[data-testid="metric-container"] label,div[data-testid="metric-container"] [data-testid="stMetricDelta"]{color:var(--jpm-muted)!important;font-size:.85rem!important}[data-testid="stWidgetLabel"] p,label p{color:var(--jpm-ink-2)!important;font-weight:680!important;font-size:.92rem!important}.stTextInput input,.stNumberInput input,.stTextArea textarea,div[data-baseweb="select"]>div,.stDateInput input{border-radius:0!important;border:1px solid var(--jpm-line-strong)!important;background:rgba(255,253,248,.72)!important;color:var(--jpm-ink)!important;box-shadow:none!important;font-size:.95rem!important}.stTextInput input:focus,.stNumberInput input:focus,.stTextArea textarea:focus{border-color:var(--jpm-bronze)!important;box-shadow:0 0 0 3px var(--jpm-focus)!important}.stButton button{border-radius:0!important;border:1px solid var(--jpm-ink)!important;color:var(--jpm-ink)!important;background:transparent!important;box-shadow:none!important;padding:.66rem 1.45rem!important;font-weight:680!important;letter-spacing:.03em!important}.stButton button:hover{color:#fffaf2!important;background:var(--jpm-ink)!important;transform:none!important}.stButton button[kind="primary"]{color:#fffaf2!important;background:var(--jpm-ink)!important;border-color:var(--jpm-ink)!important;animation:none!important}div[data-testid="stExpander"]{border:1px solid var(--jpm-line)!important;border-radius:0!important;background:rgba(255,253,248,.62)!important;box-shadow:none!important}div[data-testid="stExpander"] summary{color:var(--jpm-ink)!important;font-weight:680!important;font-size:.94rem!important}[data-testid="stDataFrame"],div[data-testid="stTable"]{border:1px solid var(--jpm-line)!important;border-radius:0!important;box-shadow:none!important;overflow:hidden!important}.stTabs [data-baseweb="tab-list"]{gap:0!important;border-bottom:1px solid var(--jpm-line)!important;background:transparent!important}.stTabs [data-baseweb="tab"]{border:0!important;border-radius:0!important;background:transparent!important;color:var(--jpm-muted)!important;padding:.74rem 1.15rem!important;font-weight:680!important}.stTabs [aria-selected="true"]{color:var(--jpm-ink)!important;border-bottom:2px solid var(--jpm-bronze)!important;background:transparent!important}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#21170f,#2b1b0d 52%,#17110b)!important}section[data-testid="stSidebar"] *{color:#fffaf2!important;font-family:var(--qa-body)!important}.sidebar-logo{background:#fffaf2!important;color:#21170f!important;border-radius:0!important}
@media(max-width:1100px){.qa-global-nav{grid-template-columns:1fr;gap:.6rem}.qa-global-links{justify-content:flex-start;flex-wrap:wrap}.qa-hero{min-height:auto!important;background:#fffdf8!important}.qa-hero-pro,.qa-page-header,.qa-premium-shell,.qa-section-title{grid-template-columns:1fr!important}.qa-hero-copy{padding:2rem!important}.qa-hero-visual{min-height:340px!important}.qa-grid,.qa-grid-4,.qa-story-grid,.qa-visual-grid,.qa-badges,.qa-premium-stats{grid-template-columns:1fr!important}.qa-card,.qa-story-card,.qa-visual-card{border-right:0!important}.qa-page-aside{border-left:0;border-top:1px solid var(--jpm-line);padding:1rem 0 0}}
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
    .qa-lens-grid {
        display:grid;
        grid-template-columns: 1.28fr .92fr;
        gap: 1rem;
        margin: 1rem 0 1.4rem 0;
        align-items: stretch;
    }
    .qa-photo-panel, .qa-photo-stack > div {
        position: relative;
        overflow: hidden;
        border: 1px solid var(--jpm-line);
        background: linear-gradient(180deg, rgba(255,255,255,.65), rgba(255,248,239,.88));
        box-shadow: var(--jpm-shadow);
    }
    .qa-photo-panel {
        min-height: 430px;
        border-radius: 28px 18px 42px 18px / 18px 34px 20px 38px;
    }
    .qa-photo-stack {
        display:grid;
        grid-template-rows: 1fr 1fr;
        gap: 1rem;
    }
    .qa-photo-stack > div {
        min-height: 205px;
        border-radius: 18px 30px 18px 36px / 18px 36px 18px 28px;
    }
    .qa-photo-panel::before, .qa-photo-stack > div::before {
        content:'';
        position:absolute; inset:0;
        background: linear-gradient(180deg, transparent 40%, rgba(33,23,15,.04) 100%);
        pointer-events:none; z-index:2;
    }
    .qa-photo-label {
        position:absolute; left: 1.15rem; bottom: 1.1rem; z-index:3;
        background: rgba(247,242,234,.82);
        backdrop-filter: blur(6px);
        border: 1px solid rgba(33,23,15,.10);
        border-radius: 999px;
        padding: .42rem .82rem;
        color: var(--jpm-ink); font-size: .76rem; font-weight: 600; letter-spacing: .03em;
    }
    .qa-photo-svg { width:100%; height:100%; display:block; }
    .qa-editorial-strip {
        display:grid; grid-template-columns: 1fr 1fr 1fr; gap:1rem; margin: 0 0 1.2rem 0;
    }
    .qa-editorial-card {
        border-top: 1px solid var(--jpm-line);
        padding-top: 0.95rem;
    }
    .qa-editorial-card h4 {
        font-family: var(--qa-display) !important;
        font-size: 1.18rem !important;
        line-height: 1.18 !important;
        color: var(--jpm-ink) !important;
        margin: 0 0 .42rem 0 !important;
    }
    .qa-editorial-card p {
        margin:0 !important; color: var(--jpm-ink-2) !important; line-height: 1.72 !important; font-size: .87rem !important;
    }
    @media (max-width: 1100px) {
        .qa-lens-grid, .qa-editorial-strip { grid-template-columns: 1fr; }
        .qa-photo-stack { grid-template-rows: none; grid-template-columns: 1fr; }
        .qa-photo-panel { min-height: 320px; }
    }
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
    html, body, [class*="css"] {
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }
    p, li, .qa-card-body, .qa-story-text, .qa-premium-body, .qa-visual-body, .qa-editorial-card p,
    .qa-page-header p, .qa-page-aside, .qa-subtitle, .qa-mini-point span {
        font-family: var(--qa-body) !important;
        line-height: 1.78 !important;
        letter-spacing: .003em !important;
    }
    .qa-title {
        font-size: clamp(2.8rem, 4vw, 4.9rem) !important;
        line-height: .98 !important;
        max-width: 11ch;
    }
    .qa-subtitle {
        max-width: 58ch;
        font-size: 1rem !important;
        color: var(--jpm-ink-2) !important;
    }
    .qa-badges {
        display: grid !important;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: .65rem !important;
        max-width: 800px;
    }
    .qa-badge {
        min-height: 52px;
        align-items: center;
    }
    .qa-page-header { align-items: end; }
    .qa-page-header h2 { font-size: 2.15rem !important; line-height: 1.02 !important; }
    .qa-page-header p { max-width: 56ch; font-size: .96rem !important; }
    .qa-page-aside {
        max-width: 26ch;
        font-size: .8rem !important;
        line-height: 1.7 !important;
    }
    .qa-premium-title { font-size: 1.48rem !important; line-height: 1.12 !important; }
    .qa-premium-body { font-size: .9rem !important; max-width: 58ch; }
    .qa-story-title { font-size: 1.02rem !important; }
    .qa-story-text, .qa-card-body, .qa-visual-body, .qa-editorial-card p {
        font-size: .85rem !important;
        color: var(--jpm-ink-2) !important;
    }
    .qa-section-title h2 { font-size: 1.9rem !important; }
    .qa-section-title span { max-width: 62ch; display:block; }
    .qa-card-title { font-size: 1.02rem !important; }
    .qa-mini-point b { font-size: .92rem !important; }
    .qa-code-panel p { max-width: 58ch; }

    .qa-visual-band {
        display:grid;
        grid-template-columns: minmax(0, .92fr) minmax(360px, 1.08fr);
        gap: 1rem;
        align-items: stretch;
        margin: .7rem 0 1.25rem 0;
    }
    .qa-visual-band-copy, .qa-visual-band-art {
        background: linear-gradient(180deg, rgba(255,255,255,.68), rgba(255,248,239,.9));
        border: 1px solid var(--jpm-line);
        box-shadow: var(--jpm-shadow);
        overflow: hidden;
        position: relative;
    }
    .qa-visual-band-copy {
        border-radius: 28px 16px 34px 18px / 18px 30px 20px 32px;
        padding: 1.28rem 1.32rem;
    }
    .qa-visual-band-art {
        border-radius: 18px 34px 18px 42px / 20px 40px 18px 34px;
        min-height: 260px;
    }
    .qa-visual-band-copy::before, .qa-visual-band-art::before {
        content:'';
        position:absolute;
        inset:0;
        background: radial-gradient(circle at 12% 14%, rgba(255,255,255,.45), transparent 30%);
        pointer-events:none;
    }
    .qa-band-kicker {
        display:inline-flex;
        margin-bottom: .65rem;
        padding: .28rem .64rem;
        border-radius: 999px;
        background: rgba(155,106,47,.08);
        border: 1px solid rgba(155,106,47,.14);
        color: var(--jpm-bronze);
        font-size: .68rem;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
    }
    .qa-visual-band-copy h3 {
        font-family: var(--qa-display) !important;
        color: var(--jpm-ink) !important;
        font-size: 1.82rem !important;
        line-height: 1.02 !important;
        margin: 0 0 .55rem 0 !important;
    }
    .qa-brief-grid {
        display:grid;
        grid-template-columns: 1fr;
        gap: .78rem;
        margin-top: .8rem;
    }
    .qa-brief-point {
        padding-top: .72rem;
        border-top: 1px solid rgba(58,34,6,.10);
        display:grid;
        grid-template-columns: 112px 1fr;
        gap: .7rem;
        align-items:start;
    }
    .qa-brief-point b {
        color: var(--jpm-ink);
        font-size: .78rem;
        letter-spacing: .08em;
        text-transform: uppercase;
    }
    .qa-brief-point span {
        color: var(--jpm-ink-2);
        font-size: .86rem;
        line-height: 1.72;
    }
    .qa-band-svg { width: 100%; height: 100%; display:block; }
    @media (max-width: 1100px) {
        .qa-visual-band, .qa-badges { grid-template-columns: 1fr !important; }
        .qa-visual-band-art { min-height: 220px; }
        .qa-brief-point { grid-template-columns: 1fr; gap: .3rem; }
    }
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
:root{
  --nl-display: -apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Hiragino Sans GB","Microsoft YaHei",Arial,sans-serif;
  --nl-body: -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",Arial,sans-serif;
  --nl-ink: #2b231a;
  --nl-copy: #53473b;
  --nl-muted: #736658;
  --nl-line: rgba(68,49,28,.14);
  --nl-soft: rgba(255,251,244,.78);
  --nl-bronze: #8d5e28;
}
html,body,.stApp,.block-container,[data-testid="stSidebar"],label,p,span,div,li,td,th,a,button,input,textarea,select,[data-testid="stWidgetLabel"],[data-testid="stMetricLabel"],[data-testid="stMetricValue"]{
  font-family:var(--nl-body)!important;
  color:var(--nl-copy);
  -webkit-font-smoothing:antialiased!important;
  -moz-osx-font-smoothing:grayscale!important;
  text-rendering:optimizeLegibility!important;
}
h1,h2,h3,h4,h5,h6,.qa-title,.qa-page-header h2,.qa-premium-title,.qa-section-title h2,.qa-card-title,.qa-story-title,.qa-visual-title,.qa-visual-band-copy h3,.qa-global-brand{
  font-family:var(--nl-display)!important;
  color:var(--nl-ink)!important;
  letter-spacing:-.032em!important;
}
.block-container{max-width:1420px!important;padding-top:1.1rem!important;padding-bottom:3rem!important}
label, [data-testid="stWidgetLabel"]{font-size:.92rem!important;line-height:1.45!important;font-weight:600!important;color:var(--nl-copy)!important}
[data-testid="stWidgetLabel"] p, label p{font-size:inherit!important;line-height:inherit!important;color:inherit!important}
.stCheckbox label, .stRadio label{font-size:1rem!important;font-weight:650!important;color:var(--nl-ink)!important}
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input{
  min-height:46px!important;
  font-size:.98rem!important;
  color:var(--nl-ink)!important;
  border:1px solid var(--nl-line)!important;
  background:rgba(255,251,244,.9)!important;
}
input::placeholder, textarea::placeholder{color:#9b907f!important;opacity:1!important}
.stSlider [data-baseweb="slider"]{padding-top:.2rem!important;padding-bottom:.5rem!important}
.stSlider [role="slider"]{box-shadow:none!important}
.stButton button, .stDownloadButton button{
  min-height:44px!important;
  font-size:.94rem!important;
  font-weight:700!important;
}
div[data-testid="metric-container"]{padding:1rem 0!important}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{font-size:2rem!important;font-weight:700!important;color:var(--nl-ink)!important}
div[data-testid="metric-container"] label,div[data-testid="metric-container"] [data-testid="stMetricDelta"]{font-size:.85rem!important;color:var(--nl-muted)!important}
.stMarkdown p, .stMarkdown li, .qa-card-body, .qa-story-text, .qa-premium-body, .qa-visual-body, .qa-editorial-card p, .qa-subtitle, .qa-page-aside, .qa-brief-point span{
  font-size:.94rem!important;
  line-height:1.8!important;
  color:var(--nl-copy)!important;
}
.qa-title{font-size:clamp(3.15rem,5vw,5.9rem)!important;line-height:.95!important;max-width:10.5ch!important}
.qa-subtitle{font-size:1.02rem!important;max-width:56ch!important}
.qa-page-header{padding-bottom:1rem!important;margin-bottom:1.2rem!important}
.qa-page-header h2{font-size:2.22rem!important;line-height:1.02!important}
.qa-page-header p{font-size:.98rem!important;max-width:54ch!important}
.qa-section-title h2{font-size:1.88rem!important}
.qa-card-title,.qa-story-title,.qa-visual-title{font-size:1.24rem!important;line-height:1.14!important}
.qa-premium-title{font-size:1.58rem!important;line-height:1.12!important}
.qa-premium-stat b{font-size:1.24rem!important}
.qa-note-banner,.qa-callout,.stat-card,.qa-code-panel,.qa-guide-panel,.qa-mini-point{
  background:rgba(255,251,244,.76)!important;
  border-left:3px solid var(--nl-bronze)!important;
}
label code, label small, summary code, summary small, [data-testid="InputInstructions"]{display:none!important}
.qa-micro-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;border-top:1px solid var(--nl-line);padding-top:.9rem;margin:.55rem 0 .85rem 0}
.qa-micro-title{font-family:var(--nl-display)!important;font-size:1.15rem!important;line-height:1.15!important;color:var(--nl-ink)!important;font-weight:700!important}
.qa-micro-caption{font-size:.82rem!important;line-height:1.6!important;color:var(--nl-muted)!important;max-width:40ch!important}
.qa-plain-panel{padding:.25rem 0 .25rem 0}
.qa-plain-panel .stDataFrame, .qa-plain-panel [data-testid="stDataFrame"]{margin-top:.25rem!important}
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
@keyframes nlFloatY {
  0%,100% { transform: translateY(0px); }
  50% { transform: translateY(-6px); }
}
@keyframes nlGlowSlide {
  0% { transform: translateX(-120%); opacity: 0; }
  25% { opacity: .28; }
  50% { opacity: .4; }
  100% { transform: translateX(220%); opacity: 0; }
}
@keyframes nlPulse {
  0%,100% { transform: scale(1); opacity: .78; }
  50% { transform: scale(1.18); opacity: 1; }
}
@keyframes nlFadeLift {
  0% { opacity: .55; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
.qa-hero, .qa-page-header, .qa-premium-shell, .qa-visual-band, .qa-home-image-story, .qa-feature-strip {
  animation: nlFadeLift .7s ease both;
}
.qa-card, .qa-story-card, .qa-visual-card, .qa-premium-stat, div[data-testid="metric-container"], .qa-feature-chip, .qa-guide-panel, .qa-code-panel, .qa-callout, .qa-note-banner {
  position: relative;
  overflow: hidden;
}
.qa-card::after, .qa-story-card::after, .qa-visual-card::after, .qa-premium-stat::after, .qa-feature-chip::after, div[data-testid="metric-container"]::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 42%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.14), transparent);
  transform: translateX(-140%);
  pointer-events: none;
}
.qa-card:hover::after, .qa-story-card:hover::after, .qa-visual-card:hover::after, .qa-premium-stat:hover::after, .qa-feature-chip:hover::after, div[data-testid="metric-container"]:hover::after {
  animation: nlGlowSlide 1.25s ease;
}
.qa-card:hover, .qa-story-card:hover, .qa-visual-card:hover {
  transform: translateY(-5px) !important;
  background: rgba(255,253,248,.86) !important;
}
.qa-premium-stat:hover, .qa-feature-chip:hover, div[data-testid="metric-container"]:hover {
  transform: translateY(-3px);
  transition: transform .24s ease;
}
.qa-premium-visual-wrap, .qa-visual-band-art, .qa-visual-frame, .qa-photo-panel, .qa-photo-stack > div {
  position: relative;
  overflow: hidden;
}
.qa-premium-visual-wrap::before, .qa-visual-band-art::before, .qa-visual-frame::before, .qa-photo-panel::before, .qa-photo-stack > div::before {
  animation: nlFloatY 9s ease-in-out infinite;
}
.qa-premium-visual-wrap::after, .qa-visual-band-art::after, .qa-visual-frame::after, .qa-photo-panel::after, .qa-photo-stack > div::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg, transparent 0%, rgba(255,255,255,.045) 48%, transparent 76%);
  mix-blend-mode: screen;
  pointer-events: none;
}
.qa-badge, .qa-brief-point, .qa-mini-point {
  transition: transform .22s ease, border-color .22s ease, background .22s ease;
}
.qa-badge:hover, .qa-brief-point:hover, .qa-mini-point:hover {
  transform: translateX(4px);
}
.stButton button, .stDownloadButton button {
  transition: transform .18s ease, box-shadow .18s ease, background .18s ease, color .18s ease !important;
}
.stButton button:hover, .stDownloadButton button:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(33,23,15,.10);
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus, .stDateInput input:focus, div[data-baseweb="select"]:focus-within {
  transform: translateY(-1px);
  transition: transform .18s ease;
}
.qa-feature-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .9rem;
  margin: .4rem 0 1.45rem 0;
}
.qa-feature-chip {
  border-top: 1px solid rgba(68,49,28,.15);
  border-bottom: 1px solid rgba(68,49,28,.08);
  padding: .95rem 0 .9rem 0;
  display: grid;
  grid-template-columns: 14px 1fr;
  gap: .72rem;
  align-items: start;
  transition: transform .22s ease, background .22s ease;
}
.qa-feature-dot {
  width: 8px;
  height: 8px;
  margin-top: .32rem;
  border-radius: 50%;
  background: var(--nl-bronze, #8d5e28);
  box-shadow: 0 0 0 6px rgba(141,94,40,.08);
  animation: nlPulse 2.2s ease-in-out infinite;
}
.qa-feature-copy b {
  display: block;
  color: var(--nl-ink, #2b231a);
  font-family: var(--nl-display, var(--qa-display)) !important;
  font-size: 1rem;
  line-height: 1.15;
  margin-bottom: .22rem;
}
.qa-feature-copy span {
  display: block;
  color: var(--nl-copy, #53473b);
  font-size: .84rem;
  line-height: 1.68;
}
div[data-testid="stProgressBar"] > div > div > div > div {
  background: linear-gradient(90deg, #8d5e28, #c89d62, #2d5f8b) !important;
}
@media (max-width: 1100px) {
  .qa-feature-strip { grid-template-columns: 1fr; }
}
</style>
"""), unsafe_allow_html=True)



st.markdown(dedent("""
<style>
:root{
  --rb-ink:#201911; --rb-copy:#5B5146; --rb-muted:#7A6F63; --rb-line:rgba(72,53,33,.14);
  --rb-strong:rgba(72,53,33,.22); --rb-paper:#F7F2EA; --rb-soft:#FCF8F2; --rb-bronze:#8A5A24;
  --rb-blue:#335F86; --rb-green:#2F7D73; --rb-red:#B4544C;
}
html, body, .stApp { background: linear-gradient(180deg,#F7F2EA 0%, #FBF8F3 36%, #F7F2EA 100%) !important; }
.block-container{ max-width: 1460px !important; padding-top: 1rem !important; }
[data-testid="stSidebar"]{ background: linear-gradient(180deg,#19130f 0%, #261b12 100%) !important; border-right: 1px solid rgba(255,255,255,.06) !important; }
.sidebar-container, .sidebar-nav { background: transparent !important; }
.sidebar-logo { background: linear-gradient(135deg,#8A5A24,#C89B5E) !important; box-shadow: 0 10px 22px rgba(138,90,36,.28) !important; }
.sidebar-brand,.sidebar-subtitle,.sidebar-footer{ color: rgba(255,248,240,.92) !important; }
button[kind="primary"], .stDownloadButton button[kind="primary"] { background: linear-gradient(135deg,#8A5A24,#A9783F) !important; border: 0 !important; }
button[kind="secondary"] { background: rgba(255,255,255,.03) !important; border: 1px solid rgba(255,255,255,.08) !important; }
.qa-hero{ background: linear-gradient(90deg, rgba(255,252,246,.98) 0%, rgba(255,252,246,.94) 52%, #221a13 52%, #17110c 100%) !important; min-height: 640px !important; box-shadow: 0 20px 64px rgba(70,45,18,.10) !important; }
.qa-hero::before{ background: linear-gradient(90deg,transparent 0 51.85%, rgba(200,155,94,.58) 52%, transparent 52.15%), radial-gradient(circle at 74% 21%, rgba(200,155,94,.28), transparent 30%) !important; }
.qa-title{ font-size: clamp(3.25rem,5.8vw,6.25rem) !important; max-width: 9.5ch !important; }
.qa-subtitle{ max-width: 54ch !important; color: var(--rb-copy) !important; }
.qa-badge{ border-top: 1px solid var(--rb-line) !important; color: var(--rb-copy) !important; }
.qa-badge strong{ color: var(--rb-bronze) !important; }
.qa-page-header{ padding: 2.1rem 0 1.4rem !important; margin-bottom: 1.4rem !important; }
.qa-page-header h2{ font-size: clamp(2.35rem,4.8vw,4.9rem) !important; }
.qa-page-header p, .qa-page-aside, .qa-section-title span{ color: var(--rb-copy) !important; }
.qa-page-aside{ border-left: 1px solid var(--rb-strong) !important; }
.qa-section-title{ border-top: 1px solid var(--rb-strong) !important; margin: 2rem 0 1rem !important; }
.qa-grid, .qa-grid-4, .qa-story-grid, .qa-visual-grid{ border-top: 1px solid var(--rb-line) !important; }
.qa-card, .qa-story-card, .qa-visual-card{ transition: transform .25s ease, background .25s ease, box-shadow .25s ease !important; }
.qa-card:hover, .qa-story-card:hover, .qa-visual-card:hover{ background: rgba(255,255,255,.58) !important; box-shadow: inset 0 0 0 1px rgba(138,90,36,.05) !important; }
.qa-premium-shell, .qa-visual-band{ border-bottom: 1px solid var(--rb-line) !important; }
.qa-premium-copy, .qa-visual-band-copy{ padding-right: 1rem !important; }
.qa-premium-body, .qa-story-text, .qa-card-body, .qa-visual-body, .qa-brief-point span{ color: var(--rb-copy) !important; }
.qa-premium-visual-wrap, .qa-visual-band-art, .qa-visual-frame{ background: linear-gradient(180deg,#20170f 0%, #17110c 100%) !important; border: 1px solid rgba(138,90,36,.12) !important; }
.qa-premium-stat, .qa-feature-chip, .qa-mini-point, .qa-guide-panel, .qa-code-panel{ background: rgba(255,255,255,.34) !important; border-color: rgba(72,53,33,.08) !important; }
.qa-note-banner, .qa-callout{ background: linear-gradient(90deg, rgba(138,90,36,.08), rgba(51,95,134,.04)) !important; color: var(--rb-copy) !important; border: 1px solid rgba(138,90,36,.10) !important; }
[data-testid="stDataFrame"], div[data-testid="stTable"]{ border:1px solid rgba(72,53,33,.10) !important; box-shadow:none !important; background:#FFFCF8 !important; }
[data-testid="stMetricValue"]{ color: var(--rb-ink) !important; }
.js-plotly-plot{ border:1px solid rgba(72,53,33,.10); background:#FBF7F0; border-radius: 0; padding:.25rem .25rem .1rem .25rem; }
.stTabs [data-baseweb="tab-list"]{ border-bottom:1px solid rgba(72,53,33,.12) !important; }
.stTabs [data-baseweb="tab"]{ padding-left:0 !important; padding-right:1.1rem !important; }
.qa-feature-strip{ margin-top:.2rem !important; margin-bottom:1.35rem !important; }
.qa-feature-chip{ border-top: 1px solid var(--rb-line) !important; }
.qa-feature-copy b{ color: var(--rb-ink) !important; }
.qa-feature-copy span{ color: var(--rb-copy) !important; }
.stMarkdown h3{ font-size:1.3rem !important; color:var(--rb-ink) !important; margin-top: .8rem !important; }
.stMarkdown h4{ color:var(--rb-ink) !important; }
.stCaption{ color: var(--rb-muted) !important; }
</style>
"""), unsafe_allow_html=True)

# Final institutional design layer. Keeping it separate makes the visual system
# auditable without touching any research, backtest or execution logic.
_institutional_css = os.path.join(os.path.dirname(__file__), "institutional.css")
with open(_institutional_css, "r", encoding="utf-8") as _css_file:
    st.markdown(f"<style>{_css_file.read()}</style>", unsafe_allow_html=True)

def render_html(markup: str):
    """安全渲染自定义 HTML：去除 Markdown 缩进，避免 <div> 被误判成代码块。"""
    st.markdown(dedent(markup).strip(), unsafe_allow_html=True)




def ui_micro_head(title: str, caption: str = ""):
    extra = f'<div class="qa-micro-caption">{escape(caption)}</div>' if caption else ''
    render_html(f'<div class="qa-micro-head"><div class="qa-micro-title">{escape(title)}</div>{extra}</div>')



def ui_feature_strip(items):
    blocks = []
    for title, desc in items:
        blocks.append(f'<div class="qa-feature-chip"><div class="qa-feature-dot"></div><div class="qa-feature-copy"><b>{escape(str(title))}</b><span>{escape(str(desc))}</span></div></div>')
    render_html('<div class="qa-feature-strip">' + ''.join(blocks) + '</div>')

def ui_hero():
    render_html("""
    <div class="qa-hero">
        <div class="qa-global-nav"><div class="qa-global-brand">Nailong Capital</div><div class="qa-global-links"><span>Research</span><span>Backtest</span><span>Portfolio</span><span>Execution</span></div><div class="qa-global-action">Institutional Demo</div></div>
        <div class="qa-hero-pro">
            <div class="qa-hero-copy">
                <div class="qa-kicker">Nailong Capital Quant Intelligence</div>
                <h1 class="qa-title">奶龙资本量化交易平台</h1>
                <p class="qa-subtitle">以更清晰的标题、分区与视觉内容，把研究、验证与执行组织成一套机构级产品体验。</p>
                <div class="qa-badges"><span class="qa-badge"><strong>01</strong> Research & Signal Discovery</span><span class="qa-badge"><strong>02</strong> Backtesting & Attribution</span><span class="qa-badge"><strong>03</strong> Portfolio Validation</span><span class="qa-badge"><strong>04</strong> Execution Workflow</span></div>
            </div>
            <div class="qa-hero-visual"><svg class="qa-hero-svg" viewBox="0 0 680 555" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="jpLine2" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#d8b16a"/><stop offset="55%" stop-color="#fff1cb"/><stop offset="100%" stop-color="#8ab9d6"/></linearGradient><radialGradient id="jpGlow2" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#d8b16a" stop-opacity=".40"/><stop offset="100%" stop-color="#d8b16a" stop-opacity="0"/></radialGradient></defs><rect width="680" height="555" fill="transparent"/><circle cx="468" cy="176" r="126" fill="url(#jpGlow2)"><animate attributeName="r" values="116;150;116" dur="7s" repeatCount="indefinite"/></circle><g opacity=".16" stroke="#fffaf2"><path d="M60 112H620"/><path d="M60 196H620"/><path d="M60 280H620"/><path d="M60 364H620"/><path d="M60 448H620"/><path d="M120 82V480"/><path d="M240 82V480"/><path d="M360 82V480"/><path d="M480 82V480"/><path d="M600 82V480"/></g><path d="M70 410 C126 370, 176 312, 230 328 S330 402, 384 314 S494 138, 610 118" fill="none" stroke="url(#jpLine2)" stroke-width="5" stroke-linecap="round" stroke-dasharray="980" stroke-dashoffset="980"><animate attributeName="stroke-dashoffset" values="980;0" dur="5.4s" repeatCount="indefinite"/></path><path d="M70 444 C146 414, 202 386, 290 388 S430 328, 610 274" fill="none" stroke="#fffaf2" stroke-opacity=".30" stroke-width="2" stroke-linecap="round" stroke-dasharray="820" stroke-dashoffset="820"><animate attributeName="stroke-dashoffset" values="820;0" dur="7.4s" repeatCount="indefinite"/></path><g transform="translate(92,112)"><rect width="214" height="98" fill="rgba(255,250,242,.055)" stroke="rgba(255,250,242,.20)"/><text x="22" y="36" fill="#d8b16a" font-size="13" font-family="Arial, sans-serif" letter-spacing="2">SIGNAL QUALITY</text><text x="22" y="73" fill="#fffaf2" font-size="36" font-family="Arial, sans-serif" font-weight="650">86.4</text></g><g transform="translate(392,350)"><rect width="220" height="92" fill="rgba(255,250,242,.055)" stroke="rgba(255,250,242,.20)"/><text x="22" y="36" fill="#d8b16a" font-size="13" font-family="Arial, sans-serif" letter-spacing="2">PORTFOLIO FLOW</text><text x="22" y="70" fill="#fffaf2" font-size="32" font-family="Arial, sans-serif" font-weight="650">+18.4%</text></g></svg></div>
        </div>
    </div>
    """)



def ui_home_image_story():
    render_html("""
    <div class="qa-section-title"><h2>Platform imagery</h2><span>用更精致的视觉内容强化首页质感，让平台更像成熟金融产品。</span></div>
    <div class="qa-lens-grid">
        <div class="qa-photo-panel">
            <svg class="qa-photo-svg" viewBox="0 0 860 520" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <linearGradient id="nlSky" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#f7f0e4"/>
                        <stop offset="100%" stop-color="#efe1c6"/>
                    </linearGradient>
                    <linearGradient id="nlGlass" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0%" stop-color="#173957" stop-opacity=".92"/>
                        <stop offset="100%" stop-color="#496781" stop-opacity=".88"/>
                    </linearGradient>
                    <linearGradient id="nlLine" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stop-color="#9b6a2f"/>
                        <stop offset="55%" stop-color="#f4d8a4"/>
                        <stop offset="100%" stop-color="#19507c"/>
                    </linearGradient>
                </defs>
                <rect width="860" height="520" fill="url(#nlSky)"/>
                <rect y="358" width="860" height="162" fill="#e6d7bd"/>
                <g fill="#7f6f61" opacity=".65">
                    <rect x="58" y="166" width="86" height="192"/><rect x="152" y="124" width="66" height="234"/><rect x="224" y="146" width="58" height="212"/><rect x="292" y="82" width="122" height="276"/><rect x="424" y="162" width="74" height="196"/><rect x="506" y="134" width="88" height="224"/><rect x="602" y="176" width="66" height="182"/><rect x="676" y="108" width="102" height="250"/>
                </g>
                <g transform="translate(86,54)">
                    <rect width="664" height="270" rx="18" fill="url(#nlGlass)"/>
                    <g opacity=".16" stroke="#fdf8ef">
                        <path d="M28 40H636"/><path d="M28 92H636"/><path d="M28 144H636"/><path d="M28 196H636"/><path d="M28 248H636"/>
                        <path d="M92 22V248"/><path d="M196 22V248"/><path d="M300 22V248"/><path d="M404 22V248"/><path d="M508 22V248"/><path d="M612 22V248"/>
                    </g>
                    <path d="M30 214 C92 196, 122 132, 178 136 S268 224, 326 178 S434 76, 486 90 S558 158, 632 72" fill="none" stroke="url(#nlLine)" stroke-width="5" stroke-linecap="round"/>
                    <circle cx="632" cy="72" r="7" fill="#f5e0b6"/>
                    <rect x="52" y="42" width="170" height="62" rx="14" fill="rgba(255,255,255,.10)" stroke="rgba(255,255,255,.20)"/>
                    <text x="72" y="68" fill="#f6ead7" font-size="13" font-family="Arial, sans-serif" letter-spacing="2">DAILY ALPHA TRACKER</text>
                    <text x="72" y="92" fill="#ffffff" font-size="28" font-family="Arial, sans-serif" font-weight="700">+12.7%</text>
                    <rect x="478" y="176" width="126" height="54" rx="14" fill="rgba(255,255,255,.10)" stroke="rgba(255,255,255,.20)"/>
                    <text x="498" y="199" fill="#f6ead7" font-size="11" font-family="Arial, sans-serif" letter-spacing="1.2">SIGNAL SCORE</text>
                    <text x="498" y="219" fill="#ffffff" font-size="23" font-family="Arial, sans-serif" font-weight="700">89 / 100</text>
                </g>
            </svg>
            <div class="qa-photo-label">首页主视觉 · Capital Markets Dashboard</div>
        </div>
        <div class="qa-photo-stack">
            <div>
                <svg class="qa-photo-svg" viewBox="0 0 420 240" xmlns="http://www.w3.org/2000/svg">
                    <defs><linearGradient id="deskA" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#1c3854"/><stop offset="100%" stop-color="#496782"/></linearGradient></defs>
                    <rect width="420" height="240" fill="#f2e8d7"/>
                    <rect x="48" y="42" width="138" height="92" rx="12" fill="url(#deskA)"/>
                    <rect x="198" y="42" width="176" height="92" rx="12" fill="url(#deskA)"/>
                    <rect x="48" y="148" width="326" height="38" rx="10" fill="#ded1b8"/>
                    <g opacity=".18" stroke="#fff"><path d="M62 62H174"/><path d="M62 90H174"/><path d="M214 64H358"/><path d="M214 90H358"/></g>
                    <path d="M68 110 C88 100, 106 76, 128 84 S168 112, 174 68" fill="none" stroke="#efca87" stroke-width="4"/>
                    <path d="M220 114 C246 100, 276 90, 304 96 S340 84, 360 64" fill="none" stroke="#efca87" stroke-width="4"/>
                    <g fill="#8a775f"><rect x="76" y="158" width="44" height="18" rx="9"/><rect x="128" y="158" width="64" height="18" rx="9"/><rect x="202" y="158" width="36" height="18" rx="9"/></g>
                </svg>
                <div class="qa-photo-label">研究终端 · Multi-screen Research Desk</div>
            </div>
            <div>
                <svg class="qa-photo-svg" viewBox="0 0 420 240" xmlns="http://www.w3.org/2000/svg">
                    <rect width="420" height="240" fill="#f4ead8"/>
                    <circle cx="322" cy="70" r="36" fill="#e6cf9c" opacity=".7"/>
                    <g fill="#173957" opacity=".9">
                        <path d="M70 172 L112 94 L162 138 L212 78 L260 122 L314 64 L350 106 L320 172 Z"/>
                    </g>
                    <g fill="#fff7ec"><circle cx="112" cy="94" r="5"/><circle cx="162" cy="138" r="5"/><circle cx="212" cy="78" r="5"/><circle cx="260" cy="122" r="5"/><circle cx="314" cy="64" r="5"/></g>
                    <path d="M66 182 H350" stroke="#8e7a63" stroke-width="2"/>
                    <rect x="64" y="192" width="92" height="18" rx="9" fill="#d9c8a8"/><rect x="164" y="192" width="124" height="18" rx="9" fill="#ded0b6"/>
                    <text x="64" y="40" fill="#6f5d49" font-size="14" font-family="Arial, sans-serif" letter-spacing="2">A-SHARE OPPORTUNITY MAP</text>
                </svg>
                <div class="qa-photo-label">市场洞察 · Opportunity Map</div>
            </div>
        </div>
    </div>
    <div class="qa-editorial-strip">
        <div class="qa-editorial-card"><h4>强化品牌识别</h4><p>主视觉与研究场景图像提升首页辨识度与信任感。</p></div>
        <div class="qa-editorial-card"><h4>数据与场景同屏</h4><p>趋势图、研究屏幕与市场地图共同呈现，兼顾数据感与展示力。</p></div>
        <div class="qa-editorial-card"><h4>适合演示与汇报</h4><p>更适合路演、业务介绍与客户展示。</p></div>
    </div>
    """)



def page_art_svg(variant: str = "home") -> str:
    svgs = {
        "backtest": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="btA" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#9b6a2f"/><stop offset="52%" stop-color="#f0d6a1"/><stop offset="100%" stop-color="#1e4f77"/></linearGradient></defs><rect width="760" height="340" fill="#f3e8d6"/><g fill="#ddcfb4"><rect x="38" y="66" width="210" height="208" rx="18"/><rect x="268" y="48" width="454" height="244" rx="22"/></g><g transform="translate(292,70)"><rect width="406" height="200" rx="16" fill="#173957" opacity=".96"/><g opacity=".14" stroke="#fff"><path d="M22 34H384"/><path d="M22 78H384"/><path d="M22 122H384"/><path d="M22 166H384"/><path d="M74 18V182"/><path d="M148 18V182"/><path d="M222 18V182"/><path d="M296 18V182"/></g><path d="M24 160 C88 148, 128 96, 180 106 S258 178, 316 122 S360 70, 388 56" fill="none" stroke="url(#btA)" stroke-width="5" stroke-linecap="round"/><circle cx="388" cy="56" r="7" fill="#f0d6a1"/><rect x="30" y="28" width="144" height="56" rx="12" fill="rgba(255,255,255,.10)" stroke="rgba(255,255,255,.18)"/><text x="48" y="52" fill="#f7ead2" font-size="11" font-family="Arial" letter-spacing="1.6">BACKTEST SCORE</text><text x="48" y="72" fill="#ffffff" font-size="24" font-family="Arial" font-weight="700">82.4</text></g><g fill="#8a785f"><rect x="64" y="102" width="132" height="14" rx="7"/><rect x="64" y="132" width="104" height="14" rx="7"/><rect x="64" y="190" width="146" height="14" rx="7"/><rect x="64" y="220" width="88" height="14" rx="7"/></g></svg>',
        "portfolio": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="pfA" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#173957"/><stop offset="100%" stop-color="#4b6a83"/></linearGradient></defs><rect width="760" height="340" fill="#f4ead8"/><rect x="42" y="58" width="228" height="222" rx="20" fill="#e3d3b4"/><rect x="292" y="46" width="426" height="248" rx="24" fill="url(#pfA)"/><g transform="translate(316,70)" opacity=".18" stroke="#fff"><path d="M0 40H378"/><path d="M0 88H378"/><path d="M0 136H378"/><path d="M0 184H378"/></g><g transform="translate(314,66)"><path d="M20 176 C86 156, 132 128, 176 136 S262 154, 360 70" fill="none" stroke="#efcb8a" stroke-width="5" stroke-linecap="round"/><path d="M20 196 C88 186, 132 174, 188 168 S278 150, 360 128" fill="none" stroke="#fff6e8" stroke-opacity=".58" stroke-width="3" stroke-linecap="round"/></g><g fill="#173957"><circle cx="112" cy="126" r="58" fill="#173957" opacity=".95"/><circle cx="112" cy="126" r="33" fill="#f4ead8" opacity=".96"/></g><g fill="#8d7c63"><rect x="66" y="216" width="160" height="14" rx="7"/><rect x="66" y="242" width="118" height="14" rx="7"/></g><text x="324" y="94" fill="#f6ead4" font-size="12" font-family="Arial" letter-spacing="2">ALLOCATION LENS</text><text x="324" y="124" fill="#ffffff" font-size="26" font-family="Arial" font-weight="700">5 Assets / 3 Layers</text></svg>',
        "screener": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><rect width="760" height="340" fill="#f4ead9"/><rect x="48" y="54" width="188" height="232" rx="20" fill="#e4d4b8"/><rect x="260" y="54" width="454" height="232" rx="22" fill="#173957"/><g transform="translate(78,92)" fill="#8d7c63"><rect x="0" y="0" width="124" height="14" rx="7"/><rect x="0" y="28" width="96" height="14" rx="7"/><rect x="0" y="84" width="132" height="12" rx="6"/><rect x="0" y="108" width="84" height="12" rx="6"/></g><g transform="translate(292,92)"><rect x="0" y="0" width="116" height="36" rx="12" fill="rgba(255,255,255,.10)"/><rect x="132" y="0" width="116" height="36" rx="12" fill="rgba(255,255,255,.10)"/><rect x="264" y="0" width="116" height="36" rx="12" fill="rgba(255,255,255,.10)"/><g fill="#efcb8a"><rect x="18" y="120" width="22" height="62" rx="6"/><rect x="62" y="90" width="22" height="92" rx="6"/><rect x="106" y="128" width="22" height="54" rx="6"/><rect x="150" y="74" width="22" height="108" rx="6"/><rect x="194" y="102" width="22" height="80" rx="6"/></g><circle cx="332" cy="118" r="38" fill="rgba(255,255,255,.08)" stroke="rgba(255,255,255,.18)"/><text x="332" y="126" text-anchor="middle" fill="#ffffff" font-size="28" font-family="Arial" font-weight="700">Top</text><path d="M356 144 L388 176" stroke="#efcb8a" stroke-width="4" stroke-linecap="round"/></g></svg>',
        "paper": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><rect width="760" height="340" fill="#f4ead8"/><rect x="48" y="48" width="664" height="246" rx="24" fill="#173957"/><g opacity=".16" stroke="#fff"><path d="M76 102H684"/><path d="M76 154H684"/><path d="M76 206H684"/><path d="M76 258H684"/></g><rect x="84" y="84" width="180" height="82" rx="18" fill="rgba(255,255,255,.10)"/><rect x="284" y="84" width="220" height="82" rx="18" fill="rgba(255,255,255,.10)"/><rect x="524" y="84" width="148" height="150" rx="18" fill="rgba(255,255,255,.10)"/><text x="108" y="112" fill="#f5e8d0" font-size="12" font-family="Arial" letter-spacing="1.8">CASH BALANCE</text><text x="108" y="144" fill="#ffffff" font-size="28" font-family="Arial" font-weight="700">¥1,000,000</text><path d="M308 144 C334 130, 370 120, 402 122 S456 114, 484 94" fill="none" stroke="#efcb8a" stroke-width="4" stroke-linecap="round"/><g fill="#efcb8a"><rect x="548" y="138" width="18" height="54" rx="5"/><rect x="578" y="122" width="18" height="70" rx="5"/><rect x="608" y="102" width="18" height="90" rx="5"/></g></svg>',
        "engine": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><rect width="760" height="340" fill="#f3ead9"/><rect x="58" y="84" width="136" height="74" rx="18" fill="#173957"/><rect x="314" y="52" width="136" height="74" rx="18" fill="#173957"/><rect x="314" y="202" width="136" height="74" rx="18" fill="#173957"/><rect x="568" y="84" width="136" height="74" rx="18" fill="#173957"/><g stroke="#efcb8a" stroke-width="4" fill="none" stroke-linecap="round"><path d="M194 121H314"/><path d="M450 89H522Q570 89 570 121"/><path d="M450 239H522Q570 239 570 121"/></g><g fill="#8d7c63"><rect x="74" y="180" width="104" height="14" rx="7"/><rect x="74" y="206" width="86" height="14" rx="7"/></g><circle cx="636" cy="121" r="8" fill="#efcb8a"/><text x="328" y="94" fill="#f6ead4" font-size="12" font-family="Arial" letter-spacing="2">EXECUTION LOOP</text><text x="328" y="238" fill="#f6ead4" font-size="12" font-family="Arial" letter-spacing="2">RISK FILTER</text></svg>',
        "guide": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><rect width="760" height="340" fill="#f4ead8"/><rect x="54" y="50" width="652" height="240" rx="24" fill="#173957"/><rect x="88" y="88" width="302" height="52" rx="14" fill="rgba(255,255,255,.10)"/><rect x="88" y="160" width="246" height="92" rx="16" fill="rgba(255,255,255,.10)"/><rect x="362" y="160" width="302" height="92" rx="16" fill="rgba(255,255,255,.10)"/><g fill="#f7ead2" font-family="Arial"><text x="114" y="120" font-size="13" letter-spacing="1.8">PLAYBOOK</text><text x="114" y="216" font-size="26" font-weight="700">Research Flow</text></g><path d="M394 226 L444 186 L488 206 L550 154" fill="none" stroke="#efcb8a" stroke-width="5" stroke-linecap="round"/><g fill="#8d7c63"><rect x="112" y="188" width="84" height="12" rx="6"/><rect x="112" y="212" width="106" height="12" rx="6"/></g></svg>',
        "about": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><rect width="760" height="340" fill="#f4ead8"/><circle cx="178" cy="170" r="94" fill="#173957"/><circle cx="178" cy="170" r="58" fill="#f4ead8"/><text x="178" y="184" text-anchor="middle" fill="#173957" font-size="52" font-family="Arial" font-weight="700">NL</text><rect x="306" y="70" width="376" height="54" rx="16" fill="#e3d3b6"/><rect x="306" y="144" width="376" height="54" rx="16" fill="#e8dcc3"/><rect x="306" y="218" width="248" height="34" rx="14" fill="#e3d3b6"/><g fill="#6f5d49"><rect x="334" y="92" width="168" height="12" rx="6"/><rect x="334" y="166" width="204" height="12" rx="6"/><rect x="334" y="229" width="116" height="10" rx="5"/></g></svg>',
        "home": '<svg class="qa-band-svg" viewBox="0 0 760 340" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="hmA" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#9b6a2f"/><stop offset="50%" stop-color="#f0d6a1"/><stop offset="100%" stop-color="#173957"/></linearGradient></defs><rect width="760" height="340" fill="#f4ead8"/><rect x="48" y="46" width="664" height="248" rx="22" fill="#173957"/><g opacity=".16" stroke="#fff"><path d="M74 94H684"/><path d="M74 146H684"/><path d="M74 198H684"/><path d="M74 250H684"/></g><path d="M80 230 C138 214, 180 154, 234 162 S328 242, 392 178 S486 70, 554 98 S628 136, 680 92" fill="none" stroke="url(#hmA)" stroke-width="5" stroke-linecap="round"/><rect x="94" y="82" width="170" height="60" rx="14" fill="rgba(255,255,255,.10)"/><text x="118" y="108" fill="#f7ead2" font-size="12" font-family="Arial" letter-spacing="1.8">Nailong Capital</text><text x="118" y="132" fill="#ffffff" font-size="26" font-family="Arial" font-weight="700">Quant Platform</text></svg>'
    }
    return svgs.get(variant, svgs["home"])


def ui_page_visual_block(eyebrow: str, title: str, points, variant: str = "home"):
    items = ''.join([f'<div class="qa-brief-point"><b>{escape(str(k))}</b><span>{escape(str(v))}</span></div>' for k, v in points])
    render_html(f'<div class="qa-visual-band"><div class="qa-visual-band-copy"><div class="qa-band-kicker">{escape(eyebrow)}</div><h3>{escape(title)}</h3><div class="qa-brief-grid">{items}</div></div><div class="qa-visual-band-art">{page_art_svg(variant)}</div></div>')

def ui_visual_showcase():
    render_html("""
    <div class="qa-section-title"><h2>Market perspectives</h2><span>以简洁洞察入口呈现市场、信号与流程。</span></div>
    <div class="qa-visual-grid">
      <div class="qa-visual-card"><div class="qa-visual-kicker">Markets</div><div class="qa-visual-title">动态行情脉冲</div><div class="qa-visual-body">用更克制的视觉呈现趋势与波动。</div><div class="qa-visual-frame"><svg class="qa-visual-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="pulseLineNew" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#d8b16a"/><stop offset="100%" stop-color="#fff1cb"/></linearGradient></defs><rect width="420" height="220" fill="#21170f"/><g opacity="0.13" stroke="#fffaf2"><path d="M24 42H396"/><path d="M24 92H396"/><path d="M24 142H396"/><path d="M24 192H396"/></g><path d="M24 174 C60 160, 86 124, 120 128 S176 168, 210 138 S270 62, 302 92 S358 142, 394 74" fill="none" stroke="url(#pulseLineNew)" stroke-width="4" stroke-linecap="round" stroke-dasharray="620" stroke-dashoffset="620"><animate attributeName="stroke-dashoffset" values="620;0" dur="4.5s" repeatCount="indefinite"/></path></svg></div></div>
      <div class="qa-visual-card"><div class="qa-visual-kicker">Signals</div><div class="qa-visual-title">信号热度矩阵</div><div class="qa-visual-body">承接筛选、打分与验证流程。</div><div class="qa-visual-frame"><svg class="qa-visual-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="#21170f"/><g fill="#d8b16a"><rect x="66" y="120" width="22" height="62"><animate attributeName="height" values="62;82;62" dur="3s" repeatCount="indefinite"/></rect><rect x="118" y="82" width="22" height="100"><animate attributeName="height" values="100;122;100" dur="3.4s" repeatCount="indefinite"/></rect><rect x="170" y="105" width="22" height="77"><animate attributeName="height" values="77;58;77" dur="2.8s" repeatCount="indefinite"/></rect><rect x="222" y="64" width="22" height="118"><animate attributeName="height" values="118;96;118" dur="3.2s" repeatCount="indefinite"/></rect></g><circle cx="324" cy="118" r="34" fill="rgba(255,250,242,.08)" stroke="rgba(255,250,242,.22)"/><text x="324" y="126" text-anchor="middle" fill="#fffaf2" font-size="28" font-family="Arial, sans-serif" font-weight="650">86</text></svg></div></div>
      <div class="qa-visual-card"><div class="qa-visual-kicker">Workflow</div><div class="qa-visual-title">研究到执行链路</div><div class="qa-visual-body">把模块组织成研究到执行的完整链路。</div><div class="qa-visual-frame"><svg class="qa-visual-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="#21170f"/><g fill="rgba(255,250,242,.06)" stroke="rgba(255,250,242,.18)"><rect x="32" y="84" width="82" height="52"/><rect x="166" y="50" width="88" height="52"/><rect x="166" y="122" width="88" height="52"/><rect x="306" y="84" width="82" height="52"/></g><g stroke="#d8b16a" stroke-width="3" fill="none"><path d="M114 110H166" stroke-dasharray="52" stroke-dashoffset="52"><animate attributeName="stroke-dashoffset" values="52;0" dur="1.2s" repeatCount="indefinite"/></path><path d="M254 76H286Q306 76 306 102" stroke-dasharray="80" stroke-dashoffset="80"><animate attributeName="stroke-dashoffset" values="80;0" dur="1.9s" repeatCount="indefinite"/></path><path d="M254 148H286Q306 148 306 118" stroke-dasharray="80" stroke-dashoffset="80"><animate attributeName="stroke-dashoffset" values="80;0" dur="1.9s" repeatCount="indefinite"/></path></g><g fill="#fffaf2" font-family="Arial, sans-serif" font-size="13" text-anchor="middle"><text x="73" y="115">筛选</text><text x="210" y="81">回测</text><text x="210" y="153">归因</text><text x="347" y="115">执行</text></g></svg></div></div>
    </div>
    """)

def ui_start_panel():
    render_html("""
    <div class="qa-code-panel"><h3>Implementation notes</h3><p>保留核心说明，并通过更轻盈的动态细节强化整站展示感。</p><div class="qa-code-box">pip install -r requirements.txt
streamlit run app.py</div><div class="qa-mini-points"><div class="qa-mini-point"><b>字体清晰</b><span>全站改为中文优先的无衬线字体栈，增强字号、字重和对比度。</span></div><div class="qa-mini-point"><b>排版升级</b><span>采用大标题、横向分割、洞察索引和左右分栏，不再只是换配色。</span></div><div class="qa-mini-point"><b>稳定渲染</b><span>保留动态 SVG，不依赖外网图片，同时继续隐藏异常 key 标签。</span></div></div></div>
    """)

def premium_svg(variant: str = "default") -> str:
    svgs = {'default': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><path d="M26 180 C80 162, 118 92, 170 108 S256 174, 316 124 S354 84, 394 62" fill="none" stroke="#f2d99f" stroke-width="4" stroke-dasharray="540" stroke-dashoffset="540"><animate attributeName="stroke-dashoffset" values="540;0" dur="4s" repeatCount="indefinite"/></path></svg>', 'backtest': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="bt1" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#69c6ff"/><stop offset="100%" stop-color="#f2d99f"/></linearGradient></defs><rect width="420" height="220" fill="transparent"/><g opacity="0.14" stroke="#fff"><path d="M20 40H400"/><path d="M20 90H400"/><path d="M20 140H400"/><path d="M20 190H400"/><path d="M60 22V200"/><path d="M140 22V200"/><path d="M220 22V200"/><path d="M300 22V200"/></g><path d="M24 176 C58 168, 96 116, 128 126 S188 176, 220 144 S286 64, 320 82 S364 124, 396 56" fill="none" stroke="url(#bt1)" stroke-width="4" stroke-linecap="round" stroke-dasharray="620" stroke-dashoffset="620"><animate attributeName="stroke-dashoffset" values="620;0" dur="3.8s" repeatCount="indefinite"/></path><g fill="#f2d99f"><circle cx="128" cy="126" r="4"/><circle cx="220" cy="144" r="4"/><circle cx="396" cy="56" r="6"><animate attributeName="r" values="6;8;6" dur="2s" repeatCount="indefinite"/></circle></g></svg>', 'portfolio': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><g opacity="0.15" stroke="#fff"><path d="M24 34H396"/><path d="M24 74H396"/><path d="M24 114H396"/><path d="M24 154H396"/><path d="M24 194H396"/></g><g><path d="M30 170 C70 152, 112 138, 156 126 S248 82, 392 52" fill="none" stroke="#f2d99f" stroke-width="3.6" stroke-dasharray="520" stroke-dashoffset="520"><animate attributeName="stroke-dashoffset" values="520;0" dur="3.6s" repeatCount="indefinite"/></path><path d="M30 182 C74 176, 122 152, 160 162 S240 126, 392 96" fill="none" stroke="#6cc5ff" stroke-width="3.2" stroke-dasharray="560" stroke-dashoffset="560"><animate attributeName="stroke-dashoffset" values="560;0" dur="4.2s" repeatCount="indefinite"/></path></g></svg>', 'screener': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><g fill="#0f1624" stroke="rgba(255,255,255,.08)"><rect x="22" y="32" width="110" height="42" rx="14"/><rect x="148" y="32" width="110" height="42" rx="14"/><rect x="274" y="32" width="124" height="42" rx="14"/></g><g><rect x="78" y="90" width="20" height="90" rx="6" fill="#6cc5ff"><animate attributeName="height" values="90;72;90" dur="3s" repeatCount="indefinite"/></rect><rect x="150" y="80" width="20" height="100" rx="6" fill="#f2d99f"><animate attributeName="height" values="100;114;100" dur="2.7s" repeatCount="indefinite"/></rect></g><g><circle cx="320" cy="120" r="34" fill="rgba(242,217,159,.12)" stroke="rgba(242,217,159,.55)"><animate attributeName="r" values="34;40;34" dur="3.2s" repeatCount="indefinite"/></circle><path d="M344 146L372 174" stroke="#6cc5ff" stroke-width="4" stroke-linecap="round"/></g></svg>', 'paper': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><g fill="#0f1624" stroke="rgba(255,255,255,.08)"><rect x="34" y="28" width="146" height="78" rx="18"/><rect x="200" y="28" width="186" height="78" rx="18"/><rect x="34" y="122" width="352" height="62" rx="18"/></g><text x="52" y="82" fill="#fff1cd" font-size="26" font-weight="700" font-family="Arial, sans-serif">¥1,000,000</text></svg>', 'engine': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><g fill="#0f1624" stroke="rgba(255,255,255,.08)"><rect x="28" y="84" width="90" height="54" rx="16"/><rect x="164" y="40" width="90" height="54" rx="16"/><rect x="164" y="126" width="90" height="54" rx="16"/><rect x="300" y="84" width="90" height="54" rx="16"/></g><g stroke="#f2d99f" stroke-width="3" fill="none" stroke-linecap="round"><path d="M118 111H164" stroke-dasharray="46" stroke-dashoffset="46"><animate attributeName="stroke-dashoffset" values="46;0" dur="1s" repeatCount="indefinite"/></path><path d="M254 68H280Q300 68 300 88V111" stroke-dasharray="88" stroke-dashoffset="88"><animate attributeName="stroke-dashoffset" values="88;0" dur="1.7s" repeatCount="indefinite"/></path></g></svg>', 'guide': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><g fill="#0f1624" stroke="rgba(255,255,255,.08)"><rect x="34" y="26" width="352" height="50" rx="16"/><rect x="34" y="92" width="166" height="94" rx="18"/><rect x="220" y="92" width="166" height="94" rx="18"/></g><g><path d="M244 164 L278 134 L302 148 L346 112" fill="none" stroke="#6cc5ff" stroke-width="4" stroke-dasharray="200" stroke-dashoffset="200"><animate attributeName="stroke-dashoffset" values="200;0" dur="2.6s" repeatCount="indefinite"/></path></g></svg>', 'about': '<svg class="qa-premium-visual" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg"><rect width="420" height="220" fill="transparent"/><circle cx="110" cy="108" r="58" fill="rgba(242,217,159,.12)" stroke="rgba(242,217,159,.46)"/><text x="110" y="116" text-anchor="middle" fill="#fff1cd" font-size="48" font-weight="700" font-family="Arial, sans-serif">Q</text></svg>'}
    return svgs.get(variant, svgs["default"])

def ui_premium_banner(eyebrow: str, title: str, body: str, stats, variant: str = "default"):
    stat_html = ''.join([f'<div class="qa-premium-stat"><b>{escape(str(v))}</b><span>{escape(str(k))}</span></div>' for k, v in stats])
    html = f'<div class="qa-premium-shell"><div class="qa-premium-copy"><div class="qa-premium-eyebrow">{escape(eyebrow)}</div><div class="qa-premium-title">{escape(title)}</div><p class="qa-premium-body">{escape(body)}</p><div class="qa-premium-stats">{stat_html}</div></div><div class="qa-premium-visual-wrap">{premium_svg(variant)}</div></div>'
    render_html(html)

def ui_story_cards(items):
    cards = []
    for tag, title, body in items:
        cards.append(f'<div class="qa-story-card"><div class="qa-story-tag">{escape(str(tag))}</div><div class="qa-story-title">{escape(str(title))}</div><p class="qa-story-text">{escape(str(body))}</p></div>')
    render_html('<div class="qa-story-grid">' + ''.join(cards) + '</div>')

def ui_note_banner(text_msg: str):
    render_html(f'<div class="qa-note-banner">{escape(text_msg)}</div>')

def ui_page_header(title: str, subtitle: str, kicker: str = "奶龙资本"):
    render_html(f"""
    <div class="qa-page-header"><div><div class="qa-kicker">{escape(kicker)}</div><h2>{escape(title)}</h2><p>{escape(subtitle)}</p></div><div class="qa-page-aside"><b>Platform Section</b>聚焦关键任务、参数与结果展示。</div></div>
    """)

def ui_section_title(title: str, subtitle: str = ""):
    render_html(f'<div class="qa-section-title"><h2>{escape(title)}</h2><span>{escape(subtitle)}</span></div>')

def ui_cards(cards, columns=3):
    cls = "qa-grid-4" if columns == 4 else "qa-grid"
    parts = [f'<div class="{cls}">']
    for icon, title, body in cards:
        parts.append('<div class="qa-card">' + f'<div class="qa-card-icon">{escape(str(icon))}</div>' + f'<div class="qa-card-title">{escape(str(title))}</div>' + f'<div class="qa-card-body">{escape(str(body))}</div>' + '</div>')
    parts.append('</div>')
    render_html(''.join(parts))


# ─── Institutional narrative components ─────────────────────

def ui_hero():
    render_html(f"""
    <section class="ib-hero ib-hero-v2">
      <div class="ib-aurora ib-aurora-a"></div>
      <div class="ib-aurora ib-aurora-b"></div>
      <div class="ib-topline">
        <div class="ib-wordmark">Nailong Capital</div>
        <div class="ib-topmeta"><span></span> Live quantitative research environment</div>
      </div>
      <div class="ib-hero-main">
        <div class="ib-hero-copy">
          <div class="ib-eyebrow">Nailong Capital / Quant intelligence</div>
          <div class="ib-hero-title">看见信号。<span>稳稳执行。</span></div>
          <p class="ib-hero-subtitle">奶龙和你一起扫描市场、验证策略、拆解组合，把复杂的量化研究变成清楚、可靠、可以持续复盘的投资纪律。</p>
          <div class="ib-hero-pills"><span>奶龙找信号</span><span>奶龙看风险</span><span>奶龙做复盘</span></div>
        </div>
        <div class="ib-signal-stage" aria-hidden="true">
          <div class="ib-signal-halo halo-one"></div>
          <div class="ib-signal-halo halo-two"></div>
          <div class="ib-signal-halo halo-three"></div>
          <div class="nl-home-mascot">{nailong_mascot_svg("home")}</div>
          <div class="ib-orbit-dot dot-one"></div>
          <div class="ib-orbit-dot dot-two"></div>
          <div class="ib-signal-tag tag-one"><b>01</b> Discover</div>
          <div class="ib-signal-tag tag-two"><b>02</b> Validate</div>
          <div class="ib-signal-tag tag-three"><b>03</b> Execute</div>
        </div>
      </div>
      <div class="ib-hero-stats">
        <div class="ib-hero-stat"><b>{len(STRATEGY_REGISTRY)}</b><span>Strategy frameworks</span></div>
        <div class="ib-hero-stat"><b>{len(SCREENER_STRATEGIES)}</b><span>Screening signals</span></div>
        <div class="ib-hero-stat"><b>A-Share</b><span>Primary universe</span></div>
        <div class="ib-hero-stat"><b>Dual Source</b><span>Real market data</span></div>
      </div>
    </section>
    """)


def page_art_v2(variant: str) -> str:
    art = {
        "cta": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs><linearGradient id="ctaSignal" x1="0" x2="1"><stop stop-color="#ffd84d"/><stop offset=".5" stop-color="#ff9872"/><stop offset="1" stop-color="#85ddc3"/></linearGradient></defs>
          <g fill="none" stroke="rgba(58,44,32,.12)"><path d="M52 80H668M52 150H668M52 220H668M52 290H668M52 360H668"/><path d="M126 52V390M246 52V390M366 52V390M486 52V390M606 52V390"/></g>
          <path d="M52 330C104 290 144 348 192 278S282 126 340 190 410 326 470 244 560 76 668 112" fill="none" stroke="url(#ctaSignal)" stroke-width="7" stroke-linecap="round" class="art-trace"/>
          <g transform="translate(504 250)"><circle r="94" fill="rgba(255,255,255,.58)" stroke="rgba(70,48,28,.12)"/><circle r="66" fill="none" stroke="#ffb645" stroke-width="14" stroke-dasharray="270 420" transform="rotate(-90)"/><text x="0" y="-8" text-anchor="middle" fill="#5a3823" font-size="12" letter-spacing="2.5">ALPHA SCORE</text><text x="0" y="30" text-anchor="middle" fill="#3f2b20" font-size="38" font-family="Georgia">0.57</text></g>
          <g transform="translate(68 54)"><rect width="238" height="54" rx="27" fill="rgba(255,255,255,.55)"/><text x="24" y="34" fill="#5b402d" font-size="11" letter-spacing="2.2">DIMENSION-SAFE PROGRAM SEARCH</text></g>
          <g fill="#5a3823"><circle cx="192" cy="278" r="7"/><circle cx="340" cy="190" r="7"/><circle cx="470" cy="244" r="7"/><circle cx="668" cy="112" r="9" class="art-pulse"/></g>
        </svg>''',
        "backtest": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs><linearGradient id="btLineV2" x1="0" x2="1"><stop stop-color="#69d3dc"/><stop offset=".52" stop-color="#f0d08a"/><stop offset="1" stop-color="#ffffff"/></linearGradient></defs>
          <g class="art-grid" stroke="rgba(255,255,255,.10)"><path d="M36 72H684M36 142H684M36 212H684M36 282H684M36 352H684"/><path d="M110 42V392M230 42V392M350 42V392M470 42V392M590 42V392"/></g>
          <g class="art-candles" stroke-width="2"><path d="M92 260v-74"/><rect x="82" y="204" width="20" height="34"/><path d="M146 296v-96"/><rect x="136" y="220" width="20" height="52"/><path d="M204 242v-116"/><rect x="194" y="154" width="20" height="62"/><path d="M264 286v-108"/><rect x="254" y="204" width="20" height="50"/><path d="M324 226v-128"/><rect x="314" y="124" width="20" height="74"/></g>
          <path class="art-trace" d="M48 328C104 310 132 240 188 258S280 326 336 240 442 110 506 162 590 246 672 84" fill="none" stroke="url(#btLineV2)" stroke-width="5" stroke-linecap="round"/>
          <circle cx="672" cy="84" r="7" fill="#f0d08a" class="art-pulse"/>
          <g transform="translate(454 236)"><circle r="76" fill="rgba(5,22,35,.60)" stroke="rgba(105,211,220,.34)"/><circle r="52" fill="none" stroke="rgba(240,208,138,.35)" stroke-dasharray="4 9" class="art-spin"/><text x="0" y="-7" text-anchor="middle" fill="#f3e4bd" font-size="12" letter-spacing="3">SIGNAL</text><text x="0" y="25" text-anchor="middle" fill="white" font-size="30" font-family="Georgia">86.4</text></g>
          <rect x="42" y="40" width="178" height="38" rx="19" fill="rgba(255,255,255,.06)" stroke="rgba(255,255,255,.13)"/><text x="62" y="64" fill="rgba(255,255,255,.66)" font-size="11" letter-spacing="2">HISTORICAL OBSERVATORY</text>
        </svg>''',
        "portfolio": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs><linearGradient id="pfRibbon" x1="0" x2="1"><stop stop-color="#153c55"/><stop offset=".55" stop-color="#b69050"/><stop offset="1" stop-color="#6a8b87"/></linearGradient></defs>
          <g transform="translate(310 226)"><circle r="170" fill="rgba(255,255,255,.36)" stroke="rgba(28,58,72,.08)"/><circle r="128" fill="none" stroke="#153c55" stroke-width="30" stroke-dasharray="245 560" transform="rotate(-90)"/><circle r="128" fill="none" stroke="#b69050" stroke-width="30" stroke-dasharray="190 615" transform="rotate(20)"/><circle r="128" fill="none" stroke="#6a8b87" stroke-width="30" stroke-dasharray="130 675" transform="rotate(105)"/><circle r="75" fill="#f7f1e6"/><text x="0" y="-5" text-anchor="middle" fill="#17384c" font-size="13" letter-spacing="3">ALLOCATION</text><text x="0" y="29" text-anchor="middle" fill="#17384c" font-size="34" font-family="Georgia">5 / 3</text></g>
          <path d="M36 356C132 292 186 390 280 320S426 226 510 256 620 252 686 168" fill="none" stroke="url(#pfRibbon)" stroke-width="4" stroke-linecap="round" class="art-trace"/>
          <g fill="#17384c"><circle cx="92" cy="317" r="6"/><circle cx="278" cy="321" r="6"/><circle cx="510" cy="256" r="6"/><circle cx="686" cy="168" r="8" class="art-pulse"/></g>
          <g fill="#17384c" font-size="11" letter-spacing="1.8"><text x="44" y="68">DIVERSIFICATION CANVAS</text><text x="534" y="72">RETURN</text><text x="534" y="94" font-size="28" font-family="Georgia">+18.4%</text></g>
          <g stroke="rgba(23,56,76,.12)"><path d="M42 108H176"/><path d="M536 112H674"/><path d="M42 390H674"/></g>
        </svg>''',
        "screener": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <g class="matrix-dots" fill="#62d4bf"><circle cx="82" cy="84" r="5"/><circle cx="142" cy="84" r="4"/><circle cx="202" cy="84" r="8"/><circle cx="262" cy="84" r="4"/><circle cx="82" cy="144" r="8"/><circle cx="142" cy="144" r="5"/><circle cx="202" cy="144" r="4"/><circle cx="262" cy="144" r="10"/><circle cx="82" cy="204" r="4"/><circle cx="142" cy="204" r="11"/><circle cx="202" cy="204" r="6"/><circle cx="262" cy="204" r="4"/><circle cx="82" cy="264" r="7"/><circle cx="142" cy="264" r="4"/><circle cx="202" cy="264" r="9"/><circle cx="262" cy="264" r="5"/></g>
          <g transform="translate(500 225)"><circle r="166" fill="rgba(4,19,25,.58)" stroke="rgba(98,212,191,.20)"/><circle r="118" fill="none" stroke="rgba(98,212,191,.28)"/><circle r="68" fill="none" stroke="rgba(230,198,121,.35)" stroke-dasharray="4 8" class="art-spin"/><path d="M0 0L106-55" stroke="#e6c679" stroke-width="3"/><circle cx="106" cy="-55" r="8" fill="#e6c679" class="art-pulse"/><path d="M-160 0H160M0-160V160" stroke="rgba(255,255,255,.08)"/></g>
          <path d="M48 348H302" stroke="rgba(255,255,255,.14)"/><rect x="48" y="374" width="206" height="10" rx="5" fill="rgba(255,255,255,.08)"/><rect x="48" y="374" width="154" height="10" rx="5" fill="#62d4bf" class="art-bar"/>
          <text x="48" y="332" fill="rgba(255,255,255,.62)" font-size="11" letter-spacing="2">UNIVERSE COVERAGE</text><text x="458" y="230" fill="white" font-family="Georgia" font-size="32">Top 20</text>
        </svg>''',
        "paper": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M126 38H524Q544 38 544 58V386L524 374 504 386 484 374 464 386 444 374 424 386 404 374 384 386 364 374 344 386 324 374 304 386 284 374 264 386 244 374 224 386 204 374 184 386 164 374 144 386 126 374Z" fill="#fffaf0" filter="drop-shadow(0 28px 36px rgba(95,60,32,.15))"/>
          <text x="164" y="84" fill="#8d5d38" font-size="11" letter-spacing="3">EXECUTION LEDGER</text><text x="164" y="126" fill="#3d3028" font-size="31" font-family="Georgia">¥1,000,000</text>
          <path d="M164 150H506M164 224H506M164 304H506" stroke="rgba(76,57,43,.13)"/>
          <g fill="#6e5c4c" font-size="11"><text x="164" y="182">AVAILABLE CASH</text><text x="434" y="182">92.8%</text><text x="164" y="258">OPEN POSITIONS</text><text x="452" y="258">03</text><text x="164" y="338">DAY P&amp;L</text><text x="430" y="338">+0.82%</text></g>
          <g transform="translate(594 116)"><circle r="58" fill="#b66a42" opacity=".92"/><path d="M-22 2H22M8-12L22 2 8 16" fill="none" stroke="#fff4df" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" class="art-nudge"/></g>
          <g transform="translate(608 306)"><circle r="72" fill="none" stroke="rgba(182,106,66,.20)" stroke-width="14"/><circle r="72" fill="none" stroke="#b66a42" stroke-width="14" stroke-dasharray="290 452" transform="rotate(-90)"/><text x="0" y="7" text-anchor="middle" fill="#694532" font-size="24" font-family="Georgia">64%</text></g>
        </svg>''',
        "engine": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <g stroke="rgba(97,230,190,.35)" stroke-width="2" fill="none" class="engine-links"><path d="M76 230H190L252 118H370L434 230H638"/><path d="M190 230L252 344H370L434 230"/></g>
          <g class="engine-nodes"><circle cx="76" cy="230" r="24"/><circle cx="190" cy="230" r="28"/><circle cx="252" cy="118" r="34"/><circle cx="252" cy="344" r="34"/><circle cx="370" cy="118" r="28"/><circle cx="370" cy="344" r="28"/><circle cx="434" cy="230" r="42"/><circle cx="638" cy="230" r="30"/></g>
          <g fill="#dffbf2" font-size="10" text-anchor="middle" letter-spacing="1.2"><text x="76" y="234">POOL</text><text x="190" y="234">SCAN</text><text x="252" y="122">BUY</text><text x="252" y="348">SELL</text><text x="370" y="122">RISK</text><text x="370" y="348">LIMIT</text><text x="434" y="234">EXECUTE</text><text x="638" y="234">LOG</text></g>
          <circle cx="76" cy="230" r="6" fill="#72e4c0" class="engine-packet packet-one"/><circle cx="76" cy="230" r="5" fill="#e6c679" class="engine-packet packet-two"/>
          <path d="M48 58H672" stroke="rgba(255,255,255,.11)"/><text x="48" y="44" fill="rgba(255,255,255,.54)" font-size="11" letter-spacing="3">LIVE EXECUTION GRAPH</text><g transform="translate(540 72)"><circle r="6" fill="#72e4c0" class="art-pulse"/><text x="18" y="4" fill="#72e4c0" font-size="10" letter-spacing="2">ENGINE READY</text></g>
        </svg>''',
        "guide": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <g transform="translate(76 68)"><path d="M0 42Q128 6 270 48V338Q136 302 0 334Z" fill="rgba(255,255,255,.94)"/><path d="M270 48Q414 6 550 42V334Q412 302 270 338Z" fill="rgba(240,247,252,.94)"/><path d="M270 48V338" stroke="rgba(32,81,130,.24)" stroke-width="3"/>
          <g stroke="rgba(32,81,130,.18)"><path d="M34 108H224M34 144H206M34 180H224M34 250H196M316 108H500M316 144H468M316 250H500M316 286H458"/></g>
          <circle cx="132" cy="226" r="42" fill="none" stroke="#2d679d"/><path d="M132 184V268M90 226H174" stroke="#2d679d"/><circle cx="414" cy="196" r="68" fill="none" stroke="#2d679d" stroke-dasharray="4 8" class="art-spin"/><path d="M414 138L432 196 414 254 396 196Z" fill="#d1a95e"/><circle cx="414" cy="196" r="8" fill="#2d679d"/></g>
          <text x="108" y="54" fill="rgba(255,255,255,.68)" font-size="11" letter-spacing="3">RESEARCH PLAYBOOK / EDITION 02</text>
        </svg>''',
        "about": '''
        <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs><linearGradient id="brandArc" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f2d99d"/><stop offset=".5" stop-color="#9b7240"/><stop offset="1" stop-color="#f8edce"/></linearGradient></defs>
          <circle cx="382" cy="226" r="168" fill="none" stroke="rgba(255,255,255,.08)"/><circle cx="382" cy="226" r="126" fill="none" stroke="rgba(242,217,157,.20)" stroke-dasharray="5 11" class="art-spin"/>
          <path d="M72 356C174 292 204 102 366 96S534 326 666 144" fill="none" stroke="url(#brandArc)" stroke-width="4" class="art-trace"/>
          <text x="382" y="214" text-anchor="middle" fill="#f5e9c9" font-size="102" font-family="Georgia" letter-spacing="-8">NL</text><text x="382" y="252" text-anchor="middle" fill="rgba(255,255,255,.52)" font-size="11" letter-spacing="5">NAILONG CAPITAL</text>
          <g fill="rgba(255,255,255,.26)"><rect x="74" y="330" width="56" height="48"/><rect x="140" y="300" width="48" height="78"/><rect x="198" y="318" width="68" height="60"/><rect x="542" y="288" width="52" height="90"/><rect x="604" y="316" width="44" height="62"/></g>
          <circle cx="666" cy="144" r="8" fill="#f2d99d" class="art-pulse"/>
        </svg>''',
    }
    return art.get(variant, art["backtest"])


def nailong_mascot_svg(variant: str) -> str:
    props = {
        "home": '<g transform="translate(205 170) rotate(-8)"><rect x="0" y="0" width="88" height="54" rx="14" fill="#fff9e8" stroke="#5a4028" stroke-width="5"/><path d="M16 38L34 24 49 30 70 14" fill="none" stroke="#e2603a" stroke-width="6" stroke-linecap="round"/><circle cx="70" cy="14" r="5" fill="#e2603a"/></g>',
        "backtest": '<g transform="translate(182 150) rotate(-12)"><rect x="0" y="0" width="112" height="30" rx="15" fill="#79c9d2" stroke="#4a3424" stroke-width="6"/><circle cx="106" cy="15" r="23" fill="#c7edf0" stroke="#4a3424" stroke-width="6"/><path d="M14 30L-4 68" stroke="#4a3424" stroke-width="7"/></g>',
        "portfolio": '<g transform="translate(190 170)"><path d="M0 0H98" stroke="#5a4028" stroke-width="7" stroke-linecap="round"/><path d="M49 0V48" stroke="#5a4028" stroke-width="7"/><path d="M18 4L4 42H34Z" fill="#77a68c"/><path d="M80 4L64 42H96Z" fill="#d9a847"/><circle cx="49" cy="-4" r="10" fill="#f8cf52" stroke="#5a4028" stroke-width="5"/></g>',
        "screener": '<g transform="translate(184 146) rotate(-10)"><circle cx="34" cy="34" r="32" fill="#bcebdc" stroke="#513725" stroke-width="7"/><circle cx="34" cy="34" r="15" fill="rgba(255,255,255,.55)"/><path d="M58 58L96 96" stroke="#513725" stroke-width="12" stroke-linecap="round"/></g>',
        "paper": '<g transform="translate(192 130) rotate(8)"><rect width="88" height="118" rx="13" fill="#fffaf0" stroke="#5b3e2a" stroke-width="6"/><path d="M18 30H70M18 52H62M18 74H68" stroke="#c27b4a" stroke-width="5" stroke-linecap="round"/><circle cx="64" cy="98" r="12" fill="#efb84e"/></g>',
        "engine": '<g transform="translate(198 148)"><circle cx="38" cy="38" r="34" fill="#92e4c8" stroke="#3e3024" stroke-width="7"/><circle cx="38" cy="38" r="12" fill="#f7cf55"/><path d="M38-8V4M38 72V84M-8 38H4M72 38H84M5 5L14 14M62 62L71 71M71 5L62 14M14 62L5 71" stroke="#3e3024" stroke-width="8" stroke-linecap="round"/></g>',
        "guide": '<g transform="translate(170 150)"><path d="M0 0Q50-18 94 6V78Q50 54 0 74Z" fill="#ffffff" stroke="#4a3827" stroke-width="6"/><path d="M94 6Q140-18 184 0V74Q140 54 94 78Z" fill="#eef7ff" stroke="#4a3827" stroke-width="6"/><path d="M94 6V78" stroke="#4a3827" stroke-width="5"/><path d="M20 26H70M116 24H162M20 44H62M116 42H154" stroke="#4e84b3" stroke-width="4" stroke-linecap="round"/></g>',
        "about": '<g transform="translate(192 146)"><circle cx="44" cy="44" r="42" fill="#f7cf55" stroke="#4c3424" stroke-width="6"/><text x="44" y="55" text-anchor="middle" fill="#4c3424" font-family="Georgia" font-size="35" font-weight="700">NL</text><path d="M44 86V124" stroke="#4c3424" stroke-width="7"/><path d="M18 124H70" stroke="#4c3424" stroke-width="8" stroke-linecap="round"/></g>',
    }
    prop = props.get(variant, props["home"])
    return f'''
    <svg viewBox="0 0 340 360" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <g class="nl-float">
        <path d="M114 82Q98 48 122 30Q150 48 150 78" fill="#f4b93f" stroke="#4f3624" stroke-width="7" stroke-linejoin="round"/>
        <path d="M196 78Q198 44 226 32Q244 58 222 88" fill="#f4b93f" stroke="#4f3624" stroke-width="7" stroke-linejoin="round"/>
        <ellipse cx="170" cy="232" rx="86" ry="102" fill="#f7c84a" stroke="#4f3624" stroke-width="8"/>
        <circle cx="170" cy="120" r="82" fill="#f8cc52" stroke="#4f3624" stroke-width="8"/>
        <ellipse cx="170" cy="254" rx="49" ry="67" fill="#ffe79b" opacity=".92"/>
        <circle cx="141" cy="112" r="8" fill="#3e2b20"/><circle cx="199" cy="112" r="8" fill="#3e2b20"/>
        <circle cx="138" cy="108" r="2.5" fill="#fff"/><circle cx="196" cy="108" r="2.5" fill="#fff"/>
        <path d="M155 139Q170 151 185 139" fill="none" stroke="#4f3624" stroke-width="7" stroke-linecap="round"/>
        <ellipse cx="118" cy="139" rx="12" ry="7" fill="#ef8b68" opacity=".62"/><ellipse cx="222" cy="139" rx="12" ry="7" fill="#ef8b68" opacity=".62"/>
        <path d="M95 218Q52 194 46 232Q58 248 102 247" fill="#f7c84a" stroke="#4f3624" stroke-width="8" stroke-linecap="round"/>
        <path d="M246 218Q286 186 300 220Q298 243 244 249" fill="#f7c84a" stroke="#4f3624" stroke-width="8" stroke-linecap="round"/>
        <path d="M120 322Q110 344 86 342" stroke="#4f3624" stroke-width="10" stroke-linecap="round"/>
        <path d="M220 322Q230 344 254 342" stroke="#4f3624" stroke-width="10" stroke-linecap="round"/>
        {prop}
      </g>
    </svg>'''


# Final character renderer uses the user-provided official-looking 3D reference.
# The surrounding page illustration and CSS pose are still unique per module.
def nailong_mascot_svg(variant: str) -> str:
    image_uri = NAILONG_STICKERS.get(variant, NAILONG_IMAGE_URI)
    return (
        f'<div class="nl-real-character nl-real-{escape(variant)}">'
        f'<img src="{image_uri}" alt="奶龙 · {escape(variant)}" />'
        f'<span class="nl-character-glow"></span>'
        f'</div>'
    )


def ui_module_header(index: str, title: str, subtitle: str, objective: str, process, variant: str = "backtest"):
    process_html = ''.join(
        f'<div class="ib-process-item"><b>{i:02d}</b><span>{escape(str(step))}</span></div>'
        for i, step in enumerate(process, start=1)
    )
    render_html(f"""
    <section class="ib-page-head theme-{escape(variant)}">
      <div>
        <div class="ib-page-code">Module {escape(index)} / Nailong Capital</div>
        <div class="ib-page-title">{escape(title)}</div>
        <p class="ib-page-copy">{escape(subtitle)}</p>
      </div>
      <aside class="ib-page-brief">
        <div class="ib-page-brief-label">Decision objective</div>
        <p>{escape(objective)}</p>
      </aside>
      <div class="ib-page-art">{page_art_v2(variant)}</div>
      <div class="nl-page-mascot">{nailong_mascot_svg(variant)}</div>
      <div class="ib-process">{process_html}</div>
    </section>
    """)


def ui_flow_journey(items):
    nodes = []
    for index, (tag, title, body) in enumerate(items, start=1):
        nodes.append(
            f'<div class="flow-node flow-node-{index}">'
            f'<div class="flow-dot"><span>{index:02d}</span></div>'
            f'<div class="flow-tag">{escape(str(tag))}</div>'
            f'<h3>{escape(str(title))}</h3>'
            f'<p>{escape(str(body))}</p>'
            f'</div>'
        )
    render_html('''
    <div class="flow-journey">
      <svg class="flow-path" viewBox="0 0 1200 260" preserveAspectRatio="none" aria-hidden="true">
        <path class="flow-path-shadow" d="M30,165 C190,20 330,235 485,115 C640,-5 760,245 930,105 C1030,25 1120,55 1180,28"/>
        <path class="flow-path-live" d="M30,165 C190,20 330,235 485,115 C640,-5 760,245 930,105 C1030,25 1120,55 1180,28"/>
      </svg>
      <div class="flow-nodes">''' + ''.join(nodes) + '''</div>
    </div>
    ''')


def ui_capability_stream(items):
    rows = []
    for code, title, body in items:
        rows.append(
            f'<div class="capability-row"><div class="capability-code">{escape(str(code))}</div>'
            f'<div class="capability-copy"><h3>{escape(str(title))}</h3><p>{escape(str(body))}</p></div>'
            f'<div class="capability-arrow">↗</div></div>'
        )
    render_html('<div class="capability-stream">' + ''.join(rows) + '</div>')

def normalize_codes(text: str):
    return [c.strip().zfill(6) for c in text.replace('，', ',').replace(';', ',').replace('；', ',').replace(' ', ',').replace('\n', ',').split(',') if c.strip()]


def plot_signal_distribution(signal_counts):
    try:
        import plotly.express as px
        sig_df = signal_counts.reset_index()
        sig_df.columns = ["信号类型", "出现次数"]
        fig = px.bar(sig_df, x="信号类型", y="出现次数", text="出现次数")
        fig.update_layout(
            template="plotly_white", height=360, title="选股信号分布",
            margin=dict(l=30, r=20, t=55, b=50), xaxis_title=None, yaxis_title=None,
        )
        fig.update_traces(marker_color="#163A5A", textfont_color="#172839")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass


# === 初始化Session State ===
defaults = {
    "sim_broker": None,
    "live_engine": None,
    "engine_logs": [],
    "stock_list": None,
    "screener_result": None,
    "screener_running": False,
    "last_backtest_summary": None,
    "research_workspace": None,
    "alpha2_run": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.research_workspace is None:
    st.session_state.research_workspace = ResearchWorkspace(
        os.path.join(os.path.dirname(__file__), "research_state")
    )
workspace = st.session_state.research_workspace


# ─── 工具函数 ────────────────────────────────────────────────

# 检测数据源状态 (Sina行情API)
@st.cache_data(ttl=300)
# 检测数据源状态 (Sina行情API)
def _check_network():
    try:
        from quant_a.data_fetcher import check_network
        return check_network()
    except Exception:
        return False
# 页面顶部网络状态提示
_net_ok = st.session_state.get("_net_ok", None)
if _net_ok is None:
    _net_ok = _check_network()
    st.session_state._net_ok = _net_ok
if not _net_ok:
    st.warning("🌐 实时行情(Sina/腾讯)当前无法连接；历史回测仍可尝试 efinance 或 baostock，系统不会生成模拟行情替代真实数据。")

def load_stock_list():
    """加载股票列表(带缓存, 失败后返回空DataFrame)"""
    if st.session_state.stock_list is None:
        with st.spinner("加载A股列表..."):
            try:
                st.session_state.stock_list = get_stock_list()
            except Exception as e:
                st.warning(f"股票列表加载失败(部分功能受限): {e}")
                st.session_state.stock_list = pd.DataFrame(columns=["code", "name"])
    if st.session_state.stock_list is None:
        st.session_state.stock_list = pd.DataFrame(columns=["code", "name"])
    return st.session_state.stock_list


def get_stock_name(code):
    sl = load_stock_list()
    if sl is not None:
        m = sl[sl["code"] == code]
        if len(m) > 0:
            return m.iloc[0]["name"]
    return ""


def fmt_yuan(v):
    if abs(v) >= 10000:
        return f"¥{v/10000:.2f}万"
    return f"¥{v:,.2f}"


def csv_download_link(df, filename, label):
    if df is None or len(df) == 0:
        return ""
    csv = df.to_csv(index=True, encoding="utf-8-sig")
    return st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")


# ─── 侧边栏 ──────────────────────────────────────────────────

st.sidebar.markdown(f"""
<div class="sidebar-brand">
    <div class="sidebar-logo profile-avatar">
        <img src="{PROFILE_IMAGE_URI}" alt="Nailong Capital 头像" />
    </div>
    <div class="sidebar-title">
        <span class="sidebar-name">Nailong Capital</span>
        <span class="sidebar-version">Quantitative Research</span>
    </div>
</div>
<div class="nav-container">
""", unsafe_allow_html=True)

# 导航菜单 — 简洁纯文字，用微妙的左边界指示当前项
nav_defs = [
    ("00  投研总览", "🏠 首页总览"),
    ("01  策略验证", "📊 策略回测"),
    ("02  Alpha² 单资产", "🧠 Alpha²单资产"),
    ("03  组合归因", "📑 组合回测"),
    ("04  信号筛选", "🎯 自动选股"),
    ("05  模拟执行", "💰 模拟盘交易"),
    ("06  自动交易", "🤖 自动交易"),
    ("07  操作手册", "📋 使用说明"),
    ("08  平台信息", "ℹ️ 关于"),
]

if "nav_tab" not in st.session_state:
    st.session_state.nav_tab = "🏠 首页总览"

for display_name, state_val in nav_defs:
    is_active = st.session_state.nav_tab == state_val
    btn_type = "primary" if is_active else "secondary"
    st.sidebar.button(
        display_name,
        key=f"nav_{state_val}",
        type=btn_type,
    )
    if st.session_state.get(f"nav_{state_val}"):
        if st.session_state.nav_tab != state_val:
            st.session_state.nav_tab = state_val
            st.rerun()

st.sidebar.markdown('</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-footer">Research · Risk · Execution</div>', unsafe_allow_html=True)
if _net_ok:
    st.sidebar.success("Market data / connected")
else:
    st.sidebar.info("Market data / offline mode")

tab = st.session_state.nav_tab


# =============================================================
# TAB 0: 首页总览
# =============================================================
if tab == "🏠 首页总览":
    ui_hero()

    ui_section_title('Research flow', '不是功能菜单，而是一条从机会发现到资本执行的完整研究路径。')
    ui_flow_journey([
        ("DISCOVER", "发现信号", "扫描市场，建立有排序、有证据的候选池。"),
        ("UNDERWRITE", "验证策略", "检验收益、回撤、胜率与成本敏感性。"),
        ("ATTRIBUTE", "组合归因", "识别收益来源、集中度与分散化质量。"),
        ("EXECUTE", "纪律执行", "用模拟账户复核仓位、订单与执行路径。"),
    ])

    ui_section_title('Core intelligence', '六项能力沿研究流程自然展开，保持连续、轻盈、可操作。')
    ui_capability_stream([
        ("BT / 01", "单标的回测", "检验策略在指定标的、区间、复权与交易成本下的表现。"),
        ("PF / 02", "组合层验证", "对多标的等权组合进行权益、回撤、月度收益与贡献度分析。"),
        ("SC / 03", "全市场筛选", "并行扫描股票池，以综合评分或信号强度建立研究优先级。"),
        ("PE / 04", "模拟盘执行", "持久化账户、仓位、订单与交易日志，验证执行闭环。"),
        ("AE / 05", "自动化引擎", "轮询策略信号并执行风控约束，连接模拟盘与实盘适配层。"),
        ("GC / 06", "治理与边界", "明确数据口径、策略假设与风险提示，避免把回测结果误当成确定性。"),
    ])

    ui_feature_strip([("Evidence first", "先定义数据、区间与成本口径，再评价策略结果。"), ("Risk before return", "优先审阅回撤、稳定性与归因，再讨论收益。"), ("Simulation before capital", "所有执行流程先通过模拟账户验证，再考虑实盘适配。")])
    ui_note_banner("本平台仅用于量化研究与流程验证，不构成投资建议。历史回测表现不代表未来收益。")


# =============================================================
# TAB 1: 策略回测 (增强版)
# =============================================================
elif tab == "📊 策略回测":
    ui_module_header("01", "策略验证", "在单一标的上建立清晰的策略假设，统一检验区间、复权方式、成本与基准口径，并将收益与下行风险放在同一张答卷中。", "判断策略表现是否来自可重复的信号，而非区间选择或成本遗漏。", ["定义标的与样本", "校准策略参数", "执行历史回测", "审阅绩效与交易"], variant="backtest")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        code_input = st.text_input("股票代码", value="600519")
        if code_input:
            name = get_stock_name(code_input)
            if name:
                st.caption(f"证券名称 / {name}")
    with col2:
        strategy_name = st.selectbox("策略", list(STRATEGY_REGISTRY.keys()))
    with col3:
        start_date = st.date_input("开始", value=pd.Timestamp("2022-01-01"))
        end_date = st.date_input("结束", value=pd.Timestamp("today"))
    with col4:
        adjust = st.selectbox("复权", ["qfq", "hfq", ""],
                              format_func=lambda x: {"qfq": "前复权", "hfq": "后复权", "": "不复权"}[x])
        initial_cash = st.number_input("本金(万)", value=100, min_value=1) * 10000

    bt_source = st.selectbox("历史数据源", ["efinance", "平台历史源"], key="bt_data_source")

    # 策略参数
    strategy_cls, default_params, param_config = STRATEGY_REGISTRY[strategy_name]
    param_keys = list(param_config.keys())
    max_cols = 2
    strategy_params = {}
    for chunk_i in range(0, len(param_keys), max_cols):
        chunk = param_keys[chunk_i:chunk_i + max_cols]
        cols = st.columns(len(chunk))
        for j, key in enumerate(chunk):
            label, min_v, max_v = param_config[key]
            default_v = default_params.get(key, min_v)
            strategy_params[key] = cols[j].slider(label, min_v, max_v, default_v, key=f"bt_{key}")

    # 基准对比开关
    show_benchmark = st.checkbox("对比沪深300基准", value=True)

    # 回测参数
    ui_micro_head("回测参数", "费用参数保持常驻可见，避免展开组件导致的排版干扰。")
    c1, c2, c3 = st.columns(3)
    commission = c1.number_input("佣金(万)", value=2.5, key="bt_commission") / 10000
    stamp = c2.number_input("印花税(千)", value=1.0, key="bt_stamp") / 1000
    slippage = c3.number_input("滑点(千)", value=1.0, key="bt_slippage") / 1000

    if st.button("开始回测", type="primary"):
        with st.spinner("获取数据与执行回测..."):
            if bt_source == "efinance":
                df = get_daily_data_efinance(code_input, start_date, end_date, adjust)
            else:
                df = get_daily_data(code_input,
                                    start_date.strftime("%Y-%m-%d"),
                                    end_date.strftime("%Y-%m-%d"), adjust)
            if df is None or len(df) == 0:
                st.error(f"{bt_source} 未返回真实历史数据，请检查网络、代码或日期区间。")
                st.stop()

            st.info(f"真实数据 / {bt_source} / {get_stock_name(code_input)} / {len(df)} 条日 K "
                    f"({df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()})")

            strategy = strategy_cls(**strategy_params)
            df_sig = strategy.generate_signals(df)

            engine = BacktestEngine(
                initial_cash=initial_cash,
                commission_rate=commission, stamp_tax=stamp, slippage=slippage,
            )
            equity_df, trades_df = engine.run(df_sig)

            # 基准
            benchmark_df = None
            if show_benchmark:
                try:
                    benchmark_df = get_index_data(
                        equity_df["date"].iloc[0].strftime("%Y-%m-%d"),
                        equity_df["date"].iloc[-1].strftime("%Y-%m-%d"),
                    )
                except Exception:
                    pass

            perf = calc_performance(equity_df, trades_df, initial_cash)
            st.session_state.last_backtest_summary = {
                "代码": code_input, "策略": strategy_name, "区间": f"{start_date} ~ {end_date}",
                "总收益率": perf.get("总收益率", "-"), "最大回撤": perf.get("最大回撤", "-"),
            }
            snapshot = workspace.save_snapshot(st.session_state.last_backtest_summary)

        # 核心指标
        st.markdown("---")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("总收益率", perf.get("总收益率", "-"))
        m2.metric("年化收益", perf.get("年化收益率", "-"))
        m3.metric("夏普比率", perf.get("夏普比率", "-"))
        m4.metric("最大回撤", perf.get("最大回撤", "-"))
        m5.metric("胜率", perf.get("胜率", "-"))
        m6.metric("交易次数", perf.get("交易次数", "-"))
        st.caption(f"研究快照已保存 / {snapshot['snapshot_id']} / 可在自动交易页审阅最近活动")

        # 第二行指标
        ui_micro_head("全部绩效指标", "保留完整绩效口径，便于复盘与导出。")
        perf_df = pd.DataFrame(list(perf.items()), columns=["指标", "值"])
        col_tb, col_btn = st.columns([4, 1])
        with col_tb:
            st.dataframe(perf_df, use_container_width=True, hide_index=True)
        with col_btn:
            csv_download_link(perf_df, f"perf_{code_input}.csv", "导出 CSV")

        # K线图
        fig_k = plot_kline_with_signals(df_sig, strategy_name=f"{code_input} {get_stock_name(code_input)}")
        st.plotly_chart(fig_k, use_container_width=True)

        # 资金曲线 + 回撤
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.plotly_chart(
                plot_equity_curve(equity_df, benchmark_df, initial_cash,
                                  title=f"{code_input} {get_stock_name(code_input)}"),
                use_container_width=True,
            )
        with col_r:
            dd_df = calc_drawdown_series(equity_df)
            st.plotly_chart(plot_drawdown(dd_df), use_container_width=True)

        # 盈亏图
        fig_pnl = plot_trade_pnl(trades_df)
        if fig_pnl:
            st.plotly_chart(fig_pnl, use_container_width=True)

        # 月度热力图
        if len(equity_df) > 60:
            try:
                hm = monthly_returns(equity_df)
                fig_hm = plot_monthly_heatmap(hm)
                if fig_hm:
                    st.plotly_chart(fig_hm, use_container_width=True)
            except Exception:
                pass

        # 交易明细
        if trades_df is not None and len(trades_df) > 0:
            st.markdown("### 交易明细")
            col_tb, col_btn = st.columns([4, 1])
            with col_tb:
                st.dataframe(trades_df, use_container_width=True, hide_index=True)
            with col_btn:
                csv_download_link(trades_df, f"trades_{code_input}.csv", "导出 CSV")
        else:
            st.info("该策略在选定时间段内没有产生交易信号")


# =============================================================
# TAB 2: Alpha² 单资产适配复现
# =============================================================
elif tab == "🧠 Alpha²单资产":
    ui_module_header(
        "02", "Alpha² 单资产实验室",
        "以一只股票的 OHLCV 历史为输入，搜索量纲正确、可解释且低相关的公式 Alpha；按训练、验证、测试时间段严格隔离，再将组合信号转化为次日仓位。",
        "验证公式因子在单一资产上的时序预测力，而不是用样本内收益替代真正的样本外检验。",
        ["载入单资产数据", "构造合法公式", "验证 IC 与多样性", "样本外回测"],
        variant="cta",
    )

    ui_note_banner("论文边界：Alpha² 原文在沪深300/500横截面上优化20日收益 IC，官方仓库仅提供伪代码。当前页面是单资产时序适配复现：保留量纲检查、未来20日目标、低相关奖励与组合逻辑，但不冒充原论文的 DRL+MCTS 基准结果。")

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        alpha_code = st.text_input("单股票代码", value="600519", key="alpha2_code")
        alpha_source = st.selectbox("数据源", ["efinance", "平台历史源"], key="alpha2_source")
    with a2:
        alpha_start = st.date_input("样本开始", value=pd.Timestamp("2015-01-01"), key="alpha2_start")
        alpha_end = st.date_input("样本结束", value=pd.Timestamp("today"), key="alpha2_end")
    with a3:
        alpha_top_k = st.slider("入选 Alpha 数", 3, 12, 8, key="alpha2_topk")
        alpha_forward = st.select_slider("预测周期(日)", options=[5, 10, 20, 40], value=20, key="alpha2_forward")
    with a4:
        alpha_cost = st.number_input("单边成本(bp)", min_value=0.0, max_value=50.0, value=8.0, step=1.0, key="alpha2_cost")
        alpha_long_short = st.checkbox("允许多空（研究模式）", value=False, key="alpha2_ls")

    b1, b2 = st.columns(2)
    alpha_diversity = b1.slider("低相关性惩罚", 0.0, 1.0, 0.65, 0.05, key="alpha2_diversity")
    alpha_threshold = b2.slider("交易信号阈值", 0.02, 0.60, 0.12, 0.01, key="alpha2_threshold")

    if st.button("运行 Alpha² 单资产复现", type="primary", key="alpha2_run_button"):
        try:
            with st.spinner("载入数据、生成合法公式并执行时间切分回测..."):
                if alpha_source == "efinance":
                    market_df = get_daily_data_efinance(alpha_code, alpha_start, alpha_end, "qfq")
                else:
                    market_df = get_daily_data(
                        alpha_code,
                        pd.Timestamp(alpha_start).strftime("%Y-%m-%d"),
                        pd.Timestamp(alpha_end).strftime("%Y-%m-%d"),
                        "qfq",
                    )

                if market_df is None or len(market_df) < 320:
                    raise ValueError("有效真实样本少于320个交易日，无法完成60/20/20时间切分；请扩大区间或切换真实数据源。")

                alpha_result, selected_alphas, all_alphas = discover_single_asset_alphas(
                    market_df,
                    forward_days=alpha_forward,
                    top_k=alpha_top_k,
                    diversity_strength=alpha_diversity,
                )
                alpha_backtest, alpha_metrics = backtest_single_asset_alpha(
                    alpha_result,
                    threshold=alpha_threshold,
                    cost_bps=alpha_cost,
                    long_short=alpha_long_short,
                )
                st.session_state.alpha2_run = {
                    "market": market_df,
                    "result": alpha_result,
                    "selected": selected_alphas,
                    "all": all_alphas,
                    "backtest": alpha_backtest,
                    "metrics": alpha_metrics,
                    "code": alpha_code,
                    "source": alpha_source,
                }
                workspace.audit(
                    "ALPHA2_SINGLE_ASSET",
                    f"Completed single-asset formula search for {alpha_code}",
                    {"source": alpha_source, "observations": len(market_df), "top_k": alpha_top_k},
                )
        except Exception as exc:
            st.error(f"Alpha² 单资产实验失败：{exc}")

    alpha_run = st.session_state.alpha2_run
    if alpha_run:
        metrics = alpha_run["metrics"]
        metric_cols = st.columns(len(metrics))
        for metric_col, (label, value) in zip(metric_cols, metrics.items()):
            metric_col.metric(label, value)

        selected_view = alpha_run["selected"].copy()
        if len(selected_view):
            ui_micro_head("入选公式 Alpha", "按照验证集 IC 与低相关性奖励顺序选择；测试集指标不参与公式选择。")
            selected_view = selected_view.rename(columns={
                "formula": "公式", "family": "因子族", "dimension": "量纲",
                "train_ic": "训练IC", "valid_ic": "验证IC", "test_ic": "测试IC",
                "valid_rank_ic": "验证RankIC", "test_rank_ic": "测试RankIC",
                "max_selected_corr": "最大相关", "selection_score": "选择得分",
            })
            visible_columns = ["公式", "因子族", "量纲", "训练IC", "验证IC", "测试IC", "验证RankIC", "测试RankIC", "最大相关", "选择得分"]
            st.dataframe(selected_view[[column for column in visible_columns if column in selected_view.columns]], use_container_width=True, hide_index=True)

        try:
            import plotly.graph_objects as go
            bt = alpha_run["backtest"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=bt["date"], y=bt["equity"], name="Alpha² 组合", line=dict(color="#f2a93b", width=3)))
            fig.add_trace(go.Scatter(x=bt["date"], y=bt["benchmark_equity"], name="持有基准", line=dict(color="#315b72", width=2)))
            test_start = bt.loc[bt["split"] == "test", "date"].min()
            if pd.notna(test_start):
                fig.add_vline(x=test_start, line_dash="dot", line_color="#bc6b4b", annotation_text="测试集开始")
            fig.update_layout(template="plotly_white", height=440, margin=dict(l=20, r=20, t=50, b=30), title=f"{alpha_run['code']} / 权益曲线")
            st.plotly_chart(fig, use_container_width=True)

            signal_fig = go.Figure()
            signal_fig.add_trace(go.Scatter(x=bt["date"], y=bt["signal_strength"], name="组合 Alpha", line=dict(color="#7b5d43", width=2)))
            signal_fig.add_hline(y=alpha_threshold, line_dash="dash", line_color="#53a37f")
            if alpha_long_short:
                signal_fig.add_hline(y=-alpha_threshold, line_dash="dash", line_color="#d56d55")
            signal_fig.update_layout(template="plotly_white", height=300, margin=dict(l=20, r=20, t=45, b=25), title="组合信号与交易阈值")
            st.plotly_chart(signal_fig, use_container_width=True)
        except Exception:
            pass

        with st.expander("查看全部合法公式与 IC 诊断"):
            st.dataframe(alpha_run["all"], use_container_width=True, hide_index=True)

        st.caption(f"数据源 / {alpha_run['source']} · 样本量 / {len(alpha_run['market'])} · 执行规则 / 当日生成信号、下一交易日持仓 · 所有收益均扣除设定换手成本")


# =============================================================
# TAB 3: 组合回测 (NEW)
# =============================================================
elif tab == "📑 组合回测":
    ui_module_header("03", "组合归因", "把多个候选标的置于统一策略和资本约束下，比较组合权益、个股贡献、回撤结构与分散化效果。", "识别收益究竟来自组合构建，还是被少数标的和单一行情阶段所主导。", ["构建候选组合", "统一策略与成本", "对比组合与基准", "拆解个股贡献"], variant="portfolio")

    ui_note_banner("建议将组合回测用于候选池的二次验证：先做自动选股，再将结果导入组合层面对比收益、回撤和分散化效果。")

    col1, col2 = st.columns(2)
    with col1:
        codes_input = st.text_area("股票代码(每行一个)", value="600519\n000858\n002594\n600036\n000333",
                                   height=150)
    with col2:
        strategy_name = st.selectbox("策略", list(STRATEGY_REGISTRY.keys()), key="pf_strategy")
        start_date = st.date_input("开始", value=pd.Timestamp("2022-01-01"), key="pf_start")
        end_date = st.date_input("结束", value=pd.Timestamp("today"), key="pf_end")
        initial_cash = st.number_input("总资金(万)", value=200, min_value=10) * 10000
        show_benchmark = st.checkbox("对比沪深300", value=True, key="pf_bm")

    # 策略参数
    strategy_cls, default_params, param_config = STRATEGY_REGISTRY[strategy_name]
    param_keys = list(param_config.keys())
    max_cols = 2
    strategy_params = {}
    for chunk_i in range(0, len(param_keys), max_cols):
        chunk = param_keys[chunk_i:chunk_i + max_cols]
        cols = st.columns(len(chunk))
        for j, key in enumerate(chunk):
            label, min_v, max_v = param_config[key]
            default_v = default_params.get(key, min_v)
            strategy_params[key] = cols[j].slider(label, min_v, max_v, default_v, key=f"pf_{key}")

    # 复权方式和回测参数
    pf_col1, pf_col2 = st.columns(2)
    with pf_col1:
        pf_adjust = st.selectbox("复权方式", ["qfq", "hfq", ""],
                                 format_func=lambda x: {"qfq": "前复权", "hfq": "后复权", "": "不复权"}[x],
                                 key="pf_adjust")
        pf_source = st.selectbox("组合数据源", ["efinance", "平台历史源"], key="pf_data_source")
    with pf_col2:
        ui_micro_head("组合回测参数", "费用参数直接展示，方便连续调整。")
        pc1, pc2, pc3 = st.columns(3)
        pf_commission = pc1.number_input("佣金(万)", value=2.5, key="pf_comm") / 10000
        pf_stamp = pc2.number_input("印花税(千)", value=1.0, key="pf_stamp") / 1000
        pf_slippage = pc3.number_input("滑点(千)", value=1.0, key="pf_slip") / 1000

    codes = normalize_codes(codes_input)

    if st.button("开始组合回测", type="primary"):
        if len(codes) < 2:
            st.warning("至少需要2只股票进行组合回测")
            st.stop()

        with st.spinner(f"并行获取{len(codes)}只股票数据 & 执行回测..."):
            if pf_source == "efinance":
                data_dict = {}
                for code in codes:
                    real_df = get_daily_data_efinance(code, start_date, end_date, pf_adjust)
                    if real_df is not None and len(real_df) > 0:
                        data_dict[code] = real_df
            else:
                data_dict = get_batch_data(codes, start_date.strftime("%Y-%m-%d"),
                                           end_date.strftime("%Y-%m-%d"), pf_adjust, max_workers=6)

            if not data_dict:
                st.error(f"{pf_source} 未返回任何真实历史数据，请检查网络、代码与日期区间。")
                st.stop()

            loaded = len(data_dict)
            failed = len(codes) - loaded
            st.info(f"成功获取 {loaded} 只股票数据" + (f", {failed}只失败" if failed else ""))

            strategy = strategy_cls(**strategy_params)
            combined_equity, all_trades, individual_results = run_portfolio_backtest(
                data_dict, strategy,
                initial_cash=initial_cash,
                commission_rate=pf_commission,
                stamp_tax=pf_stamp,
                slippage=pf_slippage,
            )

            if combined_equity is None or len(combined_equity) == 0:
                st.error("回测失败")
                st.stop()

            # 基准
            benchmark_df = None
            if show_benchmark:
                try:
                    benchmark_df = get_index_data(
                        combined_equity["date"].iloc[0].strftime("%Y-%m-%d"),
                        combined_equity["date"].iloc[-1].strftime("%Y-%m-%d"),
                    )
                except Exception:
                    pass

            perf = calc_performance(combined_equity, all_trades, initial_cash)

        # 指标
        st.markdown("---")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("组合收益率", perf.get("总收益率", "-"))
        m2.metric("年化收益", perf.get("年化收益率", "-"))
        m3.metric("夏普比率", perf.get("夏普比率", "-"))
        m4.metric("最大回撤", perf.get("最大回撤", "-"))
        m5.metric("胜率", perf.get("胜率", "-"))
        m6.metric("总交易", perf.get("交易次数", "-"))

        # 个股独立绩效
        st.markdown("### 各股票独立绩效")
        rows = []
        for code, res in individual_results.items():
            p = calc_performance(res["equity"], res["trades"], initial_cash / len(codes))
            rows.append({
                "代码": code,
                "名称": get_stock_name(code),
                "总收益率": p.get("总收益率", "-"),
                "年化收益": p.get("年化收益率", "-"),
                "夏普": p.get("夏普比率", "-"),
                "最大回撤": p.get("最大回撤", "-"),
                "胜率": p.get("胜率", "-"),
                "交易次数": p.get("交易次数", "-"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # 组合对比图
        fig_comp = plot_portfolio_comparison(individual_results, combined_equity, initial_cash)
        st.plotly_chart(fig_comp, use_container_width=True)

        # 资金曲线 + 基准
        st.plotly_chart(
            plot_equity_curve(combined_equity, benchmark_df, initial_cash, title="组合收益 vs 沪深300"),
            use_container_width=True,
        )

        # 回撤
        dd_df = calc_drawdown_series(combined_equity)
        st.plotly_chart(plot_drawdown(dd_df), use_container_width=True)

        # 月度收益热力图 (组合)
        if len(combined_equity) > 60:
            try:
                hm = monthly_returns(combined_equity)
                fig_hm = plot_monthly_heatmap(hm)
                if fig_hm:
                    ui_micro_head("月度收益热力图", "用更直观的方式观察组合在不同月份的表现。")
                    st.plotly_chart(fig_hm, use_container_width=True)
            except Exception:
                pass

        # 单个股票收益曲线对比 (叠加)
        try:
            import plotly.graph_objects as go
            fig_compare = go.Figure()
            for code, res in individual_results.items():
                eq = res["equity"]
                ret = (eq["equity"] / eq["equity"].iloc[0] - 1) * 100
                name = get_stock_name(code) or code
                fig_compare.add_trace(go.Scatter(
                    x=eq["date"], y=ret, mode="lines",
                    name=name, line=dict(width=1.5),
                ))
            # 加组合线
            comb_ret = (combined_equity["equity"] / combined_equity["equity"].iloc[0] - 1) * 100
            fig_compare.add_trace(go.Scatter(
                x=combined_equity["date"], y=comb_ret, mode="lines",
                name="组合", line=dict(width=3, color="#B79A62"),
            ))
            fig_compare.update_layout(
                title="各股票收益曲线对比（归一化）",
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            )
            style_figure(fig_compare, title="各股票收益曲线对比（归一化）", height=450, x_title="日期", y_title="累计收益率 (%)")
            ui_micro_head("个股收益曲线对比", "查看各标的与组合的归一化收益走势。")
            st.plotly_chart(fig_compare, use_container_width=True)
        except Exception:
            pass

        # 盈亏图
        fig_pnl = plot_trade_pnl(all_trades)
        if fig_pnl:
            st.plotly_chart(fig_pnl, use_container_width=True)

        # 交易明细
        if all_trades is not None and len(all_trades) > 0:
            st.markdown("### 交易明细")
            col_tb, col_btn = st.columns([4, 1])
            with col_tb:
                st.dataframe(all_trades, use_container_width=True, hide_index=True)
            with col_btn:
                csv_download_link(all_trades, "portfolio_trades.csv", "导出 CSV")

        # 全量指标导出
        perf_df = pd.DataFrame(list(perf.items()), columns=["指标", "值"])
        st.markdown("### 全部绩效指标")
        col_tb, col_btn = st.columns([4, 1])
        with col_tb:
            st.dataframe(perf_df, use_container_width=True, hide_index=True)
        with col_btn:
            csv_download_link(perf_df, "portfolio_perf.csv", "导出 CSV")


# =============================================================
# TAB 3: 自动选股 (NEW)
# =============================================================
elif tab == "🎯 自动选股":
    ui_module_header("04", "信号筛选", "在可投资股票池中叠加技术条件、价格边界与回看区间，用统一评分建立候选标的的研究优先级。", "把庞大股票池压缩成一份可解释、可排序、可继续验证的工作清单。", ["定义筛选条件", "设定样本边界", "并行扫描排序", "流转候选名单"], variant="screener")

    ui_note_banner("选股结果支持与模拟盘、自动交易模块联动，适合盘前筛查、盘中跟踪和演示展示。")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("**筛选条件**")
        all_conditions = list(SCREENER_STRATEGIES.keys())
        # 默认只选买入条件
        default_conds = [c for c in all_conditions if not c.endswith("🔻")]
        selected_conds = st.multiselect(
            "选择条件(多选)", all_conditions,
            default=default_conds[:3],
            help="选中的条件越多, 筛选越严格",
        )

        price_min, price_max = st.slider(
            "股价范围(元)", 0.0, 500.0, (5.0, 200.0), step=1.0,
        )

    with col2:
        st.markdown("**排序和数量**")
        sort_by = st.radio("排序方式", ["综合评分", "信号强度"], horizontal=True)
        max_stocks = st.slider("最多返回", 10, 100, 30)

    # 高级筛选选项
    ui_micro_head("高级选项", "并行与回看区间保持直接可见，适合连续筛查。")
    c1, c2 = st.columns(2)
    max_workers = c1.slider("并行线程数", 2, 10, 6,
                            help="越大扫描越快, 但可能被akshare限流")
    lookback_days = c2.slider("数据天数", 60, 365, 180,
                              help="扫描使用的历史数据天数, 越久越准确但越慢")

    # 进度显示
    progress_bar = st.progress(0, text="准备扫描...")
    status_text = st.empty()

    def update_progress(current, total):
        pct = min(1.0, current / max(total, 1))
        progress_bar.progress(pct)
        if current % 50 == 0 or current == total:
            status_text.text(f"扫描进度: {current}/{total} ({pct*100:.0f}%)")

    if st.button("开始全市场选股", type="primary"):
        if not selected_conds:
            st.warning("请至少选择一个筛选条件")
            st.stop()
        st.session_state.screener_running = True

        try:
            with st.spinner("正在全市场扫描, 请稍候..."):
                result_df = run_screener(
                    conditions=selected_conds,
                    price_min=price_min,
                    price_max=price_max,
                    max_stocks=max_stocks,
                    sort_by=sort_by,
                    max_workers=max_workers,
                    progress_callback=update_progress,
                    lookback_days=lookback_days,
                )

                st.session_state.screener_result = result_df
                workspace.audit(
                    "MARKET_SCREEN",
                    f"Screened universe and returned {0 if result_df is None else len(result_df)} candidates",
                    {"conditions": selected_conds, "sort_by": sort_by},
                )

            progress_bar.progress(1.0)
            status_text.text(f"扫描完成!")

        except Exception as e:
            st.error(f"选股异常: {e}")
            st.session_state.screener_running = False

    # 显示结果
    result = st.session_state.screener_result
    if result is not None and len(result) > 0:
        st.markdown(f"### 筛选结果 / {len(result)} 只股票")

        # 统计概览
        avg_score = result["综合评分"].mean()
        avg_signal = result["信号强度"].mean()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("符合条件的股票", f"{len(result)}只")
        m2.metric("平均综合评分", f"{avg_score:.1f}")
        m3.metric("平均信号强度", f"{avg_signal:.1f}")
        m4.metric("筛选条件", f"{len(selected_conds) if selected_conds else '全部'}个")

        # 表格
        st.dataframe(result, use_container_width=True)

        # 导出
        col_btn, _ = st.columns([1, 5])
        with col_btn:
            csv_download_link(result, "screener_result.csv", "导出结果")

        # 信号分布统计
        if "信号" in result.columns:
            st.markdown("### 信号分布")
            signal_counts = result["信号"].str.split(" | ", expand=True, regex=False).stack().value_counts()
            signal_df = signal_counts.reset_index()
            signal_df.columns = ["信号类型", "出现次数"]
            plot_signal_distribution(signal_counts)
            st.dataframe(signal_df, use_container_width=True, hide_index=True)

        # 一键加入模拟盘
        st.markdown("### 后续行动")
        if st.button("加入模拟盘关注"):
            if st.session_state.sim_broker is None:
                st.session_state.sim_broker = SimBroker(
                    initial_cash=1_000_000,
                    state_file=os.path.join(os.path.dirname(__file__), "sim_account.json"),
                )
                st.session_state.sim_broker.connect()

            codes = result["代码"].tolist()[:10]  # 最多10只
            persistent_watchlist = workspace.add_watchlist(codes, source="market_screener")
            st.success(f"已将 {len(codes)} 只候选股票写入研究关注池，可前往模拟执行或自动交易继续验证。")

            # 保存到session_state供其他页面使用
            st.session_state["screener_codes"] = codes
            st.info(f"选股代码: {', '.join(codes)}")
            st.caption(f"持久关注池当前共 {len(persistent_watchlist)} 只标的")

    elif result is not None:
        st.warning("当前条件下没有找到符合条件的股票, 请放宽筛选条件后重试")
        progress_bar.progress(0)
        status_text.text("")

    # 快速选股快捷入口 (放在sidebar底部)
    with st.sidebar:
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div style="color:#636678;font-size:0.72rem;padding:0.25rem 0.5rem;letter-spacing:0.05em;text-transform:uppercase">快速筛选</div>', unsafe_allow_html=True)
        quick_cond = st.selectbox("一键筛选", list(SCREENER_STRATEGIES.keys()),
                                  index=0, key="quick_screen")
        if st.button("执行"):
            try:
                from quant_a.screener import run_screener_simple
                result = run_screener_simple(quick_cond, top_n=20)
                if result is not None and len(result) > 0:
                    st.session_state.screener_result = result
                    st.success(f"共找到 {len(result)} 只股票")
                else:
                    st.warning("没有找到符合条件股票")
            except Exception as e:
                st.error(f"选股失败: {e}")


# =============================================================
# TAB 4: 模拟盘交易 (增强版)
# =============================================================
elif tab == "💰 模拟盘交易":
    ui_module_header("05", "模拟执行", "用本地仿真账户承接研究结论，集中管理现金、持仓、订单与交易记录，在不承担真实资本风险的前提下检验执行流程。", "确认研究信号能否转化为纪律化、可记录、可复盘的交易动作。", ["审阅账户敞口", "承接候选标的", "执行模拟订单", "复盘交易记录"], variant="paper")

    if st.session_state.sim_broker is None:
        st.session_state.sim_broker = SimBroker(
            initial_cash=1_000_000,
            state_file=os.path.join(os.path.dirname(__file__), "sim_account.json"),
        )
        st.session_state.sim_broker.connect()

    broker = st.session_state.sim_broker

    # 账户概览
    account = broker.get_account()
    total_value = account.total_value
    total_pnl = account.total_pnl
    pnl_pct = ((total_value / 1_000_000) - 1) * 100

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总资产", fmt_yuan(total_value))
    m2.metric("可用资金", fmt_yuan(account.cash))
    m3.metric("持仓市值", fmt_yuan(total_value - account.cash))
    m4.metric("累计盈亏", fmt_yuan(total_pnl),
              delta=f"{pnl_pct:.2f}%" if total_pnl >= 0 else f"{pnl_pct:.2f}%")

    # 选股联动: 显示筛选结果推荐
    ui_note_banner("本页可直接承接选股结果，快速完成从候选标的到模拟下单的闭环验证。")
    if st.session_state.get("screener_codes"):
        ui_micro_head("选股推荐", "点击标的即可快速填入下单区。")
        rec_codes = st.session_state["screener_codes"][:10]
        rec_cols = st.columns(5)
        for i, code in enumerate(rec_codes):
            name = get_stock_name(code)
            with rec_cols[i % 5]:
                if st.button(f"{code} {name}", key=f"rec_{code}"):
                    # 自动填入订单
                    st.session_state["order_code"] = code
                    st.rerun()

    # 持仓
    st.markdown("### 当前持仓")
    if account.positions:
        pos_data = []
        for code, pos in account.positions.items():
            pos_data.append({
                "代码": code, "名称": pos.name or get_stock_name(code),
                "持仓(股)": pos.shares, "成本价": f"{pos.cost_price:.2f}",
                "现价": f"{pos.current_price:.2f}",
                "市值": fmt_yuan(pos.market_value),
                "盈亏": fmt_yuan(pos.pnl),
                "盈亏%": f"{pos.pnl_pct:.2f}%",
            })
        st.dataframe(pd.DataFrame(pos_data), use_container_width=True, hide_index=True)
    else:
        st.info("暂无持仓")

    # 手动下单
    st.markdown("### 订单录入")

    default_code = st.session_state.get("order_code", "600519")
    oc1, oc2, oc3, oc4, oc5 = st.columns([2, 1, 1, 1, 1])
    with oc1:
        order_code = st.text_input("股票代码", value=default_code, key="order_code_input")
        name = get_stock_name(order_code)
        if name:
            st.caption(f"证券名称 / {name}")
    with oc2:
        rt_price = broker.get_realtime_price(order_code)
        st.metric("最新价", f"{rt_price:.2f}" if rt_price > 0 else "-", delta=None)
        manual_price = st.number_input("委托价", value=float(rt_price) if rt_price > 0 else 0.01,
                                       min_value=0.01, format="%.2f")
    with oc3:
        order_shares = st.number_input("数量(股)", value=100, min_value=100, step=100)
    with oc4:
        st.write("")
        st.write("")
        order_type = st.radio("方向", ["买入", "卖出"], horizontal=True, label_visibility="collapsed")
    with oc5:
        st.write("")
        st.write("")
        submit_btn = st.button("提交订单", type="primary")

    if submit_btn:
        if order_type == "买入":
            order = broker.buy(order_code, manual_price, order_shares)
        else:
            order = broker.sell(order_code, manual_price, order_shares)

        if order.status == "FILLED":
            workspace.audit(
                "PAPER_ORDER_FILLED",
                f"{order_type} {order_code} {order_shares} shares",
                {"code": order_code, "shares": order_shares, "price": order.filled_price},
            )
            st.success(f"{'买入' if order_type=='买入' else '卖出'}成交 / "
                       f"{order_code} {order_shares}股 @ {order.filled_price}")
        else:
            workspace.audit(
                "PAPER_ORDER_REJECTED",
                f"{order_type} {order_code} rejected",
                {"reason": order.msg},
            )
            st.error(order.msg)
        st.rerun()

    # 交易记录
    if broker.trade_log:
        st.markdown("### 交易记录")
        log_df = pd.DataFrame(broker.trade_log)
        col_tb, col_btn = st.columns([4, 1])
        with col_tb:
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        with col_btn:
            csv_download_link(log_df, "sim_trade_log.csv", "导出 CSV")

    # 重置
    st.markdown("---")
    col_r1, col_r2 = st.columns([1, 6])
    with col_r1:
        if st.button("重置账户", type="secondary"):
            broker.reset()
            st.success("模拟账户已重置 ¥1,000,000")
            st.rerun()


# =============================================================
# TAB 5: 自动交易 (增强版)
# =============================================================
elif tab == "🤖 自动交易":
    ui_module_header("06", "自动交易", "围绕策略、股票池、轮询频率与单股仓位上限配置自动化引擎，并通过状态与日志持续观察执行结果。", "在明确的风控边界内，把策略信号稳定地转化为可监控的执行流程。", ["选择交易模式", "配置策略与股票池", "设定风控参数", "监控状态与日志"], variant="engine")

    ui_note_banner("自动交易页建议结合选股结果作为股票池输入，先在模拟盘验证，再切换至实盘适配。")

    # 选股联动
    screener_codes = st.session_state.get("screener_codes", [])
    if screener_codes:
        st.info(f"候选池 / 当前有 {len(screener_codes)} 只筛选结果可用")

    # 交易模式
    trade_mode = st.radio("交易模式", ["模拟盘", "实盘(easytrader)"], horizontal=True)
    if trade_mode == "实盘(easytrader)":
        st.warning("注意: 实盘需要Windows + 已登录东方财富/同花顺客户端。当前macOS仅支持模拟盘。")
        exe_path = st.text_input("客户端路径(xiadan.exe)", value="")

    # 策略配置
    st.markdown("### 策略配置")
    sc1, sc2 = st.columns(2)
    with sc1:
        auto_s_name = st.selectbox("策略", list(STRATEGY_REGISTRY.keys()), key="auto_s")
    with sc2:
        auto_cls, auto_defs, _ = STRATEGY_REGISTRY[auto_s_name]
        if auto_s_name == "均线交叉":
            ma_s = st.number_input("短期均线", value=5, min_value=1, max_value=60)
            ma_l = st.number_input("长期均线", value=20, min_value=5, max_value=250)
            auto_strategy = MovingAverageCross(short=ma_s, long=ma_l)
        else:
            auto_strategy = auto_cls(**auto_defs)

    # 股票池
    st.markdown("### 股票池")
    default_pool = "600519, 000858, 002594"
    if screener_codes:
        default_pool = ", ".join(screener_codes[:10])

    pool_input = st.text_area("股票代码(逗号分隔)", value=default_pool, height=80)
    stock_pool = normalize_codes(pool_input)

    # 引擎参数
    st.markdown("### 引擎参数")
    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        check_interval = st.number_input("检查间隔(秒)", value=60, min_value=10, max_value=3600)
    with ec2:
        max_pos_pct = st.slider("单股最大仓位(%)", value=25, min_value=5, max_value=100) / 100
    with ec3:
        trade_time_only = st.checkbox("仅交易时段运行", value=True)

    # 运行控制
    st.markdown("---")
    col_start, col_stop, col_once = st.columns(3)

    with col_start:
        if st.button("启动引擎", type="primary"):
            if trade_mode == "模拟盘":
                broker = SimBroker(state_file=os.path.join(os.path.dirname(__file__), "sim_account.json"))
            else:
                broker = EasytraderBroker(client="eastmoney")
                broker.connect(exe_path=exe_path)

            st.session_state.live_engine = LiveTradingEngine(
                broker=broker, strategy=auto_strategy,
                stock_pool=stock_pool, check_interval=check_interval,
                max_position_pct=max_pos_pct, trade_time_only=trade_time_only,
            )

            def on_update(sig):
                st.session_state.engine_logs.append(sig)
                st.session_state.engine_logs = st.session_state.engine_logs[-100:]

            st.session_state.live_engine.start(on_update=on_update)
            workspace.audit(
                "ENGINE_START",
                f"Started {trade_mode} engine for {len(stock_pool)} symbols",
                {"strategy": auto_s_name, "pool": stock_pool, "max_position_pct": max_pos_pct},
            )
            st.success("自动交易引擎已启动。")

    with col_stop:
        if st.button("停止引擎"):
            if st.session_state.live_engine:
                st.session_state.live_engine.stop()
                st.session_state.live_engine = None
                workspace.audit("ENGINE_STOP", "Automatic trading engine stopped")
                st.success("引擎已停止")
            else:
                st.warning("引擎未运行")

    with col_once:
        if st.button("执行一次扫描"):
            if trade_mode == "模拟盘":
                broker = SimBroker(state_file=os.path.join(os.path.dirname(__file__), "sim_account.json"))
            else:
                broker = EasytraderBroker(client="eastmoney")
                broker.connect(exe_path=exe_path)

            temp_engine = LiveTradingEngine(
                broker=broker, strategy=auto_strategy,
                stock_pool=stock_pool, trade_time_only=False,
            )
            results = temp_engine.run_once()
            workspace.audit(
                "ENGINE_SCAN",
                f"Completed one-time scan for {len(stock_pool)} symbols",
                {"strategy": auto_s_name, "pool": stock_pool},
            )
            for r in results:
                icon = "BUY" if r["signal"] == 1 else "SELL" if r["signal"] == -1 else "HOLD"
                st.write(f"{icon} {r['code']}: {r['msg']} (价格: {r.get('price', '-')})")

    # 状态
    st.markdown("### 引擎状态")
    if st.session_state.live_engine and st.session_state.live_engine.is_running:
        eng = st.session_state.live_engine
        st.success(f"运行中 / 股票池 {len(eng.stock_pool)} 只 / 轮询间隔 {eng.check_interval}s")
    else:
        st.info("引擎状态 / 未运行")

    # 日志
    st.markdown("### 信号日志")
    if st.session_state.engine_logs:
        log_df = pd.DataFrame(st.session_state.engine_logs)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无信号记录")

    ui_micro_head("研究工作台", "关注池、策略快照与执行活动统一留痕；轻量接入 QuantDinger 的研究工作流理念。")
    hub_watch, hub_snap, hub_audit = st.tabs(["关注池", "策略快照", "执行审计"])
    with hub_watch:
        watch_rows = workspace.watchlist()
        if watch_rows:
            watch_df = pd.DataFrame(watch_rows)
            watch_df = watch_df.rename(columns={"code": "代码", "source": "来源", "added_at": "首次加入", "updated_at": "最近更新", "status": "状态"})
            st.dataframe(watch_df, use_container_width=True, hide_index=True)
        else:
            st.info("关注池为空；可在自动选股页将候选标的一键加入。")
    with hub_snap:
        snapshot_rows = workspace.snapshots()
        if snapshot_rows:
            st.dataframe(pd.DataFrame(snapshot_rows), use_container_width=True, hide_index=True)
        else:
            st.info("暂无快照；完成一次策略回测后会自动创建。")
    with hub_audit:
        activity_rows = workspace.activity()
        if activity_rows:
            activity_df = pd.DataFrame([
                {"时间": row.get("time"), "事件": row.get("event"), "说明": row.get("message")}
                for row in activity_rows
            ])
            st.dataframe(activity_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无执行活动。")


# =============================================================
# TAB 6: 使用说明
# =============================================================
elif tab == "📋 使用说明":
    ui_module_header("07", "操作手册", "从系统能力、推荐工作流与策略逻辑出发，说明数据口径、交易规则和风险边界。", "让新用户在最短时间内理解正确的研究顺序，并避免对回测与执行能力产生错误预期。", ["了解系统边界", "遵循推荐流程", "掌握策略规则", "确认风险提示"], variant="guide")

    render_html("""<div class="qa-callout"><b>使用建议：</b>如果你主要做演示，请优先展示首页、策略回测和组合回测三个页面；如果你主要做日常研究，建议按“选股 → 回测 → 组合 → 模拟盘”的顺序使用。</div>""")

    col_intro, col_quick = st.columns([3, 2])

    with col_intro:
        render_html('<div class="qa-guide-panel">')
        st.markdown("""
        ### 系统概览

        奶龙资本量化交易平台是一个完整的 A 股量化研究与交易框架。

        **核心功能:**

        | 模块 | 说明 |
        |------|------|
        | 策略验证 | MA5/20 金叉死叉、MACD、RSI、布林带等策略 |
        | 组合归因 | 多股票同时回测，等权配置 |
        | 信号筛选 | 全市场扫描，多条件筛选 |
        | 模拟执行 | 本地模拟撮合，实时行情 |
        | 自动交易 | 策略信号自动下单 |

        ### 推荐工作流

        1. **信号筛选** → 扫描全市场寻找金叉、放量等候选信号
        2. **策略验证** → 检验单一标的的收益与下行风险
        3. **组合归因** → 验证多标的组合与个股贡献
        4. **模拟执行** → 复核手动或自动交易流程
        5. **自动交易** → 在风控边界内启动信号监控
        """)
        render_html('</div>')

    with col_quick:
        render_html('<div class="qa-guide-panel">')
        st.markdown("""
        ### 策略说明

        **均线交叉 (MA5/20)**
        - 金叉：MA5 上穿 MA20 → **买入**
        - 死叉：MA5 下穿 MA20 → **卖出**
        - 注: 金叉可能滞后, 建议配合RSI过滤使用

        **止损止盈策略**
        - 均线金叉买入 + ATR跟踪止损 + 固定百分比止盈
        - 适合趋势行情, 减少回撤

        **均线交叉+RSI过滤**
        - 金叉+RSI<70才买入（避免追高）
        - 死叉+RSI>30才卖出（避免杀跌）

        ### 交易规则
        - T+1: 当日买入次日才能卖出
        - 涨跌停: ±10% (普通A股)
        - 佣金: 万2.5 (最低5元)
        - 印花税: 卖出千1
        """)
        render_html('</div>')

    st.markdown("---")
    st.markdown("""
    ### 数据说明

    - 数据来源: **baostock** (本地证券数据服务器)
    - 更新频率: baostock每日更新，数据覆盖A股全量历史
    - 历史数据: 日K线, 支持前复权/后复权
    - 双真实源: efinance 与平台历史源可切换，任一失败都不会伪造行情

    ### 风险提示

    - 本系统仅供**学习和研究**使用，**不构成投资建议**
    - 历史回测收益不代表未来收益
    - 实盘交易有风险，请充分测试后再考虑实盘
    - easytrader实盘功能需 **Windows环境** + 已登录交易客户端

    ### 快捷键

    - `Ctrl+R` / `Cmd+R`: 刷新数据
    - 侧边栏: 快速选股一键执行
    """)

    ui_micro_head("依赖包列表", "保留关键运行依赖，方便部署。")
    st.code("""
    baostock>=0.9.2    # A股历史数据
    pandas>=2.0.0      # 数据处理
    numpy>=1.24.0      # 数值计算
    plotly>=5.15.0     # 交互图表
    streamlit>=1.28.0  # Web界面
    easytrader>=0.9.0  # 实盘自动化(仅Windows)
    """, language="text")


# =============================================================
# TAB 7: 关于
# =============================================================
elif tab == "ℹ️ 关于":
    ui_module_header("08", "平台信息", "奶龙资本量化研究平台面向 A 股研究、策略验证、组合归因与交易流程演练，强调证据、风险与可复现性。", "清楚界定平台能做什么、依赖哪些数据与技术，以及哪些结论不能从历史样本直接外推。", ["研究定位", "能力边界", "技术架构", "免责声明"], variant="about")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
        ### 系统简介

        **奶龙资本量化研究平台** 是一套面向 A 股市场的量化研究与交易验证框架，覆盖从数据获取、技术指标计算、策略回测、绩效分析到自动交易的完整链路。

        系统以 **akshare** 为实时数据源，内置 **6 种策略类型**（MA5/20 金叉死叉、MACD、RSI、布林带、均线+ATR 止损止盈、均线+RSI 过滤），支持单股票回测和多股票组合回测，并配有自动选股引擎和模拟盘交易功能。

        **设计理念**：让个人投资者能够快速验证交易想法，用数据驱动决策而非情绪驱动。

        ### 技术栈

        | 层级 | 技术 |
        |------|------|
        | 前端框架 | Streamlit |
        | 数据获取 | akshare (实时), baostock (历史) |
        | 数据处理 | pandas, numpy |
        | 技术指标 | 自研指标库 (MA/EMA/MACD/RSI/KDJ/BOLL/ATR/VWAP) |
        | 可视化 | plotly, 自定义图表组件 |
        | 交易接口 | 模拟撮合引擎, easytrader (Windows 实盘) |
        | 选股引擎 | 7 条件扫描 + 综合评分排序 |

        ### 版本历史

        | 版本 | 日期 | 更新内容 |
        |------|------|----------|
        | v2.0 | 2025 | Streamlit 重构，新增组合回测、模拟盘、自动交易 |
        | v1.0 | 2024 | 初始版本，CLI 回测框架 |
        """)

    with col2:
        st.markdown("""
        ### 项目地址

        本项目托管在开发者本地环境。

        ### 免责声明

        - 本系统 **仅供学习和研究使用**
        - 所有数据来源于公开市场信息（akshare / baostock）
        - **不构成任何投资建议或交易依据**
        - 历史回测收益 **不代表未来收益**
        - 实盘交易有风险，请充分测试后再考虑实盘
        - 开发者不对因使用本系统产生的任何损失承担责任

        ### 联系方式

        如有问题或建议，请提交 Issue 或联系开发者。

        ---

        **数据来源**
        - [akshare](https://github.com/akfamily/akshare) - 实时行情 + 财务数据
        - [baostock](http://baostock.com) - 历史日 K 线数据
        """)

    st.markdown("---")

    license_col1, license_col2 = st.columns(2)
    with license_col1:
        st.markdown("""
        ### 许可证

        本项目基于 MIT 许可证开源。

        ```
        MIT License

        Copyright (c) 2024-2025

        Permission is hereby granted, free of charge, to any
        person obtaining a copy of this software...
        ```
        """)
    with license_col2:
        st.markdown("""
        ### 致谢

        感谢以下开源项目为本系统提供支撑：

        - **Streamlit** - 快速构建数据应用
        - **akshare** - 丰富全面的 A 股数据接口
        - **baostock** - 稳定可靠的历史数据
        - **plotly** - 交互式图表
        - **pandas/numpy** - 数据处理基石
        """)

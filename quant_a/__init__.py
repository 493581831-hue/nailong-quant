"""
QuantA - 大A股量化交易系统

模块:
  data_fetcher:  数据获取(akshare)
  indicators:    技术指标库
  strategies:    策略框架
  backtest:      回测引擎(T+1/涨跌停/手续费)
  analysis:      绩效分析
  visualization: 可视化(Plotly)
  broker:        交易接口(模拟盘/easytrader实盘/自动交易引擎)
"""

from . import data_fetcher
from . import indicators
from . import strategies
from . import backtest
from . import analysis
from . import visualization
from . import broker

__version__ = "1.0.0"
__all__ = [
    "data_fetcher", "indicators", "strategies", "backtest",
    "analysis", "visualization", "broker",
]

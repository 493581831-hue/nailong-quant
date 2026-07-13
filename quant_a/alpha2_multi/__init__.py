"""Alpha2 multi-asset defensive momentum research engine.

The engine uses a fixed ETF universe, monthly signal formation, next-day
execution, absolute/cross-sectional momentum and an ex-ante volatility cap.
It is intentionally long/cash only and never introduces leverage.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd


ASSET_UNIVERSE = {
    "510300": {"name": "沪深300", "market": "sh", "kind": "中国核心"},
    "510500": {"name": "中证500", "market": "sh", "kind": "中国成长"},
    "159915": {"name": "创业板", "market": "sz", "kind": "中国成长"},
    "510880": {"name": "红利ETF", "market": "sh", "kind": "中国红利"},
    "518880": {"name": "黄金ETF", "market": "sh", "kind": "避险资产"},
    "511010": {"name": "国债ETF", "market": "sh", "kind": "防御资产"},
    "513100": {"name": "纳指ETF", "market": "sh", "kind": "海外成长"},
    "159920": {"name": "恒生ETF", "market": "sz", "kind": "港股核心"},
}


@dataclass(frozen=True)
class MultiAssetParams:
    momentum_days: int = 252
    trend_days: int = 120
    volatility_target: float = 0.12
    holdings: int = 1
    cost_bps: float = 10.0


def _normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
        "最低": "low", "成交量": "volume", "成交额": "amount",
    }
    result = frame.rename(columns={key: value for key, value in mapping.items() if key in frame.columns}).copy()
    if "股票名称" in result.columns and "name" not in result.columns:
        result = result.rename(columns={"股票名称": "name"})
    required = ["date", "open", "close", "high", "low", "volume"]
    missing = [column for column in required if column not in result.columns]
    if missing:
        raise ValueError(f"行情缺少字段: {', '.join(missing)}")
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in required[1:] + (["amount"] if "amount" in result.columns else []):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna(subset=["date", "close"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _tencent_range(code: str, start: str, end: str) -> pd.DataFrame:
    asset = ASSET_UNIVERSE[code]
    symbol = f"{asset['market']}{code}"
    param = f"{symbol},day,{start},{end},640,qfq"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + urllib.parse.quote(param)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read())
    node = payload.get("data", {}).get(symbol, {})
    rows = node.get("qfqday", node.get("day", []))
    return pd.DataFrame([{
        "date": row[0], "open": row[1], "close": row[2], "high": row[3],
        "low": row[4], "volume": row[5],
    } for row in rows])


def _fetch_tencent_full(code: str, start_date, end_date) -> pd.DataFrame:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    chunks = []
    year = start.year
    while year <= end.year:
        chunk_start = max(start, pd.Timestamp(year=year, month=1, day=1))
        chunk_end = min(end, pd.Timestamp(year=min(year + 1, end.year), month=12, day=31))
        chunks.append(_tencent_range(code, chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        year += 2
    if not chunks:
        return pd.DataFrame()
    return _normalise_frame(pd.concat(chunks, ignore_index=True))


def fetch_etf_history(code: str, start_date, end_date, source: str = "腾讯证券") -> Tuple[pd.DataFrame, str]:
    """Fetch one ETF with an explicit source and no synthetic-data fallback."""

    errors = []
    ordered_sources = [source] + [item for item in ("腾讯证券", "AKShare", "efinance") if item != source]
    for candidate in ordered_sources:
        try:
            if candidate == "腾讯证券":
                frame = _fetch_tencent_full(code, start_date, end_date)
            elif candidate == "AKShare":
                import akshare as ak
                frame = ak.fund_etf_hist_em(
                    symbol=code, period="daily",
                    start_date=pd.Timestamp(start_date).strftime("%Y%m%d"),
                    end_date=pd.Timestamp(end_date).strftime("%Y%m%d"), adjust="qfq",
                )
                frame = _normalise_frame(frame)
            else:
                from quant_a.data_fetcher import get_daily_data_efinance
                frame = get_daily_data_efinance(code, start_date, end_date, "qfq")
                efinance_route = frame.attrs.get("provider", "efinance / 东方财富直连")
                frame = _normalise_frame(frame)
            if frame is not None and len(frame) >= 320:
                actual_source = efinance_route if candidate == "efinance" else candidate
                return frame, actual_source
            errors.append(f"{candidate}: 样本不足")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("；".join(errors))


def fetch_asset_pool(start_date, end_date, source: str = "腾讯证券") -> Tuple[Dict[str, pd.DataFrame], Dict[str, str]]:
    data, provenance = {}, {}
    for code in ASSET_UNIVERSE:
        frame, actual_source = fetch_etf_history(code, start_date, end_date, source)
        data[code] = frame
        provenance[code] = actual_source
    return data, provenance


def _performance(returns: pd.Series) -> dict:
    returns = returns.dropna()
    if returns.empty:
        return {"annual_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0, "volatility": 0.0, "total_return": 0.0, "win_rate": 0.0}
    equity = (1 + returns).cumprod()
    years = len(returns) / 242
    volatility = returns.std() * np.sqrt(242)
    return {
        "annual_return": float(equity.iloc[-1] ** (1 / years) - 1),
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
        "sharpe": float(returns.mean() * 242 / volatility) if volatility else 0.0,
        "volatility": float(volatility),
        "total_return": float(equity.iloc[-1] - 1),
        "win_rate": float((returns > 0).mean()),
    }


def run_multi_asset_alpha2(data: Dict[str, pd.DataFrame], params: MultiAssetParams) -> dict:
    """Run the deterministic, next-day-executed Alpha2 allocation model."""

    close = pd.concat({code: frame.set_index("date")["close"] for code, frame in data.items()}, axis=1).sort_index()
    close = close.ffill(limit=3).dropna()
    returns = close.pct_change(fill_method=None).fillna(0.0)
    momentum = close / close.shift(params.momentum_days) - 1
    trend = close.rolling(params.trend_days).mean()
    volatility = returns.rolling(63).std() * np.sqrt(242)
    score = momentum / volatility.clip(lower=0.08)
    eligible = (momentum > 0) & (close > trend)

    target = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    current = pd.Series(0.0, index=close.columns)
    rebalance_dates = close.groupby(close.index.to_period("M")).head(1).index
    warmup = max(params.momentum_days, params.trend_days, 63)

    for index, date in enumerate(close.index):
        if index < warmup:
            continue
        if date in rebalance_dates:
            current[:] = 0.0
            selected = score.loc[date].where(eligible.loc[date]).dropna().nlargest(params.holdings)
            if not selected.empty:
                inverse_vol = 1 / volatility.loc[date, selected.index].clip(lower=0.08)
                raw_weight = inverse_vol / inverse_vol.sum()
                window = returns.loc[:date, selected.index].tail(63)
                covariance = window.cov() * 242
                portfolio_vol = float(np.sqrt(max(raw_weight.values @ covariance.values @ raw_weight.values, 0)))
                scale = min(1.0, params.volatility_target / portfolio_vol) if portfolio_vol else 0.0
                current.loc[selected.index] = raw_weight * scale
        target.loc[date] = current

    executed = target.shift(1).fillna(0.0)
    turnover = executed.diff().abs().sum(axis=1).fillna(executed.abs().sum(axis=1))
    strategy_return = (executed * returns).sum(axis=1) - turnover * params.cost_bps / 10_000
    benchmark_return = returns["510300"]
    valid_start = close.index[warmup]
    strategy_return = strategy_return.loc[valid_start:]
    benchmark_return = benchmark_return.loc[valid_start:]

    equity = pd.DataFrame({
        "Alpha2": (1 + strategy_return).cumprod(),
        "沪深300": (1 + benchmark_return).cumprod(),
    })
    equity["drawdown"] = equity["Alpha2"] / equity["Alpha2"].cummax() - 1
    equity.index.name = "date"
    split_date = pd.Timestamp("2021-01-01")
    latest = executed.iloc[-1]
    latest_scores = score.iloc[-1]
    latest_momentum = momentum.iloc[-1]
    holdings = pd.DataFrame([{
        "代码": code,
        "资产": ASSET_UNIVERSE[code]["name"],
        "类型": ASSET_UNIVERSE[code]["kind"],
        "模型权重": float(weight),
        "动量": float(latest_momentum.get(code, np.nan)),
        "风险调整得分": float(latest_scores.get(code, np.nan)),
    } for code, weight in latest.items() if weight > 0.0001]).sort_values("模型权重", ascending=False)

    return {
        "equity": equity.reset_index(),
        "weights": executed,
        "turnover": turnover.loc[valid_start:],
        "holdings": holdings,
        "cash_weight": float(max(0.0, 1 - latest.sum())),
        "strategy": _performance(strategy_return),
        "benchmark": _performance(benchmark_return),
        "train": _performance(strategy_return.loc[:"2020-12-31"]),
        "test": _performance(strategy_return.loc[split_date:]),
        "last_date": close.index[-1],
        "observations": len(strategy_return),
        "trade_count": int((turnover.loc[valid_start:] > 0.0001).sum()),
        "params": params,
    }

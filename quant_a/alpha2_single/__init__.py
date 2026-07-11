"""Single-asset adaptation of the Alpha² formulaic-alpha pipeline.

The paper evaluates daily cross-sectional IC on an equity universe. A single
asset has no cross-section, so this module uses chronological time-series IC
while preserving the paper's key ideas: dimensionally valid expressions,
forward-return targets, diversity-aware selection and alpha combination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


@dataclass
class AlphaCandidate:
    name: str
    formula: str
    family: str
    dimension: str = "dimensionless"


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.replace(0, np.nan)


def _rolling_zscore(series: pd.Series, window: int = 60) -> pd.Series:
    mean = series.rolling(window, min_periods=max(12, window // 3)).mean()
    std = series.rolling(window, min_periods=max(12, window // 3)).std()
    return ((series - mean) / std.replace(0, np.nan)).clip(-5, 5)


def build_candidate_library(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[AlphaCandidate]]:
    """Build only dimensionally valid formulas from OHLCV operands."""

    frame = df.copy().sort_values("date").reset_index(drop=True)
    o, h, l, c = (frame[key].astype(float) for key in ("open", "high", "low", "close"))
    volume = frame.get("volume", pd.Series(1.0, index=frame.index)).astype(float).clip(lower=1)
    fallback_amount = volume * (o + c) / 2
    amount = frame.get("amount", fallback_amount).astype(float)
    amount = amount.where(np.isfinite(amount) & (amount > 0), fallback_amount)
    vwap = _safe_div(amount, volume).replace([np.inf, -np.inf], np.nan).fillna((o + c) / 2)
    price_range = (h - l).abs()
    returns = c.pct_change()
    log_volume_change = np.log(volume).diff()

    values: Dict[str, pd.Series] = {}
    specs: List[AlphaCandidate] = []

    def add(name: str, formula: str, family: str, value: pd.Series) -> None:
        values[name] = _rolling_zscore(value.replace([np.inf, -np.inf], np.nan))
        specs.append(AlphaCandidate(name, formula, family))

    add("candle_body", "(close - open) / (high - low)", "intraday", _safe_div(c - o, price_range))
    add("close_location", "(2×close - high - low) / (high - low)", "intraday", _safe_div(2*c - h - l, price_range))
    add("gap_reversal", "-(open / delay(close,1) - 1)", "reversal", -(o / c.shift(1) - 1))
    add("vwap_distance", "close / vwap - 1", "liquidity", c / vwap - 1)

    for window in (5, 10, 20, 40, 60):
        add(f"momentum_{window}", f"close / delay(close,{window}) - 1", "momentum", c / c.shift(window) - 1)
        add(f"mean_distance_{window}", f"close / ts_mean(close,{window}) - 1", "trend", c / c.rolling(window).mean() - 1)
        add(f"volume_shock_{window}", f"ln(volume / ts_mean(volume,{window}))", "liquidity", np.log(volume / volume.rolling(window).mean()))
        add(f"pv_corr_{window}", f"ts_corr(return, Δln(volume),{window})", "interaction", returns.rolling(window).corr(log_volume_change))
        add(f"range_expansion_{window}", f"(high-low) / ts_mean(high-low,{window}) - 1", "volatility", price_range / price_range.rolling(window).mean() - 1)

    alpha_frame = pd.DataFrame(values, index=frame.index)
    return alpha_frame, specs


def _corr(x: pd.Series, y: pd.Series, method: str = "pearson") -> float:
    valid = pd.concat([x, y], axis=1).dropna()
    if len(valid) < 20 or valid.iloc[:, 0].std() == 0 or valid.iloc[:, 1].std() == 0:
        return np.nan
    if method == "spearman":
        return float(valid.iloc[:, 0].rank().corr(valid.iloc[:, 1].rank()))
    return float(valid.iloc[:, 0].corr(valid.iloc[:, 1]))


def discover_single_asset_alphas(
    df: pd.DataFrame,
    forward_days: int = 20,
    top_k: int = 8,
    diversity_strength: float = 0.65,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score and combine valid alpha formulas using chronological splits."""

    market = df.copy().sort_values("date").reset_index(drop=True)
    alpha_values, specs = build_candidate_library(market)
    target = market["close"].shift(-forward_days) / market["close"] - 1
    n = len(market)
    train_end, valid_end = int(n * .60), int(n * .80)
    splits = {"train": slice(0, train_end), "valid": slice(train_end, valid_end), "test": slice(valid_end, n)}

    rows = []
    for spec in specs:
        series = alpha_values[spec.name]
        row = {
            "name": spec.name,
            "formula": spec.formula,
            "family": spec.family,
            "dimension": spec.dimension,
        }
        for split_name, split in splits.items():
            row[f"{split_name}_ic"] = _corr(series.iloc[split], target.iloc[split])
            row[f"{split_name}_rank_ic"] = _corr(series.iloc[split], target.iloc[split], method="spearman")
        rows.append(row)

    scored = pd.DataFrame(rows).dropna(subset=["valid_ic"]).copy()
    pool = scored.sort_values("valid_ic", key=lambda values: values.abs(), ascending=False).copy()
    selected_names: List[str] = []
    selection_rows = []
    while len(selected_names) < min(top_k, len(pool)):
        best_idx, best_payload = None, None
        for idx, row in pool.iterrows():
            if row["name"] in selected_names:
                continue
            if selected_names:
                correlations = [abs(_corr(alpha_values[row["name"]], alpha_values[name])) for name in selected_names]
                finite_corr = [value for value in correlations if np.isfinite(value)]
                max_corr = max(finite_corr) if finite_corr else 0.0
            else:
                max_corr = 0.0
            diversity_score = abs(row["valid_ic"]) * (1 - diversity_strength * max_corr)
            if best_payload is None or diversity_score > best_payload["selection_score"]:
                best_idx = idx
                best_payload = {**row.to_dict(), "max_selected_corr": max_corr, "selection_score": diversity_score}
        if best_idx is None:
            break
        selected_names.append(str(best_payload["name"]))
        selection_rows.append(best_payload)

    selected = pd.DataFrame(selection_rows)
    combined = pd.Series(0.0, index=market.index)
    total_weight = 0.0
    for _, row in selected.iterrows():
        weight = max(float(row["selection_score"]), 1e-6)
        orientation = 1.0 if float(row["valid_ic"]) >= 0 else -1.0
        combined += orientation * weight * alpha_values[str(row["name"])].fillna(0.0)
        total_weight += weight
    if total_weight:
        combined /= total_weight

    result = market.copy()
    result["future_return_20d"] = target
    result["alpha_score"] = combined.clip(-5, 5)
    result["signal_strength"] = np.tanh(result["alpha_score"] / 1.5)
    result["split"] = np.where(result.index < train_end, "train", np.where(result.index < valid_end, "validation", "test"))
    return result, selected, scored


def backtest_single_asset_alpha(
    result: pd.DataFrame,
    initial_cash: float = 1_000_000,
    threshold: float = 0.12,
    cost_bps: float = 8.0,
    long_short: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Translate the combined alpha into next-day exposure with costs."""

    frame = result.copy()
    raw = frame["signal_strength"]
    if long_short:
        target = np.where(raw > threshold, 1.0, np.where(raw < -threshold, -1.0, 0.0))
    else:
        target = np.where(raw > threshold, 1.0, 0.0)
    frame["target_position"] = target
    frame["position"] = pd.Series(target, index=frame.index).shift(1).fillna(0.0)
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["turnover"] = frame["position"].diff().abs().fillna(frame["position"].abs())
    frame["strategy_return"] = frame["position"] * frame["asset_return"] - frame["turnover"] * cost_bps / 10_000
    frame["equity"] = initial_cash * (1 + frame["strategy_return"]).cumprod()
    frame["benchmark_equity"] = initial_cash * (1 + frame["asset_return"]).cumprod()
    frame["drawdown"] = frame["equity"] / frame["equity"].cummax() - 1

    test = frame[frame["split"] == "test"].copy()
    returns = test["strategy_return"]
    total_return = test["equity"].iloc[-1] / test["equity"].iloc[0] - 1 if len(test) > 1 else 0.0
    metrics = {
        "测试集收益": f"{total_return:.2%}",
        "测试集夏普": f"{returns.mean() / returns.std() * np.sqrt(252):.2f}" if returns.std() > 0 else "-",
        "全期最大回撤": f"{frame['drawdown'].min():.2%}",
        "测试集胜率": f"{(returns > 0).mean():.1%}",
        "全期换手": f"{frame['turnover'].sum():.0f}x",
    }
    return frame, metrics

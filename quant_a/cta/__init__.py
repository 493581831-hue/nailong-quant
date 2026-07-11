"""Research-grade CTA trend factors and a transparent daily backtester.

This first release operates on continuous OHLC histories. It supports long and
short exposures and intentionally separates signal construction from execution
so a futures data/roll adapter can be added later without changing the factors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _annualized_vol(returns: pd.Series, window: int = 20) -> pd.Series:
    return returns.rolling(window, min_periods=max(10, window // 2)).std() * np.sqrt(252)


class NailongCTA:
    """Multi-horizon time-series momentum with breakout confirmation.

    Factors
    -------
    tsmom: average volatility-normalised return over 21/63/252 sessions
    breakout: close location inside a lagged Donchian channel
    trend_quality: directional movement divided by total path length
    vol_scalar: exposure targeting based on lagged realised volatility
    """

    name = "Nailong CTA / Multi-horizon Trend"

    def __init__(
        self,
        fast_horizon: int = 21,
        medium_horizon: int = 63,
        slow_horizon: int = 252,
        breakout_window: int = 55,
        quality_window: int = 30,
        score_threshold: float = 0.22,
        quality_threshold: float = 0.18,
        target_vol: float = 0.15,
        max_leverage: float = 2.0,
    ):
        self.fast_horizon = fast_horizon
        self.medium_horizon = medium_horizon
        self.slow_horizon = slow_horizon
        self.breakout_window = breakout_window
        self.quality_window = quality_window
        self.score_threshold = score_threshold
        self.quality_threshold = quality_threshold
        self.target_vol = target_vol
        self.max_leverage = max_leverage

    def generate_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy().sort_values("date").reset_index(drop=True)
        close = frame["close"].astype(float)
        returns = close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
        vol = _annualized_vol(returns, 20).shift(1)

        horizon_scores = []
        for horizon in (self.fast_horizon, self.medium_horizon, self.slow_horizon):
            raw = close.pct_change(horizon).shift(1)
            denom = vol * np.sqrt(horizon / 252)
            horizon_scores.append(np.tanh(raw / denom.replace(0, np.nan)))
        frame["tsmom_factor"] = pd.concat(horizon_scores, axis=1).mean(axis=1)

        upper = close.rolling(self.breakout_window).max().shift(1)
        lower = close.rolling(self.breakout_window).min().shift(1)
        midpoint = (upper + lower) / 2
        half_range = ((upper - lower) / 2).replace(0, np.nan)
        frame["breakout_factor"] = ((close - midpoint) / half_range).clip(-1.5, 1.5) / 1.5

        net_move = close.diff(self.quality_window).abs()
        path = close.diff().abs().rolling(self.quality_window).sum()
        frame["trend_quality"] = (net_move / path.replace(0, np.nan)).clip(0, 1)

        frame["factor_score"] = (
            0.72 * frame["tsmom_factor"] + 0.28 * frame["breakout_factor"]
        ).clip(-1, 1)
        frame["realized_vol"] = vol
        frame["vol_scalar"] = (self.target_vol / vol.replace(0, np.nan)).clip(0, self.max_leverage)

        direction = np.where(
            (frame["factor_score"] >= self.score_threshold)
            & (frame["trend_quality"] >= self.quality_threshold),
            1.0,
            np.where(
                (frame["factor_score"] <= -self.score_threshold)
                & (frame["trend_quality"] >= self.quality_threshold),
                -1.0,
                0.0,
            ),
        )
        frame["direction"] = direction
        frame["target_exposure"] = frame["direction"] * frame["vol_scalar"].fillna(0.0)
        return frame


def run_cta_backtest(
    factor_df: pd.DataFrame,
    initial_cash: float = 1_000_000,
    cost_bps: float = 5.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Backtest next-session exposures with explicit turnover costs."""

    frame = factor_df.copy().sort_values("date").reset_index(drop=True)
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["executed_exposure"] = frame["target_exposure"].shift(1).fillna(0.0)
    frame["turnover"] = frame["executed_exposure"].diff().abs().fillna(frame["executed_exposure"].abs())
    frame["cost"] = frame["turnover"] * (cost_bps / 10_000)
    frame["strategy_return"] = frame["executed_exposure"] * frame["asset_return"] - frame["cost"]
    frame["equity"] = initial_cash * (1 + frame["strategy_return"]).cumprod()
    frame["peak"] = frame["equity"].cummax()
    frame["drawdown"] = frame["equity"] / frame["peak"] - 1

    changes = frame["direction"].ne(frame["direction"].shift(1))
    trades = frame.loc[changes & frame["direction"].notna(), [
        "date", "close", "direction", "factor_score", "trend_quality", "target_exposure"
    ]].copy()
    trades["action"] = trades["direction"].map({1.0: "LONG", -1.0: "SHORT", 0.0: "FLAT"})
    trades = trades[["date", "action", "close", "factor_score", "trend_quality", "target_exposure"]]

    strategy_returns = frame["strategy_return"]
    years = max(len(frame) / 252, 1 / 252)
    total_return = frame["equity"].iloc[-1] / initial_cash - 1 if len(frame) else 0.0
    annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0
    annual_vol = strategy_returns.std() * np.sqrt(252)
    metrics = {
        "累计收益": f"{total_return:.2%}",
        "年化收益": f"{annual_return:.2%}",
        "年化波动": f"{annual_vol:.2%}",
        "夏普比率": f"{(strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)):.2f}" if strategy_returns.std() > 0 else "-",
        "最大回撤": f"{frame['drawdown'].min():.2%}" if len(frame) else "-",
        "正收益日": f"{(strategy_returns > 0).mean():.1%}",
        "换手总量": f"{frame['turnover'].sum():.1f}x",
        "方向切换": int(len(trades)),
    }
    return frame, trades, metrics


"""
EMA Crossover Strategy
----------------------
Long  when fast EMA crosses above slow EMA (+ optional trend filter)
Short when fast EMA crosses below slow EMA
Optional: RSI filter to avoid entries in overbought/oversold extremes
Optional: ATR-based volatility filter to skip low-vol environments
"""
import pandas as pd
from dataclasses import dataclass

from strategies.base import Strategy
from engine.indicators import ema, rsi, atr, crossover, crossunder


@dataclass
class EMACrossoverParams:
    fast: int = 9           # fast EMA period
    slow: int = 21          # slow EMA period
    trend_filter: int = 200 # 0 = disabled; EMA period for trend direction
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    use_rsi_filter: bool = False
    atr_period: int = 14
    atr_min_multiplier: float = 0.0  # 0 = disabled; min ATR relative to price


class EMACrossoverStrategy(Strategy):
    name = "EMA Crossover"

    def __init__(self, params: EMACrossoverParams | None = None):
        self.params = params or EMACrossoverParams()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        close = df["close"]

        fast_ema = ema(close, p.fast)
        slow_ema = ema(close, p.slow)

        long_cross = crossover(fast_ema, slow_ema)
        short_cross = crossunder(fast_ema, slow_ema)

        # Trend filter: only trade in direction of long-term EMA
        if p.trend_filter > 0:
            trend_ema = ema(close, p.trend_filter)
            long_cross = long_cross & (close > trend_ema)
            short_cross = short_cross & (close < trend_ema)

        # RSI filter: skip extreme overbought/oversold at entry
        if p.use_rsi_filter:
            r = rsi(close, p.rsi_period)
            long_cross = long_cross & (r < p.rsi_overbought)
            short_cross = short_cross & (r > p.rsi_oversold)

        # ATR volatility filter: skip trades in very quiet markets
        if p.atr_min_multiplier > 0:
            a = atr(df["high"], df["low"], close, p.atr_period)
            min_atr = close * p.atr_min_multiplier / 100
            long_cross = long_cross & (a > min_atr)
            short_cross = short_cross & (a > min_atr)

        # Exit on opposite cross
        signals = pd.DataFrame(index=df.index)
        signals["long_entry"] = long_cross.fillna(False)
        signals["long_exit"] = short_cross.fillna(False)
        signals["short_entry"] = short_cross.fillna(False)
        signals["short_exit"] = long_cross.fillna(False)

        return signals

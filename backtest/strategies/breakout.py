"""
Donchian Channel Breakout Strategy
------------------------------------
Long  when price closes above the N-bar high (breakout up)
Short when price closes below the N-bar low  (breakout down)
Exit  on opposite channel break or after X bars (time stop)
"""
import pandas as pd
from dataclasses import dataclass

from strategies.base import Strategy
from engine.indicators import donchian_channel, atr, ema


@dataclass
class BreakoutParams:
    channel_period: int = 20    # Donchian high/low lookback
    exit_period: int = 10       # Exit channel (shorter = faster exit)
    trend_filter: int = 50      # EMA period for trend direction; 0 = off
    atr_period: int = 14
    volume_filter: bool = True  # require volume > 20-bar avg on breakout
    volume_ma: int = 20


class BreakoutStrategy(Strategy):
    name = "Donchian Breakout"

    def __init__(self, params: BreakoutParams | None = None):
        self.params = params or BreakoutParams()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Entry channels (shift by 1 so we trade on the bar AFTER the breakout)
        entry_high, entry_low = donchian_channel(high, low, p.channel_period)
        exit_high, exit_low = donchian_channel(high, low, p.exit_period)

        prev_entry_high = entry_high.shift(1)
        prev_entry_low = entry_low.shift(1)
        prev_exit_low = exit_low.shift(1)
        prev_exit_high = exit_high.shift(1)

        long_entry = close > prev_entry_high
        short_entry = close < prev_entry_low

        long_exit = close < prev_exit_low
        short_exit = close > prev_exit_high

        # Trend filter
        if p.trend_filter > 0:
            trend_ema = ema(close, p.trend_filter)
            long_entry = long_entry & (close > trend_ema)
            short_entry = short_entry & (close < trend_ema)

        # Volume filter: entry only when volume > MA
        if p.volume_filter and "volume" in df.columns:
            vol_ma = df["volume"].rolling(p.volume_ma).mean()
            long_entry = long_entry & (df["volume"] > vol_ma)
            short_entry = short_entry & (df["volume"] > vol_ma)

        signals = pd.DataFrame(index=df.index)
        signals["long_entry"] = long_entry.fillna(False)
        signals["long_exit"] = long_exit.fillna(False)
        signals["short_entry"] = short_entry.fillna(False)
        signals["short_exit"] = short_exit.fillna(False)

        return signals

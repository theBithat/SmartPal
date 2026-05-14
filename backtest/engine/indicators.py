"""
Technical indicator calculations.
All functions operate on pandas Series/DataFrames and return Series.
"""
import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Returns (upper, mid, lower)."""
    mid = sma(series, period)
    std = series.rolling(period).std()
    return mid + std_dev * std, mid, mid - std_dev * std


def donchian_channel(high: pd.Series, low: pd.Series, period: int = 20):
    """Returns (upper, lower) — highest high / lowest low over period."""
    return high.rolling(period).max(), low.rolling(period).min()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical_price = (high + low + close) / 3
    cum_tp_vol = (typical_price * volume).cumsum()
    cum_vol = volume.cumsum()
    return cum_tp_vol / cum_vol


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """Returns True on the bar where a crosses above b."""
    return (a > b) & (a.shift() <= b.shift())


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    """Returns True on the bar where a crosses below b."""
    return (a < b) & (a.shift() >= b.shift())

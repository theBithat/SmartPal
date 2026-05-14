"""
Data loader — wraps both live MCP data and local CSV data into a unified DataFrame.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

from data.tv_bridge import fetch_ohlcv


def load_from_tv(count: int = 500) -> pd.DataFrame:
    """Pull OHLCV from live TradingView chart."""
    bars = fetch_ohlcv(count)
    df = pd.DataFrame(bars)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def load_from_csv(path: str | Path) -> pd.DataFrame:
    """
    Load OHLCV from a CSV file.
    Expected columns: time/date, open, high, low, close, volume (case-insensitive).
    """
    df = pd.read_csv(path)
    df.columns = df.columns.str.lower().str.strip()

    time_col = next((c for c in df.columns if c in ("time", "date", "datetime", "timestamp")), None)
    if time_col is None:
        raise ValueError("CSV must have a time/date/datetime/timestamp column")

    df[time_col] = pd.to_datetime(df[time_col])
    df = df.rename(columns={time_col: "time"}).set_index("time").sort_index()

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    if "volume" not in df.columns:
        df["volume"] = 0.0

    return df[["open", "high", "low", "close", "volume"]].astype(float)


def load_sample_data(n_bars: int = 1000, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data for testing without TradingView.
    Simulates a trending market with noise.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="1h", tz="UTC")

    # Geometric Brownian Motion price path
    returns = rng.normal(0.0002, 0.008, n_bars)
    prices = 30000.0 * np.exp(np.cumsum(returns))

    noise = rng.uniform(0.001, 0.005, n_bars)
    opens = prices * (1 + rng.normal(0, 0.002, n_bars))
    highs = prices * (1 + noise)
    lows = prices * (1 - noise)
    closes = prices
    volumes = rng.uniform(100, 5000, n_bars)

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )

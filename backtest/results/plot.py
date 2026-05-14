"""
Plotting utilities for backtest results.
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

from engine.backtest import BacktestResult


def plot_equity_curve(result: BacktestResult, title: str = "Equity Curve", save_path: str | None = None):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})

    equity = result.equity_curve["equity"]
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max * 100

    # Equity
    ax1 = axes[0]
    ax1.plot(equity.index, equity.values, color="#2196F3", linewidth=1.5, label="Portfolio")
    ax1.fill_between(equity.index, result.initial_capital, equity.values,
                     where=(equity.values >= result.initial_capital), alpha=0.1, color="green")
    ax1.fill_between(equity.index, result.initial_capital, equity.values,
                     where=(equity.values < result.initial_capital), alpha=0.1, color="red")
    ax1.axhline(result.initial_capital, color="gray", linestyle="--", linewidth=0.8, label="Start")
    ax1.set_title(title, fontsize=14)
    ax1.set_ylabel("Portfolio Value ($)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    # Drawdown
    ax2 = axes[1]
    ax2.fill_between(drawdown.index, drawdown.values, 0, color="red", alpha=0.4)
    ax2.plot(drawdown.index, drawdown.values, color="darkred", linewidth=0.8)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved plot to {save_path}")
    else:
        plt.show()
    plt.close()


def plot_trades_on_price(df: pd.DataFrame, result: BacktestResult, title: str = "Trades", save_path: str | None = None):
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(df.index, df["close"], color="#555", linewidth=0.8, label="Close", zorder=1)

    for t in result.trades:
        color = "green" if t.pnl > 0 else "red"
        marker_entry = "^" if t.direction == 1 else "v"
        ax.scatter(t.entry_time, t.entry_price, marker=marker_entry, color=color, s=60, zorder=3)
        if t.exit_time and t.exit_price:
            ax.scatter(t.exit_time, t.exit_price, marker="x", color=color, s=60, zorder=3)
            ax.plot([t.entry_time, t.exit_time], [t.entry_price, t.exit_price],
                    color=color, linewidth=0.5, alpha=0.5, zorder=2)

    ax.set_title(title)
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved plot to {save_path}")
    else:
        plt.show()
    plt.close()

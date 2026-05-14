"""
Core backtest engine.
Runs a strategy signal series against OHLCV data and computes performance metrics.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    position_size_pct: float = 0.10        # % of capital per trade
    max_open_trades: int = 1               # 1 = no pyramiding
    commission_pct: float = 0.0006        # 0.06% per side (Binance futures taker)
    slippage_pct: float = 0.0002          # 0.02% slippage estimate
    use_stop_loss: bool = True
    stop_loss_pct: float = 0.02           # 2% stop loss
    use_take_profit: bool = True
    take_profit_pct: float = 0.04         # 4% take profit (2:1 RR)
    allow_short: bool = True


@dataclass
class Trade:
    entry_bar: int
    entry_time: pd.Timestamp
    entry_price: float
    direction: int                          # 1 = long, -1 = short
    size: float                             # units
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit_bar: Optional[int] = None
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(self, df: pd.DataFrame, signals: pd.DataFrame) -> "BacktestResult":
        """
        Run backtest.
        df: OHLCV DataFrame with index = datetime
        signals: DataFrame with columns:
            - long_entry:  bool
            - long_exit:   bool
            - short_entry: bool (optional)
            - short_exit:  bool (optional)
        Returns BacktestResult.
        """
        cfg = self.config
        equity = cfg.initial_capital
        equity_curve = []
        trades: list[Trade] = []
        open_trade: Optional[Trade] = None

        bars = df.reset_index()
        sig = signals.reset_index(drop=True)

        for i, row in bars.iterrows():
            price_open = row["open"]
            price_high = row["high"]
            price_low = row["low"]
            price_close = row["close"]
            ts = row.iloc[0]  # datetime index

            # Check stop/take-profit on open trade (use high/low of bar)
            if open_trade is not None:
                exited = False

                if open_trade.direction == 1:  # long
                    if cfg.use_stop_loss and open_trade.stop_loss and price_low <= open_trade.stop_loss:
                        exit_px = open_trade.stop_loss * (1 - cfg.slippage_pct)
                        equity = self._close_trade(open_trade, i, ts, exit_px, "stop_loss", equity, trades)
                        open_trade = None
                        exited = True
                    elif cfg.use_take_profit and open_trade.take_profit and price_high >= open_trade.take_profit:
                        exit_px = open_trade.take_profit * (1 - cfg.slippage_pct)
                        equity = self._close_trade(open_trade, i, ts, exit_px, "take_profit", equity, trades)
                        open_trade = None
                        exited = True
                elif open_trade.direction == -1:  # short
                    if cfg.use_stop_loss and open_trade.stop_loss and price_high >= open_trade.stop_loss:
                        exit_px = open_trade.stop_loss * (1 + cfg.slippage_pct)
                        equity = self._close_trade(open_trade, i, ts, exit_px, "stop_loss", equity, trades)
                        open_trade = None
                        exited = True
                    elif cfg.use_take_profit and open_trade.take_profit and price_low <= open_trade.take_profit:
                        exit_px = open_trade.take_profit * (1 + cfg.slippage_pct)
                        equity = self._close_trade(open_trade, i, ts, exit_px, "take_profit", equity, trades)
                        open_trade = None
                        exited = True

                # Signal exit
                if not exited and open_trade is not None:
                    if open_trade.direction == 1 and sig.get("long_exit", pd.Series(False)).iloc[i]:
                        exit_px = price_close * (1 - cfg.slippage_pct)
                        equity = self._close_trade(open_trade, i, ts, exit_px, "signal", equity, trades)
                        open_trade = None
                    elif open_trade.direction == -1 and sig.get("short_exit", pd.Series(False)).iloc[i]:
                        exit_px = price_close * (1 + cfg.slippage_pct)
                        equity = self._close_trade(open_trade, i, ts, exit_px, "signal", equity, trades)
                        open_trade = None

            # Open new trade (on close of bar after signal)
            if open_trade is None:
                entry_px = price_close * (1 + cfg.slippage_pct)
                size = (equity * cfg.position_size_pct) / entry_px
                commission = entry_px * size * cfg.commission_pct

                if sig["long_entry"].iloc[i]:
                    sl = entry_px * (1 - cfg.stop_loss_pct) if cfg.use_stop_loss else None
                    tp = entry_px * (1 + cfg.take_profit_pct) if cfg.use_take_profit else None
                    open_trade = Trade(i, ts, entry_px, 1, size, sl, tp, commission=commission)
                    equity -= commission

                elif cfg.allow_short and sig.get("short_entry", pd.Series(False)).iloc[i]:
                    entry_px = price_close * (1 - cfg.slippage_pct)
                    sl = entry_px * (1 + cfg.stop_loss_pct) if cfg.use_stop_loss else None
                    tp = entry_px * (1 - cfg.take_profit_pct) if cfg.use_take_profit else None
                    open_trade = Trade(i, ts, entry_px, -1, size, sl, tp, commission=commission)
                    equity -= commission

            # Mark-to-market equity
            mtm = equity
            if open_trade is not None:
                unrealized = (price_close - open_trade.entry_price) * open_trade.direction * open_trade.size
                mtm = equity + unrealized
            equity_curve.append({"time": ts, "equity": mtm})

        # Force-close any open trade at end
        if open_trade is not None:
            last = bars.iloc[-1]
            equity = self._close_trade(open_trade, len(bars) - 1, last.iloc[0], last["close"], "end_of_data", equity, trades)

        return BacktestResult(
            trades=trades,
            equity_curve=pd.DataFrame(equity_curve).set_index("time"),
            initial_capital=cfg.initial_capital,
            final_equity=equity,
        )

    def _close_trade(self, trade: Trade, bar: int, ts, exit_px: float, reason: str, equity: float, trades: list) -> float:
        commission = exit_px * trade.size * self.config.commission_pct
        gross_pnl = (exit_px - trade.entry_price) * trade.direction * trade.size
        net_pnl = gross_pnl - commission - trade.commission
        trade.exit_bar = bar
        trade.exit_time = ts
        trade.exit_price = exit_px
        trade.exit_reason = reason
        trade.pnl = net_pnl
        trade.pnl_pct = net_pnl / (trade.entry_price * trade.size) * 100
        trade.commission += commission
        trades.append(trade)
        return equity + net_pnl


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.DataFrame
    initial_capital: float
    final_equity: float

    def metrics(self) -> dict:
        if not self.trades:
            return {"error": "No trades executed"}

        pnls = [t.pnl for t in self.trades]
        pnl_pcts = [t.pnl_pct for t in self.trades]
        winners = [t for t in self.trades if t.pnl > 0]
        losers = [t for t in self.trades if t.pnl <= 0]

        equity = self.equity_curve["equity"]
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max * 100
        max_dd = drawdown.min()

        total_return = (self.final_equity - self.initial_capital) / self.initial_capital * 100
        avg_win = np.mean([t.pnl for t in winners]) if winners else 0
        avg_loss = np.mean([t.pnl for t in losers]) if losers else 0
        win_rate = len(winners) / len(self.trades) * 100
        profit_factor = abs(sum(t.pnl for t in winners) / sum(t.pnl for t in losers)) if losers else float("inf")

        # Sharpe: annualized using daily equity returns
        daily_returns = equity.pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(365 * 24)) if daily_returns.std() > 0 else 0

        return {
            "total_trades": len(self.trades),
            "win_rate_pct": round(win_rate, 1),
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "expectancy_usd": round(np.mean(pnls), 2),
            "final_equity_usd": round(self.final_equity, 2),
            "total_commission_usd": round(sum(t.commission for t in self.trades), 2),
            "winners": len(winners),
            "losers": len(losers),
        }

    def print_summary(self):
        m = self.metrics()
        print("\n" + "=" * 50)
        print("  BACKTEST RESULTS")
        print("=" * 50)
        for k, v in m.items():
            print(f"  {k:<28} {v}")
        print("=" * 50)

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "direction": "LONG" if t.direction == 1 else "SHORT",
                "entry_price": round(t.entry_price, 4),
                "exit_price": round(t.exit_price, 4) if t.exit_price else None,
                "exit_reason": t.exit_reason,
                "pnl_usd": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
                "commission_usd": round(t.commission, 2),
            })
        return pd.DataFrame(rows)

"""
Main backtest runner.
Usage:
    python run_backtest.py                    # runs on synthetic data
    python run_backtest.py --data path.csv    # runs on CSV file
    python run_backtest.py --live             # pulls from TradingView via MCP
    python run_backtest.py --optimize         # runs parameter grid search
"""
import sys
import argparse
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from data.loader import load_sample_data, load_from_csv, load_from_tv
from engine.backtest import BacktestEngine, BacktestConfig
from engine.optimizer import grid_search
from strategies.ema_crossover import EMACrossoverStrategy, EMACrossoverParams
from strategies.breakout import BreakoutStrategy, BreakoutParams
from results.plot import plot_equity_curve, plot_trades_on_price


def parse_args():
    p = argparse.ArgumentParser(description="TradingView Backtest Engine")
    p.add_argument("--strategy", choices=["ema", "breakout"], default="ema")
    p.add_argument("--data", type=str, help="Path to OHLCV CSV file")
    p.add_argument("--live", action="store_true", help="Pull data from TradingView via MCP")
    p.add_argument("--optimize", action="store_true", help="Run parameter grid search")
    p.add_argument("--plot", action="store_true", help="Show equity curve plot")
    p.add_argument("--capital", type=float, default=10_000, help="Starting capital in USD")
    p.add_argument("--position-size", type=float, default=0.10, help="Position size as fraction (0.10 = 10%%)")
    p.add_argument("--no-short", action="store_true", help="Disable short trades")
    p.add_argument("--save-results", type=str, help="Save results JSON to file")
    return p.parse_args()


def main():
    args = parse_args()

    # ─── Load Data ───────────────────────────────────────────────
    print("Loading data...")
    if args.live:
        print("  Fetching from TradingView via MCP...")
        df = load_from_tv(count=500)
    elif args.data:
        print(f"  Loading CSV: {args.data}")
        df = load_from_csv(args.data)
    else:
        print("  Using synthetic data (1000 bars). Use --live or --data for real data.")
        df = load_sample_data(n_bars=1000)

    print(f"  {len(df)} bars from {df.index[0]} to {df.index[-1]}")

    # ─── Config ──────────────────────────────────────────────────
    config = BacktestConfig(
        initial_capital=args.capital,
        position_size_pct=args.position_size,
        allow_short=not args.no_short,
    )

    # ─── Optimize or Single Run ───────────────────────────────────
    if args.optimize:
        print(f"\nRunning grid search for {args.strategy} strategy...")

        if args.strategy == "ema":
            param_grid = {
                "fast": [5, 9, 13, 21],
                "slow": [21, 34, 50, 100],
                "trend_filter": [0, 100, 200],
                "use_rsi_filter": [False, True],
            }
            results_df = grid_search(df, EMACrossoverStrategy, EMACrossoverParams, param_grid, config)
        else:
            param_grid = {
                "channel_period": [10, 20, 30, 50],
                "exit_period": [5, 10, 20],
                "trend_filter": [0, 50, 100],
                "volume_filter": [False, True],
            }
            results_df = grid_search(df, BreakoutStrategy, BreakoutParams, param_grid, config)

        if results_df.empty:
            print("No valid parameter combinations found (too few trades).")
            return

        print(f"\nTop 10 parameter sets (by Sharpe ratio):")
        display_cols = ["sharpe_ratio", "total_return_pct", "max_drawdown_pct",
                        "win_rate_pct", "profit_factor", "total_trades"] + list(param_grid.keys())
        display_cols = [c for c in display_cols if c in results_df.columns]
        print(results_df[display_cols].head(10).to_string(index=False))

        best = results_df.iloc[0]
        print(f"\n Best params: {dict(best[list(param_grid.keys())])}")

        if args.save_results:
            results_df.to_json(args.save_results, orient="records", indent=2)
            print(f"Saved to {args.save_results}")

    else:
        # Single strategy run
        print(f"\nRunning {args.strategy} strategy...")

        if args.strategy == "ema":
            strategy = EMACrossoverStrategy()
        else:
            strategy = BreakoutStrategy()

        signals = strategy.generate_signals(df)
        engine = BacktestEngine(config)
        result = engine.run(df, signals)
        result.print_summary()

        trades_df = result.trades_df()
        if not trades_df.empty:
            print(f"\nLast 5 trades:")
            print(trades_df.tail().to_string(index=False))

        if args.save_results:
            output = {
                "metrics": result.metrics(),
                "trades": trades_df.to_dict(orient="records"),
            }
            Path(args.save_results).write_text(json.dumps(output, indent=2, default=str))
            print(f"\nSaved results to {args.save_results}")

        if args.plot:
            plot_equity_curve(result, title=f"{strategy.name} — Equity Curve")
            plot_trades_on_price(df, result, title=f"{strategy.name} — Trades")


if __name__ == "__main__":
    main()

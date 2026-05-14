"""
Parameter optimizer — grid search over strategy parameters.
Returns a ranked results DataFrame sorted by Sharpe ratio.
"""
import pandas as pd
import itertools
from dataclasses import asdict, fields
from typing import Type

from engine.backtest import BacktestEngine, BacktestConfig


def grid_search(
    df: pd.DataFrame,
    strategy_class,
    param_class,
    param_grid: dict,
    config: BacktestConfig | None = None,
    sort_by: str = "sharpe_ratio",
    min_trades: int = 10,
) -> pd.DataFrame:
    """
    Run grid search over param_grid.
    param_grid: {param_name: [val1, val2, ...]}
    Returns DataFrame of results sorted by sort_by descending.

    Example:
        grid_search(df, EMACrossoverStrategy, EMACrossoverParams, {
            "fast": [5, 9, 13],
            "slow": [21, 50],
        })
    """
    engine = BacktestEngine(config)
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    # Get default params
    default_fields = {f.name: f.default for f in fields(param_class)}

    results = []
    total = len(combinations)
    for idx, combo in enumerate(combinations):
        params_dict = {**default_fields, **dict(zip(keys, combo))}
        try:
            params = param_class(**params_dict)
            strategy = strategy_class(params)
            signals = strategy.generate_signals(df)
            result = engine.run(df, signals)
            m = result.metrics()
            if isinstance(m.get("error"), str):
                continue
            if m["total_trades"] < min_trades:
                continue
            row = {**params_dict, **m}
            results.append(row)
        except Exception as e:
            pass

        if (idx + 1) % 10 == 0 or idx == total - 1:
            print(f"  [{idx+1}/{total}] combinations tested...", end="\r")

    print()
    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(sort_by, ascending=False).reset_index(drop=True)
    return results_df

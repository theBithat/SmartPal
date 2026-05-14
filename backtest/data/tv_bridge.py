"""
TradingView MCP Bridge
Calls the tv CLI to pull live data from TradingView Desktop via CDP.
TradingView must be running with --remote-debugging-port=9222.
"""
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

MCP_SERVER_PATH = Path(__file__).parent.parent.parent / "mcp-server"
TV_CLI = str(MCP_SERVER_PATH / "src" / "cli" / "index.js")


def _tv(*args) -> dict:
    """Run: node src/cli/index.js <args...> and return parsed JSON."""
    cmd = ["node", TV_CLI, *[str(a) for a in args]]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=MCP_SERVER_PATH, timeout=15)
    raw = result.stdout.strip()
    if not raw:
        err = result.stderr.strip() or "Empty response from MCP CLI"
        raise RuntimeError(err)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Bad JSON from MCP CLI: {raw[:300]}")
    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(data.get("error", "MCP returned success=false"))
    return data


def check_connection() -> bool:
    """Returns True if TradingView CDP is reachable."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
        return True
    except Exception:
        return False


def fetch_ohlcv(count: int = 500) -> list[dict]:
    """
    Fetch OHLCV bars from the current TradingView chart.
    Returns list of {time (unix), open, high, low, close, volume, datetime (UTC str)}.
    """
    count = min(count, 500)
    data = _tv("ohlcv", "--count", count)
    bars = data.get("bars", [])
    for b in bars:
        t = b.get("time")
        if isinstance(t, (int, float)):
            b["datetime"] = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return bars


def fetch_quote(symbol: str = "") -> dict:
    """Fetch real-time price snapshot for the current (or given) symbol."""
    if symbol:
        return _tv("quote", symbol)
    return _tv("quote")


def fetch_study_values() -> list[dict]:
    """Return current indicator values for all visible studies."""
    data = _tv("values")
    return data.get("studies", [])


def fetch_chart_state() -> dict:
    """Return current symbol, timeframe, and indicator list."""
    return _tv("state")


def fetch_strategy_results() -> dict:
    """Return metrics from TradingView Strategy Tester (if a Pine strategy is active)."""
    return _tv("data", "strategy")


def fetch_trades(max_trades: int = 50) -> list[dict]:
    """Return trade list from TradingView Strategy Tester."""
    data = _tv("data", "trades", "--max", max_trades)
    return data.get("trades", [])


if __name__ == "__main__":
    print("Checking CDP connection...")
    if not check_connection():
        print("TradingView is NOT running with CDP.\n")
        print("Fix: run this in your terminal:")
        print("  bash /Users/amirhosseinghaderi/Tradingview-trade/mcp-server/scripts/launch_tv_debug_mac.sh")
        raise SystemExit(1)

    print("CDP connected. Fetching 10 bars...")
    bars = fetch_ohlcv(10)
    print(f"Got {len(bars)} bars.")
    if bars:
        b = bars[-1]
        print(f"  Last bar: {b.get('datetime')}  O={b['open']}  H={b['high']}  L={b['low']}  C={b['close']}  V={b['volume']}")

    print("\nFetching quote...")
    q = fetch_quote()
    print(f"  Symbol: {q.get('symbol')}  Last: {q.get('last')}")

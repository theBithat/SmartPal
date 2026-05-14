"""
Test TradingView MCP connection.
Run this after launching TradingView with CDP to verify everything works.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.tv_bridge import check_connection, fetch_ohlcv, fetch_quote, fetch_chart_state

RESET = "\033[0m"
GREEN = "\033[92m"
RED   = "\033[91m"
BOLD  = "\033[1m"

def ok(msg): print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")

print(f"\n{BOLD}TradingView MCP Connection Test{RESET}")
print("=" * 40)

# 1. CDP reachable?
print("\n[1] CDP port 9222...")
if check_connection():
    ok("TradingView CDP is reachable")
else:
    fail("Cannot reach port 9222")
    print("""
  TradingView is not running with CDP enabled.

  To fix, run:
    bash /Users/amirhosseinghaderi/Tradingview-trade/mcp-server/scripts/launch_tv_debug_mac.sh

  Or manually:
    /Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222
""")
    sys.exit(1)

# 2. Chart state
print("\n[2] Chart state (symbol + timeframe)...")
try:
    state = fetch_chart_state()
    symbol = state.get("symbol", "unknown")
    tf = state.get("timeframe", "unknown")
    ok(f"Symbol: {symbol}  Timeframe: {tf}")
    indicators = state.get("indicators", [])
    if indicators:
        ok(f"Active indicators: {', '.join(i.get('name','?') for i in indicators[:5])}")
except Exception as e:
    fail(f"chart state failed: {e}")

# 3. OHLCV
print("\n[3] OHLCV data (last 5 bars)...")
try:
    bars = fetch_ohlcv(5)
    if bars:
        ok(f"Got {len(bars)} bars")
        b = bars[-1]
        ok(f"Last bar: {b.get('datetime')}  C={b['close']:.2f}  V={b['volume']:.0f}")
    else:
        fail("No bars returned (chart may still be loading)")
except Exception as e:
    fail(f"OHLCV failed: {e}")

# 4. Quote
print("\n[4] Real-time quote...")
try:
    q = fetch_quote()
    ok(f"Symbol: {q.get('symbol')}  Last: {q.get('last'):.2f}  Vol: {q.get('volume', 'n/a')}")
except Exception as e:
    fail(f"Quote failed: {e}")

print("\n" + "=" * 40)
print(f"{GREEN}{BOLD}All checks passed — ready to backtest with live data!{RESET}")
print("\nNext step:")
print("  cd backtest")
print("  .venv/bin/python run_backtest.py --live --strategy ema --optimize")

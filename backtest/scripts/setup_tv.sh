#!/usr/bin/env bash
# Launches TradingView Desktop with Chrome DevTools Protocol enabled.
# Run this BEFORE using --live mode in the backtest engine.

echo "Launching TradingView with CDP on port 9222..."

# macOS path (adjust if different)
TV_APP="/Applications/TradingView.app/Contents/MacOS/TradingView"

if [ ! -f "$TV_APP" ]; then
  echo "ERROR: TradingView not found at $TV_APP"
  echo "Install from https://www.tradingview.com/desktop/"
  exit 1
fi

"$TV_APP" --remote-debugging-port=9222 &

echo "TradingView launched. Wait for it to fully load, then run:"
echo "  cd $(dirname "$0")/.."
echo "  .venv/bin/python run_backtest.py --live"

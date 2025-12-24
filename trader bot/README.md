# Crypto Trading Bot with Grok AI & SmartPal Arena

A Python-based cryptocurrency trading bot that uses Grok AI to analyze crypto pairs on multiple timeframes (15 minutes and 4 hours) and performs paper trading to track signal performance.

**🆕 SmartPal Arena**: Multi-agent AI trading system with God-tier orchestration and intelligent regime-based strategy management. [**Quick Start Guide →**](QUICK_START_ARENA.md)

## Features

- **Multi-Timeframe Analysis**: Analyzes crypto pairs on 15-minute and 4-hour charts
- **Grok AI Integration**: Uses Claude 3.5 Sonnet via OpenRouter for intelligent market analysis and signal generation
- **Technical Indicators**: RSI, MACD, Bollinger Bands, EMA, SMA, ATR, and volume analysis
- **Signal Generation**: Generates BUY, SELL, or HOLD signals with confidence scores
- **Paper Trading**: Simulates trades to track signal performance without risking real capital
- **Hedging Support**: Allows simultaneous long and short positions on the same pair
- **Per-Pair Capital Allocation**: $1000 USDT allocated to each trading pair
- **Database Storage**: PostgreSQL database for persistent storage of signals, positions, and balances
- **Web Interface**: Live dashboard for monitoring signals, positions, and P&L (http://localhost:8080)
- **SmartPal Arena**: Multi-agent system with God orchestration, regime-based strategies, and AI-powered strategists
- **Risk Management**: Built-in position sizing (2% risk per trade) and stop-loss management
- **Performance Tracking**: Comprehensive statistics including win rate, profit factor, and P&L

## Project Structure

```
trader bot/
├── .github/
│   └── copilot-instructions.md    # Development guidelines
├── config/
│   └── config.py                   # Configuration management
├── src/
│   ├── data_fetcher.py            # Fetches market data from exchanges
│   ├── technical_analysis.py      # Technical indicator calculations
│   ├── grok_analyzer.py           # Grok AI integration
│   ├── signal_generator.py        # Signal generation and storage
│   ├── paper_trader.py            # Paper trading simulation
│   └── trading_bot.py             # Main bot orchestrator
├── data/                          # Trading data and signals (auto-created)
├── logs/                          # Application logs (auto-created)
├── main.py                        # Application entry point
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variables template
└── README.md                      # This file
```

## Prerequisites

- Python 3.8 or higher
- Grok AI API key (from X.AI)
- Exchange API credentials (optional, for live data)

## Installation

1. **Clone or navigate to the project directory**:
   ```bash
   cd "trader bot"
   ```

2. **Create a virtual environment** (already done):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies** (already done):
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your API keys:
   ```env
   # Required: OpenRouter API Key (for Claude 3.5 Sonnet)
   GROK_API_KEY=your_openrouter_api_key_here
   GROK_API_BASE=https://openrouter.ai/api/v1
   GROK_MODEL=anthropic/claude-3.5-sonnet
   
   # Optional: Exchange API (leave empty to use public data)
   EXCHANGE_API_KEY=
   EXCHANGE_API_SECRET=
   
   # Trading Configuration
   TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT
   CAPITAL_PER_PAIR=1000
   RISK_PER_TRADE=0.02
   ```

## Getting Your OpenRouter API Key

1. Visit [OpenRouter.ai](https://openrouter.ai)
2. Sign up for an account
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key and paste it in your `.env` file

**Note**: The bot uses Claude 3.5 Sonnet through OpenRouter since Grok is not directly available via API.

## Usage

### Running the Bot

Start the bot with:
```bash
python main.py
```

Or using the full path to the virtual environment Python:
```bash
".venv/bin/python" main.py
```

The bot will:
1. Run an initial analysis of all configured trading pairs
2. Generate signals using Grok AI
3. Execute paper trades based on signals
4. Schedule analyses every 15 minutes
5. Display statistics and results in the console
6. Start a web interface at http://localhost:8080 for live monitoring

## Running as a Background Service

The bot can run as a background service with two options:

### Option 1: Simple Background Runner (Recommended)

```bash
# Start the bot
./run_background.sh start

# Check status
./run_background.sh status

# Stop the bot
./run_background.sh stop

# View logs
./run_background.sh logs
```

### Option 2: macOS Launchd Service

```bash
# Start the service
./service_manager.sh start

# Check status
./service_manager.sh status

# Stop the service
./service_manager.sh stop

# View logs
./service_manager.sh logs
```

### Web Interface

The bot includes a live web dashboard accessible at `http://localhost:5000` that shows:

- **Real-time Portfolio Value**: Total balance and unrealized P&L
- **Open Positions**: Current positions with live P&L calculations and market prices
- **Recent Signals**: Latest trading signals with confidence scores and price levels
- **Performance Statistics**: Win rate, profit factor, and trade counts
- **Auto-updates every 30 seconds** with live market data

### Features:
- ✅ Live P&L calculations for open positions
- ✅ Current market prices for all positions
- ✅ Signal confidence and entry/exit levels
- ✅ Per-pair capital allocation tracking
- ✅ Real-time updates without page refresh
### Web Interface

Access the live dashboard at: **http://localhost:8080**

The web interface shows:
- **Real-time Portfolio Value**: Total balance and unrealized P&L
- **Open Positions**: Current positions with live P&L calculations and market prices
- **Recent Signals**: Latest trading signals with confidence scores and price levels
- **Performance Statistics**: Win rate, profit factor, and trade counts
- **Auto-updates every 30 seconds** with live market data

### Features:
- ✅ Live P&L calculations for open positions
- ✅ Current market prices for all positions
- ✅ Signal confidence and entry/exit levels
- ✅ Per-pair capital allocation tracking
- ✅ Real-time updates without page refresh

### Configuration Options

Edit `.env` to customize:

- **Trading Pairs**: Comma-separated list of crypto pairs (e.g., `BTC/USDT,ETH/USDT,SOL/USDT`)
- **Capital Per Pair**: USDT allocated to each pair (default: $1000)
- **Risk Per Trade**: Percentage of capital to risk per trade (default: 2% = 0.02)
- **Log Level**: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

### Understanding the Output

The bot displays:

1. **Signal Information**:
   - Current price
   - Trading signal (BUY/SELL/HOLD)
   - Confidence score
   - Entry price, stop loss, and take profit levels
   - Reasoning from Grok AI

2. **Trading Statistics**:
   - Portfolio value and total P&L
   - Number of trades and win rate
   - Average win/loss amounts
   - Profit factor
   - Open positions

### Data Storage

- **Database**: All data stored in SQLite database (`data/trading.db`)
- **Signals Table**: Trading signals with confidence and price levels
- **Positions Table**: Open and closed positions with P&L
- **Balances Table**: Account balances for each trading pair
- **Logs**: Daily log files in `logs/` directory

## How It Works

1. **Data Fetching**: Retrieves OHLCV data from Binance (or configured exchange)
2. **Technical Analysis**: Calculates indicators (RSI, MACD, Bollinger Bands, etc.)
3. **Market Summary**: Creates a comprehensive market overview for each timeframe
4. **Grok AI Analysis**: Sends market data to Grok AI for intelligent analysis
5. **Signal Generation**: Creates trading signals with entry/exit levels
6. **Paper Trading**: Simulates trades and tracks P&L
7. **Position Management**: Automatically closes trades at stop loss or take profit

## Risk Management

The bot implements several risk management features:

- **Position Sizing**: Calculates position size based on risk per trade and stop loss
- **Capital Limits**: Never risks more than 95% of available capital
- **Stop Loss**: Mandatory stop loss for every trade
- **Take Profit**: Optional take profit targets
- **Timeframe Confirmation**: Analyzes both 15m and 4h timeframes

## Development Guidelines

- Use Python 3.8+ for all development
- Follow PEP 8 style guidelines
- Use type hints for better code clarity
- Keep API keys in environment variables
- Test with paper trading before considering live trading

## Important Notes

⚠️ **This is a paper trading bot only**. It does not execute real trades. It's designed for:
- Testing trading strategies
- Learning about algorithmic trading
- Tracking signal performance
- Gaining experience with AI-powered trading analysis

⚠️ **Never share your API keys**. Keep them secure in the `.env` file.

⚠️ **Past performance does not guarantee future results**. Use this bot for educational purposes.

## Troubleshooting

### "GROK_API_KEY is required" Error
Make sure you've created a `.env` file and added your Grok API key.

### Rate Limit Errors
The bot includes rate limiting, but if you see errors:
- Reduce the number of trading pairs
- Increase the delay between API calls in the code

### No Data Available
- Check your internet connection
- Verify the exchange is accessible
- Try different trading pairs

### Import Errors
Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

## Future Enhancements

Potential improvements:
- Web dashboard for monitoring
- More technical indicators
- Multiple exchange support
- Webhook notifications
- Backtesting capabilities
- Strategy optimization
- Real trading integration (use with extreme caution)

## License

This project is for educational purposes. Use at your own risk.

## Support

For issues or questions:
1. Check the logs in the `logs/` directory
2. Review the configuration in `.env`
3. Ensure all dependencies are installed
4. Verify your Grok API key is valid

## Credits

Built with:
- [CCXT](https://github.com/ccxt/ccxt) - Cryptocurrency exchange trading library
- [Grok AI](https://x.ai) - AI-powered market analysis
- [TA-Lib (Python)](https://github.com/bukosabino/ta) - Technical analysis library
- [Pandas](https://pandas.pydata.org/) - Data manipulation

---

**Disclaimer**: This bot is for educational and research purposes only. Cryptocurrency trading carries significant risk. Never trade with money you cannot afford to lose. Always do your own research and consider consulting with a financial advisor.

# SmartPal Arena - Multi-Agent AI Trading Platform

Advanced cryptocurrency trading platform with multi-agent AI orchestration, God-tier management system, and intelligent regime-based strategy execution.

## System Architecture

### Arena Platform (Primary System)
1. **User Interface** (`templates_arena/`) - Modern Arena UI with onboarding flow
   - **Login/Registration** → JWT authentication with refresh tokens
   - **Onboarding Wizard** → God creation with presets (Conservative → Aggressive)
   - **God Control Dashboard** → Real-time position monitoring and regime management
   - **Landing Page** → Public-facing Arena introduction

2. **Multi-Agent System**:
   - **God Manager** (`src/god_manager.py`) - Orchestrates multiple trading gods
   - **Regime Detector** (`src/regime_detector.py`) - Market phase detection (Trending/Ranging/Volatile)
   - **Strategist Runner** (`src/strategist_runner.py`) - Executes AI strategist trading logic
   - **God Spirit** (`src/god_spirit.py`) - Core god intelligence and decision-making

3. **Authentication & API**:
   - **Auth Manager** (`src/auth.py`) - JWT tokens (15min access, 7-day refresh)
   - **Arena API** (`src/arena_api.py`) - RESTful endpoints for Arena operations
   - **Arena Routes** (`src/arena_routes.py`) - Page routes with `/arena` prefix

4. **Legacy Trading Bot** (Still functional):
   - **Trading Engine** (`src/trading_bot.py`) - Original single-strategy bot
   - **Web Interface** (`web_interface.py`) - Flask dashboard at `/trading-dashboard`
   - Root `/` redirects to Arena login page

### Key Architectural Patterns
- **Multi-God Orchestration**: Each user can create multiple gods with different risk profiles
- **Regime-Based Trading**: Automatically switches strategies based on detected market conditions
- **AI Strategist Hierarchy**: Gods → Regimes → Strategists (3-tier decision structure)
- **Real-Time Monitoring**: WebSocket-ready god dashboard with live P&L tracking
- **Database-Driven Everything**: All presets, strategies, and decisions stored in PostgreSQL

## Database Schema (PostgreSQL)

### Arena Tables (New)
1. **users** - User accounts with Arena access
   - Fields: username, email, password_hash, onboarding_completed, global_risk_settings
   - JWT authentication via `src/auth.py`

2. **gods** - User-created trading gods
   - Fields: user_id, name, preset_id, total_capital, risk_tolerance, trading_pairs, status
   - Each god can have multiple regimes and strategists

3. **regimes** - Market condition strategies
   - Fields: god_id, preset_id, name, market_condition, confidence_threshold, is_active
   - Types: TRENDING, RANGING, VOLATILE

4. **strategists** - Individual trading agents
   - Fields: regime_id, preset_id, name, strategy_type, allocated_capital, winning_trades, losing_trades
   - Execute actual trades based on regime conditions

5. **preset_gods** - God templates (5 presets)
   - Conservative Tactician, Balanced Opportunist, Aggressive Hunter, Momentum Chaser, Chaos Trader

6. **preset_regimes** - Regime templates (6 presets)
   - Bull Trend, Bear Trend, Sideways Range, High Volatility, etc.

7. **preset_strategists** - Strategist templates (8 presets)
   - Momentum Scout, Mean Reversion Specialist, Breakout Hunter, etc.

### Legacy Tables (Still in use)
1. **prompts** - Trading strategies with AI prompts
   - Contains 10 strategies (conservative → very aggressive)
   - Fields: name, system_message, analysis_prompt, risk_level, is_active, analysis_cycle_minutes
   - Only ONE active prompt at a time determines trading behavior

2. **positions** - Active and historical positions
   - Includes leverage, margin_used, liquidation_price
   - Fee tracking: entry_fee, exit_fee, funding_fees, total_fees
   - Trailing stop: last_trailing_update timestamp

3. **signals** - AI-generated trading signals
   - Contains chatgpt_validation JSON field (CONFIRM/REJECT decisions)
   - Linked to positions via signal_id

4. **position_decisions** - AI review history
   - Tracks REVIEW_KEEP, REVIEW_ADJUST, REVIEW_CLOSE decisions
   - Used for AI reflection on past actions

5. **pending_orders** - Limit orders awaiting fill
   - Converted to positions when price matches entry_price

6. **account_balances** - Portfolio tracking (USDT balance)

7. **bot_settings** - Key-value configuration store
   - Overrides .env variables (e.g., chatgpt_validation_enabled)

## Configuration Management

### Environment Variable Hierarchy
1. **Database Settings** (`bot_settings` table) - Highest priority
2. **Environment Variables** (`.env` file) - Fallback
3. **Config Defaults** (`config/config.py`) - Last resort

### Critical Config Patterns
```python
# Example: Checking database setting first
db_setting = db.get_setting('chatgpt_validation_enabled', None)
if db_setting is not None:
    enabled = db_setting.lower() == 'true'
else:
    enabled = Config.CHATGPT_VALIDATION_ENABLED
```

### Key Environment Variables
- `XAI_API_KEY` - Primary AI (Grok)
- `CHATGPT_API_KEY` - Validation AI
- `CHATGPT_VALIDATION_ENABLED=true` - Toggle dual-AI mode
- `EXCHANGE_BACKEND=pyxt` - 'pyxt' or 'ccxt'
- `IS_PAPER_TRADING=true` - Paper vs live trading
- `LEVERAGE=50` - Position leverage multiplier
- `TRADING_MODE=futures` - 'spot' or 'futures'
- `DB_HOST=postgres` - Uses Docker service name in containers

## Trading Logic & Workflows

### Analysis Cycle Flow
1. `main.py` schedules analysis every N minutes (from active strategy)
2. `TradingBot.run_analysis_cycle()`:
   - Fetches OHLCV data for all pairs (15m + 4h timeframes)
   - Calculates technical indicators (RSI, MACD, EMA, BB)
   - XAI analyzes → generates signal
   - **ChatGPT validation** → CONFIRM or REJECT
   - Confidence threshold check (strategy-dependent)
   - `LiveTrader.execute_signal()` → creates position/order
3. `OrderManager` monitors (every 1s in background thread):
   - Checks pending orders → fills if price matches
   - Monitors positions → closes on SL/TP
   - Updates trailing stops (every 5 min)
4. `PositionReviewer.review_all_positions()` (if enabled):
   - AI reviews each position → KEEP/ADJUST/CLOSE
   - Adjusts stops or closes positions

### Trailing Stop Logic
```python
# Activation: $1,000 profit minimum
# Protection: Locks in 50% of profit
# Distance: $500 buffer from current price
if profit >= 1000:
    if side == 'long':
        stop = max(entry + profit/2, current - 500)
    else:
        stop = min(entry - profit/2, current + 500)
```

### Multi-Level TP/SL (4 Levels) 🆕
```python
# Configuration (.env)
ENABLE_MULTI_LEVEL_TPSL=true
TP_LEVEL_DISTANCES=1.0,2.0,3.0,5.0  # % from entry
SL_LEVEL_DISTANCES=0.5,1.0,1.5,2.0  # % from entry
TP_CLOSE_PERCENTAGES=25,25,25,25    # % position to close at each level
SL_CLOSE_PERCENTAGES=25,25,25,25

# Example for LONG BTC @ $50,000:
# TP1: $50,500 (1%) → Close 25%
# TP2: $51,000 (2%) → Close 25%
# TP3: $51,500 (3%) → Close 25%
# TP4: $52,500 (5%) → Close 25%

# SL1: $49,750 (0.5%) → Close 25%
# SL2: $49,500 (1.0%) → Close 25%
# SL3: $49,250 (1.5%) → Close 25%
# SL4: $49,000 (2.0%) → Close 25%

# Database tracks:
# - tp_levels, sl_levels (JSON arrays of prices)
# - current_tp_level, current_sl_level (0-4)
# - remaining_quantity (updated after partial closes)
```

### Position Sizing with Leverage
```python
capital_per_pair = 500  # $500 allocated
leverage = 50
effective_position = 500 * 50 = $25,000
quantity = effective_position / current_price
```

## Development Workflows

### Local Development
```bash
# Activate environment
source .venv/bin/activate

# Run locally (port 8080)
python main.py

# View dashboard
open http://localhost:8080
```

### Docker Deployment
```bash
# Full restart (required for .env changes)
docker compose down
docker compose up -d --build

# Check logs
docker logs trading-bot-app --tail=100 -f

# Verify configuration loaded
docker exec trading-bot-app python -c "from config.config import Config; print(f'Leverage: {Config.LEVERAGE}x, Backend: {Config.EXCHANGE_BACKEND}')"
```

### Remote Deployment (66.94.110.211)
```bash
# Deploy single file
sshpass -p 'amir13579' scp src/grok_analyzer.py root@66.94.110.211:/root/trader-bot/src/

# Full restart
sshpass -p 'amir13579' ssh root@66.94.110.211 'cd /root/trader-bot && docker compose down && docker compose up -d'

# Quick CSS update (no rebuild)
./deploy-css-quick.sh

# Access Arena (HTTPS with Nginx)
open https://66.94.110.211/arena/login

# Access old trading dashboard
open https://66.94.110.211/trading-dashboard
```

### Arena Production URLs
- **Main Entry**: https://66.94.110.211/ → Redirects to login
- **Login**: https://66.94.110.211/arena/login
- **Onboarding**: https://66.94.110.211/arena/onboarding (new users)
- **God Dashboard**: https://66.94.110.211/arena/god-control (existing users)
- **Legacy Bot**: https://66.94.110.211/trading-dashboard
- **API Base**: https://66.94.110.211/api/arena/

### Database Migrations
```bash
# Add new table/column
python migrate_add_<feature>.py

# Migrate to PostgreSQL (from SQLite)
python migrate_to_postgres.py

# Migrate to pyxt backend
python migrate_to_pyxt.py

# Add multi-level TP/SL support
python migrate_add_multi_level_tpsl.py
```

## Code Standards & Patterns

### Database Operations (Critical)
```python
# Always use context manager for sessions
from src.database_postgres import TradingDatabase

db = TradingDatabase()

# Single query
position = db.get_position(position_id)

# Multiple operations in transaction
with db._session_scope() as session:
    position = session.query(Position).filter_by(id=position_id).first()
    position.status = 'closed'
    session.commit()
```

### AI Analyzer Integration
```python
# XAI generates signal
analysis = self.grok_analyzer.analyze_market(symbol, timeframe_data)

# ChatGPT validates (if enabled)
validation = self.chatgpt_validator.validate_signal(signal, market_data, analysis)
if validation['decision'] == 'REJECT':
    logger.warning(f"⛔ ChatGPT REJECTED {symbol} signal")
    return None  # Skip trade
```

### Error Handling Pattern
```python
try:
    result = risky_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}", exc_info=True)
    return None  # Graceful degradation
```

### Never Hardcode Values
```python
# ❌ Bad
leverage = 50

# ✅ Good
leverage = Config.LEVERAGE
```

## Web Dashboard Features

### API Endpoints
- `GET /api/data` - Full dashboard state (positions, signals, P&L)
- `GET /api/prices` - Real-time market prices
- `GET /api/status` - XAI API health (updates every 5s)
- `POST /api/close-position` - Manual closure (body: `{"position_id": "uuid"}`)
- `POST /api/save-ai-settings` - Update AI config
- `POST /api/restart-bot` - Restart trading engine

### Manual Position Closure Flow
1. User clicks "✕ Close" button
2. JavaScript sends POST to `/api/close-position`
3. Backend: `LiveTrader.close_position()` → calculates P&L at current price
4. Database: Updates position with exit_price, exit_reason='manual', pnl
5. Response: `{"success": true, "pnl": -123.45}`
6. Frontend: Shows success message, auto-refreshes

## Common Issues & Solutions

### Port Conflicts
- **Issue**: Port 8080 used by VPN
- **Solution**: Use 8090 (set `WEB_PORT=8090` in .env)

### Environment Variables Not Loading
- **Issue**: Changes to .env not reflected
- **Solution**: Must use `docker compose down && up -d` (restart insufficient)

### DNS Resolution Failure
- **Issue**: Cannot connect to postgres container
- **Solution**: Use service name 'postgres' not 'localhost' in containers

### API 401 Errors
- **Issue**: XAI API unauthorized
- **Check**: `echo $XAI_API_KEY` in container, verify key on api.x.ai dashboard

### Database Connection Pooling
- **Pool Size**: 10 connections, max overflow 20
- **Error**: "Too many connections" → Check for leaked sessions (always use context manager)

## Testing & Validation

### Pre-Deployment Checklist
1. Verify `.env` has all required keys (XAI_API_KEY, CHATGPT_API_KEY, DB credentials)
2. Test database connection: `python -c "from src.database_postgres import TradingDatabase; db = TradingDatabase(); print('OK')"`
3. Check API keys work: `curl -H "Authorization: Bearer $XAI_API_KEY" https://api.x.ai/v1/models`
4. Validate leverage calculation: `docker exec trading-bot-app python -c "from config.config import Config; print(f'500 * {Config.LEVERAGE} = {500 * Config.LEVERAGE}')"`
5. Test web dashboard: `curl http://localhost:8080/api/status`

### Key Logs to Monitor
```
✅ HTTP Request: POST https://api.x.ai/v1/chat/completions "HTTP/1.1 200 OK"
✅ 💬 ChatGPT CONFIRM signal for BTC/USDT (confidence: 85%)
✅ Position size for BTC/USDT: 0.012345
⚠️  ⛔ ChatGPT REJECTED ETH/USDT signal - Skipping trade
❌ HTTP Request: POST https://api.x.ai/v1/chat/completions "HTTP/1.1 401 Unauthorized"
```

## Security & Safety

### Paper Trading Mode
- **Default**: `IS_PAPER_TRADING=true` (no real money)
- **Real Trading**: Requires explicit user confirmation AND setting to `false`
- **Validation**: Always check mode before executing trades

### API Cost Optimization
- XAI model: `grok-4-1-fast-reasoning` (cost-effective)
- ChatGPT: gpt-5.2 with `temperature=0.7`, `max_tokens=1000`
- Monitor costs: XAI dashboard (api.x.ai), OpenAI dashboard (platform.openai.com)

### Never Commit
- `.env` file (contains API keys)
- `data/` directory (trading database)
- `logs/` directory (may contain sensitive info)

## Strategy Portfolio System

### Active Strategy Selection
```python
# Get active strategy (only one at a time)
active_prompt = db.get_active_prompt()
analysis_interval = active_prompt['analysis_cycle_minutes']  # 12-30 minutes
strategy_name = active_prompt['name']  # "Quant Execution Trader"
```

### Risk Profiles (10 Strategies)
1. **Quant Execution Trader** (ACTIVE) - 30min cycle, conservative
2. **Range Mean-Reversion** - 20min, medium risk
3. **Market Phase Trader** - 25min, medium risk
4. **Momentum Breakout** - 15min, medium-high risk
5. **Early Reversal Hunter** - 12min, high risk
6. **Range Scalper** - 12min, high frequency
7-10. **Very Aggressive** - Parabolic Trend, Grid Trading, etc.

See `STRATEGY_PORTFOLIO.md` for full details.

## Exchange Integration

### XT.COM Backend Switching
```python
# .env configuration
EXCHANGE_BACKEND=pyxt  # Official XT.COM library (recommended)
# OR
EXCHANGE_BACKEND=ccxt  # Legacy support

# Code usage (abstracted)
from src.exchange_connector import ExchangeConnector
exchange = ExchangeConnector(backend=Config.EXCHANGE_BACKEND)
price = exchange.get_ticker(symbol)  # Works with both backends
```

### Fee Simulation (Paper Trading)
- **Maker Fee**: 0.06% (Config.MAKER_FEE_RATE)
- **Taker Fee**: 0.08% (Config.TAKER_FEE_RATE)
- **Funding Fee**: 0.01% every 8 hours (futures only)
- Fees stored per position: entry_fee, exit_fee, funding_fees, total_fees

## File Organization Conventions

### Migration Scripts
- Pattern: `migrate_add_<feature>.py`
- Location: Project root
- Purpose: Database schema changes
- Example: `migrate_add_chatgpt_validation.py` adds chatgpt_validation column

### Documentation Files
- `*.md` files in root: Feature-specific docs
- `CHATGPT_VALIDATION.md` - Dual-AI validation details
- `STRATEGY_PORTFOLIO.md` - All 10 trading strategies
- `PYXT_INTEGRATION_GUIDE.md` - Exchange backend migration

### Deploy Scripts
- `deploy-docker.sh` - Remote Docker deployment
- `deploy-remote.sh` - Direct file copy + restart
- `deploy-tabler.sh` - Alternative UI deployment (experimental)

## When Modifying This Codebase

### Adding New AI Features
1. Update database schema (migration script)
2. Add AI call in `grok_analyzer.py` or `chatgpt_validator.py`
3. Update API status tracking (`api_status_tracker.update_status()`)
4. Log to AI logs for dashboard visibility
5. Update this instructions file

### Adding New Trading Strategy
1. Insert into `prompts` table via database
2. Set `is_active=true`, others to `false`
3. Define `analysis_cycle_minutes` (12-30 typical)
4. Restart bot to load new strategy
5. Document in `STRATEGY_PORTFOLIO.md`

### Modifying Position Logic
1. Update `order_manager.py` for monitoring
2. Update `position_reviewer.py` for AI reviews
3. Test trailing stop calculations thoroughly
4. Verify P&L calculations account for leverage
5. Check fee calculations remain accurate



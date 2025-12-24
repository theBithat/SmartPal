"""
PostgreSQL Database Manager for Trading Bot
Replaces SQLite with scalable PostgreSQL backend
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Text, Boolean, DateTime, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

Base = declarative_base()


class Signal(Base):
    """Signals table model"""
    __tablename__ = 'signals'
    
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    symbol = Column(String(50), nullable=False, index=True)
    signal = Column(String(10), nullable=False)
    confidence = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    reasoning = Column(Text)
    ai_provider = Column(String(50))
    chatgpt_validation = Column(JSON)  # ChatGPT validation result


class Position(Base):
    """Positions table model"""
    __tablename__ = 'positions'
    
    id = Column(String, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    status = Column(String(20), nullable=False, index=True)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime)
    exit_price = Column(Float)
    exit_reason = Column(String(50))
    pnl = Column(Float, default=0)
    pnl_percent = Column(Float, default=0)
    signal_id = Column(String)
    reasoning = Column(Text)
    ai_provider = Column(String(50))
    last_trailing_update = Column(DateTime)
    
    # Fee tracking
    entry_fee = Column(Float, default=0)  # Trading fee on entry
    exit_fee = Column(Float, default=0)   # Trading fee on exit
    funding_fees = Column(Float, default=0)  # Accumulated funding fees
    total_fees = Column(Float, default=0)  # Total fees paid
    
    # Risk management
    leverage = Column(Float, default=1)  # Leverage used
    liquidation_price = Column(Float)  # Calculated liquidation price
    margin_used = Column(Float)  # Margin allocated
    
    # Multi-level TP/SL (4 levels)
    tp_levels = Column(JSON)  # Array of 4 take profit prices [tp1, tp2, tp3, tp4]
    sl_levels = Column(JSON)  # Array of 4 stop loss prices [sl1, sl2, sl3, sl4]
    tp_percentages = Column(JSON)  # Percentage to close at each TP [25%, 25%, 25%, 25%]
    sl_percentages = Column(JSON)  # Percentage to close at each SL [25%, 25%, 25%, 25%]
    current_tp_level = Column(Integer, default=0)  # Current TP level hit (0-4)
    current_sl_level = Column(Integer, default=0)  # Current SL level hit (0-4)
    remaining_quantity = Column(Float)  # Remaining quantity after partial closes


class PendingOrder(Base):
    """Pending orders table model"""
    __tablename__ = 'pending_orders'
    
    id = Column(String, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    order_type = Column(String(20), nullable=False)
    entry_price = Column(Float)  # Alias for price for consistency
    price = Column(Float)
    quantity = Column(Float, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    status = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    filled_at = Column(DateTime)
    exchange_order_id = Column(String)
    signal_id = Column(String)
    reasoning = Column(Text)
    ai_provider = Column(String(50))
    confidence = Column(Float)


class PositionDecision(Base):
    """Position decision history table - tracks all AI decisions for positions"""
    __tablename__ = 'position_decisions'
    
    id = Column(String, primary_key=True)
    position_id = Column(String, nullable=False, index=True)  # Links to Position.id
    timestamp = Column(DateTime, nullable=False, index=True)
    decision_type = Column(String(20), nullable=False)  # OPEN, REVIEW_KEEP, REVIEW_ADJUST, REVIEW_CLOSE, REFLECTION
    market_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float)
    unrealized_pnl_percent = Column(Float)
    ai_reasoning = Column(Text)
    ai_provider = Column(String(50))
    
    # Self-reflection (for REFLECTION decision type)
    self_reflection = Column(Text)  # AI's critique of its own performance
    
    # Technical snapshot at decision time
    technical_snapshot = Column(JSON)  # RSI, MACD, EMA values
    
    # TP/SL tracking (for ADJUST decisions)
    old_take_profit = Column(Float)
    new_take_profit = Column(Float)
    old_stop_loss = Column(Float)
    new_stop_loss = Column(Float)
    
    # AI confidence in decision
    confidence = Column(Float)


class Prompt(Base):
    """Prompts table model for dynamic signal generation strategies"""
    __tablename__ = 'prompts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    system_prompt = Column(Text, nullable=False)
    analysis_prompt_template = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False, index=True)
    strategy_type = Column(String(50), index=True)
    risk_level = Column(String(20))
    risk_score = Column(Integer)
    reward_potential = Column(String(20))
    reward_score = Column(Integer)
    max_drawdown_estimate = Column(String(20))
    win_rate_estimate = Column(String(20))
    analysis_cycle_minutes = Column(Integer, default=30)
    confidence_threshold = Column(Integer, default=60)  # Per-strategy confidence threshold
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccountBalance(Base):
    """Account balances table model"""
    __tablename__ = 'account_balances'
    
    symbol = Column(String(50), primary_key=True)
    balance = Column(Float, nullable=False, default=1000.0)
    available = Column(Float, nullable=False, default=1000.0)
    last_updated = Column(DateTime, nullable=False)


class BotSettings(Base):
    """Bot settings table model for persistent configuration"""
    __tablename__ = 'bot_settings'
    
    key = Column(String(100), primary_key=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# ============================================================================
# ARENA PLATFORM MODELS - SmartPal Gamification System
# ============================================================================

class User(Base):
    """User accounts for Arena platform"""
    __tablename__ = 'users'
    
    id = Column(String(36), primary_key=True)  # UUID
    email = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Subscription tier: sparta (free), titan (pro), kratos (elite)
    subscription_tier = Column(String(20), nullable=False, default='sparta')
    subscription_expires_at = Column(DateTime)
    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255))
    
    # Profile
    display_name = Column(String(100))
    avatar_url = Column(String(500))
    
    # Limits based on tier
    # sparta: 1 god, 1 regime/god, 2 strategists/regime, $1k training
    # titan: 1 god, 1 regime/god, 8 strategists/regime, $10k training, real trading
    # kratos: 3 gods, 3 regimes/god, 24 strategists/regime, $100k training, real trading
    
    # Tracking
    total_pnl = Column(Float, default=0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)
    
    # Onboarding
    onboarding_completed = Column(Boolean, default=False)
    global_risk_settings = Column(JSON)  # {leverage, chatgpt_validation, paper_trading}
    
    # Auth
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserRefreshToken(Base):
    """Refresh tokens for JWT authentication - allows revocation"""
    __tablename__ = 'user_refresh_tokens'
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    device_info = Column(String(255))  # e.g., "iPhone 14 Pro - Safari"
    ip_address = Column(String(45))
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserExchange(Base):
    """User's connected exchange accounts with encrypted credentials"""
    __tablename__ = 'user_exchanges'
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), nullable=False, index=True)
    exchange_name = Column(String(50), nullable=False)  # binance, xt, okx, bybit, coinw
    
    # Encrypted credentials (Fernet encryption with GOD_ENCRYPTION_KEY)
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    passphrase_encrypted = Column(Text)  # For OKX
    
    # Connection status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_verified_at = Column(DateTime)
    connection_error = Column(Text)
    
    # Permissions
    can_trade = Column(Boolean, default=False)
    can_withdraw = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class God(Base):
    """User's Gods - each God has isolated capital and positions"""
    __tablename__ = 'gods'
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), nullable=False, index=True)
    
    # Identity
    name = Column(String(100), nullable=False)
    description = Column(Text)
    avatar = Column(String(50))  # emoji or icon name: ⚡, 🌊, 🔥, 🦉, ⚔️
    preset_god_id = Column(String(36))  # If created from preset (zeus, poseidon, etc.)
    
    # Spirit (AI brain that manages regimes and strategists)
    spirit_name = Column(String(100))
    spirit_prompt = Column(Text)  # AI system prompt for regime detection & strategist management
    spirit_model = Column(String(50), default='grok-4-1-fast-reasoning')
    
    # Capital & Performance (ISOLATED per God)
    capital_balance = Column(Float, nullable=False, default=1000)  # Starting capital
    initial_capital = Column(Float, nullable=False, default=1000)
    realized_pnl = Column(Float, default=0)
    unrealized_pnl = Column(Float, default=0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    max_drawdown = Column(Float, default=0)
    
    # Exchange connection (which exchange this God trades on)
    user_exchange_id = Column(String(36))  # Links to UserExchange
    
    # Trading mode
    is_paper_trading = Column(Boolean, default=True)  # Paper vs real trading
    leverage = Column(Integer, default=50)
    trading_pairs = Column(JSON)  # List of trading pairs this God monitors
    
    # Status
    status = Column(String(20), default='inactive')  # inactive, active, paused
    current_regime_id = Column(String(36))  # Currently detected regime
    
    # Tracking
    last_analysis_at = Column(DateTime)
    last_trade_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Regime(Base):
    """Market regimes - each God can have 1-3 regimes based on tier"""
    __tablename__ = 'regimes'
    
    id = Column(String(36), primary_key=True)  # UUID
    god_id = Column(String(36), nullable=False, index=True)
    
    # Identity
    name = Column(String(100), nullable=False)
    description = Column(Text)
    preset_regime_id = Column(String(36))  # If created from preset
    
    # Detection rules (when this regime is active)
    # Each rule is a condition that must be met
    detection_rules = Column(JSON, nullable=False)
    # Example: {
    #   "rsi_range": [30, 70],
    #   "atr_percentile": [50, 100],  # High volatility
    #   "adx_min": 25,  # Strong trend
    #   "trend_direction": "up",  # up, down, neutral
    #   "bb_position": "middle"  # upper, middle, lower
    # }
    
    # Priority (lower = checked first)
    priority = Column(Integer, default=0)
    
    # Performance tracking
    times_activated = Column(Integer, default=0)
    total_pnl_in_regime = Column(Float, default=0)
    avg_duration_minutes = Column(Float, default=0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Strategist(Base):
    """Strategists - AI trading personalities assigned to regimes"""
    __tablename__ = 'strategists'
    
    id = Column(String(36), primary_key=True)  # UUID
    regime_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)  # Owner
    
    # Identity
    name = Column(String(100), nullable=False)
    description = Column(Text)
    avatar = Column(String(50))  # 🧠, 🧘, 🥷, 🔮, 🐺, 🦅, 🔥, 🏎️
    preset_strategist_id = Column(String(36))  # If created from preset
    is_custom = Column(Boolean, default=False)  # Custom-built by user
    
    # AI Configuration
    system_prompt = Column(Text, nullable=False)
    analysis_prompt_template = Column(Text, nullable=False)
    ai_model = Column(String(50), default='grok-4-1-fast-reasoning')
    
    # Trading parameters
    confidence_threshold = Column(Integer, default=60)  # 0-100
    risk_level = Column(String(20), default='medium')  # low, medium, high, extreme
    analysis_cycle_minutes = Column(Integer, default=30)
    max_positions = Column(Integer, default=3)
    position_size_percent = Column(Float, default=10)  # % of God's capital per trade
    
    # Indicators used (affects cost calculation)
    indicators = Column(JSON, nullable=False)
    # Example: {
    #   "rsi": {"enabled": true, "period": 14},
    #   "macd": {"enabled": true, "fast": 12, "slow": 26, "signal": 9},
    #   "ema": {"enabled": true, "periods": [20, 50, 200]},
    #   "bb": {"enabled": true, "period": 20, "std": 2},
    #   "atr": {"enabled": true, "period": 14},
    #   "adx": {"enabled": true, "period": 14}
    # }
    
    # Timeframes to analyze
    timeframes = Column(JSON, default=['15m', '1h', '4h'])
    
    # Performance tracking
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0)
    avg_trade_duration = Column(Float, default=0)
    
    # Cost tracking (for custom strategists)
    estimated_monthly_cost = Column(Float, default=0)  # API cost + 100% markup
    api_calls_per_hour = Column(Float, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default='inactive')  # inactive, running, paused
    last_signal_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StrategistInstance(Base):
    """Running instances of strategists - each custom strategist runs separately"""
    __tablename__ = 'strategist_instances'
    
    id = Column(String(36), primary_key=True)  # UUID
    strategist_id = Column(String(36), nullable=False, index=True)
    god_id = Column(String(36), nullable=False, index=True)
    
    # Instance status
    status = Column(String(20), default='stopped')  # stopped, starting, running, error
    pid = Column(Integer)  # Process ID if running separately
    
    # API usage tracking (for billing)
    api_calls_today = Column(Integer, default=0)
    api_calls_this_month = Column(Integer, default=0)
    api_cost_today = Column(Float, default=0)
    api_cost_this_month = Column(Float, default=0)
    
    # Performance this session
    session_pnl = Column(Float, default=0)
    session_trades = Column(Integer, default=0)
    
    started_at = Column(DateTime)
    last_heartbeat = Column(DateTime)
    error_message = Column(Text)


class GodPosition(Base):
    """Positions specific to a God (isolated from main positions table)"""
    __tablename__ = 'god_positions'
    
    id = Column(String(36), primary_key=True)  # UUID
    god_id = Column(String(36), nullable=False, index=True)
    strategist_id = Column(String(36), nullable=False, index=True)
    regime_id = Column(String(36), index=True)  # Regime when position was opened
    
    # Position details (similar to Position model)
    symbol = Column(String(50), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    status = Column(String(20), nullable=False, default='open', index=True)
    
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime)
    exit_price = Column(Float)
    exit_reason = Column(String(50))
    
    pnl = Column(Float, default=0)
    pnl_percent = Column(Float, default=0)
    
    # Fees
    entry_fee = Column(Float, default=0)
    exit_fee = Column(Float, default=0)
    funding_fees = Column(Float, default=0)
    total_fees = Column(Float, default=0)
    
    # Leverage
    leverage = Column(Float, default=50)
    margin_used = Column(Float)
    liquidation_price = Column(Float)
    
    # AI reasoning
    reasoning = Column(Text)
    signal_confidence = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class PresetGod(Base):
    """Preset God templates (Zeus, Poseidon, etc.)"""
    __tablename__ = 'preset_gods'
    
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    avatar = Column(String(50))
    
    # Spirit configuration
    spirit_name = Column(String(100))
    spirit_prompt = Column(Text)
    
    # Trading style
    risk_profile = Column(String(20))  # conservative, balanced, aggressive, extreme
    recommended_capital = Column(Float)
    
    # Default regime and strategist assignments (JSON)
    default_config = Column(JSON)
    # Example: {
    #   "regimes": ["volatile", "strong_trend"],
    #   "strategists": {
    #     "volatile": ["crazy_driver", "ninja"],
    #     "strong_trend": ["maverick", "phoenix"]
    #   }
    # }
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PresetRegime(Base):
    """Preset Regime templates"""
    __tablename__ = 'preset_regimes'
    
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    
    # Detection rules
    detection_rules = Column(JSON, nullable=False)
    
    # Recommended strategists for this regime
    recommended_strategists = Column(JSON)  # ["einstein", "zen_master"]
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PresetStrategist(Base):
    """Preset Strategist templates (Einstein, Maverick, etc.)"""
    __tablename__ = 'preset_strategists'
    
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    avatar = Column(String(50))
    
    # AI Configuration
    system_prompt = Column(Text, nullable=False)
    analysis_prompt_template = Column(Text, nullable=False)
    
    # Trading parameters
    confidence_threshold = Column(Integer, default=60)
    risk_level = Column(String(20), default='medium')
    analysis_cycle_minutes = Column(Integer, default=30)
    
    # Indicators
    indicators = Column(JSON, nullable=False)
    timeframes = Column(JSON, default=['15m', '1h', '4h'])
    
    # Best for which regimes
    best_regimes = Column(JSON)  # ["ranging", "calm"]
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StrategistCost(Base):
    """Cost calculation and billing for custom strategists"""
    __tablename__ = 'strategist_costs'
    
    id = Column(String(36), primary_key=True)
    strategist_id = Column(String(36), nullable=False, index=True)
    
    # Cost breakdown
    # Base: XAI API call cost
    xai_cost_per_call = Column(Float, default=0.002)  # ~$0.002 per analysis
    chatgpt_cost_per_call = Column(Float, default=0.003)  # If validation enabled
    
    # Usage estimates
    calls_per_hour = Column(Float)  # Based on analysis_cycle_minutes
    calls_per_day = Column(Float)
    calls_per_month = Column(Float)
    
    # Cost calculation
    base_cost_monthly = Column(Float)  # Pure API cost
    markup_percent = Column(Float, default=100)  # 100% = double the cost
    final_cost_monthly = Column(Float)  # base_cost * (1 + markup/100)
    
    # Actual usage tracking
    actual_calls_this_month = Column(Integer, default=0)
    actual_cost_this_month = Column(Float, default=0)
    
    # Billing period
    billing_period_start = Column(DateTime)
    billing_period_end = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserBilling(Base):
    """User billing records"""
    __tablename__ = 'user_billing'
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    
    # Billing type
    billing_type = Column(String(50), nullable=False)  # subscription, strategist_usage, overage
    
    # Amount
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default='USD')
    
    # Stripe
    stripe_payment_intent_id = Column(String(255))
    stripe_invoice_id = Column(String(255))
    
    # Status
    status = Column(String(20), default='pending')  # pending, paid, failed, refunded
    
    # Period
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    # Details
    description = Column(Text)
    billing_metadata = Column(JSON)  # Renamed from 'metadata' - reserved in SQLAlchemy
    
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)


class Competition(Base):
    """Trading competitions/tournaments"""
    __tablename__ = 'competitions'
    
    id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Competition type
    competition_type = Column(String(50))  # weekly, monthly, special
    
    # Dates
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    registration_deadline = Column(DateTime)
    
    # Entry
    entry_fee = Column(Float, default=0)
    min_tier = Column(String(20), default='sparta')  # Minimum tier to participate
    
    # Prizes (JSON array)
    prizes = Column(JSON)  # [{"rank": 1, "prize": "$100"}, ...]
    
    # Metrics for ranking
    ranking_metric = Column(String(50), default='pnl_percent')  # pnl_percent, total_pnl, win_rate
    
    # Status
    status = Column(String(20), default='upcoming')  # upcoming, active, ended
    
    created_at = Column(DateTime, default=datetime.utcnow)


class CompetitionEntry(Base):
    """User entries in competitions"""
    __tablename__ = 'competition_entries'
    
    id = Column(String(36), primary_key=True)
    competition_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    god_id = Column(String(36), nullable=False)  # Which God is competing
    
    # Performance during competition
    starting_balance = Column(Float)
    ending_balance = Column(Float)
    pnl = Column(Float, default=0)
    pnl_percent = Column(Float, default=0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)
    
    # Ranking
    final_rank = Column(Integer)
    prize_won = Column(String(100))
    
    registered_at = Column(DateTime, default=datetime.utcnow)


class Leaderboard(Base):
    """Global and competition leaderboards"""
    __tablename__ = 'leaderboards'
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    god_id = Column(String(36), index=True)
    
    # Leaderboard type
    leaderboard_type = Column(String(50), nullable=False)  # global_daily, global_weekly, global_monthly, competition_{id}
    
    # Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Metrics
    pnl = Column(Float, default=0)
    pnl_percent = Column(Float, default=0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)
    max_drawdown = Column(Float, default=0)
    sharpe_ratio = Column(Float, default=0)
    
    # Ranking
    rank = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemConfig(Base):
    """System-wide configuration (migrated from .env)"""
    __tablename__ = 'system_config'
    
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), default='string')  # string, int, float, bool, json
    category = Column(String(50), index=True)  # trading, ai, exchange, fees, etc.
    description = Column(Text)
    is_secret = Column(Boolean, default=False)  # If true, value is encrypted
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# END ARENA PLATFORM MODELS
# ============================================================================


class TradingDatabase:
    """PostgreSQL database manager for trading bot"""

    def __init__(self, connection_string: str = None):
        """Initialize PostgreSQL connection with connection pooling"""
        
        # If connection_string is a file path (for backward compatibility), ignore it
        if connection_string and (connection_string.endswith('.db') or 'data/' in connection_string):
            connection_string = None
        
        if connection_string is None:
            # Build connection string from environment variables
            db_type = os.getenv('DB_TYPE', 'postgresql')
            db_host = os.getenv('DB_HOST', 'localhost')
            db_port = os.getenv('DB_PORT', '5433')
            db_name = os.getenv('DB_NAME', 'trading_bot')
            db_user = os.getenv('DB_USER', 'trader')
            db_password = os.getenv('DB_PASSWORD', 'trader_password')
            
            connection_string = f"{db_type}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        # Create engine with connection pooling
        pool_size = int(os.getenv('DB_POOL_SIZE', '10'))
        max_overflow = int(os.getenv('DB_MAX_OVERFLOW', '20'))
        
        self.engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Verify connections before using
            echo=False
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Create tables
        self._create_tables()

    def _create_tables(self):
        """Create all tables if they don't exist"""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self) -> Session:
        """Context manager for database sessions"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def save_signal(self, signal_data: Dict) -> bool:
        """Save a trading signal"""
        try:
            with self.get_session() as session:
                signal = Signal(
                    id=signal_data['id'],
                    timestamp=datetime.fromisoformat(signal_data['timestamp']),
                    symbol=signal_data['symbol'],
                    signal=signal_data['signal'],
                    confidence=signal_data['confidence'],
                    current_price=signal_data['current_price'],
                    entry_price=signal_data['entry_price'],
                    stop_loss=signal_data.get('stop_loss'),
                    take_profit=signal_data.get('take_profit'),
                    reasoning=signal_data.get('reasoning'),
                    ai_provider=signal_data.get('ai_provider'),
                    chatgpt_validation=signal_data.get('chatgpt_validation')
                )
                session.merge(signal)  # Use merge instead of add to update if exists
            return True
        except Exception as e:
            print(f"Error saving signal: {e}")
            return False

    def create_position(self, position_data: Dict) -> bool:
        """Create a new position"""
        try:
            from config.config import Config
            
            with self.get_session() as session:
                # Calculate entry fee (assume taker for market orders)
                position_value = position_data['entry_price'] * position_data['quantity']
                entry_fee = position_value * Config.TAKER_FEE_RATE
                
                position = Position(
                    id=position_data['id'],
                    symbol=position_data['symbol'],
                    side=position_data['side'],
                    entry_price=position_data['entry_price'],
                    quantity=position_data['quantity'],
                    stop_loss=position_data.get('stop_loss'),
                    take_profit=position_data.get('take_profit'),
                    status=position_data.get('status', 'open'),
                    entry_time=datetime.fromisoformat(position_data['entry_time']),
                    signal_id=position_data.get('signal_id'),
                    reasoning=position_data.get('reasoning'),
                    ai_provider=position_data.get('ai_provider'),
                    entry_fee=entry_fee,
                    # Multi-level TP/SL support
                    tp_levels=position_data.get('tp_levels'),
                    sl_levels=position_data.get('sl_levels'),
                    tp_percentages=position_data.get('tp_percentages'),
                    sl_percentages=position_data.get('sl_percentages'),
                    current_tp_level=position_data.get('current_tp_level', 0),
                    current_sl_level=position_data.get('current_sl_level', 0),
                    remaining_quantity=position_data.get('remaining_quantity', position_data['quantity'])
                )
                session.add(position)
            return True
        except Exception as e:
            print(f"Error creating position: {e}")
            return False

    def update_position(self, position_id: str, updates: Dict) -> bool:
        """Update a position"""
        try:
            with self.get_session() as session:
                position = session.query(Position).filter_by(id=position_id).first()
                if position:
                    for key, value in updates.items():
                        if key == 'exit_time' and isinstance(value, str):
                            value = datetime.fromisoformat(value)
                        setattr(position, key, value)
                    return True
            return False
        except Exception as e:
            print(f"Error updating position: {e}")
            return False

    def close_position(self, position_id: str, exit_price: float, exit_reason: str = None, exit_time: str = None) -> bool:
        """Close a position"""
        try:
            from config.config import Config
            
            with self.get_session() as session:
                position = session.query(Position).filter_by(id=position_id).first()
                if position:
                    position.status = 'closed'
                    position.exit_price = exit_price
                    position.exit_time = datetime.fromisoformat(exit_time) if exit_time else datetime.now()
                    position.exit_reason = exit_reason
                    
                    # Calculate exit fee (assume taker for market orders)
                    exit_position_value = exit_price * position.quantity
                    exit_fee = exit_position_value * Config.TAKER_FEE_RATE
                    position.exit_fee = exit_fee
                    
                    # Calculate gross P&L
                    if position.side == 'long':
                        gross_pnl = (exit_price - position.entry_price) * position.quantity
                    else:
                        gross_pnl = (position.entry_price - exit_price) * position.quantity
                    
                    # Calculate net P&L (deduct all fees)
                    total_fees = (position.entry_fee or 0) + exit_fee + (position.funding_fees or 0)
                    position.pnl = gross_pnl - total_fees
                    
                    # Calculate P&L percentage based on initial position value
                    initial_value = position.entry_price * position.quantity
                    position.pnl_percent = (position.pnl / initial_value) * 100
                    
                    return True
            return False
        except Exception as e:
            print(f"Error closing position: {e}")
            return False

    def partially_close_position(self, position_id: str, close_percentage: float, 
                                  exit_price: float, level_type: str, level_number: int) -> bool:
        """
        Partially close a position at a TP/SL level
        
        Args:
            position_id: Position ID
            close_percentage: Percentage of position to close (e.g., 25 for 25%)
            exit_price: Exit price for this partial close
            level_type: 'TP' or 'SL'
            level_number: Level number (1-4)
        """
        try:
            from config.config import Config
            
            with self.get_session() as session:
                position = session.query(Position).filter_by(id=position_id).first()
                if not position or position.status != 'open':
                    return False
                
                # Calculate quantity to close
                close_qty = position.remaining_quantity * (close_percentage / 100)
                
                # Calculate partial P&L
                if position.side == 'long':
                    partial_pnl = (exit_price - position.entry_price) * close_qty
                else:
                    partial_pnl = (position.entry_price - exit_price) * close_qty
                
                # Calculate exit fee for this partial close
                exit_value = exit_price * close_qty
                exit_fee = exit_value * Config.TAKER_FEE_RATE
                
                # Update cumulative P&L and fees
                position.pnl = (position.pnl or 0) + partial_pnl - exit_fee
                position.exit_fee = (position.exit_fee or 0) + exit_fee
                position.total_fees = (position.entry_fee or 0) + position.exit_fee + (position.funding_fees or 0)
                
                # Update remaining quantity
                position.remaining_quantity -= close_qty
                
                # Update level tracking
                if level_type == 'TP':
                    position.current_tp_level = level_number
                else:  # SL
                    position.current_sl_level = level_number
                
                # If all quantity closed, mark as fully closed
                if position.remaining_quantity <= 0.0001:  # Account for floating point errors
                    position.status = 'closed'
                    position.exit_time = datetime.now()
                    position.exit_price = exit_price
                    position.exit_reason = f'{level_type}{level_number}_full'
                    
                    # Calculate final P&L percentage
                    initial_value = position.entry_price * position.quantity
                    position.pnl_percent = (position.pnl / initial_value) * 100
                
                session.commit()
                return True
                
        except Exception as e:
            print(f"Error partially closing position: {e}")
            return False

    def get_account_balances(self) -> Dict:
        """Get account balances"""
        try:
            with self.get_session() as session:
                balances_query = session.query(AccountBalance).all()
                
                balances = {}
                for bal in balances_query:
                    balances[bal.symbol] = {
                        'symbol': bal.symbol,
                        'balance': bal.balance,
                        'available': bal.available,
                        'last_updated': bal.last_updated.isoformat() if bal.last_updated else None
                    }
                
                return balances
        except Exception as e:
            print(f"Error getting balances: {e}")
            return {}

    def record_balance_update(self, balance_data: Dict) -> bool:
        """Record balance update (for compatibility, not used in PostgreSQL)"""
        return True

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions"""
        try:
            with self.get_session() as session:
                positions = session.query(Position).filter_by(status='open').all()
                return [{
                    'id': p.id,
                    'symbol': p.symbol,
                    'side': p.side,
                    'entry_price': p.entry_price,
                    'quantity': p.quantity,
                    'stop_loss': p.stop_loss,
                    'take_profit': p.take_profit,
                    'entry_time': p.entry_time.isoformat(),
                    'signal_id': p.signal_id,
                    'reasoning': p.reasoning,
                    'ai_provider': p.ai_provider,
                    # Multi-level TP/SL fields
                    'tp_levels': p.tp_levels,
                    'sl_levels': p.sl_levels,
                    'tp_percentages': p.tp_percentages,
                    'sl_percentages': p.sl_percentages,
                    'current_tp_level': p.current_tp_level,
                    'current_sl_level': p.current_sl_level,
                    'remaining_quantity': p.remaining_quantity if p.remaining_quantity is not None else p.quantity
                } for p in positions]
        except Exception as e:
            print(f"Error getting open positions: {e}")
            return []

    def get_closed_positions(self, limit: int = None) -> List[Dict]:
        """Get closed positions"""
        try:
            with self.get_session() as session:
                query = session.query(Position).filter_by(status='closed').order_by(Position.exit_time.desc())
                if limit:
                    query = query.limit(limit)
                
                positions = query.all()
                return [{
                    'id': p.id,
                    'symbol': p.symbol,
                    'side': p.side,
                    'entry_price': p.entry_price,
                    'exit_price': p.exit_price,
                    'quantity': p.quantity,
                    'entry_time': p.entry_time.isoformat(),
                    'exit_time': p.exit_time.isoformat() if p.exit_time else None,
                    'exit_reason': p.exit_reason if p.exit_reason else 'unknown',
                    'signal_id': p.signal_id,
                    'pnl': p.pnl,
                    'pnl_percent': p.pnl_percent,
                    'reasoning': p.reasoning,
                    'ai_provider': p.ai_provider
                } for p in positions]
        except Exception as e:
            print(f"Error getting closed positions: {e}")
            return []

    def get_pnl_summary(self) -> Dict:
        """Get P&L summary"""
        try:
            with self.get_session() as session:
                closed_positions = session.query(Position).filter_by(status='closed').all()
                
                total_pnl = sum(p.pnl for p in closed_positions if p.pnl is not None)
                winning_trades = [p for p in closed_positions if p.pnl and p.pnl > 0]
                losing_trades = [p for p in closed_positions if p.pnl and p.pnl < 0]
                
                return {
                    'total_pnl': total_pnl,
                    'total_trades': len(closed_positions),
                    'winning_trades': len(winning_trades),
                    'losing_trades': len(losing_trades),
                    'win_rate': len(winning_trades) / len(closed_positions) * 100 if closed_positions else 0,
                    'avg_win': sum(p.pnl for p in winning_trades) / len(winning_trades) if winning_trades else 0,
                    'avg_loss': sum(p.pnl for p in losing_trades) / len(losing_trades) if losing_trades else 0
                }
        except Exception as e:
            print(f"Error getting P&L summary: {e}")
            return {
                'total_pnl': 0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0
            }

    def get_position_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get open position by symbol"""
        try:
            with self.get_session() as session:
                position = session.query(Position).filter_by(symbol=symbol, status='open').first()
                if position:
                    return {
                        'id': position.id,
                        'symbol': position.symbol,
                        'side': position.side,
                        'entry_price': position.entry_price,
                        'quantity': position.quantity,
                        'stop_loss': position.stop_loss,
                        'take_profit': position.take_profit,
                        'entry_time': position.entry_time.isoformat(),
                        'signal_id': position.signal_id
                    }
            return None
        except Exception as e:
            print(f"Error getting position: {e}")
            return None

    def create_pending_order(self, order_data: Dict) -> bool:
        """Create a pending order"""
        try:
            with self.get_session() as session:
                order = PendingOrder(
                    id=order_data['id'],
                    symbol=order_data['symbol'],
                    side=order_data['side'],
                    order_type=order_data['order_type'],
                    entry_price=order_data.get('entry_price') or order_data.get('price'),
                    price=order_data.get('price'),
                    quantity=order_data['quantity'],
                    stop_loss=order_data.get('stop_loss'),
                    take_profit=order_data.get('take_profit'),
                    status=order_data.get('status', 'pending'),
                    created_at=datetime.fromisoformat(order_data['created_at']),
                    exchange_order_id=order_data.get('exchange_order_id'),
                    signal_id=order_data.get('signal_id'),
                    reasoning=order_data.get('reasoning'),
                    ai_provider=order_data.get('ai_provider'),
                    confidence=order_data.get('confidence')
                )
                session.add(order)
            return True
        except Exception as e:
            print(f"Error creating pending order: {e}")
            return False

    def get_pending_orders(self) -> List[Dict]:
        """Get all pending orders"""
        try:
            with self.get_session() as session:
                orders = session.query(PendingOrder).filter_by(status='pending').all()
                return [{
                    'id': o.id,
                    'symbol': o.symbol,
                    'side': o.side,
                    'order_type': o.order_type,
                    'entry_price': o.entry_price or o.price,
                    'price': o.price,
                    'quantity': o.quantity,
                    'stop_loss': o.stop_loss,
                    'take_profit': o.take_profit,
                    'status': o.status,
                    'created_at': o.created_at.isoformat(),
                    'exchange_order_id': o.exchange_order_id,
                    'signal_id': o.signal_id,
                    'reasoning': o.reasoning,
                    'ai_provider': o.ai_provider,
                    'confidence': o.confidence
                } for o in orders]
        except Exception as e:
            print(f"Error getting pending orders: {e}")
            return []

    def update_pending_order(self, order_id: str, updates: Dict) -> bool:
        """Update a pending order"""
        try:
            with self.get_session() as session:
                order = session.query(PendingOrder).filter_by(id=order_id).first()
                if order:
                    for key, value in updates.items():
                        if key == 'filled_at' and isinstance(value, str):
                            value = datetime.fromisoformat(value)
                        setattr(order, key, value)
                    return True
            return False
        except Exception as e:
            print(f"Error updating pending order: {e}")
            return False

    def get_recent_signals(self, limit: int = 100) -> List[Dict]:
        """Get recent trading signals"""
        try:
            with self.get_session() as session:
                signals = session.query(Signal).order_by(Signal.timestamp.desc()).limit(limit).all()
                return [{
                    'id': s.id,
                    'timestamp': s.timestamp.isoformat(),
                    'symbol': s.symbol,
                    'signal': s.signal,
                    'confidence': s.confidence,
                    'current_price': s.current_price,
                    'entry_price': s.entry_price,
                    'stop_loss': s.stop_loss,
                    'take_profit': s.take_profit,
                    'reasoning': s.reasoning,
                    'ai_provider': s.ai_provider,
                    'chatgpt_validation': s.chatgpt_validation
                } for s in signals]
        except Exception as e:
            print(f"Error getting recent signals: {e}")
            return []

    def get_signals(self, limit: int = 50) -> List[Dict]:
        """Get recent signals (alias for get_recent_signals)"""
        return self.get_recent_signals(limit)

    def clear_all_data(self) -> bool:
        """Clear all data from database (for testing)"""
        try:
            with self.get_session() as session:
                session.query(PendingOrder).delete()
                session.query(Position).delete()
                session.query(Signal).delete()
            print("✅ All database data cleared successfully")
            return True
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
            return False

    def initialize_balance(self, symbol: str, initial_balance: float):
        """Initialize or update account balance for a symbol"""
        try:
            with self.get_session() as session:
                balance = session.query(AccountBalance).filter_by(symbol=symbol).first()
                
                if balance:
                    # Update existing balance
                    balance.balance = initial_balance
                    balance.available = initial_balance
                    balance.last_updated = datetime.now()
                else:
                    # Create new balance entry
                    balance = AccountBalance(
                        symbol=symbol,
                        balance=initial_balance,
                        available=initial_balance,
                        last_updated=datetime.now()
                    )
                    session.add(balance)
        except Exception as e:
            print(f"Error initializing balance: {e}")

    def update_position_price(self, position_id: str, current_price: float) -> Optional[Dict]:
        """Update position with current price and check stop/take profit
        
        This method also implements trailing stop loss:
        - If position is in profit, move stop loss to protect gains
        - For LONG: Move SL above entry price as price increases
        - For SHORT: Move SL below entry price as price decreases
        """
        try:
            with self.get_session() as session:
                position = session.query(Position).filter_by(id=position_id).first()
                
                if not position or position.status != 'open':
                    return None
                
                # Calculate unrealized P&L
                if position.side == 'long':
                    unrealized_pnl = (current_price - position.entry_price) * position.quantity
                else:  # short
                    unrealized_pnl = (position.entry_price - current_price) * position.quantity
                
                # Implement trailing stop loss to protect profits
                # Only adjust if profit > $1000 and only every 5 minutes
                min_profit = 1000
                min_trail_distance = 500
                now = datetime.utcnow()
                last_update = getattr(position, 'last_trailing_update', None)
                should_update = False
                if unrealized_pnl > min_profit:
                    if last_update is None or (now - last_update).total_seconds() > 300:
                        should_update = True
                if should_update:
                    self._adjust_trailing_stop(position, current_price, unrealized_pnl, min_profit, min_trail_distance)
                    position.last_trailing_update = now
                
                # Check if should close
                should_close = self._check_stop_take(position, current_price)
                
                return {
                    'position_id': position_id,
                    'current_price': current_price,
                    'unrealized_pnl': unrealized_pnl,
                    'should_close': should_close
                }
        except Exception as e:
            print(f"Error updating position price: {e}")
            return None


    def _adjust_trailing_stop(self, position, current_price: float, unrealized_pnl: float, min_profit: float, min_trail_distance: float):
        """Custom trailing stop: only act if profit > min_profit, set SL to entry+50% profit (LONG), keep $500 distance, update every 5 min."""
        try:
            entry_price = position.entry_price
            current_stop = position.stop_loss
            profit = unrealized_pnl
            # Only act if profit > min_profit (should be enforced by caller)
            if position.side == 'long':
                # Set SL to entry + 50% of profit
                new_stop_loss = entry_price + (profit / 2.0)
                # Always keep SL at least $500 below current price
                min_allowed_sl = current_price - min_trail_distance
                if new_stop_loss < min_allowed_sl:
                    new_stop_loss = min_allowed_sl
                # Only move SL up
                if current_stop is None or new_stop_loss > current_stop:
                    old_stop = current_stop
                    position.stop_loss = new_stop_loss
                    print(f"🔒 Trailing Stop Adjusted (LONG) - {position.symbol}")
                    print(f"   Entry: ${entry_price:.6f} | Current: ${current_price:.6f}")
                    print(f"   Old SL: ${old_stop} → New SL: ${new_stop_loss:.6f}")
                    print(f"   Unrealized P&L: ${profit:.2f}")
            else:
                # SHORT: Set SL to entry - 50% of profit
                new_stop_loss = entry_price - (profit / 2.0)
                # Always keep SL at least $500 above current price
                max_allowed_sl = current_price + min_trail_distance
                if new_stop_loss > max_allowed_sl:
                    new_stop_loss = max_allowed_sl
                # Only move SL down
                if current_stop is None or new_stop_loss < current_stop:
                    old_stop = current_stop
                    position.stop_loss = new_stop_loss
                    print(f"🔒 Trailing Stop Adjusted (SHORT) - {position.symbol}")
                    print(f"   Entry: ${entry_price:.6f} | Current: ${current_price:.6f}")
                    print(f"   Old SL: {old_stop} → New SL: ${new_stop_loss:.6f}")
                    print(f"   Unrealized P&L: ${profit:.2f}")
        except Exception as e:
            print(f"Error adjusting trailing stop: {e}")

    def _check_stop_take(self, position, current_price: float) -> Optional[str]:
        """Check if position should be closed due to stop loss or take profit
        
        This handles cases where price jumps over the SL/TP levels without touching them.
        For example, if TP is $100 and price jumps from $99 to $103, it still triggers.
        """
        entry_price = position.entry_price
        
        if position.side == 'long':
            # Long position: entered at entry_price, now at current_price
            if position.stop_loss:
                # Check if price has fallen to or below stop loss
                # OR if we entered above SL and current is below SL (crossed through)
                if current_price <= position.stop_loss:
                    return 'stop_loss'
            
            if position.take_profit:
                # Check if price has risen to or above take profit
                # OR if we entered below TP and current is above TP (crossed through)
                if current_price >= position.take_profit:
                    return 'take_profit'
        
        else:  # short
            # Short position: entered at entry_price, now at current_price
            if position.stop_loss:
                # For short: SL triggers when price rises to or above stop loss
                # OR if we entered below SL and current is above SL (crossed through)
                if current_price >= position.stop_loss:
                    return 'stop_loss'
            
            if position.take_profit:
                # For short: TP triggers when price falls to or below take profit
                # OR if we entered above TP and current is below TP (crossed through)
                if current_price <= position.take_profit:
                    return 'take_profit'
        
        return None

    def save_position_decision(self, decision_data: Dict) -> bool:
        """Save a position decision to history"""
        try:
            from uuid import uuid4
            
            with self.get_session() as session:
                decision = PositionDecision(
                    id=decision_data.get('id', str(uuid4())),
                    position_id=decision_data['position_id'],
                    timestamp=datetime.fromisoformat(decision_data['timestamp']) if isinstance(decision_data.get('timestamp'), str) else decision_data.get('timestamp', datetime.now()),
                    decision_type=decision_data['decision_type'],
                    market_price=decision_data['market_price'],
                    unrealized_pnl=decision_data.get('unrealized_pnl'),
                    unrealized_pnl_percent=decision_data.get('unrealized_pnl_percent'),
                    ai_reasoning=decision_data.get('ai_reasoning'),
                    ai_provider=decision_data.get('ai_provider'),
                    technical_snapshot=decision_data.get('technical_snapshot'),
                    old_take_profit=decision_data.get('old_take_profit'),
                    new_take_profit=decision_data.get('new_take_profit'),
                    old_stop_loss=decision_data.get('old_stop_loss'),
                    new_stop_loss=decision_data.get('new_stop_loss'),
                    confidence=decision_data.get('confidence')
                )
                session.add(decision)
            return True
        except Exception as e:
            print(f"Error saving position decision: {e}")
            return False

    def get_position_decisions(self, position_id: str) -> List[Dict]:
        """Get all decisions for a specific position"""
        try:
            with self.get_session() as session:
                decisions = session.query(PositionDecision).filter_by(
                    position_id=position_id
                ).order_by(PositionDecision.timestamp.asc()).all()
                
                return [{
                    'id': d.id,
                    'position_id': d.position_id,
                    'timestamp': d.timestamp.isoformat(),
                    'decision_type': d.decision_type,
                    'market_price': d.market_price,
                    'unrealized_pnl': d.unrealized_pnl,
                    'unrealized_pnl_percent': d.unrealized_pnl_percent,
                    'ai_reasoning': d.ai_reasoning,
                    'ai_provider': d.ai_provider,
                    'technical_snapshot': d.technical_snapshot,
                    'old_take_profit': d.old_take_profit,
                    'new_take_profit': d.new_take_profit,
                    'old_stop_loss': d.old_stop_loss,
                    'new_stop_loss': d.new_stop_loss,
                    'confidence': d.confidence
                } for d in decisions]
        except Exception as e:
            print(f"Error getting position decisions: {e}")
            return []

    def get_latest_position_decision(self, position_id: str) -> Optional[Dict]:
        """Get the most recent decision for a position"""
        try:
            with self.get_session() as session:
                decision = session.query(PositionDecision).filter_by(
                    position_id=position_id
                ).order_by(PositionDecision.timestamp.desc()).first()
                
                if decision:
                    return {
                        'id': decision.id,
                        'position_id': decision.position_id,
                        'timestamp': decision.timestamp.isoformat(),
                        'decision_type': decision.decision_type,
                        'market_price': decision.market_price,
                        'unrealized_pnl': decision.unrealized_pnl,
                        'unrealized_pnl_percent': decision.unrealized_pnl_percent,
                        'ai_reasoning': decision.ai_reasoning,
                        'ai_provider': decision.ai_provider,
                        'technical_snapshot': decision.technical_snapshot,
                        'old_take_profit': decision.old_take_profit,
                        'new_take_profit': decision.new_take_profit,
                        'old_stop_loss': decision.old_stop_loss,
                        'new_stop_loss': decision.new_stop_loss,
                        'confidence': decision.confidence
                    }
                return None
        except Exception as e:
            print(f"Error getting latest position decision: {e}")
            return None

    def fill_pending_order(self, order_id: str, fill_price: float) -> Optional[str]:
        """Fill a pending order and create position, recording OPEN decision"""
        try:
            from uuid import uuid4
            from config.config import Config
            
            with self.get_session() as session:
                # Get pending order
                order = session.query(PendingOrder).filter_by(id=order_id).first()
                
                if not order:
                    return None
                
                # Create position ID
                position_id = str(uuid4())
                
                # Calculate entry fee
                position_value = fill_price * order.quantity
                entry_fee = position_value * Config.TAKER_FEE_RATE
                
                # Create position
                position = Position(
                    id=position_id,
                    symbol=order.symbol,
                    side=order.side,
                    entry_price=fill_price,
                    quantity=order.quantity,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    status='open',
                    entry_time=datetime.now(),
                    signal_id=order.signal_id,
                    reasoning=order.reasoning,
                    ai_provider=order.ai_provider,
                    entry_fee=entry_fee
                )
                session.add(position)
                
                # Update order status
                order.status = 'filled'
                order.filled_at = datetime.now()
                
                # Record OPEN decision
                decision = PositionDecision(
                    id=str(uuid4()),
                    position_id=position_id,
                    timestamp=datetime.now(),
                    decision_type='OPEN',
                    market_price=fill_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_percent=0.0,
                    ai_reasoning=order.reasoning,
                    ai_provider=order.ai_provider,
                    old_take_profit=None,
                    new_take_profit=order.take_profit,
                    old_stop_loss=None,
                    new_stop_loss=order.stop_loss,
                    confidence=order.confidence if hasattr(order, 'confidence') else None
                )
                session.add(decision)
                
                return position_id
                
        except Exception as e:
            print(f"Error filling pending order: {e}")
            return None

    # ==================== PROMPT MANAGEMENT ====================
    
    def get_all_prompts(self) -> List[Dict]:
        """Get all available prompts"""
        try:
            with self.get_session() as session:
                prompts = session.query(Prompt).order_by(Prompt.created_at.desc()).all()
                return [{
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'system_prompt': p.system_prompt,
                    'analysis_prompt_template': p.analysis_prompt_template,
                    'is_active': p.is_active,
                    'strategy_type': p.strategy_type,
                    'risk_level': p.risk_level,
                    'risk_score': p.risk_score,
                    'reward_potential': p.reward_potential,
                    'reward_score': p.reward_score,
                    'max_drawdown_estimate': p.max_drawdown_estimate,
                    'win_rate_estimate': p.win_rate_estimate,
                    'analysis_cycle_minutes': p.analysis_cycle_minutes,
                    'created_at': p.created_at.isoformat() if p.created_at else None,
                    'updated_at': p.updated_at.isoformat() if p.updated_at else None
                } for p in prompts]
        except Exception as e:
            print(f"Error getting prompts: {e}")
            return []
    
    def get_active_prompt(self) -> Optional[Dict]:
        """Get the currently active prompt"""
        try:
            with self.get_session() as session:
                prompt = session.query(Prompt).filter_by(is_active=True).first()
                if prompt:
                    return {
                        'id': prompt.id,
                        'name': prompt.name,
                        'description': prompt.description,
                        'system_prompt': prompt.system_prompt,
                        'analysis_prompt_template': prompt.analysis_prompt_template,
                        'strategy_type': prompt.strategy_type,
                        'analysis_cycle_minutes': prompt.analysis_cycle_minutes,
                        'confidence_threshold': prompt.confidence_threshold or 60
                    }
                return None
        except Exception as e:
            print(f"Error getting active prompt: {e}")
            return None
    
    def activate_prompt(self, prompt_id: int) -> bool:
        """Activate a specific prompt and deactivate all others"""
        try:
            with self.get_session() as session:
                # Deactivate all prompts
                session.query(Prompt).update({Prompt.is_active: False})
                
                # Activate the selected prompt
                prompt = session.query(Prompt).filter_by(id=prompt_id).first()
                if prompt:
                    prompt.is_active = True
                    prompt.updated_at = datetime.utcnow()
                    return True
                return False
        except Exception as e:
            print(f"Error activating prompt: {e}")
            return False
    
    def create_prompt(self, name: str, description: str, system_prompt: str, 
                     analysis_prompt_template: str, strategy_type: str = None) -> Optional[int]:
        """Create a new custom prompt"""
        try:
            with self.get_session() as session:
                prompt = Prompt(
                    name=name,
                    description=description,
                    system_prompt=system_prompt,
                    analysis_prompt_template=analysis_prompt_template,
                    strategy_type=strategy_type,
                    is_active=False
                )
                session.add(prompt)
                session.flush()
                return prompt.id
        except Exception as e:
            print(f"Error creating prompt: {e}")
            return None
    
    def update_prompt(self, prompt_id: int, **kwargs) -> bool:
        """Update an existing prompt"""
        try:
            with self.get_session() as session:
                prompt = session.query(Prompt).filter_by(id=prompt_id).first()
                if not prompt:
                    return False
                
                for key, value in kwargs.items():
                    if hasattr(prompt, key):
                        setattr(prompt, key, value)
                
                prompt.updated_at = datetime.utcnow()
                return True
        except Exception as e:
            print(f"Error updating prompt: {e}")
            return False
    
    def delete_prompt(self, prompt_id: int) -> bool:
        """Delete a prompt (cannot delete active prompt)"""
        try:
            with self.get_session() as session:
                prompt = session.query(Prompt).filter_by(id=prompt_id).first()
                if not prompt:
                    return False
                if prompt.is_active:
                    print("Cannot delete active prompt")
                    return False
                
                session.delete(prompt)
                return True
        except Exception as e:
            print(f"Error deleting prompt: {e}")
            return False
    
    def get_setting(self, key: str, default: str = None) -> str:
        """Get a bot setting value"""
        try:
            with self.get_session() as session:
                setting = session.query(BotSettings).filter_by(key=key).first()
                if setting:
                    return setting.value
                return default
        except Exception as e:
            print(f"Error getting setting {key}: {e}")
            return default
    
    def set_setting(self, key: str, value: str) -> bool:
        """Set a bot setting value"""
        try:
            with self.get_session() as session:
                setting = session.query(BotSettings).filter_by(key=key).first()
                if setting:
                    setting.value = value
                    setting.updated_at = datetime.utcnow()
                else:
                    setting = BotSettings(key=key, value=value)
                    session.add(setting)
                return True
        except Exception as e:
            print(f"Error setting {key}: {e}")
            return False

    def close(self):
        """Close database connections"""
        self.engine.dispose()

from flask import Flask, render_template, jsonify, request, redirect
from flask_cors import CORS
import threading
import time
import os
import subprocess
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key, find_dotenv
from src.database import TradingDatabase
from src.live_trader import LiveTrader
from src.order_manager import OrderManager

logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global web interface instance (created once)
_web_interface_instance = None

# API Status Tracker
class APIStatusTracker:
    def __init__(self):
        self.last_status = 'unknown'  # 'ok', 'error', 'unknown'
        self.last_check_time = None
        self.last_error_message = None
        self.credit_balance = None
        self.credit_last_updated = None
    
    def update_status(self, status: str, error_msg: str = None):
        self.last_status = status
        self.last_check_time = datetime.now()
        self.last_error_message = error_msg
    
    def update_credits(self, balance: float):
        self.credit_balance = balance
        self.credit_last_updated = datetime.now()
    
    def get_status(self):
        return {
            'status': self.last_status,
            'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
            'error_message': self.last_error_message,
            'credit_balance': self.credit_balance,
            'credit_last_updated': self.credit_last_updated.isoformat() if self.credit_last_updated else None
        }

api_status_tracker = APIStatusTracker()

# Next Analysis Time Tracker
class NextAnalysisTracker:
    def __init__(self):
        self.next_analysis_time = None
        self.last_analysis_time = None
    
    def set_next_analysis(self, next_time: datetime):
        self.next_analysis_time = next_time
        self.last_analysis_time = datetime.now()
    
    def get_info(self):
        # Get active strategy's analysis cycle
        analysis_cycle_minutes = 30  # Default
        strategy_name = "Default"
        try:
            from src.database_postgres import TradingDatabase
            db = TradingDatabase()
            active_prompt = db.get_active_prompt()
            if active_prompt:
                analysis_cycle_minutes = active_prompt.get('analysis_cycle_minutes', 30)
                strategy_name = active_prompt.get('name', 'Default')
        except Exception as e:
            pass  # Use defaults if error
        
        if self.next_analysis_time:
            seconds_remaining = (self.next_analysis_time - datetime.now()).total_seconds()
            return {
                'next_analysis_time': self.next_analysis_time.isoformat(),
                'last_analysis_time': self.last_analysis_time.isoformat() if self.last_analysis_time else None,
                'seconds_remaining': max(0, int(seconds_remaining)),
                'analysis_cycle_minutes': analysis_cycle_minutes,
                'strategy_name': strategy_name
            }
        return {
            'next_analysis_time': None,
            'last_analysis_time': None,
            'seconds_remaining': None,
            'analysis_cycle_minutes': analysis_cycle_minutes,
            'strategy_name': strategy_name
        }

next_analysis_tracker = NextAnalysisTracker()

class WebInterface:
    """Web interface for live trading monitoring"""

    def __init__(self, db_path: str = "data/trading.db"):
        """Initialize web interface"""
        self.db = TradingDatabase(db_path)
        self.live_trader = LiveTrader(db_path)
        self.order_manager = OrderManager(db_path)
        self.app = app
        # Reuse data fetcher instance instead of creating new ones
        from src.data_fetcher import DataFetcher
        self.data_fetcher = DataFetcher()
        logger.info("WebInterface initialized (reusable instance)")

    def get_dashboard_data(self):
        """Get all data for the dashboard"""
        # Use the instance's data fetcher instead of creating a new one
        # Calculate unrealized P&L for open positions
        open_positions = self.db.get_open_positions()
        total_unrealized_pnl = 0
        
        for position in open_positions:
            try:
                current_price = self.data_fetcher.get_current_price(position['symbol'])
                if current_price:
                    if position['side'] == 'long':
                        pnl = (current_price - position['entry_price']) * position['quantity']
                    else:  # short
                        pnl = (position['entry_price'] - current_price) * position['quantity']
                    total_unrealized_pnl += pnl
                    position['current_price'] = current_price
                    position['unrealized_pnl'] = pnl
                else:
                    # If price fetch failed, use entry price (P&L = 0)
                    logger.warning(f"Could not fetch price for {position['symbol']}, using entry price")
                    position['current_price'] = position['entry_price']
                    position['unrealized_pnl'] = 0
            except Exception as e:
                # Log exception and use entry price as fallback
                logger.error(f"Error calculating unrealized P&L for {position['symbol']}: {e}")
                position['current_price'] = position['entry_price']
                position['unrealized_pnl'] = 0
        
        portfolio_value = self.live_trader.get_portfolio_value()
        portfolio_value['unrealized_pnl'] = total_unrealized_pnl
        
        # Calculate total balance with unrealized P&L
        from config.config import Config
        initial_capital = Config.INITIAL_CAPITAL
        
        # Get realized P&L from closed positions
        closed_positions_all = self.db.get_closed_positions(limit=10000)
        total_realized_pnl = sum(p.get('pnl', 0) for p in closed_positions_all)
        
        # Calculate total balance
        total_balance = initial_capital + total_realized_pnl
        total_with_unrealized = total_balance + total_unrealized_pnl
        
        # Get pending orders
        pending_orders = self.db.get_pending_orders()
        
        # Get closed positions (trade history)
        closed_positions = self.db.get_closed_positions(limit=100)
        
        return {
            'portfolio': portfolio_value,
            'balances': self.db.get_account_balances(),
            'total_balance': total_balance,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_with_unrealized': total_with_unrealized,
            'initial_capital': initial_capital,
            'total_realized_pnl': total_realized_pnl,
            'open_positions': open_positions,
            'pending_orders': pending_orders,
            'closed_positions': closed_positions,
            'recent_signals': self.db.get_signals()[:20],  # Last 20 signals
            'pnl_summary': self.db.get_pnl_summary(),
            'last_update': datetime.now().isoformat()
        }

@app.route('/')
def dashboard():
    """Redirect root to Arena login"""
    return redirect('/arena/login')

@app.route('/trading-dashboard')
def trading_dashboard():
    """Serve the main trading bot dashboard"""
    return render_template('dashboard.html')

@app.route('/api/data')
def api_data():
    """API endpoint for dashboard data"""
    global _web_interface_instance
    if _web_interface_instance is None:
        _web_interface_instance = WebInterface()
    return jsonify(_web_interface_instance.get_dashboard_data())

@app.route('/api/prices')
def api_prices():
    """API endpoint for current market prices"""
    try:
        from config.config import Config
        
        logger.info("Fetching current prices...")
        
        # Use singleton instance's data_fetcher
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        data_fetcher = _web_interface_instance.data_fetcher
        
        # Use batch fetching for better performance
        price_dict = data_fetcher.get_multiple_prices(Config.TRADING_PAIRS)
        
        # Format response
        prices = {}
        for symbol, price in price_dict.items():
            if price:
                prices[symbol] = {
                    'price': price,
                    'timestamp': datetime.now().isoformat()
                }
        
        if prices:
            logger.info(f"Returning {len(prices)}/{len(Config.TRADING_PAIRS)} prices")
            return jsonify(prices)
        else:
            # If no prices were fetched, return a message
            logger.warning("No prices available - exchange may be unavailable")
            return jsonify({'message': 'Prices temporarily unavailable', 'symbols': Config.TRADING_PAIRS})
        
    except Exception as e:
        logger.error(f"Error in api_prices: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def api_status():
    """API endpoint for XAI API status"""
    try:
        # Fetch fresh API status from XAI
        try:
            from config.config import Config
            import requests
            
            headers = {
                'Authorization': f'Bearer {Config.XAI_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            # XAI doesn't have a credit endpoint, just verify API is working
            response = requests.get(
                f'{Config.XAI_API_BASE}/models',
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                # API is working
                api_status_tracker.update_status('operational', None)
            else:
                api_status_tracker.update_status('error', f'API returned {response.status_code}')
        except Exception as credit_error:
            logger.warning(f"Could not fetch API status: {credit_error}")
        
        return jsonify(api_status_tracker.get_status())
    except Exception as e:
        logger.error(f"Error in api_status: {e}")
        return jsonify({'status': 'error', 'error_message': str(e)}), 500

@app.route('/api/next-analysis')
def api_next_analysis():
    """API endpoint for next analysis countdown"""
    try:
        return jsonify(next_analysis_tracker.get_info())
    except Exception as e:
        logger.error(f"Error in api_next_analysis: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-indicators')
def api_market_indicators():
    """API endpoint for external market indicators"""
    try:
        import requests
        indicators = {}
        
        # Fear & Greed Index
        try:
            response = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5)
            if response.status_code == 200:
                fng_data = response.json()
                if 'data' in fng_data and len(fng_data['data']) > 0:
                    fng = fng_data['data'][0]
                    indicators['fear_greed'] = {
                        'value': int(fng['value']),
                        'classification': fng['value_classification'],
                        'timestamp': fng['timestamp']
                    }
        except Exception as e:
            logger.warning(f"Error fetching Fear & Greed Index: {e}")
            indicators['fear_greed'] = {'value': None, 'classification': 'N/A'}
        
        # Global Crypto Market Cap from CoinGecko
        try:
            response = requests.get('https://api.coingecko.com/api/v3/global', timeout=5)
            if response.status_code == 200:
                global_data = response.json()
                if 'data' in global_data:
                    data = global_data['data']
                    indicators['market_cap'] = {
                        'total': round(data.get('total_market_cap', {}).get('usd', 0) / 1e9, 2),  # in billions
                        'btc_dominance': round(data.get('market_cap_percentage', {}).get('btc', 0), 2),
                        'eth_dominance': round(data.get('market_cap_percentage', {}).get('eth', 0), 2),
                        'altcoin_dominance': round(100 - data.get('market_cap_percentage', {}).get('btc', 0) - data.get('market_cap_percentage', {}).get('eth', 0), 2),
                        'total_volume_24h': round(data.get('total_volume', {}).get('usd', 0) / 1e9, 2)
                    }
                    
                    # Altcoin Season Indicator (simplified: if altcoin dominance > 25% and increasing)
                    altcoin_dom = indicators['market_cap']['altcoin_dominance']
                    if altcoin_dom > 35:
                        altseason = 'Strong Altseason'
                    elif altcoin_dom > 25:
                        altseason = 'Altseason'
                    else:
                        altseason = 'Bitcoin Season'
                    
                    indicators['altcoin_season'] = {
                        'status': altseason,
                        'altcoin_dominance': altcoin_dom
                    }
        except Exception as e:
            logger.warning(f"Error fetching market cap data: {e}")
            indicators['market_cap'] = {'total': None}
            indicators['altcoin_season'] = {'status': 'N/A'}
        
        # Average Crypto RSI (using top 10 coins as proxy)
        try:
            top_coins = ['bitcoin', 'ethereum', 'binancecoin', 'ripple', 'cardano', 'solana', 'polkadot', 'dogecoin', 'avalanche-2', 'matic-network']
            rsi_values = []
            
            # Get market data for RSI calculation (simplified using price change as proxy)
            response = requests.get(
                f'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={",".join(top_coins)}&order=market_cap_desc&sparkline=false',
                timeout=5
            )
            
            if response.status_code == 200:
                coins_data = response.json()
                for coin in coins_data:
                    # Simplified RSI proxy: map price change to RSI-like value
                    price_change = coin.get('price_change_percentage_24h', 0)
                    # Map -10% to +10% change to 30-70 RSI range (simplified)
                    rsi_proxy = 50 + (price_change * 2)
                    rsi_proxy = max(0, min(100, rsi_proxy))  # Clamp to 0-100
                    rsi_values.append(rsi_proxy)
                
                avg_rsi = sum(rsi_values) / len(rsi_values) if rsi_values else 50
                
                if avg_rsi > 70:
                    rsi_status = 'Overbought'
                elif avg_rsi < 30:
                    rsi_status = 'Oversold'
                else:
                    rsi_status = 'Neutral'
                
                indicators['average_crypto_rsi'] = {
                    'value': round(avg_rsi, 1),
                    'status': rsi_status
                }
        except Exception as e:
            logger.warning(f"Error calculating average RSI: {e}")
            indicators['average_crypto_rsi'] = {'value': 50, 'status': 'N/A'}
        
        return jsonify(indicators)
        
    except Exception as e:
        logger.error(f"Error in api_market_indicators: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-logs')
def api_ai_logs():
    """API endpoint for AI analysis logs (signals with reasoning)"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        # Get recent signals from database (these contain AI reasoning)
        signals = _web_interface_instance.db.get_signals()
        
        # Format signals for AI logs display
        ai_logs = []
        for signal in signals:
            log_entry = {
                'symbol': signal.get('symbol'),
                'signal': signal.get('signal'),
                'confidence': signal.get('confidence'),
                'current_price': signal.get('current_price'),
                'entry_price': signal.get('entry_price'),
                'stop_loss': signal.get('stop_loss'),
                'take_profit': signal.get('take_profit'),
                'reasoning': signal.get('reasoning'),
                'ai_provider': signal.get('ai_provider'),
                'timestamp': signal.get('timestamp'),
                'chatgpt_validation': signal.get('chatgpt_validation')  # Include ChatGPT validation
            }
            ai_logs.append(log_entry)
        
        return jsonify(ai_logs)
        
    except Exception as e:
        logger.error(f"Error in api_ai_logs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/position-decisions/<position_id>')
def get_position_decisions(position_id):
    """Get all AI decisions for a specific position"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        # Get position details
        decisions = _web_interface_instance.db.get_position_decisions(position_id)
        
        return jsonify(decisions)
        
    except Exception as e:
        logger.error(f"Error getting position decisions: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/close-position', methods=['POST'])
def close_position():
    """Manually close a position"""
    try:
        data = request.json
        position_id = data.get('position_id')
        
        if not position_id:
            return jsonify({'error': 'Position ID is required'}), 400
        
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        # Get the position details
        positions = _web_interface_instance.db.get_open_positions()
        position = next((p for p in positions if p['id'] == position_id), None)
        
        if not position:
            return jsonify({'error': 'Position not found'}), 404
        
        # Get current price
        current_price = _web_interface_instance.data_fetcher.get_current_price(position['symbol'])
        if not current_price:
            return jsonify({'error': 'Could not fetch current price'}), 500
        
        # Calculate P&L
        if position['side'] == 'long':
            pnl = (current_price - position['entry_price']) * position['quantity']
        else:  # short
            pnl = (position['entry_price'] - current_price) * position['quantity']
        
        # Close the position
        _web_interface_instance.db.close_position(
            position_id=position_id,
            exit_price=current_price,
            exit_reason='manual'
        )
        
        logger.info(f"Position {position_id} ({position['symbol']}) manually closed by user at ${current_price:.2f}, P&L: ${pnl:.2f}")
        
        return jsonify({
            'success': True,
            'message': 'Position closed successfully',
            'pnl': pnl,
            'exit_price': current_price,
            'symbol': position['symbol']
        })
        
    except Exception as e:
        logger.error(f"Error closing position: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/signal-analytics', methods=['GET'])
def get_signal_analytics():
    """Get signal analytics (buy vs sell count) for a given time period"""
    try:
        period = request.args.get('period', '1h')
        
        # Calculate time threshold based on period
        period_map = {
            '1h': timedelta(hours=1),
            '3h': timedelta(hours=3),
            '6h': timedelta(hours=6),
            '12h': timedelta(hours=12),
            '1d': timedelta(days=1),
            '1w': timedelta(weeks=1),
            '1m': timedelta(days=30)
        }
        
        time_delta = period_map.get(period, timedelta(hours=1))
        cutoff_time = datetime.now() - time_delta
        
        # Query database for signals
        db = TradingDatabase()
        signals = db.get_recent_signals(limit=1000)  # Get more signals to filter by time
        
        # Filter by time and count buy/sell
        buy_count = 0
        sell_count = 0
        
        for signal in signals:
            # Parse timestamp
            if isinstance(signal['timestamp'], str):
                signal_time = datetime.fromisoformat(signal['timestamp'].replace('Z', '+00:00'))
            else:
                signal_time = signal['timestamp']
            
            # Remove timezone info for comparison
            if signal_time.tzinfo:
                signal_time = signal_time.replace(tzinfo=None)
            
            # Check if signal is within time period
            if signal_time >= cutoff_time:
                signal_type = signal.get('signal', '').upper()
                if signal_type == 'BUY':
                    buy_count += 1
                elif signal_type == 'SELL':
                    sell_count += 1
        
        return jsonify({
            'buy_count': buy_count,
            'sell_count': sell_count,
            'total_signals': buy_count + sell_count,
            'period': period
        })
        
    except Exception as e:
        logger.error(f"Error getting signal analytics: {e}", exc_info=True)
        return jsonify({
            'buy_count': 0,
            'sell_count': 0,
            'total_signals': 0,
            'period': period,
            'error': str(e)
        }), 500

@app.route('/api/performance-metrics', methods=['GET'])
def get_performance_metrics():
    """Get comprehensive performance metrics"""
    try:
        db = TradingDatabase()
        
        # Get both open and closed positions
        open_positions = db.get_open_positions()
        closed_positions = db.get_closed_positions(limit=1000)
        all_positions = open_positions + closed_positions
        
        if not all_positions:
            return jsonify({
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'avg_hold_time': 0,
                'equity_curve': [],
                'trade_distribution': {'wins': 0, 'losses': 0},
                'pair_performance': {},
                'hourly_performance': {},
                'error': 'No trade data available'
            })
        
        # Filter closed positions with valid data for calculations
        valid_closed = [p for p in closed_positions if p.get('pnl') is not None]
        
        if not valid_closed:
            return jsonify({
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'avg_hold_time': 0,
                'equity_curve': [],
                'trade_distribution': {'wins': 0, 'losses': 0},
                'pair_performance': {},
                'hourly_performance': {}
            })
        
        # Calculate metrics
        returns = [p['pnl'] for p in valid_closed]
        
        # Sharpe Ratio (annualized, assuming daily returns)
        if len(returns) > 1:
            import numpy as np
            returns_array = np.array(returns)
            sharpe = (np.mean(returns_array) / np.std(returns_array)) * np.sqrt(252) if np.std(returns_array) > 0 else 0
        else:
            sharpe = 0
        
        # Max Drawdown
        cumulative_returns = []
        cumsum = 0
        for ret in returns:
            cumsum += ret
            cumulative_returns.append(cumsum)
        
        if cumulative_returns:
            peak = cumulative_returns[0]
            max_dd = 0
            for val in cumulative_returns:
                if val > peak:
                    peak = val
                dd = peak - val
                if dd > max_dd:
                    max_dd = dd
        else:
            max_dd = 0
        
        # Profit Factor
        gross_profit = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Average Hold Time
        hold_times = []
        for p in valid_closed:
            if p.get('entry_time') and p.get('exit_time'):
                try:
                    entry = datetime.fromisoformat(p['entry_time'].replace('Z', '+00:00'))
                    exit = datetime.fromisoformat(p['exit_time'].replace('Z', '+00:00'))
                    duration = (exit - entry).total_seconds() / 3600  # hours
                    hold_times.append(duration)
                except:
                    pass
        
        avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
        
        # Equity Curve
        equity_curve = []
        cumulative = 10000  # Starting capital
        for i, ret in enumerate(returns):
            cumulative += ret
            equity_curve.append({
                'index': i,
                'equity': round(cumulative, 2)
            })
        
        # Trade Distribution
        wins = len([r for r in returns if r > 0])
        losses = len([r for r in returns if r < 0])
        
        # Pair Performance
        pair_pnl = {}
        for p in valid_closed:
            symbol = p.get('symbol', 'Unknown')
            pnl = p.get('pnl', 0)
            if symbol not in pair_pnl:
                pair_pnl[symbol] = 0
            pair_pnl[symbol] += pnl
        
        # Hourly Performance
        hourly_pnl = {str(h): 0 for h in range(24)}
        hourly_count = {str(h): 0 for h in range(24)}
        
        for p in valid_closed:
            if p.get('exit_time'):
                try:
                    exit_time = datetime.fromisoformat(p['exit_time'].replace('Z', '+00:00'))
                    hour = str(exit_time.hour)
                    hourly_pnl[hour] += p.get('pnl', 0)
                    hourly_count[hour] += 1
                except:
                    pass
        
        # Average P&L per hour
        hourly_avg = {h: (hourly_pnl[h] / hourly_count[h] if hourly_count[h] > 0 else 0) for h in hourly_pnl}
        
        return jsonify({
            'sharpe_ratio': round(sharpe, 2),
            'max_drawdown': round(max_dd, 2),
            'profit_factor': round(profit_factor, 2),
            'avg_hold_time': round(avg_hold_time, 2),
            'equity_curve': equity_curve,
            'trade_distribution': {'wins': wins, 'losses': losses},
            'pair_performance': pair_pnl,
            'hourly_performance': hourly_avg
        })
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-insights', methods=['GET'])
def get_market_insights():
    """Get market insights and AI analysis"""
    try:
        db = TradingDatabase()
        open_positions = db.get_open_positions()
        closed_positions = db.get_closed_positions(limit=1000)
        all_positions = open_positions + closed_positions
        # Get ALL signals (not just recent 50) to match with positions
        signals = db.get_signals(limit=10000)
        
        # AI Confidence Analysis
        confidence_buckets = {'high': [], 'medium': [], 'low': []}
        
        # Debug logging
        logger.info(f"Analyzing {len(signals)} signals and {len(all_positions)} positions")
        matched_count = 0
        
        for signal in signals:
            confidence = signal.get('confidence', 0)
            signal_id = signal.get('id')
            
            # Find corresponding position
            position = next((p for p in all_positions if p.get('signal_id') == signal_id), None)
            
            if position and position.get('pnl') is not None:
                matched_count += 1
                outcome = 'win' if position['pnl'] > 0 else 'loss'
                
                if confidence >= 80:
                    confidence_buckets['high'].append(outcome)
                elif confidence >= 60:
                    confidence_buckets['medium'].append(outcome)
                else:
                    confidence_buckets['low'].append(outcome)
        
        logger.info(f"Matched {matched_count} signals with positions. Buckets: high={len(confidence_buckets['high'])}, med={len(confidence_buckets['medium'])}, low={len(confidence_buckets['low'])}")
        
        # Calculate win rates
        high_wr = (len([o for o in confidence_buckets['high'] if o == 'win']) / len(confidence_buckets['high']) * 100) if confidence_buckets['high'] else 0
        med_wr = (len([o for o in confidence_buckets['medium'] if o == 'win']) / len(confidence_buckets['medium']) * 100) if confidence_buckets['medium'] else 0
        low_wr = (len([o for o in confidence_buckets['low'] if o == 'win']) / len(confidence_buckets['low']) * 100) if confidence_buckets['low'] else 0
        
        # Exit Reasons
        exit_reasons = {}
        for p in closed_positions:
            reason = p.get('exit_reason', 'unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        # Long vs Short Performance
        long_pnl = sum(p.get('pnl', 0) for p in closed_positions if p.get('side') == 'long')
        short_pnl = sum(p.get('pnl', 0) for p in closed_positions if p.get('side') == 'short')
        long_count = len([p for p in closed_positions if p.get('side') == 'long'])
        short_count = len([p for p in closed_positions if p.get('side') == 'short'])
        
        # AI Reasoning Keywords
        all_reasoning = ' '.join([s.get('reasoning', '') for s in signals if s.get('reasoning')])
        
        # Simple keyword extraction (common trading terms)
        keywords = {}
        trading_terms = ['bullish', 'bearish', 'support', 'resistance', 'breakout', 'trend', 
                        'reversal', 'momentum', 'oversold', 'overbought', 'consolidation',
                        'volume', 'uptrend', 'downtrend', 'crossover', 'divergence']
        
        for term in trading_terms:
            count = all_reasoning.lower().count(term)
            if count > 0:
                keywords[term] = count
        
        # Add token names from our trading pairs
        token_names = ['BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'DOGE', 'SOL', 'TRX', 'LTC']
        for token in token_names:
            # Count mentions in signals
            count = all_reasoning.upper().count(token)
            if count > 0:
                keywords[f"🪙 {token}"] = count
        
        # Fetch trending coins from CoinGecko
        try:
            trending_response = requests.get(
                'https://api.coingecko.com/api/v3/search/trending',
                timeout=3
            )
            if trending_response.status_code == 200:
                trending_data = trending_response.json()
                trending_coins = trending_data.get('coins', [])[:5]  # Top 5 trending
                for coin in trending_coins:
                    coin_info = coin.get('item', {})
                    symbol = coin_info.get('symbol', '').upper()
                    name = coin_info.get('name', '')
                    if symbol:
                        keywords[f"🔥 {symbol}"] = coin_info.get('market_cap_rank', 999)
        except Exception as e:
            logger.warning(f"Could not fetch trending coins: {e}")
        
        # Sort by frequency
        keywords = dict(sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:20])
        
        return jsonify({
            'confidence_win_rates': {
                'high': round(high_wr, 1),
                'medium': round(med_wr, 1),
                'low': round(low_wr, 1)
            },
            'confidence_distribution': {
                'high': len(confidence_buckets['high']),
                'medium': len(confidence_buckets['medium']),
                'low': len(confidence_buckets['low'])
            },
            'exit_reasons': exit_reasons,
            'long_short': {
                'long_pnl': round(long_pnl, 2),
                'short_pnl': round(short_pnl, 2),
                'long_count': long_count,
                'short_count': short_count,
                'long_avg': round(long_pnl / long_count, 2) if long_count > 0 else 0,
                'short_avg': round(short_pnl / short_count, 2) if short_count > 0 else 0
            },
            'keywords': keywords
        })
        
    except Exception as e:
        logger.error(f"Error getting market insights: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current bot settings"""
    try:
        load_dotenv()
        
        settings = {
            'ai_provider': os.getenv('AI_PROVIDER', 'openrouter'),
            'ai_model': os.getenv('AI_MODEL', 'anthropic/claude-3.5-sonnet'),
            'position_size': os.getenv('POSITION_SIZE', '100'),
            'max_positions': os.getenv('MAX_POSITIONS', '5'),
            'stop_loss_pct': os.getenv('STOP_LOSS_PCT', '2.0'),
            'take_profit_pct': os.getenv('TAKE_PROFIT_PCT', '5.0'),
            'trading_mode': os.getenv('TRADING_MODE', 'reasonable'),
            'bot_mode': os.getenv('BOT_MODE', 'reasonable'),  # aggressive or reasonable
            'is_paper_trading': os.getenv('IS_PAPER_TRADING', 'true'),  # true or false
            'confidence_threshold': os.getenv('CONFIDENCE_THRESHOLD', '60')  # 0-100
        }
        
        return jsonify(settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-ai', methods=['POST'])
def test_ai():
    """Test AI connection"""
    try:
        data = request.json
        provider = data.get('provider')
        model = data.get('model')
        api_key = data.get('api_key')
        
        if not all([provider, model, api_key]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Import requests for API testing
        import requests
        
        # Test connection based on provider
        if provider == 'openrouter':
            url = 'https://openrouter.ai/api/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model,
                'messages': [{'role': 'user', 'content': 'Hello'}],
                'max_tokens': 10
            }
        elif provider == 'openai':
            url = 'https://api.openai.com/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model,
                'messages': [{'role': 'user', 'content': 'Hello'}],
                'max_tokens': 10
            }
        elif provider == 'anthropic':
            url = 'https://api.anthropic.com/v1/messages'
            headers = {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model,
                'max_tokens': 10,
                'messages': [{'role': 'user', 'content': 'Hello'}]
            }
        elif provider == 'xai':
            url = 'https://api.x.ai/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model,
                'messages': [{'role': 'user', 'content': 'Hello'}],
                'max_tokens': 10
            }
        elif provider == 'google':
            url = f'https://generativelanguage.googleapis.com/v1/models/{model}:generateContent'
            headers = {
                'Content-Type': 'application/json'
            }
            payload = {
                'contents': [{'parts': [{'text': 'Hello'}]}]
            }
            url = f'{url}?key={api_key}'
        else:
            return jsonify({'success': False, 'error': 'Unknown provider'})
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f'API returned status {response.status_code}'})
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Connection timeout'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save-ai-settings', methods=['POST'])
def save_ai_settings():
    """Save AI provider settings"""
    try:
        data = request.json
        provider = data.get('provider')
        model = data.get('model')
        api_key = data.get('api_key')
        
        if not all([provider, model, api_key]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Check if running in Docker (read-only filesystem)
        is_docker = os.path.exists('/.dockerenv')
        
        if is_docker:
            return jsonify({
                'success': False, 
                'error': 'Cannot save settings in Docker container. Please update the .env file on the host and restart the container with: docker compose restart trading-bot'
            })
        
        # Find or create .env file
        env_file = find_dotenv()
        if not env_file:
            env_file = '.env'
            open(env_file, 'a').close()
        
        # Update .env file
        set_key(env_file, 'AI_PROVIDER', provider)
        set_key(env_file, 'AI_MODEL', model)
        
        # Save API key with appropriate key name
        if provider == 'openrouter':
            set_key(env_file, 'OPENROUTER_API_KEY', api_key)
            set_key(env_file, 'GROK_API_KEY', api_key)  # Also update GROK_API_KEY
        elif provider == 'openai':
            set_key(env_file, 'OPENAI_API_KEY', api_key)
        elif provider == 'anthropic':
            set_key(env_file, 'ANTHROPIC_API_KEY', api_key)
        elif provider == 'xai':
            set_key(env_file, 'XAI_API_KEY', api_key)
        elif provider == 'google':
            set_key(env_file, 'GOOGLE_API_KEY', api_key)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save-exchange-settings', methods=['POST'])
def save_exchange_settings():
    """Save exchange API credentials"""
    try:
        data = request.json
        api_key = data.get('api_key')
        secret = data.get('secret')
        
        if not all([api_key, secret]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Check if running in Docker (read-only filesystem)
        is_docker = os.path.exists('/.dockerenv')
        
        if is_docker:
            return jsonify({
                'success': False, 
                'error': 'Cannot save settings in Docker container. Please update the .env file on the host and restart the container with: docker compose restart trading-bot'
            })
        
        # Find or create .env file
        env_file = find_dotenv()
        if not env_file:
            env_file = '.env'
            open(env_file, 'a').close()
        
        # Update .env file
        set_key(env_file, 'XT_API_KEY', api_key)
        set_key(env_file, 'XT_SECRET', secret)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save-trading-settings', methods=['POST'])
def save_trading_settings():
    """Save trading configuration"""
    try:
        data = request.json
        
        # Find or create .env file
        env_file = find_dotenv()
        if not env_file:
            env_file = '.env'
            open(env_file, 'a').close()
        
        # Update .env file with trading settings
        if 'position_size' in data:
            set_key(env_file, 'POSITION_SIZE', str(data['position_size']))
        if 'max_positions' in data:
            set_key(env_file, 'MAX_POSITIONS', str(data['max_positions']))
        if 'stop_loss_pct' in data:
            set_key(env_file, 'STOP_LOSS_PCT', str(data['stop_loss_pct']))
        if 'take_profit_pct' in data:
            set_key(env_file, 'TAKE_PROFIT_PCT', str(data['take_profit_pct']))
        if 'trading_mode' in data:
            set_key(env_file, 'TRADING_MODE', data['trading_mode'])
        if 'bot_mode' in data:
            set_key(env_file, 'BOT_MODE', data['bot_mode'])
        if 'is_paper_trading' in data:
            set_key(env_file, 'IS_PAPER_TRADING', data['is_paper_trading'])
        if 'confidence_threshold' in data:
            set_key(env_file, 'CONFIDENCE_THRESHOLD', str(data['confidence_threshold']))
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== PROMPT MANAGEMENT ENDPOINTS ====================

@app.route('/api/prompts', methods=['GET'])
def get_prompts():
    """Get all available prompts"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        prompts = _web_interface_instance.db.get_all_prompts()
        return jsonify(prompts)
    except Exception as e:
        logger.error(f"Error getting prompts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prompts/active', methods=['GET'])
def get_active_prompt():
    """Get currently active prompt"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        prompt = _web_interface_instance.db.get_active_prompt()
        return jsonify(prompt if prompt else {})
    except Exception as e:
        logger.error(f"Error getting active prompt: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prompts/activate', methods=['POST'])
def activate_prompt():
    """Activate a specific prompt"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        data = request.get_json()
        prompt_id = data.get('prompt_id')
        
        if not prompt_id:
            return jsonify({'success': False, 'error': 'prompt_id required'}), 400
        
        success = _web_interface_instance.db.activate_prompt(prompt_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Prompt activated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to activate prompt'}), 400
            
    except Exception as e:
        logger.error(f"Error activating prompt: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prompts/create', methods=['POST'])
def create_prompt():
    """Create a new custom prompt"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        data = request.get_json()
        
        required_fields = ['name', 'description', 'system_prompt', 'analysis_prompt_template']
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return jsonify({'success': False, 'error': f'Missing fields: {", ".join(missing)}'}), 400
        
        prompt_id = _web_interface_instance.db.create_prompt(
            name=data['name'],
            description=data['description'],
            system_prompt=data['system_prompt'],
            analysis_prompt_template=data['analysis_prompt_template'],
            strategy_type=data.get('strategy_type', 'custom')
        )
        
        if prompt_id:
            return jsonify({'success': True, 'prompt_id': prompt_id, 'message': 'Prompt created successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to create prompt'}), 400
            
    except Exception as e:
        logger.error(f"Error creating prompt: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prompts/update', methods=['PUT'])
def update_prompt():
    """Update an existing prompt"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        data = request.get_json()
        prompt_id = data.get('prompt_id')
        
        if not prompt_id:
            return jsonify({'success': False, 'error': 'prompt_id required'}), 400
        
        # Remove prompt_id from data before updating
        update_data = {k: v for k, v in data.items() if k != 'prompt_id'}
        
        success = _web_interface_instance.db.update_prompt(prompt_id, **update_data)
        
        if success:
            return jsonify({'success': True, 'message': 'Prompt updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update prompt'}), 400
            
    except Exception as e:
        logger.error(f"Error updating prompt: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prompts/delete', methods=['DELETE'])
def delete_prompt():
    """Delete a prompt"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        data = request.get_json()
        prompt_id = data.get('prompt_id')
        
        if not prompt_id:
            return jsonify({'success': False, 'error': 'prompt_id required'}), 400
        
        success = _web_interface_instance.db.delete_prompt(prompt_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Prompt deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete prompt (may be active)'}), 400
            
    except Exception as e:
        logger.error(f"Error deleting prompt: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/translate', methods=['POST'])
def translate_text():
    """Translate text to Farsi using ChatGPT"""
    try:
        from src.grok_analyzer import GrokAnalyzer
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Use GrokAnalyzer's translation method
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        analyzer = GrokAnalyzer(db=_web_interface_instance.db)
        translated = analyzer.translate_to_farsi(text)
        
        return jsonify({'translated': translated})
        
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== CHATGPT VALIDATION TOGGLE ====================

@app.route('/api/chatgpt-validation/status', methods=['GET'])
def get_chatgpt_validation_status():
    """Get current ChatGPT validation status"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        from src.grok_analyzer import GrokAnalyzer
        analyzer = GrokAnalyzer(db=_web_interface_instance.db)
        enabled = analyzer.get_chatgpt_validation_status()
        
        return jsonify({
            'enabled': enabled,
            'ai_provider': 'XAI Grok',
            'validator': 'ChatGPT GPT-5.2' if enabled else 'None'
        })
        
    except Exception as e:
        logger.error(f"Error getting ChatGPT validation status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chatgpt-validation/toggle', methods=['POST'])
def toggle_chatgpt_validation():
    """Toggle ChatGPT validation on/off (persists to database)"""
    try:
        global _web_interface_instance
        if _web_interface_instance is None:
            _web_interface_instance = WebInterface()
        
        data = request.get_json()
        enabled = data.get('enabled', False)
        
        # Update analyzer - this will persist to database
        from src.grok_analyzer import GrokAnalyzer
        analyzer = GrokAnalyzer(db=_web_interface_instance.db)
        success = analyzer.set_chatgpt_validation(enabled)
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to update setting in database'}), 500
        
        logger.info(f"ChatGPT validation {'enabled' if enabled else 'disabled'} (persisted to database)")
        
        return jsonify({
            'success': True,
            'enabled': enabled,
            'message': f'ChatGPT validation {"enabled" if enabled else "disabled"}'
        })
        
    except Exception as e:
        logger.error(f"Error toggling ChatGPT validation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== BOT RESTART ====================

@app.route('/api/restart-bot', methods=['POST'])
def restart_bot():
    """Restart the trading bot"""
    try:
        # Get the current directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Path to service manager script
        script_path = os.path.join(current_dir, 'service_manager.sh')
        
        if not os.path.exists(script_path):
            return jsonify({'success': False, 'error': 'Service manager script not found'})
        
        # Run restart command in background
        subprocess.Popen([script_path, 'restart'], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def run_web_interface(port: int = 8080):
    """Run the web interface in a separate thread"""
    global _web_interface_instance
    # Create the singleton instance at startup
    if _web_interface_instance is None:
        logger.info("Creating WebInterface singleton instance...")
        _web_interface_instance = WebInterface()
        logger.info("WebInterface singleton created successfully")
    
    # Register Arena routes
    try:
        from src.arena_routes import arena_routes_bp
        from src.arena_api import arena_api_bp, init_arena_api
        from src.database_postgres import TradingDatabase
        
        # Initialize Arena API with database
        arena_db = TradingDatabase()
        init_arena_api(arena_db)
        
        # Register both blueprints
        app.register_blueprint(arena_routes_bp, url_prefix='/arena')
        app.register_blueprint(arena_api_bp)
        logger.info("✅ Arena platform routes registered")
    except ImportError as e:
        logger.warning(f"Arena routes not available: {e}")
    except Exception as e:
        logger.error(f"Error registering Arena routes: {e}")
    
    def run_app():
        try:
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"Error starting web interface: {e}")
            print("Trying different port...")
            try:
                app.run(host='0.0.0.0', port=port+1, debug=False, use_reloader=False)
            except Exception as e2:
                print(f"Failed to start web interface: {e2}")

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    print(f"Web interface started at http://localhost:{port}")
    return thread

if __name__ == '__main__':
    run_web_interface()

"""
SmartPal Arena - API Endpoints
Flask Blueprint with all Arena gamification routes
"""

import logging
from datetime import datetime
from functools import wraps
import uuid

from flask import Blueprint, request, jsonify, g

from src.auth import AuthManager, require_auth, require_tier, get_tier_limits, check_tier_limit
from src.god_manager import GodManager
from src.strategist_cost import StrategistCostCalculator
from src.exchange_adapters import (
    create_adapter, get_encryptor, get_exchange_info, SUPPORTED_EXCHANGES
)

logger = logging.getLogger(__name__)

# Create Blueprint
arena_api_bp = Blueprint('arena_api', __name__, url_prefix='/api/arena')

# Global references (set by init_arena_api)
_db = None
_auth_manager = None
_god_manager = None
_cost_calculator = None


def init_arena_api(db):
    """Initialize Arena API with database connection"""
    global _db, _auth_manager, _god_manager, _cost_calculator
    
    _db = db
    _auth_manager = AuthManager(db)
    _god_manager = GodManager(db)
    _cost_calculator = StrategistCostCalculator(db)
    
    logger.info("Arena API initialized")


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@arena_api_bp.route('/auth/register', methods=['POST'])
def register():
    """Register a new user"""
    data = request.json or {}
    
    email = data.get('email', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not email or not username or not password:
        return jsonify({'error': 'Email, username, and password required'}), 400
    
    result = _auth_manager.register(email, username, password)
    
    if result.get('success'):
        # Auto-login after registration
        login_result = _auth_manager.login(
            email, password,
            device_info=request.headers.get('User-Agent'),
            ip_address=request.remote_addr
        )
        if login_result.get('success'):
            return jsonify(login_result), 201
        return jsonify(result), 201
    
    return jsonify(result), 400


@arena_api_bp.route('/auth/login', methods=['POST'])
def login():
    """Login and get tokens"""
    from src.database_postgres import User
    
    data = request.json or {}
    
    email_or_username = (data.get('email') or data.get('username') or '').strip()
    password = data.get('password', '')
    
    if not email_or_username or not password:
        return jsonify({'error': 'Email/username and password required'}), 400
    
    result = _auth_manager.login(
        email_or_username, password,
        device_info=request.headers.get('User-Agent'),
        ip_address=request.remote_addr
    )
    
    if result.get('success'):
        # Add onboarding status to response
        try:
            with _db.get_session() as session:
                user = session.query(User).filter_by(id=result['user_id']).first()
                if user:
                    result['onboarding_completed'] = user.onboarding_completed if hasattr(user, 'onboarding_completed') else True
        except Exception as e:
            logger.error(f"Error checking onboarding status: {e}")
            result['onboarding_completed'] = True
        
        return jsonify(result), 200
    
    return jsonify(result), 401


@arena_api_bp.route('/auth/refresh', methods=['POST'])
def refresh_token():
    """Refresh access token using refresh token"""
    data = request.json or {}
    refresh_token = data.get('refresh_token', '')
    
    if not refresh_token:
        return jsonify({'error': 'Refresh token required'}), 400
    
    result = _auth_manager.refresh_tokens(
        refresh_token,
        device_info=request.headers.get('User-Agent'),
        ip_address=request.remote_addr
    )
    
    if result.get('success'):
        return jsonify(result), 200
    
    return jsonify(result), 401


@arena_api_bp.route('/auth/logout', methods=['POST'])
@require_auth
def logout():
    """Logout (revoke refresh token)"""
    data = request.json or {}
    refresh_token = data.get('refresh_token', '')
    
    result = _auth_manager.logout(refresh_token)
    return jsonify(result), 200


@arena_api_bp.route('/auth/logout-all', methods=['POST'])
@require_auth
def logout_all():
    """Logout from all devices"""
    result = _auth_manager.logout_all_devices(g.user_id)
    return jsonify(result), 200


# ============================================================================
# USER ROUTES
# ============================================================================

@arena_api_bp.route('/user/profile', methods=['GET'])
@require_auth
def get_profile():
    """Get current user's profile"""
    user = _auth_manager.get_user(g.user_id)
    if user:
        return jsonify(user), 200
    return jsonify({'error': 'User not found'}), 404


@arena_api_bp.route('/user/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile"""
    from src.database_postgres import User
    
    data = request.json or {}
    
    try:
        with _db.get_session() as session:
            user = session.query(User).filter_by(id=g.user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Update allowed fields
            if 'display_name' in data:
                user.display_name = data['display_name']
            if 'avatar_url' in data:
                user.avatar_url = data['avatar_url']
            
            user.updated_at = datetime.utcnow()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        return jsonify({'error': 'Update failed'}), 500


@arena_api_bp.route('/user/tier-limits', methods=['GET'])
@require_auth
def get_user_tier_limits():
    """Get current user's tier limits and usage"""
    from src.database_postgres import God, Strategist
    
    limits = get_tier_limits(g.tier)
    
    # Get current usage
    try:
        with _db.get_session() as session:
            god_count = session.query(God).filter_by(user_id=g.user_id).count()
            strategist_count = session.query(Strategist).filter_by(
                user_id=g.user_id, is_custom=True
            ).count()
        
        return jsonify({
            'tier': g.tier,
            'limits': limits,
            'usage': {
                'gods': god_count,
                'custom_strategists': strategist_count
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting tier limits: {e}")
        return jsonify({'tier': g.tier, 'limits': limits}), 200


@arena_api_bp.route('/onboarding/complete', methods=['POST'])
@require_auth
def complete_onboarding():
    """Complete user onboarding and create first God"""
    from src.database_postgres import User, God, Regime, Strategist, PresetGod, PresetRegime, PresetStrategist
    import uuid
    from datetime import datetime
    
    data = request.json or {}
    
    god_preset = data.get('god_preset')  # zeus, athena, poseidon, ares, hephaestus
    trading_pairs = data.get('trading_pairs', ['BTC/USDT', 'ETH/USDT', 'BNB/USDT'])
    initial_capital = data.get('initial_capital', 1000)
    leverage = data.get('leverage', 50)
    paper_trading = data.get('paper_trading', True)
    chatgpt_validation = data.get('chatgpt_validation', True)
    
    if not god_preset:
        return jsonify({'error': 'God preset required'}), 400
    
    try:
        with _db.get_session() as session:
            # Mark onboarding as completed
            user = session.query(User).filter_by(id=g.user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            user.onboarding_completed = True
            
            # Store global risk settings
            user.global_risk_settings = {
                'leverage': leverage,
                'chatgpt_validation': chatgpt_validation,
                'paper_trading': paper_trading
            }
            user.updated_at = datetime.utcnow()
            
            # Find preset God
            preset_god = session.query(PresetGod).filter_by(name=god_preset.capitalize()).first()
            if not preset_god:
                return jsonify({'error': f'Preset god {god_preset} not found'}), 404
            
            # Create God based on preset
            god_id = str(uuid.uuid4())
            new_god = God(
                id=god_id,
                user_id=g.user_id,
                name=f"{preset_god.name} - {user.username}",
                description=preset_god.description,
                avatar=preset_god.avatar,
                preset_god_id=preset_god.id,
                spirit_name=preset_god.spirit_name,
                spirit_prompt=preset_god.spirit_prompt,
                capital_balance=initial_capital,
                initial_capital=initial_capital,
                is_paper_trading=paper_trading,
                leverage=leverage,
                status='inactive',
                trading_pairs=trading_pairs,
                created_at=datetime.utcnow()
            )
            session.add(new_god)
            
            # Get preset regime for this God's archetype
            preset_regime = session.query(PresetRegime).first()  # Get first available regime
            if preset_regime:
                regime_id = str(uuid.uuid4())
                new_regime = Regime(
                    id=regime_id,
                    god_id=god_id,
                    name=preset_regime.name,
                    description=preset_regime.description,
                    preset_regime_id=preset_regime.id,
                    detection_rules=preset_regime.detection_rules,
                    priority=0,
                    created_at=datetime.utcnow()
                )
                session.add(new_regime)
                
                # Add 2 default strategists (Sparta tier limit)
                preset_strategists = session.query(PresetStrategist).limit(2).all()
                for i, preset_strat in enumerate(preset_strategists):
                    new_strategist = Strategist(
                        id=str(uuid.uuid4()),
                        regime_id=regime_id,
                        user_id=g.user_id,
                        name=preset_strat.name,
                        description=preset_strat.description,
                        avatar=preset_strat.avatar,
                        preset_strategist_id=preset_strat.id,
                        is_custom=False,
                        system_prompt=preset_strat.system_prompt,
                        analysis_prompt_template=preset_strat.analysis_prompt_template,
                        confidence_threshold=preset_strat.confidence_threshold,
                        risk_level=preset_strat.risk_level,
                        analysis_cycle_minutes=preset_strat.analysis_cycle_minutes,
                        indicators=preset_strat.indicators,
                        timeframes=preset_strat.timeframes,
                        created_at=datetime.utcnow()
                    )
                    session.add(new_strategist)
            
            session.commit()
            
            logger.info(f"✅ User {g.user_id} completed onboarding, created God: {god_id}")
            
            return jsonify({
                'success': True,
                'god_id': god_id,
                'message': f'{preset_god.name} God created successfully!'
            }), 201
            
    except Exception as e:
        logger.error(f"Onboarding completion error: {e}", exc_info=True)
        return jsonify({'error': 'Failed to complete onboarding'}), 500


@arena_api_bp.route('/gods/status', methods=['GET'])
@require_auth
def get_gods_status():
    """Get all user's Gods with current status, positions, and P&L"""
    from src.database_postgres import God, GodPosition
    
    try:
        with _db.get_session() as session:
            gods = session.query(God).filter_by(user_id=g.user_id).all()
            
            gods_data = []
            for god in gods:
                # Get active positions count
                active_positions = session.query(GodPosition).filter_by(
                    god_id=god.id,
                    status='open'
                ).count()
                
                gods_data.append({
                    'id': god.id,
                    'name': god.name,
                    'avatar': god.avatar,
                    'status': god.status,
                    'capital_balance': god.capital_balance,
                    'initial_capital': god.initial_capital,
                    'realized_pnl': god.realized_pnl,
                    'unrealized_pnl': god.unrealized_pnl,
                    'total_trades': god.total_trades,
                    'winning_trades': god.winning_trades,
                    'losing_trades': god.losing_trades,
                    'current_regime': god.current_regime_id,
                    'active_positions': active_positions,
                    'trading_pairs': god.trading_pairs,
                    'is_paper_trading': god.is_paper_trading,
                    'leverage': god.leverage,
                    'last_analysis_at': god.last_analysis_at.isoformat() if god.last_analysis_at else None
                })
            
            return jsonify({'gods': gods_data}), 200
            
    except Exception as e:
        logger.error(f"Error getting gods status: {e}")
        return jsonify({'error': 'Failed to get gods status'}), 500


# ============================================================================
# GOD ROUTES
# ============================================================================

@arena_api_bp.route('/gods', methods=['GET'])
@require_auth
def list_gods():
    """List all gods for current user"""
    gods = _god_manager.load_user_gods(g.user_id)
    return jsonify({'gods': gods}), 200


@arena_api_bp.route('/gods', methods=['POST'])
@require_auth
def create_god():
    """Create a new god"""
    from src.database_postgres import God
    
    data = request.json or {}
    
    # Check tier limits
    limits = get_tier_limits(g.tier)
    
    with _db.get_session() as session:
        current_count = session.query(God).filter_by(user_id=g.user_id).count()
    
    allowed, message = check_tier_limit(g.tier, 'max_gods', current_count)
    if not allowed:
        return jsonify({'error': message, 'upgrade_url': '/subscribe'}), 403
    
    # Create god
    from_preset = data.get('preset_id')
    god_id = _god_manager.create_god(g.user_id, data, from_preset)
    
    if god_id:
        return jsonify({'success': True, 'god_id': god_id}), 201
    
    return jsonify({'error': 'Failed to create god'}), 500


@arena_api_bp.route('/gods/<god_id>', methods=['GET'])
@require_auth
def get_god(god_id):
    """Get god details"""
    context = _god_manager.get_god_context(god_id)
    if not context:
        return jsonify({'error': 'God not found'}), 404
    
    performance = context.get_performance(days=7)
    positions = context.get_open_positions()
    
    return jsonify({
        'god': {
            'id': god_id,
            'name': context.name,
            'avatar': context.avatar,
            'status': context.status,
            'capital_balance': context.capital_balance,
            'leverage': context.leverage,
            'is_paper_trading': context.is_paper_trading,
            'current_regime': context.current_regime_name,
            'spirit_name': context.spirit_name
        },
        'performance': performance,
        'open_positions': positions,
        'active_strategists': list(context.active_strategists.keys())
    }), 200


@arena_api_bp.route('/gods/<god_id>', methods=['DELETE'])
@require_auth
def delete_god(god_id):
    """Delete a god"""
    success = _god_manager.delete_god(god_id, g.user_id)
    if success:
        return jsonify({'success': True}), 200
    return jsonify({'error': 'Failed to delete god'}), 400


@arena_api_bp.route('/gods/<god_id>/regimes', methods=['GET'])
@require_auth
def get_god_regimes(god_id):
    """Get all regimes and strategists for a specific god"""
    from src.database_postgres import God, Regime, Strategist
    
    try:
        with _db.get_session() as session:
            god = session.query(God).filter_by(id=god_id, user_id=g.user_id).first()
            if not god:
                return jsonify({'error': 'God not found'}), 404
            
            regimes = session.query(Regime).filter_by(god_id=god_id).all()
            
            regimes_data = []
            for regime in regimes:
                strategists = session.query(Strategist).filter_by(regime_id=regime.id).all()
                
                regimes_data.append({
                    'id': regime.id,
                    'name': regime.name,
                    'description': regime.description,
                    'is_active': regime.id == god.current_regime_id,
                    'priority': regime.priority,
                    'strategists': [
                        {
                            'id': s.id,
                            'name': s.name,
                            'avatar': s.avatar,
                            'risk_level': s.risk_level,
                            'confidence_threshold': s.confidence_threshold,
                            'total_trades': s.total_trades,
                            'winning_trades': s.winning_trades,
                            'losing_trades': s.losing_trades
                        } for s in strategists
                    ]
                })
            
            return jsonify({'regimes': regimes_data}), 200
            
    except Exception as e:
        logger.error(f"Error getting god regimes: {e}")
        return jsonify({'error': 'Failed to get regimes'}), 500


@arena_api_bp.route('/gods/<god_id>/status', methods=['POST'])
@require_auth
def update_god_status(god_id):
    """Update god status (active/paused/inactive)"""
    from src.database_postgres import God
    from datetime import datetime
    
    data = request.json or {}
    new_status = data.get('status')
    
    if new_status not in ['active', 'paused', 'inactive']:
        return jsonify({'error': 'Invalid status. Must be active, paused, or inactive'}), 400
    
    try:
        with _db.get_session() as session:
            god = session.query(God).filter_by(id=god_id, user_id=g.user_id).first()
            if not god:
                return jsonify({'error': 'God not found'}), 404
            
            god.status = new_status
            god.updated_at = datetime.utcnow()
            session.commit()
            
            logger.info(f"God {god_id} status updated to {new_status}")
            
            return jsonify({
                'success': True,
                'god_id': god_id,
                'status': new_status
            }), 200
            
    except Exception as e:
        logger.error(f"Error updating god status: {e}")
        return jsonify({'error': 'Failed to update status'}), 500


@arena_api_bp.route('/gods/emergency-stop', methods=['POST'])
@require_auth
def emergency_stop_all_gods():
    """Emergency stop - pause all gods and close all positions"""
    from src.database_postgres import God, GodPosition
    from datetime import datetime
    
    try:
        with _db.get_session() as session:
            # Pause all active gods
            gods = session.query(God).filter_by(user_id=g.user_id, status='active').all()
            
            for god in gods:
                god.status = 'paused'
                god.updated_at = datetime.utcnow()
            
            # Close all open positions (simplified - in production would execute trades)
            positions = session.query(GodPosition).filter(
                GodPosition.god_id.in_([g.id for g in gods]),
                GodPosition.status == 'open'
            ).all()
            
            closed_count = len(positions)
            
            for position in positions:
                position.status = 'closed'
                position.exit_reason = 'emergency_stop'
                position.closed_at = datetime.utcnow()
            
            session.commit()
            
            logger.warning(f"⚠️ Emergency stop activated by user {g.user_id}: {len(gods)} gods paused, {closed_count} positions closed")
            
            return jsonify({
                'success': True,
                'gods_paused': len(gods),
                'positions_closed': closed_count
            }), 200
            
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        return jsonify({'error': 'Emergency stop failed'}), 500


@arena_api_bp.route('/gods/<god_id>/start', methods=['POST'])
@require_auth
def start_god(god_id):
    """Start a god (begin trading)"""
    success = _god_manager.start_god(god_id)
    if success:
        return jsonify({'success': True, 'status': 'active'}), 200
    return jsonify({'error': 'Failed to start god'}), 400


@arena_api_bp.route('/gods/<god_id>/stop', methods=['POST'])
@require_auth
def stop_god(god_id):
    """Stop a god (pause trading)"""
    success = _god_manager.stop_god(god_id)
    if success:
        return jsonify({'success': True, 'status': 'inactive'}), 200
    return jsonify({'error': 'Failed to stop god'}), 400


@arena_api_bp.route('/gods/<god_id>/performance', methods=['GET'])
@require_auth
def get_god_performance(god_id):
    """Get god performance metrics"""
    days = request.args.get('days', 7, type=int)
    performance = _god_manager.get_god_performance(god_id, days)
    
    if performance:
        return jsonify(performance), 200
    return jsonify({'error': 'God not found'}), 404


@arena_api_bp.route('/gods/<god_id>/positions', methods=['GET'])
@require_auth
def get_god_positions(god_id):
    """Get god's open positions"""
    context = _god_manager.get_god_context(god_id)
    if not context:
        return jsonify({'error': 'God not found'}), 404
    
    positions = context.get_open_positions()
    return jsonify({'positions': positions}), 200


@arena_api_bp.route('/gods/<god_id>/positions/<position_id>/close', methods=['POST'])
@require_auth
def close_god_position(god_id, position_id):
    """Close a god's position"""
    data = request.json or {}
    exit_price = data.get('exit_price')
    
    if not exit_price:
        return jsonify({'error': 'exit_price required'}), 400
    
    context = _god_manager.get_god_context(god_id)
    if not context:
        return jsonify({'error': 'God not found'}), 404
    
    result = context.close_position(position_id, exit_price, 'manual')
    
    if result.get('success'):
        return jsonify(result), 200
    return jsonify(result), 400


# ============================================================================
# REGIME ROUTES
# ============================================================================

@arena_api_bp.route('/gods/<god_id>/regimes', methods=['GET'])
@require_auth
def list_regimes(god_id):
    """List regimes for a god"""
    from src.database_postgres import Regime
    
    try:
        with _db.get_session() as session:
            regimes = session.query(Regime).filter_by(god_id=god_id).all()
            
            return jsonify({
                'regimes': [{
                    'id': r.id,
                    'name': r.name,
                    'description': r.description,
                    'detection_rules': r.detection_rules,
                    'is_active': r.is_active,
                    'times_activated': r.times_activated,
                    'total_pnl': r.total_pnl_in_regime
                } for r in regimes]
            }), 200
            
    except Exception as e:
        logger.error(f"Error listing regimes: {e}")
        return jsonify({'error': str(e)}), 500


@arena_api_bp.route('/gods/<god_id>/regimes', methods=['POST'])
@require_auth
def create_regime(god_id):
    """Create a new regime for a god"""
    from src.database_postgres import Regime, God
    
    data = request.json or {}
    
    # Check tier limits
    limits = get_tier_limits(g.tier)
    
    with _db.get_session() as session:
        # Verify god belongs to user
        god = session.query(God).filter_by(id=god_id, user_id=g.user_id).first()
        if not god:
            return jsonify({'error': 'God not found'}), 404
        
        # Check regime limit
        current_count = session.query(Regime).filter_by(god_id=god_id).count()
        
        if current_count >= limits['max_regimes_per_god']:
            return jsonify({
                'error': f"Regime limit reached ({current_count}/{limits['max_regimes_per_god']})",
                'upgrade_url': '/subscribe'
            }), 403
        
        # Create regime
        regime_id = str(uuid.uuid4())
        regime = Regime(
            id=regime_id,
            god_id=god_id,
            name=data.get('name', 'New Regime'),
            description=data.get('description'),
            detection_rules=data.get('detection_rules', {}),
            preset_regime_id=data.get('preset_id'),
            priority=data.get('priority', 0),
            is_active=True
        )
        session.add(regime)
    
    return jsonify({'success': True, 'regime_id': regime_id}), 201


# ============================================================================
# STRATEGIST ROUTES
# ============================================================================

@arena_api_bp.route('/regimes/<regime_id>/strategists', methods=['GET'])
@require_auth
def list_strategists(regime_id):
    """List strategists for a regime"""
    from src.database_postgres import Strategist
    
    try:
        with _db.get_session() as session:
            strategists = session.query(Strategist).filter_by(regime_id=regime_id).all()
            
            return jsonify({
                'strategists': [{
                    'id': s.id,
                    'name': s.name,
                    'description': s.description,
                    'avatar': s.avatar,
                    'is_custom': s.is_custom,
                    'confidence_threshold': s.confidence_threshold,
                    'risk_level': s.risk_level,
                    'analysis_cycle_minutes': s.analysis_cycle_minutes,
                    'indicators': s.indicators,
                    'status': s.status,
                    'total_pnl': s.total_pnl,
                    'total_trades': s.total_trades,
                    'estimated_monthly_cost': s.estimated_monthly_cost
                } for s in strategists]
            }), 200
            
    except Exception as e:
        logger.error(f"Error listing strategists: {e}")
        return jsonify({'error': str(e)}), 500


@arena_api_bp.route('/regimes/<regime_id>/strategists', methods=['POST'])
@require_auth
def create_strategist(regime_id):
    """Create a new strategist for a regime"""
    from src.database_postgres import Strategist, Regime, God
    
    data = request.json or {}
    is_custom = data.get('is_custom', False)
    
    # Check tier limits
    limits = get_tier_limits(g.tier)
    
    # Custom strategists require Titan or higher
    if is_custom and not limits['custom_strategists']:
        return jsonify({
            'error': 'Custom strategists require Titan or Kratos subscription',
            'upgrade_url': '/subscribe'
        }), 403
    
    with _db.get_session() as session:
        # Get regime and verify ownership
        regime = session.query(Regime).filter_by(id=regime_id).first()
        if not regime:
            return jsonify({'error': 'Regime not found'}), 404
        
        god = session.query(God).filter_by(id=regime.god_id, user_id=g.user_id).first()
        if not god:
            return jsonify({'error': 'Access denied'}), 403
        
        # Check strategist limit
        current_count = session.query(Strategist).filter_by(regime_id=regime_id).count()
        
        if current_count >= limits['max_strategists_per_regime']:
            return jsonify({
                'error': f"Strategist limit reached ({current_count}/{limits['max_strategists_per_regime']})",
                'upgrade_url': '/subscribe'
            }), 403
        
        # Calculate cost for custom strategist
        estimated_cost = 0
        if is_custom:
            cost_estimate = _cost_calculator.estimate_monthly_cost({
                'analysis_cycle_minutes': data.get('analysis_cycle_minutes', 30),
                'indicators': data.get('indicators', {}),
                'timeframes': data.get('timeframes', ['15m', '1h', '4h']),
                'chatgpt_validation': data.get('chatgpt_validation', False),
                'trading_pairs': 1
            })
            estimated_cost = cost_estimate['final_cost_monthly']
        
        # Create strategist
        strategist_id = str(uuid.uuid4())
        strategist = Strategist(
            id=strategist_id,
            regime_id=regime_id,
            user_id=g.user_id,
            name=data.get('name', 'New Strategist'),
            description=data.get('description'),
            avatar=data.get('avatar', '🤖'),
            preset_strategist_id=data.get('preset_id'),
            is_custom=is_custom,
            system_prompt=data.get('system_prompt', ''),
            analysis_prompt_template=data.get('analysis_prompt_template', ''),
            confidence_threshold=data.get('confidence_threshold', 60),
            risk_level=data.get('risk_level', 'medium'),
            analysis_cycle_minutes=data.get('analysis_cycle_minutes', 30),
            indicators=data.get('indicators', {}),
            timeframes=data.get('timeframes', ['15m', '1h', '4h']),
            estimated_monthly_cost=estimated_cost,
            is_active=True,
            status='inactive'
        )
        session.add(strategist)
        
        # Create cost record for custom strategist
        if is_custom:
            _cost_calculator.create_cost_record(strategist_id, cost_estimate)
    
    return jsonify({
        'success': True,
        'strategist_id': strategist_id,
        'estimated_monthly_cost': estimated_cost
    }), 201


@arena_api_bp.route('/strategists/<strategist_id>/estimate-cost', methods=['POST'])
@require_auth
def estimate_strategist_cost(strategist_id):
    """Estimate cost for a strategist configuration"""
    data = request.json or {}
    
    cost_estimate = _cost_calculator.estimate_monthly_cost(data)
    
    return jsonify(cost_estimate), 200


# ============================================================================
# PRESET ROUTES
# ============================================================================

@arena_api_bp.route('/presets/gods', methods=['GET'])
def list_preset_gods():
    """List available preset gods"""
    from src.database_postgres import PresetGod
    
    try:
        with _db.get_session() as session:
            presets = session.query(PresetGod).filter_by(is_active=True).all()
            
            return jsonify({
                'preset_gods': [{
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'avatar': p.avatar,
                    'spirit_name': p.spirit_name,
                    'risk_profile': p.risk_profile,
                    'recommended_capital': p.recommended_capital,
                    'default_config': p.default_config
                } for p in presets]
            }), 200
            
    except Exception as e:
        logger.error(f"Error listing preset gods: {e}")
        return jsonify({'preset_gods': []}), 200


@arena_api_bp.route('/presets/regimes', methods=['GET'])
def list_preset_regimes():
    """List available preset regimes"""
    from src.database_postgres import PresetRegime
    
    try:
        with _db.get_session() as session:
            presets = session.query(PresetRegime).filter_by(is_active=True).all()
            
            return jsonify({
                'preset_regimes': [{
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'detection_rules': p.detection_rules,
                    'recommended_strategists': p.recommended_strategists
                } for p in presets]
            }), 200
            
    except Exception as e:
        logger.error(f"Error listing preset regimes: {e}")
        return jsonify({'preset_regimes': []}), 200


@arena_api_bp.route('/presets/strategists', methods=['GET'])
def list_preset_strategists():
    """List available preset strategists"""
    from src.database_postgres import PresetStrategist
    
    try:
        with _db.get_session() as session:
            presets = session.query(PresetStrategist).filter_by(is_active=True).all()
            
            return jsonify({
                'preset_strategists': [{
                    'id': p.id,
                    'name': p.name,
                    'description': p.description,
                    'avatar': p.avatar,
                    'confidence_threshold': p.confidence_threshold,
                    'risk_level': p.risk_level,
                    'analysis_cycle_minutes': p.analysis_cycle_minutes,
                    'indicators': p.indicators,
                    'timeframes': p.timeframes,
                    'best_regimes': p.best_regimes
                } for p in presets]
            }), 200
            
    except Exception as e:
        logger.error(f"Error listing preset strategists: {e}")
        return jsonify({'preset_strategists': []}), 200


# ============================================================================
# EXCHANGE ROUTES
# ============================================================================

@arena_api_bp.route('/exchanges', methods=['GET'])
def list_exchanges():
    """List supported exchanges"""
    exchanges = get_exchange_info()
    return jsonify({'exchanges': exchanges}), 200


@arena_api_bp.route('/user/exchanges', methods=['GET'])
@require_auth
def list_user_exchanges():
    """List user's connected exchanges"""
    from src.database_postgres import UserExchange
    
    try:
        with _db.get_session() as session:
            exchanges = session.query(UserExchange).filter_by(
                user_id=g.user_id
            ).all()
            
            return jsonify({
                'exchanges': [{
                    'id': e.id,
                    'exchange_name': e.exchange_name,
                    'is_active': e.is_active,
                    'is_verified': e.is_verified,
                    'last_verified_at': e.last_verified_at.isoformat() if e.last_verified_at else None,
                    'can_trade': e.can_trade,
                    'connection_error': e.connection_error
                } for e in exchanges]
            }), 200
            
    except Exception as e:
        logger.error(f"Error listing user exchanges: {e}")
        return jsonify({'exchanges': []}), 200


@arena_api_bp.route('/user/exchanges', methods=['POST'])
@require_auth
@require_tier('titan', 'kratos')  # Real trading requires paid tier
def connect_exchange():
    """Connect a new exchange"""
    from src.database_postgres import UserExchange
    
    data = request.json or {}
    
    exchange_name = data.get('exchange_name', '').lower()
    api_key = data.get('api_key', '')
    api_secret = data.get('api_secret', '')
    passphrase = data.get('passphrase', '')  # For OKX
    
    if exchange_name not in SUPPORTED_EXCHANGES:
        return jsonify({
            'error': f'Unsupported exchange. Supported: {SUPPORTED_EXCHANGES}'
        }), 400
    
    if not api_key or not api_secret:
        return jsonify({'error': 'API key and secret required'}), 400
    
    try:
        # Test connection first
        adapter = create_adapter(exchange_name, api_key, api_secret, passphrase)
        test_result = adapter.test_connection()
        
        if not test_result.get('success'):
            return jsonify({
                'error': f"Connection failed: {test_result.get('error')}",
                'details': test_result
            }), 400
        
        # Encrypt credentials
        encryptor = get_encryptor()
        
        exchange_id = str(uuid.uuid4())
        
        with _db.get_session() as session:
            user_exchange = UserExchange(
                id=exchange_id,
                user_id=g.user_id,
                exchange_name=exchange_name,
                api_key_encrypted=encryptor.encrypt(api_key),
                api_secret_encrypted=encryptor.encrypt(api_secret),
                passphrase_encrypted=encryptor.encrypt(passphrase) if passphrase else None,
                is_active=True,
                is_verified=True,
                last_verified_at=datetime.utcnow(),
                can_trade=test_result.get('can_trade', False)
            )
            session.add(user_exchange)
        
        return jsonify({
            'success': True,
            'exchange_id': exchange_id,
            'balance': test_result.get('balance')
        }), 201
        
    except Exception as e:
        logger.error(f"Exchange connection error: {e}")
        return jsonify({'error': str(e)}), 500


@arena_api_bp.route('/user/exchanges/<exchange_id>/test', methods=['POST'])
@require_auth
def test_exchange(exchange_id):
    """Test exchange connection"""
    from src.database_postgres import UserExchange
    from src.exchange_adapters import create_adapter_from_db
    
    try:
        with _db.get_session() as session:
            exchange = session.query(UserExchange).filter_by(
                id=exchange_id, user_id=g.user_id
            ).first()
            
            if not exchange:
                return jsonify({'error': 'Exchange not found'}), 404
            
            # Test connection
            adapter = create_adapter_from_db({
                'exchange_name': exchange.exchange_name,
                'api_key_encrypted': exchange.api_key_encrypted,
                'api_secret_encrypted': exchange.api_secret_encrypted,
                'passphrase_encrypted': exchange.passphrase_encrypted
            })
            
            result = adapter.test_connection()
            
            # Update verification status
            exchange.is_verified = result.get('success', False)
            exchange.last_verified_at = datetime.utcnow()
            exchange.connection_error = result.get('error') if not result.get('success') else None
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Exchange test error: {e}")
        return jsonify({'error': str(e)}), 500


@arena_api_bp.route('/user/exchanges/<exchange_id>', methods=['DELETE'])
@require_auth
def delete_exchange(exchange_id):
    """Delete/disconnect an exchange"""
    from src.database_postgres import UserExchange
    
    try:
        with _db.get_session() as session:
            exchange = session.query(UserExchange).filter_by(
                id=exchange_id, user_id=g.user_id
            ).first()
            
            if not exchange:
                return jsonify({'error': 'Exchange not found'}), 404
            
            session.delete(exchange)
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"Exchange deletion error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# SUBSCRIPTION ROUTES (Stripe sandbox)
# ============================================================================

@arena_api_bp.route('/subscribe/tiers', methods=['GET'])
def get_subscription_tiers():
    """Get available subscription tiers"""
    from src.auth import TIER_LIMITS
    
    return jsonify({
        'tiers': [
            {
                'id': 'sparta',
                'name': '🛡️ Sparta',
                'description': 'Free tier - Start your journey',
                'price_monthly': 0,
                'limits': TIER_LIMITS['sparta']
            },
            {
                'id': 'titan',
                'name': '⚔️ Titan',
                'description': 'Pro tier - Real trading unlocked',
                'price_monthly': 29.99,
                'limits': TIER_LIMITS['titan']
            },
            {
                'id': 'kratos',
                'name': '🔱 Kratos',
                'description': 'Elite tier - Maximum power',
                'price_monthly': 99.99,
                'limits': TIER_LIMITS['kratos']
            }
        ]
    }), 200


@arena_api_bp.route('/subscribe/<tier>', methods=['POST'])
@require_auth
def subscribe(tier):
    """Subscribe to a tier (Stripe sandbox)"""
    # This will be implemented with Stripe integration
    # For now, return sandbox response
    
    if tier not in ['titan', 'kratos']:
        return jsonify({'error': 'Invalid tier'}), 400
    
    return jsonify({
        'message': 'Stripe integration pending',
        'tier': tier,
        'sandbox_mode': True,
        'stripe_checkout_url': None  # Will be Stripe checkout URL
    }), 200


# ============================================================================
# LEADERBOARD ROUTES
# ============================================================================

@arena_api_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get global leaderboard"""
    from src.database_postgres import Leaderboard, User
    
    period = request.args.get('period', 'weekly')  # daily, weekly, monthly
    limit = request.args.get('limit', 50, type=int)
    
    try:
        with _db.get_session() as session:
            # Get leaderboard entries
            entries = session.query(Leaderboard, User).join(
                User, Leaderboard.user_id == User.id
            ).filter(
                Leaderboard.leaderboard_type == f'global_{period}'
            ).order_by(
                Leaderboard.rank.asc()
            ).limit(limit).all()
            
            return jsonify({
                'period': period,
                'leaderboard': [{
                    'rank': entry.Leaderboard.rank,
                    'username': entry.User.username,
                    'display_name': entry.User.display_name,
                    'avatar_url': entry.User.avatar_url,
                    'tier': entry.User.subscription_tier,
                    'pnl': entry.Leaderboard.pnl,
                    'pnl_percent': entry.Leaderboard.pnl_percent,
                    'win_rate': entry.Leaderboard.win_rate,
                    'total_trades': entry.Leaderboard.total_trades
                } for entry in entries]
            }), 200
            
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({'leaderboard': []}), 200


# ============================================================================
# HEALTH CHECK
# ============================================================================

@arena_api_bp.route('/health', methods=['GET'])
def health_check():
    """API health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    }), 200

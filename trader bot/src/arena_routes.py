"""
SmartPal Arena - Web Routes
Flask routes for Arena pages and Stripe webhooks
"""

import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for

logger = logging.getLogger(__name__)

# Create Blueprint - templates are in templates_arena folder (not arena subfolder)
arena_routes_bp = Blueprint('arena_routes', __name__, template_folder='../templates_arena')

# Lazy initialization - don't connect to database at import time
_db = None
_stripe_handler = None
_stripe_publishable_key = None

def get_db():
    """Lazy database initialization"""
    global _db
    if _db is None:
        from src.database_postgres import TradingDatabase
        _db = TradingDatabase()
    return _db

def get_stripe_handler():
    """Lazy Stripe handler initialization"""
    global _stripe_handler
    if _stripe_handler is None:
        from src.stripe_handler import StripeHandler
        _stripe_handler = StripeHandler(get_db())
    return _stripe_handler

def get_stripe_publishable_key():
    """Get Stripe publishable key"""
    global _stripe_publishable_key
    if _stripe_publishable_key is None:
        from src.stripe_handler import STRIPE_PUBLISHABLE_KEY
        _stripe_publishable_key = STRIPE_PUBLISHABLE_KEY
    return _stripe_publishable_key


# ============================================================================
# PUBLIC PAGES
# ============================================================================

@arena_routes_bp.route('/')
def landing():
    """Arena landing page"""
    return render_template('landing.html')


@arena_routes_bp.route('/login')
def login_page():
    """Login page"""
    return render_template('login.html')


@arena_routes_bp.route('/register')
def register_page():
    """Registration page"""
    return render_template('register.html')


# ============================================================================
# AUTHENTICATED PAGES
# ============================================================================

@arena_routes_bp.route('/onboarding')
def onboarding():
    """Onboarding wizard for new users"""
    return render_template('onboarding.html')


@arena_routes_bp.route('/god-control')
def god_control():
    """Main God control dashboard"""
    return render_template('god_control.html')


@arena_routes_bp.route('/settings/environment')
def settings_environment():
    """Environment settings page"""
    return render_template('settings_environment.html')


@arena_routes_bp.route('/dashboard')
def dashboard():
    """Main Arena dashboard"""
    return render_template('dashboard.html')


@arena_routes_bp.route('/gods')
def gods_page():
    """Gods management page"""
    return render_template('gods.html')


@arena_routes_bp.route('/gods/create')
def create_god_page():
    """God builder page"""
    return render_template('god_builder.html')


@arena_routes_bp.route('/gods/<god_id>')
def god_detail_page(god_id):
    """God detail/edit page"""
    return render_template('god_detail.html', god_id=god_id)


@arena_routes_bp.route('/strategists')
def strategists_page():
    """Strategists management page"""
    return render_template('strategists.html')


@arena_routes_bp.route('/strategists/create')
def create_strategist_page():
    """Strategist builder page"""
    return render_template('strategist_builder.html')


@arena_routes_bp.route('/strategists/<strategist_id>')
def strategist_detail_page(strategist_id):
    """Strategist detail page"""
    return render_template('strategist_detail.html', strategist_id=strategist_id)


@arena_routes_bp.route('/profile')
def profile_page():
    """User profile page"""
    return render_template('profile.html')


@arena_routes_bp.route('/subscription')
def subscription_page():
    """Subscription management page"""
    return render_template('subscription.html',
                          stripe_key=get_stripe_publishable_key())


@arena_routes_bp.route('/leaderboard')
def leaderboard_page():
    """Arena leaderboard page"""
    return render_template('leaderboard.html')


@arena_routes_bp.route('/training')
def training_page():
    """Training mode page (paper trading)"""
    return render_template('training.html')


# ============================================================================
# STRIPE INTEGRATION
# ============================================================================

@arena_routes_bp.route('/checkout/<tier>')
def checkout(tier):
    """Redirect to Stripe checkout"""
    from flask import session
    
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('arena.login_page'))
    
    if tier not in ['titan', 'kratos']:
        return redirect(url_for('arena.subscription_page'))
    
    success_url = request.host_url + 'arena/subscription/success'
    cancel_url = request.host_url + 'arena/subscription'
    
    result = get_stripe_handler().create_checkout_session(
        user_id=user_id,
        tier=tier,
        success_url=success_url,
        cancel_url=cancel_url
    )
    
    if result['success']:
        return redirect(result['checkout_url'])
    else:
        return redirect(url_for('arena.subscription_page'))


@arena_routes_bp.route('/subscription/success')
def subscription_success():
    """Handle successful subscription"""
    session_id = request.args.get('session_id')
    
    if session_id:
        result = get_stripe_handler().verify_checkout_session(session_id)
        if result['success']:
            return render_template('subscription_success.html',
                                  tier=result.get('metadata', {}).get('tier'))
    
    return redirect(url_for('arena.subscription_page'))


@arena_routes_bp.route('/billing-portal')
def billing_portal():
    """Redirect to Stripe billing portal"""
    from flask import session
    
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('arena.login_page'))
    
    return_url = request.host_url + 'arena/subscription'
    
    result = get_stripe_handler().create_billing_portal_session(
        user_id=user_id,
        return_url=return_url
    )
    
    if result['success']:
        return redirect(result['portal_url'])
    else:
        return redirect(url_for('arena.subscription_page'))


@arena_routes_bp.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events"""
    payload = request.get_data()
    signature = request.headers.get('Stripe-Signature')
    
    result = get_stripe_handler().handle_webhook(payload, signature)
    
    if result['success']:
        return jsonify({'status': 'success'}), 200
    else:
        logger.error(f"Webhook error: {result.get('error')}")
        return jsonify({'error': result.get('error')}), 400


# ============================================================================
# API ENDPOINTS (for AJAX calls from templates)
# ============================================================================

@arena_routes_bp.route('/api/subscription/cancel', methods=['POST'])
def api_cancel_subscription():
    """Cancel subscription"""
    from flask import session
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    immediately = data.get('immediately', False)
    
    result = get_stripe_handler().cancel_subscription(user_id, immediately)
    return jsonify(result)


@arena_routes_bp.route('/api/subscription/upgrade', methods=['POST'])
def api_upgrade_subscription():
    """Upgrade subscription tier"""
    from flask import session
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    new_tier = data.get('tier')
    
    if not new_tier:
        return jsonify({'success': False, 'error': 'Tier required'}), 400
    
    result = get_stripe_handler().upgrade_subscription(user_id, new_tier)
    return jsonify(result)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def register_arena_routes(app):
    """Register Arena blueprint with Flask app"""
    app.register_blueprint(arena_bp, url_prefix='/arena')
    logger.info("✅ Arena routes registered at /arena")

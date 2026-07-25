#!/usr/bin/env python3
import os
import logging
import string
import random
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask import Response

# Fix shared module imports
try:
    import sys
    # Add parent directory to sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from shared.config import (
        SECRET_KEY, SESSION_SECRET, WEB_HOST, WEB_PORT, WEB_DEBUG,
        validate_config, ADMIN_ID, COMMISSION_RATE, LOG_LEVEL
    )
    from shared.database import db
    from shared.database.disputes import dispute_manager
    from shared.payments import system_wallet_checkout, payment_processor
    from shared.localization import localization
    from shared.service_manager import service_manager
    from shared.health_checks import health_endpoint, detailed_health_endpoint, start_health_monitoring
    from shared.correlation_middleware import init_correlation_middleware
    from shared.url_utils import get_deal_url
    from shared.logging_system import setup_logging
    from shared import utils as shared_utils

    from web.utils import response_utils, escape_html

    try:
        setup_logging(log_level=LOG_LEVEL, log_dir=os.getenv("LOG_DIR", "logs"), service_name="web")
    except Exception as log_init_error:
        print(f"[WARNING] Failed to initialize file logging: {log_init_error}")
    print("[OK] All shared modules imported successfully")
except ImportError as e:
    print(f"[ERROR] Failed to import shared modules: {e}")
    print("[INFO] Running in diagnostic mode...")
    # Diagnostic fallback
    SECRET_KEY = 'fallback_secret_key_12345'
    SESSION_SECRET = 'fallback_session_secret_12345'
    WEB_HOST = '0.0.0.0'
    WEB_PORT = 8443
    WEB_DEBUG = True
    ADMIN_ID = 7666768819
    COMMISSION_RATE = 0.05
    LOG_LEVEL = "INFO"

    # Create stubs for missing modules
    class MockDB:
        def get_user(self, user_id): return None
        def get_deal(self, deal_code): return None
        def create_user(self, *args): return True
        def update_user(self, *args): return True
        def get_user_language(self, user_id): return 'en'
        def validate_auth_token(self, token): return None
        def get_system_wallet_checkout(self, checkout_id): return None
        def update_checkout_status(self, *args): return True
        def get_settings(self): return {'commission_rate': 0.05}
        def get_user_stats(self, user_id): return {'total_deals': 0, 'completed_deals': 0, 'active_deals': 0, 'total_volume': 0, 'success_rate': 0}
        def get_all_users(self, **kwargs): return []
        def get_users_count(self, **kwargs): return 0
        def ban_user(self, user_id, ban): return True
        def get_admin_messages_history(self, **kwargs): return []
        def save_admin_message(self, *args): return True
        def get_all_deals(self, **kwargs): return []
        def get_deals_count(self, **kwargs): return 0
        def get_user_deals(self, user_id): return []
        def get_user_notifications(self, user_id): return []
        def mark_notification_read(self, *args): return True
        def mark_all_notifications_read(self, user_id): return 0
        def delete_all_notifications(self, user_id): return 0
        def delete_multiple_notifications(self, user_id, ids): return 0
        def get_unread_notifications_count(self, user_id): return 0
        def create_deal(self, *args): return True
        def join_deal(self, *args): return True
        def update_deal_status(self, *args): return True
        def set_user_language(self, user_id, lang): return True
        def save_support_message(self, *args): return True
        def get_support_messages(self, user_id): return []
        def get_unread_support_messages_count(self, *args): return 0
        def mark_support_messages_read(self, *args): return True
        def get_all_support_conversations(self): return []
        def get_admin_analytics(self, period): return {}
        def get_stats(self): return {
            'users_count': 0,
            'deals_count': 0,
            'active_deals': 0,
            'completed_deals': 0,
            'total_volume': 0
        }

    class MockLocalization:
        def __init__(self):
            self.languages = ['en', 'ua']
            self.default_language = 'en'

        def get_text(self, key, language='en', **kwargs):
            return f"[{key}]"

    db = MockDB()
    localization = MockLocalization()

    class MockSharedUtils:
        @staticmethod
        def map_qr_code_path(qr_code_path, qr_code_url=None):
            return qr_code_url or ""

    shared_utils = MockSharedUtils()

    # Payment stubs
    class MockSystemWalletCheckout:
        def get_checkout(self, checkout_id): return None
        def check_payment_status(self, checkout_id): return False, "Mock payment"

    class MockPaymentProcessor:
        def process_deal_payment(self, **kwargs): return None

    system_wallet_checkout = MockSystemWalletCheckout()
    payment_processor = MockPaymentProcessor()

    # Stub for service manager
    class MockServiceManager:
        def is_service_enabled(self, service_key): return True
        def get_maintenance_message(self, service_key): return ""
        def get_all_services(self): return []
        def get_enabled_services(self): return []

    service_manager = MockServiceManager()

    # Stub for validate_config
    def validate_config():
        print("[OK] Configuration validated (mock)")
        return True

    def get_deal_url(deal_code, base_url=None):
        return url_for('deal_detail', deal_code=deal_code, _external=True)

    def escape_html(text):
        """Safe HTML escaping (diagnostic fallback)."""
        if not text:
            return ""
        import html as _html
        return _html.escape(str(text), quote=True).replace("'", "&#x27;")

# Logging setup
logger = logging.getLogger(__name__)

# Initialize avatar system for web app
try:
    from shared.avatar import ensure_avatars_directory
    avatars_dir = ensure_avatars_directory()
    logger.info(f"Avatar system initialized. Avatars directory: {avatars_dir}")
except Exception as e:
    logger.error(f"Failed to initialize avatar system: {e}")

# NOTE: Removed premature app.secret_key assignment that was causing 'app is not defined' error
# The Flask app is created later (lines 127-129) and secret_key is properly set there (line 131)

# Flask application creation with absolute path resolution
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            static_folder=os.path.join(_base_dir, 'static'),
            template_folder=os.path.join(_base_dir, 'templates'))

app.secret_key = SECRET_KEY
app.config['STATIC_VERSION'] = os.getenv("STATIC_VERSION") or str(int(time.time()))

# If the public URL is HTTPS (typical behind Cloudflare), mark session cookies as Secure.
# This improves cookie persistence in modern mobile WebViews/browsers.
_public_base_url = os.getenv("PUBLIC_BASE_URL") or os.getenv("BASE_URL") or ""
_public_scheme = ""
_public_host = ""
try:
    _parsed_public = urlparse(_public_base_url)
    _public_scheme = (_parsed_public.scheme or "").lower()
    _public_host = (_parsed_public.hostname or "")
except Exception:
    _public_scheme = ""
    _public_host = ""
app.config['SESSION_COOKIE_SECURE'] = (_public_scheme == "https")
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Telegram Android WebView / in-app browsers can behave like a third-party context for cookies.
# Using SameSite=None (with Secure) improves session persistence for those clients.
if app.config['SESSION_COOKIE_SECURE']:
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
else:
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Keep cookie scoped to the public hostname (helps if app is behind proxies/CDN).
if _public_host:
    app.config['SESSION_COOKIE_DOMAIN'] = _public_host
# Simplified session configuration
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Honor reverse-proxy headers (Cloudflare / Nginx) so Flask sees correct scheme/host.
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
except Exception as _proxyfix_error:
    # Not fatal; app will still run without proxy header normalization.
    pass

@app.after_request
def _consume_pending_auth_token(response):
    """Consume one-time auth tokens only after the browser has a session cookie.

    This prevents Telegram link previews/prefetchers from burning one-time tokens.
    """
    try:
        if request.endpoint == "auth_token":
            return response

        pending_token = session.get("_pending_auth_token")
        pending_user_id = session.get("_pending_auth_token_user_id")
        current_user_id = session.get("user_id")
        if not pending_token or not pending_user_id or not current_user_id:
            return response

        try:
            if int(pending_user_id) != int(current_user_id):
                return response
        except Exception:
            return response

        try:
            consumed = bool(getattr(db, "consume_auth_token")(pending_token))
            if consumed:
                logger.info("AUTH: Consumed pending token for user %s", current_user_id)
            else:
                logger.warning("AUTH: Pending token not consumed (already used or missing)")
        except Exception as consume_error:
            logger.warning("AUTH: Failed to consume pending token: %s", consume_error, exc_info=True)
        finally:
            session.pop("_pending_auth_token", None)
            session.pop("_pending_auth_token_user_id", None)
            session.modified = True

    except Exception as e:
        logger.warning("AUTH: after_request token consume error: %s", e, exc_info=True)
    return response

# Initialize correlation middleware
try:
    init_correlation_middleware(app)
    logger.info("Correlation middleware initialized")
except Exception as e:
    logger.warning(f"Failed to initialize correlation middleware: {e}")

# CRITICAL FIX: Ensure session is properly configured for Flask
# Use Flask-Session for better session management
try:
    from flask_session import Session
    app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem-based sessions
    app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'sessions')
    app.config['SESSION_FILE_THRESHOLD'] = 100
    app.config['SESSION_FILE_MODE'] = 0o600
    # Ensure sessions directory exists
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    Session(app)
    print("[OK] Flask-Session initialized successfully")
    logger.info("Flask-Session initialized with filesystem storage")
except ImportError:
    print("[WARNING] Flask-Session not available, using default Flask sessions")
    # Fallback to basic Flask sessions
    app.config['SESSION_TYPE'] = None
    logger.warning("Flask-Session not available, falling back to default Flask sessions")

# CSRF Protection (simplified without Flask-Session)
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = SECRET_KEY

def generate_deal_code() -> str:
    """Generate a deal code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(8))

def is_user_admin() -> bool:
    """Check if current user is admin"""
    user_id = session.get('user_id')
    return user_id is not None and int(user_id) == ADMIN_ID

def _get_admin_payment_sim_counters() -> dict:
    """Session-backed counters for admin payment simulation (checkout_id -> refresh count)."""
    counters = session.get('_admin_payment_sim_counters')
    if not isinstance(counters, dict):
        counters = {}
    # Ensure values are ints (session may deserialize unexpected types)
    cleaned: dict = {}
    for key, value in counters.items():
        try:
            cleaned[str(key)] = int(value)
        except Exception:
            continue
    if cleaned != counters:
        session['_admin_payment_sim_counters'] = cleaned
    return cleaned

def _admin_payment_sim_increment(checkout_id: str) -> int:
    counters = _get_admin_payment_sim_counters()
    checkout_id = str(checkout_id)
    counters[checkout_id] = int(counters.get(checkout_id, 0)) + 1
    session['_admin_payment_sim_counters'] = counters
    return counters[checkout_id]

def _admin_payment_sim_get(checkout_id: str) -> int:
    counters = _get_admin_payment_sim_counters()
    return int(counters.get(str(checkout_id), 0))

def _admin_payment_sim_clear(checkout_id: str) -> None:
    counters = _get_admin_payment_sim_counters()
    checkout_id = str(checkout_id)
    if checkout_id in counters:
        counters.pop(checkout_id, None)
        session['_admin_payment_sim_counters'] = counters

def is_mobile_device() -> bool:
    """Check if request is from mobile device"""
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone']

    # Check for mobile user agents
    if any(keyword in user_agent for keyword in mobile_keywords):
        return True

    # Check for Telegram Web App
    if request.headers.get('Telegram-Web-App', '').lower() == 'true':
        return True

    return False

def is_telegram_webview() -> bool:
    """Best-effort detection of Telegram in-app browser/WebView."""
    # Telegram Android WebView user-agent is often just Chrome/WebView and may not contain "Telegram".
    ua = (request.headers.get('User-Agent', '') or '').lower()

    if 'telegram' in ua:
        return True

    if request.headers.get('Telegram-Web-App', '').lower() == 'true':
        return True

    # Telegram Android in-app browser often sets this header.
    # Example: X-Requested-With: org.telegram.messenger
    try:
        xrw = (request.headers.get('X-Requested-With', '') or '').lower()
        if 'telegram' in xrw or xrw.startswith('org.telegram'):
            return True
    except Exception:
        pass

    # Telegram WebApp often appends tgWebApp* query params to the initial URL.
    try:
        for key in request.args.keys():
            if str(key).startswith('tgWebApp'):
                return True
    except Exception:
        pass

    # Set by templates/base.html for subsequent navigations.
    try:
        if request.cookies.get('tg_webview') == '1':
            return True
    except Exception:
        pass

    return False

@app.after_request
def _telegram_webview_cache_control(response):
    """Avoid Telegram Android in-app caching issues (can manifest as the 'duck' error)."""
    try:
        if response.mimetype == 'text/html':
            ua = (request.headers.get('User-Agent', '') or '').lower()
            is_android = 'android' in ua
            is_lite = request.args.get('lite') == '1'
            is_tg_page = (request.path or '').startswith('/__telegram_')
            is_tg = is_telegram_webview()

            if is_tg:
                # Add `no-transform` to prevent Cloudflare from injecting/rewriting HTML
                # (notably the Cloudflare Web Analytics beacon), which can crash Telegram Android WebView.
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'

                # Ensure Telegram WebView marker cookie is set server-side as well (UA may not include Telegram).
                try:
                    if request.cookies.get('tg_webview') != '1':
                        response.set_cookie(
                            'tg_webview',
                            '1',
                            max_age=60 * 60 * 24 * 30,
                            secure=True,
                            httponly=False,
                            samesite='None',
                            path='/',
                        )
                except Exception:
                    pass

            # Telegram Android "duck" often correlates with injected 3rd-party scripts/styles that throw
            # cross-origin masked errors ("Script error."). Apply a stricter CSP on Android for:
            # - Telegram WebView HTML responses
            # - any diagnostic telegram pages (/__telegram_*)
            # - explicit lite pages (?lite=1)
            if is_android and (is_lite or is_tg_page or is_tg):
                # Ensure no-transform even when Telegram detection fails but UA is Android.
                try:
                    cc = response.headers.get('Cache-Control', '')
                    if 'no-transform' not in cc:
                        response.headers['Cache-Control'] = (cc + ', no-transform').lstrip(', ').strip()
                except Exception:
                    pass
                response.headers['X-Telegram-Android-Hardening'] = '1'
                response.headers['Content-Security-Policy'] = (
                    "default-src 'self'; "
                    "base-uri 'self'; "
                    "form-action 'self'; "
                    "frame-ancestors 'self'; "
                    "object-src 'none'; "
                    "script-src 'self' 'unsafe-inline'; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                    "img-src 'self' data: blob:; "
                    "font-src 'self' data: https://fonts.gstatic.com; "
                    "connect-src 'self' https:; "
                    "media-src 'self' https: data:;"
                )
    except Exception:
        pass
    return response

@app.route('/__telegram_base_test')
def telegram_base_test_page():
    """Render a minimal page through base.html to isolate crashes caused by global assets/scripts."""
    try:
        resp = Response(render_template('telegram_base_test.html'), mimetype='text/html')
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception as e:
        logger.warning("telegram_base_test_page error: %s", e, exc_info=True)
        return redirect(url_for('index'))

@app.route('/__telegram_min_test')
def telegram_min_test_page():
    """Render a standalone minimal HTML page (no base.html) to isolate crashes caused by shared templates/assets."""
    try:
        resp = Response(render_template('telegram_min_test.html'), mimetype='text/html')
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, no-transform'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception as e:
        logger.warning("telegram_min_test_page error: %s", e, exc_info=True)
        return redirect(url_for('index'))

def check_rate_limit(key: str, limit: int, window: int) -> bool:
    """Check if rate limit is exceeded"""
    # Simple in-memory rate limiting (in production, use Redis or similar)
    import time
    current_time = int(time.time())

    if not hasattr(check_rate_limit, 'requests'):
        check_rate_limit.requests = {}

    # Clean old requests
    check_rate_limit.requests = {
        k: v for k, v in check_rate_limit.requests.items()
        if current_time - v['timestamp'] < window
    }

    # Check current requests for this key
    if key not in check_rate_limit.requests:
        check_rate_limit.requests[key] = {'count': 0, 'timestamp': current_time}

    # Reset counter if window passed
    if current_time - check_rate_limit.requests[key]['timestamp'] >= window:
        check_rate_limit.requests[key] = {'count': 0, 'timestamp': current_time}

    # Increment counter
    check_rate_limit.requests[key]['count'] += 1

    # Check limit
    return check_rate_limit.requests[key]['count'] <= limit

def is_bot_running() -> bool:
    """Check if Telegram bot is running by checking bot lock status"""
    try:
        # Import bot lock module
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from bot.bot_lock import get_bot_status
        
        # Get bot status using the lock mechanism
        bot_status = get_bot_status()
        return bot_status.get('running', False)
        
    except ImportError:
        # Fallback to old method if bot_lock module not available
        return _fallback_bot_check()
    except Exception as e:
        logger.warning(f"Error checking bot status: {e}")
        return False

def _fallback_bot_check() -> bool:
    """Fallback bot check using old lock file method"""
    import os
    import psutil

    lock_file = os.path.join(os.path.dirname(__file__), '..', 'bot', 'bot.lock')

    if not os.path.exists(lock_file):
        return False

    try:
        # Read PID from lock file
        with open(lock_file, 'r') as f:
            pid_str = f.read().strip()

        if not pid_str:
            return False

        pid = int(pid_str)

        # Check if process exists and is running
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            # Check if it's a Python process (basic check)
            if process.name().lower() in ['python', 'python.exe', 'python3', 'python3.exe']:
                # Additional check: verify it's running the bot
                cmdline = process.cmdline()
                if any('run_bot.py' in arg or 'bot/main.py' in arg for arg in cmdline):
                    return True

        # If we get here, either process doesn't exist or it's not our bot
        return False

    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
        # If we can't read the PID or process doesn't exist, consider bot not running
        return False

# === I18N UTILITIES ===

def _get_current_language() -> str:
    """Return current UI language stored in session or default."""
    lang = session.get('lang', None) or 'en'
    if lang not in localization.languages:
        lang = localization.default_language
    return lang

def _normalize_checkout_data(checkout: dict) -> dict:
    """Normalize checkout data for template compatibility."""
    co = dict(checkout)
    def _parse_datetime(value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                    try:
                        return datetime.strptime(value, fmt)
                    except Exception:
                        continue
        return None

    created_at = _parse_datetime(co.get('created_at'))
    expires_at = _parse_datetime(co.get('expires_at'))
    co['created_at'] = created_at or datetime.now()
    co['expires_at'] = expires_at or datetime.now()

    if co.get('qr_code_path') or co.get('qr_code_url'):
        co['qr_code_url'] = shared_utils.map_qr_code_path(
            co.get('qr_code_path'),
            co.get('qr_code_url')
        ) or co.get('qr_code_url')

    if co.get('wallet_address') and not co.get('address'):
        co['address'] = co['wallet_address']

    amount_value = None
    if co.get('amount') is not None:
        try:
            amount_value = float(co.get('amount'))
        except (TypeError, ValueError):
            amount_value = None

    if 'commission_amount' not in co or co.get('commission_amount') is None:
        if amount_value is not None:
            co['commission_amount'] = round(amount_value * COMMISSION_RATE, 8)
        else:
            co['commission_amount'] = None

    if 'seller_amount' not in co or co.get('seller_amount') is None:
        if amount_value is not None and co.get('commission_amount') is not None:
            co['seller_amount'] = round(amount_value - float(co['commission_amount']), 8)
        else:
            co['seller_amount'] = None

    return co

@app.context_processor
def inject_i18n():
    """Inject translation helper and current language into templates."""
    try:
        # Try to use the real localization
        lang = _get_current_language()
        def t(key: str, **kwargs):
            return localization.get_text(key, language=lang, **kwargs)
        def get_bot_name():
            return localization.get_text('bot_name', language=lang)

        return dict(
            t=t,
            current_lang=lang,
            bot_name=get_bot_name(),
            is_logged_in=bool(session.get('user_id')),
            is_admin=is_user_admin(),
            current_endpoint=request.endpoint,
            is_mobile_device=is_mobile_device(),
            is_telegram_webview=is_telegram_webview(),
            static_version=app.config.get('STATIC_VERSION', '0'),
        )
    except Exception as e:
        # Localization fallback mode
        logger.warning(f"Localization failed, using fallback mode: {e}")
        def t(key: str, **kwargs):
            return f"[{key}]"
        def get_bot_name():
            return "Black Diamond"
        return dict(
            t=t,
            current_lang='en',
            bot_name=get_bot_name(),
            is_logged_in=bool(session.get('user_id')),
            is_admin=False,
            current_endpoint=request.endpoint,
            is_mobile_device=False,
            is_telegram_webview=is_telegram_webview(),
            static_version=app.config.get('STATIC_VERSION', '0'),
        )

@app.route('/api/client-error', methods=['POST'])
def api_client_error():
    """Client-side error reporting endpoint (useful for Telegram Android WebView diagnostics)."""
    try:
        data = request.get_json(silent=True) or {}
        logger.warning(
            "CLIENT_ERROR path=%s msg=%s ua=%s details=%s",
            data.get('path') or request.path,
            data.get('message'),
            (request.headers.get('User-Agent') or '')[:200],
            {k: data.get(k) for k in ('type', 'stack', 'source', 'lineno', 'colno', 'extra') if k in data},
        )
    except Exception as e:
        logger.warning("CLIENT_ERROR parse failed: %s", e)
    return ('', 204)

def _is_android_telegram_request() -> bool:
    try:
        ua = (request.headers.get('User-Agent', '') or '').lower()
        tg_platform = (request.args.get('tgWebAppPlatform') or '').lower()
        is_android = ('android' in ua) or (tg_platform == 'android')
        return is_android and is_telegram_webview()
    except Exception:
        return False

@app.before_request
def _block_android_telegram_temporarily():
    """Temporarily disable the web UI for Telegram Android WebApp/WebView."""
    if not _is_android_telegram_request():
        return

    # Allow static assets so the fallback page can render.
    if request.path.startswith('/static/'):
        return

    # Allow the fallback page itself (and basic diagnostics).
    if request.path == '/android-unavailable':
        return
    if request.path == '/api/client-error':
        return

    # For API calls, return a proper 503 JSON so clients don't mis-handle HTML.
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'ANDROID_TEMPORARILY_UNAVAILABLE'}), 503

    return render_template('android_unavailable.html'), 503

@app.before_request
def check_service_status():
    """Check service status before each request and redirect to maintenance if service is down"""
    try:
        # Skip check for static files and certain endpoints
        allowed_endpoints = ['static', 'maintenance', 'set_language', 'service_status', 'api_service_status']
        if request.endpoint in allowed_endpoints or request.path.startswith('/static/'):
            return
        
        # Determine which service is needed based on the request
        service_key = None
        
        # Main Web Interface
        if request.endpoint in ['index', 'login', 'register', 'auth_token', 'auth_telegram_web_app', 'logout', 'terms']:
            service_key = 'web_interface'
        
        # Deal Creation
        elif request.endpoint in ['create_deal', 'api_create_deal']:
            service_key = 'web_deal_creation'
        
        # Deal Joining
        elif request.endpoint in ['join_deal', 'api_join_deal']:
            service_key = 'web_deal_joining'
        
        # Deal Viewing
        elif request.endpoint in ['deal_detail', 'deal_withdraw', 'api_deal_info']:
            service_key = 'web_deal_viewing'
        
        # Profile Management
        elif request.endpoint in ['profile', 'api_user_stats', 'api_user_deals', 'api_user_analytics', 'api_user_refresh_avatar']:
            service_key = 'web_profile'
        
        # Support Chat
        elif request.endpoint in ['support', 'api_support_messages', 'api_send_support_message', 'api_mark_support_messages_read']:
            service_key = 'web_support'
        
        # Admin Panel
        elif request.endpoint in ['admin', 'admin_settings', 'admin_users', 'admin_user_detail', 'admin_support', 'admin_deals',
                                'api_admin_settings', 'api_admin_get_users', 'api_admin_get_user_details', 'api_admin_get_user_disputes', 'api_admin_ban_user',
                                'api_admin_send_message', 'api_admin_get_messages', 'api_admin_analytics', 'api_admin_deals']:
            service_key = 'web_admin_panel'
        
        # Statistics
        elif request.endpoint in ['api_stats', 'api_settings_commission_rate']:
            service_key = 'web_statistics'
        
        # Payments
        elif request.endpoint in ['payment_page', 'payment_success', 'payment_cancel', 'api_payment_status']:
            service_key = 'payments'
        
        # Notifications
        elif request.endpoint in ['api_notifications', 'api_dismiss_notification', 'api_mark_all_notifications_read', 'api_notifications_stream']:
            service_key = 'notifications'
        
        # Telegram Bot API integration
        elif request.endpoint in ['api_create_deal', 'api_join_deal', 'api_cancel_deal', 'api_user_stats', 'api_user_deals', 'api_notifications', 'api_support_messages', 'api_send_support_message', 'api_admin_send_support_message', 'api_admin_send_message', 'api_admin_get_users', 'api_admin_get_user_details', 'api_admin_get_user_disputes', 'api_admin_ban_user']:
            # API service - this is a fallback for general API endpoints
            service_key = 'api'
        
        # Check if the required service is enabled
        if service_key and not service_manager.is_service_enabled(service_key):
            # Get the custom maintenance message
            message = service_manager.get_maintenance_message(service_key)
            if message:
                # Store the message in session for display
                session['maintenance_message'] = message
            return redirect(url_for('maintenance'))
            
    except Exception as e:
        # If there's an error checking services, log it but don't block the request
        logger.warning(f"Service check error: {e}")
        pass

@app.route('/service-status')
def service_status():
    """Service status page for checking which services are available"""
    try:
        services = service_manager.get_all_services()
        status_summary = service_manager.get_services_status_summary()
        
        return jsonify({
            'services': [
                {
                    'key': service.key,
                    'name': service.name,
                    'is_enabled': service.is_enabled,
                    'maintenance_message': service.maintenance_message
                }
                for service in services
            ],
            'summary': status_summary
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/service-status', methods=['GET'])
def api_service_status():
    """API for getting service status"""
    try:
        service_key = request.args.get('service')
        if not service_key:
            return jsonify({'error': localization.get_text('service_key_required', language=_get_current_language())}), 400
        
        is_enabled = service_manager.is_service_enabled(service_key)
        message = service_manager.get_maintenance_message(service_key) if not is_enabled else ""
        
        return jsonify({
            'service': service_key,
            'is_enabled': is_enabled,
            'maintenance_message': message
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/services', methods=['GET'])
def api_admin_get_services():
    """API for admin to get all services"""
    try:
        # Check admin access
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('access_denied', language=_get_current_language())}), 403
        
        services = service_manager.get_all_services()
        return jsonify({
            'success': True,
            'services': [
                {
                    'key': service.key,
                    'name': service.name,
                    'description': service.description,
                    'is_enabled': service.is_enabled,
                    'maintenance_message': service.maintenance_message,
                    'last_updated': service.last_updated
                }
                for service in services
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/services/<service_key>', methods=['POST'])
def api_admin_update_service(service_key):
    """API for admin to update service status"""
    try:
        # Check admin access
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('access_denied', language=_get_current_language())}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': localization.get_text('no_data_provided', language=_get_current_language())}), 400
        
        # Update service status
        if 'is_enabled' in data:
            success = service_manager.set_service_status(service_key, data['is_enabled'])
            if not success:
                return jsonify({'error': localization.get_text('failed_to_update_service_status', language=_get_current_language())}), 500
        
        # Update maintenance message
        if 'maintenance_message' in data:
            success = service_manager.update_service_message(service_key, data['maintenance_message'])
            if not success:
                return jsonify({'error': localization.get_text('failed_to_update_service_message', language=_get_current_language())}), 500
        
        # Get updated service
        service = service_manager.get_service(service_key)
        if not service:
            return jsonify({'error': localization.get_text('service_not_found', language=_get_current_language())}), 404
        
        return jsonify({
            'success': True,
            'service': {
                'key': service.key,
                'name': service.name,
                'description': service.description,
                'is_enabled': service.is_enabled,
                'maintenance_message': service.maintenance_message,
                'last_updated': service.last_updated
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === WEB ROUTES ===

@app.before_request
def check_bot_status():
    """Check bot status before each request and redirect to maintenance if bot is down"""
    # TEMPORARILY DISABLE BOT CHECK FOR DIAGNOSTICS
    # if not is_bot_running():
    #     # Allow access to maintenance page, static files, and essential deal viewing
    #     # Also allow language change endpoint so UI language can be switched
    #     allowed_endpoints = ['static', 'maintenance', 'set_language', 'deal_detail', 'index', 'login', 'register', 'auth_telegram', 'auth_token', 'logout']
    #     if request.endpoint in allowed_endpoints or request.path.startswith('/static/') or request.path.startswith('/api/deal/'):
    #         return
    #     # Redirect to maintenance page
    #     return redirect(url_for('maintenance'))
    pass

@app.before_request
def refresh_session():
    """Refresh session on user activity"""
    # CRITICAL FIX: Always mark session as modified to ensure persistence
    if session.get('user_id'):
        session.modified = True
        session.permanent = True
        logger.debug(f"Session refreshed for user {session.get('user_id')}. Session keys: {list(session.keys())}")

@app.route('/')
def index():
    """Main page"""
    try:
        ua = (request.headers.get('User-Agent', '') or '').lower()
        tg_platform = (request.args.get('tgWebAppPlatform') or '').lower()
        is_android = ('android' in ua) or (tg_platform == 'android')

        # Only show the Android outage page inside Telegram WebApp/WebView,
        # so regular Android browsers aren't affected.
        if is_android and is_telegram_webview():
            return render_template('android_unavailable.html')
    except Exception:
        # Never block the homepage if detection fails.
        pass

    return render_template('index.html')

@app.route('/android-unavailable')
def android_unavailable():
    """Temporary Android outage page for Telegram WebApp."""
    return render_template('android_unavailable.html')

@app.route('/maintenance')
def maintenance():
    """Maintenance page when services are under maintenance"""
    # Get custom maintenance message from session (if set by service check)
    custom_message = session.get('maintenance_message', '')
    # Clear the message from session after reading
    session.pop('maintenance_message', None)
    
    return render_template('maintenance.html', custom_maintenance_message=custom_message)

@app.route('/login')
def login():
    """Login page - redirects to registration modal"""
    return redirect(url_for('index'))

@app.route('/register')
def register():
    """Registration page - redirects to registration modal"""
    return redirect(url_for('index'))

@app.route('/auth/token/<token>')
def auth_token(token):
    """Authenticate user via token"""
    logger.info("AUTH FLOW START: Token authentication initiated")

    try:
        # If the user is already authenticated, avoid re-validating/burning a one-time token on refresh.
        # (Users often refresh /auth/token/<token> and think they were "logged out" when the token expires.)
        if session.get("user_id") and request.args.get("force") != "1":
            return redirect(url_for('index'))

        # Prevent one-time tokens from being "burned" by link previews/prefetchers (TelegramBot, etc.)
        ua = (request.headers.get('User-Agent') or '').lower()
        purpose = (request.headers.get('Purpose') or request.headers.get('Sec-Purpose') or '').lower()
        x_purpose = (request.headers.get('X-Purpose') or '').lower()
        sec_fetch_mode = (request.headers.get('Sec-Fetch-Mode') or '').lower()
        sec_fetch_dest = (request.headers.get('Sec-Fetch-Dest') or '').lower()
        accept = (request.headers.get('Accept') or '').lower()
        is_likely_prefetch = (
            'telegrambot' in ua
            or purpose == 'prefetch'
            or x_purpose == 'prefetch'
            or (sec_fetch_mode and sec_fetch_mode != 'navigate')
            or sec_fetch_dest in ('image', 'script', 'style', 'font', 'empty')
            or (accept and ('text/html' not in accept) and ('application/xhtml+xml' not in accept))
        )
        if is_likely_prefetch:
            return ('', 204)

        # Validate token and get user_id
        user_id = db.validate_auth_token(token)

        if not user_id:
            logger.warning("AUTH FAILURE: Invalid token - no user_id returned")
            flash(localization.get_text('invalid_token', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Get user data from database
        user = db.get_user(user_id)

        if not user:
            logger.error(f"AUTH FAILURE: User not found in database for user_id: {user_id}")
            flash(localization.get_text('user_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Prepare session data
        session_data = {
            'user_id': user_id,
            'username': user.get('username', 'Unknown'),
            'first_name': user.get('first_name', 'User'),
            'avatar_url': user.get('avatar_url', ''),
            'lang': db.get_user_language(user_id)
        }

        # Set session data
        session['user_id'] = session_data['user_id']
        session['username'] = session_data['username']
        session['first_name'] = session_data['first_name']
        session['avatar_url'] = session_data['avatar_url']
        session['lang'] = session_data['lang']

        # Configure session persistence
        session.modified = True
        session.permanent = True
        logger.debug(
            "AUTH DEBUG: session keys=%s permanent=%s modified=%s",
            list(session.keys()),
            session.permanent,
            session.modified,
        )

        logger.info(f"AUTH SUCCESS: Authentication completed successfully for user {user_id}")
        flash(localization.get_text('login_success', language=_get_current_language()), 'success')

        # Consume the token on the *next* request (after redirect), when we can be sure
        # the client stored a session cookie. This avoids burning tokens via link previews.
        session["_pending_auth_token"] = token
        session["_pending_auth_token_user_id"] = user_id

        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"AUTH ERROR: Exception in token auth: {e}", exc_info=True)
        flash(localization.get_text('auth_error', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

@app.route('/auth/telegram-web-app', methods=['POST'])
def auth_telegram_web_app():
    """Authenticate user via Telegram Web App"""
    logger.info("TELEGRAM WEB APP AUTH: Starting authentication process")
    
    try:
        data = request.get_json()
        if not data:
            logger.warning("TELEGRAM WEB APP AUTH: No JSON data provided")
            return jsonify({
                'success': False,
                'message': localization.get_text('no_data_provided', language=_get_current_language()),
            }), 400

        def _coerce_language(language_code: str) -> str:
            code = (language_code or '').lower()
            if code in ('ua', 'uk', 'uk-ua') or code.startswith('uk'):
                return 'ua'
            if code.startswith('en'):
                return 'en'
            return 'en'

        request_language = _coerce_language(data.get('language_code', 'en'))

        # Prefer validating Telegram initData when available (prevents spoofing and supports auto-auth).
        init_data = data.get('initData')
        if init_data:
            try:
                import hashlib
                import hmac
                import json as _json
                from urllib.parse import parse_qsl

                from shared.config import BOT_TOKEN

                parsed = dict(parse_qsl(init_data, keep_blank_values=True))
                received_hash = parsed.pop('hash', '')

                if not BOT_TOKEN:
                    logger.error("TELEGRAM WEB APP AUTH: BOT_TOKEN not configured")
                    return jsonify({
                        'success': False,
                        'message': localization.get_text('server_misconfigured', language=request_language),
                    }), 500

                data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
                secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
                calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

                if not received_hash or not hmac.compare_digest(calculated_hash, received_hash):
                    logger.warning("TELEGRAM WEB APP AUTH: initData hash validation failed")
                    return jsonify({
                        'success': False,
                        'message': localization.get_text('invalid_telegram_auth_data', language=request_language),
                    }), 401

                user_raw = parsed.get('user')
                if not user_raw:
                    logger.warning("TELEGRAM WEB APP AUTH: initData missing user payload")
                    return jsonify({
                        'success': False,
                        'message': localization.get_text('missing_user_data', language=request_language),
                    }), 400

                user_parsed = _json.loads(user_raw)
                data['id'] = user_parsed.get('id')
                data['first_name'] = user_parsed.get('first_name', '')
                data['last_name'] = user_parsed.get('last_name', '')
                data['username'] = user_parsed.get('username', '')
                data['language_code'] = user_parsed.get('language_code', data.get('language_code', 'en'))
                request_language = _coerce_language(data.get('language_code', request_language))
            except Exception as initdata_error:
                logger.error(f"TELEGRAM WEB APP AUTH: initData parsing/validation error: {initdata_error}")
                logger.error("TELEGRAM WEB APP AUTH: Full traceback", exc_info=True)
                return jsonify({
                    'success': False,
                    'message': localization.get_text('invalid_telegram_auth_data', language=request_language),
                }), 401
        
        # Extract user data from request
        telegram_id = data.get('id')
        first_name = data.get('first_name', '')
        username = data.get('username', '')
        hash_value = data.get('hash', '')
        
        logger.info(f"TELEGRAM WEB APP AUTH: User data - ID: {telegram_id}, Name: {first_name}, Username: {username}")
        
        if not telegram_id or not first_name:
            logger.warning("TELEGRAM WEB APP AUTH: Missing required user data")
            return jsonify({
                'success': False,
                'message': localization.get_text('missing_required_user_data', language=request_language),
            }), 400
        
        # Basic hash validation (in production, you should implement proper Telegram Web App hash validation)
        # For now, we'll accept the hash but log it for debugging
        logger.info(f"TELEGRAM WEB APP AUTH: Hash validation - received hash: {hash_value[:10]}...")
        
        # Check if user already exists in database
        user = db.get_user(telegram_id)
        
        if not user:
            logger.info(f"TELEGRAM WEB APP AUTH: Creating new user for Telegram ID {telegram_id}")
            # Create new user
            success = db.create_user(
                user_id=telegram_id,
                username=username,
                first_name=first_name
            )
            
            if not success:
                logger.error("TELEGRAM WEB APP AUTH: Failed to create user in database")
                return jsonify({
                    'success': False,
                    'message': localization.get_text('failed_to_create_user', language=request_language),
                }), 500
            
            # Set additional user data
            db.update_user(
                user_id=telegram_id,
                last_name=data.get('last_name', ''),
                language_code=data.get('language_code', 'en')
            )
            
            # Get the newly created user
            user = db.get_user(telegram_id)
            logger.info(f"TELEGRAM WEB APP AUTH: Successfully created user {telegram_id}")
        else:
            logger.info(f"TELEGRAM WEB APP AUTH: User {telegram_id} already exists, updating data")
            # Update existing user data
            db.update_user(
                user_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=data.get('last_name', ''),
                language_code=data.get('language_code', 'en')
            )
        
        # Set up user session
        session['user_id'] = telegram_id
        session['username'] = username
        session['first_name'] = first_name
        session['avatar_url'] = user.get('avatar_url', '') if user else ''
        session['lang'] = db.get_user_language(telegram_id) if user else 'en'
        
        # Make session permanent
        session.permanent = True
        session.modified = True
        
        logger.info(f"TELEGRAM WEB APP AUTH: Successfully authenticated user {telegram_id}")
        logger.info(f"TELEGRAM WEB APP AUTH: Session data set - user_id: {session.get('user_id')}, username: {session.get('username')}")
        
        return jsonify({
            'success': True,
            'redirect': '/',
            'message': localization.get_text('auth_successful', language=request_language)
        })
        
    except Exception as e:
        logger.error(f"TELEGRAM WEB APP AUTH: Error during authentication: {e}")
        logger.error(f"TELEGRAM WEB APP AUTH: Full traceback", exc_info=True)
        return jsonify({
            'success': False,
            'message': localization.get_text('auth_error', language=_get_current_language()),
        }), 500

@app.route('/profile')
def profile():
    """User profile page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    # Diagnostic: render without page-specific JS (Telegram Android WebView "duck" debugging).
    if request.args.get('lite') == '1':
        return render_template('telegram_lite_page.html', target_path='/profile')

    # Update avatar URL in session if available
    user_id = session.get('user_id')
    user = db.get_user(user_id)
    if user and user.get('avatar_url'):
        session['avatar_url'] = user.get('avatar_url', '')
        logger.info(f"Set avatar_url in session for user {user_id}: {session['avatar_url']}")
    else:
        logger.info(f"No avatar_url found for user {user_id}")
    
    # Ensure avatar_url is available in user_data for template
    if user:
        # Use session avatar_url as fallback if user_data doesn't have it
        if not user.get('avatar_url') and session.get('avatar_url'):
            user['avatar_url'] = session['avatar_url']
            logger.info(f"Using session avatar_url for user {user_id}: {session['avatar_url']}")
    
    # Note: Avatar download happens when user interacts with bot via /start command

    return render_template('profile.html', user_data=user)

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash(localization.get_text('logout_success', language=_get_current_language()), 'success')
    return redirect(url_for('index'))


@app.route('/payment/<checkout_id>')
def payment_page(checkout_id):
    """Payment page with QR code"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            flash(localization.get_text('login_required', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Get checkout data
        checkout = system_wallet_checkout.get_checkout(checkout_id)

        if not checkout:
            flash(localization.get_text('payment_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Check if user has access to this checkout
        deal = db.get_deal(checkout['deal_code'])
        if not deal or user_id not in [deal['buyer_id'], deal.get('seller_id')]:
            flash(localization.get_text('no_payment_access', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Check expiration time
        expires_at = datetime.fromisoformat(checkout['expires_at'])
        if datetime.now() > expires_at:
            flash(localization.get_text('payment_expired', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # ADMIN simulation:
        # - first page open: show regular payment page (no status checks)
        # - browser refresh: instantly "find" payment (no blockchain checks)
        if is_user_admin() and deal and deal.get('buyer_id') == user_id and deal.get('status') == 'active':
            refresh_count = _admin_payment_sim_increment(checkout_id)
            if refresh_count >= 2:
                tx_hash = "ADMIN_SIMULATED"
                try:
                    updated = db.update_decentralized_payment_status(deal['deal_code'], 'confirmed', tx_hash)
                    if not updated:
                        db.update_checkout_status(checkout_id, 'confirmed', tx_hash)
                except Exception:
                    pass
                try:
                    db.update_deal_status(deal['deal_code'], 'funded', payment_confirmed_at=datetime.now().isoformat())
                except Exception:
                    pass
                _admin_payment_sim_clear(checkout_id)
                return redirect(url_for('payment_success', checkout_id=checkout_id))

        co = _normalize_checkout_data(checkout)
        return render_template('payment.html',
                               checkout=co)

    except Exception as e:
        logger.error(f"Error loading payment page {checkout_id}: {e}")
        flash(localization.get_text('general_error', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

@app.route('/payment/deal/<deal_code>')
def payment_by_deal(deal_code):
    """Helper route to open payment page by deal code"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            flash(localization.get_text('login_required', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        deal = db.get_deal(deal_code.upper())
        if not deal:
            flash(localization.get_text('deal_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        if user_id not in [deal['buyer_id'], deal.get('seller_id')]:
            flash(localization.get_text('no_payment_access', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        checkout = db.get_crypto_checkout_by_deal(deal_code.upper())
        if not checkout:
            checkout = db.get_decentralized_payment_by_deal_code(deal_code.upper())
        if not checkout:
            try:
                new_checkout = payment_processor.process_deal_payment(
                    deal_code=deal_code.upper(),
                    amount=float(deal['amount']),
                    currency=deal['currency'],
                    description=deal.get('description')
                )
                if not new_checkout:
                    flash(localization.get_text('payment_creation_error', language=_get_current_language()), 'error')
                    return redirect(url_for('deal_detail', deal_code=deal_code.upper()))
                checkout_id = new_checkout['checkout_id']
            except Exception as e:
                logger.error(f"Failed to create checkout for deal {deal_code}: {e}")
                flash(localization.get_text('payment_creation_error', language=_get_current_language()), 'error')
                return redirect(url_for('deal_detail', deal_code=deal_code.upper()))
        else:
            checkout_id = checkout['checkout_id']

        return redirect(url_for('payment_page', checkout_id=checkout_id))

    except Exception as e:
        logger.error(f"Error loading payment by deal {deal_code}: {e}")
        flash(localization.get_text('general_error', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

@app.route('/create-deal')
def create_deal():
    """Deal creation page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required_create_deal', language=_get_current_language()), 'error')
        return redirect(url_for('index'))
    # Diagnostic: render without page-specific JS (Telegram Android WebView "duck" debugging).
    if request.args.get('lite') == '1':
        return render_template('telegram_lite_page.html', target_path='/create-deal')
    return render_template('create_deal.html')



@app.route('/terms')
def terms():
    """Terms of service page"""
    return render_template('terms.html')



@app.route('/deal/<deal_code>')
def deal_detail(deal_code):
    """Deal detail page"""
    try:
        # Get deal information first
        deal = db.get_deal(deal_code.upper())
        if not deal:
            flash(localization.get_text('deal_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Check authentication
        user_id = session.get('user_id')

        # Check if user has access to this deal
        is_participant = user_id and (deal['buyer_id'] == user_id or deal['seller_id'] == user_id)
        if not is_participant:
            flash(localization.get_text('no_deal_access', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Convert string timestamps to datetime objects for template
        deal_data = dict(deal)

        # Handle created_at timestamp
        if deal_data.get('created_at'):
            if isinstance(deal_data['created_at'], str):
                try:
                    # Try ISO format first
                    deal_data['created_at'] = datetime.fromisoformat(deal_data['created_at'])
                except (ValueError, TypeError):
                    try:
                        # Try other common formats
                        deal_data['created_at'] = datetime.strptime(deal_data['created_at'], '%Y-%m-%d %H:%M:%S.%f')
                    except (ValueError, TypeError):
                        # If all parsing fails, set to current time as fallback
                        deal_data['created_at'] = datetime.now()
            elif not isinstance(deal_data['created_at'], datetime):
                # If it's not a string or datetime, set fallback
                deal_data['created_at'] = datetime.now()

        # Handle updated_at timestamp
        if deal_data.get('updated_at'):
            if isinstance(deal_data['updated_at'], str):
                try:
                    deal_data['updated_at'] = datetime.fromisoformat(deal_data['updated_at'])
                except (ValueError, TypeError):
                    try:
                        deal_data['updated_at'] = datetime.strptime(deal_data['updated_at'], '%Y-%m-%d %H:%M:%S.%f')
                    except (ValueError, TypeError):
                        deal_data['updated_at'] = deal_data.get('created_at', datetime.now())
            elif not isinstance(deal_data['updated_at'], datetime):
                deal_data['updated_at'] = deal_data.get('created_at', datetime.now())

        # Ensure we have a created_at even if missing
        if not deal_data.get('created_at'):
            deal_data['created_at'] = datetime.now()

        deal_public_url = get_deal_url(deal_data.get('deal_code', deal_code))
        return render_template('deal_detail.html', deal=deal_data, deal_public_url=deal_public_url)

    except Exception as e:
        logger.error(f"Error loading deal detail {deal_code}: {e}")
        flash(localization.get_text('deal_load_error', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

@app.route('/deal/<deal_code>/withdraw')
def deal_withdraw(deal_code):
    """Withdrawal page for seller"""
    try:
        user_id_raw = session.get('user_id')
        if not user_id_raw:
            flash(localization.get_text('login_required', language=_get_current_language()), 'error')
            return redirect(url_for('index'))
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            flash(localization.get_text('login_required', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        deal = db.get_deal(deal_code.upper())
        if not deal:
            flash(localization.get_text('deal_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        deal_data = dict(deal)
        deal_data['deal_code'] = deal_data.get('deal_code', deal_code.upper())

        if deal_data.get('seller_id') != user_id:
            flash(localization.get_text('no_deal_access', language=_get_current_language()), 'error')
            return redirect(url_for('deal_detail', deal_code=deal_code.upper()))

        if deal_data.get('status') != 'funds_pending':
            flash(localization.get_text('deal_not_active', language=_get_current_language()), 'error')
            return redirect(url_for('deal_detail', deal_code=deal_code.upper()))

        from shared.commission import get_commission_breakdown
        amount = float(deal_data['amount'])
        _, commission_amount, seller_amount = get_commission_breakdown(amount)
        commission_amount = round(float(commission_amount), 8)
        seller_amount = round(float(seller_amount), 8)

        currency = (deal_data.get('currency') or '').upper()
        if currency == 'USDT':
            wallet_prefix = 'T'
            wallet_length = '34'
            wallet_pattern = r'^T[a-zA-Z0-9]{33}$'
        elif currency == 'TON':
            wallet_prefix = 'UQ/EQ'
            wallet_length = '46-48'
            wallet_pattern = r'^(UQ|EQ)[a-zA-Z0-9_-]{46,48}$'
        else:
            wallet_prefix = ''
            wallet_length = ''
            wallet_pattern = r'.+'

        return render_template(
            'withdraw_funds.html',
            deal=deal_data,
            commission_amount=commission_amount,
            seller_amount=seller_amount,
            wallet_prefix=wallet_prefix,
            wallet_length=wallet_length,
            wallet_pattern=wallet_pattern
        )

    except Exception as e:
        logger.error(f"Error loading withdrawal page {deal_code}: {e}")
        flash(localization.get_text('general_error', language=_get_current_language()), 'error')
        return redirect(url_for('deal_detail', deal_code=deal_code.upper()))

@app.route('/payment/success/<checkout_id>')
def payment_success(checkout_id):
    """Successful payment page"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            flash(localization.get_text('login_required', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        checkout = system_wallet_checkout.get_checkout(checkout_id)
        if not checkout:
            flash(localization.get_text('payment_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Check if user has access to this checkout
        deal = db.get_deal(checkout['deal_code'])
        if not deal or user_id not in [deal['buyer_id'], deal.get('seller_id')]:
            flash(localization.get_text('no_payment_access', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        return render_template('payment_success.html',
                               checkout=checkout)

    except Exception as e:
        logger.error(f"Error on success page {checkout_id}: {e}")
        return redirect(url_for('index'))

@app.route('/payment/cancel/<checkout_id>')
def payment_cancel(checkout_id):
    """Payment cancellation page"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            flash(localization.get_text('login_required', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        checkout = system_wallet_checkout.get_checkout(checkout_id)
        if not checkout:
            flash(localization.get_text('payment_not_found', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        # Check if user has access to this checkout
        deal = db.get_deal(checkout['deal_code'])
        if not deal or user_id not in [deal['buyer_id'], deal.get('seller_id')]:
            flash(localization.get_text('no_payment_access', language=_get_current_language()), 'error')
            return redirect(url_for('index'))

        return render_template('payment_cancel.html',
                               checkout=checkout)

    except Exception as e:
        logger.error(f"Error on cancel page {checkout_id}: {e}")
        return redirect(url_for('index'))

# === LANGUAGE ROUTE ===

@app.route('/set-language', methods=['POST'])
def set_language():
    """Set UI language for web via session."""
    try:
        data = request.get_json(silent=True) or {}
        lang = (data.get('lang') or request.form.get('lang') or '').lower()
        if lang not in localization.languages:
            return jsonify({'success': False, 'message': localization.get_text('unsupported_language', language=lang)}), 400
        session['lang'] = lang

        # Save to database if user is logged in
        user_id = session.get('user_id')
        if user_id:
            db.set_user_language(user_id, lang)

        return jsonify({'success': True, 'lang': lang})
    except Exception as e:
        logger.error(f"Error setting language: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=lang)}), 500

# === API ROUTES ===

@app.route('/api/payment/<checkout_id>/status')
def api_payment_status(checkout_id):
    """API for checking payment status"""
    try:
        checkout = system_wallet_checkout.get_checkout(checkout_id)
        if not checkout:
            return jsonify({'error': localization.get_text('payment_not_found', language=_get_current_language())}), 404

        deal = None
        try:
            deal = db.get_deal((checkout.get('deal_code') or '').upper())
        except Exception:
            deal = None

        # ADMIN simulation:
        # Don't query blockchain APIs. Confirm only after the admin refreshes the payment page.
        user_id = session.get('user_id')
        refresh_requested = str(request.args.get('refresh') or '').lower() in ('1', 'true', 'yes', 'y')
        if (
            is_user_admin()
            and user_id is not None
            and deal
            and deal.get('buyer_id') == user_id
            and deal.get('status') == 'active'
        ):
            refresh_count = _admin_payment_sim_get(checkout_id)
            if refresh_requested:
                refresh_count = _admin_payment_sim_increment(checkout_id)

            if refresh_count >= 2:
                tx_hash = "ADMIN_SIMULATED"
                try:
                    updated = db.update_decentralized_payment_status(deal['deal_code'], 'confirmed', tx_hash)
                    if not updated:
                        db.update_checkout_status(checkout_id, 'confirmed', tx_hash)
                except Exception:
                    pass
                try:
                    db.update_deal_status(deal['deal_code'], 'funded', payment_confirmed_at=datetime.now().isoformat())
                except Exception:
                    pass
                _admin_payment_sim_clear(checkout_id)
                checkout = system_wallet_checkout.get_checkout(checkout_id) or checkout
                return jsonify({
                    'checkout_id': checkout_id,
                    'status': checkout.get('status') or 'confirmed',
                    'is_paid': True,
                    'message': "Payment confirmed (TX: ADMIN_SIMULATED)",
                    'amount': checkout['amount'],
                    'currency': checkout['currency'],
                    'deal_code': checkout.get('deal_code'),
                    'deal_status': 'funded',
                })

            # First open (or before refresh): pretend it's still pending (no checks).
            return jsonify({
                'checkout_id': checkout_id,
                'status': checkout.get('status'),
                'is_paid': False,
                'message': "Payment not received yet",
                'amount': checkout['amount'],
                'currency': checkout['currency'],
                'deal_code': checkout.get('deal_code'),
                'deal_status': deal.get('status') if deal else None,
            })

        # Default behavior: check payment status via processor (blockchain scan)
        is_paid, message = system_wallet_checkout.check_payment_status(checkout_id)

        # Re-fetch to return the latest persisted status
        checkout = system_wallet_checkout.get_checkout(checkout_id) or checkout

        return jsonify({
            'checkout_id': checkout_id,
            'status': checkout.get('status'),
            'is_paid': is_paid,
            'message': message,
            'amount': checkout['amount'],
            'currency': checkout['currency'],
            'deal_code': checkout.get('deal_code'),
            'deal_status': deal.get('status') if deal else None,
        })

    except Exception as e:
        logger.error(f"Error in payment status API {checkout_id}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/deal/<deal_code>')
def api_deal_info(deal_code):
    """API for getting deal information"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        logger.info(f"DEBUG API: /api/deal/{deal_code} - Session user_id: {user_id}")
        logger.info(f"DEBUG API: Session keys: {list(session.keys())}")
        logger.info(f"DEBUG API: Session permanent: {session.permanent}")
        logger.info(f"DEBUG API: Session modified: {session.modified}")
        logger.info(f"DEBUG API: Request cookies: {dict(request.cookies)}")
        if not user_id:
            logger.info(f"DEBUG API: No user_id in session, returning 401")
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'error': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        # Check if user has access to this deal
        is_participant = user_id and (deal['buyer_id'] == user_id or deal['seller_id'] == user_id)
        is_public_preview = (deal['status'] == 'active' and (deal.get('seller_id') is None))
        if not (is_participant or is_public_preview):
            return jsonify({'error': localization.get_text('no_deal_access', language=_get_current_language())}), 403

        # Calculate commission using configurable rate
        amount = deal['amount']
        deal['currency']

        # Import commission rate from config
        from shared.config import COMMISSION_RATE
        commission_rate = COMMISSION_RATE
        commission_amount = amount * commission_rate
        seller_amount = amount - commission_amount

        return jsonify({
            'deal_code': deal['deal_code'],
            'amount': deal['amount'],
            'currency': deal['currency'],
            'status': deal['status'],
            'buyer_id': deal.get('buyer_id'),
            'seller_id': deal.get('seller_id'),
            'has_seller': bool(deal.get('seller_id')),
            'description': escape_html(deal.get('description')) if deal.get('description') else None,
            'product_link': deal.get('product_link'),
            'created_at': deal['created_at'],
            'seller_joined_at': deal.get('seller_joined_at'),
            'payment_confirmed_at': deal.get('payment_confirmed_at'),
            'completed_at': deal.get('completed_at'),
            'commission_rate': commission_rate,
            'commission_amount': commission_amount,
            'seller_amount': seller_amount
        })

    except Exception as e:
        logger.error(f"Error in deal info API {deal_code}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/create-deal', methods=['POST'])
def api_create_deal():
    """API for creating deals via web interface"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        # Rate limiting: max 5 deal creations per hour per user
        if not check_rate_limit(f"create_deal:{user_id}", limit=5, window=3600):
            return jsonify({'success': False, 'message': localization.get_text('rate_limit_exceeded', language=_get_current_language())}), 429

        # Read data from JSON
        data = request.get_json()
        currency = data.get('currency', '').upper()
        amount = data.get('amount', '')
        description = data.get('description', '')
        product_link = data.get('product_link', '')

        # Data validation
        if not currency or currency not in ['USDT', 'TON']:
            return jsonify({'success': False, 'message': localization.get_text('invalid_currency', language=_get_current_language())}), 400

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except ValueError:
            return jsonify({'success': False, 'message': localization.get_text('invalid_amount', language=_get_current_language())}), 400

        from shared.currency_conversion import convert_amount_to_usd
        from shared.constants import MIN_DEAL_AMOUNT, MAX_DEAL_AMOUNT
        amount_usd = convert_amount_to_usd(amount, currency)
        if amount_usd < MIN_DEAL_AMOUNT or amount_usd > MAX_DEAL_AMOUNT:
            return jsonify({'success': False, 'message': localization.get_text('invalid_amount_range', language=_get_current_language())}), 400

        if currency == 'TON':
            amount = round(amount, 4)
        elif currency == 'USDT':
            amount = round(amount, 2)

        # Generate deal code
        deal_code = generate_deal_code()

        # Create a deal for an existing user
        success = db.create_deal(
            deal_code=deal_code,
            buyer_id=user_id,
            amount=amount,
            currency=currency,
            description=description if description else None,
            product_link=product_link if product_link else None
        )

        if not success:
            return jsonify({'success': False, 'message': localization.get_text('deal_creation_error', language=_get_current_language())}), 500

        # Create a payment
        checkout = payment_processor.process_deal_payment(
            deal_code=deal_code,
            amount=amount,
            currency=currency,
            description=description
        )

        if not checkout:
            return jsonify({'success': False, 'message': localization.get_text('payment_creation_error', language=_get_current_language())}), 500

        return jsonify({
            'success': True,
            'deal_code': deal_code,
            'checkout_id': checkout['checkout_id'],
            'message': localization.get_text('deal_created_success', language=_get_current_language())
        })

    except Exception as e:
        logger.error(f"Error creating deal: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

import asyncio

def run_async(coro):
    """Run async function in sync context"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/api/user/refresh-avatar', methods=['POST'])
def api_refresh_avatar():
    """API for refreshing user avatar from Telegram"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

    try:
        # Create a mock User object for avatar manager
        from aiogram.types import User as AiogramUser
        
        # Get user data from database
        user_data = db.get_user(user_id)
        if not user_data:
            return jsonify({'error': localization.get_text('user_not_found', language=_get_current_language())}), 404

        # Create mock Telegram User object
        mock_user = AiogramUser(
            id=user_id,
            is_bot=False,
            first_name=user_data.get('first_name', 'User'),
            username=user_data.get('username'),
            last_name=user_data.get('last_name'),
            language_code=user_data.get('language_code', 'en')
        )

        # Import avatar manager
        from shared.avatar import avatar_manager
        
        # Update avatar from Telegram
        success = run_async(avatar_manager.update_user_avatar(mock_user))
        
        if success:
            # Get updated user data with new avatar URL
            updated_user = db.get_user(user_id)
            session['avatar_url'] = updated_user.get('avatar_url', '')
            
            return jsonify({
                'success': True,
                'message': localization.get_text('avatar_refreshed', language=_get_current_language()),
                'avatar_url': updated_user.get('avatar_url', '')
            })
        else:
            return jsonify({
                'success': False,
                'message': localization.get_text('avatar_refresh_failed', language=_get_current_language())
            }), 500

    except Exception as e:
        logger.error(f"Error refreshing avatar for user {user_id}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500


@app.route('/api/user/stats')
def api_user_stats():
    """API for getting user statistics"""
    user_id = session.get('user_id')
    logger.info(f"DEBUG API: /api/user/stats - Session user_id: {user_id}")
    logger.info(f"DEBUG API: Session keys: {list(session.keys())}")
    logger.info(f"DEBUG API: Request cookies: {dict(request.cookies)}")
    if not user_id:
        logger.info(f"DEBUG API: No user_id in session for /api/user/stats, returning 401")
        return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

    try:
        # Fetch user stats with caching
        user_stats = db.get_user_stats(user_id)

        return jsonify({
            'total_deals': user_stats['total_deals'],
            'completed_deals': user_stats['completed_deals'],
            'active_deals': user_stats['active_deals'],
            'total_volume': user_stats['total_volume'],
            'success_rate': f"{user_stats['success_rate']:.1f}%"
        })

    except Exception as e:
        logger.error(f"Error in user stats API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/user/deals')
def api_user_deals():
    """API for getting user deals"""
    user_id = session.get('user_id')
    logger.info(f"DEBUG API: /api/user/deals - Session user_id: {user_id}")
    logger.info(f"DEBUG API: Session keys: {list(session.keys())}")
    logger.info(f"DEBUG API: Request cookies: {dict(request.cookies)}")
    if not user_id:
        logger.info(f"DEBUG API: No user_id in session for /api/user/deals, returning 401")
        return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

    try:
        # Fetch all user deals
        user_deals = db.get_user_deals(user_id)

        # Split into active and completed
        active_deals = [deal for deal in user_deals if deal['status'] == 'active']
        completed_deals = [deal for deal in user_deals if deal['status'] != 'active']

        return jsonify({
            'active_deals': active_deals,
            'completed_deals': completed_deals,
            'all_deals': user_deals
        })

    except Exception as e:
        logger.error(f"Error in user deals API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/user/analytics')
def api_user_analytics():
    """API for getting user analytics data"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

        period = request.args.get('period', '30d')

        # Calculate date range based on period
        from datetime import datetime, timedelta
        end_date = datetime.now()

        if period == '7d':
            start_date = end_date - timedelta(days=7)
        elif period == '30d':
            start_date = end_date - timedelta(days=30)
        elif period == '90d':
            start_date = end_date - timedelta(days=90)
        else:
            start_date = end_date - timedelta(days=30)

        # Get user deals within the period
        user_deals = db.get_user_deals(user_id)
        period_deals = [deal for deal in user_deals
                       if datetime.fromisoformat(deal['created_at']) >= start_date]

        # Generate deals trend data (daily)
        deals_trend = {'labels': [], 'data': []}
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            deals_trend['labels'].append(date_str)

            # Count completed deals for this date
            day_deals = [deal for deal in period_deals
                        if datetime.fromisoformat(deal['created_at']).date() == current_date.date()
                        and deal['status'] == 'completed']
            deals_trend['data'].append(len(day_deals))

            current_date += timedelta(days=1)

        # Volume distribution by currency
        volume_distribution = {'USDT': 0, 'TON': 0}
        for deal in period_deals:
            if deal['status'] == 'completed':
                currency = deal['currency']
                if currency in volume_distribution:
                    volume_distribution[currency] += deal['amount']

        # Success rate trend (weekly)
        success_trend = {'labels': [], 'data': []}
        current_date = start_date
        while current_date <= end_date:
            week_start = current_date
            week_end = min(current_date + timedelta(days=6), end_date)

            week_deals = [deal for deal in period_deals
                         if week_start <= datetime.fromisoformat(deal['created_at']) <= week_end]

            if week_deals:
                completed = len([d for d in week_deals if d['status'] == 'completed'])
                success_rate = (completed / len(week_deals)) * 100
            else:
                success_rate = 0

            success_trend['labels'].append(f"{week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}")
            success_trend['data'].append(round(success_rate, 1))

            current_date = week_end + timedelta(days=1)

        # Currency usage count
        currency_usage = {'USDT': 0, 'TON': 0}
        for deal in period_deals:
            currency = deal['currency']
            if currency in currency_usage:
                currency_usage[currency] += 1

        return jsonify({
            'deals_trend': deals_trend,
            'volume_distribution': list(volume_distribution.values()),
            'success_trend': success_trend,
            'currency_usage': list(currency_usage.values())
        })

    except Exception as e:
        logger.error(f"Error in user analytics API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

# === ADMIN API ROUTES ===

@app.route('/api/admin/settings', methods=['GET'])
def api_admin_get_settings():
    """API for admin to get system settings"""
    try:
        # Check admin access
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({
                'success': False,
                'message': localization.get_text('access_denied', language=_get_current_language()),
            }), 403

        settings = db.get_settings()
        return jsonify({
            'success': True,
            'settings': settings
        })

    except Exception as e:
        logger.error(f"Error getting admin settings: {e}")
        return jsonify({
            'success': False,
            'message': localization.get_text('server_error', language=_get_current_language()),
        }), 500

@app.route('/api/admin/settings', methods=['POST'])
def api_admin_update_settings():
    """API for admin to update system settings"""
    try:
        # Check admin access
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({
                'success': False,
                'message': localization.get_text('access_denied', language=_get_current_language()),
            }), 403

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': localization.get_text('no_data_provided', language=_get_current_language()),
            }), 400

        # Validate data
        required_fields = ['commission_rate', 'min_deal_amount', 'max_deal_amount',
                          'auto_confirm_timeout', 'currency_update_interval']

        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': localization.get_text('missing_field', language=_get_current_language(), field=field),
                }), 400

        # Validate ranges
        if not (0 <= data['commission_rate'] <= 0.5):
            return jsonify({
                'success': False,
                'message': localization.get_text('validation_commission_rate_range', language=_get_current_language()),
            }), 400

        if data['min_deal_amount'] >= data['max_deal_amount']:
            return jsonify({
                'success': False,
                'message': localization.get_text('validation_min_deal_amount_less_than_max', language=_get_current_language()),
            }), 400

        if not (60 <= data['auto_confirm_timeout'] <= 86400):
            return jsonify({
                'success': False,
                'message': localization.get_text('validation_auto_confirm_timeout_range', language=_get_current_language()),
            }), 400

        if not (60 <= data['currency_update_interval'] <= 86400):
            return jsonify({
                'success': False,
                'message': localization.get_text('validation_currency_update_interval_range', language=_get_current_language()),
            }), 400

        # Update settings
        success = db.update_settings(**data)

        if success:
            return jsonify({
                'success': True,
                'message': localization.get_text('admin_settings_saved', language=_get_current_language()),
            })
        else:
            return jsonify({
                'success': False,
                'message': localization.get_text('admin_settings_error', language=_get_current_language()),
            }), 500

    except Exception as e:
        logger.error(f"Error updating admin settings: {e}")
        return jsonify({
            'success': False,
            'message': localization.get_text('server_error', language=_get_current_language()),
        }), 500

@app.route('/api/admin/users', methods=['GET'])
def api_admin_get_users():
    """API for admin to get users list"""
    try:
        # Check admin access
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('access_denied', language=_get_current_language())}), 403

        # Get query parameters
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))

        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 50

        offset = (page - 1) * per_page

        # Get users and total count
        users = db.get_all_users(search=search, limit=per_page, offset=offset)
        total_count = db.get_users_count(search=search)
        total_pages = (total_count + per_page - 1) // per_page

        enriched_users = []
        for user in users:
            stats = {}
            try:
                stats = db.get_user_stats(user['user_id'])
            except Exception as exc:
                logger.warning(f"Error loading stats for user {user['user_id']}: {exc}")
            stats = stats or {}

            enriched_user = dict(user)
            enriched_user['stats'] = stats
            enriched_user['deals_count'] = stats.get('total_deals', enriched_user.get('deals_count', 0))
            volume_value = stats.get('total_volume', enriched_user.get('total_deal_amount', 0))
            enriched_user['total_deal_amount'] = volume_value
            enriched_user['total_volume'] = volume_value
            enriched_users.append(enriched_user)

        pagination = {
            'current_page': page,
            'total_pages': total_pages,
            'total_count': total_count,
            'per_page': per_page,
            'has_previous': page > 1,
            'has_next': page < total_pages
        }

        response_payload = response_utils.success_response({
            'users': enriched_users,
            'pagination': pagination
        })
        response_payload['users'] = enriched_users
        response_payload['pagination'] = pagination
        return jsonify(response_payload)

    except Exception as e:
        logger.error(f"Error getting admin users: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
def api_admin_get_user_details(user_id):
    """API for admin to get user details"""
    try:
        # Check admin access
        admin_user_id = session.get('user_id')
        if not admin_user_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('access_denied', language=_get_current_language())}), 403

        # Get user details
        user = db.get_user(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': localization.get_text('user_not_found', language=_get_current_language()),
            }), 404

        # Get additional user statistics
        user_stats = db.get_user_stats(user_id)

        # Combine all user data
        user_data = {
            **user,
            'stats': user_stats
        }

        return jsonify({
            'success': True,
            'user': user_data
        })

    except Exception as e:
        logger.error(f"Error getting user details {user_id}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/users/<int:user_id>/disputes', methods=['GET'])
def api_admin_get_user_disputes(user_id):
    """API for admin to get disputes for a specific user"""
    try:
        admin_user_id = session.get('user_id')
        if not admin_user_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('access_denied', language=_get_current_language())}), 403

        user = db.get_user(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': localization.get_text('user_not_found', language=_get_current_language()),
            }), 404

        buyer_disputes = dispute_manager.get_buyer_disputes(user_id)
        seller_disputes = dispute_manager.get_seller_disputes(user_id)

        for dispute in buyer_disputes:
            dispute['user_role'] = 'buyer'
        for dispute in seller_disputes:
            dispute['user_role'] = 'seller'

        disputes = buyer_disputes + seller_disputes
        disputes.sort(key=lambda item: item.get('created_at') or '', reverse=True)

        return jsonify({
            'success': True,
            'disputes': disputes
        })

    except Exception as e:
        logger.error(f"Error getting user disputes for {user_id}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/users/<int:user_id>/ban', methods=['POST'])
def api_admin_ban_user(user_id):
    """API for admin to ban/unban user"""
    try:
        # Check admin access
        admin_user_id = session.get('user_id')
        if not admin_user_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('access_denied', language=_get_current_language())}), 403

        # Get request data
        data = request.get_json()
        if not data or 'ban' not in data:
            return jsonify({
                'success': False,
                'message': localization.get_text('missing_ban_parameter', language=_get_current_language()),
            }), 400

        ban = bool(data['ban'])

        # Prevent admin from banning themselves
        if user_id == admin_user_id:
            return jsonify({
                'success': False,
                'message': localization.get_text('cannot_ban_yourself', language=_get_current_language()),
            }), 400

        # Ban/unban user
        success = db.ban_user(user_id, ban)

        if success:
            return jsonify({
                'success': True,
                'message': localization.get_text(
                    'user_banned_success' if ban else 'user_unbanned_success',
                    language=_get_current_language(),
                )
            })
        else:
            return jsonify({
                'success': False,
                'message': localization.get_text('failed_to_update_user_status', language=_get_current_language()),
            }), 500

    except Exception as e:
        logger.error(f"Error banning/unbanning user {user_id}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/send-message', methods=['POST'])
def api_admin_send_message():
    """API for admin to send messages to users from website"""
    try:
        # Check admin access
        admin_id = session.get('user_id')
        if not admin_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('access_denied', language=_get_current_language())}), 403

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': localization.get_text('no_data_provided', language=_get_current_language()),
            }), 400

        message_type = data.get('type', 'direct')  # 'direct' or 'broadcast'
        message = data.get('message', '').strip()

        if not message:
            return jsonify({'success': False, 'message': localization.get_text('message_empty', language=_get_current_language())}), 400

        if len(message) > 1000:
            return jsonify({'success': False, 'message': localization.get_text('message_too_long', language=_get_current_language())}), 400

        if message_type == 'direct':
            # Direct message to specific user
            target_user_id = data.get('user_id')
            if not target_user_id:
                return jsonify({'success': False, 'message': localization.get_text('user_id_required', language=_get_current_language())}), 400

            # Validate user exists
            user = db.get_user(target_user_id)
            if not user:
                return jsonify({'success': False, 'message': localization.get_text('user_not_found', language=_get_current_language())}), 404

            # Save message to database
            db.save_admin_message(ADMIN_ID, target_user_id, message, 'direct', 'sent')

            # Send message to user via Telegram
            try:
                import aiohttp
                from shared.config import BOT_TOKEN
                import asyncio

                async def send_direct_message():
                    if not BOT_TOKEN:
                        logger.error("BOT_TOKEN not configured")
                        return

                    telegram_message = f"📨 <b>Message from admin:</b>\n\n{escape_html(message)}"
   
                    # Message length validation
                    if len(message) > 1000:
                        logger.warning(f"Admin message too long from user {admin_id}")
                        return jsonify({
                            'success': False,
                            'message': localization.get_text('message_too_long', language=_get_current_language()),
                        }), 400

                    try:
                        async with aiohttp.ClientSession() as session:
                            data_payload = {
                                "chat_id": int(target_user_id),
                                "text": telegram_message,
                                "parse_mode": "HTML"
                            }

                            async with session.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json=data_payload,
                                timeout=aiohttp.ClientTimeout(total=10)
                            ) as response:
                                if response.status != 200:
                                    error_text = await response.text()
                                    logger.error(f"Failed to send admin message to user {target_user_id}: {error_text}")
                                    # Update message status to failed
                                    db.save_admin_message(ADMIN_ID, target_user_id, message, 'direct', 'failed')
                                else:
                                    logger.info(f"Admin message sent successfully to user {target_user_id}")

                    except Exception as e:
                        logger.error(f"Error sending admin message to user {target_user_id}: {e}")
                        # Update message status to failed
                        db.save_admin_message(ADMIN_ID, target_user_id, message, 'direct', 'failed')

                # Send message asynchronously
                asyncio.create_task(send_direct_message())

                return jsonify({
                    'success': True,
                    'message': localization.get_text('message_sent_to_user', language=_get_current_language())
                })

            except Exception as e:
                logger.error(f"Error initiating admin message to user {target_user_id}: {e}")
                return jsonify({'success': False, 'message': localization.get_text('message_send_error', language=_get_current_language())}), 500

        elif message_type == 'broadcast':
            # Broadcast message to all users
            try:
                import aiohttp
                from shared.config import BOT_TOKEN
                import asyncio

                # Get all users
                users = db.get_all_users()
                if not users:
                    return jsonify({'success': False, 'message': localization.get_text('no_users_for_broadcast', language=_get_current_language())}), 400

                telegram_message = f"📢 <b>Message from admin:</b>\n\n{escape_html(message)}"

                async def send_broadcast():
                    if not BOT_TOKEN:
                        logger.error("BOT_TOKEN not configured")
                        return

                    sent_count = 0
                    failed_count = 0

                    async with aiohttp.ClientSession() as session:
                        for user in users:
                            user_id = user.get('user_id')
                            if not user_id:
                                continue

                            try:
                                data_payload = {
                                    "chat_id": int(user_id),
                                    "text": telegram_message,
                                    "parse_mode": "HTML"
                                }

                                async with session.post(
                                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                    json=data_payload,
                                    timeout=aiohttp.ClientTimeout(total=5)
                                ) as response:
                                    if response.status == 200:
                                        sent_count += 1
                                        # Save successful message
                                        db.save_admin_message(ADMIN_ID, user_id, message, 'broadcast', 'sent')
                                    else:
                                        failed_count += 1
                                        # Save failed message
                                        db.save_admin_message(ADMIN_ID, user_id, message, 'broadcast', 'failed')
                                        logger.warning(f"Failed to send broadcast to user {user_id}: {await response.text()}")

                            except Exception as e:
                                failed_count += 1
                                # Save failed message
                                db.save_admin_message(ADMIN_ID, user_id, message, 'broadcast', 'failed')
                                logger.error(f"Error sending broadcast to user {user_id}: {e}")

                    logger.info(f"Broadcast completed: sent={sent_count}, failed={failed_count}")

                # Send broadcast asynchronously
                asyncio.create_task(send_broadcast())

                return jsonify({
                    'success': True,
                    'message': localization.get_text('broadcast_started', language=_get_current_language(), count=len(users))
                })

            except Exception as e:
                logger.error(f"Error initiating broadcast: {e}")
                return jsonify({'success': False, 'message': localization.get_text('broadcast_start_error', language=_get_current_language())}), 500

        else:
            return jsonify({'success': False, 'message': localization.get_text('invalid_message_type', language=_get_current_language())}), 400

    except Exception as e:
        logger.error(f"Error in admin send message API: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/messages', methods=['GET'])
def api_admin_get_messages():
    """API for admin to get message history from website"""
    try:
        # Check admin access
        admin_id = session.get('user_id')
        if not admin_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('access_denied', language=_get_current_language())}), 403

        # Get message history
        messages = db.get_admin_messages_history(limit=50)

        return jsonify({
            'success': True,
            'messages': messages
        })

    except Exception as e:
        logger.error(f"Error getting admin messages: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500



@app.route('/api/deal/<deal_code>/cancel', methods=['POST'])
def api_cancel_deal(deal_code):
    """API for canceling a deal"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': localization.get_text('invalid_data', language=_get_current_language())}), 400

        # Check that the deal exists
        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'success': False, 'message': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        # Check if user is the buyer (only buyer can cancel)
        if deal['buyer_id'] != user_id:
            return jsonify({'success': False, 'message': localization.get_text('only_buyer_can_cancel', language=_get_current_language())}), 403

        # Check if deal can be cancelled
        if deal['status'] not in ['active', 'pending']:
            return jsonify({'success': False, 'message': localization.get_text('deal_cannot_be_cancelled', language=_get_current_language())}), 400

        # Cancel the deal
        success = db.update_deal_status(deal_code.upper(), 'cancelled')

        if success:
            # Notify seller if exists
            if deal.get('seller_id'):
                try:
                    from shared.notifications import notification_manager
                    from shared.async_utils import fire_and_forget
                    from shared.url_utils import get_deal_url

                    seller_id = deal['seller_id']
                    deal_code_upper = deal_code.upper()
                    seller_language = db.get_user_language(seller_id) or _get_current_language()

                    title = localization.get_text('deal_cancelled', language=seller_language)
                    reason_text = localization.get_text('cancelled_by_buyer', language=seller_language)
                    message = f"{localization.get_text('deal_cancelled_success_message', language=seller_language)}\n\n{reason_text}"

                    custom_keyboard = {
                        "inline_keyboard": [[
                            {
                                "text": localization.get_text('button_view_deal', seller_language, code=deal_code_upper),
                                "callback_data": f"ud_view_deal:{deal_code_upper}",
                            }
                        ]]
                    }

                    fire_and_forget(notification_manager.create_notification(
                        user_id=seller_id,
                        notification_type="deal_cancelled",
                        title=title,
                        message=message,
                        action_url=get_deal_url(deal_code_upper),
                        custom_keyboard=custom_keyboard,
                    ))
                except Exception as notify_error:
                    logger.warning(f"Failed to send deal-cancel notification for {deal_code}: {notify_error}")

            return jsonify({'success': True, 'message': localization.get_text('deal_cancelled', language=_get_current_language())})
        else:
            return jsonify({'success': False, 'message': localization.get_text('deal_cancel_error', language=_get_current_language())}), 500

    except Exception as e:
        logger.error(f"Error canceling deal {deal_code}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/deal/<deal_code>/confirm-delivery', methods=['POST'])
def api_confirm_delivery(deal_code):
    """API for seller confirming delivery"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': localization.get_text('invalid_data', language=_get_current_language())}), 400

        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'success': False, 'message': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        # Check if user is the seller
        if deal.get('seller_id') != user_id:
            return jsonify({
                'success': False,
                'message': localization.get_text('only_seller_can_confirm_delivery', language=_get_current_language()),
            }), 403

        # Check if deal is in correct status
        if deal.get('status') not in ['funded', 'delivery_pending']:
            return jsonify({
                'success': False,
                'message': localization.get_text('deal_not_ready_for_delivery_confirmation', language=_get_current_language()),
            }), 400

        # Update deal status to receipt_pending
        success = db.update_deal_status(deal_code.upper(), 'receipt_pending')
        if not success:
            return jsonify({
                'success': False,
                'message': localization.get_text('failed_to_update_deal_status', language=_get_current_language()),
            }), 500

        # Notify buyer
        try:
            from shared.notifications import notification_manager
            from shared.url_utils import get_deal_url
            from shared.async_utils import fire_and_forget

            buyer_id = deal['buyer_id']
            deal_code_upper = deal_code.upper()
            buyer_language = db.get_user_language(buyer_id) or _get_current_language()

            title = localization.get_text('deal_update', buyer_language)
            message = localization.get_text('delivery_confirmed_buyer', buyer_language)
            custom_keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": localization.get_text('button_confirm_receipt', buyer_language),
                            "callback_data": f"ud_confirm_receipt:{deal_code_upper}",
                        }
                    ],
                    [
                        {
                            "text": localization.get_text('button_view_deal', buyer_language, code=deal_code_upper),
                            "callback_data": f"ud_view_deal:{deal_code_upper}",
                        }
                    ],
                ]
            }

            fire_and_forget(notification_manager.create_notification(
                user_id=buyer_id,
                notification_type="delivery_confirmed",
                title=title,
                message=message,
                action_url=get_deal_url(deal_code_upper),
                custom_keyboard=custom_keyboard,
            ))
        except Exception as notify_error:
            logger.warning(f"Failed to send delivery notification for {deal_code}: {notify_error}")

        return jsonify({
            'success': True,
            'message': localization.get_text('delivery_confirmed', language=_get_current_language()),
        })

    except Exception as e:
        logger.error(f"Error confirming delivery for deal {deal_code}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/deal/<deal_code>/confirm-receipt', methods=['POST'])
def api_confirm_receipt(deal_code):
    """API for buyer confirming receipt"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': localization.get_text('invalid_data', language=_get_current_language())}), 400

        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'success': False, 'message': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        # Check if user is the buyer
        if deal.get('buyer_id') != user_id:
            return jsonify({
                'success': False,
                'message': localization.get_text('only_buyer_can_confirm_receipt', language=_get_current_language()),
            }), 403

        # Check if deal is in receipt_pending status
        if deal.get('status') != 'receipt_pending':
            return jsonify({
                'success': False,
                'message': localization.get_text('deal_not_ready_for_receipt_confirmation', language=_get_current_language()),
            }), 400

        # Update deal status to funds_pending
        success = db.update_deal_status(deal_code.upper(), 'funds_pending')
        if not success:
            return jsonify({
                'success': False,
                'message': localization.get_text('failed_to_update_deal_status', language=_get_current_language()),
            }), 500

        # Notify seller
        seller_id = deal.get('seller_id')
        if seller_id:
            try:
                from shared.notifications import notification_manager
                from shared.url_utils import get_deal_url
                from shared.async_utils import fire_and_forget
                deal_code_upper = deal_code.upper()
                seller_language = db.get_user_language(seller_id) or _get_current_language()

                title = localization.get_text('deal_update', seller_language)
                message = localization.get_text('funds_released_seller', seller_language)
                custom_keyboard = {
                    "inline_keyboard": [
                        [
                            {
                                "text": localization.get_text('button_withdraw_to_wallet', seller_language),
                                "callback_data": f"ud_withdraw_wallet:{deal_code_upper}",
                            }
                        ],
                        [
                            {
                                "text": localization.get_text('button_view_deal', seller_language, code=deal_code_upper),
                                "callback_data": f"ud_view_deal:{deal_code_upper}",
                            }
                        ],
                    ]
                }

                fire_and_forget(notification_manager.create_notification(
                    user_id=seller_id,
                    notification_type="funds_released",
                    title=title,
                    message=message,
                    action_url=get_deal_url(deal_code_upper),
                    custom_keyboard=custom_keyboard,
                ))
            except Exception as notify_error:
                logger.warning(f"Failed to send funds-ready notification for {deal_code}: {notify_error}")

        return jsonify({
            'success': True,
            'message': localization.get_text('receipt_confirmed', language=_get_current_language()),
        })

    except Exception as e:
        logger.error(f"Error confirming receipt for deal {deal_code}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/deal/<deal_code>/withdraw', methods=['POST'])
def api_withdraw_funds(deal_code):
    """API for seller withdrawing funds"""
    try:
        user_id_raw = session.get('user_id')
        if not user_id_raw:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'success': False, 'message': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        # Check if user is the seller
        if deal.get('seller_id') != user_id:
            return jsonify({
                'success': False,
                'message': localization.get_text('only_seller_can_withdraw_funds', language=_get_current_language()),
            }), 403

        # Check if deal is in funds_pending status
        if deal.get('status') != 'funds_pending':
            return jsonify({
                'success': False,
                'message': localization.get_text('deal_not_ready_for_withdrawal', language=_get_current_language()),
            }), 400

        data = request.get_json(silent=True) or {}
        withdraw_method = data.get('method', 'wallet')  # 'wallet' only
        wallet_address = (data.get('address') or data.get('wallet_address') or '').strip()

        if withdraw_method == 'wallet':
            if not wallet_address:
                return jsonify({
                    'success': False,
                    'message': localization.get_text('enter_wallet_address', language=_get_current_language())
                }), 400
        else:
            return jsonify({
                'success': False,
                'message': localization.get_text('unsupported_withdrawal_method', language=_get_current_language()),
            }), 400

        currency = (deal.get('currency') or '').upper()
        if currency == 'USDT':
            wallet_prefix = 'T'
            wallet_length = '34'
            wallet_pattern = r'^T[a-zA-Z0-9]{33}$'
        elif currency == 'TON':
            wallet_prefix = 'UQ/EQ'
            wallet_length = '46-48'
            wallet_pattern = r'^(UQ|EQ)[a-zA-Z0-9_-]{46,48}$'
        else:
            wallet_prefix = ''
            wallet_length = ''
            wallet_pattern = r'.+'

        import re
        if not re.match(wallet_pattern, wallet_address):
            wallet_rules = localization.get_text(
                'wallet_address_rules',
                language=_get_current_language(),
                prefix=wallet_prefix,
                length=wallet_length
            )
            invalid_message = localization.get_text(
                'invalid_wallet_address',
                language=_get_current_language(),
                currency=currency or deal.get('currency'),
                error_message=wallet_rules
            )
            return jsonify({'success': False, 'message': invalid_message}), 400

        # Calculate amounts
        from shared.commission import get_commission_breakdown
        from shared.decentralized_payments import decentralized_payment_processor

        amount = float(deal['amount'])
        _, commission_amount, seller_amount = get_commission_breakdown(amount)
        commission_amount = round(float(commission_amount), 8)
        seller_amount = round(float(seller_amount), 8)

        success, tx_hash = decentralized_payment_processor.blockchain.send_funds(
            to_address=wallet_address,
            amount=seller_amount,
            currency=currency,
            memo=f"RELEASE-{deal_code.upper()}",
        )

        if not success:
            return jsonify({
                'success': False,
                'message': localization.get_text('withdrawal_error', language=_get_current_language())
            }), 502

        db.update_deal_status(
            deal_code.upper(),
            'completed',
            commission_amount=commission_amount,
            seller_amount=seller_amount,
            completed_at=datetime.now().isoformat()
        )

        message = localization.get_text('funds_sent_to_wallet', language=_get_current_language())

        # Notify both parties
        try:
            from shared.notifications import notification_manager
            from shared.url_utils import get_deal_url
            from shared.async_utils import fire_and_forget
            
            # Get buyer's language for translation
            buyer_language = db.get_user_language(deal['buyer_id'])
            buyer_title = localization.get_text('deal_buyer_completed_title', buyer_language) if localization else "🎉 Deal Completed!"
            buyer_message = localization.get_text('deal_buyer_completed_message', buyer_language, deal_code=deal_code.upper()) if localization else f"Your deal {deal_code.upper()} has been completed successfully!"
            
            custom_keyboard = {
                "inline_keyboard": [[
                    {
                        "text": localization.get_text('button_view_deal', buyer_language, code=deal_code.upper()),
                        "callback_data": f"ud_view_deal:{deal_code.upper()}",
                    }
                ]]
            }

            buyer_coro = notification_manager.create_notification(
                user_id=deal['buyer_id'],
                notification_type="deal_completed",
                title=buyer_title,
                message=buyer_message,
                action_url=get_deal_url(deal_code.upper()),
                custom_keyboard=custom_keyboard,
            )
            fire_and_forget(buyer_coro)
        except Exception as notify_error:
            logger.warning(f"Failed to send deal-complete notification for {deal_code}: {notify_error}")

        return jsonify({'success': True, 'message': message, 'tx_hash': tx_hash})

    except Exception as e:
        logger.error(f"Error withdrawing funds for deal {deal_code}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/settings/commission-rate')
def api_get_commission_rate():
    """API for getting current commission rate"""
    try:
        settings = db.get_settings()
        return jsonify({
            'commission_rate': settings.get('commission_rate', 0.05)
        })

    except Exception as e:
        logger.error(f"Error getting commission rate: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/stats')
def api_stats():
    """API for getting statistics"""
    try:
        stats = db.get_stats()
        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error in stats API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500


@app.route('/api/admin/analytics')
def api_admin_analytics():
    """API for admin analytics"""
    try:
        # Check admin access
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('admin_access_required', language=_get_current_language())}), 403

        period = request.args.get('period', '30d')
        analytics = db.get_admin_analytics(period)
        return jsonify(analytics)

    except Exception as e:
        logger.error(f"Error in admin analytics API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/deals')
def api_admin_deals():
    """API for admin to get all deals"""
    try:
        # Check admin authentication
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('admin_access_required', language=_get_current_language())}), 403

        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        search = request.args.get('search', '').strip()
        limit = int(request.args.get('limit', 15))
        offset = int(request.args.get('offset', 0))

        status_value = status_filter if status_filter != 'all' else None

        # Get all deals from database
        deals = db.get_all_deals(status=status_value, limit=limit, offset=offset, search=search)
        total_count = db.get_deals_count(status=status_value, search=search)

        return jsonify({
            'success': True,
            'deals': deals,
            'total_count': total_count,
            'limit': limit,
            'offset': offset
        })

    except Exception as e:
        logger.error(f"Error in admin deals API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/deals/<deal_code>/cancel', methods=['POST'])
def api_admin_cancel_deal(deal_code):
    """API for admin to cancel any deal"""
    try:
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('admin_access_required', language=_get_current_language())}), 403

        deal_code_clean = (deal_code or '').strip()
        deal_code_upper = deal_code_clean.upper()
        deal = db.get_deal(deal_code_upper)
        if not deal:
            try:
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM deals WHERE UPPER(deal_code) = ? LIMIT 1', (deal_code_upper,))
                    row = cursor.fetchone()
                    deal = dict(row) if row else None
            except Exception as lookup_error:
                logger.warning(f"Admin cancel lookup failed for {deal_code}: {lookup_error}")

        if not deal:
            return jsonify({'success': False, 'message': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        if deal.get('status') not in ['active', 'pending']:
            return jsonify({'success': False, 'message': localization.get_text('deal_cannot_be_cancelled', language=_get_current_language())}), 400

        deal_code_db = deal.get('deal_code') or deal_code_upper
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE deals SET status = ?, updated_at = ? WHERE deal_code = ?',
                    ('cancelled', datetime.now().isoformat(), deal_code_db)
                )
                conn.commit()
                success = cursor.rowcount > 0
        except Exception as update_error:
            logger.error(f"Admin cancel update failed for {deal_code_db}: {update_error}")
            success = False
        if not success:
            return jsonify({'success': False, 'message': localization.get_text('deal_cancel_error', language=_get_current_language())}), 500

        try:
            from shared.notifications import notification_manager
            from shared.async_utils import fire_and_forget
            reason = None
            buyer_id = deal.get('buyer_id')
            seller_id = deal.get('seller_id')
            if buyer_id:
                fire_and_forget(notification_manager.notify_deal_cancelled(
                    user_id=buyer_id,
                    deal_code=deal_code.upper(),
                    reason=reason
                ))
            if seller_id:
                fire_and_forget(notification_manager.notify_deal_cancelled(
                    user_id=seller_id,
                    deal_code=deal_code.upper(),
                    reason=reason
                ))
        except Exception as notify_error:
            logger.warning(f"Failed to send admin cancel notification for {deal_code}: {notify_error}")

        return jsonify({'success': True, 'message': localization.get_text('deal_cancelled', language=_get_current_language())})

    except Exception as e:
        logger.error(f"Error in admin deal cancel API: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/disputes')
def api_admin_disputes():
    """API for admin to get disputes list"""
    try:
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('admin_access_required', language=_get_current_language())}), 403

        status_filter = request.args.get('status', 'all')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        disputes = dispute_manager.get_all_disputes(
            status=status_filter if status_filter != 'all' else None,
            limit=limit,
            offset=offset
        )
        total_count = dispute_manager.get_disputes_count(status=status_filter)

        return jsonify({
            'success': True,
            'disputes': disputes,
            'total_count': total_count,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        logger.error(f"Error getting admin disputes: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/disputes/<int:dispute_id>')
def api_admin_dispute_detail(dispute_id):
    """API for admin to get dispute details"""
    try:
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('admin_access_required', language=_get_current_language())}), 403

        dispute = dispute_manager.get_dispute_by_id(dispute_id)
        if not dispute:
            return jsonify({
                'success': False,
                'message': localization.get_text('dispute_not_found', language=_get_current_language()),
            }), 404

        return jsonify({'success': True, 'dispute': dispute})
    except Exception as e:
        logger.error(f"Error getting dispute {dispute_id}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/admin/disputes/<int:dispute_id>/resolve', methods=['POST'])
def api_admin_resolve_dispute(dispute_id):
    """API for admin to resolve a dispute with response"""
    try:
        user_id = session.get('user_id')
        if not user_id or not is_user_admin():
            return jsonify({'error': localization.get_text('admin_access_required', language=_get_current_language())}), 403

        data = request.get_json() or {}
        response_text = (data.get('response') or '').strip()

        if len(response_text) < 10:
            return jsonify({
                'success': False,
                'message': localization.get_text('admin_response_too_short', language=_get_current_language()),
            }), 400
        if len(response_text) > 1000:
            return jsonify({
                'success': False,
                'message': localization.get_text('admin_response_too_long', language=_get_current_language()),
            }), 400

        dispute = dispute_manager.get_dispute_by_id(dispute_id)
        if not dispute:
            return jsonify({
                'success': False,
                'message': localization.get_text('dispute_not_found', language=_get_current_language()),
            }), 404

        # Save response and update statuses
        if not dispute_manager.add_dispute_response(dispute_id, user_id, response_text):
            return jsonify({
                'success': False,
                'message': localization.get_text('failed_to_add_response', language=_get_current_language()),
            }), 500

        dispute_manager.update_dispute_status(dispute_id, 'resolved')
        db.update_deal_status(dispute['deal_code'], 'dispute_resolved')

        # Notify both parties
        try:
            from shared.notifications import notification_manager
            from shared.async_utils import fire_and_forget

            def format_dispute_response(target_language: str) -> tuple[str, str]:
                title = localization.get_text(
                    'dispute_response_title',
                    target_language,
                    deal_code=dispute['deal_code'],
                )
                message = (
                    f"{escape_html(response_text)}\n\n"
                    f"🆔 <b>{localization.get_text('admin_dispute_id', target_language)}:</b> #{dispute_id}\n"
                    f"📄 <b>{localization.get_text('admin_deal_code', target_language)}:</b> {escape_html(dispute['deal_code'])}\n\n"
                    f"ℹ️ {localization.get_text('dispute_resolved_note', target_language)}"
                )
                return title, message

            async def notify_party(target_id: int):
                target_language = db.get_user_language(target_id) or _get_current_language()
                title, message = format_dispute_response(target_language)
                await notification_manager.create_notification(
                    user_id=target_id,
                    notification_type="dispute_response",
                    title=title,
                    message=message,
                    action_url=f"/deal/{dispute['deal_code']}"
                )

            fire_and_forget(notify_party(dispute['buyer_id']))
            if dispute.get('seller_id'):
                fire_and_forget(notify_party(dispute['seller_id']))
        except Exception as notify_error:
            logger.warning(f"Failed to notify dispute parties for {dispute_id}: {notify_error}")

        return jsonify({
            'success': True,
            'message': localization.get_text('dispute_resolved_success', language=_get_current_language()),
        })

    except Exception as e:
        logger.error(f"Error resolving dispute {dispute_id}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

# === NOTIFICATION ROUTES ===

@app.route('/api/notifications')
def api_notifications():
    """API for getting user notifications"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401
    
        # Get real notifications from database
        notifications = db.get_user_notifications(user_id)

        return jsonify({'notifications': notifications})

    except Exception as e:
        logger.error(f"Error in notifications API: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/notifications/<notification_id>/dismiss', methods=['POST'])
def api_dismiss_notification(notification_id):
    """API for dismissing a notification"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

        # Mark notification as read in database
        success = db.mark_notification_read(int(notification_id), user_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': localization.get_text('notification_not_found', language=_get_current_language())}), 404

    except Exception as e:
        logger.error(f"Error dismissing notification {notification_id}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500


@app.route('/api/notifications/mark-all-read', methods=['POST'])
def api_mark_all_notifications_read():
    """API for marking all notifications as read"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

        # Mark all notifications as read in database
        updated_count = db.mark_all_notifications_read(user_id)
        return jsonify({'success': True, 'message': localization.get_text('notifications_marked_read', language=_get_current_language(), count=updated_count)})

    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/notifications/clear-all', methods=['POST'])
def api_clear_all_notifications():
    """API for clearing all notifications"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

        # Delete all user notifications from database
        deleted_count = db.delete_all_notifications(user_id)
        return jsonify({'success': True, 'message': localization.get_text('notifications_cleared', language=_get_current_language(), count=deleted_count)})

    except Exception as e:
        logger.error(f"Error clearing all notifications: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/notifications/delete-multiple', methods=['POST'])
def api_delete_multiple_notifications():
    """API for deleting multiple selected notifications"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

        data = request.get_json()
        notification_ids = data.get('notification_ids', [])

        if not notification_ids:
            return jsonify({'success': False, 'message': localization.get_text('no_notifications_selected', language=_get_current_language())}), 400

        # Validate that all IDs are integers
        try:
            notification_ids = [int(nid) for nid in notification_ids]
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': localization.get_text('invalid_notification_ids', language=_get_current_language())}), 400

        # Delete selected notifications from database
        deleted_count = db.delete_multiple_notifications(user_id, notification_ids)
        return jsonify({'success': True, 'message': localization.get_text('notifications_deleted', language=_get_current_language(), count=deleted_count)})

    except Exception as e:
        logger.error(f"Error deleting multiple notifications: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@app.route('/api/notifications/stream')
def api_notifications_stream():
    """Server-Sent Events endpoint for real-time notifications"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401

    def generate():
        last_count = 0
        while True:
            try:
                # Get current unread count
                current_count = db.get_unread_notifications_count(user_id)

                # If count changed, send update
                if current_count != last_count:
                    yield f"data: {{\"unread_count\": {current_count}}}\n\n"
                    last_count = current_count

                # Sleep for 5 seconds before next check
                import time
                time.sleep(5)

            except Exception as e:
                logger.error(f"Error in notification stream: {e}")
                break

    return app.response_class(generate(), mimetype='text/event-stream')

@app.route('/api/support/messages', methods=['GET'])
def api_get_support_messages():
    """API for getting support chat messages"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        # Check if admin is requesting messages for a specific user
        target_user_id = request.args.get('user_id')
        is_admin_viewing = False

        if target_user_id and is_user_admin():
            user_id = target_user_id
            is_admin_viewing = True
        elif target_user_id and not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('insufficient_permissions', language=_get_current_language())}), 403

        messages = db.get_support_messages(user_id)
        unread_count = db.get_unread_support_messages_count(user_id, is_admin=is_admin_viewing)

        # Mark messages as read when viewed
        if is_admin_viewing:
            # Admin is viewing user messages - mark user messages as read by admin
            db.mark_support_messages_read(user_id, is_admin=True)
        else:
            # User is viewing their messages - mark admin messages as read by user
            db.mark_support_messages_read(user_id, is_admin=False)

        return jsonify({
            'success': True,
            'messages': messages,
            'unread_count': unread_count
        })

    except Exception as e:
        logger.error(f"Error getting support messages: {e}")
        return jsonify({'success': False, 'message': localization.get_text('error_getting_messages', language=_get_current_language())}), 500

@app.route('/api/support/send-message', methods=['POST'])
def api_send_support_message():
    """API for sending support messages"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        # Rate limiting: max 20 support messages per hour per user
        if not check_rate_limit(f"support:{user_id}", limit=20, window=3600):
            return jsonify({'success': False, 'message': localization.get_text('support_message_rate_limit', language=_get_current_language())}), 429

        data = request.get_json()
        message = data.get('message', '').strip()

        if not message or len(message) < 1:
            return jsonify({'success': False, 'message': localization.get_text('message_cannot_be_empty', language=_get_current_language())}), 400

        if len(message) > 1000:
            return jsonify({'success': False, 'message': localization.get_text('message_too_long', language=_get_current_language())}), 400

        # Save the user's message
        success = db.save_support_message(user_id, message, is_from_user=True)

        if not success:
            return jsonify({'success': False, 'message': localization.get_text('message_save_error', language=_get_current_language())}), 500

        # Fetch user data for notification
        user = db.get_user(user_id)

        # Create a notification for the admin
        f"""
📞 New support message

👤 User: {user.get('first_name', 'Unknown')} (@{user.get('username', 'unknown')})
🆔 ID: {user_id}

💬 Message:
{message}

⏰ Time: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""

        # Send notification to the admin
        try:
            from shared.notifications import notification_manager
            from shared.async_utils import fire_and_forget
            fire_and_forget(notification_manager.create_notification(
                user_id=ADMIN_ID,
                notification_type="support",
                title=localization.get_text('new_support_message', language='en'),
                message=f"User {user.get('first_name', 'Unknown')} (@{user.get('username', 'unknown')}) sent a message: {message[:100]}{'...' if len(message) > 100 else ''}",
                action_url="/admin/support"
            ))
        except Exception as notify_error:
            logger.warning(f"Failed to notify admin: {notify_error}")

        logger.info(f"Support message from user {user_id}: {message[:100]}...")

        return jsonify({
            'success': True,
            'message': localization.get_text('message_sent', language=_get_current_language())
        })

    except Exception as e:
        logger.error(f"Error sending support message: {e}")
        return jsonify({'success': False, 'message': localization.get_text('error_sending_message', language=_get_current_language())}), 500

@app.route('/api/support/admin/send-message', methods=['POST'])
def api_admin_send_support_message():
    """API for admin to send support messages"""
    try:
        # Admin permission check
        admin_id = session.get('user_id')
        if not admin_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        if not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('insufficient_permissions', language=_get_current_language())}), 403

        data = request.get_json()
        user_id = data.get('user_id')
        message = data.get('message', '').strip()

        if not user_id or not message:
            return jsonify({'success': False, 'message': localization.get_text('invalid_data', language=_get_current_language())}), 400
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': localization.get_text('invalid_data', language=_get_current_language())}), 400

        if len(message) > 1000:
            return jsonify({'success': False, 'message': localization.get_text('message_too_long', language=_get_current_language())}), 400

        # Save the admin message
        success = db.save_support_message(user_id, message, is_from_user=False)

        if not success:
            return jsonify({'success': False, 'message': localization.get_text('message_save_error', language=_get_current_language())}), 500

        # Send the message to the user in Telegram
        try:
            import aiohttp
            from shared.config import BOT_TOKEN
            import asyncio

            async def send_telegram_message():
                logger.info(f"Starting to send Telegram message to user {user_id}")
                if not BOT_TOKEN:
                    logger.error("BOT_TOKEN not configured for sending admin message")
                    return

                user_language = db.get_user_language(user_id) if db else localization.default_language
                prefix = localization.get_text('support_admin_message_prefix', language=user_language) if localization else 'Support'
                telegram_message = f"💬 <b>{prefix}</b>\n\n{escape_html(message)}"
                logger.info(f"Prepared message for user {user_id}: {telegram_message[:100]}...")

                try:
                    async with aiohttp.ClientSession() as session:
                        data = {
                            "chat_id": int(user_id),
                            "text": telegram_message,
                            "parse_mode": "HTML"
                        }

                        logger.info(f"Sending Telegram message to user {user_id} via API")
                        async with session.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json=data,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            response_text = await response.text()
                            if response.status != 200:
                                logger.error(f"Failed to send Telegram message to user {user_id}: HTTP {response.status} - {response_text}")
                            else:
                                logger.info(f"Telegram message sent successfully to user {user_id}")

                except asyncio.TimeoutError:
                    logger.error(f"Timeout sending Telegram message to user {user_id}")
                except Exception as e:
                    logger.error(f"Error sending Telegram message to user {user_id}: {e}")

            # Send the message in the background
            logger.info(f"Initiating background task to send message to user {user_id}")
            threading.Thread(
                target=lambda: asyncio.run(send_telegram_message()),
                daemon=True
            ).start()

        except Exception as notify_error:
            logger.error(f"Failed to initiate Telegram message sending to user {user_id}: {notify_error}")

        return jsonify({'success': True, 'message': localization.get_text('message_sent', language=_get_current_language())})

    except Exception as e:
        logger.error(f"Error sending admin support message: {e}")
        return jsonify({'success': False, 'message': localization.get_text('message_send_error', language=_get_current_language())}), 500

@app.route('/api/support/conversations', methods=['GET'])
def api_get_support_conversations():
    """API for admin to get all support conversations"""
    try:
        # Admin permission check
        admin_id = session.get('user_id')
        if not admin_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        if not is_user_admin():
            return jsonify({'success': False, 'message': localization.get_text('insufficient_permissions', language=_get_current_language())}), 403

        conversations = db.get_all_support_conversations()

        return jsonify({
            'success': True,
            'conversations': conversations
        })

    except Exception as e:
        logger.error(f"Error getting support conversations: {e}")
        return jsonify({'success': False, 'message': localization.get_text('error_getting_conversations', language=_get_current_language())}), 500

@app.route('/api/support/mark-read', methods=['POST'])
def api_mark_support_messages_read():
    """API for marking support messages as read when user enters chat"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        # Mark all admin messages as read
        db.mark_support_messages_read(user_id)

        return jsonify({'success': True, 'message': localization.get_text('messages_marked_read', language=_get_current_language())})

    except Exception as e:
        logger.error(f"Error marking support messages as read: {e}")
        return jsonify({'success': False, 'message': localization.get_text('error_marking_messages', language=_get_current_language())}), 500

# === HEALTH CHECK ENDPOINTS ===

@app.route('/health')
async def health_check():
    """Basic health check endpoint"""
    try:
        result, status_code = await health_endpoint()
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Health check endpoint error: {e}")
        return jsonify({
            'summary': {'overall_status': 'error', 'error': str(e)},
            'checks': {}
        }), 503

@app.route('/health/detailed')
async def detailed_health_check():
    """Detailed health check endpoint"""
    try:
        result, status_code = await detailed_health_endpoint()
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Detailed health check endpoint error: {e}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503

@app.route('/api/health/status')
async def api_health_status():
    """API endpoint for health status"""
    try:
        result, status_code = await health_endpoint()
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"API health status error: {e}")
        return jsonify({'error': str(e)}), 503

@app.route('/api/health/check/<check_name>')
async def api_health_check_specific(check_name):
    """API endpoint for specific health check"""
    try:
        result = await health_checker.run_check(check_name)
        if result:
            status_code = 200 if result['status'] == 'healthy' else 503
            return jsonify(result), status_code
        else:
            return jsonify({'error': localization.get_text('health_check_not_found', language=_get_current_language())}), 404
    except Exception as e:
        logger.error(f"Specific health check error for {check_name}: {e}")
        return jsonify({'error': str(e)}), 503


@app.route('/api/debug/telegram-test', methods=['POST'])
def api_debug_telegram_test():
    """Local-only debug endpoint: sends a Telegram message to the current session user."""
    try:
        if request.remote_addr not in ("127.0.0.1", "::1"):
            return jsonify({'success': False, 'message': 'Not found'}), 404

        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        from shared.notifications import notification_manager
        text = f"DEBUG: Telegram test message at {datetime.now(timezone.utc).isoformat()}"
        ok = notification_manager.send_telegram_notification_sync(
            user_id=int(user_id),
            title="Debug",
            message=text,
            action_url=None,
            custom_keyboard=None,
            timeout=10.0,
        )
        return jsonify({'success': bool(ok), 'user_id': int(user_id)}), (200 if ok else 502)

    except Exception as e:
        logger.error(f"Telegram debug test error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/support')
def support():
    """Support chat page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required_support', language=_get_current_language()), 'error')
        return redirect(url_for('index'))
    # Diagnostic: render without page-specific JS (Telegram Android WebView "duck" debugging).
    if request.args.get('lite') == '1':
        return render_template('telegram_lite_page.html', target_path='/support')
    return render_template('support.html')


@app.route('/admin')
def admin():
    """Admin panel page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin.html')

@app.route('/admin/settings')
def admin_settings():
    """Admin settings page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin_settings.html')

@app.route('/admin/users')
def admin_users():
    """Admin users management page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin_users.html')

@app.route('/admin/users/<int:user_id>')
def admin_user_detail(user_id):
    """Admin user detail page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin_user_detail.html', user_id=user_id)

@app.route('/admin/support')
def admin_support():
    """Admin support chat page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin_support.html')

@app.route('/admin/deals')
def admin_deals():
    """Admin deals management page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin_deals.html')

@app.route('/admin/disputes')
def admin_disputes():
    """Admin disputes management page"""
    if not session.get('user_id'):
        flash(localization.get_text('login_required', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    if not is_user_admin():
        flash(localization.get_text('no_admin_access', language=_get_current_language()), 'error')
        return redirect(url_for('index'))

    return render_template('admin_disputes.html')

@app.route('/test-join-deal')
def test_join_deal():
    """Test route for join deal template inheritance"""
    return render_template('join-deal-test.html')


# === CROSS-PLATFORM API INTEGRATION ===

try:
    from web.cross_platform_api import cross_platform_bp
    app.register_blueprint(cross_platform_bp)
    logger.info("Cross-platform API blueprint registered")

    # Register join deal blueprint
    from web.join_deal import join_deal_bp
    app.register_blueprint(join_deal_bp)
    logger.info("Join deal blueprint registered")

    # Cross-platform sync initialization is now handled by the enhanced app
    # to avoid event loop conflicts

except ImportError as e:
    logger.warning(f"Cross-platform API not available: {e}")

# === WEBHOOKS ===

@app.route('/api/payments/webhook', methods=['POST'])
def payment_webhook():
    """Webhook endpoint removed - payments now use system wallet verification via blockchain APIs"""
    try:
        return jsonify({
            'status': 'disabled',
            'message': localization.get_text('webhook_disabled', language=_get_current_language()),
        }), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': localization.get_text('webhook_disabled', language=_get_current_language())}), 200


# === ERROR HANDLERS ===

@app.errorhandler(404)
def page_not_found(e):
    """404 error handler"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    """500 error handler"""
    logger.error(f"Internal error: {e}")
    return render_template('500.html'), 500

# === APPLICATION STARTUP ===

if __name__ == '__main__':
    # Check configuration
    if not validate_config():
        logger.error("Configuration error. Shutting down.")
        exit(1)

    logger.info("Starting Black Diamond web application...")

    # Start health monitoring
    try:
        start_health_monitoring(interval=60)  # Check every 60 seconds
        logger.info("Health monitoring started")
    except Exception as e:
        logger.warning(f"Failed to start health monitoring: {e}")

    try:
        # Configure for Cloudflare deployment
        print("[INFO] Starting web application for Cloudflare deployment")

        try:
            from shared.qr_code_cleanup import qr_code_cleanup_service
            qr_code_cleanup_service.start()
        except Exception as e:
            logger.warning(f"Failed to start QR code cleanup: {e}")
        
        # Check if using Cloudflare SSL mode
        cloudflare_mode = os.getenv('CLOUDFLARE_MODE', '').lower() == 'true'
        ssl_cert = os.getenv('SSL_CERT_PATH')
        ssl_key = os.getenv('SSL_KEY_PATH')
        
        if cloudflare_mode or (not ssl_cert or not ssl_key):
            # Cloudflare handles SSL termination - run on HTTP
            print("[INFO] Running in Cloudflare mode - Cloudflare handles HTTPS")
            print(f"[INFO] Origin server running on HTTP port {WEB_PORT}")
            app.run(
                host=WEB_HOST,
                port=WEB_PORT,
                debug=WEB_DEBUG
            )
        elif ssl_cert and ssl_key and os.path.exists(ssl_cert) and os.path.exists(ssl_key):
            # Run with SSL (self-hosted certificate)
            print(f"[INFO] Starting with SSL certificate: {ssl_cert}")
            app.run(
                host=WEB_HOST,
                port=WEB_PORT,
                debug=WEB_DEBUG,
                ssl_context=(ssl_cert, ssl_key)
            )
        else:
            # Run without SSL (fallback)
            print("[INFO] Starting without SSL - using HTTP")
            app.run(
                host=WEB_HOST,
                port=WEB_PORT,
                debug=WEB_DEBUG
            )
    except Exception as e:
        logger.error(f"Error starting web application: {e}")
        exit(1)

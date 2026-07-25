import os
from typing import Dict, Any

# === APPLICATION CONSTANTS ===
BOT_NAME = "Black Diamond"
BOT_USERNAME = "@BlackDiamondBot"
COMPANY_NAME = "Black Diamond"

# === CURRENCY TOLERANCES ===
# Tolerance for payment amount validation (to handle blockchain rounding)
USDT_TOLERANCE = 0.01
TON_TOLERANCE = 0.001

def get_currency_tolerance(currency: str) -> float:
    """Get tolerance for specific currency"""
    tolerances = {
        'USDT': USDT_TOLERANCE,
        'TON': TON_TOLERANCE,
        'TRX': USDT_TOLERANCE,  # TRX uses same tolerance as USDT
        'ETH': TON_TOLERANCE,   # ETH uses same tolerance as TON
    }
    return tolerances.get(currency.upper(), USDT_TOLERANCE)

# === COMMISSION RATES ===
DEFAULT_COMMISSION_RATE = 0.05  # 5%
MAX_COMMISSION_RATE = 0.10      # 10%
MIN_COMMISSION_RATE = 0.0       # 0%

# === DEAL AMOUNT LIMITS ===
MIN_DEAL_AMOUNT = float(os.getenv('MIN_DEAL_AMOUNT', '1.0'))
MAX_DEAL_AMOUNT = float(os.getenv('MAX_DEAL_AMOUNT', '10000.0'))

# === TIME CONSTANTS (in seconds) ===
PAYMENT_TIMEOUT = 3600           # 1 hour
AUTO_CONFIRM_TIMEOUT = 3600      # 1 hour
AUTO_RELEASE_TIMEOUT = 86400     # 24 hours
CURRENCY_UPDATE_INTERVAL = 3600  # 1 hour
CSRF_TOKEN_TIMEOUT = 3600        # 1 hour
TOKEN_VALIDITY = 3600           # 1 hour

# === TIMEOUT LIMITS ===
MIN_TIMEOUT_VALUE = 60           # 1 minute minimum
MAX_TIMEOUT_VALUE = 86400        # 24 hours maximum

# === RATE LIMITS ===
# API rate limits (requests per hour)
CREATE_DEAL_RATE_LIMIT = 5
JOIN_DEAL_RATE_LIMIT = 10
SUPPORT_MESSAGE_RATE_LIMIT = 20
GLOBAL_RATE_LIMIT = 1000

# Admin broadcast rate limit
ADMIN_BROADCAST_RATE_LIMIT = 100

# === PAGINATION ===
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 100
MIN_PER_PAGE = 1

# === ADMIN PAGINATION ===
DEFAULT_USERS_PER_PAGE = 50
MAX_USERS_PER_PAGE = 100
DEFAULT_ADMIN_DEALS_LIMIT = 15

# === ADMIN LIMITS ===
MAX_BALANCE_ADJUSTMENT = 10000
MAX_ADMIN_MESSAGE_LENGTH = 1000
MAX_MESSAGE_LENGTH = 1000

# === ADMIN HISTORY LIMITS ===
ADMIN_MESSAGES_HISTORY_LIMIT = 50
WITHDRAWAL_HISTORY_LIMIT = 50
RECENT_OPERATIONS_LIMIT = 10

# === VALIDATION LIMITS ===
MIN_USER_ID = 1
MAX_USER_ID = 999999999999

# === QR CODE SETTINGS ===
QR_CODE_VERSION = 1
QR_CODE_BOX_SIZE = 10
QR_CODE_BORDER = 4

# QR Code error correction levels
QR_ERROR_CORRECT_L = 'L'  # Low (~7% error correction)
QR_ERROR_CORRECT_M = 'M'  # Medium (~15% error correction) 
QR_ERROR_CORRECT_Q = 'Q'  # Quartile (~25% error correction)
QR_ERROR_CORRECT_H = 'H'  # High (~30% error correction)

# === BLOCKCHAIN CONSTANTS ===
TRON_MAINNET = 'https://api.trongrid.io'
TON_NETWORK = 'mainnet'

# Minimum withdrawal amounts
MIN_WITHDRAWAL_USDT = 1.0
MIN_WITHDRAWAL_TON = 0.1
MIN_WITHDRAWAL_ETH = 0.01

# === FILE PATHS ===
STATIC_QR_CODES_DIR = '/static/qr_codes'

# === DATABASE CONSTANTS ===
DB_POOL_MIN_SIZE = 5
DB_POOL_MAX_SIZE = 20
DB_CONNECTION_TIMEOUT = 30
DB_CACHE_TTL = 300  # 5 minutes

# === PERFORMANCE THRESHOLDS ===
CPU_THRESHOLD = 80.0
MEMORY_THRESHOLD = 85.0
DISK_THRESHOLD = 90.0
DATABASE_CONN_THRESHOLD = 80.0
SLOW_QUERY_THRESHOLD = 1.0  # seconds

# === MESSAGE PRIORITIES ===
PRIORITY_LOWEST = 0
PRIORITY_LOW = 1
PRIORITY_NORMAL = 2
PRIORITY_HIGH = 3
PRIORITY_CRITICAL = 4

# === RETRY CONFIGURATION ===
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0

# === CACHE SETTINGS ===
CACHE_STATS_TTL = 120      # 2 minutes
CACHE_DEALS_TTL = 60       # 1 minute
CACHE_NOTIFICATIONS_TTL = 30  # 30 seconds

# === USER SPECIFIC CACHE DURATIONS ===
USER_DEALS_CACHE_DURATION = 120    # 2 minutes
ANALYTICS_CACHE_DURATION = 600     # 10 minutes


# === CURRENCY CONFIGURATION ===
ALL_SUPPORTED_CURRENCIES = ['USDT', 'TON', 'TRX', 'ETH']

def _parse_enabled_currencies() -> list:
    raw = os.getenv('ENABLED_CURRENCIES', 'TON')
    enabled = [currency.strip().upper() for currency in raw.split(',') if currency.strip()]
    return enabled or ['TON']

ENABLED_CURRENCIES = _parse_enabled_currencies()
SUPPORTED_CURRENCIES = [currency for currency in ENABLED_CURRENCIES if currency in ALL_SUPPORTED_CURRENCIES]
if not SUPPORTED_CURRENCIES:
    SUPPORTED_CURRENCIES = ['TON']
DEFAULT_CURRENCY = SUPPORTED_CURRENCIES[0]
DEFAULT_ANALYTICS_PERIOD = 30     # Default analytics period in days

# === AUTH CONSTANTS ===
WEBAPP_AUTH_RATE_LIMIT = 10
WEBAPP_AUTH_WINDOW = 60  # 1 minute
TOKEN_AUTH_RATE_LIMIT = 10
TOKEN_AUTH_WINDOW = 60  # 1 minute
AUTH_DATA_VALIDITY_WINDOW = 86400  # 24 hours

# === USER VALIDATION CONSTANTS ===
MAX_FIRST_NAME_LENGTH = 100
MAX_USERNAME_LENGTH = 50
MAX_USER_ID = 999999999999
MAX_PAYLOAD_FIELDS = 10

# === TOKEN CONSTANTS ===
TOKEN_LENGTH = 16
TEST_USER_ID = 12345
TEST_USERNAME = 'test_user'
TEST_FIRST_NAME = 'Test User'

# === ADMIN CONSTANTS ===
ADMIN_ID = 7666768819
DEFAULT_ADMIN_ID = 7666768819
RATE_LIMIT_WINDOW = 3600          # 1 hour in seconds

# === LOGGING LEVELS ===
LOG_LEVEL_INFO = 'INFO'
LOG_LEVEL_WARNING = 'WARNING'
LOG_LEVEL_ERROR = 'ERROR'
LOG_LEVEL_DEBUG = 'DEBUG'

# === RESPONSE STATUS CODES ===
STATUS_SUCCESS = 200
STATUS_BAD_REQUEST = 400
STATUS_UNAUTHORIZED = 401
STATUS_FORBIDDEN = 403
STATUS_NOT_FOUND = 404
STATUS_RATE_LIMIT = 429
STATUS_INTERNAL_ERROR = 500

# === REGEX PATTERNS ===
USDT_ADDRESS_PATTERN = r'^T[A-Za-z1-9]{33}$'
TON_ADDRESS_PATTERN = r'^UQ[A-Za-z0-9_-]{46}$'
DEAL_CODE_PATTERN = r'^[A-Z0-9]{6,12}$'
MEMO_PATTERN = r'^DEAL-[A-Z0-9]{6,12}$'

# === CONFIGURATION DEFAULTS ===
DEFAULT_CONFIG = {
    'commission_rate': DEFAULT_COMMISSION_RATE,
    'min_deal_amount': MIN_DEAL_AMOUNT,
    'max_deal_amount': MAX_DEAL_AMOUNT,
    'auto_confirm_timeout': AUTO_CONFIRM_TIMEOUT,
    'currency_update_interval': CURRENCY_UPDATE_INTERVAL,
    'payment_timeout': PAYMENT_TIMEOUT,
}

def validate_config() -> Dict[str, Any]:
    """Validate and return current configuration"""
    return {
        **DEFAULT_CONFIG,
        'usdt_tolerance': USDT_TOLERANCE,
        'ton_tolerance': TON_TOLERANCE,
        'supported_currencies': SUPPORTED_CURRENCIES,
        'default_currency': DEFAULT_CURRENCY,
    }

def get_rate_limit(operation: str) -> tuple:
    """Get rate limit for specific operation (limit, window_seconds)"""
    rate_limits = {
        'create_deal': (CREATE_DEAL_RATE_LIMIT, 3600),
        'join_deal': (JOIN_DEAL_RATE_LIMIT, 3600),
        'support_message': (SUPPORT_MESSAGE_RATE_LIMIT, 3600),
        'global': (GLOBAL_RATE_LIMIT, 3600),
        'admin_broadcast': (ADMIN_BROADCAST_RATE_LIMIT, 3600),
    }
    return rate_limits.get(operation, (10, 3600))  # Default: 10 per hour

def validate_amount(amount: float, currency: str = 'USDT') -> bool:
    """Validate amount is within allowed limits"""
    if amount <= 0:
        return False
    
    tolerance = get_currency_tolerance(currency)
    min_amount = MIN_DEAL_AMOUNT + tolerance
    max_amount = MAX_DEAL_AMOUNT
    
    return min_amount <= amount <= max_amount

def format_currency(amount: float, currency: str) -> str:
    """Format currency amount for display"""
    if currency.upper() in ['USDT', 'TRX']:
        return f"{amount:.2f} {currency}"
    elif currency.upper() in ['TON', 'ETH']:
        return f"{amount:.4f} {currency}"
    else:
        return f"{amount:.2f} {currency}"

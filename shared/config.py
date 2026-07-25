import logging
import os

from shared.localization import localization
from shared.secure_config import migrate_to_secure_config, secure_config

logger = logging.getLogger(__name__)

# Run migration to secure config on first import
try:
    migrate_to_secure_config()
except Exception as e:
    logger.warning(f"Failed to run config migration: {e}")

# === BASIC SETTINGS ===
BOT_TOKEN = secure_config.get("BOT_TOKEN", secure=True)
ADMIN_ID = int(secure_config.get("ADMIN_ID", "0", secure=True) or 0)
BOT_NAME = secure_config.get("BOT_NAME", localization.get_text("bot_name", "en"))
BOT_USERNAME = secure_config.get("BOT_USERNAME", "@BlackDiamondGarantBot")

# === BLOCKCHAIN API KEYS ===
TRONGRID_API_KEY = secure_config.get("TRONGRID_API_KEY", secure=True)  # For USDT via TRON
TONCENTER_API_KEY = secure_config.get("TONCENTER_API_KEY", secure=True)  # For TON via TonCenter

# === WALLET ADDRESSES ===
USDT_WALLET_ADDRESS = secure_config.get("USDT_WALLET_ADDRESS", secure=True)
TON_WALLET_ADDRESS = secure_config.get("TON_WALLET_ADDRESS", secure=True)
USDT_SYSTEM_ADDRESS = secure_config.get(
    "USDT_SYSTEM_ADDRESS", USDT_WALLET_ADDRESS, secure=True
)
TON_SYSTEM_ADDRESS = secure_config.get("TON_SYSTEM_ADDRESS", TON_WALLET_ADDRESS, secure=True)

# === WALLET PRIVATE KEYS ===
USDT_PRIVATE_KEY = secure_config.get("USDT_PRIVATE_KEY", secure=True)
TON_PRIVATE_KEY = secure_config.get("TON_PRIVATE_KEY", secure=True)

# === DATABASE ===
DATABASE_URL = secure_config.get("DATABASE_URL", "sqlite:///black_diamond.db")

# === SECURITY ===
SECRET_KEY = secure_config.get("SECRET_KEY", secure=True)
if not SECRET_KEY:
    import secrets
    import string

    SECRET_KEY = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
    )
    secure_config.set("SECRET_KEY", SECRET_KEY, secure=True, category="security")

SESSION_SECRET = secure_config.get("SESSION_SECRET", secure=True)
if not SESSION_SECRET:
    import secrets
    import string

    SESSION_SECRET = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
    )
    secure_config.set(
        "SESSION_SECRET", SESSION_SECRET, secure=True, category="security"
    )

# === PAYMENT SETTINGS ===
COMMISSION_RATE = float(os.getenv("COMMISSION_RATE", 0.07))  # 7% - default commission
MIN_DEAL_AMOUNT = float(os.getenv("MIN_DEAL_AMOUNT", 1.0))
MAX_DEAL_AMOUNT = float(os.getenv("MAX_DEAL_AMOUNT", 10000.0))
PAYMENT_TIMEOUT = int(os.getenv("PAYMENT_TIMEOUT", 3600))  # 1 hour
AUTO_CONFIRM_TIMEOUT = int(os.getenv("AUTO_CONFIRM_TIMEOUT", 3600))

# === EXCHANGE RATES ===
EXCHANGE_UPDATE_INTERVAL = int(os.getenv("EXCHANGE_UPDATE_INTERVAL", 3600))

# === LOGGING ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "black_diamond.log")

# === WEB SERVER ===
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", 5000))
WEB_DEBUG = os.getenv("WEB_DEBUG", "true").lower() == "true"

# BASE_URL is for internal use; default is localhost.
BASE_URL = os.getenv("BASE_URL", "http://localhost")

# Public URL for login links (used in bot messages)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", BASE_URL)

if PUBLIC_BASE_URL and not (
    str(PUBLIC_BASE_URL).startswith("http://") or str(PUBLIC_BASE_URL).startswith("https://")
):
    # Keep config forgiving if only a hostname is provided
    PUBLIC_BASE_URL = f"https://{PUBLIC_BASE_URL}"


# === SUPPORTED CURRENCIES ===
def _parse_enabled_currencies() -> list:
    raw = os.getenv("ENABLED_CURRENCIES", "TON")
    enabled = [currency.strip().upper() for currency in raw.split(",") if currency.strip()]
    return enabled or ["TON"]


ENABLED_CURRENCIES = _parse_enabled_currencies()

_ALL_SUPPORTED_CURRENCIES = {
    "USDT": {
        "name": "USDT",
        "network": "TRC20",
        "min_confirmations": 1,
        "wallet_address": USDT_WALLET_ADDRESS,
    },
    "TON": {
        "name": "TON",
        "network": "TON",
        "min_confirmations": 1,
        "wallet_address": TON_WALLET_ADDRESS,
    },
}

SUPPORTED_CURRENCIES = {
    currency: config
    for currency, config in _ALL_SUPPORTED_CURRENCIES.items()
    if currency in ENABLED_CURRENCIES
}
if not SUPPORTED_CURRENCIES:
    SUPPORTED_CURRENCIES = {"TON": _ALL_SUPPORTED_CURRENCIES["TON"]}


# === CONFIG VALIDATION ===
def is_placeholder(value):
    """Checks whether a value is a placeholder."""
    if not value:
        return True
    placeholder_patterns = [
        "your_telegram_bot_token_here",
        "your_trongrid_api_key_here",
        "your_toncenter_api_key_here",
        "your_usdt_address_here",
        "your_usdt_private_key_here",
        "your_ton_address_here",
        "your_ton_private_key_here",
        "your_domain.com",
        "localhost",
    ]
    return any(pattern in str(value).lower() for pattern in placeholder_patterns)


def validate_config():
    """Validates configuration values."""
    errors = []
    warnings = []

    if not BOT_TOKEN or is_placeholder(BOT_TOKEN):
        errors.append("BOT_TOKEN is not set or is a placeholder")

    if not ADMIN_ID:
        errors.append("ADMIN_ID is not set")

    enabled_currencies = set(ENABLED_CURRENCIES)

    if "USDT" in enabled_currencies:
        if not TRONGRID_API_KEY or is_placeholder(TRONGRID_API_KEY):
            warnings.append("TRONGRID_API_KEY is not set (USDT payments will be unavailable)")
    if "TON" in enabled_currencies:
        if not TONCENTER_API_KEY or is_placeholder(TONCENTER_API_KEY):
            warnings.append("TONCENTER_API_KEY is not set (TON payments will be unavailable)")

    if "USDT" in enabled_currencies:
        if not USDT_WALLET_ADDRESS or is_placeholder(USDT_WALLET_ADDRESS):
            warnings.append("USDT_WALLET_ADDRESS is not set (USDT payments will be unavailable)")
    if "TON" in enabled_currencies:
        if not TON_WALLET_ADDRESS or is_placeholder(TON_WALLET_ADDRESS):
            warnings.append("TON_WALLET_ADDRESS is not set (TON payments will be unavailable)")

    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"   - {error}")
        print("\nCheck your .env / vault settings")
        return False

    if warnings:
        print("Configuration warnings:")
        for warning in warnings:
            print(f"   - {warning}")

    if PUBLIC_BASE_URL and "localhost" in str(PUBLIC_BASE_URL).lower() and not WEB_DEBUG:
        print("Configuration warnings:")
        print("   - PUBLIC_BASE_URL points to localhost (login links from the bot will not work for users)")

    print("[OK] Configuration loaded successfully")
    return True


# === CONSTANTS ===
DEFAULT_CURRENCY_RATES = {"TON_USDT": 3.16, "USDT_USD": 1.0}


def get_bot_text(key: str, language: str = "en", **kwargs) -> str:
    """Returns a localized bot text."""
    return localization.get_text(key, language, **kwargs)

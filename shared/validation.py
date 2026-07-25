import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from .constants import (
    MIN_DEAL_AMOUNT, MAX_DEAL_AMOUNT, MIN_USER_ID, MAX_USER_ID,
    SUPPORTED_CURRENCIES, USDT_ADDRESS_PATTERN, TON_ADDRESS_PATTERN, 
    DEAL_CODE_PATTERN
)

logger = logging.getLogger(__name__)

# === VALIDATION SCHEMAS ===

class ValidationError(Exception):
    """Custom validation error"""
    pass

class ValidationResult:
    """Validation result container"""
    def __init__(self, is_valid: bool = True, errors: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def add_error(self, error: str):
        """Add error to result"""
        self.is_valid = False
        self.errors.append(error)
    
    def __bool__(self):
        return self.is_valid
    
    def __str__(self):
        return f"Valid: {self.is_valid}, Errors: {self.errors}"

# === CORE VALIDATION FUNCTIONS ===

def validate_deal_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate deal creation/updates data
    
    Args:
        data: Deal data dictionary
        
    Returns:
        ValidationResult with validation status and errors
    """
    result = ValidationResult()
    
    # Required fields
    required_fields = ['buyer_id', 'seller_id', 'amount', 'currency']
    for field in required_fields:
        if field not in data or data[field] is None:
            result.add_error(f"Required field missing: {field}")
    
    if not result:
        return result
    
    # Validate buyer_id
    is_valid, buyer_id = validate_user_id(data['buyer_id'])
    if not is_valid:
        result.add_error(f"Invalid buyer_id: {data['buyer_id']}")
    
    # Validate seller_id
    is_valid, seller_id = validate_user_id(data['seller_id'])
    if not is_valid:
        result.add_error(f"Invalid seller_id: {data['seller_id']}")
    
    # Check buyer and seller are different
    if 'buyer_id' in data and 'seller_id' in data:
        if data['buyer_id'] == data['seller_id']:
            result.add_error("Buyer and seller cannot be the same user")
    
    # Validate amount
    is_valid, amount = validate_amount_in_range(
        data.get('amount'), 
        MIN_DEAL_AMOUNT, 
        MAX_DEAL_AMOUNT
    )
    if not is_valid:
        result.add_error(
            f"Invalid amount: {data.get('amount')}. "
            f"Must be between {MIN_DEAL_AMOUNT} and {MAX_DEAL_AMOUNT}"
        )
    
    # Validate currency
    currency = data.get('currency', '').upper()
    if currency not in SUPPORTED_CURRENCIES:
        result.add_error(f"Invalid currency: {currency}. Supported: {SUPPORTED_CURRENCIES}")
    
    # Validate deal_code if provided
    if 'deal_code' in data and data['deal_code']:
        if not validate_deal_code(data['deal_code']):
            result.add_error(f"Invalid deal_code format: {data['deal_code']}")
    
    # Validate payment timeout if provided
    if 'payment_timeout' in data and data['payment_timeout']:
        try:
            timeout = int(data['payment_timeout'])
            if timeout < 60 or timeout > 86400:  # 1 minute to 24 hours
                result.add_error("Payment timeout must be between 60 and 86400 seconds")
        except (ValueError, TypeError):
            result.add_error("Invalid payment_timeout format")
    
    return result

def validate_payment_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate payment data
    
    Args:
        data: Payment data dictionary
        
    Returns:
        ValidationResult with validation status and errors
    """
    result = ValidationResult()
    
    # Required fields
    required_fields = ['checkout_id', 'amount', 'currency', 'tx_hash']
    for field in required_fields:
        if field not in data or not data[field]:
            result.add_error(f"Required field missing: {field}")
    
    if not result:
        return result
    
    # Validate amount
    if 'amount' in data:
        try:
            amount = float(data['amount'])
            if amount <= 0:
                result.add_error("Payment amount must be positive")
        except (ValueError, TypeError):
            result.add_error("Invalid payment amount")
    
    # Validate currency
    currency = data.get('currency', '').upper()
    if currency not in SUPPORTED_CURRENCIES:
        result.add_error(f"Invalid currency: {currency}")
    
    # Validate transaction hash format
    if 'tx_hash' in data:
        tx_hash = data['tx_hash']
        if not isinstance(tx_hash, str) or len(tx_hash) < 10:
            result.add_error("Invalid transaction hash format")
    
    # Validate address if provided
    if 'address' in data and data['address']:
        if not validate_address(data['address'], currency):
            result.add_error(f"Invalid {currency} address format")
    
    # Validate memo for TON payments
    if currency == 'TON' and 'memo' in data:
        deal_code = data.get('deal_code', '')
        if not validate_memo(data['memo'], deal_code):
            result.add_error(f"Invalid memo format. Expected: DEAL-{deal_code}")
    
    return result

def validate_user_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate user data
    
    Args:
        data: User data dictionary
        
    Returns:
        ValidationResult with validation status and errors
    """
    result = ValidationResult()
    
    # Validate user_id if provided
    if 'user_id' in data and data['user_id']:
        is_valid, user_id = validate_user_id(data['user_id'])
        if not is_valid:
            result.add_error(f"Invalid user_id: {data['user_id']}")
    
    # Validate language if provided
    if 'language' in data and data['language']:
        valid_languages = ['en', 'ua', 'zh']
        if data['language'] not in valid_languages:
            result.add_error(f"Invalid language: {data['language']}")
    
    # Validate balance if provided
    if 'balance' in data and data['balance'] is not None:
        try:
            balance = float(data['balance'])
            if balance < 0:
                result.add_error("Balance cannot be negative")
        except (ValueError, TypeError):
            result.add_error("Invalid balance format")
    
    return result

def validate_settings_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate settings data
    
    Args:
        data: Settings data dictionary
        
    Returns:
        ValidationResult with validation status and errors
    """
    result = ValidationResult()
    
    # Validate commission_rate if provided
    if 'commission_rate' in data and data['commission_rate'] is not None:
        try:
            rate = float(data['commission_rate'])
            if rate < 0 or rate > 1:
                result.add_error("Commission rate must be between 0 and 1")
        except (ValueError, TypeError):
            result.add_error("Invalid commission rate format")
    
    # Validate deal amount limits
    if 'min_deal_amount' in data and data['min_deal_amount'] is not None:
        try:
            min_amount = float(data['min_deal_amount'])
            if min_amount < 0:
                result.add_error("Minimum deal amount cannot be negative")
        except (ValueError, TypeError):
            result.add_error("Invalid minimum deal amount")
    
    if 'max_deal_amount' in data and data['max_deal_amount'] is not None:
        try:
            max_amount = float(data['max_deal_amount'])
            if max_amount <= 0:
                result.add_error("Maximum deal amount must be positive")
        except (ValueError, TypeError):
            result.add_error("Invalid maximum deal amount")
    
    # Check consistency
    if ('min_deal_amount' in data and 'max_deal_amount' in data and 
        data['min_deal_amount'] is not None and data['max_deal_amount'] is not None):
        try:
            if float(data['min_deal_amount']) >= float(data['max_deal_amount']):
                result.add_error("Minimum deal amount must be less than maximum")
        except (ValueError, TypeError):
            pass  # Already validated above
    
    # Validate timeout values
    timeout_fields = ['auto_confirm_timeout', 'payment_timeout']
    for field in timeout_fields:
        if field in data and data[field] is not None:
            try:
                timeout = int(data[field])
                if timeout < 60 or timeout > 86400:  # 1 minute to 24 hours
                    result.add_error(f"{field} must be between 60 and 86400 seconds")
            except (ValueError, TypeError):
                result.add_error(f"Invalid {field} format")
    
    return result

def validate_notification_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate notification data
    
    Args:
        data: Notification data dictionary
        
    Returns:
        ValidationResult with validation status and errors
    """
    result = ValidationResult()
    
    # Required fields
    if 'user_id' not in data or not data['user_id']:
        result.add_error("user_id is required")
    else:
        is_valid, user_id = validate_user_id(data['user_id'])
        if not is_valid:
            result.add_error(f"Invalid user_id: {data['user_id']}")
    
    # Validate message
    if 'message' not in data or not data['message']:
        result.add_error("message is required")
    elif len(data['message']) > 1000:
        result.add_error("Message too long (max 1000 characters)")
    
    # Validate notification type
    valid_types = ['deal_created', 'deal_joined', 'payment_received', 'payment_confirmed', 
                   'deal_completed', 'system_message']
    if 'notification_type' in data and data['notification_type']:
        if data['notification_type'] not in valid_types:
            result.add_error(f"Invalid notification type: {data['notification_type']}")
    
    return result

# === VALIDATION HELPERS ===

def validate_deal_code(deal_code: str) -> bool:
    """Validate deal code format"""
    if not deal_code:
        return False
    return bool(re.match(DEAL_CODE_PATTERN, deal_code))

def validate_address(address: str, currency: str) -> bool:
    """Validate blockchain address format"""
    if not address:
        return False
    
    currency = currency.upper()
    
    if currency in ['USDT', 'TRX']:
        return bool(re.match(USDT_ADDRESS_PATTERN, address))
    elif currency == 'TON':
        return bool(re.match(TON_ADDRESS_PATTERN, address))
    else:
        logger.warning(f"Unknown currency for address validation: {currency}")
        return False

def validate_memo(memo: str, deal_code: str) -> bool:
    """Validate memo format"""
    if not memo or not deal_code:
        return False
    
    expected_memo = f"DEAL-{deal_code}"
    return memo == expected_memo

def validate_user_id(user_id: Any) -> Tuple[bool, Optional[int]]:
    """Validate and convert user ID"""
    try:
        user_id_int = int(user_id)
        if MIN_USER_ID <= user_id_int <= MAX_USER_ID:
            return True, user_id_int
    except (ValueError, TypeError):
        pass
    
    return False, None

def validate_amount(amount: Any) -> Tuple[bool, Optional[float]]:
    """Validate and convert amount"""
    try:
        amount_float = float(amount)
        if amount_float > 0:
            return True, amount_float
    except (ValueError, TypeError):
        pass
    
    return False, None

def validate_amount_in_range(amount: Any, min_amount: float, max_amount: float) -> Tuple[bool, Optional[float]]:
    """Validate amount is within specified range"""
    is_valid, amount_float = validate_amount(amount)
    if not is_valid:
        return False, None
    
    if min_amount <= amount_float <= max_amount:
        return True, amount_float
    
    return False, None

def validate_email(email: str) -> bool:
    """Validate email format"""
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    if not phone:
        return False
    
    # Basic phone validation (international format)
    pattern = r'^\+?[1-9]\d{1,14}$'
    return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))

def validate_date_range(start_date: str, end_date: str) -> bool:
    """Validate date range"""
    try:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        return start <= end
    except (ValueError, TypeError):
        return False

def validate_pagination_params(page: Any, per_page: Any) -> Tuple[bool, int, int]:
    """Validate pagination parameters"""
    try:
        page_int = int(page)
        per_page_int = int(per_page)
        
        if page_int < 1:
            page_int = 1
        if per_page_int < 1 or per_page_int > 100:
            per_page_int = 50
        
        return True, page_int, per_page_int
    except (ValueError, TypeError):
        return False, 1, 50

def validate_search_query(search: str) -> bool:
    """Validate search query"""
    if not search:
        return True  # Empty search is allowed
    
    # Limit length and check for dangerous characters
    if len(search) > 100:
        return False
    
    # Basic SQL injection prevention
    dangerous_chars = [';', '--', '/*', '*/', 'xp_', 'sp_']
    search_lower = search.lower()
    
    return not any(char in search_lower for char in dangerous_chars)

# === BATCH VALIDATION ===

def validate_batch_deals(deals: List[Dict[str, Any]]) -> Dict[str, ValidationResult]:
    """
    Validate multiple deals in batch
    
    Args:
        deals: List of deal dictionaries
        
    Returns:
        Dictionary mapping deal index to ValidationResult
    """
    results = {}
    
    for i, deal in enumerate(deals):
        results[i] = validate_deal_data(deal)
    
    return results

def validate_batch_payments(payments: List[Dict[str, Any]]) -> Dict[str, ValidationResult]:
    """
    Validate multiple payments in batch
    
    Args:
        payments: List of payment dictionaries
        
    Returns:
        Dictionary mapping payment index to ValidationResult
    """
    results = {}
    
    for i, payment in enumerate(payments):
        results[i] = validate_payment_data(payment)
    
    return results

# === SANITIZATION ===

def sanitize_string(text: str, max_length: int = 255) -> str:
    """
    Sanitize string input
    
    Args:
        text: Input string
        max_length: Maximum length
        
    Returns:
        Sanitized string
    """
    if not text:
        return ""
    
    # Remove dangerous characters
    sanitized = re.sub(r'[<>"\']', '', text)
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip()

def sanitize_html(text: str) -> str:
    """Sanitize HTML content"""
    if not text:
        return ""
    
    # Remove script tags and their content
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove other potentially dangerous tags
    dangerous_tags = ['script', 'object', 'embed', 'link', 'style', 'iframe', 'frame', 'frameset', 'noscript']
    for tag in dangerous_tags:
        text = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(f'<{tag}[^>]*/?>', '', text, flags=re.IGNORECASE)
    
    return text.strip()

# === VALIDATION DECORATORS ===

def require_valid_deal(func):
    """Decorator to validate deal data"""
    def wrapper(*args, **kwargs):
        # Assume first argument after self is deal data
        if len(args) > 1:
            result = validate_deal_data(args[1])
            if not result:
                raise ValidationError(f"Invalid deal data: {result.errors}")
        return func(*args, **kwargs)
    return wrapper

def require_valid_payment(func):
    """Decorator to validate payment data"""
    def wrapper(*args, **kwargs):
        # Assume first argument after self is payment data
        if len(args) > 1:
            result = validate_payment_data(args[1])
            if not result:
                raise ValidationError(f"Invalid payment data: {result.errors}")
        return func(*args, **kwargs)
    return wrapper

def require_valid_user(func):
    """Decorator to validate user data"""
    def wrapper(*args, **kwargs):
        # Assume first argument after self is user data
        if len(args) > 1:
            result = validate_user_data(args[1])
            if not result:
                raise ValidationError(f"Invalid user data: {result.errors}")
        return func(*args, **kwargs)
    return wrapper

# === EXPORT MAIN VALIDATORS ===

__all__ = [
    'ValidationError',
    'ValidationResult',
    'validate_deal_data',
    'validate_payment_data', 
    'validate_user_data',
    'validate_settings_data',
    'validate_notification_data',
    'validate_deal_code',
    'validate_address',
    'validate_memo',
    'validate_user_id',
    'validate_amount',
    'validate_amount_in_range',
    'validate_email',
    'validate_phone_number',
    'validate_date_range',
    'validate_pagination_params',
    'validate_search_query',
    'validate_batch_deals',
    'validate_batch_payments',
    'sanitize_string',
    'sanitize_html',
    'require_valid_deal',
    'require_valid_payment',
    'require_valid_user',
]

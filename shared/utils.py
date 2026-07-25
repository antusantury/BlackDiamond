import os
import re
import logging
from typing import Optional, Tuple, Dict, Any

from .constants import (
    STATIC_QR_CODES_DIR, DEAL_CODE_PATTERN,
    MIN_USER_ID, MAX_USER_ID
)

logger = logging.getLogger(__name__)

# === QR CODE UTILITIES ===

def map_qr_code_path(qr_code_path: str, qr_code_url: Optional[str] = None) -> str:
    """Map QR code path to URL, eliminating duplication across multiple files"""
    if not qr_code_path:
        return qr_code_url or ""
    
    if qr_code_url:
        return qr_code_url
    
    try:
        filename = os.path.basename(qr_code_path)
        return f"{STATIC_QR_CODES_DIR}/{filename}"
    except Exception as e:
        logger.warning(f"Error mapping QR code path: {e}")
        return ""

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent security issues"""
    if not filename:
        return ""
    
    sanitized = re.sub(r'[^\w\-_\.]', '_', filename)
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = f"{name[:250-len(ext)]}{ext}"
    
    return sanitized

def validate_deal_code(deal_code: str) -> bool:
    """Validate deal code format"""
    if not deal_code:
        return False
    
    return bool(re.match(DEAL_CODE_PATTERN, deal_code))

def validate_user_id(user_id: Any) -> Tuple[bool, Optional[int]]:
    """Validate and convert user ID"""
    try:
        user_id_int = int(user_id)
        if MIN_USER_ID <= user_id_int <= MAX_USER_ID:
            return True, user_id_int
    except (ValueError, TypeError):
        pass
    
    return False, None

def validate_amount_in_range(amount: float, min_amount: float, max_amount: float) -> Tuple[bool, Optional[float]]:
    """Validate amount is within specified range"""
    try:
        amount_float = float(amount)
        if min_amount <= amount_float <= max_amount:
            return True, amount_float
    except (ValueError, TypeError):
        pass
    
    return False, None

def build_pagination_query(base_query: str, page: int, per_page: int) -> Tuple[str, tuple]:
    """Build paginated SQL query"""
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 50
    
    offset = (page - 1) * per_page
    paginated_query = f"{base_query} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    return paginated_query, (per_page, offset)

def build_update_fields(fields: Dict[str, Any]) -> Tuple[str, tuple]:
    """Build SQL UPDATE fields safely"""
    if not fields:
        return "", ()
    
    set_parts = []
    values = []
    
    for field_name, value in fields.items():
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', field_name):
            set_parts.append(f"{field_name} = ?")
            values.append(value)
    
    if not set_parts:
        return "", ()
    
    set_clause = ", ".join(set_parts)
    return set_clause, tuple(values)

def safe_execute(func, *args, default_return=None, logger_instance=None, **kwargs):
    """Safely execute function with error handling"""
    log = logger_instance or logger
    
    try:
        return func(*args, **kwargs)
    except Exception as e:
        log.error(f"Error executing {func.__name__}: {e}")
        return default_return

def get_rate_limit(operation_type: str = 'default') -> Tuple[int, int]:
    """Get rate limit configuration"""
    rate_limits = {
        'default': (100, 3600),
        'payment': (50, 3600),
        'deal': (30, 3600),
        'user': (10, 300),
        'api': (1000, 3600),
    }
    
    return rate_limits.get(operation_type, rate_limits['default'])
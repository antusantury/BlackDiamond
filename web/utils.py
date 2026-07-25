#!/usr/bin/env python3
import logging
import string
import random
import re
import time
from typing import Dict, Any, Optional, List, Tuple

from shared.constants import SUPPORTED_CURRENCIES

logger = logging.getLogger(__name__)

class SecurityUtils:
    """Security utility functions"""
    
    @staticmethod
    def escape_html(text: str) -> str:
        """Safe HTML escaping"""
        if not text:
            return ""
        import html as _html
        return _html.escape(str(text), quote=True).replace("'", "&#x27;")
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate cryptographically secure random token"""
        import secrets
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate username format"""
        if not username or len(username) > 50:
            return False
        return re.match(r'^[a-zA-Z0-9_-]+$', username) is not None
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        if not email:
            return True  # Email is optional
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe file operations"""
        if not filename:
            return ""
        # Remove path separators and dangerous characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Limit length
        return filename[:255] if len(filename) > 255 else filename


class ValidationUtils:
    """Input validation utilities"""
    
    @staticmethod
    def validate_deal_code(deal_code: str) -> bool:
        """Validate deal code format"""
        if not deal_code or len(deal_code) != 8 or not deal_code.isalnum():
            return False
        return True
    
    @staticmethod
    def validate_amount(amount_str: str, min_amount: float = 1.0, max_amount: float = 10000.0) -> Tuple[bool, Optional[float]]:
        """Validate amount string"""
        try:
            amount = float(amount_str)
            if min_amount <= amount <= max_amount:
                return True, amount
            return False, None
        except (ValueError, TypeError):
            return False, None
    
    @staticmethod
    def validate_currency(currency: str) -> bool:
        """Validate currency"""
        return currency.upper() in SUPPORTED_CURRENCIES
    
    @staticmethod
    def validate_address(address: str, currency: str) -> bool:
        """Validate wallet address for currency"""
        if not address or len(address) < 12 or len(address) > 200:
            return False
        
        if currency.upper() == 'USDT':
            # Basic USDT TRC20 address validation
            return address.startswith('T') and len(address) == 34
        elif currency.upper() == 'TON':
            # Basic TON address validation  
            return address.startswith('U') and len(address) >= 48
        else:
            return True  # Generic validation for other currencies
    
    @staticmethod
    def validate_telegram_id(telegram_id: str) -> Tuple[bool, Optional[int]]:
        """Validate Telegram user ID"""
        try:
            user_id = int(telegram_id)
            if 1 <= user_id <= 999999999999:
                return True, user_id
            return False, None
        except (ValueError, TypeError):
            return False, None


class ResponseUtils:
    """Response formatting utilities"""
    
    @staticmethod
    def success_response(data: Any = None, message: str = "Success") -> Dict:
        """Create success response"""
        response = {
            'success': True,
            'message': message
        }
        if data is not None:
            response['data'] = data
        return response
    
    @staticmethod
    def error_response(message: str, status_code: int = 400, details: Dict = None) -> Dict:
        """Create error response"""
        response = {
            'success': False,
            'error': message,
            'status_code': status_code
        }
        if details:
            response['details'] = details
        return response
    
    @staticmethod
    def paginated_response(items: List, page: int, per_page: int, total: int) -> Dict:
        """Create paginated response"""
        return {
            'success': True,
            'data': items,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_count': total,
                'total_pages': (total + per_page - 1) // per_page,
                'has_previous': page > 1,
                'has_next': page < (total + per_page - 1) // per_page
            }
        }


class AsyncUtils:
    """Async/await utilities for replacing blocking operations"""
    
    @staticmethod
    async def async_sleep(seconds: float):
        """Async sleep to replace time.sleep()"""
        import asyncio
        await asyncio.sleep(seconds)
    
    @staticmethod
    async def async_request(url: str, method: str = 'GET', **kwargs):
        """Make async HTTP request"""
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=kwargs.get('timeout', 30))
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                return await response.json() if response.status == 200 else None
    
    @staticmethod
    async def async_file_read(filepath: str):
        """Async file reading"""
        import aiofiles
        async with aiofiles.open(filepath, 'r') as f:
            return await f.read()


class MobileUtils:
    """Mobile device detection utilities"""
    
    @staticmethod
    def is_mobile_device(user_agent: str) -> bool:
        """Check if request is from mobile device"""
        mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone']
        
        # Check for mobile user agents
        if any(keyword in user_agent.lower() for keyword in mobile_keywords):
            return True
        
        return False
    
    @staticmethod
    def is_telegram_web_app(headers: Dict) -> bool:
        """Check if request is from Telegram WebApp"""
        return headers.get('Telegram-Web-App', '').lower() == 'true'


class DealUtils:
    """Deal-related utility functions"""
    
    @staticmethod
    def generate_deal_code() -> str:
        """Generate unique deal code"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choice(chars) for _ in range(8))
    
    @staticmethod
    def calculate_commission(amount: float, commission_rate: float) -> Tuple[float, float]:
        """Calculate commission and seller amount"""
        commission_amount = round(amount * commission_rate, 8)
        seller_amount = round(amount - commission_amount, 8)
        return commission_amount, seller_amount
    
    @staticmethod
    def format_deal_status(status: str, localization=None, language: str = 'en') -> str:
        """Format deal status for display using translation keys"""
        if localization:
            # Use localization with translation keys
            status_key = f'status_{status}'
            return localization.get_text(status_key, language=language)

        # Fallback to title case if no localization (should not happen in production)
        status_map = {
            'active': 'Active',
            'pending': 'Pending',
            'funded': 'Funded',
            'confirmed': 'Confirmed',
            'completed': 'Completed',
            'cancelled': 'Cancelled',
            'expired': 'Expired'
        }

        return status_map.get(status, status.title())


class CacheUtils:
    """Caching utilities"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        if key in self.cache:
            if key in self.cache_ttl and time.time() < self.cache_ttl[key]:
                return self.cache[key]
            else:
                # Expired
                del self.cache[key]
                if key in self.cache_ttl:
                    del self.cache_ttl[key]
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set cached value with TTL"""
        self.cache[key] = value
        self.cache_ttl[key] = time.time() + ttl_seconds
    
    def delete(self, key: str):
        """Delete cached value"""
        if key in self.cache:
            del self.cache[key]
        if key in self.cache_ttl:
            del self.cache_ttl[key]
    
    def clear(self):
        """Clear all cache"""
        self.cache.clear()
        self.cache_ttl.clear()


# Global utility instances
security_utils = SecurityUtils()
validation_utils = ValidationUtils()
response_utils = ResponseUtils()
async_utils = AsyncUtils()
mobile_utils = MobileUtils()
deal_utils = DealUtils()
cache_utils = CacheUtils()


def escape_html(text: str) -> str:
    """Safe HTML escaping (convenience function)"""
    return security_utils.escape_html(text)


def generate_deal_code() -> str:
    """Generate deal code (convenience function)"""
    return deal_utils.generate_deal_code()


def validate_input(data: Dict, rules: Dict) -> Tuple[bool, str]:
    """Validate input data against rules"""
    try:
        for field, rule in rules.items():
            value = data.get(field)
            
            # Required check
            if rule.get('required', False) and not value:
                return False, f"Field '{field}' is required"
            
            # Type check
            expected_type = rule.get('type')
            if value and expected_type and not isinstance(value, expected_type):
                return False, f"Field '{field}' must be of type {expected_type.__name__}"
            
            # Length check
            max_length = rule.get('max_length')
            if value and max_length and len(str(value)) > max_length:
                return False, f"Field '{field}' exceeds maximum length of {max_length} characters"
            
            # Custom validation
            validator = rule.get('validator')
            if value and validator and not validator(value):
                return False, f"Field '{field}' is invalid"
        
        return True, "Valid"
        
    except Exception as e:
        return False, f"Validation error: {str(e)}"

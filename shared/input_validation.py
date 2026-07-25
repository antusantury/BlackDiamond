import re
import logging
from typing import Dict, Any, Tuple, List, Union
from urllib.parse import quote
from html import escape as html_escape
import bleach

logger = logging.getLogger(__name__)


class InputValidator:
    """Input validator with multi-layer protection."""

    def __init__(self):
        # Configure bleach for HTML sanitization
        self.allowed_tags = ['b', 'i', 'u', 's', 'code', 'pre', 'a']
        self.allowed_attributes = {
            'a': ['href', 'title'],
        }

        # Regular expressions for different validation types
        self.patterns = {
            'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
            'phone': re.compile(r'^\+?[\d\s\-\(\)]{10,15}$'),
            'url': re.compile(r'^https?://[^\s/$.?#].[^\s]*$'),
            'alphanumeric': re.compile(r'^[a-zA-Z0-9]+$'),
            'alphanumeric_underscore': re.compile(r'^[a-zA-Z0-9_]+$'),
            'deal_code': re.compile(r'^[A-Z0-9]{8}$'),
            'telegram_username': re.compile(r'^@[a-zA-Z0-9_]{5,32}$'),
            'wallet_address_usdt': re.compile(r'^T[a-zA-Z0-9]{33}$'),
            'wallet_address_ton': re.compile(r'^(UQ|EQ)[a-zA-Z0-9_-]{46,48}$'),
            'amount': re.compile(r'^\d+(\.\d{1,8})?$'),
            'integer': re.compile(r'^\d+$'),
            'safe_text': re.compile(r'^[a-zA-Z0-9\s\-_.,!?()\[\]{}:;@#$%^&*+=|<>?/\\]+$'),
        }

        # Forbidden words and patterns
        self.forbidden_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'vbscript:',
            r'on\w+\s*=',
            r'<\w+[^>]*>',
            r'union\s+select',
            r';\s*drop\s+table',
            r';\s*delete\s+from',
            r';\s*update\s+.*set',
            r'--',
            r'/\*.*\*/',
            r'xp_cmdshell',
            r'exec\s*\(',
        ]

    def validate_and_sanitize(self, value: Any, validation_type: str,
                            max_length: int = None, required: bool = False) -> Tuple[bool, Union[str, None], List[str]]:
        """
        Validate and sanitize input.

        Returns:
            Tuple[bool, Union[str, None], List[str]]: (is_valid, sanitized_value, error_messages)
        """
        errors = []

        # Required check
        if required and (value is None or str(value).strip() == ''):
            errors.append("This field is required")
            return False, None, errors

        # If value is None/empty and not required, return None
        if value is None or str(value).strip() == '':
            return True, None, []

        # Convert to string for processing
        str_value = str(value).strip()

        # Max length check
        if max_length and len(str_value) > max_length:
            errors.append(f"Length must not exceed {max_length} characters")
            return False, None, errors

        # Forbidden pattern check
        if self._contains_forbidden_patterns(str_value):
            errors.append("Input contains invalid characters or patterns")
            logger.warning(f"Detected forbidden patterns in input: {str_value[:50]}...")
            return False, None, errors

        # Type-specific validation
        try:
            sanitized_value = self._validate_by_type(str_value, validation_type)
            return True, sanitized_value, []
        except ValueError as e:
            errors.append(str(e))
            return False, None, errors

    def _validate_by_type(self, value: str, validation_type: str) -> str:
        """Validate by a specific type."""
        if validation_type == 'email':
            return self._validate_email(value)
        elif validation_type == 'phone':
            return self._validate_phone(value)
        elif validation_type == 'url':
            return self._validate_url(value)
        elif validation_type == 'deal_code':
            return self._validate_deal_code(value)
        elif validation_type == 'wallet_address':
            return self._validate_wallet_address(value)
        elif validation_type == 'amount':
            return self._validate_amount(value)
        elif validation_type == 'integer':
            return self._validate_integer(value)
        elif validation_type == 'telegram_username':
            return self._validate_telegram_username(value)
        elif validation_type == 'safe_text':
            return self._validate_safe_text(value)
        elif validation_type == 'alphanumeric':
            return self._validate_alphanumeric(value)
        elif validation_type == 'description':
            return self._validate_description(value)
        elif validation_type == 'username':
            return self._validate_username(value)
        elif validation_type == 'name':
            return self._validate_name(value)
        else:
            # Default: safe text
            return self._validate_safe_text(value)

    def _validate_email(self, value: str) -> str:
        """Validate email."""
        if not self.patterns['email'].match(value):
            raise ValueError("Invalid email format")
        return value.lower()

    def _validate_phone(self, value: str) -> str:
        """Validate phone number."""
        # Remove spaces/dashes for validation
        clean_phone = re.sub(r'[\s\-\(\)]', '', value)
        if not self.patterns['phone'].match(clean_phone):
            raise ValueError("Invalid phone number format")
        return clean_phone

    def _validate_url(self, value: str) -> str:
        """Validate URL."""
        if not self.patterns['url'].match(value):
            raise ValueError("Invalid URL format")
        return quote(value, safe=':/?=&')

    def _validate_deal_code(self, value: str) -> str:
        """Validate deal code."""
        if not self.patterns['deal_code'].match(value.upper()):
            raise ValueError("Invalid deal code format (must be 8 characters A-Z, 0-9)")
        return value.upper()

    def _validate_wallet_address(self, value: str) -> str:
        """Validate wallet address."""
        # Check USDT address
        if value.startswith('T') and self.patterns['wallet_address_usdt'].match(value):
            return value
        # Check TON address
        elif (value.startswith('UQ') or value.startswith('EQ')) and self.patterns['wallet_address_ton'].match(value):
            return value
        else:
            raise ValueError("Invalid wallet address format")

    def _validate_amount(self, value: str) -> str:
        """Validate amount."""
        if not self.patterns['amount'].match(value):
            raise ValueError("Invalid amount format (must be a positive number)")

        amount = float(value)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > 1000000:
            raise ValueError("Amount is too large (max 1,000,000)")

        return value

    def _validate_integer(self, value: str) -> str:
        """Validate integer."""
        if not self.patterns['integer'].match(value):
            raise ValueError("Must be a positive integer")

        num = int(value)
        if num < 0:
            raise ValueError("Number must be positive")

        return value

    def _validate_telegram_username(self, value: str) -> str:
        """Validate Telegram username."""
        if not self.patterns['telegram_username'].match(value):
            raise ValueError("Invalid Telegram username format")
        return value

    def _validate_safe_text(self, value: str) -> str:
        """Validate safe text."""
        # Remove potentially dangerous characters
        cleaned = re.sub(r'[<>"\'`]', '', value)
        cleaned = bleach.clean(cleaned, tags=[], strip=True)

        if not cleaned.strip():
            raise ValueError("Text contains invalid characters")

        return cleaned.strip()

    def _validate_description(self, value: str) -> str:
        """Validate description."""
        if len(value) > 500:
            raise ValueError("Description is too long (max 500 characters)")

        # Allow more content in descriptions
        cleaned = bleach.clean(value, tags=self.allowed_tags, attributes=self.allowed_attributes, strip=True)

        if not cleaned.strip():
            raise ValueError("Description contains invalid characters")

        return cleaned.strip()

    def _validate_username(self, value: str) -> str:
        """Validate username."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', value):
            raise ValueError("Username may contain only letters, digits, hyphen and underscore")
        if len(value) < 3 or len(value) > 50:
            raise ValueError("Username must be between 3 and 50 characters")
        return value

    def _validate_name(self, value: str) -> str:
        """Validate name."""
        # Allow letters, spaces, hyphens, apostrophes
        if not re.match(r"^[a-zA-Z\s\-']+$", value):
            raise ValueError("Name may contain only letters, spaces, hyphens and apostrophes")
        if len(value) < 1 or len(value) > 100:
            raise ValueError("Name must be between 1 and 100 characters")

        cleaned = bleach.clean(value, tags=[], strip=True)
        return cleaned.strip()

    def _validate_alphanumeric(self, value: str) -> str:
        """Validate alphanumeric text."""
        if not self.patterns['alphanumeric'].match(value):
            raise ValueError("Only letters and digits are allowed")
        return value

    def _contains_forbidden_patterns(self, value: str) -> bool:
        """Check for forbidden patterns."""
        value_lower = value.lower()
        for pattern in self.forbidden_patterns:
            if re.search(pattern, value_lower, re.IGNORECASE):
                return True
        return False

    def sanitize_sql_input(self, value: Any) -> str:
        """Safely prepare input for SQL."""
        if value is None:
            return 'NULL'

        str_value = str(value)

        # Escape special characters
        str_value = str_value.replace("'", "''")
        str_value = str_value.replace("\\", "\\\\")

        # Limit length to prevent DoS
        if len(str_value) > 1000:
            str_value = str_value[:1000] + '...'

        return str_value

    def sanitize_html_output(self, value: Any) -> str:
        """Safely escape output for HTML."""
        if value is None:
            return ''

        str_value = str(value)

        # Escape HTML
        return html_escape(str_value, quote=True)

    def validate_bulk_data(self, data: Dict[str, Any], schema: Dict[str, Dict[str, Any]]) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Validate multiple fields using a schema.

        schema format:
        {
            'field_name': {
                'type': 'email|phone|url|deal_code|amount|safe_text|description',
                'max_length': 100,
                'required': True
            }
        }
        """
        errors = []
        sanitized_data = {}

        for field_name, field_config in schema.items():
            value = data.get(field_name)

            field_type = field_config.get('type', 'safe_text')
            max_length = field_config.get('max_length', 1000)
            required = field_config.get('required', False)

            is_valid, sanitized_value, field_errors = self.validate_and_sanitize(
                value, field_type, max_length, required
            )

            if not is_valid:
                errors.extend([f"{field_name}: {error}" for error in field_errors])
            else:
                sanitized_data[field_name] = sanitized_value

        return len(errors) == 0, sanitized_data, errors


# Global validator instance
input_validator = InputValidator()


def validate_input(value: Any, validation_type: str, max_length: int = None, required: bool = False) -> Tuple[bool, Union[str, None], List[str]]:
    """Convenience validation wrapper (compatibility helper)."""
    return input_validator.validate_and_sanitize(value, validation_type, max_length, required)


def sanitize_sql(value: Any) -> str:
    """Safely prepare input for SQL."""
    return input_validator.sanitize_sql_input(value)


def sanitize_html(value: Any) -> str:
    """Safely escape output for HTML."""
    return input_validator.sanitize_html_output(value)


def validate_deal_data(data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Validate deal data."""
    schema = {
        'deal_code': {'type': 'deal_code', 'required': True},
        'amount': {'type': 'amount', 'required': True},
        'currency': {'type': 'alphanumeric', 'max_length': 10, 'required': True},
        'description': {'type': 'description', 'max_length': 500, 'required': False},
        'product_link': {'type': 'url', 'max_length': 500, 'required': False},
    }

    return input_validator.validate_bulk_data(data, schema)


def validate_user_data(data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Validate user data."""
    schema = {
        'username': {'type': 'username', 'max_length': 50, 'required': False},
        'first_name': {'type': 'name', 'max_length': 100, 'required': False},
        'last_name': {'type': 'name', 'max_length': 100, 'required': False},
        'language': {'type': 'alphanumeric', 'max_length': 5, 'required': False},
    }

    return input_validator.validate_bulk_data(data, schema)

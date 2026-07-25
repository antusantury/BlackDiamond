import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input by removing potentially dangerous characters."""
    if not text:
        return ""

    # Limit length
    text = str(text)[:max_length]

    # Remove potentially dangerous characters while keeping basic punctuation
    text = re.sub(r'[<>"\'\`]', '', text)

    return text.strip()

def validate_deal_code(deal_code: str) -> bool:
    """Validate a deal code."""
    if not deal_code or not isinstance(deal_code, str):
        return False

    # The code must be 8 characters of letters/digits
    return bool(re.match(r'^[A-Z0-9]{8}$', deal_code.upper()))

def validate_user_input(
    text: str, 
    field_type: str = 'text', 
    max_length: int = 1000
) -> Tuple[bool, str]:
    """Validate user input and return sanitized text."""
    if not text:
        return True, ""

    if not isinstance(text, str):
        return False, "Invalid data type"

    # Length check
    if len(text) > max_length:
        return False, f"Text is too long (max {max_length} characters)"

    # Field-type-specific validation
    if field_type == 'description':
        # Allow more characters for descriptions
        max_length = 500
        # Allow basic punctuation
        cleaned = re.sub(r'[<>"\'\`]', '', text[:max_length])
    elif field_type == 'username':
        # Strict rules for username
        if not re.match(r'^[a-zA-Z0-9_-]+$', text):
            return False, "Username may contain only letters, digits, hyphen and underscore"
        cleaned = text[:50]  # Limit length
    elif field_type == 'amount':
        # Amount must be a valid number
        try:
            amount = float(text.replace(',', '.'))
            if amount <= 0:
                return False, "Amount must be positive"
            if amount > 1000000:
                return False, "Сумма слишком большая"
            return True, str(amount)
        except ValueError:
            return False, "Invalid amount format"
    else:
        # Generic sanitization for text fields
        cleaned = re.sub(r'[<>"\'\`]', '', text[:max_length])

    return True, cleaned.strip()

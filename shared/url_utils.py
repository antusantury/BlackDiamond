import logging
from typing import Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def get_base_url() -> str:
    """
    Get the public base URL for the application.
    
    Returns:
        str: The public base URL (e.g., 'https://blackdiamond.fun')
    """
    try:
        from shared.config import PUBLIC_BASE_URL
        return PUBLIC_BASE_URL.rstrip('/')
    except ImportError:
        logger.warning("Could not import PUBLIC_BASE_URL, using fallback")
        return "https://blackdiamond.fun"


def get_deal_url(deal_code: str, base_url: Optional[str] = None) -> str:
    """
    Generate a full deal URL from a deal code.
    
    Args:
        deal_code (str): The deal code (e.g., 'XI1XRI2V')
        base_url (Optional[str]): Base URL to use (defaults to PUBLIC_BASE_URL)
    
    Returns:
        str: Full deal URL (e.g., 'https://blackdiamond.fun/deal/XI1XRI2V')
    """
    if not base_url:
        base_url = get_base_url()
    
    # Remove trailing slash and construct URL
    base_url = base_url.rstrip('/')
    deal_url = f"{base_url}/deal/{deal_code.upper()}"
    
    logger.debug(f"Generated deal URL: {deal_url} from code: {deal_code}")
    return deal_url


def get_profile_url(base_url: Optional[str] = None) -> str:
    """
    Generate a full profile URL.
    
    Args:
        base_url (Optional[str]): Base URL to use (defaults to PUBLIC_BASE_URL)
    
    Returns:
        str: Full profile URL (e.g., 'https://blackdiamond.fun/profile')
    """
    if not base_url:
        base_url = get_base_url()
    
    base_url = base_url.rstrip('/')
    return f"{base_url}/profile"


def get_support_url(base_url: Optional[str] = None) -> str:
    """
    Generate a full support URL.
    
    Args:
        base_url (Optional[str]): Base URL to use (defaults to PUBLIC_BASE_URL)
    
    Returns:
        str: Full support URL (e.g., 'https://blackdiamond.fun/support')
    """
    if not base_url:
        base_url = get_base_url()
    
    base_url = base_url.rstrip('/')
    return f"{base_url}/support"


def get_admin_url(endpoint: str = "", base_url: Optional[str] = None) -> str:
    """
    Generate a full admin URL.
    
    Args:
        endpoint (str): Admin endpoint (e.g., 'support', 'users')
        base_url (Optional[str]): Base URL to use (defaults to PUBLIC_BASE_URL)
    
    Returns:
        str: Full admin URL (e.g., 'https://blackdiamond.fun/admin/support')
    """
    if not base_url:
        base_url = get_base_url()
    
    base_url = base_url.rstrip('/')
    if endpoint:
        return f"{base_url}/admin/{endpoint}"
    else:
        return f"{base_url}/admin"


def construct_full_url(relative_path: str, base_url: Optional[str] = None) -> str:
    """
    Construct a full URL from a relative path and base URL.
    
    Args:
        relative_path (str): Relative path (e.g., '/deal/XI1XRI2V' or 'deal/XI1XRI2V')
        base_url (Optional[str]): Base URL to use (defaults to PUBLIC_BASE_URL)
    
    Returns:
        str: Full URL (e.g., 'https://blackdiamond.fun/deal/XI1XRI2V')
    """
    if not base_url:
        base_url = get_base_url()
    
    # Remove leading slash from relative_path if present
    relative_path = relative_path.lstrip('/')
    
    # Use urljoin for proper URL construction
    full_url = urljoin(base_url.rstrip('/') + '/', relative_path)
    
    logger.debug(f"Constructed full URL: {full_url} from path: {relative_path}")
    return full_url


# Convenience functions for common URL patterns
def deal_url(deal_code: str) -> str:
    """Convenience function for deal URLs."""
    return get_deal_url(deal_code)


def profile_url() -> str:
    """Convenience function for profile URL."""
    return get_profile_url()


def support_url() -> str:
    """Convenience function for support URL."""
    return get_support_url()


def admin_url(endpoint: str = "") -> str:
    """Convenience function for admin URLs."""
    return get_admin_url(endpoint)
import ssl
import aiohttp
import certifi
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SSLConfig:
    """Enhanced SSL configuration for cryptocurrency API calls"""
    
    @staticmethod
    def create_secure_ssl_context() -> ssl.SSLContext:
        """Create a secure SSL context with proper certificate verification"""
        try:
            # Use certifi's bundle if available, fallback to system certificates
            ca_bundle = certifi.where()
            if not os.path.exists(ca_bundle):
                logger.warning("Certifi bundle not found, using system certificates")
                ca_bundle = None
            
            # Create SSL context with certificate verification
            ssl_context = ssl.create_default_context(cafile=ca_bundle)
            
            # Set additional security options
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            
            # Disable weak ciphers and protocols
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            
            logger.info("Created secure SSL context with certificate verification")
            return ssl_context
            
        except Exception as e:
            logger.error(f"Failed to create secure SSL context: {e}")
            return SSLConfig.create_fallback_ssl_context()
    
    @staticmethod
    def create_fallback_ssl_context() -> ssl.SSLContext:
        """Create a fallback SSL context for environments with certificate issues"""
        try:
            # Create basic SSL context
            ssl_context = ssl.create_default_context()
            
            # In some environments, we may need to be more lenient
            # but still maintain security
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            
            logger.info("Created fallback SSL context")
            return ssl_context
            
        except Exception as e:
            logger.error(f"Failed to create fallback SSL context: {e}")
            # Last resort - create unverified context but log warning
            logger.warning("Creating unverified SSL context - security compromised!")
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context
    
    @staticmethod
    def create_allowlist_ssl_context() -> ssl.SSLContext:
        """Create SSL context that allows specific certificate issues"""
        try:
            ssl_context = ssl.create_default_context()
            
            # Allow some flexibility for known certificate issues
            # but still verify most aspects
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            
            # Add specific cipher suites
            ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
            
            logger.info("Created allowlist SSL context")
            return ssl_context
            
        except Exception as e:
            logger.error(f"Failed to create allowlist SSL context: {e}")
            return SSLConfig.create_fallback_ssl_context()

def create_secure_aiohttp_session(
    timeout: int = 30,
    max_connections: int = 100,
    ssl_mode: str = 'secure'  # 'secure', 'fallback', 'allowlist'
) -> aiohttp.ClientSession:
    """
    Create an aiohttp session with proper SSL configuration
    
    Args:
        timeout: Request timeout in seconds
        max_connections: Maximum connections in the pool
        ssl_mode: SSL mode - 'secure', 'fallback', or 'allowlist'
    """
    
    # Create appropriate SSL context based on mode
    if ssl_mode == 'secure':
        ssl_context = SSLConfig.create_secure_ssl_context()
    elif ssl_mode == 'allowlist':
        ssl_context = SSLConfig.create_allowlist_ssl_context()
    else:
        ssl_context = SSLConfig.create_fallback_ssl_context()
    
    # Create TCP connector with SSL configuration
    connector = aiohttp.TCPConnector(
        ssl=ssl_context,
        limit=max_connections,
        limit_per_host=30,
        enable_cleanup_closed=True,
        keepalive_timeout=30
    )
    
    # Create timeout configuration
    timeout_config = aiohttp.ClientTimeout(
        total=timeout,
        connect=10,
        sock_read=10
    )
    
    # Create session with secure configuration
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout_config,
        headers={
            'User-Agent': 'BlackDiamond-Bot/1.0 (Secure-Crypto-API)',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }
    )
    
    logger.info(f"Created secure aiohttp session with SSL mode: {ssl_mode}")
    return session

def create_unverified_aiohttp_session(timeout: int = 30) -> aiohttp.ClientSession:
    """
    Create an aiohttp session with SSL verification disabled (emergency fallback)
    Only use this in production when absolutely necessary
    """
    connector = aiohttp.TCPConnector(
        ssl=False,  # Disable SSL verification
        limit=50,
        limit_per_host=20
    )
    
    timeout_config = aiohttp.ClientTimeout(total=timeout)
    
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout_config,
        headers={
            'User-Agent': 'BlackDiamond-Bot/1.0 (Emergency-Unverified)',
            'Accept': 'application/json'
        }
    )
    
    logger.warning("Created unverified aiohttp session - SECURITY RISK!")
    return session

# Environment-specific SSL configuration
def get_ssl_config_for_environment() -> Dict[str, Any]:
    """
    Get SSL configuration based on environment
    """
    # Check environment variables
    ssl_strict = os.getenv('SSL_VERIFY_STRICT', 'true').lower() == 'true'
    ssl_mode = os.getenv('SSL_MODE', 'secure')
    
    # Check if running in specific environments
    is_production = os.getenv('ENVIRONMENT', '').lower() in ['production', 'prod']
    is_docker = os.getenv('DOCKER', '').lower() == 'true'
    is_cloudflare = os.getenv('CLOUDFLARE_MODE', '').lower() == 'true'
    
    config = {
        'ssl_mode': 'secure',
        'timeout': 30,
        'max_retries': 3,
        'fallback_enabled': True
    }
    
    # Adjust configuration based on environment
    if is_production:
        config['ssl_mode'] = 'secure'
        config['timeout'] = 15
        config['max_retries'] = 2
    elif is_docker:
        config['ssl_mode'] = 'allowlist'
        config['timeout'] = 45
        config['max_retries'] = 3
    elif is_cloudflare:
        config['ssl_mode'] = 'secure'
        config['timeout'] = 20
        config['max_retries'] = 2
    
    # Override with environment variables
    if not ssl_strict:
        config['ssl_mode'] = 'allowlist'
    
    if ssl_mode in ['secure', 'fallback', 'allowlist']:
        config['ssl_mode'] = ssl_mode
    
    logger.info(f"SSL configuration for environment: {config}")
    return config
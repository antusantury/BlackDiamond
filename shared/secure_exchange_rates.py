import asyncio
import time
import aiohttp
import logging
import ssl
import certifi
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SecureExchangeRateFetcher:
    """Enhanced exchange rate fetcher with comprehensive SSL handling"""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.last_update: Dict[str, float] = {}
        self.cache_duration = 300  # 5 minutes cache
        
        # Multiple exchange sources for redundancy
        self.exchange_apis = [
            {
                'name': 'coingecko',
                'url': 'https://api.coingecko.com/api/v3/simple/price',
                'params': {'ids': 'the-open-network', 'vs_currencies': 'usd'},
                'parser': self._parse_coingecko_response
            },
            {
                'name': 'binance',
                'url': 'https://api.binance.com/api/v3/ticker/price',
                'params': {'symbol': 'TONUSDT'},
                'parser': self._parse_binance_response
            },
            {
                'name': 'okx',
                'url': 'https://www.okx.com/api/v5/market/ticker',
                'params': {'instId': 'TON-USDT'},
                'parser': self._parse_okx_response
            }
        ]
    
    def _parse_coingecko_response(self, data: Dict) -> Optional[float]:
        """Parse CoinGecko API response"""
        try:
            ton_data = data.get('the-open-network', {})
            price = ton_data.get('usd')
            return float(price) if price else None
        except (ValueError, KeyError) as e:
            logger.warning(f"CoinGecko parsing error: {e}")
            return None
    
    def _parse_binance_response(self, data: Dict) -> Optional[float]:
        """Parse Binance API response"""
        try:
            return float(data.get('price', 0))
        except (ValueError, KeyError) as e:
            logger.warning(f"Binance parsing error: {e}")
            return None
    
    def _parse_okx_response(self, data: Dict) -> Optional[float]:
        """Parse OKX API response"""
        try:
            tickers = data.get('data', [])
            if tickers:
                return float(tickers[0].get('last', 0))
            return None
        except (ValueError, KeyError, IndexError) as e:
            logger.warning(f"OKX parsing error: {e}")
            return None
    
    def _create_secure_ssl_context(self) -> ssl.SSLContext:
        """Create a secure SSL context"""
        try:
            # Use certifi's bundle
            ca_bundle = certifi.where()
            ssl_context = ssl.create_default_context(cafile=ca_bundle)
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            return ssl_context
        except Exception as e:
            logger.error(f"Failed to create secure SSL context: {e}")
            return None
    
    def _create_permissive_ssl_context(self) -> ssl.SSLContext:
        """Create a more permissive SSL context for problematic environments"""
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            # Allow some flexibility
            ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5')
            return ssl_context
        except Exception as e:
            logger.error(f"Failed to create permissive SSL context: {e}")
            return None
    
    async def _fetch_with_session(self, session: aiohttp.ClientSession) -> Optional[float]:
        """Fetch rates using provided session"""
        try:
            tasks = []
            for exchange in self.exchange_apis:
                task = self._fetch_single_exchange(session, exchange)
                tasks.append(task)
            
            # Wait for all exchanges to respond
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Find valid rates
            valid_rates = []
            for result in results:
                if isinstance(result, (int, float)) and result > 0:
                    valid_rates.append(result)
            
            if valid_rates:
                # Use median to avoid outliers
                sorted_rates = sorted(valid_rates)
                median_rate = sorted_rates[len(sorted_rates) // 2]
                return median_rate
            
            return None
            
        except Exception as e:
            logger.error(f"Error in batch fetch: {e}")
            return None
    
    async def _fetch_single_exchange(self, session: aiohttp.ClientSession, exchange: Dict) -> Optional[float]:
        """Fetch rate from a single exchange"""
        try:
            async with session.get(
                exchange['url'],
                params=exchange['params'],
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return exchange['parser'](data)
                else:
                    logger.warning(f"{exchange['name']} API returned status {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching from {exchange['name']}")
            return None
        except Exception as e:
            logger.error(f"Error fetching from {exchange['name']}: {e}")
            return None
    
    async def get_ton_usdt_rate(self) -> Optional[float]:
        """Get current TON/USDT exchange rate with SSL fallback"""
        cache_key = 'TON_USDT'
        now = time.time()
        
        # Check cache first
        if cache_key in self.cache and cache_key in self.last_update:
            if now - self.last_update[cache_key] < self.cache_duration:
                cached_data = self.cache[cache_key]
                logger.debug(f"Using cached rate: {cached_data['rate']}")
                return cached_data['rate']
        
        # Try different SSL configurations
        ssl_configs = [
            ('secure', self._create_secure_ssl_context),
            ('permissive', self._create_permissive_ssl_context)
        ]
        
        for ssl_name, ssl_factory in ssl_configs:
            ssl_context = ssl_factory()
            if ssl_context is None:
                continue
                
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            timeout_config = aiohttp.ClientTimeout(total=15)
            
            try:
                async with aiohttp.ClientSession(connector=connector, timeout=timeout_config) as session:
                    rate = await self._fetch_with_session(session)
                    
                    if rate:
                        # Cache the result
                        self.cache[cache_key] = {
                            'rate': rate,
                            'sources': 3,  # All sources attempted
                            'timestamp': now
                        }
                        self.last_update[cache_key] = now
                        
                        logger.info(f"TON/USDT rate updated ({ssl_name}): {rate:.4f}")
                        return rate
                        
            except Exception as e:
                logger.warning(f"SSL config '{ssl_name}' failed: {e}")
                continue
        
        # Last resort: try without SSL verification
        try:
            logger.warning("Using unverified session as last resort")
            async with aiohttp.ClientSession() as session:
                connector = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(connector=connector) as session:
                    rate = await self._fetch_with_session(session)
                    
                    if rate:
                        self.cache[cache_key] = {
                            'rate': rate,
                            'sources': 3,
                            'timestamp': now
                        }
                        self.last_update[cache_key] = now
                        
                        logger.info(f"TON/USDT rate updated (unverified): {rate:.4f}")
                        return rate
                        
        except Exception as e:
            logger.error(f"Even unverified session failed: {e}")
        
        # Fallback to cached rate if available
        if cache_key in self.cache:
            logger.warning("Using stale cached rate due to API failures")
            return self.cache[cache_key]['rate']
        
        # Final fallback to hardcoded rate
        logger.warning("Using hardcoded fallback rate")
        return 3.16
    
    def get_cached_rate(self, pair: str) -> Optional[float]:
        """Get cached exchange rate"""
        return self.cache.get(pair, {}).get('rate')
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache information for monitoring"""
        info = {}
        for pair, data in self.cache.items():
            info[pair] = {
                'rate': data['rate'],
                'sources': data.get('sources', 1),
                'age_seconds': time.time() - data['timestamp'],
                'fresh': time.time() - data['timestamp'] < self.cache_duration
            }
        return info

# Global instance
secure_exchange_rate_fetcher = SecureExchangeRateFetcher()
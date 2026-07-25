import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any
import time

from .ssl_config import create_secure_aiohttp_session, get_ssl_config_for_environment
logger = logging.getLogger(__name__)

class ExchangeRateFetcher:
    """Fetches real-time exchange rates from crypto exchanges"""
    
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
    
    async def _fetch_from_exchange(self, session: aiohttp.ClientSession, exchange: Dict) -> Optional[float]:
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
        """Get current TON/USDT exchange rate with fallback"""
        # Check cache first
        cache_key = 'TON_USDT'
        now = time.time()
        
        if cache_key in self.cache and cache_key in self.last_update:
            if now - self.last_update[cache_key] < self.cache_duration:
                cached_data = self.cache[cache_key]
                logger.debug(f"Using cached rate: {cached_data['rate']}")
                return cached_data['rate']
        
        # Try multiple approaches for robustness
        session = None
        try:
            # First attempt: secure SSL
            ssl_config = get_ssl_config_for_environment()
            session = create_secure_aiohttp_session(
                timeout=ssl_config.get('timeout', 15),
                ssl_mode=ssl_config.get('ssl_mode', 'secure')
            )
            
            async with session:
                tasks = [self._fetch_from_exchange(session, exchange) for exchange in self.exchange_apis]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                valid_rates = [r for r in results if isinstance(r, (int, float)) and r > 0]
                if valid_rates:
                    return self._calculate_median_rate(cache_key, now, valid_rates)
            
            # Second attempt: fallback SSL - close previous session properly
            if session:
                await session.close()
            session = create_secure_aiohttp_session(
                timeout=ssl_config.get('timeout', 30),
                ssl_mode='fallback'
            )
            
            async with session:
                tasks = [self._fetch_from_exchange(session, exchange) for exchange in self.exchange_apis]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                valid_rates = [r for r in results if isinstance(r, (int, float)) and r > 0]
                if valid_rates:
                    return self._calculate_median_rate(cache_key, now, valid_rates)
            
        except Exception as e:
            logger.warning(f"Secure SSL attempts failed, trying basic: {e}")
        finally:
            if session:
                try:
                    await session.close()
                except Exception as e:
                    logger.warning(f"Error closing session: {e}")
        
        # Third attempt: basic session
        try:
            async with aiohttp.ClientSession() as session:
                tasks = [self._fetch_from_exchange(session, exchange) for exchange in self.exchange_apis]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                valid_rates = [r for r in results if isinstance(r, (int, float)) and r > 0]
                if valid_rates:
                    return self._calculate_median_rate(cache_key, now, valid_rates)
        except Exception as e:
            logger.error(f"All fetch attempts failed: {e}")
        
        # Fallback to cached rate
        if cache_key in self.cache:
            logger.warning("Using stale cached rate due to API failures")
            return self.cache[cache_key]['rate']
        
        # Final hardcoded fallback
        logger.warning("Using hardcoded fallback rate")
        return 3.16
    
    def _calculate_median_rate(self, cache_key: str, now: float, valid_rates: list) -> float:
        """Calculate and cache median rate"""
        sorted_rates = sorted(valid_rates)
        median_rate = sorted_rates[len(valid_rates) // 2]
        
        # Cache the result
        self.cache[cache_key] = {
            'rate': median_rate,
            'sources': len(valid_rates),
            'timestamp': now
        }
        self.last_update[cache_key] = now
        
        logger.info(f"TON/USDT rate updated: {median_rate:.4f} (from {len(valid_rates)} sources)")
        return median_rate
    
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
exchange_rate_fetcher = ExchangeRateFetcher()
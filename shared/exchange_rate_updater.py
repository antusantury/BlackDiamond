import asyncio
import logging
from shared.exchange_rates import exchange_rate_fetcher

logger = logging.getLogger(__name__)

class ExchangeRateUpdater:
    """Background service to keep exchange rates updated"""
    
    def __init__(self):
        self.update_task = None
        self.is_running = False
    
    async def start_updater(self):
        """Start the background rate updater"""
        if self.is_running:
            logger.info("Exchange rate updater already running")
            return
        
        self.is_running = True
        logger.info("Starting exchange rate updater")
        
        # Initial update
        try:
            rate = await exchange_rate_fetcher.get_ton_usdt_rate()
            if rate:
                logger.info(f"Initial TON/USDT rate loaded: {rate:.4f}")
            else:
                logger.warning("Failed to load initial exchange rate")
        except Exception as e:
            logger.error(f"Error loading initial exchange rate: {e}")
        
        # Start periodic updates
        self.update_task = asyncio.create_task(self._periodic_update())
    
    async def stop_updater(self):
        """Stop the background rate updater"""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("Stopping exchange rate updater")
        
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
    
    async def _periodic_update(self):
        """Periodically update exchange rates"""
        while self.is_running:
            try:
                await asyncio.sleep(300)  # Wait 5 minutes
                
                if not self.is_running:
                    break
                
                rate = await exchange_rate_fetcher.get_ton_usdt_rate()
                if rate:
                    logger.debug(f"Exchange rates updated: TON/USDT = {rate:.4f}")
                else:
                    logger.warning("Failed to update exchange rates")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating exchange rates: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(60)
    
    def get_status(self) -> dict:
        """Get updater status"""
        cache_info = exchange_rate_fetcher.get_cache_info()
        
        return {
            'is_running': self.is_running,
            'cache_info': cache_info,
            'ton_usdt_rate': cache_info.get('TON_USDT', {}).get('rate'),
            'rate_age': cache_info.get('TON_USDT', {}).get('age_seconds'),
            'rate_fresh': cache_info.get('TON_USDT', {}).get('fresh', False)
        }

# Global instance
exchange_rate_updater = ExchangeRateUpdater()
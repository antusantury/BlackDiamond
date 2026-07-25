import asyncio
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Health monitoring system for actors"""
    
    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self._actors: Dict[str, 'HealthTracker'] = {}
        self._lock = asyncio.Lock()
        self._monitoring_active = False
        
    def register_actor(self, actor_id: str):
        """Register actor for health monitoring"""
        tracker = HealthTracker(actor_id)
        self._actors[actor_id] = tracker
        logger.info(f"Registered actor {actor_id} for health monitoring")
    
    def unregister_actor(self, actor_id: str):
        """Unregister actor from health monitoring"""
        self._actors.pop(actor_id, None)
        logger.info(f"Unregistered actor {actor_id} from health monitoring")
    
    def heartbeat(self, actor_id: str, state: str):
        """Record heartbeat from actor"""
        if actor_id in self._actors:
            self._actors[actor_id].update(state)
    
    async def start_monitoring(self):
        """Start health monitoring"""
        self._monitoring_active = True
        logger.info("Started actor health monitoring")
        
        while self._monitoring_active:
            try:
                await self._check_actor_health()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self._monitoring_active = False
        logger.info("Stopped actor health monitoring")
    
    async def _check_actor_health(self):
        """Check health of all registered actors"""
        async with self._lock:
            current_time = time.time()
            failed_actors = []
            
            for actor_id, tracker in self._actors.items():
                if tracker.is_healthy(current_time):
                    logger.debug(f"Actor {actor_id} is healthy")
                else:
                    logger.warning(f"Actor {actor_id} is unhealthy")
                    failed_actors.append(actor_id)
            
            return failed_actors
    
    def get_stats(self) -> Dict[str, Any]:
        """Get health monitoring statistics"""
        return {
            "total_actors": len(self._actors),
            "healthy_actors": sum(1 for tracker in self._actors.values() 
                                if tracker.is_healthy()),
            "failed_actors": sum(1 for tracker in self._actors.values() 
                               if not tracker.is_healthy())
        }


class HealthTracker:
    """Individual actor health tracker"""
    
    def __init__(self, actor_id: str):
        self.actor_id = actor_id
        self.last_heartbeat = time.time()
        self.last_state = "unknown"
        self.consecutive_failures = 0
        self.max_failures = 3
    
    def update(self, state: str):
        """Update actor state and heartbeat"""
        self.last_heartbeat = time.time()
        self.last_state = state
        
        if state in ["error", "failed"]:
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0
    
    def is_healthy(self, current_time: Optional[float] = None) -> bool:
        """Check if actor is healthy"""
        if current_time is None:
            current_time = time.time()
        
        # Check if heartbeat is recent
        heartbeat_stale = current_time - self.last_heartbeat > 60  # 1 minute
        
        # Check for too many failures
        too_many_failures = self.consecutive_failures >= self.max_failures
        
        is_healthy = not heartbeat_stale and not too_many_failures
        
        return is_healthy
    
    def reset_failures(self):
        """Reset failure count"""
        self.consecutive_failures = 0


# Export all components
__all__ = [
    'HealthMonitor',
    'HealthTracker'
]
import asyncio
import time
import logging
import statistics
import sqlite3
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import threading
import functools
from contextlib import contextmanager


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitMetrics:
    """Metrics for circuit breaker monitoring"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_calls: int = 0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    failure_rate: float = 0.0
    avg_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    response_times: List[float] = field(default_factory=list)
    
    def add_call(self, success: bool, response_time: float, timeout: bool = False):
        """Add a call result to metrics"""
        self.total_calls += 1
        
        if timeout:
            self.timeout_calls += 1
            self.failed_calls += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.last_failure_time = datetime.now(timezone.utc)
        elif success:
            self.successful_calls += 1
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.last_success_time = datetime.now(timezone.utc)
        else:
            self.failed_calls += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.last_failure_time = datetime.now(timezone.utc)
            
        # Update response time statistics
        self.response_times.append(response_time)
        self.response_times = self.response_times[-100:]  # Keep only last 100
        
        self.min_response_time = min(self.min_response_time, response_time)
        self.max_response_time = max(self.max_response_time, response_time)
        
        # Calculate rolling failure rate (last 20 calls)
        recent_calls = self.response_times[-20:] if len(self.response_times) >= 20 else self.response_times
        recent_successes = len(recent_calls) - min(len(recent_calls), self.failed_calls)
        if len(recent_calls) > 0:
            self.failure_rate = (len(recent_calls) - recent_successes) / len(recent_calls)
        else:
            self.failure_rate = 0.0
            
        # Calculate average response time
        if self.response_times:
            self.avg_response_time = statistics.mean(self.response_times)
        else:
            self.avg_response_time = 0.0
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'timeout_calls': self.timeout_calls,
            'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
            'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'consecutive_failures': self.consecutive_failures,
            'consecutive_successes': self.consecutive_successes,
            'failure_rate': round(self.failure_rate, 3),
            'avg_response_time': round(self.avg_response_time, 3),
            'min_response_time': round(self.min_response_time, 3) if self.min_response_time != float('inf') else 0,
            'max_response_time': round(self.max_response_time, 3),
            'current_state': getattr(self, 'current_state', 'unknown')
        }


@dataclass
class CircuitConfig:
    """Configuration for circuit breaker"""
    failure_threshold: float = 0.5      # Failure rate threshold to open circuit
    success_threshold: int = 3          # Success count to close circuit from half-open
    timeout: float = 60.0               # Seconds to wait before trying half-open
    expected_exception: type = Exception  # Exception type that counts as failure
    name: str = ""                      # Circuit breaker name
    
    # Sliding window configuration
    window_size: int = 20               # Number of calls to consider for failure rate
    min_calls: int = 5                  # Minimum calls before evaluating failure rate
    
    # Recovery configuration
    recovery_timeout: float = 30.0      # Time to wait before attempting recovery
    max_recovery_attempts: int = 3      # Maximum recovery attempts
    
    # Health check configuration
    health_check_enabled: bool = True
    health_check_interval: float = 10.0
    health_check_timeout: float = 5.0


class CircuitBreaker:
    """Circuit breaker implementation with metrics and health monitoring"""
    
    def __init__(self, config: CircuitConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.metrics = CircuitMetrics()
        self.state_lock = threading.RLock()
        self.logger = logging.getLogger(f"CircuitBreaker.{config.name or 'default'}")

        # State transition tracking
        self.last_state_change = datetime.now(timezone.utc)
        self.state_changes: List[tuple] = []  # (timestamp, from_state, to_state, reason)

        # Health check
        self._health_check_task: Optional[asyncio.Task] = None
        self._stop_health_check = False

        # Defer health check initialization to avoid event loop issues during import
        self._health_check_initialized = False
            
    def _start_health_check(self):
        """Start background health check task"""
        async def health_check_loop():
            while not self._stop_health_check:
                try:
                    await asyncio.sleep(self.config.health_check_interval)
                    if self.state == CircuitState.OPEN:
                        await self._attempt_recovery()
                except Exception as e:
                    self.logger.error(f"Health check error: {e}")

        # Only start health check if we have a running event loop
        try:
            loop = asyncio.get_running_loop()
            self._health_check_task = loop.create_task(health_check_loop())
            self._health_check_initialized = True
        except RuntimeError:
            # No running event loop, defer initialization
            self.logger.debug(f"Health check deferred for circuit {self.config.name} - no running event loop")
            self._health_check_initialized = False
        
    async def _attempt_recovery(self):
        """Attempt to transition from OPEN to HALF_OPEN"""
        with self.state_lock:
            if self.state != CircuitState.OPEN:
                return
                
            time_since_open = (datetime.now(timezone.utc) - self.last_state_change).total_seconds()
            
            if time_since_open >= self.config.timeout:
                self._transition_to_half_open("Recovery timeout reached")
                
    def _transition_to_half_open(self, reason: str):
        """Transition circuit breaker to HALF_OPEN state"""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.last_state_change = datetime.now(timezone.utc)
        self.state_changes.append((datetime.now(timezone.utc), old_state.value, self.state.value, reason))
        self.metrics.consecutive_successes = 0  # Reset for half-open testing
        
        self.logger.info(f"Circuit breaker {self.config.name} transitioned from {old_state.value} to {self.state.value}: {reason}")
        
    def _transition_to_open(self, reason: str):
        """Transition circuit breaker to OPEN state"""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.last_state_change = datetime.now(timezone.utc)
        self.state_changes.append((datetime.now(timezone.utc), old_state.value, self.state.value, reason))
        
        self.logger.warning(f"Circuit breaker {self.config.name} transitioned from {old_state.value} to {self.state.value}: {reason}")
        
    def _transition_to_closed(self, reason: str):
        """Transition circuit breaker to CLOSED state"""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.last_state_change = datetime.now(timezone.utc)
        self.state_changes.append((datetime.now(timezone.utc), old_state.value, self.state.value, reason))
        
        self.logger.info(f"Circuit breaker {self.config.name} transitioned from {old_state.value} to {self.state.value}: {reason}")
        
    def _should_open(self) -> bool:
        """Determine if circuit should be opened based on metrics"""
        # Check if we have enough calls to evaluate
        if self.metrics.total_calls < self.config.min_calls:
            return False
            
        # Check failure rate threshold
        if self.metrics.failure_rate >= self.config.failure_threshold:
            return True
            
        # Check consecutive failures
        if self.metrics.consecutive_failures >= 3:
            return True
            
        return False
        
    def _should_close_from_half_open(self) -> bool:
        """Determine if circuit should be closed from half-open"""
        return self.metrics.consecutive_successes >= self.config.success_threshold
        
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        start_time = time.time()
        
        # Check state before executing
        with self.state_lock:
            if self.state == CircuitState.OPEN:
                # Circuit is open, reject request
                raise CircuitOpenError(f"Circuit breaker {self.config.name} is OPEN")
                
        try:
            # Execute function
            result = func(*args, **kwargs)
            response_time = time.time() - start_time
            
            # Record success
            self._record_success(response_time)
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            is_expected_failure = isinstance(e, self.config.expected_exception)
            
            # Record failure
            self._record_failure(response_time, timeout=False, expected_failure=is_expected_failure)
            
            if not is_expected_failure:
                # Re-raise unexpected exceptions
                raise
                
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection"""
        start_time = time.time()
        
        # Check state before executing
        with self.state_lock:
            if self.state == CircuitState.OPEN:
                # Circuit is open, reject request
                raise CircuitOpenError(f"Circuit breaker {self.config.name} is OPEN")
                
        try:
            # Execute async function
            result = await func(*args, **kwargs)
            response_time = time.time() - start_time
            
            # Record success
            self._record_success(response_time)
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            is_expected_failure = isinstance(e, self.config.expected_exception)
            
            # Record failure
            self._record_failure(response_time, timeout=False, expected_failure=is_expected_failure)
            
            if not is_expected_failure:
                # Re-raise unexpected exceptions
                raise
                
    def _record_success(self, response_time: float):
        """Record successful call"""
        with self.state_lock:
            # Add to metrics
            self.metrics.add_call(success=True, response_time=response_time)
            
            # Check state transitions
            if self.state == CircuitState.HALF_OPEN:
                if self._should_close_from_half_open():
                    self._transition_to_closed("Success threshold reached in half-open state")
                    
    def _record_failure(self, response_time: float, timeout: bool = False, expected_failure: bool = True):
        """Record failed call"""
        with self.state_lock:
            # Add to metrics
            self.metrics.add_call(success=False, response_time=response_time, timeout=timeout)
            
            # Check state transitions
            if self.state == CircuitState.CLOSED:
                if self._should_open():
                    self._transition_to_open("Failure threshold exceeded")
            elif self.state == CircuitState.HALF_OPEN:
                # Any failure in half-open state opens the circuit
                self._transition_to_open("Failure during half-open test")
                
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state and metrics"""
        with self.state_lock:
            return {
                'state': self.state.value,
                'last_state_change': self.last_state_change.isoformat(),
                'time_in_current_state': (datetime.now(timezone.utc) - self.last_state_change).total_seconds(),
                'metrics': self.metrics.to_dict(),
                'recent_state_changes': [
                    {
                        'timestamp': change[0].isoformat(),
                        'from_state': change[1],
                        'to_state': change[2],
                        'reason': change[3]
                    }
                    for change in self.state_changes[-10:]  # Last 10 changes
                ]
            }
            
    def reset(self):
        """Reset circuit breaker to initial state"""
        with self.state_lock:
            old_state = self.state
            self.state = CircuitState.CLOSED
            self.metrics = CircuitMetrics()
            self.last_state_change = datetime.now(timezone.utc)
            
            self.logger.info(f"Circuit breaker {self.config.name} reset from {old_state.value} to CLOSED")
            
    async def stop(self):
        """Stop circuit breaker and cleanup resources"""
        self._stop_health_check = True
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

    def initialize_health_check(self):
        """Initialize health check when event loop is available"""
        if not self._health_check_initialized and self.config.health_check_enabled:
            try:
                loop = asyncio.get_running_loop()
                async def health_check_loop():
                    while not self._stop_health_check:
                        try:
                            await asyncio.sleep(self.config.health_check_interval)
                            if self.state == CircuitState.OPEN:
                                await self._attempt_recovery()
                        except Exception as e:
                            self.logger.error(f"Health check error: {e}")

                self._health_check_task = loop.create_task(health_check_loop())
                self._health_check_initialized = True
                self.logger.debug(f"Health check initialized for circuit {self.config.name}")
            except RuntimeError:
                # Still no running event loop
                pass


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitRegistry:
    """Registry for managing multiple circuit breakers"""
    
    def __init__(self):
        self.circuits: Dict[str, CircuitBreaker] = {}
        self.registry_lock = threading.RLock()
        self.logger = logging.getLogger("CircuitRegistry")
        
    def register(self, name: str, config: CircuitConfig) -> CircuitBreaker:
        """Register a new circuit breaker"""
        with self.registry_lock:
            if name in self.circuits:
                self.logger.warning(f"Circuit breaker {name} already exists, updating configuration")

            circuit = CircuitBreaker(config)
            self.circuits[name] = circuit
            self.logger.info(f"Registered circuit breaker: {name}")

            # Try to initialize health check if event loop is available
            try:
                circuit.initialize_health_check()
            except Exception as e:
                self.logger.debug(f"Health check initialization deferred for {name}: {e}")

            return circuit
            
    def get_circuit(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        with self.registry_lock:
            return self.circuits.get(name)
            
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states of all registered circuits"""
        with self.registry_lock:
            return {name: circuit.get_state() for name, circuit in self.circuits.items()}
            
    def get_unhealthy_services(self) -> List[str]:
        """Get list of services with open circuits"""
        with self.registry_lock:
            return [name for name, circuit in self.circuits.items() 
                    if circuit.state == CircuitState.OPEN]
                    
    def reset_circuit(self, name: str) -> bool:
        """Reset specific circuit breaker"""
        with self.registry_lock:
            circuit = self.circuits.get(name)
            if circuit:
                circuit.reset()
                return True
            return False
            
    def reset_all(self):
        """Reset all circuit breakers"""
        with self.registry_lock:
            for circuit in self.circuits.values():
                circuit.reset()
                
    async def stop_all(self):
        """Stop all circuit breakers"""
        with self.registry_lock:
            stop_tasks = [circuit.stop() for circuit in self.circuits.values()]
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)


# Global circuit registry
circuit_registry = CircuitRegistry()


def circuit_breaker(name: str = None, failure_threshold: float = 0.5,
                   timeout: float = 60.0, expected_exception: type = Exception,
                   success_threshold: int = 3):
    """Decorator for adding circuit breaker protection to functions with lazy initialization"""

    def decorator(func: Callable) -> Callable:
        circuit_name = name or f"{func.__module__}.{func.__name__}"

        # Store configuration for lazy initialization
        config = CircuitConfig(
            name=circuit_name,
            failure_threshold=failure_threshold,
            timeout=timeout,
            expected_exception=expected_exception,
            success_threshold=success_threshold
        )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Lazy initialization of circuit breaker
            circuit = circuit_registry.get_circuit(circuit_name)
            if circuit is None:
                circuit = circuit_registry.register(circuit_name, config)
            return await circuit.call_async(func, *args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Lazy initialization of circuit breaker
            circuit = circuit_registry.get_circuit(circuit_name)
            if circuit is None:
                circuit = circuit_registry.register(circuit_name, config)
            return circuit.call(func, *args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class ExternalServiceCircuitBreaker:
    """Specialized circuit breaker for external services"""
    
    @staticmethod
    def create_blockchain_circuit(service_name: str) -> CircuitBreaker:
        """Create circuit breaker for blockchain services"""
        config = CircuitConfig(
            name=f"blockchain_{service_name}",
            failure_threshold=0.3,      # Lower threshold for external services
            timeout=30.0,               # Shorter timeout
            expected_exception=(ConnectionError, TimeoutError),
            success_threshold=5,        # Need more successes to close
            min_calls=3,
            window_size=10,
            health_check_enabled=True,
            health_check_interval=15.0
        )
        return circuit_registry.register(f"blockchain_{service_name}", config)
        
    @staticmethod
    def create_database_circuit(service_name: str) -> CircuitBreaker:
        """Create circuit breaker for database services"""
        config = CircuitConfig(
            name=f"database_{service_name}",
            failure_threshold=0.2,      # Very low threshold for critical services
            timeout=15.0,               # Quick timeout
            expected_exception=(ConnectionError, sqlite3.Error),
            success_threshold=10,       # Many successes needed
            min_calls=5,
            window_size=20,
            health_check_enabled=True,
            health_check_interval=5.0
        )
        return circuit_registry.register(f"database_{service_name}", config)
        
    @staticmethod
    def create_payment_circuit(service_name: str) -> CircuitBreaker:
        """Create circuit breaker for payment services"""
        config = CircuitConfig(
            name=f"payment_{service_name}",
            failure_threshold=0.1,      # Very low threshold for financial services
            timeout=10.0,               # Very quick timeout
            expected_exception=(ConnectionError, TimeoutError, PaymentError),
            success_threshold=20,       # Many successes needed
            min_calls=5,
            window_size=30,
            health_check_enabled=True,
            health_check_interval=3.0
        )
        return circuit_registry.register(f"payment_{service_name}", config)

    @staticmethod
    def create_external_circuit(service_name: str) -> CircuitBreaker:
        """Create circuit breaker for generic external services"""
        config = CircuitConfig(
            name=f"external_{service_name}",
            failure_threshold=0.4,
            timeout=30.0,
            expected_exception=(ConnectionError, TimeoutError),
            success_threshold=5,
            min_calls=3,
            window_size=10,
            health_check_enabled=True,
            health_check_interval=10.0
        )
        return circuit_registry.register(f"external_{service_name}", config)


# Convenience functions for creating standard circuit breakers
def create_trongrid_circuit() -> CircuitBreaker:
    """Create circuit breaker for TronGrid API"""
    return ExternalServiceCircuitBreaker.create_blockchain_circuit("trongrid")


def create_toncenter_circuit() -> CircuitBreaker:
    """Create circuit breaker for TonCenter API"""
    return ExternalServiceCircuitBreaker.create_blockchain_circuit("toncenter")


def create_database_circuit() -> CircuitBreaker:
    """Create circuit breaker for main database"""
    return ExternalServiceCircuitBreaker.create_database_circuit("main")


def create_payment_processor_circuit() -> CircuitBreaker:
    """Create circuit breaker for payment processing"""
    return ExternalServiceCircuitBreaker.create_payment_circuit("processor")


@contextmanager
def circuit_breaker_context(circuit_name: str, timeout: float = 30.0):
    """Context manager for circuit breaker operations"""
    circuit = circuit_registry.get_circuit(circuit_name)
    if not circuit:
        raise ValueError(f"Circuit breaker {circuit_name} not found")
        
    try:
        yield circuit
    except CircuitOpenError:
        # Circuit is open, handle gracefully
        logger = logging.getLogger(f"CircuitBreaker.{circuit_name}")
        logger.warning(f"Circuit {circuit_name} is OPEN, operation rejected")
        raise
    except Exception:
        # Other errors, let them propagate
        raise


# Initialize default circuit breakers
def initialize_default_circuits():
    """Initialize default circuit breakers for common services"""
    try:
        create_trongrid_circuit()
        create_toncenter_circuit()
        create_database_circuit()
        create_payment_processor_circuit()

        logging.getLogger(__name__).info("Default circuit breakers initialized")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Default circuit breakers initialization failed: {e}")
        # Don't fail the entire application if circuit breakers can't be initialized

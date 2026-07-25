import logging
import asyncio
import time
import uuid
import traceback
import functools
import sqlite3
import requests
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification"""
    NETWORK = "network"
    DATABASE = "database"
    BLOCKCHAIN = "blockchain"
    PAYMENT = "payment"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM = "system"
    EXTERNAL_API = "external_api"


@dataclass
class ErrorContext:
    """Context information for error handling"""
    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    service: str = ""
    operation: str = ""
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    request_data: Dict[str, Any] = field(default_factory=dict)
    environment: str = "production"
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            'error_id': self.error_id,
            'timestamp': self.timestamp.isoformat(),
            'service': self.service,
            'operation': self.operation,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'correlation_id': self.correlation_id,
            'request_data': self.request_data,
            'environment': self.environment,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries
        }


@dataclass
class ErrorInfo:
    """Structured error information"""
    exception: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    context: ErrorContext
    retryable: bool = True
    permanent: bool = False
    recoverable: bool = True
    suggested_action: str = ""
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        return {
            'error_id': self.context.error_id,
            'timestamp': self.context.timestamp.isoformat(),
            'category': self.category.value,
            'severity': self.severity.value,
            'message': self.message,
            'service': self.context.service,
            'operation': self.context.operation,
            'retryable': self.retryable,
            'permanent': self.permanent,
            'recoverable': self.recoverable,
            'suggested_action': self.suggested_action,
            'error_code': self.error_code,
            'retry_count': self.context.retry_count,
            'metadata': self.metadata,
            'exception_type': type(self.exception).__name__,
            'exception_message': str(self.exception),
            'traceback': traceback.format_exception(type(self.exception), self.exception, self.exception.__traceback__)
        }


class ErrorClassifier:
    """Classifies errors and determines appropriate handling strategy"""
    
    @staticmethod
    def classify_error(exception: Exception, context: ErrorContext) -> ErrorInfo:
        """Classify an error and return ErrorInfo"""
        
        # Network errors
        if isinstance(exception, (ConnectionError, TimeoutError, OSError)):
            category = ErrorCategory.NETWORK
            severity = ErrorSeverity.HIGH
            retryable = True
            suggested_action = "Check network connectivity and retry operation"
            
        # Blockchain errors
        elif any(keyword in str(exception).lower() for keyword in ['tron', 'ton', 'blockchain', 'transaction', 'api.trongrid', 'toncenter']):
            category = ErrorCategory.BLOCKCHAIN
            severity = ErrorSeverity.HIGH
            retryable = True
            suggested_action = "Blockchain service unavailable, retry with exponential backoff"
            
        # Database errors
        elif isinstance(exception, (sqlite3.Error, ConnectionError)) or 'database' in str(exception).lower():
            category = ErrorCategory.DATABASE
            severity = ErrorSeverity.HIGH
            retryable = True
            suggested_action = "Database service unavailable, retry operation"
            
        # Authentication errors
        elif isinstance(exception, (PermissionError, AuthenticationError)):
            category = ErrorCategory.AUTHENTICATION
            severity = ErrorSeverity.MEDIUM
            retryable = False
            suggested_action = "Check authentication credentials"
            
        # Validation errors
        elif isinstance(exception, (ValueError, TypeError, ValidationError)):
            category = ErrorCategory.VALIDATION
            severity = ErrorSeverity.LOW
            retryable = False
            suggested_action = "Correct input validation errors"
            
        # External API errors
        elif isinstance(exception, (requests.exceptions.RequestException,)):
            category = ErrorCategory.EXTERNAL_API
            severity = ErrorSeverity.HIGH
            retryable = True
            suggested_action = "External API service unavailable, retry with backoff"
            
        # Payment errors
        elif any(keyword in str(exception).lower() for keyword in ['payment', 'escrow', 'balance', 'withdrawal']):
            category = ErrorCategory.PAYMENT
            severity = ErrorSeverity.HIGH
            retryable = True
            suggested_action = "Payment service unavailable, retry operation"
            
        # System errors
        elif isinstance(exception, (SystemExit, KeyboardInterrupt)):
            category = ErrorCategory.SYSTEM
            severity = ErrorSeverity.CRITICAL
            retryable = False
            suggested_action = "System shutting down"
            
        # Default classification
        else:
            category = ErrorCategory.BUSINESS_LOGIC
            severity = ErrorSeverity.MEDIUM
            retryable = True
            suggested_action = "Internal processing error, retry if appropriate"
            
        # Determine permanent vs temporary
        permanent = category in [ErrorCategory.VALIDATION, ErrorCategory.AUTHENTICATION]
        recoverable = category not in [ErrorCategory.VALIDATION]
        
        return ErrorInfo(
            exception=exception,
            category=category,
            severity=severity,
            message=str(exception),
            context=context,
            retryable=retryable,
            permanent=permanent,
            recoverable=recoverable,
            suggested_action=suggested_action,
            error_code=f"{category.value.upper()}_{type(exception).__name__}"
        )


class RetryManager:
    """Manages retry policies with exponential backoff"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        
    def calculate_delay(self, retry_count: int) -> float:
        """Calculate delay with exponential backoff and jitter"""
        delay = min(self.base_delay * (2 ** retry_count), self.max_delay)
        # Add jitter to avoid thundering herd
        import random
        jitter = delay * 0.1 * random.random()
        return delay + jitter
        
    def should_retry(self, error_info: ErrorInfo, retry_count: int) -> bool:
        """Determine if operation should be retried"""
        if retry_count >= self.max_retries:
            return False
        if not error_info.retryable:
            return False
        if error_info.permanent:
            return False
        return True


class FallbackManager:
    """Manages fallback strategies for graceful degradation"""
    
    def __init__(self):
        self.fallback_strategies: Dict[str, Callable] = {}
        self.register_default_strategies()
        
    def register_strategy(self, service_name: str, strategy: Callable):
        """Register fallback strategy for a service"""
        self.fallback_strategies[service_name] = strategy
        
    def register_default_strategies(self):
        """Register default fallback strategies"""
        self.register_strategy('database', self._database_fallback)
        self.register_strategy('blockchain', self._blockchain_fallback)
        self.register_strategy('external_api', self._external_api_fallback)
        self.register_strategy('payment', self._payment_fallback)
        
    async def _database_fallback(self, context: ErrorContext, *args, **kwargs):
        """Database fallback strategy"""
        return {
            'fallback': True,
            'strategy': 'read_only',
            'message': 'Database service temporarily unavailable',
            'data': {'status': 'degraded', 'mode': 'read_only'}
        }
        
    async def _blockchain_fallback(self, context: ErrorContext, *args, **kwargs):
        """Blockchain service fallback strategy"""
        return {
            'fallback': True,
            'strategy': 'cached_response',
            'message': 'Blockchain service temporarily unavailable',
            'data': {'status': 'degraded', 'mode': 'cached'}
        }
        
    async def _external_api_fallback(self, context: ErrorContext, *args, **kwargs):
        """External API fallback strategy"""
        return {
            'fallback': True,
            'strategy': 'default_response',
            'message': 'External service temporarily unavailable',
            'data': {'status': 'degraded', 'mode': 'default'}
        }
        
    async def _payment_fallback(self, context: ErrorContext, *args, **kwargs):
        """Payment service fallback strategy"""
        return {
            'fallback': True,
            'strategy': 'queue_processing',
            'message': 'Payment service temporarily unavailable',
            'data': {'status': 'degraded', 'mode': 'queued'}
        }
        
    async def execute_fallback(self, service_name: str, context: ErrorContext, *args, **kwargs):
        """Execute fallback strategy for a service"""
        strategy = self.fallback_strategies.get(service_name)
        if strategy:
            return await strategy(context, *args, **kwargs)
        else:
            return {
                'fallback': True,
                'strategy': 'none',
                'message': f'No fallback strategy for {service_name}',
                'data': {'status': 'failed'}
            }


class ErrorHandler:
    """Central error handling manager"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.retry_manager = RetryManager()
        self.fallback_manager = FallbackManager()
        self.error_handlers: Dict[ErrorCategory, Callable] = {}
        self.global_error_count = 0
        self.recent_errors: List[ErrorInfo] = []
        self.max_recent_errors = 100
        
    def register_error_handler(self, category: ErrorCategory, handler: Callable):
        """Register custom error handler for category"""
        self.error_handlers[category] = handler
        
    def handle_error(self, exception: Exception, context: ErrorContext = None, 
                    fallback_on_error: bool = True) -> ErrorInfo:
        """Handle an error with classification and processing"""
        
        # Create context if not provided
        if context is None:
            context = ErrorContext()
            
        # Classify error
        error_info = ErrorClassifier.classify_error(exception, context)
        
        # Add to recent errors
        self._add_recent_error(error_info)
        
        # Log error
        self._log_error(error_info)
        
        # Execute custom handler if available
        handler = self.error_handlers.get(error_info.category)
        if handler:
            try:
                handler(error_info)
            except Exception as handler_exception:
                self.logger.error(f"Error in custom handler for {error_info.category}: {handler_exception}")
                
        return error_info
        
    def _add_recent_error(self, error_info: ErrorInfo):
        """Add error to recent errors list"""
        self.recent_errors.append(error_info)
        if len(self.recent_errors) > self.max_recent_errors:
            self.recent_errors.pop(0)
            
    def _log_error(self, error_info: ErrorInfo):
        """Log error with appropriate level"""
        error_dict = error_info.to_dict()
        exception = error_info.exception
        exc_info = (type(exception), exception, exception.__traceback__) if exception else None
        
        # Use different log levels based on severity
        if error_info.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(
                f"CRITICAL ERROR: {error_info.message}",
                extra={'error_info': error_dict},
                exc_info=exc_info,
            )
        elif error_info.severity == ErrorSeverity.HIGH:
            self.logger.error(
                f"HIGH SEVERITY ERROR: {error_info.message}",
                extra={'error_info': error_dict},
                exc_info=exc_info,
            )
        elif error_info.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(
                f"MEDIUM SEVERITY ERROR: {error_info.message}",
                extra={'error_info': error_dict},
                exc_info=exc_info,
            )
        else:
            self.logger.info(f"LOW SEVERITY ERROR: {error_info.message}", extra={'error_info': error_dict})
            
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics"""
        now = datetime.now(timezone.utc)
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)
        
        recent_errors = [e for e in self.recent_errors if e.context.timestamp > last_hour]
        daily_errors = [e for e in self.recent_errors if e.context.timestamp > last_day]
        
        return {
            'total_errors': len(self.recent_errors),
            'errors_last_hour': len(recent_errors),
            'errors_last_day': len(daily_errors),
            'error_categories': {
                category.value: len([e for e in self.recent_errors if e.category == category])
                for category in ErrorCategory
            },
            'error_severities': {
                severity.value: len([e for e in self.recent_errors if e.severity == severity])
                for severity in ErrorSeverity
            },
            'top_error_messages': {}
        }


# Global error handler instance
error_handler = ErrorHandler()


def handle_errors(operation_name: str = "", service: str = "", fallback_on_error: bool = True):
    """Decorator for automatic error handling"""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            context = ErrorContext(
                service=service or func.__module__,
                operation=operation_name or func.__name__
            )
            
            max_retries = kwargs.pop('max_retries', 3)
            context.max_retries = max_retries
            
            for retry_count in range(max_retries + 1):
                try:
                    # Add correlation ID if available in kwargs
                    if 'correlation_id' in kwargs:
                        context.correlation_id = kwargs['correlation_id']
                    if 'user_id' in kwargs:
                        context.user_id = kwargs['user_id']
                        
                    result = await func(*args, **kwargs)
                    return result
                    
                except Exception as exception:
                    context.retry_count = retry_count
                    error_info = error_handler.handle_error(exception, context, fallback_on_error)
                    
                    # Check if we should retry
                    if error_info.retryable and retry_count < max_retries:
                        # Calculate delay and wait
                        delay = error_handler.retry_manager.calculate_delay(retry_count)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # No more retries or non-retryable error
                        if fallback_on_error and error_info.recoverable:
                            # Try fallback
                            fallback_result = await error_handler.fallback_manager.execute_fallback(
                                service, context, *args, **kwargs
                            )
                            return fallback_result
                        else:
                            # Re-raise original exception
                            raise
                            
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            context = ErrorContext(
                service=service or func.__module__,
                operation=operation_name or func.__name__
            )
            
            max_retries = kwargs.pop('max_retries', 3)
            context.max_retries = max_retries
            
            for retry_count in range(max_retries + 1):
                try:
                    # Add correlation ID if available in kwargs
                    if 'correlation_id' in kwargs:
                        context.correlation_id = kwargs['correlation_id']
                    if 'user_id' in kwargs:
                        context.user_id = kwargs['user_id']
                        
                    result = func(*args, **kwargs)
                    return result
                    
                except Exception as exception:
                    context.retry_count = retry_count
                    error_info = error_handler.handle_error(exception, context, fallback_on_error)
                    
                    # Check if we should retry
                    if error_info.retryable and retry_count < max_retries:
                        # Calculate delay and wait
                        delay = error_handler.retry_manager.calculate_delay(retry_count)
                        time.sleep(delay)
                        continue
                    else:
                        # No more retries or non-retryable error
                        if fallback_on_error and error_info.recoverable:
                            # Try fallback (synchronous version)
                            fallback_result = error_handler.fallback_manager.execute_fallback(
                                service, context, *args, **kwargs
                            )
                            return fallback_result
                        else:
                            # Re-raise original exception
                            raise
                            
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


@contextmanager
def error_context(operation: str, service: str = "", **context_data):
    """Context manager for error handling"""
    context = ErrorContext(
        service=service or "unknown",
        operation=operation,
        **context_data
    )
    
    try:
        yield context
    except Exception as exception:
        error_handler.handle_error(exception, context)
        raise


class GracefulDegradationManager:
    """Manages graceful degradation across services"""
    
    def __init__(self):
        self.service_status: Dict[str, Dict[str, Any]] = {}
        self.degradation_rules: List[Callable] = []
        
    def register_service(self, service_name: str, health_check: Callable = None):
        """Register a service for health monitoring"""
        self.service_status[service_name] = {
            'status': 'healthy',
            'last_check': datetime.now(timezone.utc),
            'error_count': 0,
            'health_check': health_check
        }
        
    async def check_service_health(self, service_name: str) -> bool:
        """Check if service is healthy"""
        if service_name not in self.service_status:
            return False
            
        service_info = self.service_status[service_name]
        
        if service_info['health_check']:
            try:
                is_healthy = await service_info['health_check']()
                service_info['last_check'] = datetime.now(timezone.utc)
                
                if is_healthy:
                    service_info['error_count'] = 0
                    service_info['status'] = 'healthy'
                else:
                    service_info['error_count'] += 1
                    service_info['status'] = 'degraded' if service_info['error_count'] < 5 else 'unhealthy'
                    
                return is_healthy
                
            except Exception:
                service_info['error_count'] += 1
                service_info['status'] = 'unhealthy'
                return False
                
        return service_info['status'] == 'healthy'
        
    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Get current status of a service"""
        return self.service_status.get(service_name, {'status': 'unknown'})
        
    def is_service_available(self, service_name: str) -> bool:
        """Check if service is available for operations"""
        status = self.get_service_status(service_name)
        return status.get('status') in ['healthy', 'degraded']
        
    def get_degraded_services(self) -> List[str]:
        """Get list of services in degraded state"""
        return [name for name, info in self.service_status.items() 
                if info['status'] in ['degraded', 'unhealthy']]


# Global degradation manager
degradation_manager = GracefulDegradationManager()


# Custom exceptions
class BlackDiamondError(Exception):
    """Base exception for Black Diamond platform"""
    def __init__(self, message: str, error_code: str = None, context: Dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}


class BlockchainError(BlackDiamondError):
    """Blockchain-related errors"""
    pass


class PaymentError(BlackDiamondError):
    """Payment-related errors"""
    pass


class DatabaseError(BlackDiamondError):
    """Database-related errors"""
    pass


class AuthenticationError(BlackDiamondError):
    """Authentication-related errors"""
    pass


class ValidationError(BlackDiamondError):
    """Validation-related errors"""
    pass

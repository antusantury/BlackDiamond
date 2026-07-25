import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union, List, Type

from .typings import ErrorSeverity, ErrorContext, UserID, DealCode, PaymentID


# === BASE EXCEPTIONS ===

class BlackDiamondBaseException(Exception):
    """Base exception for all Black Diamond errors"""
    
    def __init__(
        self, 
        message: str, 
        context: Optional[ErrorContext] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.context = context
        self.severity = severity
        self.code = code or self.__class__.__name__
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/API responses"""
        result = {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'code': self.code,
            'severity': self.severity.value if self.severity else None,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details
        }
        
        if self.context:
            result['context'] = {
                'service': self.context.service,
                'operation': self.context.operation,
                'correlation_id': self.context.correlation_id,
                'user_id': self.context.user_id,
                'request_id': self.context.request_id,
                'metadata': self.context.metadata
            }
        
        if self.cause:
            result['cause'] = {
                'type': self.cause.__class__.__name__,
                'message': str(self.cause)
            }
        
        return result
    
    def log(self, logger: logging.Logger, level: str = 'error'):
        """Log exception with full context"""
        log_data = self.to_dict()
        log_message = f"[{self.code}] {self.message}"
        
        if level.upper() == 'CRITICAL':
            logger.critical(log_message, extra=log_data)
        elif level.upper() == 'ERROR':
            logger.error(log_message, extra=log_data)
        elif level.upper() == 'WARNING':
            logger.warning(log_message, extra=log_data)
        else:
            logger.info(log_message, extra=log_data)


# === DOMAIN-SPECIFIC EXCEPTIONS ===

class DomainException(BlackDiamondBaseException):
    """Base exception for domain-related errors"""
    pass


# === USER EXCEPTIONS ===

class UserException(DomainException):
    """Base exception for user-related errors"""
    pass


class UserNotFoundError(UserException):
    """User not found exception"""
    
    def __init__(
        self, 
        user_id: UserID, 
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"User {user_id} not found",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={'user_id': user_id, **(details or {})}
        )
        self.user_id = user_id


class UserAlreadyExistsError(UserException):
    """User already exists exception"""
    
    def __init__(
        self, 
        user_id: UserID, 
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"User {user_id} already exists",
            context=context,
            severity=ErrorSeverity.LOW,
            details={'user_id': user_id, **(details or {})}
        )
        self.user_id = user_id


class UserBannedError(UserException):
    """User is banned exception"""
    
    def __init__(
        self, 
        user_id: UserID, 
        reason: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"User {user_id} is banned" + (f": {reason}" if reason else ""),
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'user_id': user_id, 'reason': reason, **(details or {})}
        )
        self.user_id = user_id
        self.reason = reason


class InsufficientBalanceError(UserException):
    """Insufficient balance exception"""
    
    def __init__(
        self, 
        user_id: UserID, 
        required_amount: Union[int, float, str],
        current_balance: Union[int, float, str],
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Insufficient balance: required {required_amount}, current {current_balance}",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={
                'user_id': user_id,
                'required_amount': str(required_amount),
                'current_balance': str(current_balance),
                **(details or {})
            }
        )
        self.user_id = user_id
        self.required_amount = str(required_amount)
        self.current_balance = str(current_balance)


# === DEAL EXCEPTIONS ===

class DealException(DomainException):
    """Base exception for deal-related errors"""
    pass


class DealNotFoundError(DealException):
    """Deal not found exception"""
    
    def __init__(
        self, 
        deal_code: DealCode, 
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Deal {deal_code} not found",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={'deal_code': deal_code, **(details or {})}
        )
        self.deal_code = deal_code


class DealAlreadyExistsError(DealException):
    """Deal already exists exception"""
    
    def __init__(
        self, 
        deal_code: DealCode, 
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Deal {deal_code} already exists",
            context=context,
            severity=ErrorSeverity.LOW,
            details={'deal_code': deal_code, **(details or {})}
        )
        self.deal_code = deal_code


class DealInvalidStatusError(DealException):
    """Deal invalid status exception"""
    
    def __init__(
        self, 
        deal_code: DealCode, 
        current_status: str,
        expected_statuses: List[str],
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Deal {deal_code} has invalid status {current_status}, expected one of: {expected_statuses}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={
                'deal_code': deal_code,
                'current_status': current_status,
                'expected_statuses': expected_statuses,
                **(details or {})
            }
        )
        self.deal_code = deal_code
        self.current_status = current_status
        self.expected_statuses = expected_statuses


class DealAmountInvalidError(DealException):
    """Deal amount validation error"""
    
    def __init__(
        self, 
        deal_code: DealCode,
        amount: Union[int, float, str],
        min_amount: Union[int, float, str],
        max_amount: Union[int, float, str],
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Deal {deal_code} amount {amount} is outside valid range [{min_amount}, {max_amount}]",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={
                'deal_code': deal_code,
                'amount': str(amount),
                'min_amount': str(min_amount),
                'max_amount': str(max_amount),
                **(details or {})
            }
        )
        self.deal_code = deal_code
        self.amount = str(amount)
        self.min_amount = str(min_amount)
        self.max_amount = str(max_amount)


class DealUnauthorizedError(DealException):
    """Deal unauthorized access exception"""
    
    def __init__(
        self, 
        deal_code: DealCode, 
        user_id: UserID,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"User {user_id} not authorized for deal {deal_code}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'deal_code': deal_code, 'user_id': user_id, **(details or {})}
        )
        self.deal_code = deal_code
        self.user_id = user_id


# === PAYMENT EXCEPTIONS ===

class PaymentException(DomainException):
    """Base exception for payment-related errors"""
    pass


class PaymentNotFoundError(PaymentException):
    """Payment not found exception"""
    
    def __init__(
        self, 
        payment_id: PaymentID, 
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Payment {payment_id} not found",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={'payment_id': payment_id, **(details or {})}
        )
        self.payment_id = payment_id


class PaymentTimeoutError(PaymentException):
    """Payment timeout exception"""
    
    def __init__(
        self, 
        payment_id: PaymentID,
        timeout_seconds: int,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Payment {payment_id} timed out after {timeout_seconds} seconds",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={
                'payment_id': payment_id,
                'timeout_seconds': timeout_seconds,
                **(details or {})
            }
        )
        self.payment_id = payment_id
        self.timeout_seconds = timeout_seconds


class PaymentConfirmationFailedError(PaymentException):
    """Payment confirmation failed exception"""
    
    def __init__(
        self, 
        payment_id: PaymentID,
        tx_hash: Optional[str] = None,
        confirmations: int = 0,
        required_confirmations: int = 1,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Payment {payment_id} confirmation failed: {confirmations}/{required_confirmations} confirmations",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={
                'payment_id': payment_id,
                'tx_hash': tx_hash,
                'confirmations': confirmations,
                'required_confirmations': required_confirmations,
                **(details or {})
            }
        )
        self.payment_id = payment_id
        self.tx_hash = tx_hash
        self.confirmations = confirmations
        self.required_confirmations = required_confirmations


class PaymentAmountMismatchError(PaymentException):
    """Payment amount mismatch exception"""
    
    def __init__(
        self, 
        payment_id: PaymentID,
        expected_amount: Union[int, float, str],
        actual_amount: Union[int, float, str],
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Payment {payment_id} amount mismatch: expected {expected_amount}, got {actual_amount}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={
                'payment_id': payment_id,
                'expected_amount': str(expected_amount),
                'actual_amount': str(actual_amount),
                **(details or {})
            }
        )
        self.payment_id = payment_id
        self.expected_amount = str(expected_amount)
        self.actual_amount = str(actual_amount)


class BlockchainNetworkError(PaymentException):
    """Blockchain network error exception"""
    
    def __init__(
        self, 
        network: str,
        error_message: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Blockchain network {network} error: {error_message}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'network': network, 'error_message': error_message, **(details or {})}
        )
        self.network = network
        self.error_message = error_message


# === DATABASE EXCEPTIONS ===

class DatabaseException(BlackDiamondBaseException):
    """Base exception for database-related errors"""
    pass


class DatabaseConnectionError(DatabaseException):
    """Database connection error"""
    
    def __init__(
        self, 
        message: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message,
            context=context,
            severity=ErrorSeverity.CRITICAL,
            details=details
        )


class DatabaseQueryError(DatabaseException):
    """Database query error"""
    
    def __init__(
        self, 
        query: str,
        error_message: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Database query failed: {error_message}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'query': query, 'error_message': error_message, **(details or {})}
        )
        self.query = query
        self.error_message = error_message


class DatabaseIntegrityError(DatabaseException):
    """Database integrity constraint violation"""
    
    def __init__(
        self, 
        constraint: str,
        error_message: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Database integrity error: {constraint} - {error_message}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'constraint': constraint, 'error_message': error_message, **(details or {})}
        )
        self.constraint = constraint
        self.error_message = error_message


# === VALIDATION EXCEPTIONS ===

class ValidationException(BlackDiamondBaseException):
    """Base exception for validation errors"""
    pass


class InvalidInputError(ValidationException):
    """Invalid input data exception"""
    
    def __init__(
        self, 
        field: str,
        value: Any,
        reason: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Invalid input for field '{field}': {reason}",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={
                'field': field,
                'value': str(value),
                'reason': reason,
                **(details or {})
            }
        )
        self.field = field
        self.value = value
        self.reason = reason


class MissingRequiredFieldError(ValidationException):
    """Missing required field exception"""
    
    def __init__(
        self, 
        field: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Missing required field: {field}",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={'field': field, **(details or {})}
        )
        self.field = field


# === EXTERNAL SERVICE EXCEPTIONS ===

class ExternalServiceException(BlackDiamondBaseException):
    """Base exception for external service errors"""
    pass


class APIRateLimitError(ExternalServiceException):
    """API rate limit exceeded"""
    
    def __init__(
        self, 
        service: str,
        retry_after: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Rate limit exceeded for {service}" + (f", retry after {retry_after} seconds" if retry_after else ""),
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={'service': service, 'retry_after': retry_after, **(details or {})}
        )
        self.service = service
        self.retry_after = retry_after


class ExternalAPITimeoutError(ExternalServiceException):
    """External API timeout exception"""
    
    def __init__(
        self, 
        service: str,
        timeout_seconds: int,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"External API {service} timed out after {timeout_seconds} seconds",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'service': service, 'timeout_seconds': timeout_seconds, **(details or {})}
        )
        self.service = service
        self.timeout_seconds = timeout_seconds


class ExternalAPIError(ExternalServiceException):
    """General external API error"""
    
    def __init__(
        self, 
        service: str,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"External API {service} error" + (f": {error_message}" if error_message else ""),
            context=context,
            severity=ErrorSeverity.HIGH,
            details={
                'service': service,
                'status_code': status_code,
                'error_message': error_message,
                **(details or {})
            }
        )
        self.service = service
        self.status_code = status_code
        self.error_message = error_message


# === CONFIGURATION EXCEPTIONS ===

class ConfigurationException(BlackDiamondBaseException):
    """Base exception for configuration errors"""
    pass


class MissingConfigurationError(ConfigurationException):
    """Missing configuration exception"""
    
    def __init__(
        self, 
        key: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Missing configuration key: {key}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'key': key, **(details or {})}
        )
        self.key = key


class InvalidConfigurationError(ConfigurationException):
    """Invalid configuration exception"""
    
    def __init__(
        self, 
        key: str,
        value: Any,
        expected_type: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Invalid configuration for {key}: expected {expected_type}, got {type(value).__name__}",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={
                'key': key,
                'value': str(value),
                'expected_type': expected_type,
                'actual_type': type(value).__name__,
                **(details or {})
            }
        )
        self.key = key
        self.value = value
        self.expected_type = expected_type
        self.actual_type = type(value).__name__


# === SECURITY EXCEPTIONS ===

class SecurityException(BlackDiamondBaseException):
    """Base exception for security-related errors"""
    pass


class AuthenticationError(SecurityException):
    """Authentication error"""
    
    def __init__(
        self, 
        message: str = "Authentication failed",
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message,
            context=context,
            severity=ErrorSeverity.HIGH,
            details=details
        )


class AuthorizationError(SecurityException):
    """Authorization error"""
    
    def __init__(
        self, 
        action: str,
        resource: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Authorization failed for {action}" + (f" on {resource}" if resource else ""),
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'action': action, 'resource': resource, **(details or {})}
        )
        self.action = action
        self.resource = resource


class RateLimitExceededError(SecurityException):
    """Rate limit exceeded exception"""
    
    def __init__(
        self, 
        key: str,
        limit: int,
        window_seconds: int,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Rate limit exceeded for {key}: {limit} requests per {window_seconds} seconds",
            context=context,
            severity=ErrorSeverity.MEDIUM,
            details={
                'key': key,
                'limit': limit,
                'window_seconds': window_seconds,
                **(details or {})
            }
        )
        self.key = key
        self.limit = limit
        self.window_seconds = window_seconds


# === SYSTEM EXCEPTIONS ===

class SystemException(BlackDiamondBaseException):
    """Base exception for system-level errors"""
    pass


class MaintenanceModeError(SystemException):
    """System in maintenance mode exception"""
    
    def __init__(
        self, 
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            "System is in maintenance mode",
            context=context,
            severity=ErrorSeverity.LOW,
            details=details
        )


class CircuitBreakerOpenError(SystemException):
    """Circuit breaker open exception"""
    
    def __init__(
        self, 
        circuit_name: str,
        context: Optional[ErrorContext] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Circuit breaker {circuit_name} is open",
            context=context,
            severity=ErrorSeverity.HIGH,
            details={'circuit_name': circuit_name, **(details or {})}
        )
        self.circuit_name = circuit_name


# === EXCEPTION FACTORIES ===

class ExceptionFactory:
    """Factory for creating context-aware exceptions"""
    
    @staticmethod
    def create_user_not_found(user_id: UserID, context: Optional[ErrorContext] = None) -> UserNotFoundError:
        return UserNotFoundError(user_id, context=context)
    
    @staticmethod
    def create_deal_not_found(deal_code: DealCode, context: Optional[ErrorContext] = None) -> DealNotFoundError:
        return DealNotFoundError(deal_code, context=context)
    
    @staticmethod
    def create_payment_not_found(payment_id: PaymentID, context: Optional[ErrorContext] = None) -> PaymentNotFoundError:
        return PaymentNotFoundError(payment_id, context=context)
    
    @staticmethod
    def create_database_error(message: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None) -> DatabaseException:
        return DatabaseException(message, context=context, cause=cause)
    
    @staticmethod
    def create_validation_error(field: str, value: Any, reason: str, context: Optional[ErrorContext] = None) -> InvalidInputError:
        return InvalidInputError(field, value, reason, context=context)
    
    @staticmethod
    def create_external_service_error(service: str, message: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None) -> ExternalServiceException:
        return ExternalServiceException(f"{service}: {message}", context=context, cause=cause)


# === EXCEPTION HANDLERS ===

class ExceptionHandler:
    """Centralized exception handling utilities"""
    
    @staticmethod
    def safe_execute(func: callable, *args, context: Optional[ErrorContext] = None, logger: Optional[logging.Logger] = None, **kwargs) -> Union[Any, Exception]:
        """Safely execute a function and return result or exception"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if logger:
                if isinstance(e, BlackDiamondBaseException):
                    e.log(logger)
                else:
                    logger.error(f"Unhandled exception in {func.__name__}: {e}", extra={
                        'exception_type': e.__class__.__name__,
                        'exception_message': str(e),
                        'function': func.__name__,
                        'args': str(args),
                        'kwargs': str(kwargs)
                    })
            return e
    
    @staticmethod
    def is_retryable_error(error: Exception) -> bool:
        """Check if an error is retryable"""
        if isinstance(error, (DatabaseConnectionError, ExternalAPITimeoutError, APIRateLimitError)):
            return True
        if isinstance(error, ExternalServiceException) and error.severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]:
            return True
        return False
    
    @staticmethod
    def should_circuit_break(error: Exception) -> bool:
        """Check if error should trigger circuit breaker"""
        return isinstance(error, (
            DatabaseConnectionError,
            ExternalAPITimeoutError, 
            ExternalAPIError,
            BlockchainNetworkError,
            CircuitBreakerOpenError
        )) and error.severity == ErrorSeverity.CRITICAL


# === EXCEPTION REGISTRY ===

class ExceptionRegistry:
    """Registry for exception mappings and hierarchies"""
    
    _registry: Dict[str, Type[BlackDiamondBaseException]] = {}
    
    @classmethod
    def register(cls, name: str, exception_class: Type[BlackDiamondBaseException]):
        """Register an exception class"""
        cls._registry[name] = exception_class
    
    @classmethod
    def get_exception_class(cls, name: str) -> Optional[Type[BlackDiamondBaseException]]:
        """Get exception class by name"""
        return cls._registry.get(name)
    
    @classmethod
    def get_all_exceptions(cls) -> List[Type[BlackDiamondBaseException]]:
        """Get all registered exception classes"""
        return list(cls._registry.values())


# Auto-register core exceptions
EXCEPTION_REGISTRY = {
    'UserNotFound': UserNotFoundError,
    'DealNotFound': DealNotFoundError,
    'PaymentNotFound': PaymentNotFoundError,
    'DatabaseError': DatabaseException,
    'ValidationError': ValidationException,
    'ExternalServiceError': ExternalServiceException,
    'SecurityError': SecurityException,
    'SystemError': SystemException,
}

for name, exc_class in EXCEPTION_REGISTRY.items():
    ExceptionRegistry.register(name, exc_class)


# === EXPORTS ===

__all__ = [
    # Base exception
    'BlackDiamondBaseException',
    
    # Domain exceptions
    'DomainException',
    
    # User exceptions
    'UserException', 'UserNotFoundError', 'UserAlreadyExistsError', 
    'UserBannedError', 'InsufficientBalanceError',
    
    # Deal exceptions
    'DealException', 'DealNotFoundError', 'DealAlreadyExistsError',
    'DealInvalidStatusError', 'DealAmountInvalidError', 'DealUnauthorizedError',
    
    # Payment exceptions
    'PaymentException', 'PaymentNotFoundError', 'PaymentTimeoutError',
    'PaymentConfirmationFailedError', 'PaymentAmountMismatchError', 'BlockchainNetworkError',
    
    # Database exceptions
    'DatabaseException', 'DatabaseConnectionError', 'DatabaseQueryError', 'DatabaseIntegrityError',
    
    # Validation exceptions
    'ValidationException', 'InvalidInputError', 'MissingRequiredFieldError',
    
    # External service exceptions
    'ExternalServiceException', 'APIRateLimitError', 'ExternalAPITimeoutError', 'ExternalAPIError',
    
    # Configuration exceptions
    'ConfigurationException', 'MissingConfigurationError', 'InvalidConfigurationError',
    
    # Security exceptions
    'SecurityException', 'AuthenticationError', 'AuthorizationError', 'RateLimitExceededError',
    
    # System exceptions
    'SystemException', 'MaintenanceModeError', 'CircuitBreakerOpenError',
    
    # Factories and handlers
    'ExceptionFactory', 'ExceptionHandler', 'ExceptionRegistry',
    
    # Types
    'ErrorContext',
]
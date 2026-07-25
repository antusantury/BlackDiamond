import logging
from typing import Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Base class for database-related errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        self.timestamp = datetime.now()
        super().__init__(self.message)

class ValidationError(DatabaseError):
    """Exception raised for validation errors."""
    
    def __init__(self, field: str, value: Any, message: str):
        self.field = field
        self.value = value
        super().__init__(f"Validation error for field '{field}' with value '{value}': {message}")

class ConnectionError(DatabaseError):
    """Exception raised for database connection errors."""
    pass

class TransactionError(DatabaseError):
    """Exception raised for transaction-related errors."""
    pass

def handle_database_error(func):
    """Decorator to handle and log database errors consistently."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Database error in {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise DatabaseError(error_msg, e) from e
    return wrapper

def log_and_reraise(logger_instance: logging.Logger, level: str = "error"):
    """Decorator to log exceptions and re-raise them."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_method = getattr(logger_instance, level.lower())
                log_method(f"Error in {func.__name__}: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator

class DatabaseMetrics:
    """Utility class for tracking database operation metrics."""
    
    def __init__(self):
        self.query_count = 0
        self.error_count = 0
        self.average_response_time = 0.0
        
    def record_query(self, response_time: float):
        """Record a successful query."""
        self.query_count += 1
        # Simple moving average
        if self.average_response_time == 0:
            self.average_response_time = response_time
        else:
            self.average_response_time = (self.average_response_time + response_time) / 2
            
    def record_error(self):
        """Record an error."""
        self.error_count += 1
        
    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            'query_count': self.query_count,
            'error_count': self.error_count,
            'average_response_time': self.average_response_time,
            'error_rate': (self.error_count / max(1, self.query_count + self.error_count)) * 100
        }
import uuid
import logging
import time
from typing import Optional, Callable
from functools import wraps
import threading

# Thread-local storage for correlation IDs
_local = threading.local()

logger = logging.getLogger(__name__)


class CorrelationMiddleware:
    """Middleware for managing correlation IDs."""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the middleware for a Flask app."""

        @app.before_request
        def before_request():
            """Set a correlation ID before each request."""
            # Check request headers
            correlation_id = self.get_correlation_id_from_request()

            if not correlation_id:
                correlation_id = self.generate_correlation_id()

            self.set_correlation_id(correlation_id)

            # Log request start
            from flask import request
            logger.info(
                f"Request started: {request.method} {request.path}",
                extra={
                    'correlation_id': correlation_id,
                    'method': request.method,
                    'path': request.path,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'remote_addr': request.remote_addr,
                    'request_id': correlation_id
                }
            )

        @app.after_request
        def after_request(response):
            """Add a correlation ID to response headers."""
            correlation_id = self.get_correlation_id()
            if correlation_id:
                response.headers['X-Correlation-ID'] = correlation_id

                # Log request completion
                from flask import request, g
                duration = getattr(g, 'request_start_time', None)
                if duration:
                    duration = time.time() - duration

                logger.info(
                    f"Request completed: {request.method} {request.path} -> {response.status_code}",
                    extra={
                        'correlation_id': correlation_id,
                        'method': request.method,
                        'path': request.path,
                        'status_code': response.status_code,
                        'duration': round(duration, 3) if duration else None,
                        'request_id': correlation_id
                    }
                )

            return response

        @app.before_request
        def set_request_start_time():
            """Store request start time."""
            from flask import g
            g.request_start_time = time.time()

    def generate_correlation_id(self) -> str:
        """Generate a new correlation ID."""
        return str(uuid.uuid4())

    def get_correlation_id(self) -> Optional[str]:
        """Get the current correlation ID from thread-local storage."""
        return getattr(_local, 'correlation_id', None)

    def set_correlation_id(self, correlation_id: str):
        """Set the correlation ID in thread-local storage."""
        _local.correlation_id = correlation_id

    def get_correlation_id_from_request(self) -> Optional[str]:
        """Extract correlation ID from request headers."""
        try:
            from flask import request
            return request.headers.get('X-Correlation-ID') or \
                   request.headers.get('X-Request-ID') or \
                   request.headers.get('Correlation-ID')
        except RuntimeError:
            # Not in a Flask request context
            return None

    def clear_correlation_id(self):
        """Clear the correlation ID."""
        if hasattr(_local, 'correlation_id'):
            delattr(_local, 'correlation_id')


def correlation_logging_filter(record: logging.LogRecord) -> bool:
    """Logging filter that injects the correlation ID."""
    correlation_id = getattr(_local, 'correlation_id', None)
    if correlation_id:
        record.correlation_id = correlation_id
        record.request_id = correlation_id
    else:
        record.correlation_id = 'no-correlation-id'
        record.request_id = 'no-correlation-id'

    return True


def setup_correlation_logging(logger_name: str = None):
    """Configure logging with correlation IDs."""

    # Configure filter for the root logger
    root_logger = logging.getLogger()
    root_logger.addFilter(correlation_logging_filter)

    # If a specific logger is provided, configure it too
    if logger_name:
        specific_logger = logging.getLogger(logger_name)
        specific_logger.addFilter(correlation_logging_filter)


def get_current_correlation_id() -> Optional[str]:
    """Return the current correlation ID."""
    return getattr(_local, 'correlation_id', None)


def with_correlation_id(correlation_id: str = None):
    """Decorator to set a correlation ID for async functions."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Preserve the existing correlation ID
            existing_id = get_current_correlation_id()

            # Set a new correlation ID
            if correlation_id:
                _local.correlation_id = correlation_id
            elif not existing_id:
                _local.correlation_id = str(uuid.uuid4())

            try:
                return await func(*args, **kwargs)
            finally:
                # Restore the existing correlation ID
                if existing_id:
                    _local.correlation_id = existing_id
                elif hasattr(_local, 'correlation_id'):
                    delattr(_local, 'correlation_id')

        return wrapper
    return decorator


def log_with_correlation(level: int, message: str, *args, **kwargs):
    """Log with the correlation ID automatically added."""
    correlation_id = get_current_correlation_id()
    if correlation_id:
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        kwargs['extra']['correlation_id'] = correlation_id
        kwargs['extra']['request_id'] = correlation_id

    logger.log(level, message, *args, **kwargs)


class CorrelationContextManager:
    """Context manager for correlation IDs."""

    def __init__(self, correlation_id: str = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.existing_id = None

    def __enter__(self):
        self.existing_id = get_current_correlation_id()
        _local.correlation_id = self.correlation_id
        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.existing_id:
            _local.correlation_id = self.existing_id
        elif hasattr(_local, 'correlation_id'):
            delattr(_local, 'correlation_id')


def create_correlation_context(correlation_id: str = None) -> CorrelationContextManager:
    """Create a context manager for correlation IDs."""
    return CorrelationContextManager(correlation_id)


# Global middleware instance
correlation_middleware = CorrelationMiddleware()


# Convenience logging helpers
def log_info(message: str, **kwargs):
    """Log INFO with correlation ID."""
    log_with_correlation(logging.INFO, message, **kwargs)


def log_warning(message: str, **kwargs):
    """Log WARNING with correlation ID."""
    log_with_correlation(logging.WARNING, message, **kwargs)


def log_error(message: str, **kwargs):
    """Log ERROR with correlation ID."""
    log_with_correlation(logging.ERROR, message, **kwargs)


def log_debug(message: str, **kwargs):
    """Log DEBUG with correlation ID."""
    log_with_correlation(logging.DEBUG, message, **kwargs)


# Initialize correlation middleware in the app
def init_correlation_middleware(app):
    """Initialize correlation middleware for a Flask app."""
    correlation_middleware.init_app(app)
    setup_correlation_logging()

    # Configure formatter for logs with correlation ID
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
    )

    # Apply to existing handlers and add filter
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
        handler.addFilter(correlation_logging_filter)
    
    # Add filter to all loggers
    root_logger = logging.getLogger()
    root_logger.addFilter(correlation_logging_filter)

    logger.info("Correlation middleware initialized")


# SQLAlchemy extension (optional)
class CorrelationSQLAlchemy:
    """SQLAlchemy extension for correlation IDs."""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize for Flask-SQLAlchemy."""

        @app.before_request
        def set_sqlalchemy_correlation():
            """Attach the correlation ID to the SQLAlchemy context."""
            correlation_id = get_current_correlation_id()
            if correlation_id and hasattr(app, 'db'):
                # If Flask-SQLAlchemy is used, attach correlation_id to the session context
                from flask import g
                g.correlation_id = correlation_id

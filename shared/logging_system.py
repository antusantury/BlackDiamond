import logging
import logging.handlers
import json
import time
import uuid
import threading
import functools
import asyncio
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import sys
import os
import fnmatch


class LogLevel(Enum):
    """Custom log levels"""
    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    SECURITY = 60  # For security-related logs


class LogCategory(Enum):
    """Log categories for structured logging"""
    SYSTEM = "system"
    WEB = "web"
    BUSINESS = "business"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ERROR = "error"
    AUDIT = "audit"
    PAYMENT = "payment"
    BLOCKCHAIN = "blockchain"
    ESCROW = "escrow"
    DATABASE = "database"
    API = "api"
    NETWORK = "network"
    USER_ACTION = "user_action"


@dataclass
class LogContext:
    """Context information for structured logging"""
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    request_id: Optional[str] = None
    service: str = "black_diamond"
    environment: str = "production"
    version: str = "1.0.0"
    hostname: str = os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'unknown')
    process_id: int = os.getpid()
    thread_id: int = threading.get_ident()
    operation: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging"""
        result = {
            'correlation_id': self.correlation_id,
            'service': self.service,
            'environment': self.environment,
            'version': self.version,
            'hostname': self.hostname,
            'process_id': self.process_id,
            'thread_id': self.thread_id,
        }
        
        if self.session_id:
            result['session_id'] = self.session_id
        if self.user_id:
            result['user_id'] = self.user_id
        if self.request_id:
            result['request_id'] = self.request_id
            
        result.update(self.custom_fields)
        return result


@dataclass
class StructuredLogEntry:
    """Structured log entry"""
    timestamp: datetime
    level: str
    category: LogCategory
    message: str
    context: LogContext
    exception_info: Optional[str] = None
    stack_trace: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level,
            'category': self.category.value,
            'message': self.message,
            'context': self.context.to_dict(),
            'exception_info': self.exception_info,
            'stack_trace': self.stack_trace,
            'duration_ms': self.duration_ms,
            'metadata': self.metadata,
            'performance_metrics': self.performance_metrics
        }


class CorrelationIdContext:
    """Context variable for correlation ID management"""
    
    def __init__(self):
        self._local = threading.local()
        
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current thread"""
        self._local.correlation_id = correlation_id
        
    def get_correlation_id(self) -> Optional[str]:
        """Get correlation ID for current thread"""
        return getattr(self._local, 'correlation_id', None)
        
    def clear_correlation_id(self):
        """Clear correlation ID for current thread"""
        if hasattr(self._local, 'correlation_id'):
            delattr(self._local, 'correlation_id')


# Global correlation ID context
correlation_context = CorrelationIdContext()


class PerformanceLogger:
    """Performance logging and metrics collection"""
    
    def __init__(self):
        self.metrics: Dict[str, List[float]] = {}
        self.metrics_lock = threading.RLock()
        
    def record_timing(self, operation: str, duration_ms: float, **tags):
        """Record operation timing"""
        with self.metrics_lock:
            key = f"{operation}"
            if key not in self.metrics:
                self.metrics[key] = []
            self.metrics[key].append(duration_ms)
            
            # Keep only last 1000 measurements
            if len(self.metrics[key]) > 1000:
                self.metrics[key] = self.metrics[key][-1000:]
                
    def get_statistics(self, operation: str) -> Dict[str, Any]:
        """Get statistics for an operation"""
        with self.metrics_lock:
            if operation not in self.metrics:
                return {}
                
            timings = self.metrics[operation]
            if not timings:
                return {}
                
            import statistics
            
            return {
                'operation': operation,
                'count': len(timings),
                'avg_ms': statistics.mean(timings),
                'median_ms': statistics.median(timings),
                'min_ms': min(timings),
                'max_ms': max(timings),
                'p95_ms': self._percentile(timings, 95),
                'p99_ms': self._percentile(timings, 99),
                'total_ms': sum(timings)
            }
            
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile"""
        if not data:
            return 0.0
        data_sorted = sorted(data)
        index = (len(data_sorted) - 1) * percentile / 100
        if index.is_integer():
            return data_sorted[int(index)]
        else:
            lower = data_sorted[int(index)]
            upper = data_sorted[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))


# Global performance logger
performance_logger = PerformanceLogger()


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        # Create structured log entry
        context = LogContext()
        
        # Extract context from record
        if hasattr(record, 'correlation_id'):
            context.correlation_id = record.correlation_id
        if hasattr(record, 'session_id'):
            context.session_id = record.session_id
        if hasattr(record, 'user_id'):
            context.user_id = record.user_id
        if hasattr(record, 'category'):
            category = record.category
        else:
            category = LogCategory.SYSTEM
            
        # Extract additional fields
        metadata = {}
        for attr in ['operation', 'duration_ms', 'status_code', 'request_path', 'method']:
            if hasattr(record, attr):
                metadata[attr] = getattr(record, attr)
        if hasattr(record, 'error_info'):
            metadata['error_info'] = getattr(record, 'error_info')
                
        # Create log entry
        entry = StructuredLogEntry(
            timestamp=datetime.now(timezone.utc),
            level=record.levelname,
            category=category,
            message=record.getMessage(),
            context=context,
            exception_info=str(record.exc_info[1]) if record.exc_info else None,
            stack_trace=traceback.format_exception(record.exc_info[0], record.exc_info[1], record.exc_info[2]) if record.exc_info else None,
            metadata=metadata
        )
        
        # Convert to JSON
        return json.dumps(entry.to_dict(), ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Console formatter for human-readable output"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output"""
        def _ascii(text: str) -> str:
            if not text:
                return ""
            try:
                return str(text).encode("ascii", errors="ignore").decode("ascii", errors="ignore")
            except Exception:
                return ""

        # Get correlation ID
        correlation_id = getattr(record, 'correlation_id', correlation_context.get_correlation_id())
        correlation_id_str = f"[{correlation_id[:8]}]" if correlation_id else "[N/A]"
        
        # Get category
        category = getattr(record, 'category', 'system')
        category_str = f"[{category.value}]" if hasattr(category, 'value') else f"[{category}]"
        
        # Format timestamp
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]
        
        # Format message
        msg = _ascii(record.getMessage())
        
        # Add user info if available
        user_info = ""
        if hasattr(record, 'user_id') and record.user_id:
            user_info = _ascii(f"[user:{record.user_id}]")
            
        # Add operation info if available
        operation_info = ""
        if hasattr(record, 'operation') and record.operation:
            operation_info = _ascii(f"[{record.operation}]")
            
        # Format based on level
        if record.levelno >= logging.ERROR:
            level_color = '\033[91m'  # Red
            level_reset = '\033[0m'
        elif record.levelno >= logging.WARNING:
            level_color = '\033[93m'  # Yellow
            level_reset = '\033[0m'
        else:
            level_color = ''
            level_reset = ''
             
        line = f"{timestamp} {level_color}{record.levelname:<8}{level_reset} {correlation_id_str} {category_str} {user_info} {operation_info} {msg}"
        # Ensure console output is ASCII-only so it never breaks cp1252/cp1251 consoles or UTF-8 parsers.
        return _ascii(line)


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that drops characters not encodable by the target stream.

    This prevents UnicodeEncodeError on Windows consoles (often cp1252) when logs contain emoji.
    """

    @staticmethod
    def _sanitize_for_stream(text: str, stream) -> str:
        if not text:
            return text
        encoding = getattr(stream, "encoding", None) or "utf-8"
        try:
            # Drop only characters the stream can't encode (emoji, etc.)
            return text.encode(encoding, errors="ignore").decode(encoding, errors="ignore")
        except Exception:
            try:
                return text.encode("ascii", errors="ignore").decode("ascii", errors="ignore")
            except Exception:
                return ""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            msg = self._sanitize_for_stream(msg, self.stream)
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


class LogCollector:
    """Collects logs for analysis and monitoring"""
    
    def __init__(self, max_entries: int = 10000):
        self.entries: List[StructuredLogEntry] = []
        self.entries_lock = threading.RLock()
        self.max_entries = max_entries
        self.error_count = 0
        self.warning_count = 0
        self.start_time = datetime.now(timezone.utc)
        
    def add_entry(self, entry: StructuredLogEntry):
        """Add log entry to collector"""
        with self.entries_lock:
            self.entries.append(entry)
            
            # Update counters
            if entry.level == 'ERROR':
                self.error_count += 1
            elif entry.level == 'WARNING':
                self.warning_count += 1
                
            # Trim old entries
            if len(self.entries) > self.max_entries:
                self.entries = self.entries[-self.max_entries:]
                
    def get_recent_entries(self, limit: int = 100, level: str = None, 
                          category: LogCategory = None) -> List[StructuredLogEntry]:
        """Get recent log entries"""
        with self.entries_lock:
            entries = self.entries[-limit:]
            
            # Filter by level
            if level:
                entries = [e for e in entries if e.level == level]
                
            # Filter by category
            if category:
                entries = [e for e in entries if e.category == category]
                
            return entries
            
    def get_statistics(self) -> Dict[str, Any]:
        """Get log statistics"""
        with self.entries_lock:
            now = datetime.now(timezone.utc)
            uptime = now - self.start_time
            
            # Group by level
            level_counts = {}
            for entry in self.entries:
                level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
                
            # Group by category
            category_counts = {}
            for entry in self.entries:
                category_counts[entry.category.value] = category_counts.get(entry.category.value, 0) + 1
                
            return {
                'total_entries': len(self.entries),
                'error_count': self.error_count,
                'warning_count': self.warning_count,
                'uptime_seconds': uptime.total_seconds(),
                'entries_per_second': len(self.entries) / max(uptime.total_seconds(), 1),
                'level_distribution': level_counts,
                'category_distribution': category_counts,
                'recent_errors': len([e for e in self.entries[-100:] if e.level == 'ERROR'])
            }


# Global log collector
log_collector = LogCollector()


class StructuredLogger:
    """Main structured logging class"""
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        # Use root handlers (console/file) to avoid multiple RotatingFileHandlers
        # pointing at the same file (which breaks rollover on Windows).
        self.logger.propagate = True
        self.name = name
        self.log_dir = None
        self.configure(level=level, log_dir=os.getenv("BLACK_DIAMOND_LOG_DIR", "logs"))

    def configure(self, level: int = None, log_dir: str = None) -> None:
        """(Re)configure logger level and log directory.

        Note: Handlers are installed on the root logger in initialize_logging().
        This avoids file rotation issues on Windows when multiple handlers/processes
        try to rotate the same file.
        """
        if level is None:
            level = self.logger.level or logging.INFO
        if log_dir is None:
            log_dir = self.log_dir or "logs"

        self.log_dir = log_dir
        self.logger.setLevel(level)
        self.logger.propagate = True

        os.makedirs(log_dir, exist_ok=True)

        for handler in list(self.logger.handlers):
            try:
                self.logger.removeHandler(handler)
                handler.close()
            except Exception:
                pass
        
    def _log(self, level: int, category: LogCategory, message: str, 
            context: LogContext = None, exception: Exception = None, 
            duration_ms: float = None, **metadata):
        """Internal logging method"""
        
        if context is None:
            context = LogContext()
            
        # Get correlation ID from thread context
        correlation_id = correlation_context.get_correlation_id()
        if correlation_id and not context.correlation_id:
            context.correlation_id = correlation_id
            
        # Record performance metrics
        if duration_ms is not None:
            operation = metadata.pop('operation', 'unknown')
            performance_logger.record_timing(operation, duration_ms, **metadata)
            
        # Create structured log entry
        entry = StructuredLogEntry(
            timestamp=datetime.now(timezone.utc),
            level=logging.getLevelName(level),
            category=category,
            message=message,
            context=context,
            exception_info=str(exception) if exception else None,
            stack_trace=traceback.format_exception(type(exception), exception, exception.__traceback__) if exception else None,
            duration_ms=duration_ms,
            metadata=metadata
        )
        
        # Add to collector
        log_collector.add_entry(entry)
        
        # Create log record
        record = self.logger.makeRecord(
            self.logger.name, level, "", 0, message, (), None
        )
        
        # Add custom fields to record
        record.correlation_id = context.correlation_id
        record.session_id = context.session_id
        record.user_id = context.user_id
        record.category = category
        record.duration_ms = duration_ms
        
        for key, value in metadata.items():
            setattr(record, key, value)
            
        # Handle exception
        if exception:
            record.exc_info = (type(exception), exception, exception.__traceback__)
            
        # Log the record
        self.logger.handle(record)
        
    def trace(self, message: str, category: LogCategory = LogCategory.SYSTEM, 
             context: LogContext = None, **metadata):
        """Log at TRACE level"""
        self._log(LogLevel.TRACE.value, category, message, context, **metadata)
        
    def debug(self, message: str, category: LogCategory = LogCategory.SYSTEM, 
             context: LogContext = None, **metadata):
        """Log at DEBUG level"""
        self._log(logging.DEBUG, category, message, context, **metadata)
        
    def info(self, message: str, category: LogCategory = LogCategory.SYSTEM, 
            context: LogContext = None, **metadata):
        """Log at INFO level"""
        self._log(logging.INFO, category, message, context, **metadata)
        
    def warning(self, message: str, category: LogCategory = LogCategory.ERROR, 
               context: LogContext = None, exception: Exception = None, **metadata):
        """Log at WARNING level"""
        self._log(logging.WARNING, category, message, context, exception, **metadata)
        
    def error(self, message: str, category: LogCategory = LogCategory.ERROR, 
             context: LogContext = None, exception: Exception = None, **metadata):
        """Log at ERROR level"""
        self._log(logging.ERROR, category, message, context, exception, **metadata)
        
    def critical(self, message: str, category: LogCategory = LogCategory.SECURITY, 
                context: LogContext = None, exception: Exception = None, **metadata):
        """Log at CRITICAL level"""
        self._log(logging.CRITICAL, category, message, context, exception, **metadata)
        
    def security(self, message: str, context: LogContext = None, **metadata):
        """Log security events"""
        self._log(LogLevel.SECURITY.value, LogCategory.SECURITY, message, context, **metadata)
        
    def business(self, message: str, context: LogContext = None, **metadata):
        """Log business events"""
        self._log(logging.INFO, LogCategory.BUSINESS, message, context, **metadata)
        
    def payment(self, message: str, context: LogContext = None, **metadata):
        """Log payment events"""
        self._log(logging.INFO, LogCategory.PAYMENT, message, context, **metadata)
        
    def blockchain(self, message: str, context: LogContext = None, **metadata):
        """Log blockchain events"""
        self._log(logging.INFO, LogCategory.BLOCKCHAIN, message, context, **metadata)
        
    def api(self, message: str, context: LogContext = None, status_code: int = None, **metadata):
        """Log API events"""
        self._log(logging.INFO, LogCategory.API, message, context, duration_ms=metadata.get('duration_ms'), **metadata)
        
    def performance(self, message: str, duration_ms: float, operation: str, context: LogContext = None, **metadata):
        """Log performance events"""
        metadata['operation'] = operation
        self._log(logging.INFO, LogCategory.PERFORMANCE, message, context, duration_ms=duration_ms, **metadata)
        
    def audit(self, message: str, action: str, user_id: int = None, context: LogContext = None, **metadata):
        """Log audit events"""
        metadata['action'] = action
        metadata['user_id'] = user_id
        self._log(logging.INFO, LogCategory.AUDIT, message, context, **metadata)


# Global structured logger
structured_logger = StructuredLogger("BlackDiamond")


def log_operation(operation: str, category: LogCategory = LogCategory.SYSTEM, 
                 level: str = "info"):
    """Decorator for automatic operation logging"""
    
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            context = LogContext()
            
            # Extract user info if available
            if 'user_id' in kwargs:
                context.user_id = kwargs['user_id']
            if 'session_id' in kwargs:
                context.session_id = kwargs['session_id']
                
            try:
                # Set correlation ID
                correlation_context.set_correlation_id(context.correlation_id)
                
                # Log operation start
                structured_logger.info(
                    f"Starting {operation}", 
                    category=category,
                    context=context,
                    operation=operation,
                    status="started"
                )
                
                # Execute function
                result = await func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log success
                structured_logger.performance(
                    f"Completed {operation}",
                    duration_ms=duration_ms,
                    operation=operation,
                    context=context,
                    status="success"
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log error
                structured_logger.error(
                    f"Failed {operation}: {str(e)}",
                    category=category,
                    context=context,
                    exception=e,
                    operation=operation,
                    status="error",
                    duration_ms=duration_ms
                )
                
                raise
                
            finally:
                # Clear correlation ID
                correlation_context.clear_correlation_id()
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            context = LogContext()
            
            # Extract user info if available
            if 'user_id' in kwargs:
                context.user_id = kwargs['user_id']
            if 'session_id' in kwargs:
                context.session_id = kwargs['session_id']
                
            try:
                # Set correlation ID
                correlation_context.set_correlation_id(context.correlation_id)
                
                # Log operation start
                structured_logger.info(
                    f"Starting {operation}",
                    category=category,
                    context=context,
                    operation=operation,
                    status="started"
                )
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log success
                structured_logger.performance(
                    f"Completed {operation}",
                    duration_ms=duration_ms,
                    operation=operation,
                    context=context,
                    status="success"
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log error
                structured_logger.error(
                    f"Failed {operation}: {str(e)}",
                    category=category,
                    context=context,
                    exception=e,
                    operation=operation,
                    status="error",
                    duration_ms=duration_ms
                )
                
                raise
                
            finally:
                # Clear correlation ID
                correlation_context.clear_correlation_id()
                
        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


def create_log_context(**kwargs) -> LogContext:
    """Create log context with provided parameters"""
    return LogContext(**kwargs)


def set_correlation_id(correlation_id: str):
    """Set correlation ID for current thread"""
    correlation_context.set_correlation_id(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get correlation ID for current thread"""
    return correlation_context.get_correlation_id()


def get_performance_stats(operation: str = None) -> Dict[str, Any]:
    """Get performance statistics"""
    if operation:
        return performance_logger.get_statistics(operation)
    else:
        return {
            name: performance_logger.get_statistics(name)
            for name in performance_logger.metrics.keys()
        }


def get_log_stats() -> Dict[str, Any]:
    """Get logging statistics"""
    return log_collector.get_statistics()


def setup_logging(log_level: str = "INFO", log_dir: str = "logs", service_name: Optional[str] = None):
    """Setup logging system (alias for initialize_logging)"""
    return initialize_logging(log_level, log_dir, service_name=service_name)


# Initialize logging system
def _sanitize_log_component(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join(ch if ch in allowed else "_" for ch in value)
    cleaned = cleaned.strip("._-")
    return cleaned[:80]


def _default_service_name() -> str:
    env_name = (
        os.getenv("BLACK_DIAMOND_SERVICE")
        or os.getenv("SERVICE_NAME")
        or os.getenv("APP_NAME")
    )
    env_name = _sanitize_log_component(env_name or "")
    if env_name:
        return env_name

    try:
        argv0 = Path(sys.argv[0]).name
    except Exception:
        argv0 = ""

    argv0 = _sanitize_log_component(Path(argv0).stem if argv0 else "")
    return argv0 or "service"


def _build_log_paths(log_dir: str, service_name: Optional[str] = None) -> tuple[str, str]:
    # Multi-process safe by default: BOT and WEB (and/or multiple workers) must not share
    # the same rotating file on Windows. Include service + PID.
    if os.getenv("BLACK_DIAMOND_LOG_SHARED", "").strip() in {"1", "true", "True", "yes", "YES"}:
        return (
            os.path.join(log_dir, "errors.log"),
            os.path.join(log_dir, "structured.log"),
        )

    explicit_tag = _sanitize_log_component(os.getenv("BLACK_DIAMOND_LOG_TAG", ""))
    if explicit_tag:
        tag = explicit_tag
    else:
        service = _sanitize_log_component(service_name or "") or _default_service_name()
        tag = f"{service}.{os.getpid()}"

    return (
        os.path.join(log_dir, f"errors.{tag}.log"),
        os.path.join(log_dir, f"structured.{tag}.log"),
    )


def _cleanup_old_log_files(log_dir: str, retention_days: int = 7) -> None:
    if retention_days <= 0:
        return

    cutoff = time.time() - (retention_days * 86400)
    patterns = ("structured*.log*", "errors*.log*")

    try:
        for entry in os.scandir(log_dir):
            try:
                if not entry.is_file():
                    continue
                if not any(fnmatch.fnmatch(entry.name, pat) for pat in patterns):
                    continue
                if entry.stat().st_mtime >= cutoff:
                    continue
                try:
                    os.remove(entry.path)
                except PermissionError:
                    # File may still be open/locked on Windows; ignore and try again later.
                    pass
            except FileNotFoundError:
                continue
            except PermissionError:
                continue
    except FileNotFoundError:
        return
    except PermissionError:
        return


def initialize_logging(log_level: str = "INFO", log_dir: str = "logs", service_name: Optional[str] = None):
    """Initialize the logging system"""
    # Resolve log directory. If relative, anchor it at the project root so systemd/cron
    # don't accidentally write logs somewhere unexpected depending on CWD.
    if not os.path.isabs(log_dir):
        project_root = Path(__file__).resolve().parents[1]
        log_dir = str(project_root / log_dir)

    # Create log directory
    os.makedirs(log_dir, exist_ok=True)

    retention_days = os.getenv("BLACK_DIAMOND_LOG_RETENTION_DAYS", "").strip()
    try:
        retention_days_int = int(retention_days) if retention_days else 7
    except ValueError:
        retention_days_int = 7
    _cleanup_old_log_files(log_dir, retention_days=retention_days_int)
    
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    os.environ["BLACK_DIAMOND_LOG_DIR"] = log_dir
    structured_logger.configure(level=numeric_level, log_dir=log_dir)
    
    # Configure Python logging for standard loggers (not just structured_logger)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    def _is_console_stream_handler(handler: logging.Handler) -> bool:
        # logging.FileHandler (and its subclasses like RotatingFileHandler) are also StreamHandlers.
        # We only want "console" stream handlers here.
        return isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)

    # Replace any pre-existing StreamHandlers with a safe version that drops
    # unencodable characters (emoji, etc.) to avoid console crashes on Windows.
    for handler in list(root_logger.handlers):
        if _is_console_stream_handler(handler) and not isinstance(handler, SafeStreamHandler):
            try:
                safe_handler = SafeStreamHandler(getattr(handler, "stream", sys.stdout))
                safe_handler.setLevel(handler.level)
                safe_handler.setFormatter(handler.formatter or ConsoleFormatter())
                root_logger.removeHandler(handler)
                root_logger.addHandler(safe_handler)
            except Exception:
                pass

    def _find_rotating_file_handler(target_path: str) -> Optional[logging.Handler]:
        target_abs = os.path.abspath(target_path)
        for handler in root_logger.handlers:
            if isinstance(handler, (logging.handlers.RotatingFileHandler, logging.handlers.TimedRotatingFileHandler)):
                base = getattr(handler, "baseFilename", None)
                if base and os.path.abspath(base) == target_abs:
                    return handler
        return None

    # Install handlers idempotently. (logging.basicConfig() may have already installed
    # a StreamHandler, which previously prevented file logs from being added.)
    error_log_path, structured_log_path = _build_log_paths(log_dir, service_name=service_name)

    existing_error_handler = _find_rotating_file_handler(error_log_path)
    if existing_error_handler is not None:
        existing_encoding = (getattr(existing_error_handler, "encoding", None) or "").lower()
        if (
            (existing_encoding and existing_encoding != "utf-8")
            or not isinstance(existing_error_handler, logging.handlers.TimedRotatingFileHandler)
        ):
            try:
                root_logger.removeHandler(existing_error_handler)
                existing_error_handler.close()
            except Exception:
                pass
            existing_error_handler = None

    if existing_error_handler is None:
        error_file_handler = logging.handlers.TimedRotatingFileHandler(
            error_log_path,
            when="midnight",
            interval=1,
            backupCount=7,
            utc=True,
            encoding="utf-8",
            errors="backslashreplace",
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(error_file_handler)

    existing_structured_handler = _find_rotating_file_handler(structured_log_path)
    if existing_structured_handler is not None:
        existing_encoding = (getattr(existing_structured_handler, "encoding", None) or "").lower()
        if (
            (existing_encoding and existing_encoding != "utf-8")
            or not isinstance(existing_structured_handler, logging.handlers.TimedRotatingFileHandler)
        ):
            try:
                root_logger.removeHandler(existing_structured_handler)
                existing_structured_handler.close()
            except Exception:
                pass
            existing_structured_handler = None

    if existing_structured_handler is None:
        structured_file_handler = logging.handlers.TimedRotatingFileHandler(
            structured_log_path,
            when="midnight",
            interval=1,
            backupCount=7,
            utc=True,
            encoding="utf-8",
            errors="backslashreplace",
        )
        structured_file_handler.setLevel(logging.DEBUG)
        structured_file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(structured_file_handler)

    # Ensure there is at least one console handler for visibility in process logs.
    if not any(_is_console_stream_handler(h) for h in root_logger.handlers):
        console_handler = SafeStreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(ConsoleFormatter())
        root_logger.addHandler(console_handler)
    
    structured_logger.info("Logging system initialized", 
                          category=LogCategory.SYSTEM,
                          metadata={'log_level': log_level, 'log_dir': log_dir})


if __name__ == "__main__":
    # Test logging system
    initialize_logging()
    
    # Test different log types
    context = create_log_context(user_id=12345, session_id="test_session")
    
    structured_logger.info("Test info message", category=LogCategory.SYSTEM, context=context)
    structured_logger.warning("Test warning message", category=LogCategory.ERROR)
    structured_logger.error("Test error message", category=LogCategory.ERROR)
    structured_logger.payment("Test payment message", context=context)
    structured_logger.blockchain("Test blockchain message")
    
    # Test performance logging
    import time
    time.sleep(0.1)
    structured_logger.performance("Test operation", 100.0, "test_operation")
    
    # Test statistics
    print("Performance stats:", get_performance_stats())
    print("Log stats:", get_log_stats())

# Graceful asyncpg import with fallback for testing
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    # Create mock asyncpg classes for testing
    ASYNCPG_AVAILABLE = False
    
    class MockAsyncPG:
        """Mock asyncpg for testing when not available"""
        class Pool:
            async def acquire(self):
                return MockConnection()
            async def release(self, conn):
                pass
            async def close(self):
                pass
        
        class Connection:
            async def execute(self, query, *args):
                return "OK"
            async def fetchrow(self, query, *args):
                return None
            async def fetchval(self, query, *args):
                return None
            async def fetch(self, query, *args):
                return []
            async def executemany(self, query, data):
                pass
        
        class UniqueViolationError(Exception):
            pass
        
        @staticmethod
        async def create_pool(*args, **kwargs):
            return MockAsyncPG.Pool()
    
    asyncpg = MockAsyncPG()
import os

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Union, Callable, TypeVar
import time
import threading
from decimal import Decimal

from .constants import (
    MIN_DEAL_AMOUNT, MAX_DEAL_AMOUNT, DEFAULT_COMMISSION_RATE,
    AUTO_CONFIRM_TIMEOUT, CURRENCY_UPDATE_INTERVAL,
    TOKEN_VALIDITY,
    SUPPORTED_CURRENCIES,
    DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE, DB_CONNECTION_TIMEOUT
)
from .utils import (
    validate_deal_code, validate_user_id,
    validate_amount_in_range, get_rate_limit
)
from .validation import (
    validate_deal_data, validate_payment_data,
    validate_user_data, validate_settings_data, require_valid_deal,
    require_valid_payment, require_valid_user
)
from .typings import (
    User, Deal, Payment, Settings, Notification, UserID, DealCode, PaymentID, Currency, DealStatus, PaymentStatus,
    NotificationType, LanguageCode, UserRole, NotificationList
)
from .exceptions import (
    DatabaseConnectionError, DatabaseQueryError,
    UserNotFoundError, DealNotFoundError, PaymentNotFoundError,
    DealAmountInvalidError, DealInvalidStatusError, InvalidInputError, ErrorContext
)

# Resource management imports
from .resource_manager import resource_manager, ResourceType, register_database_connection
from .connection_pool_monitor import ConnectionPoolMonitor

# Type variables for generic operations
T = TypeVar('T')
ResultType = TypeVar('ResultType', bound=Union[User, Deal, Payment, Settings])

logger = logging.getLogger(__name__)

def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input by removing potentially dangerous characters."""
    if not text:
        return ""

    # Limit length
    text = str(text)[:max_length]

    # Remove potentially dangerous characters while keeping basic punctuation
    text = re.sub(r'[<>"\'\`]', '', text)

    return text.strip()


class PostgreSQLConnectionPool:
    """Enhanced PostgreSQL connection pool management with monitoring"""
    
    def __init__(self, database_url: str):
        self.database_url: str = database_url
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = threading.Lock()
        self._pool_size: int = DB_POOL_MAX_SIZE
        self._min_size: int = DB_POOL_MIN_SIZE
        
        # Resource management
        self._connection_monitor: Optional[ConnectionPoolMonitor] = None
        self._connection_id: Optional[str] = None
        self._cleanup_handlers: List[Callable] = []
        
        # Statistics
        self._total_connections_acquired = 0
        self._total_connections_released = 0
        self._total_query_time_ms = 0.0
        
    async def get_connection(self) -> asyncpg.Connection:
        """Get connection from pool with resource tracking"""
        if self._pool is None:
            await self._initialize_pool()
        
        # Track connection acquisition
        connection_id = self._track_connection_acquire()
        
        try:
            conn = await self._pool.acquire()
            
            # Register connection with monitor
            if self._connection_monitor:
                self._connection_monitor.track_connection_release(connection_id)
            
            # Register with resource manager
            register_database_connection(conn, self._create_connection_cleanup(conn))
            
            logger.debug(f"Acquired database connection: {connection_id}")
            return conn
            
        except Exception as e:
            logger.error(f"Failed to acquire database connection: {e}")
            self._track_connection_error(connection_id)
            raise
    
    def _track_connection_acquire(self) -> str:
        """Track connection acquisition"""
        self._total_connections_acquired += 1
        
        if self._connection_monitor:
            return self._connection_monitor.track_connection_acquire()
        else:
            return f"db_conn_{self._total_connections_acquired}"
    
    def _track_connection_release(self, connection_id: str, query_time_ms: float = 0.0):
        """Track connection release"""
        self._total_connections_released += 1
        self._total_query_time_ms += query_time_ms
        
        if self._connection_monitor:
            self._connection_monitor.track_connection_release(connection_id, query_time_ms)
    
    def _track_connection_error(self, connection_id: str):
        """Track connection error"""
        if self._connection_monitor:
            # Update connection info with error state
            pass  # This would be implemented in the monitor
    
    def _create_connection_cleanup(self, conn):
        """Create cleanup callback for a connection"""
        async def cleanup_connection():
            try:
                if self._pool and conn:
                    await self._pool.release(conn)
                    logger.debug("Database connection cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up database connection: {e}")
        return cleanup_connection

    async def _initialize_pool(self) -> None:
        """Initialize PostgreSQL connection pool with monitoring"""
        try:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self._min_size,
                max_size=self._pool_size,
                command_timeout=DB_CONNECTION_TIMEOUT,
                server_settings={
                    'application_name': 'black_diamond_trading_platform'
                }
            )
            
            # Initialize connection monitoring
            self._connection_monitor = ConnectionPoolMonitor(
                self._pool,
                pool_name="postgresql_main",
                idle_timeout_seconds=300,  # 5 minutes
                max_idle_connections=10,
                health_check_interval=60,
                leak_detection_threshold=3600  # 1 hour
            )
            
            # Start monitoring
            await self._connection_monitor.start_monitoring()
            
            # Register with resource manager
            self._connection_id = resource_manager.register_resource(
                self,
                ResourceType.DATABASE_CONNECTION,
                self._get_pool_cleanup_callback(),
                metadata={
                    'pool_name': 'postgresql_main',
                    'min_size': self._min_size,
                    'max_size': self._pool_size,
                    'database_url': self.database_url
                }
            )
            
            logger.info(f"PostgreSQL connection pool initialized with {self._min_size}-{self._pool_size} connections and monitoring")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
            raise DatabaseConnectionError(
                connection_info=self.database_url,
                error_message=str(e)
            )
    
    def _get_pool_cleanup_callback(self):
        """Get cleanup callback for the pool"""
        async def cleanup_pool():
            await self.close_pool()
        return cleanup_pool
    
    async def return_connection(self, conn: asyncpg.Connection) -> None:
        """Return connection to pool with cleanup tracking"""
        try:
            if self._pool and conn:
                await self._pool.release(conn)
                self._total_connections_released += 1
                logger.debug("Database connection returned to pool")
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")
    
    async def close_pool(self) -> None:
        """Close all connections in the pool with cleanup"""
        try:
            # Stop monitoring
            if self._connection_monitor:
                await self._connection_monitor.stop_monitoring()
                self._connection_monitor = None
            
            # Close pool
            if self._pool:
                await self._pool.close()
                self._pool = None
            
            # Unregister from resource manager
            if self._connection_id:
                resource_manager.unregister_resource(self._connection_id)
                self._connection_id = None
            
            # Run cleanup handlers
            for handler in self._cleanup_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as e:
                    logger.error(f"Error in cleanup handler: {e}")
            
            self._cleanup_handlers.clear()
            logger.info("PostgreSQL connection pool closed gracefully")
            
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}")
    
    def add_cleanup_handler(self, handler: Callable):
        """Add cleanup handler"""
        self._cleanup_handlers.append(handler)
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        stats = {
            'total_connections_acquired': self._total_connections_acquired,
            'total_connections_released': self._total_connections_released,
            'average_query_time_ms': (
                self._total_query_time_ms / max(self._total_connections_acquired, 1)
            ),
            'pool_size_range': f"{self._min_size}-{self._pool_size}",
            'has_monitoring': self._connection_monitor is not None,
            'resource_registered': self._connection_id is not None
        }
        
        # Add monitor stats if available
        if self._connection_monitor:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                monitor_stats = loop.run_until_complete(
                    self._connection_monitor.get_comprehensive_stats()
                )
                stats['monitor_stats'] = monitor_stats
            except Exception:
                pass  # Don't fail if monitoring stats unavailable
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform connection pool health check"""
        try:
            # Test connection
            async with self.get_connection() as conn:
                result = await conn.fetchval("SELECT 1")
                connection_ok = result == 1
            
            # Get current metrics
            current_metrics = await self._connection_monitor.get_current_metrics() if self._connection_monitor else None
            
            # Get memory usage
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            
            health_status = "healthy"
            if current_metrics:
                if current_metrics.health_status.value in ["critical", "degraded"]:
                    health_status = "unhealthy"
                elif current_metrics.health_status.value == "warning":
                    health_status = "degraded"
            
            return {
                'status': health_status,
                'connection_test': connection_ok,
                'memory_usage_mb': round(memory_mb, 2),
                'pool_stats': self.get_pool_stats(),
                'monitor_metrics': current_metrics.__dict__ if current_metrics else None,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during pool health check: {e}")
            return {
                'status': 'critical',
                'connection_test': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def optimize_pool(self) -> Dict[str, Any]:
        """Optimize connection pool settings"""
        optimization_start = time.time()
        
        try:
            # Get current metrics
            current_metrics = await self._connection_monitor.get_current_metrics() if self._connection_monitor else None
            
            optimization_actions = []
            recommendations = []
            
            if current_metrics:
                # Analyze connection usage patterns
                if current_metrics.active_connections < self._min_size * 0.5:
                    recommendations.append("Consider reducing min_pool_size")
                    optimization_actions.append("reduce_min_size")
                
                if current_metrics.active_connections > self._pool_size * 0.9:
                    recommendations.append("Consider increasing max_pool_size")
                    optimization_actions.append("increase_max_size")
                
                if current_metrics.idle_connections > 20:
                    recommendations.append("High idle connections - consider reducing pool size")
                    optimization_actions.append("reduce_overall_size")
            
            # Memory optimization
            import gc
            collected = gc.collect()
            
            optimization_result = {
                'duration_seconds': time.time() - optimization_start,
                'recommendations': recommendations,
                'optimization_actions': optimization_actions,
                'memory_optimized': True,
                'objects_collected': collected,
                'applied_optimizations': []
            }
            
            logger.info(f"Pool optimization completed: {optimization_result}")
            return optimization_result
            
        except Exception as e:
            logger.error(f"Error during pool optimization: {e}")
            return {
                'duration_seconds': time.time() - optimization_start,
                'error': str(e),
                'recommendations': ["Review pool configuration", "Check database performance"]
            }

# === SQL TEMPLATES TO ELIMINATE DUPLICATION ===

class PostgreSQLTemplates:
    """Centralized PostgreSQL query templates to eliminate duplication"""
    
    # User queries (PostgreSQL uses $1, $2 instead of ?)
    USER_SELECT = "SELECT * FROM users WHERE user_id = $1"
    USER_INSERT = "INSERT OR IGNORE INTO users (user_id, username, first_name, registered_date, language) VALUES ($1, $2, $3, $4, $5)"
    USER_UPDATE_LANGUAGE = "UPDATE users SET language = $1 WHERE user_id = $2"
    USER_UPDATE_AVATAR = "UPDATE users SET avatar_url = $1 WHERE user_id = $2"
    USER_UPDATE_BALANCE = "UPDATE users SET balance = COALESCE(balance, 0) + $1 WHERE user_id = $2"
    
    # Deal queries
    DEAL_SELECT = "SELECT * FROM deals WHERE deal_code = $1"
    DEAL_INSERT = "INSERT INTO deals (deal_code, buyer_id, amount, currency, description, product_link, image_link, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)"
    DEAL_JOIN_UPDATE = "UPDATE deals SET seller_id = $1, seller_joined_at = $2, updated_at = $3 WHERE deal_code = $4 AND seller_id IS NULL AND status = 'active'"
    DEAL_STATUS_UPDATE = "UPDATE deals SET {fields} WHERE deal_code = $last"
    
    # Payment queries
    PAYMENT_SELECT = "SELECT * FROM payments WHERE checkout_id = $1 ORDER BY created_at DESC LIMIT 1"
    PAYMENT_INSERT = "INSERT INTO payments (payment_id, checkout_id, tx_hash, amount, currency, created_at) VALUES ($1, $2, $3, $4, $5, $6)"
    PAYMENT_UPDATE_CONFIRMATIONS = "UPDATE payments SET confirmations = $1, {status_field} WHERE payment_id = $2"
    
    # Settings queries
    SETTINGS_SELECT = "SELECT * FROM settings WHERE id = 1"
    SETTINGS_UPDATE = "UPDATE settings SET {fields} WHERE id = 1"
    
    # Notification queries
    NOTIFICATION_SELECT = "SELECT id, user_id, type, title, message, action_url, read, created_at FROM notifications WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2"
    NOTIFICATION_INSERT = "INSERT INTO notifications (user_id, type, title, message, action_url, created_at) VALUES ($1, $2, $3, $4, $5, $6)"
    NOTIFICATION_MARK_READ = "UPDATE notifications SET read = 1 WHERE id = $1 AND user_id = $2"
    NOTIFICATION_MARK_ALL_READ = "UPDATE notifications SET read = 1 WHERE user_id = $1 AND read = 0"
    
    # Rate limiting queries
    RATE_LIMIT_SELECT = "SELECT count FROM rate_limits WHERE key = $1 AND window_start = $2 AND window_seconds = $3"
    RATE_LIMIT_UPDATE = "UPDATE rate_limits SET count = $1, updated_at = $2 WHERE key = $3 AND window_start = $4 AND window_seconds = $5"
    RATE_LIMIT_INSERT = "INSERT INTO rate_limits (key, count, window_start, window_seconds, created_at, updated_at) VALUES ($1, 1, $2, $3, $4, $5)"


class PostgreSQLDatabase:
    """PostgreSQL database class with comprehensive typing and production-ready features"""
    
    def __init__(self, database_url: str):
        self.database_url: str = database_url.replace('sqlite:///', '')  # Remove sqlite prefix if present
        self._connection_pool = PostgreSQLConnectionPool(self.database_url)
        
        # Initialize database with proper event loop handling
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop exists, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Initialize database only if asyncpg is available
        if ASYNCPG_AVAILABLE:
            try:
                loop.run_until_complete(self._init_db())
                loop.run_until_complete(self.cleanup_expired_tokens())
                loop.run_until_complete(self.cleanup_rate_limits())
                logger.info("🚀 PostgreSQL Database initialized with production optimizations")
            except Exception as e:
                logger.warning(f"PostgreSQL initialization failed, using mock mode: {e}")
                # Continue with mock database
        else:
            logger.info("🔧 Running in mock mode - PostgreSQL not available")

    async def _get_connection(self) -> asyncpg.Connection:
        """Get PostgreSQL database connection"""
        return await self._connection_pool.get_connection()

    async def _return_connection(self, conn: asyncpg.Connection) -> None:
        """Return PostgreSQL database connection to pool"""
        await self._connection_pool.return_connection(conn)

    async def _init_db(self):
        """Database initialization with centralized constants"""
        conn = await self._get_connection()
        try:
            # Create all tables using centralized constants
            await self._create_tables(conn)
            
            # Insert default settings
            await self._insert_default_settings(conn)
            
            # Default achievements feature removed — no insertion performed
            
            await conn.execute("COMMIT")
            logger.info("PostgreSQL database initialized with refactored structure")
        except Exception as e:
            await conn.execute("ROLLBACK")
            logger.error(f"Error initializing PostgreSQL database: {e}")
            raise
        finally:
            await self._return_connection(conn)

    async def _create_tables(self, conn: asyncpg.Connection):
        """Create PostgreSQL database tables"""
        
        # Base table schema definitions (PostgreSQL syntax)
        tables = {
            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    registered_date TIMESTAMPTZ,
                    language TEXT DEFAULT 'en',
                    avatar_url TEXT,
                    deals_count INTEGER DEFAULT 0,
                    total_deal_amount DECIMAL(15,2) DEFAULT 0,
                    is_banned BOOLEAN DEFAULT FALSE,
                    balance DECIMAL(15,2) DEFAULT 0.0
                )
            ''',
            'deals': '''
                CREATE TABLE IF NOT EXISTS deals (
                    deal_code TEXT PRIMARY KEY,
                    buyer_id BIGINT,
                    seller_id BIGINT,
                    amount DECIMAL(15,2),
                    currency TEXT,
                    status TEXT DEFAULT 'active',
                    description TEXT,
                    product_link TEXT,
                    image_link TEXT,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    seller_joined_at TIMESTAMPTZ,
                    payment_confirmed_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    cancelled_at TIMESTAMPTZ,
                    cancel_reason TEXT,
                    commission_amount DECIMAL(15,2) DEFAULT 0,
                    seller_amount DECIMAL(15,2) DEFAULT 0,
                    payout_method TEXT,
                    is_automatic BOOLEAN DEFAULT FALSE,
                    CONSTRAINT fk_deals_buyer FOREIGN KEY (buyer_id) REFERENCES users (user_id),
                    CONSTRAINT fk_deals_seller FOREIGN KEY (seller_id) REFERENCES users (user_id)
                )
            ''',
            'settings': f'''
                CREATE TABLE IF NOT EXISTS settings (
                    id SERIAL PRIMARY KEY,
                    commission_rate DECIMAL(5,4) DEFAULT {DEFAULT_COMMISSION_RATE},
                    min_deal_amount DECIMAL(15,2) DEFAULT {MIN_DEAL_AMOUNT},
                    max_deal_amount DECIMAL(15,2) DEFAULT {MAX_DEAL_AMOUNT},
                    auto_confirm_timeout INTEGER DEFAULT {AUTO_CONFIRM_TIMEOUT},
                    currency_update_interval INTEGER DEFAULT {CURRENCY_UPDATE_INTERVAL}
                )
            '''
        }
        
        # Execute table creation
        for table_sql in tables.values():
            await conn.execute(table_sql)

        # Create other tables with PostgreSQL-specific features
            other_tables = [
            '''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                checkout_id TEXT,
                tx_hash TEXT,
                amount DECIMAL(15,2),
                currency TEXT,
                status TEXT DEFAULT 'pending',
                confirmations INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ,
                confirmed_at TIMESTAMPTZ,
                CONSTRAINT fk_payments_checkout FOREIGN KEY (checkout_id) REFERENCES crypto_checkouts (checkout_id)
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS rate_limits (
                id BIGSERIAL PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                count INTEGER DEFAULT 0,
                window_start BIGINT,
                window_seconds INTEGER,
                created_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS notifications (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                type TEXT,
                title TEXT,
                message TEXT,
                action_url TEXT,
                read BOOLEAN DEFAULT FALSE,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ,
                CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''',
            '''
            # Achievement table removed
            '''
        ]
        
        for table_sql in other_tables:
            await conn.execute(table_sql)

    async def _insert_default_settings(self, conn: asyncpg.Connection):
        """Insert default settings using constants"""
        from shared.config import COMMISSION_RATE
        await conn.execute('INSERT OR IGNORE INTO settings (id, commission_rate) VALUES (1, ?)', (COMMISSION_RATE,))

    # Default achievements insertion removed — achievements feature disabled

    # === USER METHODS (Consolidated) ===

    @require_valid_user
    async def create_user(self, user_data: Dict[str, Any], context: Optional[ErrorContext] = None) -> bool:
        """Create user with centralized validation and proper error handling"""
        try:
            # Validate user data
            validation_result = validate_user_data(user_data)
            if not validation_result[0]:
                raise InvalidInputError(
                    field="user_data",
                    value=user_data,
                    reason="User validation failed",
                    context=context
                )

            conn = await self._get_connection()
            try:
                await conn.execute(PostgreSQLTemplates.USER_INSERT, (
                    user_data['user_id'],
                    sanitize_input(user_data.get('username', '')),
                    sanitize_input(user_data.get('first_name', '')),
                    datetime.now(),
                    user_data.get('language', 'en')
                ))
                await conn.execute("COMMIT")
                return True
            except Exception as e:
                await conn.execute("ROLLBACK")
                raise DatabaseQueryError(
                    query="INSERT user",
                    error_message=str(e),
                    context=context,
                    cause=e
                )
            finally:
                await self._return_connection(conn)

        except Exception as e:
            logger.error(f"Error creating user {user_data.get('user_id', 'unknown')}: {e}")
            return False

    async def get_user(self, user_id: UserID, context: Optional[ErrorContext] = None) -> Optional[User]:
        """Get user with improved validation and typing"""
        try:
            # Validate user_id using centralized function
            validation_result = validate_user_id(user_id)
            if not validation_result[0]:
                logger.warning(f"Invalid user_id: {user_id}")
                return None

            conn = await self._get_connection()
            try:
                row = await conn.fetchrow(PostgreSQLTemplates.USER_SELECT, user_id)
                
                if not row:
                    raise UserNotFoundError(user_id=user_id, context=context)
                
                return User(
                    user_id=row['user_id'],
                    username=row.get('username'),
                    first_name=row.get('first_name'),
                    language=LanguageCode(row.get('language', 'en')),
                    avatar_url=row.get('avatar_url'),
                    registered_date=row['registered_date'],
                    deals_count=row.get('deals_count', 0),
                    total_deal_amount=Decimal(str(row.get('total_deal_amount', 0))),
                    # achievements_count removed from user mapping
                    is_banned=bool(row.get('is_banned', False)),
                    balance=Decimal(str(row.get('balance', 0))),
                    role=UserRole.USER  # Default for now
                )
            finally:
                await self._return_connection(conn)
                
        except UserNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def set_user_language(self, user_id: UserID, language: LanguageCode, context: Optional[ErrorContext] = None) -> bool:
        """Set user language with validation and proper typing"""
        try:
            # Validate user_id
            validation_result = validate_user_id(user_id)
            if not validation_result[0]:
                raise InvalidInputError(
                    field="user_id",
                    value=user_id,
                    reason="Invalid user ID",
                    context=context
                )

            if language not in [LanguageCode.ENGLISH, LanguageCode.UKRAINIAN, LanguageCode.CHINESE]:
                raise InvalidInputError(
                    field="language",
                    value=language,
                    reason="Unsupported language",
                    context=context
                )

            conn = await self._get_connection()
            try:
                result = await conn.execute(PostgreSQLTemplates.USER_UPDATE_LANGUAGE, language.value, user_id)
                
                if "UPDATE 0" in result:
                    raise UserNotFoundError(user_id=user_id, context=context)
                
                return True
            finally:
                await self._return_connection(conn)
                
        except (InvalidInputError, UserNotFoundError):
            return False
        except Exception as e:
            logger.error(f"Error setting language for {user_id}: {e}")
            return False

    async def get_user_balance(self, user_id: UserID, context: Optional[ErrorContext] = None) -> Decimal:
        """Get user balance with proper error handling"""
        try:
            user = await self.get_user(user_id, context)
            if not user:
                raise UserNotFoundError(user_id=user_id, context=context)
            
            return user.balance
            
        except UserNotFoundError:
            return Decimal("0.00")
        except Exception as e:
            logger.error(f"Error getting balance for user {user_id}: {e}")
            return Decimal("0.00")

    # === DEAL METHODS (Consolidated) ===

    @require_valid_deal
    async def create_deal(self, deal_data: Dict[str, Any], context: Optional[ErrorContext] = None) -> bool:
        """Create deal with centralized validation and comprehensive typing"""
        try:
            # Validate deal data
            validation_result = validate_deal_data(deal_data)
            if not validation_result[0]:
                raise InvalidInputError(
                    field="deal_data",
                    value=deal_data,
                    reason="Deal validation failed",
                    context=context
                )

            # Additional validation specific to deal creation
            amount_validation = validate_amount_in_range(
                deal_data['amount'],
                MIN_DEAL_AMOUNT,
                MAX_DEAL_AMOUNT
            )
            if not amount_validation[0]:
                raise DealAmountInvalidError(
                    deal_code=deal_data['deal_code'],
                    amount=deal_data['amount'],
                    min_amount=MIN_DEAL_AMOUNT,
                    max_amount=MAX_DEAL_AMOUNT,
                    context=context
                )

            if deal_data['currency'] not in SUPPORTED_CURRENCIES:
                raise InvalidInputError(
                    field="currency",
                    value=deal_data['currency'],
                    reason=f"Unsupported currency: {deal_data['currency']}",
                    context=context
                )

            conn = await self._get_connection()
            try:
                await conn.execute(PostgreSQLTemplates.DEAL_INSERT, (
                    sanitize_input(deal_data['deal_code']),
                    deal_data['buyer_id'],
                    Decimal(str(deal_data['amount'])),
                    deal_data['currency'],
                    sanitize_input(deal_data.get('description', '')),
                    sanitize_input(deal_data.get('product_link', '')),
                    sanitize_input(deal_data.get('image_link', '')),
                    datetime.now(),
                    datetime.now()
                ))
                await conn.execute("COMMIT")
                return True
            except asyncpg.UniqueViolationError as e:
                logger.warning(f"Deal {deal_data.get('deal_code', '')} already exists: {e}")
                return False
            except Exception as e:
                await conn.execute("ROLLBACK")
                raise DatabaseQueryError(
                    query="INSERT deal",
                    error_message=str(e),
                    context=context,
                    cause=e
                )
            finally:
                await self._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error creating deal {deal_data.get('deal_code', 'unknown')}: {e}")
            return False

    async def get_deal(self, deal_code: DealCode, context: Optional[ErrorContext] = None) -> Optional[Deal]:
        """Get deal with centralized validation and proper typing"""
        try:
            if not validate_deal_code(deal_code):
                logger.warning(f"Invalid deal code: {deal_code}")
                return None

            conn = await self._get_connection()
            try:
                row = await conn.fetchrow(PostgreSQLTemplates.DEAL_SELECT, deal_code)
                
                if not row:
                    raise DealNotFoundError(deal_code=deal_code, context=context)
                
                return Deal(
                    deal_code=row['deal_code'],
                    buyer_id=row['buyer_id'],
                    seller_id=row.get('seller_id'),
                    amount=Decimal(str(row.get('amount', 0))),
                    currency=Currency(row.get('currency', 'USDT')),
                    status=DealStatus(row.get('status', 'active')),
                    description=row.get('description'),
                    product_link=row.get('product_link'),
                    image_link=row.get('image_link'),
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    seller_joined_at=row.get('seller_joined_at'),
                    payment_confirmed_at=row.get('payment_confirmed_at'),
                    completed_at=row.get('completed_at'),
                    cancelled_at=row.get('cancelled_at'),
                    cancel_reason=row.get('cancel_reason'),
                    commission_amount=Decimal(str(row.get('commission_amount', 0))),
                    seller_amount=Decimal(str(row.get('seller_amount', 0))),
                    payout_method=row.get('payout_method'),
                    is_automatic=row.get('is_automatic', False)
                )
            finally:
                await self._return_connection(conn)
                
        except DealNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting deal {deal_code}: {e}")
            return None

    async def update_deal_status(
        self,
        deal_code: DealCode,
        status: DealStatus,
        context: Optional[ErrorContext] = None,
        **kwargs: Any
    ) -> bool:
        """Update deal status with centralized validation and field whitelisting"""
        try:
            # Validate deal code
            if not validate_deal_code(deal_code):
                raise InvalidInputError(
                    field="deal_code",
                    value=deal_code,
                    reason="Invalid deal code format",
                    context=context
                )

            # Validate status using enum
            allowed_statuses = [
                DealStatus.PENDING, DealStatus.ACTIVE, DealStatus.FUNDED,
                DealStatus.COMPLETED, DealStatus.CANCELLED, DealStatus.EXPIRED
            ]
            
            if status not in allowed_statuses:
                raise DealInvalidStatusError(
                    deal_code=deal_code,
                    current_status=status.value,
                    expected_statuses=[s.value for s in allowed_statuses],
                    context=context
                )

            # Use centralized field validation
            allowed_fields = {
                'payment_confirmed_at': 'payment_confirmed_at',
                'completed_at': 'completed_at',
                'cancelled_at': 'cancelled_at',
                'cancel_reason': 'cancel_reason',
                'commission_amount': 'commission_amount',
                'seller_amount': 'seller_amount',
                'payout_method': 'payout_method'
            }
            
            update_fields = ['status = $1', 'updated_at = $2']
            values = [status.value, datetime.now()]

            # Only allow whitelisted fields
            param_counter = 3
            for field, db_field in allowed_fields.items():
                if field in kwargs:
                    if isinstance(kwargs[field], Decimal):
                        values.append(str(kwargs[field]))
                    else:
                        values.append(kwargs[field])
                    update_fields.append(f'{db_field} = ${param_counter}')
                    param_counter += 1

            # Build and execute query
            query = PostgreSQLTemplates.DEAL_STATUS_UPDATE.format(fields=', '.join(update_fields))
            if param_counter > 3:
                query = query.replace('$last', f'${param_counter}')
            else:
                query = query.replace('$last', '$3')
            values.append(deal_code)

            conn = await self._get_connection()
            try:
                result = await conn.execute(query, *values)
                
                if "UPDATE 0" in result:
                    raise DealNotFoundError(deal_code=deal_code, context=context)
                
                return True
            finally:
                await self._return_connection(conn)
                
        except (InvalidInputError, DealInvalidStatusError, DealNotFoundError):
            return False
        except Exception as e:
            logger.error(f"Error updating deal status {deal_code}: {e}")
            return False

    # === PAYMENT METHODS (Consolidated) ===

    @require_valid_payment
    async def create_payment(self, payment_data: Dict[str, Any], context: Optional[ErrorContext] = None) -> bool:
        """Create payment with centralized validation and comprehensive typing"""
        try:
            # Validate payment data
            validation_result = validate_payment_data(payment_data)
            if not validation_result[0]:
                raise InvalidInputError(
                    field="payment_data",
                    value=payment_data,
                    reason="Payment validation failed",
                    context=context
                )

            conn = await self._get_connection()
            try:
                await conn.execute(PostgreSQLTemplates.PAYMENT_INSERT, (
                    sanitize_input(payment_data['payment_id']),
                    sanitize_input(payment_data['checkout_id']),
                    sanitize_input(payment_data['tx_hash']),
                    Decimal(str(payment_data['amount'])),
                    payment_data['currency'],
                    datetime.now()
                ))
                await conn.execute("COMMIT")
                return True
            except asyncpg.UniqueViolationError as e:
                logger.warning(f"Payment {payment_data['payment_id']} already exists: {e}")
                return False
            except Exception as e:
                await conn.execute("ROLLBACK")
                raise DatabaseQueryError(
                    query="INSERT payment",
                    error_message=str(e),
                    context=context,
                    cause=e
                )
            finally:
                await self._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error creating payment {payment_data.get('payment_id', 'unknown')}: {e}")
            return False

    async def update_payment_confirmations(self, payment_id: PaymentID, confirmations: int, context: Optional[ErrorContext] = None) -> bool:
        """Update payment confirmations with centralized constants and proper typing"""
        try:
            # Use centralized minimum confirmations
            MIN_CONFIRMATIONS = 1
            
            if confirmations < 0:
                raise InvalidInputError(
                    field="confirmations",
                    value=confirmations,
                    reason="Confirmations cannot be negative",
                    context=context
                )
            
            conn = await self._get_connection()
            try:
                # Use conditional query based on confirmations
                if confirmations >= MIN_CONFIRMATIONS:
                    status_field = "status = $2, confirmed_at = $3"
                    values = [confirmations, 'confirmed', datetime.now(), payment_id]
                else:
                    status_field = ""  # No status update
                    values = [confirmations, payment_id]
                
                query = PostgreSQLTemplates.PAYMENT_UPDATE_CONFIRMATIONS.format(status_field=status_field)
                result = await conn.execute(query, *values)
                
                if "UPDATE 0" in result:
                    raise PaymentNotFoundError(payment_id=payment_id, context=context)
                
                return True
            finally:
                await self._return_connection(conn)
                
        except (InvalidInputError, PaymentNotFoundError):
            return False
        except Exception as e:
            logger.error(f"Error updating confirmations for {payment_id}: {e}")
            return False

    async def get_payment(self, payment_id: PaymentID, context: Optional[ErrorContext] = None) -> Optional[Payment]:
        """Get payment with proper typing"""
        try:
            conn = await self._get_connection()
            try:
                row = await conn.fetchrow("SELECT * FROM payments WHERE payment_id = $1", payment_id)
                
                if not row:
                    raise PaymentNotFoundError(payment_id=payment_id, context=context)
                
                return Payment(
                    payment_id=row['payment_id'],
                    checkout_id=row['checkout_id'],
                    tx_hash=row.get('tx_hash'),
                    amount=Decimal(str(row.get('amount', 0))),
                    currency=Currency(row.get('currency', 'USDT')),
                    status=PaymentStatus(row.get('status', 'pending')),
                    confirmations=row.get('confirmations', 0),
                    created_at=row['created_at'],
                    confirmed_at=row.get('confirmed_at')
                )
            finally:
                await self._return_connection(conn)
                
        except PaymentNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting payment {payment_id}: {e}")
            return None

    # === SETTINGS METHODS (Consolidated) ===

    async def get_settings(self, context: Optional[ErrorContext] = None) -> Settings:
        """Get settings with improved error handling and proper typing"""
        try:
            conn = await self._get_connection()
            try:
                row = await conn.fetchrow(PostgreSQLTemplates.SETTINGS_SELECT)
                
                if not row:
                    # Return default settings if none exist
                    return Settings()
                
                return Settings(
                    id=row['id'],
                    commission_rate=Decimal(str(row.get('commission_rate', DEFAULT_COMMISSION_RATE))),
                    min_deal_amount=Decimal(str(row.get('min_deal_amount', MIN_DEAL_AMOUNT))),
                    max_deal_amount=Decimal(str(row.get('max_deal_amount', MAX_DEAL_AMOUNT))),
                    auto_confirm_timeout=row.get('auto_confirm_timeout', AUTO_CONFIRM_TIMEOUT),
                    currency_update_interval=row.get('currency_update_interval', CURRENCY_UPDATE_INTERVAL)
                )
            finally:
                await self._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return Settings()  # Return defaults on error

    async def update_settings(self, **kwargs: Any) -> bool:
        """Update settings with centralized validation and proper typing"""
        try:
            # Use centralized validation
            result = validate_settings_data(kwargs)
            if not result:
                logger.error(f"Invalid settings data: {result.errors}")
                return False

            # Filter to allowed settings using centralized constants
            allowed_settings = {
                'commission_rate': DEFAULT_COMMISSION_RATE,
                'min_deal_amount': MIN_DEAL_AMOUNT,
                'max_deal_amount': MAX_DEAL_AMOUNT,
                'auto_confirm_timeout': AUTO_CONFIRM_TIMEOUT,
                'currency_update_interval': CURRENCY_UPDATE_INTERVAL
            }
            
            update_fields = []
            values = []
            param_counter = 1
            
            for key, value in kwargs.items():
                if key in allowed_settings:
                    update_fields.append(f"{key} = ${param_counter}")
                    # Convert Decimal values to string for database storage
                    if isinstance(value, Decimal):
                        values.append(str(value))
                    else:
                        values.append(value)
                    param_counter += 1
            
            if not update_fields:
                return False
            
            query = PostgreSQLTemplates.SETTINGS_UPDATE.format(fields=', '.join(update_fields))
            
            conn = await self._get_connection()
            try:
                result = await conn.execute(query, *values)
                return "UPDATE 1" in result or "UPDATE 0" in result
            finally:
                await self._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return False

    # === RATE LIMITING METHODS (Consolidated) ===

    async def check_rate_limit(self, key: str, limit: int = None, window: int = None) -> bool:
        """Check rate limiting with centralized constants"""
        # Use centralized rate limits if not specified
        if limit is None or window is None:
            limit, window = get_rate_limit('default')
        
        current_time = int(time.time())
        window_start = current_time - (current_time % window)

        conn = await self._get_connection()
        try:
            # Get or create rate limiting record
            row = await conn.fetchrow(PostgreSQLTemplates.RATE_LIMIT_SELECT, key, window_start, window)

            if row:
                current_count = row['count'] + 1
                if current_count > limit:
                    return False

                # Update counter
                await conn.execute(PostgreSQLTemplates.RATE_LIMIT_UPDATE, (
                    current_count, datetime.now(), key, window_start, window
                ))
            else:
                # Create new record
                await conn.execute(PostgreSQLTemplates.RATE_LIMIT_INSERT, (
                    key, window_start, window, 
                    datetime.now(), datetime.now()
                ))

            return True

        except Exception as e:
            logger.error(f"Error checking rate limiting for {key}: {e}")
            return True  # Allow request in case of error
        finally:
            await self._return_connection(conn)

    # === NOTIFICATION METHODS (Consolidated) ===

    async def create_notification(
        self,
        user_id: UserID,
        notification_type: NotificationType,
        title: str,
        message: str,
        action_url: Optional[str] = None,
        priority: int = 0,
        context: Optional[ErrorContext] = None
    ) -> bool:
        """Create notification with centralized validation and proper typing"""
        try:
            # Validate user_id
            is_valid, user_id = validate_user_id(user_id)
            if not is_valid:
                logger.error(f"Invalid user_id for notification: {user_id}")
                return False

            if not title or len(title.strip()) == 0:
                raise InvalidInputError(
                    field="title",
                    value=title,
                    reason="Title cannot be empty",
                    context=context
                )

            if not message or len(message.strip()) == 0:
                raise InvalidInputError(
                    field="message",
                    value=message,
                    reason="Message cannot be empty",
                    context=context
                )

            if priority < 0 or priority > 2:
                raise InvalidInputError(
                    field="priority",
                    value=priority,
                    reason="Priority must be 0, 1, or 2",
                    context=context
                )

            conn = await self._get_connection()
            try:
                await conn.execute(PostgreSQLTemplates.NOTIFICATION_INSERT, (
                    user_id,
                    notification_type.value,
                    sanitize_input(title),
                    sanitize_input(message),
                    sanitize_input(action_url) if action_url else None,
                    priority,
                    datetime.now()
                ))
                return True
            finally:
                await self._return_connection(conn)
                
        except InvalidInputError:
            return False
        except Exception as e:
            logger.error(f"Error creating notification for {user_id}: {e}")
            return False

    async def get_user_notifications(self, user_id: UserID, limit: int = 50, context: Optional[ErrorContext] = None) -> NotificationList:
        """Get user notifications with centralized validation and proper typing"""
        try:
            # Validate user_id and limit
            is_valid, user_id = validate_user_id(user_id)
            if not is_valid:
                return []

            if limit <= 0 or limit > 100:
                limit = 50

            conn = await self._get_connection()
            try:
                rows = await conn.fetch(PostgreSQLTemplates.NOTIFICATION_SELECT, user_id, limit)
                
                notifications = []
                for row in rows:
                    notifications.append(Notification(
                        id=row['id'],
                        user_id=row['user_id'],
                        type=NotificationType(row.get('type', 'system')),
                        title=row.get('title', ''),
                        message=row.get('message', ''),
                        action_url=row.get('action_url'),
                        read=bool(row.get('read', False)),
                        priority=row.get('priority', 0),
                        created_at=row['created_at']
                    ))
                
                return notifications
            finally:
                await self._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error getting notifications for {user_id}: {e}")
            return []

    async def get_unread_notifications_count(self, user_id: UserID, context: Optional[ErrorContext] = None) -> int:
        """Get count of unread notifications"""
        try:
            is_valid, user_id = validate_user_id(user_id)
            if not is_valid:
                return 0

            conn = await self._get_connection()
            try:
                result = await conn.fetchval("SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND read = FALSE", user_id)
                return result or 0
            finally:
                await self._return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error getting unread notifications count for {user_id}: {e}")
            return 0

    async def mark_notification_read(self, notification_id: int, user_id: UserID, context: Optional[ErrorContext] = None) -> bool:
        """Mark notification as read with validation"""
        try:
            if notification_id <= 0:
                raise InvalidInputError(
                    field="notification_id",
                    value=notification_id,
                    reason="Notification ID must be positive",
                    context=context
                )

            is_valid, user_id = validate_user_id(user_id)
            if not is_valid:
                raise InvalidInputError(
                    field="user_id",
                    value=user_id,
                    reason="Invalid user ID",
                    context=context
                )

            conn = await self._get_connection()
            try:
                result = await conn.execute(PostgreSQLTemplates.NOTIFICATION_MARK_READ, notification_id, user_id)
                
                if "UPDATE 0" in result:
                    logger.warning(f"Notification {notification_id} not found or not owned by user {user_id}")
                    return False
                
                return True
            finally:
                await self._return_connection(conn)
                
        except InvalidInputError:
            return False
        except Exception as e:
            logger.error(f"Error marking notification {notification_id} as read: {e}")
            return False

    # === CLEANUP METHODS ===

    async def cleanup_expired_tokens(self):
        """Clean up expired tokens using centralized constants"""
        conn = await self._get_connection()
        try:
            expiration_time = datetime.now() - timedelta(seconds=TOKEN_VALIDITY)
            await conn.execute('DELETE FROM auth_tokens WHERE expires_at < $1', expiration_time)
            logger.info(f"Cleaned up expired tokens")
        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {e}")
        finally:
            await self._return_connection(conn)

    async def cleanup_rate_limits(self):
        """Clean up old rate limiting records using centralized constants"""
        current_time = int(time.time())
        CLEANUP_WINDOW_HOURS = 24
        cutoff_time = current_time - (CLEANUP_WINDOW_HOURS * 60 * 60)

        conn = await self._get_connection()
        try:
            await conn.execute('DELETE FROM rate_limits WHERE window_start < $1', cutoff_time)
            logger.info(f"Cleaned up old rate limiting records")
        except Exception as e:
            logger.error(f"Error cleaning up rate limiting: {e}")
        finally:
            await self._return_connection(conn)

    async def close_connection(self):
        """Close all connections in the pool with graceful shutdown"""
        try:
            await self._connection_pool.close_pool()
            logger.info("✅ PostgreSQL database connections closed gracefully")
            
        except Exception as e:
            logger.error(f"❌ Error during database shutdown: {e}")

    async def create_decentralized_payment(self, deal_code: str, escrow_address: str, amount: float,
                                         currency: str, qr_code: str = "", status: str = "pending",
                                         created_at: str = None, expires_at: str = None) -> bool:
        """Create decentralized payment record"""
        try:
            conn = await self._get_connection()
            try:
                await conn.execute('''
                    INSERT INTO decentralized_payments
                    (deal_code, escrow_address, amount, currency, qr_code, status, created_at, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ''', deal_code, escrow_address, amount, currency, qr_code, status,
                     created_at or datetime.now().isoformat(),
                     expires_at or (datetime.now() + timedelta(hours=24)).isoformat())
                return True
            finally:
                await self._return_connection(conn)
        except Exception as e:
            logger.error(f"Error creating decentralized payment: {e}")
            return False

    async def update_decentralized_payment_status(self, deal_code: str, status: str, tx_hash: str = None) -> bool:
        """Update decentralized payment status"""
        try:
            conn = await self._get_connection()
            try:
                if tx_hash:
                    await conn.execute('''
                        UPDATE decentralized_payments
                        SET status = $1, tx_hash = $2, confirmed_at = $3
                        WHERE deal_code = $4
                    ''', status, tx_hash, datetime.now().isoformat(), deal_code)
                else:
                    await conn.execute('''
                        UPDATE decentralized_payments
                        SET status = $1
                        WHERE deal_code = $2
                    ''', status, deal_code)
                return True
            finally:
                await self._return_connection(conn)
        except Exception as e:
            logger.error(f"Error updating decentralized payment status: {e}")
            return False

    async def get_decentralized_payment_by_checkout(self, checkout_id: str) -> Optional[Dict]:
        """Get decentralized payment by checkout ID"""
        try:
            conn = await self._get_connection()
            try:
                row = await conn.fetchrow('''
                    SELECT * FROM decentralized_payments WHERE checkout_id = $1
                ''', checkout_id)
                return dict(row) if row else None
            finally:
                await self._return_connection(conn)
        except Exception as e:
            logger.error(f"Error getting decentralized payment by checkout: {e}")
            return None

    async def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        try:
            conn = await self._get_connection()
            try:
                users_count = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
                deals_count = await conn.fetchval("SELECT COUNT(*) FROM deals") or 0
                payments_count = await conn.fetchval("SELECT COUNT(*) FROM payments") or 0
                settings_count = await conn.fetchval("SELECT COUNT(*) FROM settings") or 0

                return {
                    'users_count': users_count,
                    'deals_count': deals_count,
                    'payments_count': payments_count,
                    'settings_count': settings_count
                }
            finally:
                await self._return_connection(conn)
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {
                'users_count': 0,
                'deals_count': 0,
                'payments_count': 0,
                'settings_count': 0
            }

# === LEGACY SYNCHRONOUS WRAPPER FOR BACKWARD COMPATIBILITY ===
class Database:
    """
    Legacy synchronous wrapper for backward compatibility.
    This allows existing synchronous code to work with the new PostgreSQL async implementation.
    """
    
    def __init__(self, database_url: str):
        import asyncio
        
        # Initialize the async database
        self._async_db = PostgreSQLDatabase(database_url)
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        logger.info("🚀 Database initialized with PostgreSQL and async/sync compatibility")

    def _run_async(self, coro):
        """Helper to run async code in sync context"""
        return self._loop.run_until_complete(coro)

    # === USER METHODS ===

    @require_valid_user
    def create_user(self, user_data: Dict[str, Any], context: Optional[ErrorContext] = None) -> bool:
        """Create user with centralized validation and proper error handling"""
        return self._run_async(self._async_db.create_user(user_data, context))

    def get_user(self, user_id: UserID, context: Optional[ErrorContext] = None) -> Optional[User]:
        """Get user with improved validation and typing"""
        return self._run_async(self._async_db.get_user(user_id, context))

    def set_user_language(self, user_id: UserID, language: LanguageCode, context: Optional[ErrorContext] = None) -> bool:
        """Set user language with validation and proper typing"""
        return self._run_async(self._async_db.set_user_language(user_id, language, context))

    def get_user_balance(self, user_id: UserID, context: Optional[ErrorContext] = None) -> Decimal:
        """Get user balance with proper error handling"""
        return self._run_async(self._async_db.get_user_balance(user_id, context))

    # === DEAL METHODS ===

    @require_valid_deal
    def create_deal(self, deal_data: Dict[str, Any], context: Optional[ErrorContext] = None) -> bool:
        """Create deal with centralized validation and comprehensive typing"""
        return self._run_async(self._async_db.create_deal(deal_data, context))

    def get_deal(self, deal_code: DealCode, context: Optional[ErrorContext] = None) -> Optional[Deal]:
        """Get deal with centralized validation and proper typing"""
        return self._run_async(self._async_db.get_deal(deal_code, context))

    def update_deal_status(self, deal_code: DealCode, status: DealStatus, context: Optional[ErrorContext] = None, **kwargs: Any) -> bool:
        """Update deal status with centralized validation and field whitelisting"""
        return self._run_async(self._async_db.update_deal_status(deal_code, status, context, **kwargs))

    # === PAYMENT METHODS ===

    @require_valid_payment
    def create_payment(self, payment_data: Dict[str, Any], context: Optional[ErrorContext] = None) -> bool:
        """Create payment with centralized validation and comprehensive typing"""
        return self._run_async(self._async_db.create_payment(payment_data, context))

    def update_payment_confirmations(self, payment_id: PaymentID, confirmations: int, context: Optional[ErrorContext] = None) -> bool:
        """Update payment confirmations with centralized constants and proper typing"""
        return self._run_async(self._async_db.update_payment_confirmations(payment_id, confirmations, context))

    def get_payment(self, payment_id: PaymentID, context: Optional[ErrorContext] = None) -> Optional[Payment]:
        """Get payment with proper typing"""
        return self._run_async(self._async_db.get_payment(payment_id, context))

    # === SETTINGS METHODS ===

    def get_settings(self, context: Optional[ErrorContext] = None) -> Settings:
        """Get settings with improved error handling and proper typing"""
        return self._run_async(self._async_db.get_settings(context))

    def update_settings(self, **kwargs: Any) -> bool:
        """Update settings with centralized validation and proper typing"""
        return self._run_async(self._async_db.update_settings(**kwargs))

    # === RATE LIMITING METHODS ===

    def check_rate_limit(self, key: str, limit: int = None, window: int = None) -> bool:
        """Check rate limiting with centralized constants"""
        return self._run_async(self._async_db.check_rate_limit(key, limit, window))

    # === NOTIFICATION METHODS ===

    def create_notification(self, user_id: UserID, notification_type: NotificationType, title: str, message: str, action_url: Optional[str] = None, priority: int = 0, context: Optional[ErrorContext] = None) -> bool:
        """Create notification with centralized validation and proper typing"""
        return self._run_async(self._async_db.create_notification(user_id, notification_type, title, message, action_url, priority, context))

    def get_user_notifications(self, user_id: UserID, limit: int = 50, context: Optional[ErrorContext] = None) -> NotificationList:
        """Get user notifications with centralized validation and proper typing"""
        return self._run_async(self._async_db.get_user_notifications(user_id, limit, context))

    def get_unread_notifications_count(self, user_id: UserID, context: Optional[ErrorContext] = None) -> int:
        """Get count of unread notifications"""
        return self._run_async(self._async_db.get_unread_notifications_count(user_id, context))

    def mark_notification_read(self, notification_id: int, user_id: UserID, context: Optional[ErrorContext] = None) -> bool:
        """Mark notification as read with validation"""
        return self._run_async(self._async_db.mark_notification_read(notification_id, user_id, context))

    # === CLEANUP METHODS ===

    def cleanup_expired_tokens(self):
        """Clean up expired tokens using centralized constants"""
        return self._run_async(self._async_db.cleanup_expired_tokens())

    def cleanup_rate_limits(self):
        """Clean up old rate limiting records using centralized constants"""
        return self._run_async(self._async_db.cleanup_rate_limits())

    def close_connection(self):
        """Close all connections in the pool with graceful shutdown"""
        return self._run_async(self._async_db.close_connection())

    def create_decentralized_payment(self, deal_code: str, escrow_address: str, amount: float,
                                     currency: str, qr_code: str = "", status: str = "pending",
                                     created_at: str = None, expires_at: str = None) -> bool:
        """Create decentralized payment record"""
        return self._run_async(self._async_db.create_decentralized_payment(
            deal_code, escrow_address, amount, currency, qr_code, status, created_at, expires_at
        ))

    def update_decentralized_payment_status(self, deal_code: str, status: str, tx_hash: str = None) -> bool:
        """Update decentralized payment status"""
        return self._run_async(self._async_db.update_decentralized_payment_status(deal_code, status, tx_hash))

    def get_decentralized_payment_by_checkout(self, checkout_id: str) -> Optional[Dict]:
        """Get decentralized payment by checkout ID"""
        return self._run_async(self._async_db.get_decentralized_payment_by_checkout(checkout_id))

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        return self._run_async(self._async_db.get_stats())


# Global database instance (prefer explicit DATABASE_URL; safe default avoids embedding credentials)
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///black_diamond.db')

# Initialize global database instance for backward compatibility
db = Database(DATABASE_URL)

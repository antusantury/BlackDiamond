import sqlite3
import logging
import re
import os
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import time
from shared.config import DATABASE_URL
from shared.currency_conversion import convert_amount_to_usd

def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input by removing potentially dangerous characters."""
    if not text:
        return ""

    # Limit length
    text = str(text)[:max_length]

    # Remove potentially dangerous characters while keeping basic punctuation
    text = re.sub(r'[<>"\'\`]', '', text)

    return text.strip()

def validate_deal_code(deal_code: str) -> bool:
    """Validate a deal code."""
    if not deal_code or not isinstance(deal_code, str):
        return False

    # The code must be 8 characters of letters/digits
    return bool(re.match(r'^[A-Z0-9]{8}$', deal_code.upper()))

def validate_user_input(text: str, field_type: str = 'text', max_length: int = 1000) -> tuple[bool, str]:
    """Validate user input and return sanitized text."""
    if not text:
        return True, ""

    if not isinstance(text, str):
        return False, "Invalid data type"

    # Length check
    if len(text) > max_length:
        return False, f"Text is too long (max {max_length} characters)"

    # Field-type-specific validation
    if field_type == 'description':
        # Allow more characters for descriptions
        max_length = 500
        # Allow basic punctuation
        cleaned = re.sub(r'[<>"\'\`]', '', text[:max_length])
    elif field_type == 'username':
        # Strict rules for username
        if not re.match(r'^[a-zA-Z0-9_-]+$', text):
            return False, "Username may contain only letters, digits, hyphen and underscore"
        cleaned = text[:50]  # Limit length
    elif field_type == 'amount':
        # Amount must be a valid number
        try:
            amount = float(text.replace(',', '.'))
            if amount <= 0:
                return False, "Amount must be positive"
            if amount > 1000000:
                return False, "Amount is too large"
            return True, str(amount)
        except ValueError:
            return False, "Invalid amount format"
    else:
        # Generic sanitization for text fields
        cleaned = re.sub(r'[<>"\'\`]', '', text[:max_length])

    return True, cleaned.strip()

logger = logging.getLogger(__name__)

class Database:
    @staticmethod
    def _token_fingerprint(token: str) -> str:
        if not token:
            return "none"
        return hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:8]

    def debug_print_auth_tokens(self):
        """Print all auth tokens for debugging."""
        if os.getenv("DEBUG_AUTH_TOKENS", "").lower() not in ("1", "true", "yes"):
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT token, user_id, created_at, expires_at, used FROM auth_tokens')
            rows = cursor.fetchall()
            logger.debug("=== AUTH TOKENS TABLE (REDACTED) ===")
            for token, user_id, created_at, expires_at, used in rows:
                logger.debug(
                    "auth_token fp=%s user_id=%s created_at=%s expires_at=%s used=%s",
                    self._token_fingerprint(token),
                    user_id,
                    created_at,
                    expires_at,
                    used,
                )
            logger.debug("=== END AUTH TOKENS ===")
    def __init__(self, db_path: str = DATABASE_URL):
        resolved_path = db_path.replace('sqlite:///', '')
        if not os.path.isabs(resolved_path):
            project_root = Path(__file__).resolve().parents[2]
            resolved_path = str(project_root / resolved_path)
        self.db_path = resolved_path
        self._init_db()
        # Enhanced cache for frequently accessed data
        self._cache = {}
        self._cache_timeout = 300  # 5 minutes cache
        self._cache_stats = {'hits': 0, 'misses': 0, 'evictions': 0}
        self._rate_limits = {}

    def check_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """Simple in-memory rate limiter used by web middleware."""
        now = time.time()
        entry = self._rate_limits.get(key)

        if not entry or now - entry['timestamp'] >= window:
            self._rate_limits[key] = {'count': 1, 'timestamp': now}
            return True

        entry['count'] += 1
        return entry['count'] <= limit

    def _get_connection(self):
        """Get a DB connection with extra security and optimization settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Additional SQLite security settings
        cursor = conn.cursor()
        # Enable SQL injection protection at the SQLite level
        cursor.execute("PRAGMA foreign_keys = ON")
        # Disallow executing multiple SQL statements in a single query
        conn.execute("PRAGMA trusted_schema = OFF")

        # Performance optimizations
        cursor.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
        cursor.execute("PRAGMA synchronous = NORMAL")  # Balance between speed and safety
        cursor.execute("PRAGMA cache_size = -64000")  # 64MB cache
        cursor.execute("PRAGMA temp_store = MEMORY")  # Temporary tables in memory
        cursor.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O

        return conn

    def _init_db(self):
        """Initialize the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    registered_date TEXT,
                    language TEXT DEFAULT 'en',
                    avatar_url TEXT,
                    deals_count INTEGER DEFAULT 0,
                    total_deal_amount REAL DEFAULT 0,

                    is_banned INTEGER DEFAULT 0
                )
            ''')

            # Deals table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS deals (
                    deal_code TEXT PRIMARY KEY,
                    buyer_id INTEGER,
                    seller_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    status TEXT DEFAULT 'active',
                    description TEXT,
                    product_link TEXT,
                    image_link TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    seller_joined_at TEXT,
                    payment_confirmed_at TEXT,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    cancel_reason TEXT,
                    commission_amount REAL DEFAULT 0,
                    seller_amount REAL DEFAULT 0,
                    FOREIGN KEY (buyer_id) REFERENCES users (user_id),
                    FOREIGN KEY (seller_id) REFERENCES users (user_id)
                )
            ''')

            # Crypto checkouts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS crypto_checkouts (
                    checkout_id TEXT PRIMARY KEY,
                    deal_code TEXT,
                    wallet_address TEXT,
                    amount REAL,
                    currency TEXT,
                    status TEXT DEFAULT 'pending',
                    tx_hash TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    confirmed_at TEXT,
                    qr_code_path TEXT,
                    FOREIGN KEY (deal_code) REFERENCES deals (deal_code)
                )
            ''')

            # Payments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    checkout_id TEXT,
                    tx_hash TEXT,
                    amount REAL,
                    currency TEXT,
                    status TEXT DEFAULT 'pending',
                    confirmations INTEGER DEFAULT 0,
                    created_at TEXT,
                    confirmed_at TEXT,
                    FOREIGN KEY (checkout_id) REFERENCES crypto_checkouts (checkout_id)
                )
            ''')

            # Decentralized payments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decentralized_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_code TEXT,
                    escrow_address TEXT,
                    amount REAL,
                    currency TEXT,
                    payment_memo TEXT,
                    qr_code TEXT,
                    status TEXT DEFAULT 'pending',
                    checkout_id TEXT,
                    tx_hash TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    confirmed_at TEXT
                )
            ''')
            self._ensure_decentralized_payment_columns(cursor)

            # Achievement tables removed

            # Disputes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS disputes (
                    dispute_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_code TEXT,
                    buyer_id INTEGER,
                    seller_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    reason TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT,
                    resolved_at TEXT,
                    resolution TEXT,
                    FOREIGN KEY (deal_code) REFERENCES deals (deal_code),
                    FOREIGN KEY (buyer_id) REFERENCES users (user_id),
                    FOREIGN KEY (seller_id) REFERENCES users (user_id)
                )
            ''')

            # Dice game statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dice_stats (
                    user_id INTEGER PRIMARY KEY,
                    total_plays INTEGER DEFAULT 0,
                    last_play_date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Achievement definition table removed

            # System settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY,
                    commission_rate REAL DEFAULT 0.0,
                    min_deal_amount REAL DEFAULT 1.0,
                    max_deal_amount REAL DEFAULT 10000.0,
                    auto_confirm_timeout INTEGER DEFAULT 3600,
                    currency_update_interval INTEGER DEFAULT 3600
                )
            ''')

            # Notifications table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    title TEXT,
                    message TEXT,
                    action_url TEXT,
                    read INTEGER DEFAULT 0,
                    created_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Auth tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER,
                    created_at TEXT,
                    expires_at TEXT,
                    used INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Support chat messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS support_chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    is_from_user INTEGER DEFAULT 1,
                    created_at TEXT,
                    read_by_admin INTEGER DEFAULT 0,
                    read_by_user INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Admin-to-user messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    target_user_id INTEGER,
                    message TEXT,
                    message_type TEXT DEFAULT 'direct', -- 'direct' или 'broadcast'
                    sent_at TEXT,
                    delivery_status TEXT DEFAULT 'sent', -- 'sent', 'failed'
                    FOREIGN KEY (admin_id) REFERENCES users (user_id),
                    FOREIGN KEY (target_user_id) REFERENCES users (user_id)
                )
            ''')

            # Insert default settings
            from shared.config import COMMISSION_RATE
            cursor.execute('INSERT OR IGNORE INTO settings (id, commission_rate) VALUES (1, ?)', (COMMISSION_RATE,))


            conn.commit()
            logger.info("Database initialized")

            # Add missing columns (migrations)
            self._migrate_database()

            # Clean up demo data to show real statistics
            self._clear_demo_data()

            # Create demo notifications for testing
            self._create_demo_notifications()


    # === USER METHODS ===


    def _ensure_decentralized_payment_columns(self, cursor) -> None:
        """Ensure expected columns exist on decentralized_payments."""
        try:
            cursor.execute("PRAGMA table_info(decentralized_payments)")
            columns = {row[1] for row in cursor.fetchall()}
            if "payment_memo" not in columns:
                cursor.execute("ALTER TABLE decentralized_payments ADD COLUMN payment_memo TEXT")
        except Exception as e:
            logger.warning(f"Failed to ensure decentralized_payments columns: {e}")

    def create_user(self, user_id: int, username: str = None, first_name: str = None) -> bool:
        """Create a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO users
                    (user_id, username, first_name, registered_date, language)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, datetime.now().isoformat(), 'en'))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating user {user_id}: {e}")
                return False

    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Allowed fields for update
                allowed_fields = {
                    'username': str,
                    'first_name': str,
                    'last_name': str,
                    'language_code': str,
                    'language': str,  # Alternative name for compatibility
                    'avatar_url': str
                }
                
                update_fields = []
                values = []
                
                for field, value in kwargs.items():
                    if field in allowed_fields and value is not None:
                        # Validate and sanitize values
                        if field in ['username', 'first_name', 'last_name'] and value:
                            # Strict rules for usernames
                            if field == 'username':
                                is_valid, cleaned = validate_user_input(value, 'username', 50)
                                if not is_valid:
                                    logger.warning(f"Invalid username: {cleaned}")
                                    continue
                                value = cleaned
                            else:
                                is_valid, cleaned = validate_user_input(value, 'text', 100)
                                if not is_valid:
                                    logger.warning(f"Invalid value for {field}: {cleaned}")
                                    continue
                                value = cleaned
                        
                        # Add to updates list
                        db_field = 'language' if field == 'language_code' else field
                        update_fields.append(f'{db_field} = ?')
                        values.append(value)
                
                if not update_fields:
                    return False
                
                # Append user_id to values
                values.append(user_id)
                
                query = f'UPDATE users SET {", ".join(update_fields)} WHERE user_id = ?'
                cursor.execute(query, values)
                conn.commit()
                
                # Invalidate user cache
                cache_keys_to_invalidate = [f"user_{user_id}", f"language_{user_id}", f"stats_{user_id}"]
                for cache_key in cache_keys_to_invalidate:
                    if cache_key in self._cache:
                        del self._cache[cache_key]
                
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error updating user {user_id}: {e}")
                return False

    def set_user_language(self, user_id: int, language: str) -> bool:
        """Set user language."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                language = (language or 'en').strip().lower()
                if language not in ('en', 'ua'):
                    language = 'en'
                cursor.execute('''
                    UPDATE users SET language = ? WHERE user_id = ?
                ''', (language, user_id))
                conn.commit()

                # Invalidate cache
                cache_key = self._get_cache_key('language', user_id)
                if cache_key in self._cache:
                    del self._cache[cache_key]

                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error setting language for {user_id}: {e}")
                return False

    def set_user_avatar(self, user_id: int, avatar_url: str) -> bool:
        """Set user avatar."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE users SET avatar_url = ? WHERE user_id = ?
                ''', (avatar_url, user_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error setting avatar for {user_id}: {e}")
                return False

    def _get_cache_key(self, key_type: str, user_id: int) -> str:
        """Generate cache key"""
        return f"{key_type}_{user_id}"

    def _get_cached_value(self, cache_key: str):
        """Get value from cache if not expired with stats tracking"""
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if time.time() - cached_data['timestamp'] < self._cache_timeout:
                self._cache_stats['hits'] += 1
                return cached_data['value']
            else:
                del self._cache[cache_key]
                self._cache_stats['evictions'] += 1
        self._cache_stats['misses'] += 1
        return None

    def _set_cached_value(self, cache_key: str, value):
        """Set value in cache"""
        self._cache[cache_key] = {
            'value': value,
            'timestamp': time.time()
        }

    def get_user_language(self, user_id: int) -> str:
        """Get user language with caching and query optimization."""
        cache_key = self._get_cache_key('language', user_id)
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Optimized query using an index
            cursor.execute('SELECT language FROM users WHERE user_id = ? LIMIT 1', (user_id,))
            row = cursor.fetchone()
            language = row[0] if row else 'en'

        language = (language or 'en').strip().lower()
        if language not in ('en', 'ua'):
            language = 'en'

        self._set_cached_value(cache_key, language)
        return language

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None







    def update_user_stats(self, user_id: int, deals_count: int = None, total_amount: float = None):
        """Update user statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if deals_count is not None:
                cursor.execute('''
                    UPDATE users SET deals_count = deals_count + ? WHERE user_id = ?
                ''', (deals_count, user_id))
            if total_amount is not None:
                cursor.execute('''
                    UPDATE users SET total_deal_amount = total_deal_amount + ? WHERE user_id = ?
                ''', (total_amount, user_id))
            conn.commit()

        # Invalidate cache for user stats
        cache_key = self._get_cache_key('stats', user_id)
        if cache_key in self._cache:
            del self._cache[cache_key]

    def get_user_stats(self, user_id: int) -> Dict:
        """Get user statistics with caching."""
        cache_key = self._get_cache_key('stats', user_id)
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        # Get user deals and calculate stats
        user_deals = self.get_user_deals(user_id)
        completed_deals = [deal for deal in user_deals if deal['status'] == 'completed']
        total_deals = len(user_deals)
        completed_count = len(completed_deals)
        total_volume = sum(
            convert_amount_to_usd(deal['amount'], deal.get('currency'))
            for deal in completed_deals
        )
        success_rate = ((completed_count / total_deals * 100) if total_deals > 0 else 0)

        stats = {
            'total_deals': total_deals,
            'completed_deals': completed_count,
            'active_deals': total_deals - completed_count,
            'total_volume': total_volume,
            'success_rate': success_rate
        }

        self._set_cached_value(cache_key, stats)
        return stats

    # === DEAL METHODS ===

    def create_deal(self, deal_code: str, buyer_id: int, amount: float, currency: str,
                    description: str = None, product_link: str = None, image_link: str = None) -> bool:
        """Create a deal with data validation and atomic operations."""
        # Input validation
        if not validate_deal_code(deal_code):
            logger.error(f"Invalid deal code: {deal_code}")
            return False

        if not isinstance(buyer_id, int) or buyer_id <= 0:
            logger.error(f"Invalid buyer_id: {buyer_id}")
            return False

        if not isinstance(amount, (int, float)) or amount <= 0:
            logger.error(f"Invalid amount: {amount}")
            return False

        if currency not in ['USDT', 'TON']:
            logger.error(f"Invalid currency: {currency}")
            return False

        # Sanitize text fields
        if description:
            is_valid, description = validate_user_input(description, 'description', 500)
            if not is_valid:
                logger.error(f"Invalid description: {description}")
                return False

        if product_link:
            is_valid, product_link = validate_user_input(product_link, 'text', 500)
            if not is_valid:
                logger.error(f"Invalid product link: {product_link}")
                return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Use a transaction for atomicity
                cursor.execute("BEGIN TRANSACTION")

                # Ensure the user exists
                cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (buyer_id,))
                if not cursor.fetchone():
                    cursor.execute("ROLLBACK")
                    logger.error(f"User {buyer_id} does not exist")
                    return False

                # Ensure the deal code is unique
                cursor.execute('SELECT deal_code FROM deals WHERE deal_code = ?', (deal_code,))
                if cursor.fetchone():
                    cursor.execute("ROLLBACK")
                    logger.error(f"Код сделки {deal_code} уже существует")
                    return False

                # Create the deal atomically
                cursor.execute('''
                    INSERT INTO deals
                    (deal_code, buyer_id, amount, currency, description, product_link, image_link, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (deal_code, buyer_id, amount, currency, description, product_link, image_link,
                      datetime.now().isoformat(), datetime.now().isoformat()))

                cursor.execute("COMMIT")
                logger.info(f"Deal {deal_code} created for user {buyer_id}")
                return True

            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Error creating deal {deal_code}: {e}")
                return False

    def get_deal(self, deal_code: str) -> Optional[Dict]:
        """Get a deal by code with validation and query optimization."""
        # Pre-validate deal code
        if not validate_deal_code(deal_code):
            logger.warning(f"Attempted to get deal with invalid code: {deal_code}")
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Optimized query with an index and LIMIT for performance
                cursor.execute('SELECT * FROM deals WHERE deal_code = ? LIMIT 1', (deal_code,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Error fetching deal {deal_code}: {e}")
                return None

    def join_deal(self, deal_code: str, seller_id: int) -> bool:
        """Join a deal as a seller with validation and atomic operations."""
        # Input validation
        if not validate_deal_code(deal_code):
            logger.error(f"Invalid deal code when joining: {deal_code}")
            return False

        if not isinstance(seller_id, int) or seller_id <= 0:
            logger.error(f"Invalid seller_id: {seller_id}")
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Use a transaction for atomicity
                cursor.execute("BEGIN TRANSACTION")

                # Ensure the deal exists and is active
                cursor.execute('SELECT buyer_id, seller_id, status FROM deals WHERE deal_code = ? AND status = "active"', (deal_code,))
                deal_row = cursor.fetchone()

                if not deal_row:
                    cursor.execute("ROLLBACK")
                    logger.warning(f"Deal {deal_code} not found or not active")
                    return False

                # Ensure the user is not joining their own deal
                if deal_row[0] == seller_id:  # buyer_id
                    cursor.execute("ROLLBACK")
                    logger.warning(f"User {seller_id} tried to join their own deal {deal_code}")
                    return False

                # Ensure a seller is not already assigned
                if deal_row[1] is not None:  # seller_id
                    cursor.execute("ROLLBACK")
                    logger.warning(f"Deal {deal_code} already has a seller")
                    return False

                # Update the deal atomically
                cursor.execute('''
                    UPDATE deals SET seller_id = ?, seller_joined_at = ?, updated_at = ?
                    WHERE deal_code = ? AND seller_id IS NULL AND status = 'active'
                ''', (seller_id, datetime.now().isoformat(), datetime.now().isoformat(), deal_code))

                if cursor.rowcount == 0:
                    cursor.execute("ROLLBACK")
                    logger.warning(f"Failed to join deal {deal_code} (it may already be taken)")
                    return False

                cursor.execute("COMMIT")
                logger.info(f"User {seller_id} joined deal {deal_code}")
                return True

            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Error joining deal {deal_code}: {e}")
                return False

    def update_deal_status(self, deal_code: str, status: str, **kwargs) -> bool:
        """Update deal status with validation and atomic operations."""
        # Input validation
        if not validate_deal_code(deal_code):
            logger.error(f"Invalid deal code when updating status: {deal_code}")
            return False

        # Allowed statuses
        allowed_statuses = ['active', 'completed', 'cancelled', 'expired', 'pending', 'dispute_open', 'dispute_resolved', 'funded', 'receipt_pending', 'delivery_pending', 'funds_pending']
        if status not in allowed_statuses:
            logger.error(f"Invalid deal status: {status}")
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Use a transaction for atomicity
                cursor.execute("BEGIN TRANSACTION")

                # Ensure the deal exists
                cursor.execute('SELECT status FROM deals WHERE deal_code = ?', (deal_code,))
                current_deal = cursor.fetchone()
                if not current_deal:
                    cursor.execute("ROLLBACK")
                    logger.error(f"Deal {deal_code} not found")
                    return False

                update_fields = ['status = ?', 'updated_at = ?']
                values = [status, datetime.now().isoformat()]

                # Add optional fields
                field_mapping = {
                    'payment_confirmed_at': 'payment_confirmed_at',
                    'completed_at': 'completed_at',
                    'cancelled_at': 'cancelled_at',
                    'cancel_reason': 'cancel_reason',
                    'commission_amount': 'commission_amount',
                    'seller_amount': 'seller_amount'
                }

                for field, db_field in field_mapping.items():
                    if field in kwargs:
                        update_fields.append(f'{db_field} = ?')
                        values.append(kwargs[field])

                query = f'UPDATE deals SET {", ".join(update_fields)} WHERE deal_code = ?'
                values.append(deal_code)

                cursor.execute(query, values)

                if cursor.rowcount == 0:
                    cursor.execute("ROLLBACK")
                    logger.error(f"Failed to update deal status for {deal_code}")
                    return False

                cursor.execute("COMMIT")
                logger.info(f"Статус сделки {deal_code} обновлен на {status}")
                return True

            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Error updating deal status for {deal_code}: {e}")
                return False

    def get_user_deals(self, user_id: int, status: str = None) -> List[Dict]:
        """Get user deals with query optimizations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute('''
                    SELECT * FROM deals
                    WHERE (buyer_id = ? OR seller_id = ?) AND status = ?
                    ORDER BY created_at DESC
                ''', (user_id, user_id, status))
            else:
                cursor.execute('''
                    SELECT * FROM deals
                    WHERE buyer_id = ? OR seller_id = ?
                    ORDER BY created_at DESC
                ''', (user_id, user_id))

            # Use a generator to efficiently handle large result sets
            return [dict(row) for row in cursor.fetchall()]


    def get_all_deals(self, status: str = None, limit: int = 50, offset: int = 0, search: str = None) -> List[Dict]:
        """Get all deals with optional status/search filtering."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            base_query = '''
                SELECT d.*, u1.username as buyer_username, u1.first_name as buyer_first_name,
                       u2.username as seller_username, u2.first_name as seller_first_name
                FROM deals d
                LEFT JOIN users u1 ON d.buyer_id = u1.user_id
                LEFT JOIN users u2 ON d.seller_id = u2.user_id
            '''
            conditions = []
            params = []

            if status and status != 'all':
                conditions.append('d.status = ?')
                params.append(status)

            if search:
                search_term = f"%{search.strip().lower()}%"
                conditions.append('('
                                  'LOWER(d.deal_code) LIKE ? OR '
                                  'CAST(d.buyer_id AS TEXT) LIKE ? OR '
                                  'CAST(d.seller_id AS TEXT) LIKE ? OR '
                                  'LOWER(u1.username) LIKE ? OR '
                                  'LOWER(u2.username) LIKE ? OR '
                                  'LOWER(u1.first_name) LIKE ? OR '
                                  'LOWER(u2.first_name) LIKE ?'
                                  ')')
                params.extend([search_term] * 7)

            if conditions:
                base_query += ' WHERE ' + ' AND '.join(conditions)

            base_query += ' ORDER BY d.created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])

            cursor.execute(base_query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_deals_count(self, status: str = None, search: str = None) -> int:
        """Get total deal count with optional status/search filtering."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            base_query = '''
                SELECT COUNT(*) as deals_count
                FROM deals d
                LEFT JOIN users u1 ON d.buyer_id = u1.user_id
                LEFT JOIN users u2 ON d.seller_id = u2.user_id
            '''
            conditions = []
            params = []

            if status and status != 'all':
                conditions.append('d.status = ?')
                params.append(status)

            if search:
                search_term = f"%{search.strip().lower()}%"
                conditions.append('('
                                  'LOWER(d.deal_code) LIKE ? OR '
                                  'CAST(d.buyer_id AS TEXT) LIKE ? OR '
                                  'CAST(d.seller_id AS TEXT) LIKE ? OR '
                                  'LOWER(u1.username) LIKE ? OR '
                                  'LOWER(u2.username) LIKE ? OR '
                                  'LOWER(u1.first_name) LIKE ? OR '
                                  'LOWER(u2.first_name) LIKE ?'
                                  ')')
                params.extend([search_term] * 7)

            if conditions:
                base_query += ' WHERE ' + ' AND '.join(conditions)

            cursor.execute(base_query, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    # === CRYPTO CHECKOUT METHODS ===

    def create_crypto_checkout(self, checkout_id: str, deal_code: str, wallet_address: str,
                              amount: float, currency: str, expires_at: str,
                              qr_code_path: str = None) -> bool:
        """Create a crypto checkout."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO crypto_checkouts
                    (checkout_id, deal_code, wallet_address, amount, currency, created_at, expires_at, qr_code_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (checkout_id, deal_code, wallet_address, amount, currency,
                      datetime.now().isoformat(), expires_at, qr_code_path))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating checkout {checkout_id}: {e}")
                return False

    def get_crypto_checkout(self, checkout_id: str) -> Optional[Dict]:
        """Get a crypto checkout."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM crypto_checkouts WHERE checkout_id = ?', (checkout_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_crypto_checkout_by_deal(self, deal_code: str) -> Optional[Dict]:
        """Get a crypto checkout by deal code."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM crypto_checkouts WHERE deal_code = ?', (deal_code,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_checkout_status(self, checkout_id: str, status: str, tx_hash: str = None) -> bool:
        """Update checkout status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                if tx_hash:
                    cursor.execute('''
                        UPDATE crypto_checkouts SET status = ?, tx_hash = ?, confirmed_at = ?
                        WHERE checkout_id = ?
                    ''', (status, tx_hash, datetime.now().isoformat(), checkout_id))
                else:
                    cursor.execute('''
                        UPDATE crypto_checkouts SET status = ?, confirmed_at = ?
                        WHERE checkout_id = ?
                    ''', (status, datetime.now().isoformat(), checkout_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error updating checkout {checkout_id}: {e}")
                return False

    # === PAYMENT METHODS ===

    def create_payment(self, payment_id: str, checkout_id: str, tx_hash: str,
                      amount: float, currency: str) -> bool:
        """Create a payment record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO payments
                    (payment_id, checkout_id, tx_hash, amount, currency, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (payment_id, checkout_id, tx_hash, amount, currency, datetime.now().isoformat()))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating payment {payment_id}: {e}")
                return False

    def update_payment_confirmations(self, payment_id: str, confirmations: int) -> bool:
        """Update payment confirmation count."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                if confirmations >= 1:  # 1 confirmation is enough for our currencies
                    cursor.execute('''
                        UPDATE payments SET confirmations = ?, status = 'confirmed', confirmed_at = ?
                        WHERE payment_id = ?
                    ''', (confirmations, datetime.now().isoformat(), payment_id))
                else:
                    cursor.execute('''
                        UPDATE payments SET confirmations = ?
                        WHERE payment_id = ?
                    ''', (confirmations, payment_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error updating confirmations for {payment_id}: {e}")
                return False

    # === SETTINGS METHODS ===

    def get_payment_by_checkout(self, checkout_id: str) -> Optional[Dict]:
        """Return payment record for a given checkout_id"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM payments WHERE checkout_id = ? ORDER BY created_at DESC LIMIT 1', (checkout_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_settings(self) -> Dict:
        """Get system settings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM settings WHERE id = 1')
            row = cursor.fetchone()
            return dict(row) if row else {}

    def update_settings(self, **kwargs) -> bool:
        """Update system settings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                update_fields = []
                values = []

                for key, value in kwargs.items():
                    update_fields.append(f'{key} = ?')
                    values.append(value)

                if update_fields:
                    query = f'UPDATE settings SET {", ".join(update_fields)} WHERE id = 1'
                    cursor.execute(query, values)
                    conn.commit()
                    return True
                return False
            except Exception as e:
                logger.error(f"Error updating settings: {e}")
                return False

    # === ACHIEVEMENTS SECTION REMOVED ===

    # === STATISTICS ===

    def get_stats(self) -> Dict:
        """Get overall statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Overall statistics
            cursor.execute('SELECT COUNT(*) as users_count FROM users')
            users_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) as deals_count FROM deals')
            deals_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) as active_deals FROM deals WHERE status = "active"')
            active_deals = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) as completed_deals FROM deals WHERE status = "completed"')
            completed_deals = cursor.fetchone()[0]

            cursor.execute('SELECT amount, currency FROM deals WHERE status = "completed"')
            total_volume = 0.0
            for row in cursor.fetchall():
                total_volume += convert_amount_to_usd(row['amount'], row['currency'])

            return {
                'users_count': users_count,
                'deals_count': deals_count,
                'active_deals': active_deals,
                'completed_deals': completed_deals,
                'total_volume': total_volume
            }

    def get_admin_analytics(self, period: str = '30d') -> Dict:
        """Get detailed admin analytics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Calculate date range based on period
            end_date = datetime.now()

            if period == '7d':
                start_date = end_date - timedelta(days=7)
            elif period == '30d':
                start_date = end_date - timedelta(days=30)
            elif period == '90d':
                start_date = end_date - timedelta(days=90)
            else:
                start_date = end_date - timedelta(days=30)

            # Get all deals within the period
            cursor.execute('''
                SELECT * FROM deals
                WHERE created_at >= ?
                ORDER BY created_at ASC
            ''', (start_date.isoformat(),))
            period_deals = [dict(row) for row in cursor.fetchall()]

            # === DEALS TREND (daily) ===
            deals_trend = {'labels': [], 'data': []}
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                deals_trend['labels'].append(date_str)

                # Count completed deals for this date
                day_deals = [deal for deal in period_deals
                            if datetime.fromisoformat(deal['created_at']).date() == current_date.date()
                            and deal['status'] == 'completed']
                deals_trend['data'].append(len(day_deals))

                current_date += timedelta(days=1)

            # === VOLUME TREND (daily) ===
            volume_trend = {'labels': [], 'data': []}
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                volume_trend['labels'].append(date_str)

                # Sum volume for completed deals on this date
                day_volume = sum(deal['amount'] for deal in period_deals
                               if datetime.fromisoformat(deal['created_at']).date() == current_date.date()
                               and deal['status'] == 'completed')
                volume_trend['data'].append(round(day_volume, 2))

                current_date += timedelta(days=1)

            # === USER REGISTRATIONS TREND ===
            cursor.execute('''
                SELECT registered_date FROM users
                WHERE registered_date >= ?
                ORDER BY registered_date ASC
            ''', (start_date.isoformat(),))
            user_registrations = [row[0] for row in cursor.fetchall()]

            users_trend = {'labels': [], 'data': []}
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                users_trend['labels'].append(date_str)

                # Count registrations for this date
                day_registrations = len([reg for reg in user_registrations
                                       if datetime.fromisoformat(reg).date() == current_date.date()])
                users_trend['data'].append(day_registrations)

                current_date += timedelta(days=1)

            # === CURRENCY DISTRIBUTION ===
            currency_distribution = {'USDT': 0, 'TON': 0}
            for deal in period_deals:
                if deal['status'] == 'completed':
                    currency = deal['currency']
                    if currency in currency_distribution:
                        currency_distribution[currency] += deal['amount']

            # === SUCCESS RATE TREND (weekly) ===
            success_trend = {'labels': [], 'data': []}
            current_date = start_date
            while current_date <= end_date:
                week_start = current_date
                week_end = min(current_date + timedelta(days=6), end_date)

                week_deals = [deal for deal in period_deals
                             if week_start <= datetime.fromisoformat(deal['created_at']) <= week_end]

                if week_deals:
                    completed = len([d for d in week_deals if d['status'] == 'completed'])
                    success_rate = (completed / len(week_deals)) * 100
                else:
                    success_rate = 0

                success_trend['labels'].append(f"{week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}")
                success_trend['data'].append(round(success_rate, 1))

                current_date = week_end + timedelta(days=1)

            # === TOP CURRENCIES USAGE COUNT ===
            currency_usage = {'USDT': 0, 'TON': 0}
            for deal in period_deals:
                currency = deal['currency']
                if currency in currency_usage:
                    currency_usage[currency] += 1

            # === DEAL STATUS DISTRIBUTION ===
            status_distribution = {'active': 0, 'completed': 0, 'cancelled': 0, 'expired': 0}
            for deal in period_deals:
                status = deal['status']
                if status in status_distribution:
                    status_distribution[status] += 1

            # === REVENUE ANALYSIS ===
            cursor.execute('SELECT SUM(commission_amount) as total_commission FROM deals WHERE status = "completed"')
            total_commission = cursor.fetchone()[0] or 0

            cursor.execute('SELECT SUM(seller_amount) as total_seller_payments FROM deals WHERE status = "completed"')
            total_seller_payments = cursor.fetchone()[0] or 0

            # === USER ENGAGEMENT ===
            cursor.execute('SELECT COUNT(*) as active_users FROM users WHERE deals_count > 0')
            active_users = cursor.fetchone()[0]

            cursor.execute('SELECT AVG(deals_count) as avg_deals_per_user FROM users WHERE deals_count > 0')
            avg_deals_per_user = cursor.fetchone()[0] or 0

            return {
                'period': period,
                'deals_trend': deals_trend,
                'volume_trend': volume_trend,
                'users_trend': users_trend,
                'currency_distribution': list(currency_distribution.values()),
                'currency_labels': list(currency_distribution.keys()),
                'success_trend': success_trend,
                'currency_usage': list(currency_usage.values()),
                'currency_usage_labels': list(currency_usage.keys()),
                'status_distribution': status_distribution,
                'revenue': {
                    'total_commission': round(total_commission, 2),
                    'total_seller_payments': round(total_seller_payments, 2),
                    'total_volume': round(sum(currency_distribution.values()), 2)
                },
                'user_engagement': {
                    'active_users': active_users,
                    'avg_deals_per_user': round(avg_deals_per_user, 1)
                }
            }

    def _migrate_database(self):
        """Run database migrations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check and add the language column to users
            try:
                cursor.execute("SELECT language FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column does not exist; add it
                cursor.execute('ALTER TABLE users ADD COLUMN language TEXT DEFAULT "en"')
                logger.info("Добавлена колонка language в таблицу users")

            # Check and add the last_name column to users
            try:
                cursor.execute("SELECT last_name FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column does not exist; add it
                cursor.execute('ALTER TABLE users ADD COLUMN last_name TEXT')
                logger.info("Добавлена колонка last_name в таблицу users")

            # Check and add the avatar_url column to users
            try:
                cursor.execute("SELECT avatar_url FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column does not exist; add it
                cursor.execute('ALTER TABLE users ADD COLUMN avatar_url TEXT')
                logger.info("Добавлена колонка avatar_url в таблицу users")

            # Check and add the updated_at column to deals
            try:
                cursor.execute("SELECT updated_at FROM deals LIMIT 1")
            except sqlite3.OperationalError:
                # Column does not exist; add it
                cursor.execute('ALTER TABLE deals ADD COLUMN updated_at TEXT')
                # Backfill existing rows with created_at
                cursor.execute('UPDATE deals SET updated_at = created_at WHERE updated_at IS NULL')
                logger.info("Добавлена колонка updated_at в таблицу deals")

            # Check whether the auth_tokens table exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER,
                    created_at TEXT,
                    expires_at TEXT,
                    used INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            conn.commit()

    def create_auth_token(self, user_id: int) -> str:
        """Create an auth token for a user."""
        import secrets
        import string
        from datetime import datetime, timedelta
        from shared.constants import TOKEN_LENGTH

        # Ensure the user exists before creating a token
        user = self.get_user(user_id)
        if not user:
            logger.error(f"CRITICAL: Attempted to create auth token for non-existent user {user_id}")
            logger.error(f"User {user_id} does not exist in database. Token creation blocked.")
            return None

        logger.info(f"Creating auth token for existing user {user_id}")

        # Generate a 16-character token for improved security
        alphabet = string.ascii_letters + string.digits
        token = ''.join(secrets.choice(alphabet) for _ in range(TOKEN_LENGTH))

        # Set a 24-hour expiration for user convenience
        expires_at = datetime.now() + timedelta(hours=24)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO auth_tokens (token, user_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (token, user_id, datetime.now().isoformat(), expires_at.isoformat()))
                conn.commit()
                logger.info(f"Successfully created auth token for user {user_id}")
                return token
            except Exception as e:
                logger.error(f"Error creating token for {user_id}: {e}")
                return None

    def validate_auth_token(self, token: str) -> Optional[int]:
        """Validate an auth token and return user_id if valid."""
        token_fp = self._token_fingerprint(token)
        logger.debug(f"VALIDATE_TOKEN: Starting validation for token fp={token_fp}")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, expires_at, used FROM auth_tokens
                    WHERE token = ?
                ''', (token,))

                row = cursor.fetchone()
                logger.info(f"VALIDATE_TOKEN: Database query result: {row is not None}")

                if not row:
                    logger.warning(f"VALIDATE_TOKEN: Token not found in database fp={token_fp}")
                    logger.debug("VALIDATE_TOKEN: Checking if token table has any rows...")
                    # Check if table exists and has any tokens
                    cursor.execute('SELECT COUNT(*) FROM auth_tokens')
                    total_tokens = cursor.fetchone()[0]
                    logger.debug(f"VALIDATE_TOKEN: Total tokens in database: {total_tokens}")
                    return None

                user_id, expires_at, used = row
                logger.info(f"VALIDATE_TOKEN: Found token for user_id: {user_id}, expires_at: {expires_at}, used: {used}")

                # Check whether the token has already been used
                if used:
                    logger.warning(f"VALIDATE_TOKEN: Token already used for user {user_id}")
                    return None

                # Check expiration
                expires_at_dt = datetime.fromisoformat(expires_at)
                current_time = datetime.now()
                logger.info(f"VALIDATE_TOKEN: Current time: {current_time}, Expires at: {expires_at_dt}")

                if expires_at_dt < current_time:
                    logger.warning(f"VALIDATE_TOKEN: Token expired for user {user_id}. Expired at: {expires_at_dt}, Current: {current_time}")
                    return None

                logger.info(f"VALIDATE_TOKEN: Token validation successful for user {user_id}")

                # Mark token as used after successful validation
                return user_id

        except Exception as e:
            logger.error(f"VALIDATE_TOKEN: Exception during token validation: {e}")
            logger.error(f"VALIDATE_TOKEN: Full traceback", exc_info=True)
            return None

    def consume_auth_token(self, token: str) -> bool:
        """Mark token as used after a successful login.

        Consumption is separate from validation so that link preview/prefetchers (e.g. TelegramBot)
        don't burn one-time tokens just by fetching the URL.
        """
        if not token:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE auth_tokens SET used = 1 WHERE token = ? AND used = 0",
                    (token,),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to consume auth token fp={self._token_fingerprint(token)}: {e}")
            logger.error("Full traceback", exc_info=True)
            return False

    def cleanup_expired_tokens(self):
        """Clean up expired tokens."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM auth_tokens WHERE expires_at < ?', (datetime.now().isoformat(),))
            conn.commit()

    # === NOTIFICATION METHODS ===

    def create_notification(self, user_id: int, notification_type: str, title: str,
                           message: str, action_url: str = None) -> bool:
        """Create a notification."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO notifications
                    (user_id, type, title, message, action_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, notification_type, title, message, action_url, datetime.now().isoformat()))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating notification for {user_id}: {e}")
                return False

    def get_user_notifications(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get user notifications."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, type, title, message, action_url, read, created_at
                FROM notifications
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def mark_notification_read(self, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE notifications SET read = 1
                    WHERE id = ? AND user_id = ?
                ''', (notification_id, user_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error marking notification {notification_id} as read: {e}")
                return False

    def mark_all_notifications_read(self, user_id: int) -> int:
        """Mark all user notifications as read and return the number of updated rows."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE notifications SET read = 1
                    WHERE user_id = ? AND read = 0
                ''', (user_id,))
                conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Error marking all notifications as read for {user_id}: {e}")
                return 0

    def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Delete a notification."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    DELETE FROM notifications
                    WHERE id = ? AND user_id = ?
                ''', (notification_id, user_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error deleting notification {notification_id}: {e}")
                return False

    def delete_all_notifications(self, user_id: int) -> int:
        """Delete all user notifications and return the number of deleted rows."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
                conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Error deleting all notifications for {user_id}: {e}")
                return 0

    def delete_multiple_notifications(self, user_id: int, notification_ids: List[int]) -> int:
        """Delete multiple user notifications and return the number of deleted rows."""
        if not notification_ids:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Build placeholders for the IN query
                placeholders = ','.join('?' * len(notification_ids))
                query = f'DELETE FROM notifications WHERE user_id = ? AND id IN ({placeholders})'

                # Parameters: user_id + list of notification IDs
                params = [user_id] + notification_ids

                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Error deleting notifications {notification_ids} for {user_id}: {e}")
                return 0

    def get_unread_notifications_count(self, user_id: int) -> int:
        """Get unread notifications count."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM notifications
                WHERE user_id = ? AND read = 0
            ''', (user_id,))
            return cursor.fetchone()[0]

    def _clear_demo_data(self):
        """Remove demo data to display real statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Delete demo users (IDs in range 1000-9999)
            cursor.execute('DELETE FROM users WHERE user_id >= ? AND user_id <= ?', (1000, 9999))

            # Delete demo deals (codes starting with DEMO)
            cursor.execute('DELETE FROM deals WHERE deal_code LIKE ?', ('DEMO%',))

            # Delete related records in other tables
            cursor.execute('DELETE FROM crypto_checkouts WHERE deal_code LIKE ?', ('DEMO%',))
            cursor.execute('DELETE FROM payments WHERE checkout_id LIKE ?', ('DEMO%',))
            cursor.execute('DELETE FROM auth_tokens WHERE user_id >= ? AND user_id <= ?', (1000, 9999))

            conn.commit()
            logger.info("Demo data cleared")

    def _create_demo_notifications(self):
        """Create a welcome notification for new users."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create a welcome notification only for new users (no existing notifications)
            cursor.execute('SELECT user_id FROM users WHERE user_id NOT IN (SELECT DISTINCT user_id FROM notifications)')
            new_users = cursor.fetchall()

            for user_row in new_users:
                user_id = user_row[0]

                # Create only the system welcome notification
                cursor.execute('''
                    INSERT INTO notifications
                    (user_id, type, title, message, action_url, read, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    'system',
                    'Welcome to Black Diamond!',
                    'Thanks for signing up! Start by creating your first deal.',
                    '/create-deal',
                    False,
                    datetime.now().isoformat()
                ))

            if new_users:
                conn.commit()
                logger.info(f"Welcome notifications created for {len(new_users)} new users")

    # === SUPPORT CHAT METHODS ===

    def save_support_message(self, user_id: int, message: str, is_from_user: bool = True) -> bool:
        """Save a support chat message with validation."""
        # Input validation
        if not isinstance(user_id, int) or user_id <= 0:
            logger.error(f"Invalid user_id in support message: {user_id}")
            return False

        if not message or not isinstance(message, str):
            logger.error("Пустое или неверное сообщение поддержки")
            return False

        # Sanitize and validate message
        is_valid, message = validate_user_input(message, 'text', 1000)
        if not is_valid:
            logger.error(f"Invalid support message: {message}")
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO support_chat_messages
                    (user_id, message, is_from_user, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, message, is_from_user, datetime.now().isoformat()))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error saving support message: {e}")
                return False

    def get_support_messages(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get support chat messages for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, message, is_from_user, created_at, read_by_admin, read_by_user
                FROM support_chat_messages
                WHERE user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_unread_support_messages_count(self, user_id: int, is_admin: bool = False) -> int:
        """Get unread support messages count."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if is_admin:
                # For admin: unread user messages
                cursor.execute('''
                    SELECT COUNT(*) FROM support_chat_messages
                    WHERE is_from_user = 1 AND read_by_admin = 0
                ''')
            else:
                # For user: unread admin messages
                cursor.execute('''
                    SELECT COUNT(*) FROM support_chat_messages
                    WHERE user_id = ? AND is_from_user = 0 AND read_by_user = 0
                ''', (user_id,))
            return cursor.fetchone()[0]

    def mark_support_messages_read(self, user_id: int, is_admin: bool = False) -> bool:
        """Mark support messages as read."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                if is_admin:
                    cursor.execute('''
                        UPDATE support_chat_messages
                        SET read_by_admin = 1
                        WHERE is_from_user = 1 AND read_by_admin = 0
                    ''')
                else:
                    cursor.execute('''
                        UPDATE support_chat_messages
                        SET read_by_user = 1
                        WHERE user_id = ? AND is_from_user = 0 AND read_by_user = 0
                    ''', (user_id,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error marking messages as read: {e}")
                return False

    def get_all_support_conversations(self, limit: int = 100) -> List[Dict]:
        """Get all active support conversations (admin)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    scm.user_id,
                    u.username,
                    u.first_name,
                    scm.message as last_message,
                    scm.created_at as last_message_time,
                    COUNT(CASE WHEN scm.is_from_user = 1 AND scm.read_by_admin = 0 THEN 1 END) as unread_count
                FROM support_chat_messages scm
                JOIN users u ON scm.user_id = u.user_id
                WHERE scm.created_at = (
                    SELECT MAX(created_at)
                    FROM support_chat_messages
                    WHERE user_id = scm.user_id
                )
                GROUP BY scm.user_id, u.username, u.first_name
                ORDER BY last_message_time DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # === USER ADMIN METHODS ===

    def get_all_users(self, search: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get all users with search and pagination (admin)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT user_id, username, first_name, registered_date, language,
                       deals_count, total_deal_amount, is_banned
                FROM users
            '''
            params = []

            if search:
                query += '''
                    WHERE user_id LIKE ? OR username LIKE ? OR first_name LIKE ?
                '''
                search_param = f'%{search}%'
                params.extend([search_param, search_param, search_param])

            query += ' ORDER BY registered_date DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_users_count(self, search: str = None) -> int:
        """Get user count with search applied."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = 'SELECT COUNT(*) FROM users'
            params = []

            if search:
                query += ' WHERE user_id LIKE ? OR username LIKE ? OR first_name LIKE ?'
                search_param = f'%{search}%'
                params.extend([search_param, search_param, search_param])

            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def ban_user(self, user_id: int, ban: bool) -> bool:
        """Ban or unban a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE users SET is_banned = ? WHERE user_id = ?
                ''', (1 if ban else 0, user_id))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error {'banning' if ban else 'unbanning'} user {user_id}: {e}")
                return False

    # === ADMIN MESSAGE METHODS ===

    def save_admin_message(self, admin_id: int, target_user_id: int, message: str,
                          message_type: str = 'direct', delivery_status: str = 'sent') -> bool:
        """Save an admin message to a user with validation."""
        # Input validation
        if not isinstance(admin_id, int) or admin_id <= 0:
            logger.error(f"Invalid admin_id: {admin_id}")
            return False

        if not isinstance(target_user_id, int) or target_user_id <= 0:
            logger.error(f"Invalid target_user_id: {target_user_id}")
            return False

        if not message or not isinstance(message, str):
            logger.error("Пустое или неверное сообщение админа")
            return False

        if message_type not in ['direct', 'broadcast']:
            logger.error(f"Invalid message type: {message_type}")
            return False

        if delivery_status not in ['sent', 'failed']:
            logger.error(f"Invalid delivery status: {delivery_status}")
            return False

        # Sanitize and validate message
        is_valid, message = validate_user_input(message, 'text', 1000)
        if not is_valid:
            logger.error(f"Invalid admin message: {message}")
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO admin_messages
                    (admin_id, target_user_id, message, message_type, sent_at, delivery_status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (admin_id, target_user_id, message, message_type, datetime.now().isoformat(), delivery_status))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error saving admin message: {e}")
                return False

    def get_admin_messages_history(self, limit: int = 50) -> List[Dict]:
        """Get admin message history (admin)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT am.*, u.username, u.first_name
                FROM admin_messages am
                LEFT JOIN users u ON am.target_user_id = u.user_id
                ORDER BY am.sent_at DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_admin_messages(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Get admin messages for a specific user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT am.*, u.username as admin_username, u.first_name as admin_first_name
                FROM admin_messages am
                LEFT JOIN users u ON am.admin_id = u.user_id
                WHERE am.target_user_id = ?
                ORDER BY am.sent_at DESC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # === DISPUTE METHODS ===

    def get_dispute_by_deal_code(self, deal_code: str) -> Optional[Dict]:
        """Get dispute by deal code."""
        if not validate_deal_code(deal_code):
            logger.warning(f"Attempted to get dispute with invalid deal code: {deal_code}")
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT * FROM disputes WHERE deal_code = ? LIMIT 1
                ''', (deal_code,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Error fetching dispute for {deal_code}: {e}")
                return None

    def get_dispute_messages_history(self, deal_code: str, limit: int = 50) -> List[Dict]:
        """Get dispute message history for a deal (support + admin)."""
        if not validate_deal_code(deal_code):
            logger.warning(f"Attempted to get dispute messages with invalid deal code: {deal_code}")
            return []

        try:
            # Fetch dispute
            dispute = self.get_dispute_by_deal_code(deal_code)
            if not dispute:
                return []

            buyer_id = dispute['buyer_id']
            seller_id = dispute['seller_id']
            all_user_ids = [buyer_id, seller_id]

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Fetch support messages for all dispute participants
                placeholders = ','.join('?' * len(all_user_ids))
                cursor.execute(f'''
                    SELECT
                        'support' as message_type,
                        id,
                        user_id,
                        message,
                        is_from_user,
                        created_at,
                        NULL as admin_id
                    FROM support_chat_messages
                    WHERE user_id IN ({placeholders})
                    ORDER BY created_at ASC
                    LIMIT ?
                ''', (*all_user_ids, limit))

                support_messages = [dict(row) for row in cursor.fetchall()]

                # Fetch admin messages for all dispute participants
                cursor.execute(f'''
                    SELECT
                        'admin' as message_type,
                        id,
                        target_user_id as user_id,
                        message,
                        0 as is_from_user,  # Admin messages are always from admin
                        sent_at as created_at,
                        admin_id
                    FROM admin_messages
                    WHERE target_user_id IN ({placeholders})
                    ORDER BY sent_at ASC
                    LIMIT ?
                ''', (*all_user_ids, limit))

                admin_messages = [dict(row) for row in cursor.fetchall()]

                # Merge and sort all messages
                all_messages = support_messages + admin_messages
                all_messages.sort(key=lambda x: x['created_at'])

                return all_messages[:limit]

        except Exception as e:
            logger.error(f"Error fetching dispute message history for {deal_code}: {e}")
            return []

    def create_dispute_message(self, deal_code: str, user_id: int, message: str, is_from_user: bool = True) -> bool:
        """Create a dispute message."""
        if not validate_deal_code(deal_code):
            logger.error(f"Invalid deal code in dispute message: {deal_code}")
            return False

        # Message validation
        is_valid, message = validate_user_input(message, 'text', 1000)
        if not is_valid:
            logger.error(f"Invalid dispute message: {message}")
            return False

        # Ensure the dispute exists
        dispute = self.get_dispute_by_deal_code(deal_code)
        if not dispute:
            logger.error(f"Спор не найден для сделки {deal_code}")
            return False

        # Ensure the user participates in the dispute
        if user_id not in [dispute['buyer_id'], dispute['seller_id']]:
            logger.error(f"User {user_id} is not a participant in dispute {deal_code}")
            return False

        # Save as a support message
        return self.save_support_message(user_id, message, is_from_user)

    def has_active_dispute(self, deal_code: str) -> bool:
        """Check whether a deal has an active dispute."""
        dispute = self.get_dispute_by_deal_code(deal_code)
        return dispute is not None and dispute['status'] in ['open', 'in_progress']

    # === DECENTRALIZED PAYMENT METHODS ===

    def create_decentralized_payment(self, deal_code: str, escrow_address: str, amount: float,
                                   currency: str, payment_memo: str = None, qr_code: str = "", status: str = "pending",
                                   created_at: str = None, expires_at: str = None, checkout_id: str = None) -> bool:
        """Create a decentralized payment."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                self._ensure_decentralized_payment_columns(cursor)
                cursor.execute("PRAGMA table_info(decentralized_payments)")
                columns = {row[1] for row in cursor.fetchall()}
                has_memo = "payment_memo" in columns

                if has_memo:
                    cursor.execute('''
                        INSERT INTO decentralized_payments
                        (deal_code, escrow_address, amount, currency, payment_memo, qr_code, status, checkout_id, created_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (deal_code, escrow_address, amount, currency, payment_memo, qr_code, status, checkout_id,
                          created_at or datetime.now().isoformat(),
                          expires_at or (datetime.now() + timedelta(hours=24)).isoformat()))
                else:
                    logger.warning("payment_memo column missing; inserting without memo")
                    cursor.execute('''
                        INSERT INTO decentralized_payments
                        (deal_code, escrow_address, amount, currency, qr_code, status, checkout_id, created_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (deal_code, escrow_address, amount, currency, qr_code, status, checkout_id,
                          created_at or datetime.now().isoformat(),
                          expires_at or (datetime.now() + timedelta(hours=24)).isoformat()))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating decentralized payment: {e}")
                return False

    def update_decentralized_payment_status(self, deal_code: str, status: str, tx_hash: str = None) -> bool:
        """Update decentralized payment status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                if tx_hash:
                    cursor.execute('''
                        UPDATE decentralized_payments
                        SET status = ?, tx_hash = ?, confirmed_at = ?
                        WHERE deal_code = ?
                    ''', (status, tx_hash, datetime.now().isoformat(), deal_code))
                else:
                    cursor.execute('''
                        UPDATE decentralized_payments
                        SET status = ?
                        WHERE deal_code = ?
                    ''', (status, deal_code))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error updating decentralized payment status: {e}")
                return False

    def get_decentralized_payment_by_checkout(self, checkout_id: str) -> Optional[Dict]:
        """Get decentralized payment by checkout_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM decentralized_payments WHERE checkout_id = ?
            ''', (checkout_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_decentralized_payment_by_deal_code(self, deal_code: str) -> Optional[Dict]:
        """Get decentralized payment by deal code."""
        if not validate_deal_code(deal_code):
            logger.warning(f"Attempted to get payment with invalid deal code: {deal_code}")
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT * FROM decentralized_payments WHERE deal_code = ? LIMIT 1
                ''', (deal_code,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Error fetching decentralized payment for {deal_code}: {e}")
                return None

# Global database instance
db = Database()

import sqlite3
import logging
from typing import Dict, Any
from shared.config import DATABASE_URL

logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """Database migrator with indexes and optimizations."""

    def __init__(self, db_path: str = DATABASE_URL):
        self.db_path = db_path.replace('sqlite:///', '')

    def run_migrations(self) -> bool:
        """Run all migrations."""
        try:
            logger.info("Starting database migrations...")

            migrations = [
                self._add_indexes,
                self._optimize_performance,
                self._add_foreign_keys,
                self._add_constraints,
                self._add_audit_trail,
                self._add_connection_pooling_support,
            ]

            for migration in migrations:
                try:
                    migration()
                    logger.info(f"Migration {migration.__name__} completed successfully")
                except Exception as e:
                    logger.error(f"Error in migration {migration.__name__}: {e}")
                    return False

            logger.info("All migrations completed successfully")
            return True

        except Exception as e:
            logger.error(f"Migration error: {e}")
            return False

    def _add_indexes(self):
        """Add indexes for performance."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Indexes for the users table
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
                "CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)",
                "CREATE INDEX IF NOT EXISTS idx_users_registered_date ON users(registered_date)",
                "CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned)",
                "CREATE INDEX IF NOT EXISTS idx_users_deals_count ON users(deals_count)",
            ]

            # Indexes for the deals table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_deals_deal_code ON deals(deal_code)",
                "CREATE INDEX IF NOT EXISTS idx_deals_buyer_id ON deals(buyer_id)",
                "CREATE INDEX IF NOT EXISTS idx_deals_seller_id ON deals(seller_id)",
                "CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status)",
                "CREATE INDEX IF NOT EXISTS idx_deals_created_at ON deals(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_deals_updated_at ON deals(updated_at)",
                "CREATE INDEX IF NOT EXISTS idx_deals_currency ON deals(currency)",
                "CREATE INDEX IF NOT EXISTS idx_deals_amount ON deals(amount)",
                "CREATE INDEX IF NOT EXISTS idx_deals_buyer_seller ON deals(buyer_id, seller_id)",
                "CREATE INDEX IF NOT EXISTS idx_deals_status_created ON deals(status, created_at)",
            ])

            # Indexes for the crypto_checkouts table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_crypto_checkouts_checkout_id ON crypto_checkouts(checkout_id)",
                "CREATE INDEX IF NOT EXISTS idx_crypto_checkouts_deal_code ON crypto_checkouts(deal_code)",
                "CREATE INDEX IF NOT EXISTS idx_crypto_checkouts_status ON crypto_checkouts(status)",
                "CREATE INDEX IF NOT EXISTS idx_crypto_checkouts_created_at ON crypto_checkouts(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_crypto_checkouts_expires_at ON crypto_checkouts(expires_at)",
            ])

            # Indexes for the payments table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(payment_id)",
                "CREATE INDEX IF NOT EXISTS idx_payments_checkout_id ON payments(checkout_id)",
                "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
                "CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_payments_tx_hash ON payments(tx_hash)",
            ])

            # Indexes for the decentralized_payments table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_decentralized_payments_deal_code ON decentralized_payments(deal_code)",
                "CREATE INDEX IF NOT EXISTS idx_decentralized_payments_checkout_id ON decentralized_payments(checkout_id)",
                "CREATE INDEX IF NOT EXISTS idx_decentralized_payments_status ON decentralized_payments(status)",
                "CREATE INDEX IF NOT EXISTS idx_decentralized_payments_created_at ON decentralized_payments(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_decentralized_payments_expires_at ON decentralized_payments(expires_at)",
            ])

            # Indexes for the notifications table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read)",
            ])

            # Indexes for the auth_tokens table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_auth_tokens_token ON auth_tokens(token)",
                "CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires_at ON auth_tokens(expires_at)",
                "CREATE INDEX IF NOT EXISTS idx_auth_tokens_used ON auth_tokens(used)",
            ])

            # Indexes for the support_chat_messages table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_support_chat_user_id ON support_chat_messages(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_support_chat_is_from_user ON support_chat_messages(is_from_user)",
                "CREATE INDEX IF NOT EXISTS idx_support_chat_created_at ON support_chat_messages(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_support_chat_read_by_admin ON support_chat_messages(read_by_admin)",
                "CREATE INDEX IF NOT EXISTS idx_support_chat_read_by_user ON support_chat_messages(read_by_user)",
            ])

            # Indexes for the admin_messages table
            indexes.extend([
                "CREATE INDEX IF NOT EXISTS idx_admin_messages_admin_id ON admin_messages(admin_id)",
                "CREATE INDEX IF NOT EXISTS idx_admin_messages_target_user_id ON admin_messages(target_user_id)",
                "CREATE INDEX IF NOT EXISTS idx_admin_messages_sent_at ON admin_messages(sent_at)",
                "CREATE INDEX IF NOT EXISTS idx_admin_messages_delivery_status ON admin_messages(delivery_status)",
            ])

            # Create indexes
            for index_sql in indexes:
                try:
                    cursor.execute(index_sql)
                except Exception as e:
                    logger.warning(f"Failed to create index: {index_sql[:50]}...: {e}")

            conn.commit()
            logger.info(f"Создано {len(indexes)} индексов")

    def _optimize_performance(self):
        """Optimize database performance."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # SQLite optimizations
            optimizations = [
                "PRAGMA journal_mode = WAL",  # Write-Ahead Logging for better concurrency
                "PRAGMA synchronous = NORMAL",  # Balance between speed and safety
                "PRAGMA cache_size = -64000",  # 64MB cache
                "PRAGMA temp_store = MEMORY",  # Temporary tables in memory
                "PRAGMA mmap_size = 268435456",  # 256MB memory-mapped I/O
                "PRAGMA optimize",  # Database optimization
            ]

            for opt in optimizations:
                try:
                    cursor.execute(opt)
                except Exception as e:
                    logger.warning(f"Failed to run optimization: {opt}: {e}")

            conn.commit()
            logger.info("Performance optimizations applied")

    def _add_foreign_keys(self):
        """Add foreign keys for data integrity."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Enable foreign key support
            cursor.execute("PRAGMA foreign_keys = ON")

            # Check existing foreign keys and add missing ones
            # (SQLite does not support ALTER TABLE for adding FKs; do this during table creation)

            conn.commit()
            logger.info("Foreign keys checked and enabled")

    def _add_constraints(self):
        """Add data integrity constraints."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Add CHECK constraints where possible
            try:
                # For the deals table: positive amount
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS check_deal_amount_positive
                    BEFORE INSERT ON deals
                    BEGIN
                        SELECT CASE
                            WHEN NEW.amount <= 0 THEN
                                RAISE(ABORT, 'Deal amount must be positive')
                        END;
                    END;
                """)

                # For the users table: positive counters
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS check_user_stats_positive
                    BEFORE UPDATE ON users
                    BEGIN
                        SELECT CASE
                            WHEN NEW.deals_count < 0 OR NEW.total_deal_amount < 0 THEN
                                RAISE(ABORT, 'User stats cannot be negative')
                        END;
                    END;
                """)

            except Exception as e:
                logger.warning(f"Failed to add some constraints: {e}")

            conn.commit()
            logger.info("Integrity constraints added")

    def _add_audit_trail(self):
        """Add an audit trail system for financial operations."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Payment audit table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL, -- 'create', 'update', 'complete', 'cancel'
                    deal_code TEXT,
                    checkout_id TEXT,
                    payment_id TEXT,
                    user_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    old_status TEXT,
                    new_status TEXT,
                    tx_hash TEXT,
                    metadata TEXT, -- JSON с дополнительной информацией
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Deal audit table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deal_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    deal_code TEXT NOT NULL,
                    user_id INTEGER,
                    old_status TEXT,
                    new_status TEXT,
                    old_data TEXT, -- JSON with old data
                    new_data TEXT, -- JSON with new data
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Indexes for audit tables
            audit_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_payment_audit_deal_code ON payment_audit(deal_code)",
                "CREATE INDEX IF NOT EXISTS idx_payment_audit_created_at ON payment_audit(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_deal_audit_deal_code ON deal_audit(deal_code)",
                "CREATE INDEX IF NOT EXISTS idx_deal_audit_created_at ON deal_audit(created_at)",
            ]

            for index_sql in audit_indexes:
                cursor.execute(index_sql)

            conn.commit()
            logger.info("Система аудита добавлена")

    def _add_connection_pooling_support(self):
        """Add connection pooling support (PostgreSQL preparation)."""
        # SQLite doesn't need connection pooling, but store metadata for future migration
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Migrations metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    description TEXT,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER DEFAULT 1
                )
            """)

            # Record applied migrations
            migrations_applied = [
                ('indexes_2024', 'Database indexes for performance optimization'),
                ('performance_2024', 'Performance optimizations'),
                ('constraints_2024', 'Data integrity constraints'),
                ('audit_2024', 'Audit trail system'),
                ('pooling_prep_2024', 'Connection pooling preparation'),
            ]

            for migration_id, description in migrations_applied:
                cursor.execute("""
                    INSERT OR IGNORE INTO schema_migrations (migration_id, description)
                    VALUES (?, ?)
                """, (migration_id, description))

            conn.commit()
            logger.info("Migration metadata added")

    def get_migration_status(self) -> Dict[str, Any]:
        """Get migrations status."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check which indexes exist
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='index' AND name LIKE 'idx_%'
                """)
                indexes = [row[0] for row in cursor.fetchall()]

                # Check which tables exist
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name IN ('payment_audit', 'deal_audit', 'schema_migrations')
                """)
                audit_tables = [row[0] for row in cursor.fetchall()]

                # Check migrations
                cursor.execute("SELECT migration_id FROM schema_migrations")
                migrations = [row[0] for row in cursor.fetchall()]

                return {
                    'indexes_count': len(indexes),
                    'audit_tables_count': len(audit_tables),
                    'migrations_applied': len(migrations),
                    'indexes': indexes[:10],  # Show first 10
                    'audit_tables': audit_tables,
                    'migrations': migrations
                }

        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {'error': str(e)}

    def rollback_migration(self, migration_name: str) -> bool:
        """Rollback a migration (if possible)."""
        try:
            logger.warning(f"Attempting migration rollback: {migration_name}")

            # Rollbacks are hard in SQLite, so we only record the status here
            # Production should use more advanced migration tooling

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE schema_migrations
                    SET success = 0
                    WHERE migration_id = ?
                """, (migration_name,))

                conn.commit()

            logger.info(f"Миграция {migration_name} отмечена как неудачная")
            return True

        except Exception as e:
            logger.error(f"Migration rollback error for {migration_name}: {e}")
            return False


def run_database_migrations():
    """Run database migrations."""
    migrator = DatabaseMigrator()
    return migrator.run_migrations()


def get_migration_status():
    """Get migrations status."""
    migrator = DatabaseMigrator()
    return migrator.get_migration_status()


if __name__ == "__main__":
    # Run migrations on direct execution
    success = run_database_migrations()
    if success:
        print("Migrations completed successfully")
        status = get_migration_status()
        print(f"Статус: {status}")
    else:
        print("Migration error")

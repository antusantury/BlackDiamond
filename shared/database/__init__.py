from .validators import sanitize_input, validate_deal_code, validate_user_input
from .errors import (
    DatabaseError,
    ValidationError,
    ConnectionError,
    TransactionError,
    handle_database_error,
    log_and_reraise,
    DatabaseMetrics
)

# Import Database class - try legacy first, then refactored
try:
    # Import from the database module in the same directory
    from .database import Database, db
    print("Successfully imported real database with token validation")
except ImportError as e:
    print(f"Warning: Could not import from .database: {e}")
    # Fallback to refactored database if legacy version not available
    try:
        from ..database_refactored import Database as RealDatabase, db as real_db
        # Use the real database class and instance
        Database = RealDatabase
        db = real_db
    except ImportError as e:
        print(f"Warning: Could not import from .database_refactored: {e}")
        # Create dummy instances if both imports fail
        class Database:
            def get_stats(self):
                return {'users_count': 0, 'deals_count': 0, 'active_deals': 0, 'completed_deals': 0, 'total_volume': 0}

        class DummyDB:
            def get_user(self, user_id):
                return {'user_id': user_id, 'username': f'user_{user_id}', 'first_name': 'User', 'language': 'en'}

            def get_deal(self, deal_code):
                return None

            def create_user(self, user_id, username=None, first_name=None):
                return True

            def update_user(self, user_id, **kwargs):
                return True

            def get_user_language(self, user_id):
                return 'en'

            def set_user_language(self, user_id, lang):
                return True

            def get_user_stats(self, user_id):
                return {'total_deals': 0, 'completed_deals': 0, 'active_deals': 0, 'total_volume': 0, 'success_rate': 0}

            def get_user_achievements(self, user_id):
                return []

            def get_all_users(self, **kwargs):
                return []

            def get_users_count(self, **kwargs):
                return 0

            def ban_user(self, user_id, ban):
                return True

            def get_admin_messages_history(self, **kwargs):
                return []

            def save_admin_message(self, *args):
                return True

            def get_all_deals(self, **kwargs):
                return []

            def get_deals_count(self, **kwargs):
                return 0

            def get_user_deals(self, user_id):
                return []

            def get_user_notifications(self, user_id):
                return []

            def mark_notification_read(self, *args):
                return True

            def mark_all_notifications_read(self, user_id):
                return 0

            def delete_all_notifications(self, user_id):
                return 0

            def delete_multiple_notifications(self, user_id, ids):
                return 0

            def get_unread_notifications_count(self, user_id):
                return 0

            def create_deal(self, *args):
                return True

            def join_deal(self, *args):
                return True

            def update_deal_status(self, *args):
                return True

            def save_support_message(self, *args):
                return True

            def get_support_messages(self, user_id):
                return []

            def get_unread_support_messages_count(self, *args):
                return 0

            def mark_support_messages_read(self, *args):
                return True

            def get_all_support_conversations(self):
                return []

            def get_admin_analytics(self, period):
                return {}

            def get_stats(self):
                return {'users_count': 0, 'deals_count': 0, 'active_deals': 0, 'completed_deals': 0, 'total_volume': 0}

            def get_settings(self):
                return {'commission_rate': 0.05}

            def update_settings(self, **kwargs):
                return True

            def create_auth_token(self, user_id):
                """Create a dummy auth token for the given user_id.

                This is a stand-in implementation used by tests and local/dev runs
                when the full database/token storage is not available.
                """
                try:
                    import secrets
                    import string
                    from shared.constants import TOKEN_LENGTH

                    # Generate cryptographically secure token
                    alphabet = string.ascii_letters + string.digits
                    return ''.join(secrets.choice(alphabet) for _ in range(TOKEN_LENGTH))
                except Exception:
                    return None

            def validate_auth_token(self, token):
                return None

            def get_crypto_checkout(self, checkout_id):
                return None

            def get_crypto_checkout_by_deal(self, deal_code):
                return None

            def check_rate_limit(self, *args):
                return True

        db = DummyDB()

__all__ = [
    # Validators
    'sanitize_input',
    'validate_deal_code',
    'validate_user_input',
    
    # Error handling
    'DatabaseError',
    'ValidationError',
    'ConnectionError',
    'TransactionError',
    'handle_database_error',
    'log_and_reraise',
    'DatabaseMetrics',
    
    # Database class and instance
    'Database',
    'db'
]

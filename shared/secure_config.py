import os
import json
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import secrets
import logging

logger = logging.getLogger(__name__)


class SecureVault:
    """Secure vault for sensitive data."""

    def __init__(self, vault_file: str = ".vault.enc", key_file: str = ".vault.key"):
        self.vault_file = vault_file
        self.key_file = key_file
        self._cipher = None
        self._secrets = {}
        self._initialize_vault()

    def _initialize_vault(self):
        """Initialize the vault with automatic key generation."""
        try:
            # Check or generate the encryption key
            if not os.path.exists(self.key_file):
                self._generate_encryption_key()

            # Load the key and initialize the cipher
            with open(self.key_file, 'rb') as f:
                key = f.read()

            self._cipher = Fernet(key)

            # Load or create the vault
            if os.path.exists(self.vault_file):
                self._load_vault()
            else:
                self._secrets = {}
                self._save_vault()

        except Exception as e:
            logger.error(f"Vault initialization error: {e}")
            raise RuntimeError(f"Failed to initialize secure storage: {e}")

    def _generate_encryption_key(self):
        """Generate an encryption key."""
        # Use PBKDF2 to derive a key from random salt
        salt = secrets.token_bytes(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        # Generate a random password
        password = secrets.token_hex(32).encode()

        key = base64.urlsafe_b64encode(kdf.derive(password))

        # Save the key
        with open(self.key_file, 'wb') as f:
            f.write(key)

        logger.info("Generated a new encryption key for vault")

    def _load_vault(self):
        """Load encrypted secrets."""
        try:
            with open(self.vault_file, 'rb') as f:
                encrypted_data = f.read()

            if encrypted_data:
                decrypted_data = self._cipher.decrypt(encrypted_data)
                self._secrets = json.loads(decrypted_data.decode('utf-8'))
            else:
                self._secrets = {}

        except Exception as e:
            logger.error(f"Vault load error: {e}")
            self._secrets = {}

    def _save_vault(self):
        """Save encrypted secrets."""
        try:
            data = json.dumps(self._secrets, ensure_ascii=False)
            encrypted_data = self._cipher.encrypt(data.encode('utf-8'))

            with open(self.vault_file, 'wb') as f:
                f.write(encrypted_data)

        except Exception as e:
            logger.error(f"Vault save error: {e}")
            raise

    def set_secret(self, key: str, value: str, category: str = "general"):
        """Safely store a secret."""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Invalid secret key")

        if not isinstance(value, str):
            value = str(value)

        # Ensure this is not a placeholder
        if self._is_placeholder(value):
            logger.warning(f"Attempted to save a placeholder as a secret: {key}")
            return False

        self._secrets[key] = {
            'value': value,
            'category': category,
            'created_at': self._get_timestamp(),
            'updated_at': self._get_timestamp()
        }

        self._save_vault()
        logger.info(f"Saved secret: {key} (category: {category})")
        return True

    def get_secret(self, key: str, default: str = None) -> Optional[str]:
        """Get a secret."""
        secret_data = self._secrets.get(key)
        if secret_data:
            return secret_data['value']
        return default

    def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        if key in self._secrets:
            del self._secrets[key]
            self._save_vault()
            logger.info(f"Deleted secret: {key}")
            return True
        return False

    def list_secrets(self, category: str = None) -> Dict[str, Dict[str, Any]]:
        """List secret keys (without values)."""
        result = {}
        for key, data in self._secrets.items():
            if category is None or data.get('category') == category:
                result[key] = {
                    'category': data.get('category'),
                    'created_at': data.get('created_at'),
                    'updated_at': data.get('updated_at')
                }
        return result

    def _is_placeholder(self, value: str) -> bool:
        """Check whether a value is a placeholder."""
        placeholders = [
            'your_', 'example', 'test', 'dummy', 'placeholder',
            'change_me', 'replace_with', 'fill_in', 'not_set'
        ]

        value_lower = value.lower().strip()
        return any(placeholder in value_lower for placeholder in placeholders)

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        return datetime.now(timezone.utc).isoformat()

    def rotate_key(self):
        """Rotate the encryption key."""
        try:
            logger.info("Started encryption key rotation")

            # Create a new key
            self._generate_encryption_key()

            # Re-encrypt data
            with open(self.key_file, 'rb') as f:
                new_key = f.read()

            new_cipher = Fernet(new_key)

            # Re-encrypt the vault
            data = json.dumps(self._secrets, ensure_ascii=False)
            encrypted_data = new_cipher.encrypt(data.encode('utf-8'))

            with open(self.vault_file, 'wb') as f:
                f.write(encrypted_data)

            self._cipher = new_cipher

            logger.info("Encryption key rotated successfully")

        except Exception as e:
            logger.error(f"Key rotation error: {e}")
            raise


class SecureConfig:
    """Secure configuration system."""

    def __init__(self):
        self.vault = SecureVault()
        self._env_cache = {}
        self._load_env_config()

    def _load_env_config(self):
        """Load configuration from a .env file."""
        try:
            from dotenv import load_dotenv
            load_dotenv()

            # Cache environment variables
            self._env_cache = dict(os.environ)

        except ImportError:
            logger.warning("python-dotenv is not installed; skipping .env loading")
            self._env_cache = dict(os.environ)

    def get(self, key: str, default: Any = None, secure: bool = False) -> Any:
        """Get a configuration value."""
        # Check the vault first (for secrets)
        if secure:
            value = self.vault.get_secret(key)
            if value is not None:
                return value

        # Then check environment variables
        value = self._env_cache.get(key)
        if value is not None:
            return value

        # Finally, return the default
        return default

    def set(self, key: str, value: Any, secure: bool = False, category: str = "general"):
        """Set a configuration value."""
        if secure:
            # Save to the vault
            success = self.vault.set_secret(key, str(value), category)
            if success:
                # Also update .env for compatibility
                self._update_env_file(key, str(value))
            return success
        else:
            # Save to environment variables and .env
            os.environ[key] = str(value)
            self._env_cache[key] = str(value)
            self._update_env_file(key, str(value))
            return True

    def _update_env_file(self, key: str, value: str):
        """Update the .env file."""
        try:
            env_file = '.env'
            lines = []

            # Read existing file
            if os.path.exists(env_file):
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

            # Find and update the line
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f'{key}='):
                    lines[i] = f'{key}={value}\n'
                    updated = True
                    break

            # If not found, add a new line
            if not updated:
                lines.append(f'{key}={value}\n')

            # Write back
            with open(env_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)

        except Exception as e:
            logger.error(f".env update error: {e}")

    def migrate_secrets_to_vault(self):
        """Migrate existing secrets into the vault."""
        try:
            logger.info("Started secret migration to secure storage")

            # List of secret keys to migrate
            secret_keys = {
                'BOT_TOKEN': 'telegram',
                'ADMIN_ID': 'telegram',
                'TRONGRID_API_KEY': 'blockchain',
                'TONCENTER_API_KEY': 'blockchain',
                'USDT_WALLET_ADDRESS': 'wallet',
                'USDT_PRIVATE_KEY': 'wallet',
                'TON_WALLET_ADDRESS': 'wallet',
                'TON_PRIVATE_KEY': 'wallet',
                'SECRET_KEY': 'security',
                'SESSION_SECRET': 'security',
                'DATABASE_URL': 'database'
            }

            migrated_count = 0

            for key, category in secret_keys.items():
                value = self._env_cache.get(key)
                if value and not self._is_placeholder(value):
                    # Save into the vault
                    self.vault.set_secret(key, value, category)
                    migrated_count += 1
                    logger.info(f"Migrated secret: {key}")

            logger.info(f"Migration completed: moved {migrated_count} secrets")

            # Create a backup of the .env file
            self._backup_env_file()

            return migrated_count

        except Exception as e:
            logger.error(f"Secret migration error: {e}")
            return 0

    def _backup_env_file(self):
        """Create a backup of the .env file."""
        try:
            import shutil
            backup_file = '.env.backup'
            if os.path.exists('.env'):
                shutil.copy2('.env', backup_file)
                logger.info("Created .env backup")
        except Exception as e:
            logger.error(f"Backup creation error: {e}")

    def _is_placeholder(self, value: str) -> bool:
        """Check for placeholders."""
        return self.vault._is_placeholder(value)

    def get_security_status(self) -> Dict[str, Any]:
        """Get configuration security status."""
        status = {
            'vault_initialized': True,
            'secrets_migrated': False,
            'placeholders_found': [],
            'security_score': 0
        }

        # Check for placeholders
        secret_keys = [
            'BOT_TOKEN', 'ADMIN_ID', 'TRONGRID_API_KEY', 'TONCENTER_API_KEY',
            'USDT_PRIVATE_KEY', 'TON_PRIVATE_KEY', 'SECRET_KEY', 'SESSION_SECRET'
        ]

        for key in secret_keys:
            value = self.get(key, secure=True)
            if value and self._is_placeholder(value):
                status['placeholders_found'].append(key)

        # Check migration
        migrated_secrets = self.vault.list_secrets()
        if migrated_secrets:
            status['secrets_migrated'] = True

        # Calculate security score
        score = 0
        if status['secrets_migrated']:
            score += 40
        if not status['placeholders_found']:
            score += 40
        if os.path.exists('.vault.key'):
            score += 20

        status['security_score'] = score

        return status


# Global secure configuration instance
secure_config = SecureConfig()


def migrate_to_secure_config():
    """Migrate to secure configuration."""
    try:
        logger.info("Starting secure configuration migration")

        # Migrate secrets
        migrated = secure_config.migrate_secrets_to_vault()

        # Get security status
        status = secure_config.get_security_status()

        logger.info(f"Migration completed. Secrets moved: {migrated}")
        logger.info(f"Security status: {status['security_score']}/100")

        if status['placeholders_found']:
            logger.warning(f"Found placeholders: {', '.join(status['placeholders_found'])}")

        return True

    except Exception as e:
        logger.error(f"Secure config migration error: {e}")
        return False


# Compatibility functions for backward compatibility
def get_secure_config(key: str, default: Any = None) -> Any:
    """Get secure configuration (compatibility helper)."""
    return secure_config.get(key, default, secure=True)


def set_secure_config(key: str, value: Any, category: str = "general"):
    """Set secure configuration (compatibility helper)."""
    return secure_config.set(key, value, secure=True, category=category)

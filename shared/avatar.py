import logging
import os
import aiohttp
from aiogram import Bot
from aiogram.types import User
from shared.database import db

logger = logging.getLogger(__name__)


class AvatarManager:
    """Handles retrieving and persisting Telegram user avatars."""

    def __init__(self, bot: Bot = None):
        self.bot = bot

    def set_bot(self, bot: Bot):
        """Inject a ready Bot instance to reuse session."""
        self.bot = bot

    async def get_user_avatar_url(self, user: User) -> str:
        """
        Download the user's largest Telegram profile photo and
        return a local static URL path that the web app can serve.
        Returns empty string if no photo is available or on failure.
        """
        try:
            # Ensure bot instance exists
            if not self.bot:
                from shared.config import BOT_TOKEN
                if not BOT_TOKEN:
                    logger.error("BOT_TOKEN not configured")
                    return ""
                from aiogram import Bot
                self.bot = Bot(token=BOT_TOKEN)

            # Try standard API to get profile photos
            profile_photos = await self.bot.get_user_profile_photos(user.id, limit=1)
            file = None
            if profile_photos and profile_photos.photos:
                # Pick the largest size variant
                photo_sizes = profile_photos.photos[0]
                largest_photo = photo_sizes[-1]
                file = await self.bot.get_file(largest_photo.file_id)
            else:
                # Fallback: try via get_chat -> chat.photo (covers video avatars and edge cases)
                try:
                    chat = await self.bot.get_chat(user.id)
                    if getattr(chat, 'photo', None):
                        file_id = getattr(chat.photo, 'big_file_id', None) or getattr(chat.photo, 'small_file_id', None)
                        if file_id:
                            file = await self.bot.get_file(file_id)
                        else:
                            logger.info(f"Chat photo exists but no file_id for user {user.id}")
                    else:
                        logger.info(f"No profile photo found for user {user.id}")
                except Exception as e:
                    logger.info(f"get_chat fallback failed for user {user.id}: {e}")

            if not file:
                return ""

            # Build Telegram download URL WITH full token (required by Telegram)
            # Note: We will download server-side and serve locally to avoid exposing token.
            download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

            # Prepare local target path under static/avatars
            # Get the project root directory
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            avatars_dir = os.path.join(project_root, 'static', 'avatars')
            logger.info(f"[AVATAR DEBUG] Project root: {project_root}")
            logger.info(f"[AVATAR DEBUG] Avatars directory: {avatars_dir}")
            logger.info(f"[AVATAR DEBUG] Avatars directory exists: {os.path.exists(avatars_dir)}")
            os.makedirs(avatars_dir, exist_ok=True)

            ext = os.path.splitext(file.file_path)[1] or '.jpg'
            filename = f"{user.id}{ext}"
            target_path = os.path.join(avatars_dir, filename)

            # Download and save
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(verify_ssl=False)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(download_url) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to download avatar for user {user.id}: HTTP {resp.status}")
                        return ""
                    content = await resp.read()
                    with open(target_path, 'wb') as f:
                        f.write(content)

            web_path = f"/static/avatars/{filename}"
            logger.info(f"Saved avatar for user {user.id} to {web_path}")
            return web_path

        except Exception as e:
            logger.error(f"Error getting avatar for user {user.id}: {e}")
            return ""

    async def update_user_avatar(self, user: User) -> bool:
        """
        Fetch avatar and persist its local URL into DB. Clears field if absent.
        """
        bot_created_here = False
        try:
            if not self.bot:
                bot_created_here = True

            avatar_url = await self.get_user_avatar_url(user)
            if avatar_url:
                success = db.set_user_avatar(user.id, avatar_url)
                if success:
                    logger.info(f"Updated avatar for user {user.id}")
                    return True
                logger.error(f"Failed to save avatar URL to database for user {user.id}")
                return False
            else:
                # No avatar available — clear stored value
                success = db.set_user_avatar(user.id, "")
                logger.info(f"Cleared avatar for user {user.id} (no avatar found)")
                return success

        except Exception as e:
            logger.error(f"Error updating avatar for user {user.id}: {e}")
            return False
        finally:
            # Close the session if we created a temporary bot instance
            if bot_created_here and self.bot:
                try:
                    await self.bot.session.close()
                    self.bot = None
                except Exception as e:
                    logger.warning(f"Error closing temporary bot session: {e}")


# Shared singleton
avatar_manager = AvatarManager()

def initialize_avatar_system(bot=None):
    """Initialize the avatar system with a bot instance"""
    if bot:
        avatar_manager.set_bot(bot)
        logger.info("Avatar system initialized with bot instance")
    else:
        logger.warning("No bot instance provided for avatar system initialization")

# Create avatars directory at module import
def ensure_avatars_directory():
    """Ensure the avatars directory exists"""
    # Go up one level from shared/ to project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    avatars_dir = os.path.join(project_root, 'static', 'avatars')
    os.makedirs(avatars_dir, exist_ok=True)
    logger.info(f"Avatars directory ensured at: {avatars_dir}")
    return avatars_dir

# Initialize avatars directory
try:
    ensure_avatars_directory()
except Exception as e:
    logger.error(f"Failed to create avatars directory: {e}")

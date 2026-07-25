import logging
import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from shared.database import db
from shared.localization import localization

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseMiddleware):
    """Performs basic security checks and blocks banned users."""

    def __init__(self):
        super().__init__()
        self._alt_db_paths = self._discover_alt_db_paths()

    def _discover_alt_db_paths(self):
        try:
            primary = Path(db.db_path).resolve()
            project_root = Path(__file__).resolve().parents[2]
            candidates = [
                project_root / "black_diamond.db",
                project_root / "web" / "black_diamond.db"
            ]
            return [path for path in candidates if path.exists() and path.resolve() != primary]
        except Exception:
            return []

    def _is_banned_in_alt_dbs(self, user_id: int):
        for path in self._alt_db_paths:
            try:
                conn = sqlite3.connect(str(path))
                cursor = conn.cursor()
                cursor.execute("SELECT is_banned, language FROM users WHERE user_id = ? LIMIT 1", (user_id,))
                row = cursor.fetchone()
                conn.close()
                if row and row[0]:
                    language = row[1] or 'en'
                    return True, language
            except Exception:
                continue
        return False, 'en'

    async def _block_if_banned(self, event: Message | CallbackQuery) -> None:
        user_id = event.from_user.id if getattr(event, "from_user", None) else None
        if not user_id:
            return

        user = db.get_user(user_id)
        is_banned = bool(user and user.get("is_banned"))
        language = (user.get("language") if user else None) or "en"

        if not is_banned:
            is_banned, alt_language = self._is_banned_in_alt_dbs(user_id)
            if is_banned:
                language = alt_language

        if not is_banned:
            return

        logger.info(f"Blocked update from banned user {user_id}")
        ban_text = localization.get_text("account_banned", language)

        if isinstance(event, Message):
            try:
                await event.answer(ban_text, reply_markup=ReplyKeyboardRemove())
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(ban_text, show_alert=True)
            except Exception:
                pass

        raise CancelHandler()

    async def _basic_checks(self, event: Message | CallbackQuery) -> None:
        if isinstance(event, Message):
            if event.text and len(event.text) > 4096:
                user_id = event.from_user.id if event.from_user else "unknown"
                logger.warning(f"Message too long from user {user_id}")
                raise CancelHandler()

            suspicious_patterns = ["<script", "javascript:", "onload=", "onclick="]
            if event.text and any(pattern in event.text.lower() for pattern in suspicious_patterns):
                user_id = event.from_user.id if event.from_user else "unknown"
                logger.warning(f"Suspicious content detected from user {user_id}")

        elif isinstance(event, CallbackQuery):
            if event.data and len(event.data) > 64:
                user_id = event.from_user.id if event.from_user else "unknown"
                logger.warning(f"Callback data too long from user {user_id}")
                raise CancelHandler()

    # aiogram 2.x middleware hooks
    async def on_pre_process_message(self, message: Message, data: Dict[str, Any]):
        await self._block_if_banned(message)
        await self._basic_checks(message)

    async def on_pre_process_callback_query(self, callback: CallbackQuery, data: Dict[str, Any]):
        await self._block_if_banned(callback)
        await self._basic_checks(callback)

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Process incoming updates with security checks."""
        try:
            await self._block_if_banned(event)
            await self._basic_checks(event)

            # Proceed with handler
            return await handler(event, data)

        except CancelHandler:
            raise
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            # Don't block the handler, just log the error
            return await handler(event, data)

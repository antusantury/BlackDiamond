import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Logs incoming updates and handler duration."""

    def __init__(self):
        super().__init__()

    def _log_incoming(self, event: Message | CallbackQuery) -> None:
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else "unknown"
            chat_id = event.chat.id if event.chat else "unknown"
            message_type = (
                "text"
                if event.text
                else ("photo" if event.photo else ("document" if event.document else "other"))
            )
            logger.info(f"📨 Message from user {user_id} in chat {chat_id}: {message_type}")
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else "unknown"
            callback_data = event.data or ""
            data_preview = (callback_data[:50] + "...") if len(callback_data) > 50 else callback_data
            logger.info(f"🔘 Callback from user {user_id}: {data_preview}")

    # aiogram 2.x middleware hooks
    async def on_pre_process_message(self, message: Message, data: Dict[str, Any]):
        data["_logging_mw_start_time"] = time.time()
        self._log_incoming(message)

    async def on_pre_process_callback_query(self, callback: CallbackQuery, data: Dict[str, Any]):
        data["_logging_mw_start_time"] = time.time()
        self._log_incoming(callback)

    async def on_post_process_message(self, message: Message, results: Any, data: Dict[str, Any]):
        start_time = data.get("_logging_mw_start_time")
        if isinstance(start_time, (int, float)):
            logger.debug(f"⚡ Handler executed in {time.time() - start_time:.3f}s")

    async def on_post_process_callback_query(self, callback: CallbackQuery, results: Any, data: Dict[str, Any]):
        start_time = data.get("_logging_mw_start_time")
        if isinstance(start_time, (int, float)):
            logger.debug(f"⚡ Handler executed in {time.time() - start_time:.3f}s")

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Process incoming updates with logging."""
        start_time = time.time()

        try:
            self._log_incoming(event)

            # Execute handler
            result = await handler(event, data)

            # Log execution time
            execution_time = time.time() - start_time
            logger.debug(f"⚡ Handler executed in {execution_time:.3f}s")

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Handler failed after {execution_time:.3f}s: {e}")
            raise

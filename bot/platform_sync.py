import logging
import threading
from typing import Any, Dict, Optional

from shared.platform_sync import (
    cross_platform_sync,
    notify_deal_created,
    notify_deal_joined,
    notify_deal_status_changed,
    notify_payment_received,
)

logger = logging.getLogger(__name__)


class BotCrossPlatformIntegration:
    """Integration layer for bot to communicate with cross-platform sync system."""

    def __init__(self):
        self._active_sessions: Dict[int, str] = {}

    def create_session_for_user(self, user_id: int) -> str:
        session_id = cross_platform_sync.create_session(user_id, "bot")
        self._active_sessions[user_id] = session_id
        logger.info("Created bot sync session %s for user %s", session_id, user_id)
        return session_id

    def get_session_for_user(self, user_id: int) -> Optional[str]:
        return self._active_sessions.get(user_id)

    def subscribe_to_deal(self, user_id: int, deal_code: str) -> bool:
        session_id = self.get_session_for_user(user_id) or self.create_session_for_user(user_id)
        success = cross_platform_sync.subscribe_to_deal(session_id, deal_code)
        if success:
            logger.info("User %s subscribed to deal %s", user_id, deal_code)
        return success

    def unsubscribe_from_deal(self, user_id: int, deal_code: str) -> bool:
        session_id = self.get_session_for_user(user_id)
        if not session_id:
            return False
        success = cross_platform_sync.unsubscribe_from_deal(session_id, deal_code)
        if success:
            logger.info("User %s unsubscribed from deal %s", user_id, deal_code)
        return success

    def remove_user_session(self, user_id: int) -> None:
        session_id = self._active_sessions.get(user_id)
        if not session_id:
            return
        cross_platform_sync.remove_session(session_id)
        del self._active_sessions[user_id]
        logger.info("Removed bot sync session for user %s", user_id)

    async def notify_deal_created_from_bot(self, deal_code: str, user_id: int, deal_data: Dict[str, Any]):
        await notify_deal_created(
            deal_code=deal_code,
            user_id=user_id,
            platform="bot",
            deal_data=deal_data,
        )

    async def notify_deal_joined_from_bot(self, deal_code: str, user_id: int, deal_data: Dict[str, Any]):
        await notify_deal_joined(
            deal_code=deal_code,
            user_id=user_id,
            platform="bot",
            deal_data=deal_data,
        )

    async def notify_deal_status_changed_from_bot(
        self,
        deal_code: str,
        user_id: int,
        old_status: str,
        new_status: str,
    ):
        await notify_deal_status_changed(
            deal_code=deal_code,
            user_id=user_id,
            platform="bot",
            old_status=old_status,
            new_status=new_status,
        )

    async def notify_payment_received_from_bot(self, deal_code: str, user_id: int, payment_data: Dict[str, Any]):
        await notify_payment_received(
            deal_code=deal_code,
            user_id=user_id,
            platform="bot",
            payment_data=payment_data,
        )


bot_integration = BotCrossPlatformIntegration()


async def init_bot_cross_platform_sync():
    """Initialize cross-platform sync for bot."""
    try:
        await cross_platform_sync.start_sync()
        logger.info("Bot cross-platform synchronization initialized")
    except Exception as e:
        logger.error("Failed to initialize bot cross-platform sync: %s", e)


def _init_sync_in_thread():
    """Initialize sync in a separate thread to avoid event loop issues."""
    try:
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_bot_cross_platform_sync())
        loop.close()
    except Exception as e:
        logger.warning("Could not initialize bot cross-platform sync in thread: %s", e)


try:
    import asyncio

    if threading.current_thread() is threading.main_thread():
        try:
            asyncio.get_running_loop()
            asyncio.create_task(init_bot_cross_platform_sync())
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(init_bot_cross_platform_sync())
                else:
                    asyncio.create_task(init_bot_cross_platform_sync())
            except RuntimeError:
                logger.info("Skipping auto-initialization: no event loop available")
    else:
        init_thread = threading.Thread(target=_init_sync_in_thread, daemon=True)
        init_thread.start()
except Exception as e:
    logger.warning("Could not auto-initialize bot cross-platform sync: %s", e)

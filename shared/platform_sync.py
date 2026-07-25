import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import threading
import time

from shared.notifications import notification_manager

logger = logging.getLogger(__name__)


@dataclass
class SyncEvent:
    """Represents a synchronization event"""
    event_type: str  # 'deal_created', 'deal_joined', 'deal_status_changed', etc.
    deal_code: str
    user_id: int
    platform: str  # 'bot' or 'web'
    timestamp: datetime
    data: Dict[str, Any]
    event_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class SyncSession:
    """Represents a user's synchronization session"""
    user_id: int
    platform: str
    session_id: str
    connected_at: datetime
    last_activity: datetime
    subscribed_deals: Set[str]


class CrossPlatformSync:
    """
    Main synchronization system for cross-platform deal operations
    """

    def __init__(self):
        self._active_sessions: Dict[str, SyncSession] = {}
        self._deal_subscriptions: Dict[str, Set[str]] = {}  # deal_code -> set of session_ids
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None

        # Register event handlers
        self._register_event_handlers()

    def _register_event_handlers(self):
        """Register handlers for different sync events"""
        self.register_event_handler('deal_created', self._handle_deal_created)
        self.register_event_handler('deal_joined', self._handle_deal_joined)
        self.register_event_handler('deal_status_changed', self._handle_deal_status_changed)
        self.register_event_handler('payment_received', self._handle_payment_received)

    async def start_sync(self):
        """Start the synchronization system"""
        if self._running:
            return

        self._running = True
        self._sync_thread = threading.Thread(target=self._run_sync_loop, daemon=True)
        self._sync_thread.start()

        logger.info("Cross-platform synchronization started")

    def stop_sync(self):
        """Stop the synchronization system"""
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=5)

        logger.info("Cross-platform synchronization stopped")

    def _run_sync_loop(self):
        """Main synchronization loop running in background thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._process_events())
        except Exception as e:
            logger.error(f"Error in sync loop: {e}")
        finally:
            loop.close()

    async def _process_events(self):
        """Process synchronization events"""
        while self._running:
            try:
                # Process pending events with timeout
                try:
                    event = self._event_queue.get_nowait()
                    await self._handle_event(event)
                    self._event_queue.task_done()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.1)  # Small delay when no events

            except Exception as e:
                logger.error(f"Error processing sync event: {e}")

    async def _handle_event(self, event: SyncEvent):
        """Handle a synchronization event"""
        try:
            # Get registered handlers for this event type
            handlers = self._event_handlers.get(event.event_type, [])

            # Execute all handlers
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler for {event.event_type}: {e}")

            # Notify subscribed sessions
            await self._notify_subscribed_sessions(event)

        except Exception as e:
            logger.error(f"Error handling event {event.event_type}: {e}")

    async def _notify_subscribed_sessions(self, event: SyncEvent):
        """Notify all sessions subscribed to this deal"""
        deal_code = event.deal_code
        subscribed_sessions = self._deal_subscriptions.get(deal_code, set())

        for session_id in subscribed_sessions:
            session = self._active_sessions.get(session_id)
            if session and session.user_id != event.user_id:  # Don't notify the originator
                await self._send_to_session(session, event)

    async def _send_to_session(self, session: SyncSession, event: SyncEvent):
        """Send event to a specific session"""
        try:
            # This would be implemented differently for web vs bot
            if session.platform == 'web':
                await self._send_to_web_session(session, event)
            elif session.platform == 'bot':
                await self._send_to_bot_session(session, event)

        except Exception as e:
            logger.error(f"Error sending event to session {session.session_id}: {e}")

    async def _send_to_web_session(self, session: SyncSession, event: SyncEvent):
        """Send event to web session via WebSocket/SSE"""
        # Implementation would depend on WebSocket setup
        # For now, use notifications as fallback
        try:
            await notification_manager.create_notification(
                user_id=session.user_id,
                notification_type=f"sync_{event.event_type}",
                title=f"Deal Update: {event.deal_code}",
                message=f"Deal {event.deal_code} has been updated",
                action_url=f"/deal/{event.deal_code}"
            )
        except Exception as e:
            logger.error(f"Failed to send web notification: {e}")

    async def _send_to_bot_session(self, session: SyncSession, event: SyncEvent):
        """Send event to bot session via Telegram"""
        try:
            # Use existing notification system
            await notification_manager.create_notification(
                user_id=session.user_id,
                notification_type=f"sync_{event.event_type}",
                title=f"🔄 Deal Update: {event.deal_code}",
                message=f"Your deal {event.deal_code} has been updated from another platform",
                action_url=None  # Bot doesn't need URLs
            )
        except Exception as e:
            logger.error(f"Failed to send bot notification: {e}")

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register an event handler"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def publish_event(self, event: SyncEvent):
        """Publish a synchronization event"""
        try:
            await self._event_queue.put(event)
            logger.debug(f"Published sync event: {event.event_type} for deal {event.deal_code}")
        except Exception as e:
            logger.error(f"Error publishing event: {e}")

    def create_session(self, user_id: int, platform: str) -> str:
        """Create a new synchronization session"""
        session_id = f"{platform}_{user_id}_{int(time.time())}"

        session = SyncSession(
            user_id=user_id,
            platform=platform,
            session_id=session_id,
            connected_at=datetime.now(),
            last_activity=datetime.now(),
            subscribed_deals=set()
        )

        self._active_sessions[session_id] = session
        logger.info(f"Created sync session: {session_id} for user {user_id} on {platform}")

        return session_id

    def remove_session(self, session_id: str):
        """Remove a synchronization session"""
        if session_id in self._active_sessions:
            session = self._active_sessions[session_id]

            # Remove from deal subscriptions
            for deal_code in session.subscribed_deals:
                if deal_code in self._deal_subscriptions:
                    self._deal_subscriptions[deal_code].discard(session_id)
                    if not self._deal_subscriptions[deal_code]:
                        del self._deal_subscriptions[deal_code]

            del self._active_sessions[session_id]
            logger.info(f"Removed sync session: {session_id}")

    def subscribe_to_deal(self, session_id: str, deal_code: str):
        """Subscribe a session to deal updates"""
        if session_id not in self._active_sessions:
            return False

        session = self._active_sessions[session_id]
        session.subscribed_deals.add(deal_code)

        if deal_code not in self._deal_subscriptions:
            self._deal_subscriptions[deal_code] = set()
        self._deal_subscriptions[deal_code].add(session_id)

        logger.debug(f"Session {session_id} subscribed to deal {deal_code}")
        return True

    def unsubscribe_from_deal(self, session_id: str, deal_code: str):
        """Unsubscribe a session from deal updates"""
        if session_id not in self._active_sessions:
            return False

        session = self._active_sessions[session_id]
        session.subscribed_deals.discard(deal_code)

        if deal_code in self._deal_subscriptions:
            self._deal_subscriptions[deal_code].discard(session_id)
            if not self._deal_subscriptions[deal_code]:
                del self._deal_subscriptions[deal_code]

        logger.debug(f"Session {session_id} unsubscribed from deal {deal_code}")
        return True

    # Event Handlers

    async def _handle_deal_created(self, event: SyncEvent):
        """Handle deal creation event"""
        logger.info(f"Deal created: {event.deal_code} by user {event.user_id}")

        # Auto-subscribe creator to deal updates
        if event.platform == 'web':
            # For web, we might need to get session from somewhere
            pass
        # Bot sessions are handled differently

    async def _handle_deal_joined(self, event: SyncEvent):
        """Handle deal joining event"""
        logger.info(f"Deal joined: {event.deal_code} by user {event.user_id}")

        # Subscribe the new participant to deal updates
        # This would be called when a user joins from either platform

    async def _handle_deal_status_changed(self, event: SyncEvent):
        """Handle deal status change event"""
        new_status = event.data.get('new_status')
        logger.info(f"Deal status changed: {event.deal_code} -> {new_status}")

        # Notify all subscribers about status change

    async def _handle_payment_received(self, event: SyncEvent):
        """Handle payment received event"""
        logger.info(f"Payment received for deal: {event.deal_code}")

        # Trigger deal status update and notifications

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session"""
        session = self._active_sessions.get(session_id)
        if not session:
            return None

        return {
            'session_id': session.session_id,
            'user_id': session.user_id,
            'platform': session.platform,
            'connected_at': session.connected_at.isoformat(),
            'last_activity': session.last_activity.isoformat(),
            'subscribed_deals': list(session.subscribed_deals)
        }

    def get_deal_subscriptions(self, deal_code: str) -> List[str]:
        """Get all sessions subscribed to a deal"""
        return list(self._deal_subscriptions.get(deal_code, set()))

    def cleanup_inactive_sessions(self, max_age_minutes: int = 30):
        """Clean up inactive sessions"""
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        inactive_sessions = []

        for session_id, session in self._active_sessions.items():
            if session.last_activity < cutoff_time:
                inactive_sessions.append(session_id)

        for session_id in inactive_sessions:
            self.remove_session(session_id)

        if inactive_sessions:
            logger.info(f"Cleaned up {len(inactive_sessions)} inactive sessions")

        return len(inactive_sessions)


# Global instance
cross_platform_sync = CrossPlatformSync()


# Integration functions for existing code

async def notify_deal_created(deal_code: str, user_id: int, platform: str, deal_data: Dict[str, Any]):
    """Notify about deal creation across platforms"""
    event = SyncEvent(
        event_type='deal_created',
        deal_code=deal_code,
        user_id=user_id,
        platform=platform,
        timestamp=datetime.now(),
        data=deal_data,
        event_id=f"deal_created_{deal_code}_{int(time.time())}"
    )

    await cross_platform_sync.publish_event(event)


async def notify_deal_joined(deal_code: str, user_id: int, platform: str, deal_data: Dict[str, Any]):
    """Notify about deal joining across platforms"""
    event = SyncEvent(
        event_type='deal_joined',
        deal_code=deal_code,
        user_id=user_id,
        platform=platform,
        timestamp=datetime.now(),
        data=deal_data,
        event_id=f"deal_joined_{deal_code}_{int(time.time())}"
    )

    await cross_platform_sync.publish_event(event)


async def notify_deal_status_changed(deal_code: str, user_id: int, platform: str,
                                   old_status: str, new_status: str):
    """Notify about deal status changes across platforms"""
    event = SyncEvent(
        event_type='deal_status_changed',
        deal_code=deal_code,
        user_id=user_id,
        platform=platform,
        timestamp=datetime.now(),
        data={'old_status': old_status, 'new_status': new_status},
        event_id=f"status_change_{deal_code}_{int(time.time())}"
    )

    await cross_platform_sync.publish_event(event)


async def notify_payment_received(deal_code: str, user_id: int, platform: str, payment_data: Dict[str, Any]):
    """Notify about payment received across platforms"""
    event = SyncEvent(
        event_type='payment_received',
        deal_code=deal_code,
        user_id=user_id,
        platform=platform,
        timestamp=datetime.now(),
        data=payment_data,
        event_id=f"payment_{deal_code}_{int(time.time())}"
    )

    await cross_platform_sync.publish_event(event)
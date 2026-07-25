import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Simple message structure for actor communication"""
    message_id: str
    sender: str
    receiver: str
    message_type: str
    payload: Dict[str, Any]


class Mailbox:
    """Simple async queue for actor messages with improved concurrency"""

    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.pending_responses: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
    
    async def send(self, message: Message) -> bool:
        """Send message to mailbox with thread safety"""
        try:
            async with self._lock:
                await self.queue.put(message)
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    async def receive(self, timeout: float = 1.0) -> Optional[Message]:
        """Receive message from mailbox"""
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
    
    def reply(self, correlation_id: str, response: Any):
        """Send reply to waiting sender with thread safety"""
        async def _reply():
            async with self._lock:
                if correlation_id in self.pending_responses:
                    future = self.pending_responses[correlation_id]
                    if not future.done():
                        future.set_result(response)

        # Schedule reply in event loop
        asyncio.create_task(_reply())


class ActorRef:
    """Reference to an actor for sending messages"""
    
    def __init__(self, actor_id: str, mailbox: Mailbox):
        self.actor_id = actor_id
        self.mailbox = mailbox
    
    async def tell(self, message_type: str, payload: Dict[str, Any] = None) -> bool:
        """Send message to actor (fire-and-forget)"""
        message = Message(
            message_id=str(uuid.uuid4()),
            sender="system",
            receiver=self.actor_id,
            message_type=message_type,
            payload=payload or {}
        )
        return await self.mailbox.send(message)
    
    async def ask(self, message_type: str, payload: Dict[str, Any] = None, timeout: float = 30.0) -> Optional[Any]:
        """Send message and wait for response with improved concurrency"""
        message = Message(
            message_id=str(uuid.uuid4()),
            sender="system",
            receiver=self.actor_id,
            message_type=message_type,
            payload=payload or {}
        )

        # Create response future with thread safety
        future = asyncio.Future()
        async with self.mailbox._lock:
            self.mailbox.pending_responses[message.message_id] = future

        # Send message
        if not await self.mailbox.send(message):
            async with self.mailbox._lock:
                self.mailbox.pending_responses.pop(message.message_id, None)
            return None

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response from {self.actor_id}")
            return None
        finally:
            async with self.mailbox._lock:
                self.mailbox.pending_responses.pop(message.message_id, None)


class BaseActor:
    """Simplified base actor class"""
    
    def __init__(self, actor_id: str):
        self.actor_id = actor_id
        self.mailbox = Mailbox()
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{actor_id}")
        self.is_running = False
    
    async def receive(self, message: Message) -> Optional[Any]:
        """Handle incoming message"""
        try:
            return await self._handle_message(message)
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            return {"error": str(e)}
    
    async def _handle_message(self, message: Message) -> Optional[Any]:
        """Override this method in subclasses"""
        self.logger.info(f"Received message: {message.message_type}")
        return {"status": "processed"}
    
    async def start(self):
        """Start actor"""
        self.is_running = True
        self.logger.info(f"Actor {self.actor_id} started")
    
    async def stop(self):
        """Stop actor"""
        self.is_running = False
        self.logger.info(f"Actor {self.actor_id} stopped")
    
    def get_actor_ref(self) -> ActorRef:
        """Get reference to this actor"""
        return ActorRef(self.actor_id, self.mailbox)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get actor statistics"""
        return {
            'actor_id': self.actor_id,
            'is_running': self.is_running,
            'queue_size': self.mailbox.queue.qsize()
        }


class Actor(BaseActor):
    """Compatibility Actor class expected by older integration code.

    Subclasses should override `handle_message(self, message: Dict[str, Any])`.
    This class provides `send_message` and adapts Message objects from the
    mailbox into payload dicts for `handle_message`.
    """

    def __init__(self, actor_id: str, actor_system: Optional['ActorSystem'] = None):
        super().__init__(actor_id)
        self.actor_system = actor_system

    async def handle_message(self, message: Dict[str, Any]) -> Optional[Any]:
        """Override this in subclasses to handle plain payload dicts."""
        # Default behaviour delegates to BaseActor implementation
        return await super()._handle_message(message)  # type: ignore[arg-type]

    async def _handle_message(self, message: Message) -> Optional[Any]:
        """Adapter: convert Message -> payload dict and call handle_message."""
        try:
            return await self.handle_message(message.payload)
        except Exception as e:
            self.logger.error(f"Error in compatibility Actor.handle_message: {e}")
            return {"error": str(e)}

    async def send_message(self, message: Dict[str, Any], timeout: float = 30.0) -> Optional[Any]:
        """Send a message to this actor and wait for the response with improved concurrency."""
        msg = Message(
            message_id=str(uuid.uuid4()),
            sender="system",
            receiver=self.actor_id,
            message_type=message.get('type', 'message'),
            payload=message
        )

        fut = asyncio.Future()
        async with self.mailbox._lock:
            self.mailbox.pending_responses[msg.message_id] = fut

        if not await self.mailbox.send(msg):
            async with self.mailbox._lock:
                self.mailbox.pending_responses.pop(msg.message_id, None)
            return None

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout waiting for response to message {msg.message_id} on actor {self.actor_id}")
            return None
        finally:
            async with self.mailbox._lock:
                self.mailbox.pending_responses.pop(msg.message_id, None)


class DealActor(BaseActor):
    """Deal lifecycle management actor"""
    
    def __init__(self, actor_id: str, deal_code: str):
        super().__init__(actor_id)
        self.deal_code = deal_code
    
    async def _handle_message(self, message: Message) -> Optional[Any]:
        """Handle deal messages"""
        try:
            if message.message_type == "update_status":
                return await self._handle_update_status(message.payload)
            elif message.message_type == "get_status":
                return self._handle_get_status()
            else:
                self.logger.warning(f"Unknown message type: {message.message_type}")
                return {"error": "Unknown message type"}
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            return {"error": str(e)}
    
    async def _handle_update_status(self, payload: Dict) -> Dict:
        """Update deal status"""
        new_status = payload.get('status')
        if not new_status:
            return {"success": False, "error": "Status required"}
        
        # Import here to avoid circular imports
        from shared.database import db
        success = db.update_deal_status(self.deal_code, new_status)
        return {"success": success}
    
    def _handle_get_status(self) -> Dict:
        """Get current deal status"""
        from shared.database import db
        deal_data = db.get_deal(self.deal_code)
        return {
            "deal_code": self.deal_code,
            "status": deal_data.get('status') if deal_data else None,
            "data": deal_data
        }


class PaymentActor(BaseActor):
    """Payment processing actor"""
    
    def __init__(self, actor_id: str):
        super().__init__(actor_id)
    
    async def _handle_message(self, message: Message) -> Optional[Any]:
        """Handle payment messages"""
        try:
            if message.message_type == "process_payment":
                return await self._handle_process_payment(message.payload)
            elif message.message_type == "check_payment_status":
                return await self._handle_check_payment_status(message.payload)
            else:
                self.logger.warning(f"Unknown payment message type: {message.message_type}")
                return {"error": "Unknown message type"}
        except Exception as e:
            self.logger.error(f"Error handling payment message: {e}")
            return {"error": str(e)}
    
    async def _handle_process_payment(self, payload: Dict) -> Dict:
        """Process payment for deal"""
        deal_code = payload.get('deal_code')
        amount = payload.get('amount')
        currency = payload.get('currency')
        
        if not all([deal_code, amount, currency]):
            return {"success": False, "error": "Missing required fields"}
        
        try:
            # Import here to avoid circular imports
            from shared.payments import payment_processor
            checkout = payment_processor.process_payment(
                deal_code=deal_code,
                amount=amount,
                currency=currency
            )
            
            return {
                "success": bool(checkout),
                "checkout": checkout,
                "message": f"Payment created for deal {deal_code}"
            }
        except Exception as e:
            self.logger.error(f"Error processing payment: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_check_payment_status(self, payload: Dict) -> Dict:
        """Check payment status"""
        deal_code = payload.get('deal_code')
        if not deal_code:
            return {"success": False, "error": "Deal code required"}
        
        try:
            # Import here to avoid circular imports
            from shared.payments import payment_processor
            is_paid, message = payment_processor.check_deal_payment(deal_code)
            return {
                "success": True,
                "is_paid": is_paid,
                "message": message
            }
        except Exception as e:
            self.logger.error(f"Error checking payment status: {e}")
            return {"success": False, "error": str(e)}


class NotificationActor(BaseActor):
    """Notification actor"""
    
    def __init__(self, actor_id: str):
        super().__init__(actor_id)
    
    async def _handle_message(self, message: Message) -> Optional[Any]:
        """Handle notification messages"""
        try:
            if message.message_type == "send_notification":
                return await self._handle_send_notification(message.payload)
            else:
                self.logger.warning(f"Unknown notification message type: {message.message_type}")
                return {"error": "Unknown message type"}
        except Exception as e:
            self.logger.error(f"Error handling notification message: {e}")
            return {"error": str(e)}
    
    async def _handle_send_notification(self, payload: Dict) -> Dict:
        """Send notification"""
        user_id = payload.get('user_id')
        notification_type = payload.get('type')
        title = payload.get('title')
        message_text = payload.get('message')
        
        if not all([user_id, notification_type, title, message_text]):
            return {"success": False, "error": "Missing required fields"}
        
        try:
            # Import here to avoid circular imports
            from shared.notifications import notification_manager
            success = await notification_manager.create_notification(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message_text,
                action_url=payload.get('action_url')
            )
            return {"success": success}
        except Exception as e:
            self.logger.error(f"Error sending notification: {e}")
            return {"success": False, "error": str(e)}


class ActorSystem:
    """Simplified actor system coordinator"""
    
    def __init__(self, name: str = "BlackDiamondActorSystem", max_actors: int = 100):
        self.name = name
        self.actors: Dict[str, BaseActor] = {}
        self.running = False
        self.logger = logging.getLogger(f"ActorSystem.{name}")
        self.max_actors = max_actors
    
    async def start(self):
        """Start the actor system"""
        if self.running:
            return
        
        self.running = True
        self.logger.info(f"Starting actor system: {self.name}")
        
        # Start system actors
        try:
            self.spawn_actor(PaymentActor, "payment-actor")
            self.spawn_actor(NotificationActor, "notification-actor")
            
            self.logger.info(f"Actor system {self.name} started")
            
        except Exception as e:
            self.logger.error(f"Error starting system actors: {e}")
            raise
    
    async def stop(self):
        """Stop the actor system"""
        self.logger.info(f"Stopping actor system: {self.name}")
        self.running = False
        
        # Stop all actors
        actor_ids = list(self.actors.keys())
        for actor_id in actor_ids:
            await self._remove_actor(actor_id)
        
        self.logger.info(f"Actor system {self.name} stopped")
    
    def spawn_actor(self, actor_class: type, actor_id: str, *args, **kwargs) -> ActorRef:
        """Spawn a new actor"""
        if actor_id in self.actors:
            raise ValueError(f"Actor {actor_id} already exists")
        
        if len(self.actors) >= self.max_actors:
            raise RuntimeError(f"Cannot spawn actor {actor_id}: system at capacity")
        
        try:
            actor = actor_class(actor_id, *args, **kwargs)
            asyncio.create_task(self._run_actor(actor_id))
            
            # Register actor
            self.actors[actor_id] = actor
            
            self.logger.info(f"Spawned actor: {actor_id} (total: {len(self.actors)})")
            return actor.get_actor_ref()
            
        except Exception as e:
            self.logger.error(f"Error spawning actor {actor_id}: {e}")
            raise
    
    async def _remove_actor(self, actor_id: str):
        """Remove and cleanup an actor"""
        if actor_id not in self.actors:
            return
        
        actor = self.actors[actor_id]
        try:
            await actor.stop()
            del self.actors[actor_id]
            self.logger.debug(f"Removed actor: {actor_id}")
        except Exception as e:
            self.logger.error(f"Error removing actor {actor_id}: {e}")
    
    def get_actor_ref(self, actor_id: str) -> Optional[ActorRef]:
        """Get actor reference"""
        actor = self.actors.get(actor_id)
        return actor.get_actor_ref() if actor else None
    
    async def _run_actor(self, actor_id: str):
        """Run actor message processing loop with improved concurrency"""
        actor = self.actors.get(actor_id)
        if not actor:
            return

        try:
            await actor.start()

            while self.running and actor.is_running:
                try:
                    # Use shorter timeout for better responsiveness
                    message = await actor.mailbox.receive(0.05)
                    if message:
                        # Process message in background to avoid blocking
                        asyncio.create_task(self._process_message_safe(actor, message))

                    await asyncio.sleep(0.005)  # Reduced sleep for better throughput
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"Error in actor {actor_id} message loop: {e}")
                    actor.is_running = False
                    break

        except Exception as e:
            self.logger.error(f"Critical error running actor {actor_id}: {e}")
            actor.is_running = False

    async def _process_message_safe(self, actor: BaseActor, message: Message):
        """Safely process a message without blocking the actor loop"""
        try:
            await actor.receive(message)
        except Exception as e:
            actor.logger.error(f"Error processing message {message.message_id}: {e}")
    
    async def create_deal_actor(self, deal_code: str) -> ActorRef:
        """Create deal-specific actor"""
        actor_id = f"deal-{deal_code}"
        return self.spawn_actor(DealActor, actor_id, deal_code)
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get actor system statistics"""
        running_actors = sum(1 for actor in self.actors.values() if actor.is_running)
        
        return {
            'system_name': self.name,
            'is_running': self.running,
            'total_actors': len(self.actors),
            'running_actors': running_actors,
            'max_actors': self.max_actors
        }
    
    def get_actor_details(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about all actors"""
        return {
            actor_id: actor.get_stats()
            for actor_id, actor in self.actors.items()
        }

    # Backwards-compatible registration API expected by older code
    async def register_actor(self, actor: 'Actor') -> ActorRef:
        """Register an Actor instance with the system and start its loop.

        Accepts Actor instances that subclass BaseActor or the compatibility
        `Actor` class defined below. Returns an ActorRef for sending messages.
        """
        actor_id = getattr(actor, 'actor_id', None)
        if not actor_id:
            raise ValueError("Actor instance must have an 'actor_id' attribute")

        if actor_id in self.actors:
            raise ValueError(f"Actor {actor_id} already registered")

        # If actor is a compatibility Actor wrapper that contains a BaseActor
        # we register the actor object directly. Otherwise assume it's a BaseActor.
        self.actors[actor_id] = actor
        # Start actor loop
        asyncio.create_task(self._run_actor(actor_id))
        # Register with health monitor if available
        try:
            from shared.actor_health import health_monitor
            health_monitor.register_actor(actor_id)
        except Exception:
            pass

        return actor.get_actor_ref()

    async def shutdown(self):
        """Backward-compatible shutdown method that stops the system."""
        await self.stop()


# Global actor system instance
actor_system = ActorSystem("BlackDiamond")

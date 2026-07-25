import asyncio
import logging
from typing import Dict, Any
from shared.actor_system import ActorSystem, Actor
from shared.database import db
# Note: blockchain_integration.py was removed as redundant
# Blockchain functionality is now handled in decentralized_payments.py
from shared.notifications import NotificationService

logger = logging.getLogger(__name__)


class DealActor(Actor):
    """Actor for handling deal-related operations."""

    def __init__(self, actor_system: ActorSystem):
        super().__init__("deal_actor", actor_system)
        self.active_deals = {}  # deal_id -> deal_data

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle deal-related messages."""
        action = message.get('action')

        if action == 'create_deal':
            return await self._create_deal(message)
        elif action == 'join_deal':
            return await self._join_deal(message)
        elif action == 'complete_deal':
            return await self._complete_deal(message)
        elif action == 'cancel_deal':
            return await self._cancel_deal(message)
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}

    async def _create_deal(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new deal."""
        try:
            deal_data = message.get('deal_data', {})
            user_id = message.get('user_id')

            # Generate deal code
            deal_code = db.generate_deal_code()

            # Create deal in database
            deal_id = db.create_deal(
                buyer_id=user_id,
                amount=deal_data['amount'],
                currency=deal_data['currency'],
                title=deal_data.get('title', ''),
                description=deal_data.get('description', ''),
                deal_code=deal_code
            )

            if deal_id:
                self.active_deals[deal_id] = {
                    'deal_code': deal_code,
                    'buyer_id': user_id,
                    'status': 'pending'
                }

                return {
                    'status': 'success',
                    'deal_id': deal_id,
                    'deal_code': deal_code
                }
            else:
                return {'status': 'error', 'message': 'Failed to create deal'}

        except Exception as e:
            logger.error(f"Error creating deal: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _join_deal(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Join an existing deal as seller."""
        try:
            deal_code = message.get('deal_code')
            user_id = message.get('user_id')

            deal = db.get_deal_by_code(deal_code)
            if not deal:
                return {'status': 'error', 'message': 'Deal not found'}

            if deal['buyer_id'] == user_id:
                return {'status': 'error', 'message': 'Cannot join your own deal'}

            if deal['seller_id']:
                return {'status': 'error', 'message': 'Deal already has a seller'}

            # Join deal
            success = db.join_deal(deal['deal_id'], user_id)
            if success:
                self.active_deals[deal['deal_id']] = {
                    'deal_code': deal_code,
                    'buyer_id': deal['buyer_id'],
                    'seller_id': user_id,
                    'status': 'active'
                }

                return {'status': 'success', 'deal_id': deal['deal_id']}
            else:
                return {'status': 'error', 'message': 'Failed to join deal'}

        except Exception as e:
            logger.error(f"Error joining deal: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _complete_deal(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Complete a deal."""
        try:
            deal_id = message.get('deal_id')
            user_id = message.get('user_id')

            deal = db.get_deal(deal_id)
            if not deal:
                return {'status': 'error', 'message': 'Deal not found'}

            # Check permissions
            if user_id not in [deal['buyer_id'], deal['seller_id']]:
                return {'status': 'error', 'message': 'Not authorized'}

            # Complete deal
            success = db.complete_deal(deal_id)
            if success:
                if deal_id in self.active_deals:
                    del self.active_deals[deal_id]

                return {'status': 'success'}
            else:
                return {'status': 'error', 'message': 'Failed to complete deal'}

        except Exception as e:
            logger.error(f"Error completing deal: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _cancel_deal(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a deal."""
        try:
            deal_id = message.get('deal_id')
            user_id = message.get('user_id')
            reason = message.get('reason', '')

            deal = db.get_deal(deal_id)
            if not deal:
                return {'status': 'error', 'message': 'Deal not found'}

            # Check permissions (only buyer can cancel)
            if deal['buyer_id'] != user_id:
                return {'status': 'error', 'message': 'Only buyer can cancel deal'}

            # Cancel deal
            success = db.cancel_deal(deal_id, reason)
            if success:
                if deal_id in self.active_deals:
                    del self.active_deals[deal_id]

                return {'status': 'success'}
            else:
                return {'status': 'error', 'message': 'Failed to cancel deal'}

        except Exception as e:
            logger.error(f"Error cancelling deal: {e}")
            return {'status': 'error', 'message': str(e)}


class PaymentActor(Actor):
    """Actor for handling payment operations."""

    def __init__(self, actor_system: ActorSystem):
        super().__init__("payment_actor", actor_system)
        # Blockchain functionality is now handled in decentralized_payments.py
        # self.blockchain = BlockchainIntegration()

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment-related messages."""
        action = message.get('action')

        if action == 'create_payment':
            return await self._create_payment(message)
        elif action == 'verify_payment':
            return await self._verify_payment(message)
        elif action == 'process_refund':
            return await self._process_refund(message)
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}

    async def _create_payment(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Create a payment record."""
        try:
            deal_id = message.get('deal_id')
            payer_id = message.get('payer_id')
            payee_id = message.get('payee_id')
            amount = message.get('amount')
            currency = message.get('currency')

            payment_id = db.create_payment(
                deal_id=deal_id,
                payer_id=payer_id,
                payee_id=payee_id,
                amount=amount,
                currency=currency
            )

            if payment_id:
                return {'status': 'success', 'payment_id': payment_id}
            else:
                return {'status': 'error', 'message': 'Failed to create payment'}

        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _verify_payment(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Verify blockchain payment."""
        try:
            payment_id = message.get('payment_id')
            tx_hash = message.get('tx_hash')

            payment = db.get_payment(payment_id)
            if not payment:
                return {'status': 'error', 'message': 'Payment not found'}

            # Use decentralized payments processor for verification
            from shared.decentralized_payments import decentralized_payment_processor

            # Get checkout information
            checkout = decentralized_payment_processor.get_checkout(payment_id)
            if not checkout:
                return {'status': 'error', 'message': 'Checkout not found'}

            # Check payment status
            is_paid, status_message = decentralized_payment_processor.check_payment_status(payment_id)

            if is_paid:
                # Update payment status
                db.update_payment_status(payment_id, 'confirmed', tx_hash)
                return {'status': 'success', 'verification': {'status': 'confirmed', 'tx_hash': tx_hash}}
            else:
                return {'status': 'pending', 'verification': {'status': 'pending', 'message': status_message}}

        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _process_refund(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process payment refund."""
        try:
            payment_id = message.get('payment_id')
            reason = message.get('reason', '')

            payment = db.get_payment(payment_id)
            if not payment:
                return {'status': 'error', 'message': 'Payment not found'}

            # For now, just mark as refunded in database
            # Full blockchain refund implementation would be added later
            db.update_payment_status(payment_id, 'refunded')

            refund_result = {
                'status': 'success',
                'payment_id': payment_id,
                'amount': payment['amount'],
                'currency': payment['currency'],
                'reason': reason,
                'refunded_at': str(asyncio.get_event_loop().time())
            }

            logger.info(f"Payment {payment_id} marked as refunded: {reason}")
            return {'status': 'success', 'refund': refund_result}

        except Exception as e:
            logger.error(f"Error processing refund: {e}")
            return {'status': 'error', 'message': str(e)}


class NotificationActor(Actor):
    """Actor for handling notifications."""

    def __init__(self, actor_system: ActorSystem):
        super().__init__("notification_actor", actor_system)
        self.notification_service = NotificationService()

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle notification messages."""
        action = message.get('action')

        if action == 'send_notification':
            return await self._send_notification(message)
        elif action == 'broadcast':
            return await self._broadcast_message(message)
        else:
            return {'status': 'error', 'message': f'Unknown action: {action}'}

    async def _send_notification(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification to user."""
        try:
            user_id = message.get('user_id')
            notification_type = message.get('type')
            title = message.get('title')
            content = message.get('content')

            # Send via bot
            success = await self.notification_service.send_bot_notification(
                user_id=user_id,
                message=f"<b>{title}</b>\n\n{content}",
                notification_type=notification_type
            )

            if success:
                return {'status': 'success'}
            else:
                return {'status': 'error', 'message': 'Failed to send notification'}

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _broadcast_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Broadcast message to all users."""
        try:
            title = message.get('title')
            content = message.get('content')
            user_filter = message.get('filter', {})

            # Get users to broadcast to
            users = db.get_users_for_broadcast(**user_filter)

            sent_count = 0
            for user in users:
                try:
                    await self.notification_service.send_bot_notification(
                        user_id=user['user_id'],
                        message=f"<b>{title}</b>\n\n{content}",
                        notification_type='broadcast'
                    )
                    sent_count += 1
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    logger.error(f"Failed to send broadcast to user {user['user_id']}: {e}")

            return {
                'status': 'success',
                'sent_count': sent_count,
                'total_users': len(users)
            }

        except Exception as e:
            logger.error(f"Error broadcasting message: {e}")
            return {'status': 'error', 'message': str(e)}


class BotIntegration:
    """Main integration class for bot system."""

    def __init__(self):
        self.actor_system = ActorSystem()
        self.deal_actor = None
        self.payment_actor = None
        self.notification_actor = None
        self.is_initialized = False

    async def initialize(self) -> bool:
        """Initialize the integration system."""
        try:
            logger.info("Initializing bot integration system...")

            # Create actors
            self.deal_actor = DealActor(self.actor_system)
            self.payment_actor = PaymentActor(self.actor_system)
            self.notification_actor = NotificationActor(self.actor_system)

            # Register actors
            await self.actor_system.register_actor(self.deal_actor)
            await self.actor_system.register_actor(self.payment_actor)
            await self.actor_system.register_actor(self.notification_actor)

            # Start actor system
            await self.actor_system.start()

            self.is_initialized = True
            logger.info("✅ Bot integration system initialized")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize integration system: {e}")
            return False

    async def shutdown(self):
        """Shutdown the integration system."""
        try:
            if self.actor_system:
                await self.actor_system.shutdown()
            self.is_initialized = False
            logger.info("✅ Bot integration system shutdown")
        except Exception as e:
            logger.error(f"Error during integration shutdown: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on integration system."""
        health = {
            'status': 'healthy' if self.is_initialized else 'unhealthy',
            'components': {}
        }

        if self.actor_system:
            health['components']['actor_system'] = {
                'status': 'healthy',
                'active_actors': len(self.actor_system.actors)
            }

        if self.deal_actor:
            health['components']['deal_actor'] = {
                'status': 'healthy',
                'active_deals': len(self.deal_actor.active_deals)
            }

        return health

    # Convenience methods for common operations
    async def create_deal(self, user_id: int, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new deal."""
        if not self.deal_actor:
            return {'status': 'error', 'message': 'Deal actor not initialized'}

        message = {
            'action': 'create_deal',
            'user_id': user_id,
            'deal_data': deal_data
        }

        return await self.deal_actor.send_message(message)

    async def join_deal(self, user_id: int, deal_code: str) -> Dict[str, Any]:
        """Join an existing deal."""
        if not self.deal_actor:
            return {'status': 'error', 'message': 'Deal actor not initialized'}

        message = {
            'action': 'join_deal',
            'user_id': user_id,
            'deal_code': deal_code
        }

        return await self.deal_actor.send_message(message)

    async def verify_payment(self, payment_id: str, tx_hash: str) -> Dict[str, Any]:
        """Verify a blockchain payment."""
        if not self.payment_actor:
            return {'status': 'error', 'message': 'Payment actor not initialized'}

        message = {
            'action': 'verify_payment',
            'payment_id': payment_id,
            'tx_hash': tx_hash
        }

        return await self.payment_actor.send_message(message)

    async def send_notification(self, user_id: int, notification_type: str,
                              title: str, content: str) -> Dict[str, Any]:
        """Send notification to user."""
        if not self.notification_actor:
            return {'status': 'error', 'message': 'Notification actor not initialized'}

        message = {
            'action': 'send_notification',
            'user_id': user_id,
            'type': notification_type,
            'title': title,
            'content': content
        }

        return await self.notification_actor.send_message(message)

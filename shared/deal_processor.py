import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .database import db
from .payments import payment_processor
from .decentralized_payments import decentralized_payment_processor
from .platform_sync import cross_platform_sync, notify_deal_status_changed
from .notifications import notification_manager
from .config import COMMISSION_RATE
from .localization import localization

logger = logging.getLogger(__name__)


class DealProcessingStatus(Enum):
    """Status of automated deal processing"""
    PENDING = "pending"
    PAYMENT_CHECKING = "payment_checking"
    PAYMENT_RECEIVED = "payment_received"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class AutomatedDeal:
    """Represents an automated deal being processed"""
    deal_code: str
    status: DealProcessingStatus
    last_checked: datetime
    retry_count: int = 0
    max_retries: int = 5
    next_check_time: datetime = None
    payment_checkout_id: str = None
    blockchain_tx_hash: str = None


class AutomatedDealProcessor:
    """
    Main processor for automated deal handling
    Monitors deals, checks payments, and completes transactions automatically
    """

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval  # seconds between checks
        self.active_deals: Dict[str, AutomatedDeal] = {}
        self.processing_lock = asyncio.Lock()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

        # Processing statistics
        self.stats = {
            'deals_processed': 0,
            'payments_checked': 0,
            'deals_completed': 0,
            'errors': 0,
            'last_run': None
        }

    async def start_automated_processing(self):
        """Start the automated deal processing system"""
        if self.is_running:
            return

        self.is_running = True
        self._task = asyncio.create_task(self._processing_loop())
        await cross_platform_sync.start_sync()

        logger.info("🚀 Automated deal processor started")

    def stop_automated_processing(self):
        """Stop the automated deal processing system"""
        self.is_running = False
        if self._task:
            self._task.cancel()
        cross_platform_sync.stop_sync()

        logger.info("⏹️ Automated deal processor stopped")

    async def _processing_loop(self):
        """Main processing loop"""
        while self.is_running:
            try:
                await self._process_pending_deals()
                self.stats['last_run'] = datetime.now()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(self.check_interval)

    async def _process_pending_deals(self):
        """Process all pending deals"""
        try:
            # Get active deals from database
            active_deals = db.get_active_deals()
            if not active_deals:
                return

            logger.debug(f"📋 Processing {len(active_deals)} active deals")

            for deal in active_deals:
                deal_code = deal['deal_code']
                await self._process_single_deal(deal_code)

        except Exception as e:
            logger.error(f"Error processing pending deals: {e}")

    async def _process_single_deal(self, deal_code: str):
        """Process a single deal through its lifecycle"""
        async with self.processing_lock:
            try:
                # Get or create automated deal tracking
                automated_deal = self._get_or_create_automated_deal(deal_code)
                if not automated_deal:
                    return

                # Skip if recently checked
                if automated_deal.next_check_time and datetime.now() < automated_deal.next_check_time:
                    return

                # Process based on current status
                if automated_deal.status == DealProcessingStatus.PENDING:
                    await self._handle_pending_deal(automated_deal)
                elif automated_deal.status == DealProcessingStatus.PAYMENT_CHECKING:
                    await self._handle_payment_checking(automated_deal)
                elif automated_deal.status == DealProcessingStatus.PAYMENT_RECEIVED:
                    await self._handle_payment_received(automated_deal)

                # Update last checked time
                automated_deal.last_checked = datetime.now()
                automated_deal.next_check_time = datetime.now() + timedelta(seconds=self.check_interval)

            except Exception as e:
                logger.error(f"Error processing deal {deal_code}: {e}")
                automated_deal = self.active_deals.get(deal_code)
                if automated_deal:
                    automated_deal.retry_count += 1
                    if automated_deal.retry_count >= automated_deal.max_retries:
                        automated_deal.status = DealProcessingStatus.FAILED
                        logger.error(f"Deal {deal_code} failed after {automated_deal.max_retries} retries")

    def _get_or_create_automated_deal(self, deal_code: str) -> Optional[AutomatedDeal]:
        """Get existing automated deal or create new one"""
        if deal_code in self.active_deals:
            return self.active_deals[deal_code]

        # Check if deal exists in database
        deal = db.get_deal(deal_code)
        if not deal:
            return None

        # Create new automated deal
        automated_deal = AutomatedDeal(
            deal_code=deal_code,
            status=DealProcessingStatus.PENDING,
            last_checked=datetime.now(),
            next_check_time=datetime.now()
        )

        self.active_deals[deal_code] = automated_deal
        logger.info(f"📝 Created automated deal tracking for {deal_code}")

        return automated_deal

    async def _handle_pending_deal(self, automated_deal: AutomatedDeal):
        """Handle a deal that is pending payment setup"""
        deal_code = automated_deal.deal_code
        deal = db.get_deal(deal_code)

        if not deal:
            automated_deal.status = DealProcessingStatus.FAILED
            return

        # Check if deal has expired
        created_at = deal.get('created_at')
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
            if datetime.now() - created_at > timedelta(hours=24):
                automated_deal.status = DealProcessingStatus.EXPIRED
                await self._expire_deal(deal_code)
                return

        # Create payment checkout if not exists
        if not automated_deal.payment_checkout_id:
            checkout = await self._create_payment_checkout(deal)
            if checkout:
                automated_deal.payment_checkout_id = checkout['checkout_id']
                automated_deal.status = DealProcessingStatus.PAYMENT_CHECKING
                logger.info(f"💳 Created payment checkout for deal {deal_code}: {checkout['checkout_id']}")
            else:
                logger.error(f"Failed to create payment checkout for deal {deal_code}")
                automated_deal.retry_count += 1

    async def _create_payment_checkout(self, deal: Dict) -> Optional[Dict]:
        """Create payment checkout for deal"""
        try:
            # Try decentralized payment first (with escrow)
            checkout = decentralized_payment_processor.process_deal_payment(
                deal_code=deal['deal_code'],
                amount=deal['amount'],
                currency=deal['currency'],
                description=f"Deal payment: {deal['deal_code']}"
            )

            if checkout:
                logger.info(f"✅ Created decentralized payment for deal {deal['deal_code']}")
                return checkout

            # Fallback to system wallet payment
            checkout = payment_processor.process_deal_payment(
                deal_code=deal['deal_code'],
                amount=deal['amount'],
                currency=deal['currency'],
                description=f"Deal payment: {deal['deal_code']}"
            )

            if checkout:
                logger.info(f"✅ Created system wallet payment for deal {deal['deal_code']}")
                return checkout

            return None

        except Exception as e:
            logger.error(f"Error creating payment checkout for deal {deal['deal_code']}: {e}")
            return None

    async def _handle_payment_checking(self, automated_deal: AutomatedDeal):
        """Handle payment checking phase"""
        deal_code = automated_deal.deal_code

        try:
            # Check payment status
            is_paid, message = await self._check_deal_payment(deal_code)

            if is_paid:
                automated_deal.status = DealProcessingStatus.PAYMENT_RECEIVED
                automated_deal.blockchain_tx_hash = message if message != "Payment received" else None
                logger.info(f"💰 Payment received for deal {deal_code}")
                self.stats['payments_checked'] += 1
            else:
                # Continue checking (status remains PAYMENT_CHECKING)
                pass

        except Exception as e:
            logger.error(f"Error checking payment for deal {deal_code}: {e}")
            automated_deal.retry_count += 1

    async def _check_deal_payment(self, deal_code: str) -> tuple[bool, str]:
        """Check if payment has been received for deal"""
        try:
            # Try decentralized payment check first
            is_paid, message = await decentralized_payment_processor.check_deal_payment(deal_code)
            if is_paid:
                return True, message

            # Fallback to system wallet check
            is_paid, message = payment_processor.check_deal_payment(deal_code)
            return is_paid, message

        except Exception as e:
            logger.error(f"Error checking deal payment {deal_code}: {e}")
            return False, "Check failed"

    async def _handle_payment_received(self, automated_deal: AutomatedDeal):
        """Handle payment received - move to delivery pending status"""
        deal_code = automated_deal.deal_code

        # Update deal status to delivery_pending instead of completing
        success = db.update_deal_status(deal_code, 'delivery_pending')
        if success:
            logger.info(f"📦 Deal {deal_code} moved to delivery pending status")
            # Send notifications to both parties
            await self._send_delivery_pending_notifications(deal_code)
            # Clean up automated processing for this deal
            if deal_code in self.active_deals:
                del self.active_deals[deal_code]
        else:
            logger.error(f"Failed to update deal {deal_code} to delivery_pending")
            automated_deal.status = DealProcessingStatus.FAILED


    async def _complete_deal_transaction(self, deal_code: str, tx_hash: str = None) -> bool:
        """Complete the deal transaction with commission calculation"""
        try:
            deal = db.get_deal(deal_code)
            if not deal:
                return False

            # Calculate commission
            amount = deal['amount']
            commission = amount * COMMISSION_RATE
            seller_amount = amount - commission

            # Update deal status to completed
            success = db.update_deal_status(deal_code, 'completed')
            if not success:
                return False

            # Update deal with completion details
            db.update_deal_completion(
                deal_code=deal_code,
                commission_amount=commission,
                seller_amount=seller_amount,
                tx_hash=tx_hash,
                completed_at=datetime.now().isoformat()
            )

            # Update user statistics
            buyer_id = deal['buyer_id']
            seller_id = deal.get('seller_id')

            db.update_user_deal_stats(buyer_id, 'completed', amount)
            if seller_id:
                db.update_user_deal_stats(seller_id, 'completed', seller_amount)

            # Notify cross-platform sync
            await notify_deal_status_changed(
                deal_code=deal_code,
                user_id=buyer_id,
                platform='automated',
                old_status='active',
                new_status='completed'
            )

            return True

        except Exception as e:
            logger.error(f"Error completing deal transaction {deal_code}: {e}")
            return False

    async def _expire_deal(self, deal_code: str):
        """Expire a deal that has timed out"""
        try:
            db.update_deal_status(deal_code, 'expired')
            logger.info(f"⏰ Deal {deal_code} expired")

            # Notify participants
            deal = db.get_deal(deal_code)
            if deal:
                from .url_utils import deal_url
                await notification_manager.create_notification(
                    user_id=deal['buyer_id'],
                    notification_type="deal_expired",
                    title="Deal Expired",
                    message=f"Your deal {deal_code} has expired due to no payment received.",
                    action_url=deal_url(deal_code)
                )

        except Exception as e:
            logger.error(f"Error expiring deal {deal_code}: {e}")

    async def _send_delivery_pending_notifications(self, deal_code: str):
        """Send delivery pending notifications to all participants"""
        try:
            deal = db.get_deal(deal_code)
            if not deal:
                return

            buyer_id = deal['buyer_id']
            seller_id = deal.get('seller_id')

            # Notify buyer - wait for delivery
            buyer_language = db.get_user_language(buyer_id)
            buyer_message = localization.get_text('payment_confirmed_buyer', buyer_language) if localization else "Payment confirmed. Wait for seller to deliver goods."

            from .url_utils import deal_url
            await notification_manager.create_notification(
                user_id=buyer_id,
                notification_type="delivery_pending",
                title="📦 Delivery Pending",
                message=buyer_message,
                action_url=deal_url(deal_code)
            )

            # Notify seller - confirm delivery
            if seller_id:
                seller_language = db.get_user_language(seller_id)
                seller_message = localization.get_text('payment_received_seller', seller_language) if localization else "Payment received. Please deliver the goods/services."

                from .url_utils import deal_url
                await notification_manager.create_notification(
                    user_id=seller_id,
                    notification_type="delivery_pending",
                    title="📦 Confirm Delivery",
                    message=seller_message,
                    action_url=deal_url(deal_code)
                )

            logger.info(f"📤 Delivery pending notifications sent for deal {deal_code}")

        except Exception as e:
            logger.error(f"Error sending delivery pending notifications for {deal_code}: {e}")

    async def _send_completion_notifications(self, deal_code: str):
        """Send completion notifications to all participants"""
        try:
            deal = db.get_deal(deal_code)
            if not deal:
                return

            buyer_id = deal['buyer_id']
            seller_id = deal.get('seller_id')

            # Notify buyer
            buyer_language = db.get_user_language(buyer_id)
            buyer_title = localization.get_text('deal_buyer_completed_title', buyer_language) if localization else "🎉 Deal Completed!"
            buyer_message = localization.get_text('deal_buyer_completed_message', buyer_language, deal_code=deal_code) if localization else f"Your deal {deal_code} has been completed successfully!"
            
            from .url_utils import deal_url
            await notification_manager.create_notification(
                user_id=buyer_id,
                notification_type="deal_completed",
                title=buyer_title,
                message=buyer_message,
                action_url=deal_url(deal_code)
            )

            # Notify seller
            if seller_id:
                commission = deal['amount'] * COMMISSION_RATE
                seller_amount = deal['amount'] - commission
                
                # Get seller's language for translation
                seller_language = db.get_user_language(seller_id)
                
                # Get translated title and message
                title = localization.get_text('deal_completed_notification_title', seller_language) if localization else "💰 Funds Released!"
                message = localization.get_text('deal_completed_notification_message', seller_language,
                    deal_code=deal_code,
                    amount=seller_amount,
                    currency=deal['currency'],
                    commission=commission
                ) if localization else f"Deal {deal_code} completed. You received {seller_amount} {deal['currency']} (commission: {commission:.4f} {deal['currency']})"

                from .url_utils import deal_url
                await notification_manager.create_notification(
                    user_id=seller_id,
                    notification_type="deal_completed",
                    title=title,
                    message=message,
                    action_url=deal_url(deal_code)
                )

            logger.info(f"📤 Completion notifications sent for deal {deal_code}")

        except Exception as e:
            logger.error(f"Error sending completion notifications for {deal_code}: {e}")

    def get_processing_stats(self) -> Dict:
        """Get processing statistics"""
        return {
            **self.stats,
            'active_deals': len(self.active_deals),
            'uptime': str(datetime.now() - (self.stats['last_run'] or datetime.now()))
        }

    def get_deal_status(self, deal_code: str) -> Optional[Dict]:
        """Get status of a specific deal"""
        automated_deal = self.active_deals.get(deal_code)
        if not automated_deal:
            return None

        return {
            'deal_code': automated_deal.deal_code,
            'status': automated_deal.status.value,
            'last_checked': automated_deal.last_checked.isoformat(),
            'retry_count': automated_deal.retry_count,
            'payment_checkout_id': automated_deal.payment_checkout_id,
            'blockchain_tx_hash': automated_deal.blockchain_tx_hash
        }

    async def force_check_deal(self, deal_code: str) -> bool:
        """Force immediate check of a specific deal"""
        automated_deal = self._get_or_create_automated_deal(deal_code)
        if not automated_deal:
            return False

        automated_deal.next_check_time = datetime.now()  # Force immediate check
        await self._process_single_deal(deal_code)
        return True


# Global instance
automated_deal_processor = AutomatedDealProcessor()


# Integration functions

async def start_automated_deal_processing():
    """Start the automated deal processing system"""
    await automated_deal_processor.start_automated_processing()


def stop_automated_deal_processing():
    """Stop the automated deal processing system"""
    automated_deal_processor.stop_automated_processing()


async def process_new_deal_automatically(deal_code: str):
    """Process a newly created deal automatically"""
    await automated_deal_processor.force_check_deal(deal_code)


# Background task for continuous processing
async def run_automated_deal_processing():
    """Run automated deal processing as a background service"""
    await start_automated_deal_processing()

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        stop_automated_deal_processing()

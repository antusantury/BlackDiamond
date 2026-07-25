import logging
from .database import db
from .localization import localization
from .commission import get_commission_breakdown

logger = logging.getLogger(__name__)

class NotificationManager:
    """Notification manager for cross-platform synchronization."""

    def __init__(self):
        self.telegram_bot = None  # Set during bot initialization

    def set_telegram_bot(self, bot):
        """Set the Telegram bot instance."""
        self.telegram_bot = bot

    def _get_public_base_url(self) -> str:
        """Get public base URL for notifications"""
        try:
            from .url_utils import get_base_url
            return get_base_url()
        except Exception:
            return "https://your-domain.com"  # fallback

    async def create_notification(self, user_id: int, notification_type: str, title: str,
                                message: str, action_url: str = None, send_telegram: bool = True,
                                custom_keyboard=None) -> bool:
        """Create a notification and send it to Telegram if needed."""
        try:
            # Ensure action_url is a full URL for Telegram compatibility
            if action_url and action_url.startswith('/'):
                from .url_utils import construct_full_url
                action_url = construct_full_url(action_url)
            
            # Create notification in the database (best-effort; Telegram delivery should not depend on DB writes).
            try:
                success = db.create_notification(user_id, notification_type, title, message, action_url)
            except Exception as db_error:
                logger.error(f"Failed to create DB notification for user {user_id}: {db_error}")
                success = False

            if send_telegram:
                try:
                    await self._send_telegram_notification(user_id, title, message, action_url, custom_keyboard)
                except Exception as telegram_error:
                    logger.error(f"Failed to send Telegram notification for user {user_id}: {telegram_error}")

            return success
        except Exception as e:
            logger.error(f"Error creating notification for user {user_id}: {e}")
            return False

    async def _send_telegram_notification(self, user_id: int, title: str, message: str, action_url: str = None, custom_keyboard=None):
        """Send a notification to Telegram."""
        try:
            # Always try direct API first for reliability in async contexts
            await self._send_telegram_notification_direct(user_id, title, message, action_url, custom_keyboard)
            return

        except Exception as e:
            logger.warning(f"Direct API notification failed for user {user_id}, trying bot instance: {e}")
            
            # Try bot instance as fallback if available
            if self.telegram_bot:
                try:
                    # Build notification text
                    if title:
                        telegram_message = f"🔔 {title}\n\n{message}"
                    else:
                        # If title is not set, use the body without extra prefixes
                        telegram_message = message

                    # Use custom_keyboard if provided, otherwise build a default button
                    reply_markup = custom_keyboard
                    if not reply_markup and action_url:
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        user_language = db.get_user_language(user_id) or localization.default_language
                        open_text = localization.get_text("button_open", user_language)
                        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=open_text, url=action_url)]
                        ])

                    # Send message via bot instance
                    await self.telegram_bot.send_message(
                        chat_id=user_id,
                        text=telegram_message,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    logger.info(f"Telegram notification sent successfully to user {user_id} via bot instance")
                    return
                    
                except Exception as bot_error:
                    logger.error(f"Bot instance notification also failed for user {user_id}: {bot_error}")
            else:
                logger.warning(f"No bot instance available for user {user_id}")
            
            # If both methods fail, log the error but don't raise
            logger.error(f"All notification methods failed for user {user_id}: {e}")

    # Notification helpers for specific event types

    async def notify_deal_created(self, user_id: int, deal_code: str, amount: float, currency: str):
        """Notify about a newly created deal."""
        title = "Deal created"
        message = f"Your deal {deal_code} was created. Amount: {amount} {currency}"
        from .url_utils import deal_url
        action_url = deal_url(deal_code)

        await self.create_notification(user_id, "deal", title, message, action_url)

    async def notify_deal_joined(self, user_id: int, deal_code: str, amount: float, currency: str,
                                custom_message: str = None, custom_keyboard = None):
        """Notify about joining a deal."""
        # IMPORTANT:
        # - When custom_message is provided (e.g. from _notify_buyer_deal_joined),
        #   it already contains a fully localized header/body for the BUYER.
        #   In that case we must NOT prepend our own "seller joined" title to avoid mixed languages.
        # - When custom_message is not provided, use localized text based on user's language.
        if custom_message:
            # Use the provided, fully localized content as-is.
            title = ""
            message = custom_message
        else:
            # Get user's language for proper localization
            user_language = 'en'  # Default fallback
            try:
                user_data = db.get_user(user_id)
                if user_data and user_data.get('language'):
                    user_language = user_data['language']
            except Exception as e:
                logger.warning(f"Could not get user language for {user_id}: {e}")
            
            # Use localized text
            try:
                title = localization.get_text('deal_update', user_language)
                message_template = localization.get_text('seller_joined_notification', user_language)
                message = message_template.format(deal_code=deal_code, amount=amount, currency=currency)
            except Exception as e:
                logger.warning(f"Could not get localized text for user {user_id}: {e}")
                # Fallback to English if localization fails
                title = "Deal update"
                message = f"A seller joined your deal {deal_code}. Amount: {amount} {currency}"

        from .url_utils import deal_url
        action_url = deal_url(deal_code)

        # Always create notification in database and send to Telegram
        await self.create_notification(user_id, "deal", title, message, action_url, custom_keyboard=custom_keyboard)

    async def notify_payment_received(self, user_id: int, deal_code: str, amount: float, currency: str):
        """Notify about a received payment."""
        title = "Payment received"
        message = f"Payment for deal {deal_code} was received. Amount: {amount} {currency}"
        from .url_utils import deal_url
        action_url = deal_url(deal_code)

        await self.create_notification(user_id, "payment", title, message, action_url)

    async def notify_deal_completed(self, user_id: int, deal_code: str, amount: float, currency: str):
        """Notify about a completed deal."""
        title = "Deal completed"
        message = f"Deal {deal_code} completed. Amount: {amount} {currency}"
        from .url_utils import deal_url
        action_url = deal_url(deal_code)

        await self.create_notification(user_id, "deal", title, message, action_url)

    async def notify_deal_cancelled(self, user_id: int, deal_code: str, reason: str = None):
        """Notify about a cancelled deal."""
        title = "Deal cancelled"
        message = f"Deal {deal_code} was cancelled."
        if reason:
            message += f" Reason: {reason}"
        from .url_utils import deal_url
        action_url = deal_url(deal_code)

        await self.create_notification(user_id, "deal", title, message, action_url)

    async def notify_support_response(self, user_id: int, admin_message: str):
        """Notify about a support response."""
        title = "💬 Support reply"
        # Send the full message
        message = f"Support:\n\n{admin_message}"
        action_url = "/support"

        await self.create_notification(user_id, "support", title, message, action_url)

        # Send notification directly via Telegram API if the bot is not initialized
        if not self.telegram_bot:
            await self._send_telegram_notification_direct(user_id, title, message, action_url)

    async def notify_deal_confirmed(self, user_id: int, deal_code: str, amount: float, currency: str):
        """Notify about a deal confirmed by an admin."""
        title = "✅ Deal confirmed"
        message = f"Deal {deal_code} was confirmed by admin. Amount: {amount} {currency}\n\nFunds were moved to escrow and are waiting for delivery."
        from .url_utils import deal_url
        action_url = deal_url(deal_code)

        await self.create_notification(user_id, "deal_confirmed", title, message, action_url)

    async def notify_payment_confirmed_admin(self, deal_code: str, amount: float, currency: str, tx_hash: str = None):
        """Notify both parties that an admin confirmed the payment."""
        try:
            # Fetch deal data
            from .database import db
            deal = db.get_deal(deal_code)
            if not deal:
                logger.error(f"Deal {deal_code} not found for admin-confirmation notifications")
                return

            buyer_id = deal['buyer_id']
            seller_id = deal.get('seller_id')

            # Buyer notification
            buyer_title = "💰 Payment confirmed"
            buyer_message = (
                f"✅ <b>Payment confirmed!</b>\n\n"
                f"┌─ 💎 Deal code: {deal_code}\n"
                f"├─ 💵 Amount: {amount} {currency}\n"
                f"└─ 🔗 Status: Payment confirmed by admin\n\n"
                f"📦 Next: wait for seller to confirm delivery, then confirm receipt to release funds.\n\n"
                f"🔒 Funds are protected by escrow!"
            )
            
            try:
                from .url_utils import deal_url
                buyer_action_url = deal_url(deal_code)
                # Create notification in database first
                await self.create_notification(buyer_id, "payment_confirmed_admin", buyer_title, buyer_message, buyer_action_url, send_telegram=False)
                
                # Use the unified notification method for reliable delivery
                await self._send_telegram_notification(buyer_id, buyer_title, buyer_message, buyer_action_url)
                
                logger.info(f"Payment confirmation sent to buyer {buyer_id} for deal {deal_code}")
            except Exception as e:
                logger.error(f"Failed to send payment confirmation to buyer {buyer_id}: {e}")
                # Try direct API as final fallback
                try:
                    from .url_utils import deal_url
                    await self._send_telegram_notification_direct(buyer_id, buyer_title, buyer_message, deal_url(deal_code))
                except Exception as direct_error:
                    logger.error(f"Direct API also failed for buyer {buyer_id}: {direct_error}")

            # Seller notification
            if seller_id:
                _, commission, seller_amount = get_commission_breakdown(amount)
                
                seller_title = "📦 Confirm delivery"
                seller_message = (
                    f"💰 <b>Payment confirmed!</b>\n\n"
                    f"┌─ 💎 Deal code: {deal_code}\n"
                    f"├─ 💵 Amount to receive: {seller_amount:.4f} {currency}\n"
                    f"├─ 💸 Commission: {commission:.4f} {currency}\n"
                    f"└─ 🔗 Status: Payment confirmed by admin\n\n"
                    f"📦 Next: deliver the goods/service to the buyer and confirm delivery.\n\n"
                    f"🔒 Payment is protected by escrow!"
                )
                
                try:
                    from .url_utils import deal_url
                    seller_action_url = deal_url(deal_code)
                    # Create notification in database first
                    await self.create_notification(seller_id, "payment_confirmed_admin", seller_title, seller_message, seller_action_url, send_telegram=False)
                    
                    # Use the unified notification method for reliable delivery
                    await self._send_telegram_notification(seller_id, seller_title, seller_message, seller_action_url)
                    
                    logger.info(f"Payment confirmation sent to seller {seller_id} for deal {deal_code}")
                except Exception as e:
                    logger.error(f"Failed to send payment confirmation to seller {seller_id}: {e}")
                    # Try direct API as final fallback
                    try:
                        from .url_utils import deal_url
                        await self._send_telegram_notification_direct(seller_id, seller_title, seller_message, deal_url(deal_code))
                    except Exception as direct_error:
                        logger.error(f"Direct API also failed for seller {seller_id}: {direct_error}")

            logger.info(f"Admin payment-confirmation notifications sent for deal {deal_code}")

        except Exception as e:
            logger.error(f"Error in notify_payment_confirmed_admin for {deal_code}: {e}")

    async def _send_telegram_notification_direct(self, user_id: int, title: str, message: str, action_url: str = None, custom_keyboard=None):
        """Send a notification to Telegram directly via the API."""
        try:
            import aiohttp
            from shared.config import BOT_TOKEN

            if not BOT_TOKEN:
                logger.warning(f"BOT_TOKEN not configured, cannot send direct Telegram notification to user {user_id}")
                return

            # Ensure action_url is a full URL for Telegram compatibility
            if action_url and action_url.startswith('/'):
                from .url_utils import construct_full_url
                action_url = construct_full_url(action_url)

            # Build notification text (do not prepend a header when title is intentionally empty).
            if title and str(title).strip():
                telegram_message = f"🔔 {title}\n\n{message}"
            else:
                telegram_message = message

            # Add a button if action_url is provided
            keyboard = None
            if action_url:
                user_language = db.get_user_language(user_id) or localization.default_language
                open_text = localization.get_text("button_open", user_language)
                keyboard = {
                    "inline_keyboard": [[{
                        "text": open_text,
                        "url": action_url
                    }]]
                }
            
            # Use custom_keyboard if provided, but only if it doesn't conflict with action_url
            if custom_keyboard:
                # Convert InlineKeyboardMarkup to dictionary format for JSON serialization
                try:
                    # Try to convert InlineKeyboardMarkup to JSON-serializable format
                    if hasattr(custom_keyboard, 'inline_keyboard'):
                        # Convert InlineKeyboardMarkup manually
                        keyboard = {
                            "inline_keyboard": []
                        }
                        for row in custom_keyboard.inline_keyboard:
                            row_dicts = []
                            for button in row:
                                button_dict = {"text": button.text}
                                if button.callback_data:
                                    button_dict["callback_data"] = button.callback_data
                                if button.url:
                                    button_dict["url"] = button.url
                                row_dicts.append(button_dict)
                            keyboard["inline_keyboard"].append(row_dicts)
                    else:
                        # If it's already a dictionary, use it directly
                        keyboard = custom_keyboard
                except Exception as conversion_error:
                    logger.warning(f"Failed to convert custom_keyboard: {conversion_error}")
                    # Fall back to default keyboard if conversion fails
                    if action_url:
                        user_language = db.get_user_language(user_id) or localization.default_language
                        open_text = localization.get_text("button_open", user_language)
                        keyboard = {
                            "inline_keyboard": [[{
                                "text": open_text,
                                "url": action_url
                            }]]
                        }
                    else:
                        keyboard = None

            # Send message via Telegram API
            async with aiohttp.ClientSession() as session:
                data = {
                    "chat_id": user_id,
                    "text": telegram_message,
                    "parse_mode": "HTML"
                }
                if keyboard:
                    data["reply_markup"] = keyboard

                async with session.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=data
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Failed to send direct Telegram notification to user {user_id}: HTTP {response.status} - {error_text}")
                    else:
                        logger.info(f"Direct Telegram notification sent successfully to user {user_id}")

        except Exception as e:
            logger.error(f"Error sending direct Telegram notification to user {user_id}: {e}")

    def send_telegram_notification_sync(
        self,
        user_id: int,
        title: str,
        message: str,
        action_url: str = None,
        custom_keyboard=None,
        timeout: float = 10.0,
    ) -> bool:
        """Send a Telegram notification synchronously (useful for sync Flask handlers)."""
        try:
            import requests
            from shared.config import BOT_TOKEN

            if not BOT_TOKEN:
                logger.warning(f"BOT_TOKEN not configured, cannot send Telegram notification to user {user_id}")
                return False

            # Ensure action_url is a full URL for Telegram compatibility
            if action_url and action_url.startswith('/'):
                from .url_utils import construct_full_url
                action_url = construct_full_url(action_url)

            # Build notification text (do not prepend a header when title is intentionally empty).
            if title and str(title).strip():
                telegram_message = f"🔔 {title}\n\n{message}"
            else:
                telegram_message = message

            keyboard = None
            if action_url:
                user_language = db.get_user_language(user_id) or localization.default_language
                open_text = localization.get_text("button_open", user_language)
                keyboard = {
                    "inline_keyboard": [[{
                        "text": open_text,
                        "url": action_url
                    }]]
                }

            if custom_keyboard:
                try:
                    if hasattr(custom_keyboard, 'inline_keyboard'):
                        keyboard = {"inline_keyboard": []}
                        for row in custom_keyboard.inline_keyboard:
                            row_dicts = []
                            for button in row:
                                button_dict = {"text": button.text}
                                if getattr(button, "callback_data", None):
                                    button_dict["callback_data"] = button.callback_data
                                if getattr(button, "url", None):
                                    button_dict["url"] = button.url
                                row_dicts.append(button_dict)
                            keyboard["inline_keyboard"].append(row_dicts)
                    else:
                        keyboard = custom_keyboard
                except Exception as conversion_error:
                    logger.warning(f"Failed to convert custom_keyboard: {conversion_error}")

            data = {
                "chat_id": user_id,
                "text": telegram_message,
                "parse_mode": "HTML",
            }
            if keyboard:
                data["reply_markup"] = keyboard

            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=data,
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.error(
                    "Failed to send sync Telegram notification to user %s: HTTP %s - %s",
                    user_id,
                    resp.status_code,
                    resp.text,
                )
                return False

            logger.info("Sync Telegram notification sent successfully to user %s", user_id)
            return True

        except Exception as e:
            logger.error(f"Error sending sync Telegram notification to user {user_id}: {e}")
            return False

# Global notification manager instance
notification_manager = NotificationManager()

# Backward-compatible name expected by other modules
NotificationService = NotificationManager

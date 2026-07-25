import logging
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from aiogram import Dispatcher
from aiogram.dispatcher.filters.builtin import Text
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InputFile

from shared.localization import localization
from shared.database import db
from shared.config import PUBLIC_BASE_URL, BOT_USERNAME
from shared.constants import DEFAULT_COMMISSION_RATE, DEFAULT_CURRENCY, SUPPORTED_CURRENCIES
from shared.commission import get_commission_breakdown
from shared.decentralized_payments import decentralized_payment_processor
from shared.constants import ADMIN_ID
from shared.database.disputes import dispute_manager
from shared.notifications import notification_manager
from web.utils import generate_deal_code, validation_utils, deal_utils
from bot.utils.formatting import format_welcome_message, format_deal_info, format_deal_summary, format_deal_creation_progress
import asyncio
from bot.security.zero_trust_security import security_manager, AuthorizationError, StateValidationError

logger = logging.getLogger(__name__)

# Unified callback prefixes to avoid conflicts
UNIFIED_PREFIXES = {
    'deal': 'ud_',      # unified deal
    'nav': 'un_',       # unified navigation
    'profile': 'up_',   # unified profile
    'start': 'us_',     # unified start
    'state': 'ust_',    # unified state
    'error': 'ue_',     # unified error
    'admin': 'ua_',     # admin dispute management
    'support': 'usup_',  # support chat
}


class ConsolidatedErrorHandler:
    """Centralized error handling for all bot operations."""

    @staticmethod
    async def handle_error(update: Union[Message, CallbackQuery], error: Exception,
                          context: str = "general", language: str = 'en') -> None:
        """Handle errors with appropriate user feedback and logging."""
        user_id = update.from_user.id if update else "unknown"

        logger.error(
            f"Error in {context} for user {user_id}: {error}",
            exc_info=(type(error), error, error.__traceback__),
        )

        error_messages = {
            'deal_creation': localization.get_text('error_creating_deal_fallback', language),
            'deal_join': localization.get_text('error_joining_deal_fallback', language),
            'deal_view': localization.get_text('error_loading_deal_details', language),
            'deal_management': localization.get_text('error_loading_deal_details', language),
            'navigation': localization.get_text('error_loading_deal_details', language),
            'profile': localization.get_text('error_loading_deal_details', language),
            'start': localization.get_text('error_loading_deal_details', language),
            'help': localization.get_text('error_loading_deal_details', language),
            'general': localization.get_text('error_loading_deal_details', language)
        }

        error_text = error_messages.get(context, error_messages['general'])

        try:
            if isinstance(update, CallbackQuery):
                await update.answer(error_text, show_alert=True)
            elif isinstance(update, Message):
                await update.reply(error_text)
        except Exception as send_error:
            logger.error(f"Failed to send error message to user {user_id}: {send_error}")
            # Try to send a minimal fallback error message
            try:
                if isinstance(update, CallbackQuery):
                    await update.answer("❌ Error occurred", show_alert=True)
            except Exception as fallback_error:
                logger.error(f"Failed to send fallback error message to user {user_id}: {fallback_error}")

    @staticmethod
    def log_operation(operation: str, user_id: int, success: bool, details: str = "") -> None:
        """Log bot operations for monitoring."""
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"[{status}] {operation} - User: {user_id} - {details}")


class UnifiedKeyboardFactory:
    """Factory for creating unified keyboards across all bot functionalities."""

    @staticmethod
    def create_main_menu_keyboard(language: str = 'en', user_id: int = None) -> InlineKeyboardMarkup:
        """Create streamlined main menu keyboard with minimal inline options."""
        buttons = [
            [InlineKeyboardButton(
                text=localization.get_text('language', language),
                callback_data=f"{UNIFIED_PREFIXES['start']}language"
            )],
            [InlineKeyboardButton(
                text=localization.get_text('login_website', language),
                callback_data=f"{UNIFIED_PREFIXES['start']}login_website"
            )]
        ]

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def create_navigation_keyboard(current_section: str, language: str = 'en',
                                 context: Dict[str, Any] = None) -> InlineKeyboardMarkup:
        """Create context-aware navigation keyboard."""
        keyboard_buttons = []
        context = context or {}

        if current_section == "deals":
            keyboard_buttons.extend([
                [InlineKeyboardButton(text=localization.get_text('button_active_deals', language), callback_data=f"{UNIFIED_PREFIXES['nav']}active_deals")],
                [InlineKeyboardButton(text=localization.get_text('button_completed', language), callback_data=f"{UNIFIED_PREFIXES['nav']}completed_deals")],
                [InlineKeyboardButton(text=localization.get_text('button_search', language), callback_data=f"{UNIFIED_PREFIXES['nav']}search_deals")]
            ])

        elif current_section == "profile":
            keyboard_buttons.extend([
                [InlineKeyboardButton(text=localization.get_text('button_statistics', language), callback_data=f"{UNIFIED_PREFIXES['nav']}profile_stats")],
                [InlineKeyboardButton(text=localization.get_text('button_settings', language), callback_data=f"{UNIFIED_PREFIXES['nav']}settings")]
            ])

        elif current_section == "create_deal":
            keyboard_buttons.extend([
                [InlineKeyboardButton(text=localization.get_text('button_set_amount', language), callback_data=f"{UNIFIED_PREFIXES['deal']}set_amount")],
                [InlineKeyboardButton(text=localization.get_text('button_add_description', language), callback_data=f"{UNIFIED_PREFIXES['deal']}add_description")],
                [InlineKeyboardButton(text=localization.get_text('button_create_now', language), callback_data=f"{UNIFIED_PREFIXES['deal']}create_confirm")]
            ])

        # Always add back button if not in main
        if current_section != "main":
            keyboard_buttons.append([InlineKeyboardButton(
                text=localization.get_text('back', language),
                callback_data=f"{UNIFIED_PREFIXES['nav']}main"
            )])

        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    @staticmethod
    def create_language_selection_keyboard(current_lang: str = 'en') -> InlineKeyboardMarkup:
        """Create language selection keyboard."""
        languages = localization.get_available_languages()
        buttons = []

        for lang_code, lang_name in languages.items():
            display_name = f"✅ {lang_name}" if lang_code == current_lang else lang_name
            buttons.append(InlineKeyboardButton(
                text=display_name,
                callback_data=f"{UNIFIED_PREFIXES['start']}lang_{lang_code}"
            ))

        return InlineKeyboardMarkup(inline_keyboard=[buttons])

    @staticmethod
    def create_confirmation_keyboard(action: str, language: str = 'en') -> InlineKeyboardMarkup:
        """Create confirmation dialog keyboard."""
        confirm_text = {
            'cancel_deal': '✅ Confirm Cancel',
            'complete_deal': '✅ Confirm Complete',
            'delete_notification': '🗑️ Delete',
            'ban_user': '🚫 Ban User',
            'unban_user': '✅ Unban User'
        }.get(action, '✅ Confirm')

        cancel_text = localization.get_text('cancel', language)

        keyboard_buttons = [
            [InlineKeyboardButton(text=confirm_text, callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_{action}"),
             InlineKeyboardButton(text=cancel_text, callback_data=f"{UNIFIED_PREFIXES['state']}cancel_action")]
        ]

        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    @staticmethod
    def create_pagination_keyboard(current_page: int, total_pages: int,
                                 prefix: str = "page") -> InlineKeyboardMarkup:
        """Create pagination keyboard for lists."""
        keyboard_buttons = []
        row = []

        if current_page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Previous",
                callback_data=f"{UNIFIED_PREFIXES['nav']}{prefix}_{current_page - 1}"
            ))

        row.append(InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data="noop"
        ))

        if current_page < total_pages:
            row.append(InlineKeyboardButton(
                text="Next ➡️",
                callback_data=f"{UNIFIED_PREFIXES['nav']}{prefix}_{current_page + 1}"
            ))

        if row:
            keyboard_buttons.append(row)

        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    @staticmethod
    def create_welcome_inline_keyboard(language: str) -> InlineKeyboardMarkup:
        """Create welcome screen inline keyboard."""
        buttons = [
            InlineKeyboardButton(text=localization.get_text('language', language), callback_data=f"{UNIFIED_PREFIXES['start']}language"),
            InlineKeyboardButton(text=localization.get_text('login_website', language), callback_data=f"{UNIFIED_PREFIXES['start']}login_website")
        ]
        return InlineKeyboardMarkup(inline_keyboard=[buttons])

    @staticmethod
    def create_main_reply_keyboard(language: str, user_id: int = None) -> ReplyKeyboardMarkup:
        """Create persistent reply keyboard with main actions."""
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)

        # Main user actions
        keyboard.add(KeyboardButton(text=localization.get_text('create_deal', language)))
        keyboard.add(KeyboardButton(text=localization.get_text('join_deal', language)))
        keyboard.add(KeyboardButton(text=localization.get_text('profile', language)))

        return keyboard


class UnifiedBotHandler:
    """Unified handler for all bot functionalities with consolidated state management."""

    def __init__(self):
        # Centralized conversation states
        self.conversation_states: Dict[int, Dict[str, Any]] = {}

        # Navigation breadcrumb system
        self.breadcrumb_trail: Dict[int, List[str]] = {}

        # Rate limiting for support messages: user_id -> List[float]
        self.support_message_timestamps: Dict[int, List[float]] = {}

        # Track which users have already received sharing messages for deals
        # Format: {(user_id, deal_code): True}
        self.shared_deal_messages_sent: set[tuple[int, str]] = set()

        # Admin payment simulation:
        # - first "Payment sent" press: show "not found" UI without blockchain lookup
        # - second press (refresh): confirm immediately
        self._admin_payment_refresh_ready: set[str] = set()

        # Initialize helper classes
        self.keyboard_factory = UnifiedKeyboardFactory()
        self.error_handler = ConsolidatedErrorHandler()

        logger.info("UnifiedBotHandler initialized")

    def _t(self, key: str, language: Optional[str] = None, user_id: Optional[int] = None, **kwargs) -> str:
        """Small helper to fetch localized text for a user.

        Priority:
        1) explicit `language`
        2) conversation state language (`state['language']`)
        3) DB language fallback
        """
        lang = language
        if not lang and user_id is not None:
            try:
                lang = self._get_user_state(user_id).get('language')
            except Exception:
                lang = None

        if not lang and user_id is not None:
            try:
                lang = self._get_user_language(user_id)
            except Exception:
                lang = None

        lang = lang or 'en'
        try:
            return localization.get_text(key, lang, **kwargs)
        except Exception:
            # Fail-safe: don't break UI if translations have issues
            return f"[missing:{key}]"

    # ===== STATE MANAGEMENT METHODS =====

    def _get_user_state(self, user_id: int) -> Dict[str, Any]:
        """Get user's conversation state."""
        return self.conversation_states.get(user_id, {})

    def _set_user_state(self, user_id: int, state: Dict[str, Any]) -> None:
        """Set user's conversation state."""
        self.conversation_states[user_id] = state

    def _update_user_state(self, user_id: int, updates: Dict[str, Any]) -> None:
        """Update user's conversation state."""
        if user_id not in self.conversation_states:
            self.conversation_states[user_id] = {}
        self.conversation_states[user_id].update(updates)

    def _clear_user_state(self, user_id: int) -> None:
        """Clear user's conversation state."""
        if user_id in self.conversation_states:
            del self.conversation_states[user_id]

    # ===== ZERO TRUST SECURITY HELPERS =====

    async def _zt_enforce_rate_limit(self, update: Union[Message, CallbackQuery], language: str) -> bool:
        """Apply Zero Trust rate limiting to user actions."""
        try:
            user_id = update.from_user.id if update and update.from_user else None
            if not user_id:
                return True

            if security_manager.check_rate_limit(user_id):
                return True

            rate_text = (
                localization.get_text('rate_limit_exceeded', language)
                if localization else
                "❌ <b>Rate limit exceeded</b>\n\nPlease wait a bit and try again."
            )

            if isinstance(update, CallbackQuery):
                await update.answer(rate_text, show_alert=True)
            else:
                await update.reply(rate_text, parse_mode='HTML')
            return False
        except Exception:
            return True

    def _zt_validate_deal(
        self,
        user_id: int,
        deal_code: str,
        required_role: Optional[str] = None,
        allowed_states: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Zero Trust: validate deal access and (optionally) state."""
        deal = security_manager.validate_deal_access(user_id, deal_code, required_role=required_role)
        if allowed_states:
            security_manager.validate_deal_state(deal, allowed_states)
        return deal

    # ===== PAYMENT MONITORING METHODS =====

    async def _monitor_payment_status(self, deal_code: str, buyer_id: int, seller_id: Optional[int] = None) -> None:
        """Monitor payment status for a deal and notify users when payment is confirmed."""
        try:
            logger.info(f"Starting payment monitoring for deal {deal_code}")

            # Admin should not auto-skip payment stage and should not trigger blockchain polling.
            if buyer_id == ADMIN_ID:
                logger.info(f"Skipping payment monitoring for admin buyer in deal {deal_code}")
                return

            # Get the checkout ID for this deal using the new database method
            payment = db.get_decentralized_payment_by_deal_code(deal_code)
            if not payment:
                logger.error(f"No decentralized payment found for deal {deal_code}")
                return

            checkout_id = payment.get('checkout_id')
            if not checkout_id:
                logger.error(f"No checkout ID found in payment record for deal {deal_code}")
                return

            logger.info(f"Monitoring payment for checkout {checkout_id} (deal {deal_code})")

            # Monitor for up to 24 hours (checking every 30 seconds)
            max_checks = 2880  # 24 hours * 60 minutes * 2 checks per minute
            check_count = 0

            while check_count < max_checks:
                try:
                    # Stop monitoring once deal is no longer awaiting payment
                    try:
                        current_deal = db.get_deal(deal_code)
                        if current_deal and current_deal.get('status') != 'active':
                            logger.info(
                                f"Stopping payment monitoring for {deal_code}: status={current_deal.get('status')}"
                            )
                            break
                    except Exception:
                        pass

                    # Check payment status using enhanced processor with correct checkout ID
                    is_paid, tx_hash = decentralized_payment_processor.check_payment_status(checkout_id, buyer_id)

                    if is_paid:
                        logger.info(f"Payment confirmed for deal {deal_code}, TX: {tx_hash}")

                        # Update deal status
                        db.update_deal_status(deal_code, 'funded')

                        # Notify both parties
                        await self._notify_payment_confirmed(deal_code, buyer_id, seller_id, tx_hash)
                        break

                    # Wait 30 seconds before next check
                    await asyncio.sleep(30)
                    check_count += 1

                except Exception as check_error:
                    logger.warning(f"Error checking payment status for {deal_code}: {check_error}")
                    await asyncio.sleep(60)  # Wait longer on error
                    check_count += 2

            if check_count >= max_checks:
                logger.warning(f"Payment monitoring timeout for deal {deal_code}")

        except Exception as e:
            logger.error(f"Error in payment monitoring for deal {deal_code}: {e}")

    async def _notify_payment_confirmed(self, deal_code: str, buyer_id: int, seller_id: Optional[int], tx_hash: str) -> None:
        """Notify users when payment is confirmed."""
        try:
            from shared.notifications import notification_manager

            deal = db.get_deal(deal_code)
            if not deal:
                return

            currency_display = "USDT (TRC20)" if deal['currency'] == "USDT" else deal['currency'].upper()

            # Notify buyer with enhanced message
            language = self._get_user_language(buyer_id)
            buyer_message = (
                f"{localization.get_text('payment_confirmed_buyer_title', language)}\n\n"
                f"{localization.get_text('payment_confirmed_buyer_code', language, code=deal_code)}\n"
                f"{localization.get_text('payment_confirmed_buyer_amount', language, amount=deal['amount'], currency=currency_display)}\n"
                f"{localization.get_text('payment_confirmed_buyer_commission', language, tx_hash=str(tx_hash)[:10]+'...')}\n\n"
                f"{localization.get_text('payment_confirmed_buyer_progress', language)}\n\n"
                f"{localization.get_text('payment_confirmed_buyer_step_created', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_step_joined', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_step_paid', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_step_delivery', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_step_receipt', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_step_withdrawal', language)}\n\n"
                f"{localization.get_text('payment_confirmed_buyer_next_steps', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_next_delivery', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_next_confirm', language)}\n"
                f"{localization.get_text('payment_confirmed_buyer_next_release', language)}\n\n"
                f"{localization.get_text('payment_confirmed_buyer_guarantee', language)}"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="👁️ View Deal",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                )]
            ])

            # Use notification manager for reliable delivery
            await notification_manager.create_notification(
                user_id=buyer_id,
                notification_type="payment_confirmed",
                title="💰 Payment confirmed",
                message=buyer_message,
                action_url=f"/deal/{deal_code}",
                custom_keyboard=keyboard
            )

            # Notify seller with buyer username and a "Deliver item" button
            if seller_id:
                seller_language = self._get_user_language(seller_id)
                buyer = db.get_user(buyer_id) or {}
                buyer_username = buyer.get('username') or buyer.get('first_name') or f"ID: {buyer_id}"
                
                seller_message = (
                    f"{localization.get_text('payment_received_seller_title', seller_language)}\n\n"
                    f"{localization.get_text('payment_received_seller_code', seller_language, code=deal_code)}\n"
                    f"{localization.get_text('payment_received_seller_amount', seller_language, amount=deal['amount'], currency=currency_display)}\n"
                    f"{localization.get_text('payment_received_seller_buyer', seller_language, buyer_username=buyer_username)}\n"
                    f"{localization.get_text('payment_received_seller_tx', seller_language, tx_hash=str(tx_hash)[:10]+'...')}\n\n"
                    f"{localization.get_text('payment_received_seller_progress', seller_language)}\n\n"
                    f"{localization.get_text('payment_received_seller_step_created', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_step_joined', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_step_paid', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_step_delivery', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_step_receipt', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_step_withdrawal', seller_language)}\n\n"
                    f"{localization.get_text('payment_received_seller_next_steps', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_next_deliver', seller_language, buyer_username=buyer_username)}\n"
                    f"{localization.get_text('payment_received_seller_next_confirm', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_next_wait', seller_language)}\n"
                    f"{localization.get_text('payment_received_seller_next_receive', seller_language)}\n\n"
                    f"{localization.get_text('payment_received_seller_guarantee', seller_language)}"
                )

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=localization.get_text('button_confirm_delivery', seller_language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_delivery:{deal_code}"
                    )],
                    [InlineKeyboardButton(
                        text=localization.get_text('button_view_deal', seller_language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                    )]
                ])

                # Use notification manager for reliable delivery
                await notification_manager.create_notification(
                    user_id=seller_id,
                    notification_type="payment_received",
                    title="💰 Payment confirmed",
                    message=seller_message,
                    action_url=f"/deal/{deal_code}",
                    custom_keyboard=keyboard
                )

            logger.info(f"Payment confirmation notifications sent for deal {deal_code}")

        except Exception as e:
            logger.error(f"Error sending payment confirmation notifications for {deal_code}: {e}")

    def _get_user_language(self, user_id: int) -> str:
        """Get user's preferred language."""
        return db.get_user_language(user_id)

    async def _send_telegram_notification(self, user_id: int, title: str, message: str, action_url: str = None, custom_keyboard=None):
        """Send a notification to Telegram."""
        try:
            # Always try direct API first for reliability in async contexts
            await self._send_telegram_notification_direct(user_id, title, message, action_url, custom_keyboard)
            return

        except Exception as e:
            logger.warning(f"Direct API notification failed for user {user_id}, trying bot instance: {e}")
            
            # Try bot instance as fallback if available
            if hasattr(self, 'telegram_bot') and self.telegram_bot:
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
                        user_language = self._get_user_language(user_id) or 'en'
                        open_text = localization.get_text('button_open', user_language)
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

    async def _send_telegram_notification_direct(self, user_id: int, title: str, message: str, action_url: str = None, custom_keyboard=None):
        """Send a notification to Telegram directly via the API."""
        try:
            import aiohttp
            from shared.config import BOT_TOKEN, PUBLIC_BASE_URL

            if not BOT_TOKEN:
                logger.warning(f"BOT_TOKEN not configured, cannot send direct Telegram notification to user {user_id}")
                return

            # Ensure action_url is a full URL for Telegram compatibility
            if action_url and action_url.startswith('/'):
                action_url = f"{PUBLIC_BASE_URL.rstrip('/')}{action_url}"

            # Build notification text
            telegram_message = f"🔔 {title}\n\n{message}"

            # Add a button if action_url is provided
            keyboard = None
            if action_url:
                user_language = self._get_user_language(user_id) or 'en'
                open_text = localization.get_text('button_open', user_language)
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
                        user_language = self._get_user_language(user_id) or 'en'
                        open_text = localization.get_text('button_open', user_language)
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

    async def create_notification(self, user_id: int, notification_type: str, title: str,
                                message: str, action_url: str = None, send_telegram: bool = True,
                                custom_keyboard=None) -> bool:
        """Create a notification and send it to Telegram if needed."""
        try:
            # Create notification in database
            success = db.create_notification(user_id, notification_type, title, message, action_url)

            if success and send_telegram:
                try:
                    # Send via Telegram using the notification manager
                    await self._send_telegram_notification(user_id, title, message, action_url, custom_keyboard)
                except Exception as telegram_error:
                    logger.error(f"Failed to send Telegram notification for user {user_id}: {telegram_error}")
                    # Continue without failing the entire notification creation

            return success
        except Exception as e:
            logger.error(f"Error creating notification for user {user_id}: {e}")
            return False
    
    def _format_clickable_address(self, address: str, language: str) -> str:
        """
        Format payment address for display.
        
        Args:
            address: The wallet address to format
            language: User's language for localization
            
        Returns:
            Formatted address with copy instructions
        """
        if not address or address == 'Not specified':
            return address
        
        # Telegram doesn't support the copy: protocol in HTML
        # Return the address in a code block for better visibility
        try:
            copy_text = localization.get_text('click_to_copy', language) if localization else "Click to copy"
        except Exception:
            copy_text = "Click to copy"
        return f'<code>{address}</code>\n{copy_text}'

    def _check_support_rate_limit(self, user_id: int) -> bool:
        """
        Check if user has exceeded support message rate limit.
        
        Returns:
            bool: True if rate limit exceeded, False otherwise
        """
        try:
            from time import time
            current_time = time()
            
            # Get or initialize user's message timestamps
            if user_id not in self.support_message_timestamps:
                self.support_message_timestamps[user_id] = []
            
            timestamps = self.support_message_timestamps[user_id]
            
            # Remove old timestamps (older than 5 seconds)
            window_start = current_time - 5.0  # 5 second window
            timestamps = [t for t in timestamps if t >= window_start]
            self.support_message_timestamps[user_id] = timestamps
            
            # Check if user has sent a message in the last 5 seconds
            if len(timestamps) >= 1:
                # Rate limit exceeded - user can only send 1 message every 5 seconds
                return True
            
            # Add current timestamp
            timestamps.append(current_time)
            
            return False
        except Exception as e:
            logger.error(f"Error checking rate limit for user {user_id}: {e}")
            return False

    async def handle_admin_deal_paid_callback(self, callback: CallbackQuery) -> None:
        """
        ADMIN fast-path handler for 'deal_paid:{deal_code}' callbacks.

        Behavior:
        - Only ADMIN_ID is allowed to use this path.
        - Immediately marks deal as paid / escrow funded without on-chain verification.
        - Reuses existing payment confirmation side-effects via _notify_payment_confirmed.
        - Non-admins are rejected and do not trigger payment checks.
        - Idempotent: if already marked as paid (or equivalent), responds gracefully.
        """
        try:
            user_id = callback.from_user.id
            data = callback.data or ""

            if not isinstance(data, str) or not data.startswith("deal_paid:"):
                await callback.answer()
                return

            # Enforce admin-only usage
            if user_id != ADMIN_ID:
                language = self._get_user_language(user_id)
                await callback.answer(
                    localization.get_text('confirmation_path_restricted', language),
                    show_alert=True
                )
                return

            # Extract deal code
            deal_code = data.split(":", 1)[1].strip().upper()
            if not deal_code:
                await callback.answer("❌ Invalid deal code.", show_alert=True)
                return

            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found.", show_alert=True)
                return

            # Ensure both parties exist
            buyer_id = deal.get('buyer_id')
            seller_id = deal.get('seller_id')
            if not buyer_id or not seller_id:
                await callback.answer(
                    "❌ Deal must have both buyer and seller to confirm payment.",
                    show_alert=True
                )
                return

            status = str(deal.get('status', '')).lower()

            # Idempotent if already funded / payment already confirmed
            if status in ("funded", "payment_confirmed", "escrow_funded"):
                await callback.answer(
                    "✅ Payment already confirmed for this deal.",
                    show_alert=True
                )
                return

            # Only allow from payable states
            if status not in ("active", "pending"):
                await callback.answer(
                    "❌ Deal is not in a payable state.",
                    show_alert=True
                )
                return

            # Mark deal as funded (escrow funded) immediately
            updated = db.update_deal_status(deal_code, "funded")
            if not updated:
                await callback.answer(
                    "❌ Failed to update deal status.",
                    show_alert=True
                )
                return

            # Trigger comprehensive admin payment confirmation notifications
            try:
                from shared.notifications import notification_manager
                import asyncio
                
                # Get deal details for comprehensive notification
                deal = db.get_deal(deal_code)
                if deal:
                    asyncio.create_task(notification_manager.notify_payment_confirmed_admin(
                        deal_code=deal_code,
                        amount=deal['amount'],
                        currency=deal['currency'],
                        tx_hash="ADMIN_CONFIRMED"
                    ))
                    logger.info(f"Admin payment confirmation notifications sent for deal {deal_code}")
                else:
                    logger.warning(f"Deal {deal_code} not found for admin payment confirmation")
            except Exception as notify_err:
                logger.error(
                    f"Error in admin fast-path payment notifications for {deal_code}: {notify_err}"
                )

            # Edit admin's message to reflect success (best-effort)
            try:
                language = self._get_user_language(user_id)
                if localization and hasattr(localization, "get_text"):
                    success_text = localization.get_text(
                        "payment_confirmed_admin_fastpath",
                        language,
                        code=deal_code
                    )
                else:
                    success_text = (
                        f"✅ Payment for deal {deal_code} has been confirmed by admin.\n\n"
                        f"💰 Standard payment-confirmed notifications have been sent.\n"
                        f"📦 Seller is instructed to proceed with the deal."
                    )

                await callback.message.edit_text(
                    success_text,
                    parse_mode="HTML"
                )
            except Exception as edit_err:
                logger.warning(
                    f"Failed to edit admin payment message for {deal_code}: {edit_err}"
                )

            await callback.answer(
                "✅ Payment confirmed via admin fast-path.",
                show_alert=True
            )

        except Exception as e:
            logger.error(f"Error in handle_admin_deal_paid_callback: {e}")
            try:
                await callback.answer("❌ Error confirming payment.", show_alert=True)
            except Exception:
                pass

    async def _notify_buyer_deal_joined(self, deal_code: str, deal: dict, payment_result: dict,
                                      language: str, seller_id: int) -> None:
        """
        Send comprehensive buyer notification when seller joins deal.

        Note:
        - 'language' parameter is kept for backward compatibility but MUST NOT be used
          for buyer-facing text in this notification.
        - Buyer-facing text MUST always use the buyer's own language settings.
        """
        try:
            logger.info(f"Sending buyer notification for deal {deal_code}")

            # Determine buyer and their language (authoritative for this notification)
            buyer_id = deal.get('buyer_id')
            buyer_language = self._get_user_language(buyer_id) if buyer_id else 'en'

            # Import notification manager
            from shared.notifications import notification_manager

            # Get deal data with error checking
            deal_obj = db.get_deal(deal_code)
            if not deal_obj:
                logger.error(f"Deal {deal_code} not found when sending buyer notification")
                return

            # Get payment address from ENV (system wallet address)
            from shared.config import USDT_WALLET_ADDRESS, TON_WALLET_ADDRESS
            currency = deal.get('currency', 'USDT')
            if currency == 'USDT':
                escrow_address = USDT_WALLET_ADDRESS
            elif currency == 'TON':
                escrow_address = TON_WALLET_ADDRESS
            else:
                escrow_address = None

            if not escrow_address:
                logger.error(f"Payment address not configured for currency {currency}")
                escrow_address = (
                    localization.get_text('not_specified', buyer_language)
                    if localization else
                    'Not specified'
                )

            # Calculate commission amounts
            settings = db.get_settings()
            commission_rate = settings.get('commission_rate', DEFAULT_COMMISSION_RATE)
            commission_amount = float(deal.get('amount', 0)) * commission_rate
            seller_amount = float(deal.get('amount', 0)) - commission_amount

            # Get currency display name
            currency_display = "USDT (TRC20)" if deal.get('currency') == "USDT" else deal.get('currency', 'USDT').upper()
            payment_memo = f"DEAL-{deal_code}" if deal.get('currency', 'USDT').upper() == "TON" else None
            memo_block = f"Memo/Comment:\n<code>{payment_memo}</code>\n\n" if payment_memo else ""

            # Create comprehensive buyer notification message with payment address
            formatted_address = self._format_clickable_address(escrow_address, buyer_language)
            buyer_info = (
                f"{localization.get_text('seller_joined_deal_title', buyer_language)}\n\n"
                f"{localization.get_text('seller_joined_deal_code', buyer_language, code=deal_code)}\n"
                f"{localization.get_text('seller_joined_deal_amount', buyer_language, amount=deal.get('amount', 0), currency=currency_display)}\n"
                f"{localization.get_text('seller_joined_deal_commission', buyer_language, commission=f'{commission_amount:.2f}', currency=currency_display)}\n"
                f"{localization.get_text('seller_joined_deal_seller_receives', buyer_language, seller_amount=f'{seller_amount:.2f}', currency=currency_display)}\n\n"
                f"💳 <b>{localization.get_text('payment_instructions_title', buyer_language)}</b>\n"
                f"💰 {localization.get_text('payment_amount', buyer_language, amount=deal.get('amount'), currency=currency_display)}\n"
                f"🏦 {localization.get_text('payment_address', buyer_language)}\n"
                f"{formatted_address}\n\n"
                f"{memo_block}"
                
                f"⚠️ <b>{localization.get_text('payment_warning', buyer_language)}</b>\n"
                f"• {localization.get_text('payment_warning_exact', buyer_language, amount=deal.get('amount', 0), currency=currency_display)}\n"
                f"• {localization.get_text('payment_warning_address', buyer_language)}\n"
                f"• {localization.get_text('payment_warning_confirmed', buyer_language)}\n\n"
                f"{localization.get_text('seller_joined_instructions', buyer_language)}\n"
                f"{localization.get_text('seller_joined_instruction_1', buyer_language, amount=deal.get('amount', 0), currency=currency_display)}\n"
                f"{localization.get_text('seller_joined_instruction_2', buyer_language)}\n"
                f"{localization.get_text('seller_joined_instruction_3', buyer_language)}\n"
                f"{localization.get_text('seller_joined_instruction_4', buyer_language)}\n\n"
                f"{localization.get_text('seller_joined_warning', buyer_language)}\n\n"
                f"{localization.get_text('seller_joined_deal_progress', buyer_language)}\n\n"
                f"{localization.get_text('seller_joined_deal_step_created', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_step_joined', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_step_waiting_payment', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_step_delivery', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_step_receipt', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_step_withdrawal', buyer_language)}\n\n"
                f"{localization.get_text('seller_joined_deal_next_steps', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_next_wait_payment', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_next_deliver', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_next_confirm_delivery', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_next_confirm_receipt', buyer_language)}\n"
                f"{localization.get_text('seller_joined_deal_next_receive_funds', buyer_language, seller_amount=f'{seller_amount:.2f}', currency=currency_display)}\n\n"
                f"{localization.get_text('seller_joined_deal_guarantee', buyer_language)}"
            )

            # Create action keyboard with payment method selection
            keyboard_buttons = []

            # Add direct payment button
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="💳 Pay",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}payment_method:{deal_code}"
                )
            ])

            # Add view deal button
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=localization.get_text('button_view_deal', buyer_language),
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                )
            ])

            # Add exit deal button (STRICTLY in buyer_language)
            try:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=localization.get_text('button_exit_deal', buyer_language) if localization else "❌ Exit deal",
                        callback_data=f"exit_deal:{deal_code}"
                    )
                ])
            except Exception as exit_error:
                logger.warning(f"Failed to add exit button: {exit_error}")

            # Create keyboard markup with proper error handling
            custom_keyboard = None
            try:
                if keyboard_buttons:
                    custom_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            except Exception as keyboard_error:
                logger.error(f"Failed to create keyboard markup for deal {deal_code}: {keyboard_error}")
                # Create a minimal keyboard with just the view deal button
                try:
                    custom_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=localization.get_text('button_view_deal', buyer_language) if localization else "View Deal",
                            callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                        )]
                    ])
                    logger.info(f"Created fallback keyboard for deal {deal_code}")
                except Exception as fallback_keyboard_error:
                    logger.error(f"Failed to create fallback keyboard for deal {deal_code}: {fallback_keyboard_error}")

            # Use notification manager for reliable delivery with fallback mechanisms
            try:
                await notification_manager.notify_deal_joined(
                    user_id=deal.get('buyer_id'),
                    deal_code=deal_code,
                    amount=float(deal.get('amount', 0)),
                    currency=deal.get('currency', 'USDT'),
                    custom_message=buyer_info,
                    custom_keyboard=custom_keyboard
                )
                logger.info(f"Buyer notification sent successfully for deal {deal_code} via notification manager")
            except Exception as notify_error:
                logger.warning(f"Notification manager failed for deal {deal_code}: {notify_error}")
                
                # Try direct notification as fallback
                try:
                    await self._send_telegram_notification_direct(
                        user_id=deal.get('buyer_id'),
                        title="🔹 Seller joined deal!",
                        message=buyer_info,
                        action_url=f"/deal/{deal_code}",
                        custom_keyboard=custom_keyboard
                    )
                    logger.info(f"Direct notification sent to buyer for deal {deal_code}")
                except Exception as direct_error:
                    logger.error(f"All notification methods failed for deal {deal_code}: {direct_error}")
                    # Create database notification only as last resort
                    try:
                        await self.create_notification(
                            user_id=deal.get('buyer_id'),
                            notification_type="deal_joined",
                            title="🔹 Seller joined deal!",
                            message=buyer_info,
                            action_url=f"/deal/{deal_code}",
                            send_telegram=False  # Don't try to send via telegram
                        )
                    except Exception as db_error:
                        logger.error(f"Database notification also failed for deal {deal_code}: {db_error}")

        except Exception as e:
            logger.error(f"Critical error in buyer notification for deal {deal_code}: {e}")
            # Don't re-raise the exception to avoid breaking the deal join flow
            # But ensure we log the error properly for debugging
            import traceback
            logger.error(f"Full traceback for deal {deal_code}:\n{traceback.format_exc()}")

    def _set_user_language(self, user_id: int, language: str) -> None:
        """Set user's preferred language."""
        db.set_user_language(user_id, language)

    def _create_user_if_not_exists(self, user_id: int, username: str = None,
                                 first_name: str = None) -> None:
        """Create user record if doesn't exist."""
        user = db.get_user(user_id)
        if not user:
            db.create_user(user_id, username, first_name)
            logger.info(f"Created new user: {user_id}")

    async def _block_banned_user(self, update: Union[Message, CallbackQuery]) -> bool:
        """Return True if user is banned and response was sent."""
        try:
            user_id = update.from_user.id if update and update.from_user else None
            if not user_id:
                return False

            user = db.get_user(user_id)
            if not user or not user.get('is_banned'):
                return False

            language = user.get('language') or self._get_user_language(user_id)
            ban_text = localization.get_text('account_banned', language)

            if isinstance(update, Message):
                await update.answer(ban_text, reply_markup=ReplyKeyboardRemove())
            else:
                await update.answer(ban_text, show_alert=True)

            return True
        except Exception:
            return False

    # ===== NAVIGATION METHODS =====

    def get_breadcrumb_trail(self, user_id: int) -> List[str]:
        """Get breadcrumb trail for user."""
        return self.breadcrumb_trail.get(user_id, ["main"])

    def add_breadcrumb(self, user_id: int, section: str) -> None:
        """Add section to breadcrumb trail."""
        if user_id not in self.breadcrumb_trail:
            self.breadcrumb_trail[user_id] = ["main"]

        trail = self.breadcrumb_trail[user_id]
        if section not in trail:
            trail.append(section)

        # Keep only last 5 breadcrumbs
        if len(trail) > 5:
            trail.pop(0)

    def remove_breadcrumb(self, user_id: int, section: str) -> None:
        """Remove section from breadcrumb trail."""
        if user_id in self.breadcrumb_trail:
            trail = self.breadcrumb_trail[user_id]
            if section in trail:
                trail.remove(section)

    def clear_breadcrumbs(self, user_id: int) -> None:
        """Clear breadcrumb trail for user."""
        self.breadcrumb_trail[user_id] = ["main"]

    def _get_not_assigned_text(self, language: str) -> str:
        """Get localized 'not assigned' text for sellers."""
        not_assigned_texts = {
            'en': 'Not assigned',
            'ua': 'Не призначений'
        }
        return not_assigned_texts.get(language, not_assigned_texts['en'])

    async def create_context_menu(self, user_id: int, current_section: str,
                                language: str) -> InlineKeyboardMarkup:
        """Create context-aware navigation menu."""
        return self.keyboard_factory.create_navigation_keyboard(current_section, language)

    # ===== DEAL MANAGEMENT METHODS =====

    async def handle_create_deal_start(self, update: Union[Message, CallbackQuery]) -> None:
        """Handle deal creation start with compact visual interface."""
        if await self._block_banned_user(update):
            return
        try:
            if isinstance(update, CallbackQuery):
                user_id = update.from_user.id
                message = update.message
                answer_method = update.answer
            elif isinstance(update, Message):
                user_id = update.from_user.id
                message = update
                answer_method = None
            else:
                return

            language = self._get_user_language(user_id)

            # Initialize state
            self._set_user_state(user_id, {'step': 'select_currency', 'language': language})

            # Create compact visual interface
            text = self._build_deal_creation_text(user_id)
            keyboard = self._build_deal_creation_keyboard(user_id)

            if isinstance(update, CallbackQuery):
                await message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                try:
                    self._update_user_state(
                        user_id,
                        {
                            'deal_creation_chat_id': message.chat.id,
                            'deal_creation_message_id': message.message_id,
                        },
                    )
                except Exception:
                    pass
                await answer_method()
            else:
                sent = await message.reply(text, reply_markup=keyboard, parse_mode='HTML')
                try:
                    self._update_user_state(
                        user_id,
                        {
                            'deal_creation_chat_id': sent.chat.id,
                            'deal_creation_message_id': sent.message_id,
                        },
                    )
                except Exception:
                    pass

        except Exception as e:
            await self.error_handler.handle_error(update, e, "deal_creation")

    def _build_deal_creation_text(self, user_id: int) -> str:
        """Build compact deal creation text with current progress."""
        state = self._get_user_state(user_id)
        step = state.get('step', 'select_currency')
        language = state.get('language') or self._get_user_language(user_id) or 'en'

        text = f"🛍️ <b>{self._t('deal_create_title', language=language)}</b>\n\n"

        # Use new progress bar format
        step_mapping = {
            'select_currency': 1,
            'awaiting_amount': 2,
            'awaiting_description': 3,
            'confirm': 4
        }
        current_step = step_mapping.get(step, 1)
        
        progress_bar = format_deal_creation_progress(current_step, language)
        text += f"{progress_bar}\n\n"

        # Current step content
        if step == 'select_currency':
            text += f"💰 <b>{self._t('deal_create_choose_currency_title', language=language)}</b>\n"
            text += self._t('deal_create_choose_currency_subtitle', language=language)
        elif step == 'awaiting_amount':
            from shared.constants import MIN_DEAL_AMOUNT
            from shared.currency_conversion import get_ton_usd_rate

            currency = state.get('currency', DEFAULT_CURRENCY)
            currency_upper = (currency or DEFAULT_CURRENCY).upper()
            if currency_upper == "TON":
                rate = get_ton_usd_rate()
                min_amount_value = (MIN_DEAL_AMOUNT / rate) if rate else MIN_DEAL_AMOUNT
                min_amount = f"{min_amount_value:.4f}".rstrip("0").rstrip(".")
                max_decimals = 4
            else:
                min_amount = f"{float(MIN_DEAL_AMOUNT):.2f}".rstrip("0").rstrip(".")
                max_decimals = 2

            text += f"💵 <b>{self._t('deal_create_enter_amount_title', language=language, currency=currency)}</b>\n"
            text += f"{self._t('deal_create_enter_amount_min', language=language, currency=currency, min_amount=min_amount)}\n"
            text += self._t('deal_create_enter_amount_hint', language=language)
        elif step == 'awaiting_description':
            amount = state.get('amount', 0)
            currency = state.get('currency', DEFAULT_CURRENCY)
            text += f"📝 <b>{self._t('deal_create_add_description_title', language=language)}</b>\n"
            text += f"{self._t('deal_create_add_description_amount', language=language, amount=amount, currency=currency)}\n"
            text += f"{self._t('deal_create_add_description_question', language=language)}\n"
            text += self._t('deal_create_add_description_optional', language=language)
        elif step == 'confirm':
            currency = state.get('currency', DEFAULT_CURRENCY)
            amount = state.get('amount', 0)
            description = state.get('description', '')
            desc_text = f"\n📝 {description}" if description else f"\n📝 {self._t('deal_create_no_description', language=language)}"

            amount_value = float(amount) if amount else 0.0
            _, commission_amount, seller_amount = get_commission_breakdown(amount_value)
            currency_upper = (currency or DEFAULT_CURRENCY).upper()
            decimals = 4 if currency_upper == 'TON' else 2

            text += f"✅ <b>{self._t('deal_create_confirm_title', language=language)}</b>\n"
            text += f"💰 {currency}: {amount}\n"
            text += f"💸 {self._t('deal_create_confirm_fee', language=language, fee=f'{commission_amount:.{decimals}f}', currency=currency)}{desc_text}\n\n"
            text += f"🎯 {self._t('deal_create_confirm_seller_gets', language=language, seller_amount=f'{seller_amount:.{decimals}f}', currency=currency)}"

        text += f"\n\n🛡️ <b>{self._t('deal_create_footer_protected', language=language)}</b>"
        return text

    def _build_deal_creation_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Build keyboard for current deal creation step."""
        state = self._get_user_state(user_id)
        step = state.get('step', 'select_currency')
        language = state.get('language') or self._get_user_language(user_id) or 'en'

        buttons = []

        if step == 'select_currency':
            # Currency selection
            buttons = []
            if 'USDT' in SUPPORTED_CURRENCIES:
                buttons.append([InlineKeyboardButton(text="💰 USDT (TRC20)", callback_data="ud_currency_usdt")])
            if 'TON' in SUPPORTED_CURRENCIES:
                buttons.append([InlineKeyboardButton(text="💎 TON", callback_data="ud_currency_ton")])
            if not buttons:
                buttons = [[InlineKeyboardButton(text="💎 TON", callback_data="ud_currency_ton")]]
        elif step == 'awaiting_amount':
            # Amount input prompt
            buttons = [
                [InlineKeyboardButton(text=self._t('deal_create_btn_back', language=language), callback_data="ud_back_to_currency")]
            ]
        elif step == 'awaiting_description':
            # Description input
            buttons = [
                [InlineKeyboardButton(text=self._t('deal_create_btn_skip', language=language), callback_data="ud_skip_description")],
                [InlineKeyboardButton(text=self._t('deal_create_btn_back', language=language), callback_data="ud_back_to_amount")]
            ]
        elif step == 'confirm':
            # Confirmation
            buttons = [
                [InlineKeyboardButton(text=self._t('deal_create_btn_create', language=language), callback_data="ud_create_confirm")],
                [InlineKeyboardButton(text=self._t('deal_create_btn_back', language=language), callback_data="ud_back_to_description")]
            ]

        # Add cancel option
        buttons.append([InlineKeyboardButton(text=localization.get_text('cancel', language), callback_data="un_main")])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def _is_step_completed(self, user_id: int, step: str) -> bool:
        """Check if a step is completed."""
        state = self._get_user_state(user_id)
        step_order = ['select_currency', 'awaiting_amount', 'awaiting_description', 'confirm']
        current_step = state.get('step', 'select_currency')
        current_index = step_order.index(current_step) if current_step in step_order else 0
        step_index = step_order.index(step) if step in step_order else 0
        return step_index < current_index

    async def _handle_compact_deal_action(self, callback: CallbackQuery, action: str) -> None:
        """Handle compact deal creation navigation actions."""
        try:
            user_id = callback.from_user.id
            language = self._get_user_state(user_id).get('language') or self._get_user_language(user_id) or 'en'
            
            if action == 'skip_description':
                # Skip description and go to confirm
                self._update_user_state(user_id, {'description': None, 'step': 'confirm'})
                text = self._build_deal_creation_text(user_id)
                keyboard = self._build_deal_creation_keyboard(user_id)
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                await callback.answer(self._t('deal_create_toast_description_skipped', language=language))

            elif action == 'back_to_currency':
                # Go back to currency selection
                self._update_user_state(user_id, {'step': 'select_currency'})
                text = self._build_deal_creation_text(user_id)
                keyboard = self._build_deal_creation_keyboard(user_id)
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                await callback.answer(self._t('deal_create_toast_back_to_currency', language=language))

            elif action == 'back_to_amount':
                # Go back to amount input
                self._update_user_state(user_id, {'step': 'awaiting_amount'})
                text = self._build_deal_creation_text(user_id)
                keyboard = self._build_deal_creation_keyboard(user_id)
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                await callback.answer(self._t('deal_create_toast_back_to_amount', language=language))

            elif action == 'back_to_description':
                # Go back to description input
                self._update_user_state(user_id, {'step': 'awaiting_description'})
                text = self._build_deal_creation_text(user_id)
                keyboard = self._build_deal_creation_keyboard(user_id)
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                await callback.answer(self._t('deal_create_toast_back_to_description', language=language))

            else:
                await callback.answer(self._t('deal_create_unknown_action', language=language), show_alert=True)

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "compact_deal_action")

    async def handle_currency_selected(self, callback: CallbackQuery) -> None:
        """Handle currency selection for deal creation with compact interface."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace("ud_", "")
            language = self._get_user_state(user_id).get('language') or self._get_user_language(user_id) or 'en'
            if not await self._zt_enforce_rate_limit(callback, language):
                return

            if user_id not in self.conversation_states or self.conversation_states[user_id].get('step') != 'select_currency':
                await callback.answer(localization.get_text('no_active_deal_creation_flow', language))
                return

            # Map callback to currency
            currency = 'USDT' if data == 'currency_usdt' else 'TON' if data == 'currency_ton' else data.upper()
            if currency not in SUPPORTED_CURRENCIES:
                await callback.answer(self._t('currency_unavailable', language=language, currency=currency), show_alert=True)
                return

            self._update_user_state(user_id, {'currency': currency, 'step': 'awaiting_amount'})

            # Update the same message with new state
            text = self._build_deal_creation_text(user_id)
            keyboard = self._build_deal_creation_keyboard(user_id)

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_creation")

    async def handle_amount_message(self, message: Message) -> None:
        """Handle amount input for deal creation with compact interface."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            language = self._get_user_state(user_id).get('language', 'en')
            if user_id not in self.conversation_states or self.conversation_states[user_id].get('step') != 'awaiting_amount':
                return  # Not our flow

            state = self._get_user_state(user_id)
            currency = (state.get('currency') or DEFAULT_CURRENCY).upper()

            text = message.text.strip()
            try:
                amount = float(text)
            except (ValueError, TypeError):
                amount = None

            from shared.constants import MIN_DEAL_AMOUNT, MAX_DEAL_AMOUNT
            from shared.currency_conversion import convert_amount_to_usd, get_ton_usd_rate

            min_amount_display = None
            max_amount_display = None
            max_decimals = 4 if currency == "TON" else 2
            if currency == "TON":
                rate = get_ton_usd_rate()
                min_amount_display = f"{(MIN_DEAL_AMOUNT / rate) if rate else MIN_DEAL_AMOUNT:.4f}".rstrip("0").rstrip(".")
                max_amount_display = f"{(MAX_DEAL_AMOUNT / rate) if rate else MAX_DEAL_AMOUNT:.4f}".rstrip("0").rstrip(".")
            else:
                min_amount_display = f"{float(MIN_DEAL_AMOUNT):.2f}".rstrip("0").rstrip(".")
                max_amount_display = f"{float(MAX_DEAL_AMOUNT):.2f}".rstrip("0").rstrip(".")

            if amount is None or amount <= 0:
                error_text = self._t(
                    'deal_create_invalid_amount_message',
                    language=language,
                    currency=currency,
                    min_amount=min_amount_display,
                    max_amount=max_amount_display,
                    max_decimals=max_decimals,
                )
                await message.reply(error_text, parse_mode='HTML')
                return

            amount_usd = convert_amount_to_usd(amount, currency)
            if amount_usd < MIN_DEAL_AMOUNT or amount_usd > MAX_DEAL_AMOUNT:
                error_text = self._t(
                    'deal_create_invalid_amount_message',
                    language=language,
                    currency=currency,
                    min_amount=min_amount_display,
                    max_amount=max_amount_display,
                    max_decimals=max_decimals,
                )
                await message.reply(error_text, parse_mode='HTML')
                return

            # Normalize like web: TON 4 decimals, USDT 2 decimals
            amount = round(amount, max_decimals)

            self._update_user_state(user_id, {'amount': amount, 'step': 'awaiting_description'})

            # Update the main deal creation message
            await self._update_deal_creation_message(user_id, message)

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_creation")

    async def _update_deal_creation_message(self, user_id: int, reference_message: Message) -> None:
        """Update the main deal creation message after input."""
        try:
            text = self._build_deal_creation_text(user_id)
            keyboard = self._build_deal_creation_keyboard(user_id)

            state = self._get_user_state(user_id)
            chat_id = state.get('deal_creation_chat_id') or reference_message.chat.id
            message_id = state.get('deal_creation_message_id')

            if message_id:
                try:
                    await reference_message.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        reply_markup=keyboard,
                        parse_mode='HTML',
                    )
                    return
                except Exception as edit_error:
                    logger.warning(f"Could not edit deal creation message: {edit_error}")

            sent = await reference_message.reply(text, reply_markup=keyboard, parse_mode='HTML')
            try:
                self._update_user_state(
                    user_id,
                    {
                        'deal_creation_chat_id': sent.chat.id,
                        'deal_creation_message_id': sent.message_id,
                    },
                )
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Could not update deal creation message: {e}")

    async def handle_description_message(self, message: Message) -> None:
        """Handle description input for deal creation with compact interface."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_state(user_id).get('language', 'en')
            if user_id not in self.conversation_states or self.conversation_states[user_id].get('step') != 'awaiting_description':
                return

            text = message.text.strip()
            description = None if text.lower() in ['/skip', 'skip', 'пропустити'] else text

            self._update_user_state(user_id, {'description': description, 'step': 'confirm'})

            # Update the main deal creation message
            await self._update_deal_creation_message(user_id, message)

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_creation")

    async def handle_cancel_deal_creation(self, callback: CallbackQuery) -> None:
        """Handle cancellation of deal creation flow."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)
            
            # Check if user is in awaiting_amount state
            state = self._get_user_state(user_id)
            if state.get('step') == 'awaiting_amount':
                # Clear the user's conversation state
                self._clear_user_state(user_id)
                
                # Send confirmation message
                cancel_text = localization.get_text('deal_creation_cancelled', language) if localization else "✅ Deal creation cancelled"
                await callback.message.edit_text(cancel_text, parse_mode='HTML')
                await callback.answer(cancel_text)
                return
            
            # If not in amount input state, proceed with normal back to main
            await self.handle_back_to_main(callback)
            
        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_creation_cancel")

    async def handle_create_confirm(self, callback: CallbackQuery) -> None:
        """Handle deal creation confirmation."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_state(user_id).get('language', 'en')
            if user_id not in self.conversation_states or self.conversation_states[user_id].get('step') != 'confirm':
                await callback.answer(localization.get_text('nothing_to_confirm', language))
                return

            s = self.conversation_states[user_id]

            # Validate that all required fields are present
            required_fields = ['amount', 'currency']
            missing_fields = []
            
            for field in required_fields:
                if field not in s or s[field] is None:
                    missing_fields.append(field)
            
            if missing_fields:
                logger.error(f"Missing required fields {missing_fields} for deal creation by user {user_id}")
                
                # Clear the invalid state and redirect to start
                self._clear_user_state(user_id)
                
                error_text = localization.get_text('deal_creation_missing_data', language)
                if not error_text or error_text.startswith('[missing:'):
                    error_text = "❌ Deal creation data incomplete. Please start again."
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=localization.get_text('create_deal', language) if localization else "Create Deal",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}create_deal_start"
                    )],
                    [InlineKeyboardButton(
                        text=localization.get_text('back', language) if localization else "Back",
                        callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                    )]
                ])
                
                await callback.message.edit_text(
                    error_text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                await callback.answer("❌ Deal creation data incomplete", show_alert=True)
                return

            # Validate amount is positive
            try:
                amount = float(s['amount'])
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid amount '{s.get('amount')}' for user {user_id}: {e}")
                
                # Clear the invalid state and redirect to amount input
                self._update_user_state(user_id, {'step': 'awaiting_amount'})
                
                try:
                    from shared.constants import MIN_DEAL_AMOUNT
                    from shared.currency_conversion import get_ton_usd_rate

                    currency = (s.get('currency') or DEFAULT_CURRENCY).upper()
                    if currency == "TON":
                        rate = get_ton_usd_rate()
                        min_amount_display = f"{(MIN_DEAL_AMOUNT / rate) if rate else MIN_DEAL_AMOUNT:.4f}".rstrip("0").rstrip(".")
                        max_decimals = 4
                    else:
                        min_amount_display = f"{float(MIN_DEAL_AMOUNT):.2f}".rstrip("0").rstrip(".")
                        max_decimals = 2
                except Exception:
                    currency = (s.get('currency') or DEFAULT_CURRENCY).upper()
                    min_amount_display = "1"
                    max_decimals = 2

                error_text = self._t(
                    'deal_create_invalid_amount_message',
                    language=language,
                    currency=currency,
                    min_amount=min_amount_display,
                    max_decimals=max_decimals,
                )
                if not error_text or error_text.startswith('[missing:'):
                    error_text = "❌ Invalid amount. Please enter a valid positive number."
                
                text = self._build_deal_creation_text(user_id)
                keyboard = self._build_deal_creation_keyboard(user_id)
                
                await callback.message.edit_text(
                    error_text + "\n\n" + text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                await callback.answer("❌ Invalid amount", show_alert=True)
                return

            # Validate min/max the same way as web (USD equivalent)
            try:
                from shared.constants import MIN_DEAL_AMOUNT, MAX_DEAL_AMOUNT
                from shared.currency_conversion import convert_amount_to_usd, get_ton_usd_rate

                currency = (s.get('currency') or DEFAULT_CURRENCY).upper()
                amount_usd = convert_amount_to_usd(amount, currency)
                if amount_usd < MIN_DEAL_AMOUNT or amount_usd > MAX_DEAL_AMOUNT:
                    max_decimals = 4 if currency == "TON" else 2
                    if currency == "TON":
                        rate = get_ton_usd_rate()
                        min_amount_display = f"{(MIN_DEAL_AMOUNT / rate) if rate else MIN_DEAL_AMOUNT:.4f}".rstrip("0").rstrip(".")
                        max_amount_display = f"{(MAX_DEAL_AMOUNT / rate) if rate else MAX_DEAL_AMOUNT:.4f}".rstrip("0").rstrip(".")
                    else:
                        min_amount_display = f"{float(MIN_DEAL_AMOUNT):.2f}".rstrip("0").rstrip(".")
                        max_amount_display = f"{float(MAX_DEAL_AMOUNT):.2f}".rstrip("0").rstrip(".")

                    self._update_user_state(user_id, {'step': 'awaiting_amount'})
                    error_text = self._t(
                        'deal_create_invalid_amount_message',
                        language=language,
                        currency=currency,
                        min_amount=min_amount_display,
                        max_amount=max_amount_display,
                        max_decimals=max_decimals,
                    )
                    text = self._build_deal_creation_text(user_id)
                    keyboard = self._build_deal_creation_keyboard(user_id)
                    await callback.message.edit_text(
                        error_text + "\n\n" + text,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    await callback.answer("❌ Invalid amount", show_alert=True)
                    return
            except Exception as e:
                logger.warning(f"Failed to validate amount range for deal creation: {e}")

            # Show processing message
            processing_text = localization.get_text('creating_deal', language)
            await callback.message.edit_text(processing_text, parse_mode='HTML')

            # Generate deal code
            deal_code = generate_deal_code()

            # Create deal in DB
            success = db.create_deal(
                deal_code=deal_code,
                buyer_id=user_id,
                amount=amount,
                currency=s['currency'],
                description=s.get('description')
            )

            if not success:
                self._clear_user_state(user_id)
                error_text = localization.get_text('deal_creation_failed', language) if localization else "❌ Failed to create deal. Please try again."
                await callback.message.edit_text(error_text, parse_mode='HTML')
                return


            # Clear state
            self._clear_user_state(user_id)

            # Get commission settings and calculate amounts
            settings = db.get_settings()
            commission_rate = settings.get('commission_rate', DEFAULT_COMMISSION_RATE)
            commission_amount = float(s['amount']) * commission_rate
            seller_amount = float(s['amount']) - commission_amount

            currency_display = "USDT (TRC20)" if s['currency'] == "USDT" else s['currency'].upper()
            currency_upper = (s.get('currency') or DEFAULT_CURRENCY).upper()
            amount_decimals = 4 if currency_upper == 'TON' else 2
            amount_fmt = f"{float(s['amount']):.{amount_decimals}f}"
            commission_fmt = f"{commission_amount:.{amount_decimals}f}"
            seller_fmt = f"{seller_amount:.{amount_decimals}f}"

            # Success message with deal code
            # Determine escrow address for the success message:
            # - If a real address exists (from payment/deal), use it.
            # - Otherwise, use localized "not_specified" as a fallback.
            escrow_address = None

            try:
                # Prefer decentralized payment record for this deal, if available
                payment = db.get_decentralized_payment_by_deal_code(deal_code)
                if payment:
                    escrow_address = (
                        payment.get('escrow_address')
                        or payment.get('address')
                        or payment.get('checkout_address')
                    )
            except Exception as e:
                logger.warning(f"Error fetching escrow address for deal {deal_code}: {e}")

            # If still not set, try reading from the created deal record
            if not escrow_address:
                try:
                    deal = db.get_deal(deal_code)
                    if deal:
                        escrow_address = (
                            deal.get('escrow_address')
                            or deal.get('address')
                            or deal.get('payment_address')
                        )
                except Exception as e:
                    logger.warning(f"Error fetching deal escrow address for {deal_code}: {e}")

            # Final localized fallback if no real address is available
            if not escrow_address:
                escrow_address = (
                    localization.get_text('not_specified', language)
                    if localization else
                    'Not specified'
                )

            # Enhanced visual success message using localized translations
            success_text = localization.get_text('deal_created_success_title', language) + "\n\n"
            success_text += localization.get_text('deal_created_success_code', language, code=deal_code) + "\n"
            success_text += localization.get_text('deal_created_success_amount', language, amount=amount_fmt, currency=currency_display) + "\n"
            success_text += localization.get_text('deal_created_success_commission', language, commission=commission_fmt, currency=currency_display) + "\n"
            success_text += localization.get_text('deal_created_success_seller_receives', language, seller_amount=seller_fmt, currency=currency_display) + "\n\n"

            success_text += localization.get_text('deal_created_success_progress', language) + "\n\n"
            success_text += localization.get_text('deal_created_success_step_created', language) + "\n"
            success_text += localization.get_text('deal_created_success_step_waiting_seller', language) + "\n"
            success_text += localization.get_text('deal_created_success_step_payment', language) + "\n"
            success_text += localization.get_text('deal_created_success_step_delivery', language) + "\n"
            success_text += localization.get_text('deal_created_success_step_receipt', language) + "\n"
            success_text += localization.get_text('deal_created_success_step_withdrawal', language) + "\n\n"

            success_text += localization.get_text('deal_created_success_next_steps', language) + "\n"
            success_text += localization.get_text('deal_created_success_next_share', language, code=deal_code) + "\n"
            success_text += localization.get_text('deal_created_success_next_join', language) + "\n"
            success_text += localization.get_text('deal_created_success_next_payment', language) + "\n"
            success_text += localization.get_text('deal_created_success_next_delivery', language) + "\n"
            success_text += localization.get_text('deal_created_success_next_confirm', language) + "\n"
            success_text += localization.get_text('deal_created_success_next_receive', language) + "\n\n"

            success_text += localization.get_text('deal_created_success_guarantee', language)

            keyboard_buttons = [
                [
                    InlineKeyboardButton(
                        text=localization.get_text('view_deal', language, code=deal_code)
                        if localization else f"View {deal_code}",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                    )
                ]
            ]

            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=localization.get_text('back_to_main', language)
                    if localization else '🔙 Back to main',
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            await callback.message.edit_text(success_text, reply_markup=keyboard, parse_mode='HTML')
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_creation")
            self._clear_user_state(user_id)

    async def handle_my_deals(self, update: Union[Message, CallbackQuery]) -> None:
        """Handle my deals display."""
        if await self._block_banned_user(update):
            return
        try:
            if isinstance(update, CallbackQuery):
                user_id = update.from_user.id
                message = update.message
                data = update.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")
                answer_method = update.answer
            elif isinstance(update, Message):
                user_id = update.from_user.id
                message = update
                data = None
                answer_method = None
            else:
                return

            language = self._get_user_language(user_id)

            # Add breadcrumb to track navigation
            self.add_breadcrumb(user_id, 'my_deals')

            user_deals = db.get_user_deals(user_id)
            if not user_deals:
                logger.info(f"User {user_id} has no deals, prompting to enter deal code")
                self._set_user_state(user_id, {'step': 'awaiting_join_code', 'language': language})

                text = localization.get_text('join_deal_prompt', language)

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=localization.get_text('back', language) if localization else 'Back', callback_data=f"{UNIFIED_PREFIXES['nav']}main")]
                ])

                if isinstance(update, CallbackQuery):
                    await message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                    await answer_method()
                else:
                    await message.reply(text, reply_markup=keyboard, parse_mode='HTML')
                return

            # Pagination support
            page_size = 5
            page = 1
            if data and isinstance(data, str) and data.startswith('my_deals_page:'):
                try:
                    page = max(1, int(data.split(':', 1)[1]))
                except Exception:
                    page = 1

            start = (page - 1) * page_size
            end = start + page_size

            # Header and list using improved formatting
            lines = [format_deal_summary(user_deals[start:end], language)]
            text = lines[0]

            # Inline keyboard with per-deal actions
            buttons = []
            for deal in user_deals[start:end]:
                code = deal.get('deal_code')
                row = [InlineKeyboardButton(text=localization.get_text('button_view_deal', language, code=code), callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{code}")]
                # Allow cancelling active deals that belong to the user as buyer
                if deal.get('buyer_id') == user_id and deal.get('status') == 'active':
                    row.append(InlineKeyboardButton(text=localization.get_text('button_cancel', language), callback_data=f"{UNIFIED_PREFIXES['deal']}cancel_deal:{code}"))
                buttons.append(row)

            # Pagination controls
            nav_row = []
            total = len(user_deals)
            total_pages = max(1, (total + page_size - 1) // page_size)
            if page > 1:
                nav_row.append(InlineKeyboardButton(text=localization.get_text('button_previous', language), callback_data=f"{UNIFIED_PREFIXES['deal']}my_deals_page:{page-1}"))
            nav_row.append(InlineKeyboardButton(text=localization.get_text('button_page_label', language, page=page, total_pages=total_pages), callback_data='noop'))
            if page < total_pages:
                nav_row.append(InlineKeyboardButton(text=localization.get_text('button_next', language), callback_data=f"{UNIFIED_PREFIXES['deal']}my_deals_page:{page+1}"))
            buttons.append(nav_row)

            # Back button - use breadcrumb system
            breadcrumb_trail = self.get_breadcrumb_trail(user_id)
            if len(breadcrumb_trail) > 1:
                # Go back to previous section
                previous_section = breadcrumb_trail[-2]  # Second to last is the previous page
                if previous_section == 'profile':
                    back_callback = f"{UNIFIED_PREFIXES['profile']}view"
                elif previous_section == 'my_deals':
                    back_callback = f"{UNIFIED_PREFIXES['deal']}my_deals"
                elif previous_section == 'main':
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"
                else:
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"  # Default fallback
            else:
                # No breadcrumb or only one entry, default to main
                back_callback = f"{UNIFIED_PREFIXES['nav']}main"

            buttons.append([InlineKeyboardButton(text=localization.get_text('back', language) if localization else 'Back', callback_data=back_callback)])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            if isinstance(update, CallbackQuery):
                await message.edit_text(text=text, reply_markup=keyboard, parse_mode='HTML')
                await answer_method()
            else:
                await message.reply(text=text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            await self.error_handler.handle_error(update, e, "deal_join")

    async def handle_cancel_deal(self, callback: CallbackQuery) -> None:
        """Handle deal cancellation."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)  # Get user language
            if not await self._zt_enforce_rate_limit(callback, language):
                return
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")

            if not data.startswith('cancel_deal:'):
                await callback.answer()
                return

            code = data.split(':', 1)[1].upper()
            try:
                self._zt_validate_deal(user_id, code, required_role='buyer', allowed_states=['active'])
            except StateValidationError:
                await callback.answer('Deal cannot be cancelled at this stage')
                return
            except AuthorizationError:
                await callback.answer('Access denied - only buyer can cancel')
                return

            # Create confirmation keyboard
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('confirm_cancel_deal', language) if localization else "✅ Confirm Cancel",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_cancel_deal:{code}"
                )],
                [InlineKeyboardButton(
                    text=localization.get_text('keep_deal', language) if localization else "❌ Keep Deal",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}my_deals"
                )]
            ])

            await callback.message.edit_text(
                text=localization.get_text('confirm_cancel_deal_text', language, code=code) if localization else f"<b>Cancel Deal {code}</b>\n\nAre you sure you want to cancel this deal? This action cannot be undone.",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_management")

    async def handle_confirm_cancel_deal(self, callback: CallbackQuery) -> None:
        """Handle deal cancellation confirmation."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)  # Get user language
            if not await self._zt_enforce_rate_limit(callback, language):
                return
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")

            if not data.startswith('confirm_cancel_deal:'):
                await callback.answer()
                return

            code = data.split(':', 1)[1].upper()
            try:
                self._zt_validate_deal(user_id, code, required_role='buyer', allowed_states=['active'])
            except StateValidationError:
                await callback.answer('Deal cannot be cancelled at this stage')
                return
            except AuthorizationError:
                await callback.answer('Access denied - only buyer can cancel')
                return

            # Cancel the deal
            success = db.update_deal_status(code, 'cancelled')
            if success:
                await callback.message.edit_text(
                    text=localization.get_text('deal_cancelled_success', language, code=code) if localization else f"✅ <b>Deal {code} Cancelled</b>\n\nThe deal has been cancelled successfully. The funds have been released back to your account.",
                    parse_mode="HTML"
                )
                await callback.answer(localization.get_text('deal_cancelled_success_message', language) if localization else "Deal cancelled successfully")
            else:
                await callback.answer("Failed to cancel deal", show_alert=True)

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_management")

    async def handle_open_dispute(self, callback: CallbackQuery) -> None:
        """Handle opening a dispute for a deal."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)  # Get user language
            if not await self._zt_enforce_rate_limit(callback, language):
                return
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")

            if not data.startswith('open_dispute:'):
                await callback.answer()
                return

            code = data.split(':', 1)[1].upper()
            try:
                deal = self._zt_validate_deal(user_id, code, required_role='participant')
            except AuthorizationError:
                await callback.answer('Access denied - only deal participants can open disputes')
                return

            # Check if deal is in dispute state - using actual database statuses
            if deal.get('status') in ('cancelled', 'completed'):
                await callback.answer('Cannot open dispute for completed or cancelled deals')
                return

            # Create dispute opening confirmation
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('confirm_open_dispute', language) if localization else "✅ Open Dispute",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_open_dispute:{code}"
                )],
                [InlineKeyboardButton(
                    text=localization.get_text('cancel', language) if localization else "❌ Cancel",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{code}"
                )]
            ])

            await callback.message.edit_text(
                text=localization.get_text('confirm_open_dispute_text', language, code=code) if localization else f"<b>Open Dispute for Deal {code}</b>\n\n⚠️ <b>Warning:</b> Opening a dispute will halt the deal process and require manual resolution by our support team.\n\nAre you sure you want to open a dispute?",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_management")

    async def handle_confirm_open_dispute(self, callback: CallbackQuery) -> None:
        """Handle dispute opening confirmation and start dispute description flow."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)
            if not await self._zt_enforce_rate_limit(callback, language):
                return
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")

            if not data.startswith('confirm_open_dispute:'):
                await callback.answer()
                return

            code = data.split(':', 1)[1].upper()
            try:
                deal = self._zt_validate_deal(user_id, code, required_role='participant')
            except AuthorizationError:
                await callback.answer('Access denied - only deal participants can open disputes')
                return

            # Check if deal is in dispute state - using actual database statuses
            if deal.get('status') in ('cancelled', 'completed'):
                await callback.answer('Cannot open dispute for completed or cancelled deals')
                return

            # Set up conversation state to collect dispute description
            self._set_user_state(user_id, {
                'step': 'awaiting_dispute_description',
                'deal_code': code,
                'language': language
            })

            # Show description input prompt
            text = localization.get_text('dispute_description_prompt', language, code=code) if localization else f"🛡️ <b>Dispute Description for Deal {code}</b>\n\n📝 <b>Please describe your problem:</b>\n\n• What happened?\n• What went wrong?\n• What do you expect as a resolution?\n\n💡 <b>Be as detailed as possible to help our support team resolve the dispute quickly.</b>"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('cancel', language) if localization else "❌ Cancel",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{code}"
                )]
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_management")

    async def handle_view_deal(self, callback: CallbackQuery) -> None:
        """Handle deal view request."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)  # Get user language
            if not await self._zt_enforce_rate_limit(callback, language):
                return
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")

            if not data.startswith('view_deal:'):
                await callback.answer()
                return

            code = data.split(':', 1)[1].upper()
            try:
                deal = self._zt_validate_deal(user_id, code, required_role='participant')
            except AuthorizationError:
                await callback.answer('Access denied')
                return

            # Add breadcrumb to track navigation
            self.add_breadcrumb(user_id, 'deal_view')

            # Prepare deal data with user names
            buyer = db.get_user(deal.get('buyer_id')) or {}
            seller = db.get_user(deal.get('seller_id')) or {}
            
            # Enhanced deal data for formatting
            enhanced_deal = dict(deal)
            enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
            enhanced_deal['seller_name'] = seller.get('username') or seller.get('first_name') or f"ID: {deal.get('seller_id')}" if deal.get('seller_id') else self._get_not_assigned_text(language)
            
            # Use improved formatting with proper language
            text = format_deal_info(enhanced_deal, language)
            
            # Action buttons based on deal status and user role
            buttons = []
            is_buyer = deal.get('buyer_id') == user_id
            is_seller = deal.get('seller_id') == user_id
            deal_status = deal.get('status')
            
            # Add payment information section when deal is active and seller has joined
            if deal_status == 'active' and deal.get('seller_id') and is_buyer:
                # Get payment address for display
                from shared.config import USDT_WALLET_ADDRESS, TON_WALLET_ADDRESS
                currency = deal.get('currency', 'USDT')
                currency_upper = currency.upper()
                if currency == 'USDT':
                    payment_address = USDT_WALLET_ADDRESS
                elif currency == 'TON':
                    payment_address = TON_WALLET_ADDRESS
                else:
                    payment_address = None
                
                if payment_address:
                    currency_display = "USDT (TRC20)" if currency_upper == "USDT" else currency_upper
                    payment_memo = f"DEAL-{deal.get('deal_code')}" if currency.upper() == "TON" and deal.get('deal_code') else None
                    payment_info = f"\n\n💳 <b>{localization.get_text('payment_instructions_title', language)}</b>\n"
                    formatted_payment_address = self._format_clickable_address(payment_address, language)
                    payment_info += f"💰 {localization.get_text('payment_amount', language, amount=deal.get('amount'), currency=currency_display)}\n"
                    payment_info += f"🏦 {localization.get_text('payment_address', language)}\n"
                    payment_info += f"{formatted_payment_address}\n\n"
                    if payment_memo:
                        payment_info += f"Memo/Comment:\n<code>{payment_memo}</code>\n\n"
                    payment_info += f"⚠️ <b>{localization.get_text('payment_warning', language)}</b>\n"
                    payment_info += f"• {localization.get_text('payment_warning_exact', language, amount=deal.get('amount'), currency=currency_display)}\n"
                    payment_info += f"• {localization.get_text('payment_warning_address', language)}\n"
                    payment_info += f"• {localization.get_text('payment_warning_confirmed', language)}\n"
                    text += payment_info
            
            # Status-specific action buttons
            if deal_status == 'active':
                if is_buyer:
                    # Check if seller has joined
                    if deal.get('seller_id'):
                        # Seller has joined - show payment options
                        # Check buyer balance for payment options
                        # Add payment method selection button
                        buttons.append([
                            InlineKeyboardButton(
                                text="💳 Pay",
                                callback_data=f"{UNIFIED_PREFIXES['deal']}payment_method:{code}"
                            )
                        ])
                    
                    # Always show cancel button for active deals
                    buttons.append([
                        InlineKeyboardButton(
                            text=localization.get_text('button_cancel', language),
                            callback_data=f"{UNIFIED_PREFIXES['deal']}cancel_deal:{code}"
                        )
                    ])
                elif is_seller:
                    # Seller should wait for buyer's payment, no payment button needed
                    # The seller should see a message about waiting for payment
                    pass
                elif not deal.get('seller_id'):
                    buttons.append([InlineKeyboardButton(
                        text="🤝 Join Deal",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_join:{code}"
                    )])

            elif deal_status == 'funded':
                if is_seller:
                    buttons.append([InlineKeyboardButton(
                        text="✅ Confirm Delivery",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_delivery:{code}"
                    )])
                elif is_buyer:
                    buttons.append([InlineKeyboardButton(
                        text="🔵 Waiting for Delivery",
                        callback_data='noop'
                    )])

            elif deal_status == 'delivery_pending':
                if is_seller:
                    buttons.append([InlineKeyboardButton(
                        text="✅ Confirm Delivery",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_delivery:{code}"
                    )])
                elif is_buyer:
                    buttons.append([InlineKeyboardButton(
                        text="⏳ Waiting for Confirmation",
                        callback_data='noop'
                    )])

            elif deal_status == 'receipt_pending':
                if is_buyer:
                    buttons.append([InlineKeyboardButton(
                        text="✅ Confirm Receipt",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_receipt:{code}"
                    )])
                elif is_seller:
                    buttons.append([InlineKeyboardButton(
                        text="⏳ Waiting for Confirmation",
                        callback_data='noop'
                    )])

            elif deal_status == 'funds_pending':
                if is_seller:
                    buttons.append([InlineKeyboardButton(
                        text=localization.get_text('button_withdraw_to_wallet', language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}withdraw_wallet:{code}"
                    )])

                elif is_buyer:
                    buttons.append([InlineKeyboardButton(
                        text="🔵 Waiting for Withdrawal",
                        callback_data='noop'
                    )])

            # Dispute button (for active deals)
            if deal_status not in ('cancelled', 'completed') and (is_buyer or is_seller):
                buttons.append([InlineKeyboardButton(
                    text="🛡️ " + localization.get_text('button_open_dispute', language),
                    callback_data=f"{UNIFIED_PREFIXES['deal']}open_dispute:{code}"
                )])

            # Back button - use breadcrumb system
            breadcrumb_trail = self.get_breadcrumb_trail(user_id)
            if len(breadcrumb_trail) > 1:
                # Go back to previous section
                previous_section = breadcrumb_trail[-2]  # Second to last is the previous page
                if previous_section == 'profile':
                    back_callback = f"{UNIFIED_PREFIXES['profile']}view"
                elif previous_section == 'my_deals':
                    back_callback = f"{UNIFIED_PREFIXES['deal']}my_deals"
                elif previous_section == 'main':
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"
                else:
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"  # Default fallback
            else:
                # No breadcrumb or only one entry, default to main
                back_callback = f"{UNIFIED_PREFIXES['nav']}main"

            buttons.append([InlineKeyboardButton(
                text=localization.get_text('back', language),
                callback_data=back_callback
            )])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode='HTML')
    
            # Send share deal link for buyer only once per user per deal
            if deal.get('buyer_id') == user_id:
                # Create unique key for this user-deal combination
                user_deal_key = (user_id, code)
                
                # Only send the sharing message if we haven't sent it before
                if user_deal_key not in self.shared_deal_messages_sent:
                    share_link = f"https://t.me/{BOT_USERNAME[1:]}?start={code}"
                    share_message = localization.get_text('share_deal_link', language, link=share_link) if localization else f"Share this deal: {share_link}"
                    await callback.message.reply(share_message, parse_mode='HTML')
                    
                    # Mark this user-deal combination as having received the sharing message
                    self.shared_deal_messages_sent.add(user_deal_key)
    
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_view")

    async def handle_join_deal_start(self, update: Union[Message, CallbackQuery]) -> None:
        """Handle join deal start - separate from my_deals flow."""
        if await self._block_banned_user(update):
            return
        try:
            if isinstance(update, CallbackQuery):
                user_id = update.from_user.id
                message = update.message
                answer_method = update.answer
            elif isinstance(update, Message):
                user_id = update.from_user.id
                message = update
                answer_method = None
            else:
                return

            language = self._get_user_language(user_id)

            # Initialize state for join deal flow
            self._set_user_state(user_id, {'step': 'awaiting_join_code', 'language': language})

            text = localization.get_text('join_deal_prompt', language) if localization else "🤝 <b>Join Deal</b>\n\n🔑 <b>Enter deal code:</b>\n\n📝 Code must be 8 characters\n🔍 Find code from seller\n\n⚡ <b>After entering code, deal will start!</b>"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=localization.get_text('back', language) if localization else 'Back', callback_data=f"{UNIFIED_PREFIXES['nav']}main")]
            ])

            if isinstance(update, CallbackQuery):
                await message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
                await answer_method()
            else:
                await message.reply(text, reply_markup=keyboard, parse_mode='HTML')

        except Exception as e:
            await self.error_handler.handle_error(update, e, "deal_join")

    async def handle_join_code_message(self, message: Message) -> None:
        """Handle joining a deal with step-by-step visual feedback."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            if user_id not in self.conversation_states or self.conversation_states[user_id].get('step') != 'awaiting_join_code':
                return

            code = message.text.strip().upper()
            language = self.conversation_states[user_id]['language']

            # Step 1: Validate code format
            validating_msg = await message.reply("🔍 <b>Validating deal code...</b>", parse_mode='HTML')

            if not validation_utils.validate_deal_code(code):
                await validating_msg.edit_text(localization.get_text('invalid_deal_code_format', language), parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Step 2: Look up deal
            await validating_msg.edit_text("📋 <b>Looking up deal information...</b>", parse_mode='HTML')

            deal = db.get_deal(code)
            if not deal:
                await validating_msg.edit_text("❌ <b>Deal not found</b>\n\nPlease check the code and try again.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Step 3: Check deal status
            await validating_msg.edit_text("✅ <b>Checking deal availability...</b>", parse_mode='HTML')

            if deal['status'] != 'active':
                await validating_msg.edit_text("❌ <b>Deal is no longer active</b>\n\nThis deal cannot be joined.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Step 4: Verify eligibility
            await validating_msg.edit_text("🔗 <b>Verifying your eligibility...</b>", parse_mode='HTML')

            if deal['buyer_id'] == user_id:
                await validating_msg.edit_text("❌ <b>Cannot join your own deal</b>\n\nYou cannot join a deal you created.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            if deal.get('seller_id'):
                await validating_msg.edit_text("❌ <b>Deal already taken</b>\n\nThis deal has already been joined by another seller.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Step 5: Display deal information and confirmation
            await validating_msg.edit_text(
                f"📋 <b>{localization.get_text('loading_deal_information', language)}</b>",
                parse_mode='HTML'
            )

            # Prepare deal data for formatting
            buyer = db.get_user(deal.get('buyer_id')) or {}
            enhanced_deal = dict(deal)
            enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
            enhanced_deal['seller_name'] = self._get_not_assigned_text(language)

            # Format deal information
            deal_info = format_deal_info(enhanced_deal, language)

            # Create confirmation keyboard
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('join_deal', language) if localization else 'Join Deal',
                    callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_join:{code}"
                )],
                [InlineKeyboardButton(
                    text=localization.get_text('back', language) if localization else 'Back',
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )]
            ])

            await validating_msg.edit_text(deal_info, reply_markup=keyboard, parse_mode='HTML')
            self._clear_user_state(user_id)

        except Exception as e:
            # Check if the deal was actually joined successfully before showing error
            deal = db.get_deal(code)
            if deal and deal.get('seller_id') == user_id:
                # Deal was joined successfully, don't show error message
                logger.warning(f"Non-critical error after successful deal join for user {user_id}: {e}")
                # Send a follow-up message to acknowledge any issues
                try:
                    await message.reply(
                        localization.get_text('deal_joined_with_notification_issue', language),
                        parse_mode='HTML'
                    )
                except Exception:
                    pass  # Ignore any further errors
            else:
                # Deal join actually failed, show error
                await self.error_handler.handle_error(message, e, "deal_join")
                self._clear_user_state(user_id)

    async def handle_confirm_join_deal(self, callback: CallbackQuery) -> None:
        """Handle deal join confirmation after user checks deal information."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}", "")

            if not data.startswith('confirm_join:'):
                await callback.answer()
                return

            code = data.split(':', 1)[1].upper()
            language = self._get_user_language(user_id)

            # Re-validate the deal (in case it changed)
            deal = db.get_deal(code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            if deal['status'] != 'active':
                await callback.answer("❌ Deal is no longer active", show_alert=True)
                return

            if deal['buyer_id'] == user_id:
                await callback.answer("❌ Cannot join your own deal", show_alert=True)
                return

            if deal.get('seller_id'):
                await callback.answer("❌ Deal already taken", show_alert=True)
                return

            # Show processing message
            await callback.message.edit_text("🤝 <b>Joining deal...</b>", parse_mode='HTML')

            # Join the deal
            success = db.join_deal(code, user_id)
            if not success:
                await callback.message.edit_text("❌ <b>Failed to join deal</b>\n\nPlease try again later.", parse_mode='HTML')
                return

            # Success - show joined message
            settings = db.get_settings()
            commission_rate = settings.get('commission_rate', DEFAULT_COMMISSION_RATE)
            commission_amount, seller_amount = deal_utils.calculate_commission(deal['amount'], commission_rate)

            currency_display = "USDT (TRC20)" if deal['currency'] == "USDT" else deal['currency'].upper()

            # Determine escrow address
            escrow_address = None
            try:
                existing_payment = db.get_decentralized_payment_by_deal_code(code)
                if existing_payment:
                    escrow_address = existing_payment.get('escrow_address') or existing_payment.get('address')
            except Exception as e:
                logger.warning(f"Failed to fetch existing payment for deal {code}: {e}")

            if not escrow_address:
                try:
                    escrow_address = localization.get_text('not_specified', language) if localization else 'Not specified'
                except Exception:
                    escrow_address = 'Not specified'

            # Enhanced success message with timeline - now localized
            seller_info = (
                f"{localization.get_text('seller_joined_deal_title', language)}\n\n"
                f"{localization.get_text('seller_joined_deal_code', language, code=code)}\n"
                f"{localization.get_text('seller_joined_deal_amount', language, amount=deal['amount'], currency=currency_display)}\n"
                f"{localization.get_text('seller_joined_deal_commission', language, commission=f'{commission_amount:.2f}', currency=currency_display)}\n"
                f"{localization.get_text('seller_joined_deal_seller_receives', language, seller_amount=f'{seller_amount:.2f}', currency=currency_display)}\n\n"
                f"{localization.get_text('seller_joined_deal_progress', language)}\n\n"
                f"{localization.get_text('seller_joined_deal_step_created', language)}\n"
                f"{localization.get_text('seller_joined_deal_step_joined', language)}\n"
                f"{localization.get_text('seller_joined_deal_step_waiting_payment', language)}\n"
                f"{localization.get_text('seller_joined_deal_step_delivery', language)}\n"
                f"{localization.get_text('seller_joined_deal_step_receipt', language)}\n"
                f"{localization.get_text('seller_joined_deal_step_withdrawal', language)}\n\n"
                f"{localization.get_text('seller_joined_deal_next_steps', language)}\n"
                f"{localization.get_text('seller_joined_deal_next_wait_payment', language)}\n"
                f"{localization.get_text('seller_joined_deal_next_deliver', language)}\n"
                f"{localization.get_text('seller_joined_deal_next_confirm_delivery', language)}\n"
                f"{localization.get_text('seller_joined_deal_next_confirm_receipt', language)}\n"
                f"{localization.get_text('seller_joined_deal_next_receive_funds', language, seller_amount=f'{seller_amount:.2f}', currency=currency_display)}\n\n"
                f"{localization.get_text('seller_joined_deal_guarantee', language)}"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=localization.get_text('button_view', language) if localization else 'View', callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{code}")],
                [InlineKeyboardButton(text=localization.get_text('back', language) if localization else 'Back', callback_data=f"{UNIFIED_PREFIXES['nav']}main")]
            ])

            await callback.message.edit_text(seller_info, reply_markup=keyboard, parse_mode='HTML')

            # Create payment and start monitoring
            payment_result = decentralized_payment_processor.create_payment(
                deal_code=code,
                amount=deal['amount'],
                currency=deal['currency'],
                buyer_address=f"buyer_{deal['buyer_id']}",
                seller_address=f"seller_{user_id}"
            )

            if payment_result:
                asyncio.create_task(self._monitor_payment_status(code, deal['buyer_id'], user_id))

            # Notify buyer
            await self._notify_buyer_deal_joined(code, deal, payment_result, language, user_id)

            await callback.answer(
                f"{localization.get_text('joined_deal_successfully', language)}!",
                show_alert=True
            )

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "deal_join")

    # ===== PROFILE METHODS =====

    def get_status_emoji(self, status: str) -> str:
        """Get emoji for deal status."""
        status_emojis = {
            'active': '⏳',
            'completed': '✅',
            'cancelled': '❌',
            'failed': '💥'
        }
        return status_emojis.get(status.lower(), '❓')

    async def format_profile(self, user_id: int, language: str) -> str:
        """Format profile with modern, attractive design."""
        user = db.get_user(user_id)
        user_deals = db.get_user_deals(user_id)
        
        # Handle case where user doesn't exist
        if user is None:
            return f"""👤 <b>Profile</b>

❌ User not found. Please restart the bot with /start

📋 <b>Recent Deals</b>"""
        
        # Use the new modern formatting function without balance information
        from bot.utils.formatting import format_modern_profile
        
        return format_modern_profile(
            user=user,
            user_deals=user_deals,
            language=language
        )

    async def handle_profile_view(self, update: Union[Message, CallbackQuery]) -> None:
        """Handle profile view request."""
        if await self._block_banned_user(update):
            return
        try:
            if isinstance(update, CallbackQuery):
                user_id = update.from_user.id
                message = update.message
                answer_method = update.answer
            elif isinstance(update, Message):
                user_id = update.from_user.id
                message = update
                answer_method = None
            else:
                return

            language = self._get_user_language(user_id)

            # Add breadcrumb to track navigation
            self.add_breadcrumb(user_id, 'profile')

            profile_text = await self.format_profile(user_id, language)

            keyboard_buttons = [
                [InlineKeyboardButton(text=localization.get_text('profile_my_deals', language), callback_data=f"{UNIFIED_PREFIXES['deal']}my_deals")]
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            if isinstance(update, CallbackQuery):
                await message.edit_text(
                    text=profile_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                await answer_method()
            else:
                await message.reply(
                    text=profile_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

        except Exception as e:
            await self.error_handler.handle_error(update, e, "profile")

    async def handle_start(self, message: Message) -> None:
        """Handle /start command with modern interface and deal_code support."""
        try:
            user_id = message.from_user.id
            username = message.from_user.username
            first_name = message.from_user.first_name

            user_record = db.get_user(user_id)
            if user_record and user_record.get('is_banned'):
                language = user_record.get('language') or self._get_user_language(user_id)
                ban_text = localization.get_text('account_banned', language)
                logger.info(f"Blocked /start from banned user {user_id}")
                try:
                    await message.answer(ban_text, reply_markup=ReplyKeyboardRemove())
                except Exception:
                    pass
                return

            # Create user if doesn't exist
            self._create_user_if_not_exists(user_id, username, first_name)

            # Get user's language preference
            language = self._get_user_language(user_id)

            # Parse command arguments to extract deal_code (second argument after /start)
            args = message.text.split()
            deal_code = args[1].upper() if len(args) > 1 else None

            # Check if deal_code is provided and handle deal joining flow
            if deal_code:
                logger.info(f"User {user_id} started with deal_code: {deal_code}")

                # Validate deal code format
                if not validation_utils.validate_deal_code(deal_code):
                    logger.warning(f"Invalid deal code format: {deal_code} for user {user_id}")
                    # Show standard welcome for invalid format
                    await self._send_welcome_message(message, language, user_id)
                    return

                # Look up deal
                deal = db.get_deal(deal_code)
                if not deal:
                    logger.warning(f"Deal not found: {deal_code} for user {user_id}")
                    # Show standard welcome for non-existent deal
                    await self._send_welcome_message(message, language, user_id)
                    return

                # Check if deal is joinable
                if deal['status'] != 'active':
                    logger.info(f"Deal {deal_code} not active (status: {deal['status']}) for user {user_id}")
                    # Show standard welcome for non-active deal
                    await self._send_welcome_message(message, language, user_id)
                    return

                if deal['buyer_id'] == user_id:
                    logger.info(f"User {user_id} cannot join their own deal {deal_code}")
                    # Show standard welcome for own deal
                    await self._send_welcome_message(message, language, user_id)
                    return

                if deal.get('seller_id'):
                    logger.info(f"Deal {deal_code} already taken by seller {deal.get('seller_id')}")
                    # Show standard welcome for already taken deal
                    await self._send_welcome_message(message, language, user_id)
                    return

                # Deal is valid and joinable - show deal information with join button
                await self._send_deal_join_message(message, deal, language, user_id)
                return

            # No deal_code provided - show standard welcome
            await self._send_welcome_message(message, language, user_id)

        except Exception as e:
            logger.error(f"Start handler error for user {message.from_user.id}: {e}")
            try:
                await message.reply("❌ Error starting bot. Please try again.", parse_mode='HTML')
            except Exception:
                pass

    async def _send_welcome_message(self, message: Message, language: str, user_id: int) -> None:
        """Send standard welcome message."""
        first_name = message.from_user.first_name or message.from_user.username or "User"

        # Format welcome message
        welcome_text = format_welcome_message(language, first_name)

        # Create inline keyboard for welcome message
        self.keyboard_factory.create_welcome_inline_keyboard(language)

        # Create main menu inline keyboard
        main_menu_keyboard = self.keyboard_factory.create_main_menu_keyboard(language, user_id)

        # Create persistent reply keyboard
        reply_keyboard = self.keyboard_factory.create_main_reply_keyboard(language, user_id)

        # Send photo with inline keyboard - handle file not found gracefully
        sent_message = None
        try:
            sent_message = await message.reply_photo(
                photo=InputFile(open("static/welcome_images/photo_2025-10-16_11-30-00.jpg", 'rb')),
                caption=welcome_text,
                reply_markup=main_menu_keyboard,
                parse_mode="HTML"
            )
        except FileNotFoundError:
            logger.warning(f"Welcome image not found for user {user_id}, sending text message instead")
            sent_message = await message.reply(
                text=welcome_text,
                reply_markup=main_menu_keyboard,
                parse_mode="HTML"
            )
        except Exception as photo_error:
            logger.warning(f"Failed to send photo to user {user_id}: {photo_error}")
            sent_message = await message.reply(
                text=welcome_text,
                reply_markup=main_menu_keyboard,
                parse_mode="HTML"
            )

        # Send separate message to set persistent reply keyboard
        try:
            await message.reply("💎", reply_markup=reply_keyboard)
        except Exception as keyboard_error:
            logger.warning(f"Failed to send reply keyboard to user {user_id}: {keyboard_error}")

        # Pin the welcome message to the chat
        if sent_message:
            try:
                await sent_message.pin(disable_notification=True)
                logger.info(f"Pinned welcome message for user {user_id} ({language})")
            except Exception as pin_error:
                logger.warning(f"Failed to pin welcome message for user {user_id}: {pin_error}")

        logger.info(f"Sent welcome message for user {user_id} ({language})")

    async def _send_deal_join_message(self, message: Message, deal: dict, language: str, user_id: int) -> None:
        """Send deal information with join button for shared links."""
        try:
            deal_code = deal.get('deal_code')

            # Prepare deal data with user names
            buyer = db.get_user(deal.get('buyer_id')) or {}
            enhanced_deal = dict(deal)
            enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
            enhanced_deal['seller_name'] = self._get_not_assigned_text(language)

            # Format deal information
            deal_info = format_deal_info(enhanced_deal, language)

            # Create join button keyboard
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('join_deal', language) if localization else 'Join Deal',
                    callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_join:{deal_code}"
                )],
                [InlineKeyboardButton(
                    text=localization.get_text('back', language) if localization else 'Back',
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )]
            ])

            await message.reply(
                text=deal_info,
                reply_markup=keyboard,
                parse_mode='HTML'
            )

            logger.info(f"Sent deal join message for deal {deal_code} to user {user_id}")

        except Exception as e:
            logger.error(f"Error sending deal join message for user {user_id}: {e}")
            # Fallback to welcome message
            await self._send_welcome_message(message, language, user_id)

    async def handle_create_deal_command(self, message: Message) -> None:
        """Handle /create command - start deal creation flow."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} used /create command")

            # Start the deal creation flow
            await self.handle_create_deal_start(message)

            logger.info(f"User {user_id} successfully started create deal flow from /create command")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_creation")

    async def handle_my_deals_command(self, message: Message) -> None:
        """Handle /my_deals command - show user's deals."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} used /my_deals command")

            # Start the my deals flow
            await self.handle_my_deals(message)

            logger.info(f"User {user_id} successfully started my deals flow from /my_deals command")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_join")

    async def handle_profile_command(self, message: Message) -> None:
        """Handle /profile command - show user profile."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} used /profile command")

            # Start the profile view
            await self.handle_profile_view(message)

            logger.info(f"User {user_id} successfully started profile view from /profile command")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "profile")

    async def handle_support_command(self, message: Message) -> None:
        """Handle /support command - start support chat."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            language = self._get_user_language(user_id)

            logger.info(f"User {user_id} used /support command")

            # Check if user is already in support mode
            state = self._get_user_state(user_id)
            if state.get('support_mode'):
                # User is already in support mode
                support_text = localization.get_text('support_already_in_chat', language) if localization else "🆘 <b>Support Chat</b>\n\nYou are already in support chat mode. Type your message and we'll respond as soon as possible."
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=localization.get_text('exit_support', language) if localization else '❌ Exit Support', callback_data=f"{UNIFIED_PREFIXES['support']}exit")]
                ])
                await message.reply(support_text, reply_markup=keyboard, parse_mode='HTML')
                return

            # Enter support mode
            self._update_user_state(user_id, {'support_mode': True, 'language': language})

            # Get welcome message
            support_text = localization.get_text('support_welcome', language) if localization else "🆘 <b>Support Chat</b>\n\nYou are now in support chat mode. Type your message and our support team will respond as soon as possible.\n\n💡 <b>Tip:</b> Include your deal code and user ID for faster resolution."

            # Create keyboard with exit option
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=localization.get_text('exit_support', language) if localization else '❌ Exit Support', callback_data=f"{UNIFIED_PREFIXES['support']}exit")]
            ])

            await message.reply(support_text, reply_markup=keyboard, parse_mode='HTML')

            # Send initial message to admin about new support request
            try:
                from shared.notifications import notification_manager
                user = db.get_user(user_id) or {}
                username = user.get('username') or user.get('first_name') or f"ID: {user_id}"
                
                admin_notification = f"🆘 <b>NEW SUPPORT REQUEST</b>\n\n👤 <b>User:</b> {username} (ID: {user_id})\n⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                await notification_manager.create_notification(
                    user_id=ADMIN_ID,
                    notification_type="new_support_request",
                    title="🆘 New Support Request",
                    message=admin_notification,
                    action_url=f"/admin/support"
                )
                logger.info(f"New support request notification sent to admin for user {user_id}")
            except Exception as admin_error:
                logger.error(f"Failed to send admin notification: {admin_error}")

            logger.info(f"User {user_id} entered support mode ({language})")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "support")

    async def handle_support_message(self, message: Message) -> None:
        """Handle messages in support chat mode."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            text = message.text.strip()
            language = self._get_user_language(user_id)

            # Check if user is in support mode
            state = self._get_user_state(user_id)
            if not state.get('support_mode'):
                # User is not in support mode, handle as regular message
                return

            logger.info(f"User {user_id} sent support message: '{text}'")

            # Check rate limit - only 1 message every 5 seconds
            if self._check_support_rate_limit(user_id):
                rate_limit_text = localization.get_text('support_message_rate_limit', language) if localization else "❌ <b>Rate limit exceeded</b>\n\nYou can send only 1 message every 5 seconds.\n\nPlease wait and try again later."
                await message.reply(rate_limit_text, parse_mode='HTML')
                return

            # Save message to database
            if db.save_support_message(user_id, text, is_from_user=True):
                # Send confirmation to user
                confirmation_text = localization.get_text('support_message_sent', language) if localization else "✅ <b>Message sent!</b>\n\nOur support team will respond as soon as possible."
                await message.reply(confirmation_text, parse_mode='HTML')

                # Notify admin
                try:
                    from shared.notifications import notification_manager
                    user = db.get_user(user_id) or {}
                    username = user.get('username') or user.get('first_name') or f"ID: {user_id}"
                    
                    admin_notification = f"💬 <b>NEW SUPPORT MESSAGE</b>\n\n👤 <b>From:</b> {username} (ID: {user_id})\n📝 <b>Message:</b> {text[:100]}...\n⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    
                    await notification_manager.create_notification(
                        user_id=ADMIN_ID,
                        notification_type="support_message",
                        title=f"💬 New Message from {username}",
                        message=admin_notification,
                        action_url=f"/admin/support"
                    )
                    logger.info(f"Support message notification sent to admin for user {user_id}")
                except Exception as admin_error:
                    logger.error(f"Failed to send admin notification: {admin_error}")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "support_message")

    async def handle_support_exit(self, callback: CallbackQuery) -> None:
        """Handle exiting support mode."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)

            # Check if user is in support mode
            state = self._get_user_state(user_id)
            if not state.get('support_mode'):
                await callback.answer("You are not in support mode", show_alert=True)
                return

            # Exit support mode
            self._update_user_state(user_id, {'support_mode': False})

            # Send confirmation
            exit_text = localization.get_text('support_exited', language) if localization else "✅ <b>Support chat ended</b>\n\nYou have exited support mode. Use /support to start a new chat."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=localization.get_text('back', language) if localization else '🔙 Back', callback_data=f"{UNIFIED_PREFIXES['nav']}main")]
            ])

            await callback.message.edit_text(exit_text, reply_markup=keyboard, parse_mode='HTML')
            await callback.answer("Support chat ended")

            logger.info(f"User {user_id} exited support mode")

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "support_exit")

    async def handle_admin_support_chat(self, callback: CallbackQuery) -> None:
        """Handle admin support chat interface."""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return


            # Get all active support conversations
            conversations = db.get_all_support_conversations(limit=20)

            if not conversations:
                text = "🆘 <b>SUPPORT CHAT</b>\n\nNo active support conversations."
            else:
                text = "🆘 <b>SUPPORT CHAT</b>\n\n📋 <b>Active Conversations:</b>\n\n"
                
                for conv in conversations:
                    unread = conv.get('unread_count', 0)
                    last_msg = conv.get('last_message', '')[:50] + '...' if len(conv.get('last_message', '')) > 50 else conv.get('last_message', '')
                    
                    text += f"👤 {conv.get('username', 'Unknown')} (ID: {conv['user_id']})\n"
                    text += f"   📝 {last_msg}\n"
                    if unread > 0:
                        text += f"   🔴 {unread} unread\n"
                    text += f"   ⏰ {conv.get('last_message_time', '')[:16]}\n\n"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"{UNIFIED_PREFIXES['admin']}support")],
                [InlineKeyboardButton(text="🔙 Back to Admin", callback_data=f"{UNIFIED_PREFIXES['admin']}disputes")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_support")

    async def handle_admin_support_response(self, callback: CallbackQuery) -> None:
        """Handle admin responding to support messages."""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            # Parse user ID from callback data
            data = callback.data.replace(f"{UNIFIED_PREFIXES['admin']}support_response:", "")
            target_user_id = int(data)

            # Set up state for admin response
            self._set_user_state(user_id, {
                'step': 'admin_support_response',
                'target_user_id': target_user_id,
                'language': 'en'
            })

            # Get user info
            target_user = db.get_user(target_user_id) or {}
            username = target_user.get('username') or target_user.get('first_name') or f"ID: {target_user_id}"

            text = f"✏️ <b>RESPOND TO SUPPORT REQUEST</b>\n\n👤 <b>User:</b> {username} (ID: {target_user_id})\n\n💬 <b>Enter your response:</b>"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"{UNIFIED_PREFIXES['admin']}support")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_support_response")

    async def handle_admin_support_message(self, message: Message) -> None:
        """Handle admin support response message."""
        try:
            user_id = message.from_user.id
            if user_id != ADMIN_ID:
                return

            state = self._get_user_state(user_id)
            if not state or state.get('step') != 'admin_support_response':
                return

            target_user_id = state.get('target_user_id')
            response_text = message.text.strip()

            if len(response_text) < 10:
                await message.reply("❌ <b>Response too short</b>\n\nPlease provide a more detailed response (at least 10 characters).", parse_mode='HTML')
                return

            if len(response_text) > 1000:
                await message.reply("❌ <b>Response too long</b>\n\nPlease keep your response under 1000 characters.", parse_mode='HTML')
                return

            # Save admin message
            if db.save_admin_message(user_id, target_user_id, response_text, 'direct'):
                # Also save to support chat for tracking
                db.save_support_message(target_user_id, response_text, is_from_user=False)

                # Send confirmation to admin
                success_text = f"✅ <b>Response sent!</b>\n\n👤 <b>To:</b> User {target_user_id}\n💬 <b>Message:</b> {response_text[:100]}..."
                await message.reply(success_text, parse_mode='HTML')

                # Send message to user
                try:
                    from bot.main import bot
                    
                    db.get_user_language(target_user_id)
                    formatted_message = f"🆘 <b>Support Response</b>\n\n{response_text}"
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💬 Continue Chat", callback_data=f"/support")]
                    ])
                    
                    await bot.send_message(
                        target_user_id,
                        formatted_message,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    
                    logger.info(f"Admin {user_id} sent support response to user {target_user_id}")
                except Exception as send_error:
                    logger.error(f"Failed to send support response to user {target_user_id}: {send_error}")

                # Clear state
                self._clear_user_state(user_id)

        except Exception as e:
            await self.error_handler.handle_error(message, e, "admin_support_message")
            self._clear_user_state(user_id)

    async def handle_help(self, message: Message) -> None:
        """Handle /help command with localized help message."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            language = self._get_user_language(user_id)

            # Get localized help text
            help_text = localization.get_text('help_text', language) if localization else "Help & Support\n\nAvailable Commands:\n/start - Start bot and main menu\n/help - Show this help message\n/profile - View your profile and statistics\n\nMain Features:\n• Create guaranteed deals\n• Join existing deals\n• Track your statistics\n• Multi-language support\n\nSecurity:\n• All transactions are guaranteed\n• Funds are blocked until conditions are met\n• 24/7 automatic processing\n\nSupport:\nIf you need help, use the support chat in your profile.\n\nBlack Diamond - Your reliable guarantor!"

            # Create keyboard with main menu option
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=localization.get_text('back', language) if localization else 'Back', callback_data=f"{UNIFIED_PREFIXES['nav']}main")]
            ])

            await message.reply(help_text, reply_markup=keyboard, parse_mode='HTML')

            logger.info(f"Handled /help for user {user_id} ({language})")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "help")

    async def handle_language_selection(self, callback: CallbackQuery) -> None:
        """Handle language selection button click - show language options."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)

            # Create language selection keyboard
            keyboard = self.keyboard_factory.create_language_selection_keyboard(language)

            # Check if message has content (text or caption) before editing
            has_content = (callback.message and
                          (callback.message.text or
                           (hasattr(callback.message, 'caption') and callback.message.caption)))

            if has_content:
                try:
                    # Try to edit text first
                    if callback.message.text:
                        await callback.message.edit_text(
                            text=localization.get_text('language_selection_header', language),
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                    # If it's a photo message with caption
                    elif hasattr(callback.message, 'caption') and callback.message.caption:
                        await callback.message.edit_caption(
                            caption=localization.get_text('language_selection_header', language),
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                except Exception as edit_error:
                    # If editing fails, send new message
                    logger.warning(f"Failed to edit message for user {user_id}: {edit_error}")
                    await callback.message.answer(
                        text=localization.get_text('language_selection_header', language),
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            else:
                # Send new message if no content
                await callback.message.answer(
                    text=localization.get_text('language_selection_header', language),
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

            await callback.answer()

        except Exception as e:
            logger.error(f"Language selection button error for user {callback.from_user.id}: {e}")
            try:
                await callback.answer("❌ Error opening language menu. Please try again.", show_alert=True)
            except Exception:
                pass

    async def handle_language_change(self, callback: CallbackQuery) -> None:
        """Handle actual language change from selection menu with immediate reply keyboard."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language_code = callback.data.replace(f"{UNIFIED_PREFIXES['start']}", "").replace("lang_", "")

            # Validate language
            available_langs = list(localization.get_available_languages().keys())
            if language_code not in available_langs:
                await callback.answer("❌ Invalid language selection", show_alert=True)
                return

            # Update user language
            self._set_user_language(user_id, language_code)

            # Get updated welcome message
            first_name = callback.from_user.first_name or callback.from_user.username or "User"
            welcome_text = format_welcome_message(language_code, first_name)

            # Create new inline keyboard with updated language and admin access
            keyboard = self.keyboard_factory.create_main_menu_keyboard(language_code, user_id)

            # Check if message has content (text or caption) before editing
            has_content = (callback.message and
                          (callback.message.text or
                           (hasattr(callback.message, 'caption') and callback.message.caption)))

            if has_content:
                try:
                    # Try to edit text first
                    if callback.message.text:
                        await callback.message.edit_text(
                            text=welcome_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                    # If it's a photo message with caption
                    elif hasattr(callback.message, 'caption') and callback.message.caption:
                        await callback.message.edit_caption(
                            caption=welcome_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                except Exception as edit_error:
                    # If editing fails, send new message
                    logger.warning(f"Failed to edit message for user {user_id}: {edit_error}")
                    await callback.message.answer(
                        text=welcome_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            else:
                # Send new message if no content
                await callback.message.answer(
                    text=welcome_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

            # Create and send updated reply keyboard with new language immediately
            try:
                # First, remove the old reply keyboard by sending empty keyboard
                await callback.message.answer("🔄", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, keyboard=[]))
                 
                # Then send the new reply keyboard with updated language (respecting admin)
                main_menu_keyboard = self.keyboard_factory.create_main_reply_keyboard(language_code, user_id)
                await callback.message.answer("💎", reply_markup=main_menu_keyboard)
                
                logger.info(f"Updated reply keyboard for user {user_id} to language {language_code}")
            except Exception as keyboard_error:
                logger.warning(f"Failed to send updated reply keyboard for user {user_id}: {keyboard_error}")

            await callback.answer(f"✅ Language changed to {localization.get_available_languages()[language_code]}")

            logger.info(f"User {user_id} changed language to {language_code}")

        except Exception as e:
            logger.error(f"Language change error for user {callback.from_user.id}: {e}")
            try:
                await callback.answer("❌ Error changing language. Please try again.", show_alert=True)
            except Exception:
                pass

    async def handle_login_website(self, callback: CallbackQuery) -> None:
        """Handle website login action."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)

            # Ensure user exists
            user = db.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} does not exist but tried to login to website")
                await callback.answer("❌ User not found. Please restart the bot with /start", show_alert=True)
                return

            # Generate auth token
            token = db.create_auth_token(user_id)

            if not token:
                await callback.answer("❌ Error generating login token", show_alert=True)
                return

            login_text = localization.get_text('login_title', language)
            base_url = (PUBLIC_BASE_URL or "").strip().rstrip("/")
            if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
                base_url = f"https://{base_url}"
            login_link = f"{base_url}/auth/token/{token}"
            short_link = login_link.replace("https://", "")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('login_website', language),
                    url=login_link
                )],
                [InlineKeyboardButton(
                    text=localization.get_text('back', language),
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )]
            ])

            login_message = f"{login_text}\n\n{localization.get_text('login_link', language)}\n{short_link}\n\n{localization.get_text('login_important', language)}\n{localization.get_text('login_valid', language)}\n{localization.get_text('login_once', language)}\n{localization.get_text('login_auto', language)}\n\n{localization.get_text('login_click', language)}"

            # Check if message has content before editing
            if callback.message and callback.message.text:
                try:
                    await callback.message.edit_text(
                        text=login_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as edit_error:
                    # If editing fails, send new message
                    logger.warning(f"Failed to edit message for user {user_id}: {edit_error}")
                    await callback.message.answer(
                        text=login_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
            else:
                # Send new message if no text content
                await callback.message.answer(
                    text=login_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

            await callback.answer()

        except Exception as e:
            logger.error(f"Login website handler error for user {callback.from_user.id}: {e}")
            try:
                await callback.answer("❌ Error generating login link. Please try again.", show_alert=True)
            except Exception:
                pass

    async def handle_back_to_main(self, callback: CallbackQuery) -> None:
        """Handle back to main menu with proper reply keyboard."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            language = self._get_user_language(user_id)

            first_name = callback.from_user.first_name or callback.from_user.username or "User"
            welcome_text = format_welcome_message(language, first_name)

            keyboard = self.keyboard_factory.create_main_menu_keyboard(language, user_id)

            # Check if message has content (text or caption) before editing
            has_content = (callback.message and
                          (callback.message.text or
                           (hasattr(callback.message, 'caption') and callback.message.caption)))

            if has_content:
                try:
                    # Try to edit text first
                    if callback.message.text:
                        await callback.message.edit_text(
                            text=welcome_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                    # If it's a photo message with caption
                    elif hasattr(callback.message, 'caption') and callback.message.caption:
                        await callback.message.edit_caption(
                            caption=welcome_text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                except Exception as edit_error:
                    # If editing fails, send new message
                    logger.warning(f"Failed to edit message for user {user_id}: {edit_error}")
                    await callback.message.answer(
                        text=welcome_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            else:
                # Send new message if no content
                await callback.message.answer(
                    text=welcome_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

            # Send the reply keyboard to ensure it's properly set
            try:
                # First, remove the old reply keyboard by sending empty keyboard
                await callback.message.answer("🔄", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, keyboard=[]))
                 
                # Then send the new reply keyboard
                main_menu_keyboard = self.keyboard_factory.create_main_reply_keyboard(language, user_id)
                await callback.message.answer("💎", reply_markup=main_menu_keyboard)
                
                logger.info(f"Updated reply keyboard for user {user_id} in back to main")
            except Exception as keyboard_error:
                logger.warning(f"Failed to send reply keyboard for user {user_id}: {keyboard_error}")

            await callback.answer()

        except Exception as e:
            logger.error(f"Back to main handler error for user {callback.from_user.id}: {e}")
            try:
                await callback.answer("❌ Error returning to main menu. Please try again.", show_alert=True)
            except Exception:
                pass

    # ===== REPLY KEYBOARD HANDLERS =====

    def _build_admin_panel_keyboard(self, language: str) -> InlineKeyboardMarkup:
        """
        Build unified admin panel inline keyboard.

        This helper is used both by handle_admin_panel_command (reply button)
        and handle_admin_disputes (callback entrypoint) to keep admin menu consistent.
        """
        # Core admin sections + disputes
        rows = [
            [
                InlineKeyboardButton(
                    text=localization.get_text("admin_users", language) if localization else "Users",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}users"
                )
            ],
            [
                InlineKeyboardButton(
                    text=localization.get_text("admin_deals", language) if localization else "Deals",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}deals"
                )
            ],
            [
                InlineKeyboardButton(
                    text=localization.get_text("admin_settings", language) if localization else "Settings",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}settings"
                )
            ],
            [
                InlineKeyboardButton(
                    text=localization.get_text("admin_statistics", language) if localization else "Statistics",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}platform_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="View All Disputes",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}list_all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Active Disputes",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}list_open"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Add Dispute Response",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}response_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Dispute Stats",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}stats"
                )
            ],
        ]

        # Support chat button
        rows.append(
            [
                InlineKeyboardButton(
                    text="🆘 Support Chat",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}support"
                )
            ]
        )

        # Mass cancel button (admin-only action entrypoint)
        try:
            cancel_all_text = localization.get_text("admin_cancel_all_deals", language)
        except Exception:
            # Fallback text in case of localization issues; key should exist per spec
            cancel_all_text = "🛑 Cancel all active deals"

        rows.append(
            [
                InlineKeyboardButton(
                    text=cancel_all_text,
                    callback_data="admin_cancel_all_deals"
                )
            ]
        )

        # Back to main navigation
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔙 Back to Main",
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )
            ]
        )

        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def handle_admin_panel_command(self, message: Message) -> None:
        """Handle Admin panel button/command from reply keyboard safely."""
        if await self._block_banned_user(message):
            return
        try:
            # Strictly validate sender and admin rights
            if not message.from_user or message.from_user.id != ADMIN_ID:
                # Default to English if we cannot resolve language safely
                user_id = message.from_user.id if message.from_user else None
                language = self._get_user_language(user_id) if user_id else 'en'
                access_denied_text = (
                    localization.get_text("access_denied", language)
                    if localization else "Access denied"
                )
                await message.answer(access_denied_text)
                return

            user_id = message.from_user.id
            language = self._get_user_language(user_id)

            # Build admin panel keyboard via shared helper
            keyboard = self._build_admin_panel_keyboard(language)

            # Show admin panel directly in admin chat WITHOUT fake callbacks
            title = (
                localization.get_text("admin_panel_title", language)
                if localization else "🏛️ Admin panel"
            )
            await message.answer(title, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "admin_panel")

    async def handle_create_deal_button(self, message: Message) -> None:
        """Handle create deal button press from reply keyboard."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} pressed 'create deal' button")

            # Start the deal creation flow
            await self.handle_create_deal_start(message)

            logger.info(f"User {user_id} successfully started create deal flow")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_creation")

    async def handle_join_deal_button(self, message: Message) -> None:
        """Handle join deal button press from reply keyboard."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} pressed 'join deal' button")

            # Start the join deal flow
            await self.handle_join_deal_start(message)

            logger.info(f"User {user_id} successfully started join deal flow")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_join")

    async def handle_my_deals_button(self, message: Message) -> None:
        """Handle my deals button press from reply keyboard."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} pressed 'my deals' button")

            # Start the my deals flow
            await self.handle_my_deals(message)

            logger.info(f"User {user_id} successfully started my deals flow")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "deal_join")

    async def handle_profile_button(self, message: Message) -> None:
        """Handle profile button press from reply keyboard."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            self._get_user_language(user_id)

            logger.info(f"User {user_id} pressed 'profile' button")

            # Start the profile view
            await self.handle_profile_view(message)

            logger.info(f"User {user_id} successfully started profile view")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "profile")

    async def handle_fallback_text_message(self, message: Message) -> None:
        """Handle any text message that doesn't match specific handlers."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            text = message.text.strip().lower()
            language = self._get_user_language(user_id)

            logger.info(f"User {user_id} sent text message: '{message.text}' (language: {language})")

            # Check if it's a deal code (8 characters) first
            original_text = message.text.strip()
            if len(original_text) == 8 and re.match(r'^[A-Z0-9]+$', original_text):
                # Treat as deal code input - check if user is in join flow
                if user_id in self.conversation_states and self.conversation_states[user_id].get('step') == 'awaiting_join_code':
                    await self.handle_join_code_message(message)
                    return
                else:
                    # Not in join flow, ignore
                    return

            # Handle common button texts regardless of localization
            if text in ['create deal', 'create_deal', 'створити угоду']:
                await self.handle_create_deal_button(message)
            elif text in ['my deals', 'my_deals', 'мої угоди']:
                # Start my deals flow - show user's deal history
                await self.handle_my_deals_button(message)
            elif text in ['join deal', 'join_deal', 'приєднатися до угоди']:
                # Start join deal flow with prompt
                await self.handle_join_deal_start(message)
            elif text in ['profile', 'профіль']:
                await self.handle_profile_button(message)
            else:
                # Unknown command - show help
                help_text = localization.get_text('help_text', language)
                await message.reply(help_text, parse_mode='HTML')

        except Exception as e:
            await self.error_handler.handle_error(message, e, "general")

    async def handle_dispute_description_message(self, message: Message) -> None:
        """Handle dispute description input and create dispute record."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            if user_id not in self.conversation_states or self.conversation_states[user_id].get('step') != 'awaiting_dispute_description':
                return

            language = self.conversation_states[user_id]['language']
            deal_code = self.conversation_states[user_id]['deal_code']
            description = message.text.strip()

            # Validate description length
            if len(description) < 10:
                error_text = localization.get_text('dispute_description_too_short', language) if localization else "❌ <b>Description too short</b>\n\nPlease provide a more detailed description of your problem (at least 10 characters)."
                await message.reply(error_text, parse_mode='HTML')
                return

            if len(description) > 1000:
                error_text = localization.get_text('dispute_description_too_long', language) if localization else "❌ <b>Description too long</b>\n\nPlease keep your description under 1000 characters."
                await message.reply(error_text, parse_mode='HTML')
                return

            # Get deal and user information
            deal = db.get_deal(deal_code)
            if not deal:
                await message.reply("❌ Deal not found. Please try again.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Get user information
            db.get_user(user_id) or {}
            buyer = db.get_user(deal.get('buyer_id')) or {}
            seller = db.get_user(deal.get('seller_id')) or {}

            # Create dispute record in database
            from datetime import datetime
            
            try:
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO disputes
                        (deal_code, buyer_id, seller_id, amount, currency, reason, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        deal_code,
                        deal.get('buyer_id'),
                        deal.get('seller_id'),
                        deal.get('amount'),
                        deal.get('currency'),
                        description,
                        'open',
                        datetime.now().isoformat()
                    ))
                    dispute_id = cursor.lastrowid
                    conn.commit()
                    
                logger.info(f"Created dispute record {dispute_id} for deal {deal_code}")
                
            except Exception as db_error:
                logger.error(f"Failed to create dispute record: {db_error}")
                await message.reply("❌ Error creating dispute record. Please try again.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Update deal status to dispute_open
            success = db.update_deal_status(deal_code, 'dispute_open')
            if not success:
                logger.error(f"Failed to update deal {deal_code} status to dispute_open")
                await message.reply("❌ Error updating deal status. Please contact support.", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Send confirmation to user
            success_text = localization.get_text('dispute_created_success', language,
                code=deal_code,
                dispute_id=dispute_id
            ) if localization else f"✅ <b>Dispute Created Successfully!</b>\n\n🆔 <b>Dispute ID:</b> #{dispute_id}\n📄 <b>Deal Code:</b> {deal_code}\n\n🛡️ <b>What happens next:</b>\n• Our support team will review your dispute\n• You'll receive updates via notifications\n• Both parties will be contacted for additional information\n• Resolution typically takes 24-48 hours\n\n💬 <b>You can track your dispute status in the deal details.</b>"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=localization.get_text('view_deal', language, code=deal_code) if localization else f"View {deal_code}",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                )],
                [InlineKeyboardButton(
                    text=localization.get_text('back_to_main', language) if localization else "Back to Main",
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )]
            ])

            await message.reply(success_text, reply_markup=keyboard, parse_mode='HTML')

            # Send dispute notification to admin
            try:
                from shared.notifications import notification_manager
                
                from html import escape as _html_escape

                buyer = dict(buyer or {})
                seller = dict(seller or {})
                if buyer.get('username'):
                    buyer['username'] = _html_escape(str(buyer['username']), quote=False)
                if buyer.get('first_name'):
                    buyer['first_name'] = _html_escape(str(buyer['first_name']), quote=False)
                if seller.get('username'):
                    seller['username'] = _html_escape(str(seller['username']), quote=False)
                if seller.get('first_name'):
                    seller['first_name'] = _html_escape(str(seller['first_name']), quote=False)
                description = _html_escape(str(description), quote=False)

                buyer_part = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
                seller_part = seller.get('username') or seller.get('first_name') or f"ID: {deal.get('seller_id')}"

                admin_notification = (
                    f"🚨 <b>NEW DISPUTE OPENED</b>\n\n"
                    f"🆔 <b>Dispute ID:</b> #{dispute_id}\n"
                    f"📄 <b>Deal Code:</b> {deal_code}\n"
                    f"💰 <b>Amount:</b> {deal.get('amount')} {deal.get('currency')}\n\n"
                    f"👥 <b>Parties:</b>\n"
                    f"• Buyer: {buyer_part}\n"
                    f"• Seller: {seller_part}\n\n"
                    f"📝 <b>Problem Description:</b>\n{description}\n\n"
                    f"⏰ <b>Opened:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                await notification_manager.create_notification(
                    user_id=ADMIN_ID,
                    notification_type="new_dispute",
                    title="🚨 New Dispute Opened",
                    message=admin_notification,
                    action_url=f"/admin/disputes/{dispute_id}"
                )
                
                logger.info(f"Dispute notification sent to admin for dispute {dispute_id}")
                
            except Exception as admin_error:
                logger.error(f"Failed to send admin notification: {admin_error}")
                # Don't fail the whole process if admin notification fails

            # Clear conversation state
            self._clear_user_state(user_id)

            logger.info(f"Dispute created successfully: {dispute_id} for deal {deal_code} by user {user_id}")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "dispute_creation")
            self._clear_user_state(user_id)

    async def handle_confirm_delivery(self, callback: CallbackQuery) -> None:
        """Handle seller confirming delivery"""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}confirm_delivery:", "")
            deal_code = data.upper()
            language = self._get_user_language(user_id)
            if not await self._zt_enforce_rate_limit(callback, language):
                return

            # Zero Trust: enforce access + allowed state (do not trust callback payload)
            try:
                self._zt_validate_deal(
                    user_id,
                    deal_code,
                    required_role='seller',
                    allowed_states=['funded', 'delivery_pending']
                )
            except StateValidationError:
                await callback.answer("❌ Deal is not ready for delivery confirmation", show_alert=True)
                return
            except AuthorizationError as e:
                if "not found" in str(e).lower():
                    await callback.answer("❌ Deal not found", show_alert=True)
                else:
                    await callback.answer("❌ Only the seller can confirm delivery", show_alert=True)
                return




            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            # Check if user is the seller
            if deal.get('seller_id') != user_id:
                await callback.answer("❌ Only the seller can confirm delivery", show_alert=True)
                return

            # Check if deal is in correct status
            if deal.get('status') not in ['funded', 'delivery_pending']:
                await callback.answer("❌ Deal is not ready for delivery confirmation", show_alert=True)
                return

            # Show processing
            await callback.message.edit_text(
                localization.get_text("processing_delivery_confirmation", language),
                parse_mode="HTML",
            )

            # Update deal status to receipt_pending
            success = db.update_deal_status(deal_code, 'receipt_pending')
            if not success:
                await callback.message.edit_text(
                    localization.get_text("error_status_update", language),
                    parse_mode="HTML",
                )
                await callback.answer("❌ Failed to update deal status", show_alert=True)
                return

            # Refresh deal data
            deal = db.get_deal(deal_code)
            buyer = db.get_user(deal.get('buyer_id')) or {}
            seller = db.get_user(deal.get('seller_id')) or {}
            enhanced_deal = dict(deal)
            enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
            enhanced_deal['seller_name'] = seller.get('username') or seller.get('first_name') or f"ID: {deal.get('seller_id')}"

            # Update message with new deal info
            text = format_deal_info(enhanced_deal, language)
            buttons = [
                [InlineKeyboardButton(
                    text=localization.get_text('button_view_deal', language, code=deal_code) if localization else f"View {deal_code}",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                )]
            ]

            # Back button - use breadcrumb system
            breadcrumb_trail = self.get_breadcrumb_trail(user_id)
            if len(breadcrumb_trail) > 1:
                # Go back to previous section
                previous_section = breadcrumb_trail[-2]  # Second to last is the previous page
                if previous_section == 'profile':
                    back_callback = f"{UNIFIED_PREFIXES['profile']}view"
                elif previous_section == 'my_deals':
                    back_callback = f"{UNIFIED_PREFIXES['deal']}my_deals"
                elif previous_section == 'main':
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"
                else:
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"  # Default fallback
            else:
                # No breadcrumb or only one entry, default to main
                back_callback = f"{UNIFIED_PREFIXES['nav']}main"

            buttons.append([InlineKeyboardButton(
                text=localization.get_text('back', language) if localization else 'Back',
                callback_data=back_callback
            )])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode='HTML')

            # Notify buyer to confirm receipt
            buyer_id = deal.get('buyer_id')
            if buyer_id:
                buyer_language = self._get_user_language(buyer_id)
                buyer_message = localization.get_text('delivery_confirmed_buyer', buyer_language)

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=localization.get_text('button_confirm_receipt', buyer_language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}confirm_receipt:{deal_code}"
                    )],
                    [InlineKeyboardButton(
                        text=localization.get_text('button_view_deal', buyer_language, code=deal_code) if localization else f"View {deal_code}",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                    )]
                ])

                try:
                    # Use direct Telegram API notification for reliability
                    await self._send_telegram_notification_direct(
                        user_id=buyer_id,
                        title="",
                        message=buyer_message,
                        action_url=f"/deal/{deal_code}",
                        custom_keyboard=keyboard
                    )
                except Exception as notify_error:
                    logger.warning(f"Failed to send delivery confirmation to buyer {buyer_id}: {notify_error}")

            await callback.answer(
                localization.get_text("alert_delivery_confirmed", language),
                show_alert=True,
            )

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "confirm_delivery")

    async def handle_confirm_receipt(self, callback: CallbackQuery) -> None:
        """Handle buyer confirming receipt"""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}confirm_receipt:", "")
            deal_code = data.upper()
            language = self._get_user_language(user_id)

            if not await self._zt_enforce_rate_limit(callback, language):
                return

            try:
                self._zt_validate_deal(user_id, deal_code, required_role='buyer', allowed_states=['receipt_pending'])
            except (AuthorizationError, StateValidationError):
                await callback.answer("Access denied", show_alert=True)
                return

            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            # Check if user is the buyer
            if deal.get('buyer_id') != user_id:
                await callback.answer("❌ Only the buyer can confirm receipt", show_alert=True)
                return

            # Check if deal is in receipt_pending status
            if deal.get('status') != 'receipt_pending':
                await callback.answer("❌ Deal is not ready for receipt confirmation", show_alert=True)
                return

            # Show processing
            await callback.message.edit_text(
                localization.get_text("processing_receipt_confirmation", language),
                parse_mode="HTML",
            )

            # Update deal status to funds_pending
            success = db.update_deal_status(deal_code, 'funds_pending')
            if not success:
                await callback.message.edit_text(
                    localization.get_text("error_status_update", language),
                    parse_mode="HTML",
                )
                await callback.answer("❌ Failed to update deal status", show_alert=True)
                return

            # Refresh deal data
            deal = db.get_deal(deal_code)
            buyer = db.get_user(deal.get('buyer_id')) or {}
            seller = db.get_user(deal.get('seller_id')) or {}
            enhanced_deal = dict(deal)
            enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
            enhanced_deal['seller_name'] = seller.get('username') or seller.get('first_name') or f"ID: {deal.get('seller_id')}"

            # Update message with new deal info
            text = format_deal_info(enhanced_deal, language)
            buttons = [
                [InlineKeyboardButton(
                    text=localization.get_text('button_view_deal', language, code=deal_code) if localization else f"View {deal_code}",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                )]
            ]

            # Back button - use breadcrumb system
            breadcrumb_trail = self.get_breadcrumb_trail(user_id)
            if len(breadcrumb_trail) > 1:
                # Go back to previous section
                previous_section = breadcrumb_trail[-2]  # Second to last is the previous page
                if previous_section == 'profile':
                    back_callback = f"{UNIFIED_PREFIXES['profile']}view"
                elif previous_section == 'my_deals':
                    back_callback = f"{UNIFIED_PREFIXES['deal']}my_deals"
                elif previous_section == 'main':
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"
                else:
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"  # Default fallback
            else:
                # No breadcrumb or only one entry, default to main
                back_callback = f"{UNIFIED_PREFIXES['nav']}main"

            buttons.append([InlineKeyboardButton(
                text=localization.get_text('back', language) if localization else 'Back',
                callback_data=back_callback
            )])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode='HTML')

            # Notify seller to provide wallet address for withdrawal
            seller_id = deal.get('seller_id')
            if seller_id:
                seller_language = self._get_user_language(seller_id)
                _, commission_amount, seller_amount = get_commission_breakdown(float(deal['amount']))

                seller_message = localization.get_text('funds_released_seller', seller_language) if localization else (
                    f"💰 <b>Funds ready for withdrawal!</b>\n\n"
                    f"✅ Buyer confirmed receipt.\n\n"
                    f"💵 <b>Your amount:</b> {seller_amount:.2f} {deal['currency']}\n"
                    f"💸 <b>Fee:</b> {commission_amount:.2f} {deal['currency']}\n\n"
                    f"Funds will be sent to your wallet."
                )

                # Set conversation state to await wallet address
                self._set_user_state(seller_id, {
                    'step': 'awaiting_withdrawal_wallet',
                    'deal_code': deal_code,
                    'language': seller_language
                })

                # Create wallet address input prompt
                wallet_prompt = (
                    f"{localization.get_text('withdraw_to_wallet_message', seller_language)}\n\n"
                    f"{localization.get_text('final_amount_line', seller_language, final_amount=seller_amount, currency=deal['currency'])}\n"
                    f"{localization.get_text('platform_fee_line', seller_language, fee=commission_amount, currency=deal['currency'])}\n"
                    f"{localization.get_text('withdraw_amount_line', seller_language, amount=seller_amount, currency=deal['currency'])}\n\n"
                    f"{localization.get_text('enter_wallet_address', seller_language)}\n\n"
                    f"{localization.get_text('withdrawal_important', seller_language)}\n"
                    f"{localization.get_text('check_address_before_sending', seller_language)}\n"
                    f"{localization.get_text('address_must_match_currency', seller_language, currency=deal['currency'])}\n"
                    f"{localization.get_text('you_will_receive_exact', seller_language, amount=seller_amount, currency=deal['currency'])}"
                )

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=localization.get_text('button_view_deal', seller_language, code=deal_code) if localization else f"View {deal_code}",
                        callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                    )],

                ])

                try:
                    # Use direct Telegram API notification for reliability
                    await self._send_telegram_notification_direct(
                        user_id=seller_id,
                        title="",
                        message=f"{seller_message}\n\n{wallet_prompt}",
                        action_url=f"/deal/{deal_code}",
                        custom_keyboard=keyboard
                    )
                except Exception as notify_error:
                    logger.warning(f"Failed to send funds release notification to seller {seller_id}: {notify_error}")

            await callback.answer("✅ Receipt confirmed!", show_alert=True)

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "confirm_receipt")

    async def handle_share_deal(self, callback: CallbackQuery) -> None:
        """Handle share deal code button - deal code is shared via link sharing"""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}share_deal:", "")
            deal_code = data.upper()
            self._get_user_language(user_id)

            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            # Check if user is the buyer
            if deal.get('buyer_id') != user_id:
                await callback.answer("❌ Only the buyer can share the deal code", show_alert=True)
                return

            # Deal code sharing is handled via the link in the message above
            # No additional message needed as per user request
            await callback.answer("✅ Deal code ready for sharing!", show_alert=True)

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "share_deal")

    async def handle_payment_method_selection(self, callback: CallbackQuery) -> None:
        """Handle buyer selecting payment method (direct cryptocurrency payment)."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}payment_method:", "")
            deal_code = data.upper()
            language = self._get_user_language(user_id)

            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            # Check if user is the buyer
            if deal.get('buyer_id') != user_id:
                await callback.answer("❌ Only buyer can pay", show_alert=True)
                return

            # Check if deal is in correct status
            if deal.get('status') != 'active':
                await callback.answer("❌ Deal not ready for payment", show_alert=True)
                return

            currency = deal.get('currency', 'USDT')
            currency_upper = currency.upper()
            deal_amount = float(deal.get('amount', 0))
            payment_memo = None
            try:
                payment = db.get_decentralized_payment_by_deal_code(deal_code)
                if payment:
                    payment_memo = (
                        payment.get('memo')
                        or payment.get('checkout_id')
                        or payment.get('deal_memo')
                        or payment.get('comment')
                    )
            except Exception:
                payment_memo = None
            if not payment_memo and currency_upper == "TON":
                payment_memo = f"DEAL-{deal_code}"

            # Get payment address from ENV
            from shared.config import USDT_SYSTEM_ADDRESS, TON_SYSTEM_ADDRESS, USDT_WALLET_ADDRESS, TON_WALLET_ADDRESS
            if currency == 'USDT':
                payment_address = USDT_SYSTEM_ADDRESS or USDT_WALLET_ADDRESS
            elif currency == 'TON':
                payment_address = TON_SYSTEM_ADDRESS or TON_WALLET_ADDRESS
            else:
                await callback.answer("❌ Currency not supported", show_alert=True)
                return

            if not payment_address:
                await callback.answer("❌ Wallet address not configured", show_alert=True)
                return

            # Format the payment address for display
            formatted_address = self._format_clickable_address(payment_address, language)
            currency_display = "USDT (TRC20)" if currency == "USDT" else currency.upper()

            # Show detailed payment instructions
            text = f"💳 <b>{localization.get_text('payment_instructions_title', language)}</b>\n\n"
            text += f"💰 {localization.get_text('payment_amount', language, amount=deal_amount, currency=currency_display)}\n"
            text += f"🏦 {localization.get_text('payment_address', language)}\n"
            text += f"{formatted_address}\n\n"
            if payment_memo:
                text += f"Memo/Comment:\n<code>{payment_memo}</code>\n\n"
            text += f"⚠️ <b>{localization.get_text('payment_warning', language)}</b>\n"
            text += f"• {localization.get_text('payment_warning_exact', language, amount=deal_amount, currency=currency_display)}\n"
            text += f"• {localization.get_text('payment_warning_address', language)}\n"
            text += f"• {localization.get_text('payment_warning_confirmed', language)}\n\n"
            text += f"📋 <b>{localization.get_text('seller_joined_instructions', language)}</b>\n"
            text += f"{localization.get_text('seller_joined_instruction_1', language, amount=deal_amount, currency=currency_display)}\n"
            text += f"{localization.get_text('seller_joined_instruction_2', language)}\n"
            text += f"{localization.get_text('seller_joined_instruction_3', language)}\n"
            text += f"{localization.get_text('seller_joined_instruction_4', language)}\n\n"
            text += f"{localization.get_text('seller_joined_warning', language)}"

            # Create payment confirmation buttons
            buttons = [
                [
                    InlineKeyboardButton(
                        text=localization.get_text('button_sent_funds', language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}payment_sent:{deal_code}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=localization.get_text('back', language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                    )
                ]
            ]

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "payment_method_selection")



    async def handle_payment_sent(self, callback: CallbackQuery) -> None:
        """Handle buyer clicking the 'Payment sent' button and start wallet scanning."""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}payment_sent:", "")
            deal_code = data.upper()
            language = self._get_user_language(user_id)
            if not await self._zt_enforce_rate_limit(callback, language):
                return

            try:
                self._zt_validate_deal(user_id, deal_code, required_role='buyer', allowed_states=['active'])
            except (AuthorizationError, StateValidationError):
                await callback.answer("Access denied", show_alert=True)
                return

            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            # Check if user is the buyer
            if deal.get('buyer_id') != user_id:
                await callback.answer("❌ Only the buyer can confirm funds transfer", show_alert=True)
                return

            # Check if deal is in correct status
            if deal.get('status') != 'active':
                await callback.answer("❌ Deal is not ready for payment confirmation", show_alert=True)
                return

            # Show processing message with user's language
            await callback.message.edit_text(
                f"<b>{localization.get_text('checking_incoming_funds', language)}</b>\n\n{localization.get_text('scanning_wallet', language)}",
                parse_mode='HTML'
            )

            # Get payment address from ENV
            from shared.config import USDT_SYSTEM_ADDRESS, TON_SYSTEM_ADDRESS, USDT_WALLET_ADDRESS, TON_WALLET_ADDRESS
            currency = deal.get('currency', 'USDT')
            if currency == 'USDT':
                payment_address = USDT_SYSTEM_ADDRESS or USDT_WALLET_ADDRESS
            elif currency == 'TON':
                payment_address = TON_SYSTEM_ADDRESS or TON_WALLET_ADDRESS
            else:
                await callback.message.edit_text(
                    "❌ <b>Error</b>\n\nCurrency is not supported.",
                    parse_mode="HTML",
                )
                return

            if not payment_address:
                await callback.message.edit_text(
                    "❌ <b>Error</b>\n\nWallet address is not configured.",
                    parse_mode="HTML",
                )
                return

            # ADMIN simulation: keep flow like a regular user, but avoid blockchain scanning.
            # First press shows the "not found" UI; next press confirms instantly.
            if user_id == ADMIN_ID:
                amount = float(deal.get('amount', 0))
                currency = deal.get('currency', 'USDT')

                if deal_code not in self._admin_payment_refresh_ready:
                    self._admin_payment_refresh_ready.add(deal_code)

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=localization.get_text('button_check_again', language),
                            callback_data=f"{UNIFIED_PREFIXES['deal']}payment_sent:{deal_code}"
                        )],
                        [InlineKeyboardButton(
                            text=localization.get_text('button_view_deal', language, code=deal_code),
                            callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                        )]
                    ])

                    await callback.message.edit_text(
                        f"<b>{localization.get_text('funds_not_found', language)}</b>\n\n"
                        f"{localization.get_text('payment_check_performed', language, count=2)}\n\n"
                        f"💡 <b>{localization.get_text('payment_tip_title', language)}:</b> {localization.get_text('payment_tip_ensure', language)}\n"
                        f"• {localization.get_text('payment_tip_exact_amount', language, amount=amount, currency=currency)}\n"
                        f"• {localization.get_text('payment_tip_correct_address', language)}\n"
                        f"• {localization.get_text('payment_tip_confirmed', language)}",
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    await callback.answer(localization.get_text('funds_not_found', language), show_alert=True)
                    return

                self._admin_payment_refresh_ready.discard(deal_code)
                tx_hash = "ADMIN_SIMULATED"

                try:
                    updated = db.update_decentralized_payment_status(deal_code, 'confirmed', tx_hash)
                    if not updated:
                        payment = db.get_decentralized_payment_by_deal_code(deal_code)
                        if payment and payment.get('checkout_id'):
                            db.update_checkout_status(payment['checkout_id'], 'confirmed', tx_hash)
                except Exception:
                    pass

                db.update_deal_status(deal_code, 'funded', payment_confirmed_at=datetime.now().isoformat())

                seller_id = deal.get('seller_id')
                await self._notify_payment_confirmed(deal_code, user_id, seller_id, tx_hash)

                await callback.message.edit_text(
                    "✅ <b>Funds found!</b>\n\nCheck completed successfully. Notifications were sent to both parties.",
                    parse_mode='HTML'
                )
                await callback.answer("✅ Funds found!", show_alert=True)

                # Return the user to the updated deal card
                try:
                    refreshed_deal = db.get_deal(deal_code) or deal
                    buyer = db.get_user(refreshed_deal.get('buyer_id')) or {}
                    seller = db.get_user(refreshed_deal.get('seller_id')) or {}

                    enhanced_deal = dict(refreshed_deal)
                    enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {refreshed_deal.get('buyer_id')}"
                    enhanced_deal['seller_name'] = (
                        seller.get('username')
                        or seller.get('first_name')
                        or (f"ID: {refreshed_deal.get('seller_id')}" if refreshed_deal.get('seller_id') else self._get_not_assigned_text(language))
                    )

                    deal_text = format_deal_info(enhanced_deal, language)
                    deal_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=localization.get_text('button_view_deal', language, code=deal_code) if localization else f"View {deal_code}",
                            callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}",
                        )],
                        [InlineKeyboardButton(
                            text=localization.get_text('back', language) if localization else "Back",
                            callback_data=f"{UNIFIED_PREFIXES['nav']}main",
                        )],
                    ])
                    await callback.message.reply(deal_text, reply_markup=deal_keyboard, parse_mode='HTML')
                except Exception as deal_view_error:
                    logger.warning(f"Failed to send updated deal card after payment for {deal_code}: {deal_view_error}")

                return

            # Scan wallet 1-2 times
            amount = float(deal.get('amount', 0))
            is_paid = False
            tx_hash = None
            payment_memo = None
            try:
                payment = db.get_decentralized_payment_by_deal_code(deal_code)
                if payment:
                    payment_memo = (
                        payment.get('memo')
                        or payment.get('checkout_id')
                        or payment.get('deal_memo')
                        or payment.get('comment')
                    )
            except Exception:
                payment_memo = None
            if not payment_memo and currency.upper() == "TON":
                payment_memo = f"DEAL-{deal_code}"

            for attempt in range(2):  # Scan 2 times
                try:
                    # Use enhanced payment processor to check payment
                    # Check if payment exists in the wallet
                    if currency == 'USDT':
                        is_paid, tx_hash = decentralized_payment_processor.blockchain.check_incoming_payment(
                            payment_address, amount, 'USDT'
                        )
                    elif currency == 'TON':
                        is_paid, tx_hash = decentralized_payment_processor.blockchain.check_incoming_payment(
                            payment_address, amount, 'TON', payment_memo
                        )
                    else:
                        is_paid, tx_hash = False, None

                    if is_paid:
                        break

                    # Wait 5 seconds before second attempt
                    if attempt == 0:
                        await asyncio.sleep(5)
                        await callback.message.edit_text(
                            f"<b>{localization.get_text('checking_incoming_funds', language)}</b>\n\n{localization.get_text('rechecking_funds', language)}...",
                            parse_mode='HTML'
                        )

                except Exception as scan_error:
                    logger.warning(f"Error scanning wallet for deal {deal_code}, attempt {attempt + 1}: {scan_error}")
                    if attempt == 0:
                        await asyncio.sleep(5)

            if is_paid:
                # Payment found - update deal status
                db.update_deal_status(deal_code, 'funded', payment_confirmed_at=datetime.now().isoformat())

                # Notify both parties
                seller_id = deal.get('seller_id')
                await self._notify_payment_confirmed(deal_code, user_id, seller_id, tx_hash)

                # Update message
                await callback.message.edit_text(
                    "✅ <b>Funds found!</b>\n\nCheck completed successfully. Notifications were sent to both parties.",
                    parse_mode='HTML'
                )
                await callback.answer("✅ Funds found!", show_alert=True)

                # After the success message, return the user to the updated deal card
                try:
                    refreshed_deal = db.get_deal(deal_code) or deal
                    buyer = db.get_user(refreshed_deal.get('buyer_id')) or {}
                    seller = db.get_user(refreshed_deal.get('seller_id')) or {}

                    enhanced_deal = dict(refreshed_deal)
                    enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {refreshed_deal.get('buyer_id')}"
                    enhanced_deal['seller_name'] = (
                        seller.get('username')
                        or seller.get('first_name')
                        or (f"ID: {refreshed_deal.get('seller_id')}" if refreshed_deal.get('seller_id') else self._get_not_assigned_text(language))
                    )

                    deal_text = format_deal_info(enhanced_deal, language)
                    deal_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=localization.get_text('button_view_deal', language, code=deal_code) if localization else f"View {deal_code}",
                            callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}",
                        )],
                        [InlineKeyboardButton(
                            text=localization.get_text('back', language) if localization else "Back",
                            callback_data=f"{UNIFIED_PREFIXES['nav']}main",
                        )],
                    ])
                    await callback.message.reply(deal_text, reply_markup=deal_keyboard, parse_mode='HTML')
                except Exception as deal_view_error:
                    logger.warning(f"Failed to send updated deal card after payment for {deal_code}: {deal_view_error}")
            else:
                # Payment not found - add keyboard to check again
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=localization.get_text('button_check_again', language),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}payment_sent:{deal_code}"
                    )],
                    [InlineKeyboardButton(
                        text=localization.get_text('button_view_deal', language, code=deal_code),
                        callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                    )]
                ])

                await callback.message.edit_text(
                    f"<b>{localization.get_text('funds_not_found', language)}</b>\n\n"
                    f"{localization.get_text('payment_check_performed', language, count=2)}\n\n"
                    f"💡 <b>{localization.get_text('payment_tip_title', language)}:</b> {localization.get_text('payment_tip_ensure', language)}\n"
                    f"• {localization.get_text('payment_tip_exact_amount', language, amount=amount, currency=currency)}\n"
                    f"• {localization.get_text('payment_tip_correct_address', language)}\n"
                    f"• {localization.get_text('payment_tip_confirmed', language)}",
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                await callback.answer(localization.get_text('funds_not_found', language), show_alert=True)

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "payment_sent")

    async def handle_withdrawal_wallet_address(self, message: Message) -> None:
        """Handle seller entering wallet address for withdrawal."""
        if await self._block_banned_user(message):
            return
        try:
            user_id = message.from_user.id
            if user_id not in self.conversation_states:
                return

            state = self.conversation_states[user_id]
            if state.get('step') != 'awaiting_withdrawal_wallet':
                return

            deal_code = state.get('deal_code')
            language = state.get('language', 'en')

            if not deal_code:
                await message.reply("❌ Error: deal code not found", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            if not await self._zt_enforce_rate_limit(message, language):
                return

            try:
                self._zt_validate_deal(user_id, deal_code, required_role='seller', allowed_states=['funds_pending'])
            except (AuthorizationError, StateValidationError):
                await message.reply("Access denied", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            deal = db.get_deal(deal_code)
            if not deal:
                await message.reply("❌ Deal not found", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            # Check if user is the seller
            if deal.get('seller_id') != user_id:
                await message.reply("❌ Only the seller can withdraw funds", parse_mode='HTML')
                self._clear_user_state(user_id)
                return

            wallet_address = message.text.strip()
            
            # Basic address validation
            currency = deal.get('currency', 'USDT')
            if currency == 'USDT':
                if not wallet_address.startswith('T') or len(wallet_address) != 34:
                    await message.reply(
                        "❌ <b>Invalid USDT address</b>\n\nUSDT address must start with 'T' and be 34 characters long.",
                        parse_mode="HTML",
                    )
                    return
            elif currency == 'TON':
                if not (wallet_address.startswith('UQ') or wallet_address.startswith('EQ')) or len(wallet_address) < 48:
                    await message.reply(
                        "❌ <b>Invalid TON address</b>\n\nPlease check the TON wallet address.",
                        parse_mode="HTML",
                    )
                    return

            # Show processing
            processing_msg = await message.reply(
                "⏳ <b>Checking address and sending funds...</b>",
                parse_mode="HTML",
            )

            # Calculate seller amount (without commission)
            _, commission_amount, seller_amount = get_commission_breakdown(float(deal['amount']))

            try:
                # Verify address one more time before sending
                await processing_msg.edit_text(
                    f"⏳ <b>Checking address...</b>\n\n"
                    f"Address: <code>{wallet_address}</code>\n"
                    f"Amount: {seller_amount:.2f} {currency}",
                    parse_mode='HTML'
                )

                # Send funds via blockchain API using real private keys
                try:
                    # Use blockchain processor to send funds
                    from shared.decentralized_payments import decentralized_payment_processor
                    
                    success, tx_hash = decentralized_payment_processor.blockchain.send_funds(
                        to_address=wallet_address,
                        amount=seller_amount,
                        currency=currency,
                        memo=f"RELEASE-{deal_code}",
                    )
                    
                    if not success:
                        logger.warning(
                            f"❌ Failed to send funds via blockchain: {seller_amount} {currency} to {wallet_address}"
                        )
                        await processing_msg.edit_text(
                            "❌ <b>Failed to send funds</b>\n\n"
                            "Please try again in a minute. If it keeps failing, contact support.",
                            parse_mode='HTML'
                        )
                        return

                    logger.info(
                        f"✅ Funds sent successfully: {seller_amount} {currency} to {wallet_address}, TX: {tx_hash or 'unknown'}"
                    )
                except Exception as send_error:
                    logger.error(f"Error sending funds via blockchain: {send_error}")
                    await processing_msg.edit_text(
                        "❌ <b>Error sending funds</b>\n\nPlease try again later or contact support.",
                        parse_mode='HTML'
                    )
                    return

                # Update deal status to completed
                db.update_deal_status(
                    deal_code,
                    'completed',
                    commission_amount=commission_amount,
                    seller_amount=seller_amount,
                    completed_at=datetime.now().isoformat()
                )

                # Clear state
                self._clear_user_state(user_id)

                # Success message with transaction info
                if tx_hash:
                    explorer_url = f"https://tronscan.org/#/transaction/{tx_hash}" if currency == 'USDT' else f"https://tonscan.org/tx/{tx_hash}"
                    tx_info = f"\n🔗 <b>Transaction:</b> <code>{tx_hash}</code>\n📊 <a href='{explorer_url}'>View on explorer</a>"
                else:
                    tx_info = "\n✅ <b>Transaction:</b> Sent (hash pending)"
                 
                success_msg = (
                    f"✅ <b>Funds sent!</b>\n\n"
                    f"💵 <b>Amount (excluding fee):</b> {seller_amount:.2f} {currency}\n"
                    f"💸 <b>Platform fee:</b> {commission_amount:.2f} {currency}\n"
                    f"🏦 <b>Recipient address:</b> <code>{wallet_address}</code>{tx_info}\n\n"
                    f"⏳ <b>Transaction is being processed...</b>\n"
                    f"This usually takes a few minutes.\n\n"
                    f"🔒 <b>Deal completed!</b>"
                )
                await processing_msg.edit_text(success_msg, parse_mode='HTML')

                # Send completion notifications
                try:
                    from shared.deal_processor import automated_deal_processor
                    await automated_deal_processor._send_completion_notifications(deal_code)
                except Exception as notify_error:
                    logger.warning(f"Failed to send completion notifications: {notify_error}")

            except Exception as transfer_error:
                logger.error(f"Error transferring funds for deal {deal_code}: {transfer_error}")
                await processing_msg.edit_text(
                    "❌ <b>Error sending funds</b>\n\nPlease try again later or contact support.",
                    parse_mode='HTML'
                )

        except Exception as e:
            await self.error_handler.handle_error(message, e, "withdrawal_wallet")

    async def handle_withdraw_choice(self, callback: CallbackQuery) -> None:
        """Handle seller's withdrawal choice"""
        if await self._block_banned_user(callback):
            return
        try:
            user_id = callback.from_user.id
            data = callback.data.replace(f"{UNIFIED_PREFIXES['deal']}withdraw_", "")
            action, deal_code = data.split(":", 1)
            deal_code = deal_code.upper()
            language = self._get_user_language(user_id)

            if not await self._zt_enforce_rate_limit(callback, language):
                return

            try:
                self._zt_validate_deal(user_id, deal_code, required_role='seller', allowed_states=['funds_pending'])
            except (AuthorizationError, StateValidationError):
                await callback.answer("Access denied", show_alert=True)
                return

            deal = db.get_deal(deal_code)
            if not deal:
                await callback.answer("❌ Deal not found", show_alert=True)
                return

            # Check if user is the seller
            if deal.get('seller_id') != user_id:
                await callback.answer("❌ Only the seller can choose withdrawal method", show_alert=True)
                return

            # Check if deal is in funds_pending status
            if deal.get('status') != 'funds_pending':
                await callback.answer("❌ Deal is not ready for fund withdrawal", show_alert=True)
                return

            # Since balance option is removed, automatically proceed with wallet withdrawal
            await callback.answer("Proceed to wallet address input...", show_alert=True)
            
            # Request wallet address from seller
            self._set_user_state(user_id, {
                'step': 'awaiting_withdrawal_wallet',
                'deal_code': deal_code,
                'language': language
            })
            
            _, commission_amount, seller_amount = get_commission_breakdown(float(deal['amount']))
            
            await callback.message.edit_text(
                f"{localization.get_text('withdraw_to_wallet_message', language)}\n\n"
                f"{localization.get_text('withdraw_amount_line', language, amount=seller_amount, currency=deal['currency'])}\n"
                f"{localization.get_text('platform_fee_line', language, fee=commission_amount, currency=deal['currency'])}\n"
                f"{localization.get_text('final_amount_line', language, final_amount=seller_amount, currency=deal['currency'])}\n\n"
                f"{localization.get_text('enter_wallet_address', language)}\n\n"
                f"{localization.get_text('withdrawal_important', language)}\n"
                f"{localization.get_text('check_address_before_sending', language)}\n"
                f"{localization.get_text('address_must_match_currency', language, currency=deal['currency'])}\n"
                f"{localization.get_text('you_will_receive_exact', language, amount=seller_amount, currency=deal['currency'])}",
                parse_mode='HTML'
            )
            return

            # Refresh deal data
            deal = db.get_deal(deal_code)
            buyer = db.get_user(deal.get('buyer_id')) or {}
            seller = db.get_user(deal.get('seller_id')) or {}
            enhanced_deal = dict(deal)
            enhanced_deal['buyer_name'] = buyer.get('username') or buyer.get('first_name') or f"ID: {deal.get('buyer_id')}"
            enhanced_deal['seller_name'] = seller.get('username') or seller.get('first_name') or f"ID: {deal.get('seller_id')}"

            # Update message with completed deal info
            text = format_deal_info(enhanced_deal, language)
            buttons = [
                [InlineKeyboardButton(
                    text=localization.get_text('button_view_deal', language, code=deal_code) if localization else f"View {deal_code}",
                    callback_data=f"{UNIFIED_PREFIXES['deal']}view_deal:{deal_code}"
                )]
            ]

            # Back button - use breadcrumb system
            breadcrumb_trail = self.get_breadcrumb_trail(user_id)
            if len(breadcrumb_trail) > 1:
                # Go back to previous section
                previous_section = breadcrumb_trail[-2]  # Second to last is the previous page
                if previous_section == 'profile':
                    back_callback = f"{UNIFIED_PREFIXES['profile']}view"
                elif previous_section == 'my_deals':
                    back_callback = f"{UNIFIED_PREFIXES['deal']}my_deals"
                elif previous_section == 'main':
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"
                else:
                    back_callback = f"{UNIFIED_PREFIXES['nav']}main"  # Default fallback
            else:
                # No breadcrumb or only one entry, default to main
                back_callback = f"{UNIFIED_PREFIXES['nav']}main"

            buttons.append([InlineKeyboardButton(
                text=localization.get_text('back', language) if localization else 'Back',
                callback_data=back_callback
            )])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode='HTML')

            # Send completion notifications
            try:
                await automated_deal_processor._send_completion_notifications(deal_code)
            except Exception as notify_error:
                logger.warning(f"Failed to send completion notifications: {notify_error}")

            await callback.answer("✅ Deal completed!", show_alert=True)

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "withdraw_choice")

    # ===== ADMIN GENERAL MANAGEMENT METHODS =====

    async def handle_admin_users(self, callback: CallbackQuery) -> None:
        """Show admin users list with basic paging."""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            language = self._get_user_language(user_id)
            data = callback.data.replace(f"{UNIFIED_PREFIXES['admin']}users", "")
            page = 1
            if data.startswith(":"):
                try:
                    page = max(1, int(data.replace(":", "")))
                except Exception:
                    page = 1

            per_page = 10
            offset = (page - 1) * per_page
            users = db.get_all_users(limit=per_page, offset=offset)
            total_count = db.get_users_count()
            total_pages = max(1, (total_count + per_page - 1) // per_page)

            text = "<b>Users</b>\n\n"
            text += f"Total users: {total_count}\nPage: {page}/{total_pages}\n\n"

            if not users:
                text += "No users found."
            else:
                for user in users:
                    status_key = "admin_banned" if user.get('is_banned') else "admin_active"
                    status = localization.get_text(status_key, language) if localization else status_key
                    username = user.get('username') or "no_username"
                    text += f"{status} <code>{user['user_id']}</code> @{username}\n"

            text += "\nUse /admin user <id> for details."
            text += "\nUse /admin ban <id> or /admin unban <id>."

            rows = []
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="Previous",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}users:{page - 1}"
                ))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(
                    text="Next",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}users:{page + 1}"
                ))
            if nav_buttons:
                rows.append(nav_buttons)

            rows.append([
                InlineKeyboardButton(
                    text="Back to Admin",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_users")

    async def handle_admin_deals(self, callback: CallbackQuery) -> None:
        """Show admin deals list with basic paging."""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            data = callback.data.replace(f"{UNIFIED_PREFIXES['admin']}deals", "")
            page = 1
            if data.startswith(":"):
                try:
                    page = max(1, int(data.replace(":", "")))
                except Exception:
                    page = 1

            per_page = 10
            offset = (page - 1) * per_page
            deals = db.get_all_deals(limit=per_page, offset=offset)

            text = "<b>Deals</b>\n\n"
            if not deals:
                text += "No deals found."
            else:
                for deal in deals:
                    text += (
                        f"<code>{deal['deal_code']}</code> "
                        f"{deal['amount']} {deal['currency']} "
                        f"({deal.get('status', 'unknown')})\n"
                    )

            text += "\nUse /admin deal <code> for details."
            text += "\nUse /admin cancel <code> to cancel."
            text += "\nUse /admin confirm-payment <code> <amount> <currency> [tx_hash]."

            rows = []
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="Previous",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}deals:{page - 1}"
                ))
            if len(deals) == per_page:
                nav_buttons.append(InlineKeyboardButton(
                    text="Next",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}deals:{page + 1}"
                ))
            if nav_buttons:
                rows.append(nav_buttons)

            rows.append([
                InlineKeyboardButton(
                    text="Back to Admin",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_deals")

    async def handle_admin_settings(self, callback: CallbackQuery) -> None:
        """Show admin settings with update instructions."""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            settings = db.get_settings()
            text = "<b>System Settings</b>\n\n"
            if not settings:
                text += "Settings not found."
            else:
                text += f"commission_rate: {settings.get('commission_rate')}\n"
                text += f"min_deal_amount: {settings.get('min_deal_amount')}\n"
                text += f"max_deal_amount: {settings.get('max_deal_amount')}\n"
                text += f"auto_confirm_timeout: {settings.get('auto_confirm_timeout')}\n"
                text += f"currency_update_interval: {settings.get('currency_update_interval')}\n"

            text += "\nUpdate with /admin set <key> <value>."

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Back to Admin",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )]
            ])

            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_settings")

    async def handle_admin_platform_stats(self, callback: CallbackQuery) -> None:
        """Show platform statistics for admin."""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            system_stats = db.get_stats()
            text = "<b>Platform Statistics</b>\n\n"
            text += f"Total users: {system_stats.get('users_count')}\n"
            text += f"Total deals: {system_stats.get('deals_count')}\n"
            text += f"Active deals: {system_stats.get('active_deals')}\n"
            text += f"Completed deals: {system_stats.get('completed_deals')}\n"
            text += f"Total volume: {system_stats.get('total_volume')}\n"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Back to Admin",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )]
            ])

            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_platform_stats")

# ===== ADMIN DISPUTE MANAGEMENT METHODS =====

    async def handle_admin_disputes(self, callback: CallbackQuery) -> None:
        """Handle admin dispute management - show all disputes"""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            self._get_user_language(user_id)
            callback.data.replace(f"{UNIFIED_PREFIXES['admin']}", "")
            
            # Get disputes and their counts
            disputes = dispute_manager.get_all_disputes(limit=10)
            counts = dispute_manager.get_dispute_count_by_status()
            
            # Format header
            total = counts.get('open', 0) + counts.get('resolved', 0)
            text = f"🏛️ <b>DISPUTE MANAGEMENT</b>\n\n📊 <b>Overview:</b>\n"
            text += f"• Active disputes: {counts.get('open', 0)}\n"
            text += f"• Resolved: {counts.get('resolved', 0)}\n"
            text += f"• Total: {total}\n\n"
            
            if not disputes:
                text += "📝 <b>No disputes found</b>\n"
            else:
                text += "📋 <b>Recent Disputes:</b>\n\n"
                
                for i, dispute in enumerate(disputes, 1):
                    status_emoji = "🔴" if dispute['status'] == 'open' else "✅"
                    buyer_name = dispute.get('buyer_username') or dispute.get('buyer_name') or f"ID:{dispute['buyer_id']}"
                    seller_name = dispute.get('seller_username') or dispute.get('seller_name') or f"ID:{dispute['seller_id']}"
                    
                    # Truncate reason to fit
                    reason = dispute['reason'][:50] + "..." if len(dispute['reason']) > 50 else dispute['reason']
                    
                    text += f"{i}. {status_emoji} <b>#{dispute['dispute_id']}</b> - {dispute['deal_code']}\n"
                    text += f"   💰 {dispute['amount']} {dispute['currency']}\n"
                    text += f"   👥 {buyer_name} vs {seller_name}\n"
                    text += f"   📝 {reason}\n\n"
            
            # Create keyboard
            buttons = [
                [InlineKeyboardButton(
                    text="🔍 View All Disputes",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}list_all"
                )],
                [InlineKeyboardButton(
                    text="📋 Active Disputes",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}list_open"
                )],
                [InlineKeyboardButton(
                    text="📝 Add Response",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}response_start"
                )],
                [InlineKeyboardButton(
                    text="📊 Statistics",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}stats"
                )],
                [InlineKeyboardButton(
                    text="🔙 Back to Main",
                    callback_data=f"{UNIFIED_PREFIXES['nav']}main"
                )]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()
            
        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_disputes")

    async def handle_admin_list_disputes(self, callback: CallbackQuery, status: str = None) -> None:
        """Handle admin dispute listing with pagination"""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            self._get_user_language(user_id)
            data = callback.data.replace(f"{UNIFIED_PREFIXES['admin']}", "")
            
            # Parse pagination
            page = 1
            if data and ":" in data:
                try:
                    page = max(1, int(data.split(":")[1]))
                except Exception:
                    page = 1
            
            # Get disputes for the specified status
            limit = 5
            offset = (page - 1) * limit
            
            if status == "open":
                disputes = dispute_manager.get_all_disputes(status="open", limit=limit)
                title = "🔴 <b>ACTIVE DISPUTES</b>"
            else:
                disputes = dispute_manager.get_all_disputes(limit=limit)
                title = "📋 <b>ALL DISPUTES</b>"
            
            text = f"{title}\n\n"
            
            if not disputes:
                text += "📝 <b>No disputes found</b>\n"
            else:
                for i, dispute in enumerate(disputes, offset + 1):
                    status_emoji = "🔴" if dispute['status'] == 'open' else "✅"
                    buyer_name = dispute.get('buyer_username') or dispute.get('buyer_name') or f"ID:{dispute['buyer_id']}"
                    seller_name = dispute.get('seller_username') or dispute.get('seller_name') or f"ID:{dispute['seller_id']}"
                    
                    text += f"{i}. {status_emoji} <b>Dispute #{dispute['dispute_id']}</b>\n"
                    text += f"   📄 Deal: {dispute['deal_code']}\n"
                    text += f"   💰 Amount: {dispute['amount']} {dispute['currency']}\n"
                    text += f"   👤 Buyer: {buyer_name}\n"
                    text += f"   👤 Seller: {seller_name}\n"
                    text += f"   ⏰ Opened: {dispute['created_at'][:19]}\n"
                    text += f"   📝 Reason: {dispute['reason'][:100]}...\n\n"
            
            # Create keyboard with pagination
            buttons = []
            
            if page > 1:
                buttons.append(InlineKeyboardButton(
                    text="⬅️ Previous",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}list_{status or 'all'}:{page-1}"
                ))
            
            if len(disputes) == limit:
                buttons.append(InlineKeyboardButton(
                    text="Next ➡️",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}list_{status or 'all'}:{page+1}"
                ))
            
            if buttons:
                keyboard_rows = [buttons]
            else:
                keyboard_rows = []
            
            keyboard_rows.extend([
                [InlineKeyboardButton(
                    text="✏️ Respond to Dispute",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}response_start"
                )],
                [InlineKeyboardButton(
                    text="🔍 View by ID",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}view_single"
                )],
                [InlineKeyboardButton(
                    text="🏛️ Back to Admin",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()
            
        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_dispute_list")

    async def handle_admin_response_start(self, callback: CallbackQuery) -> None:
        """Start admin response flow - ask for dispute ID"""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            # Set up conversation state for admin response
            self._set_user_state(user_id, {
                'step': 'admin_awaiting_dispute_id',
                'language': 'en'  # Admin typically uses English
            })

            text = "✏️ <b>ADMIN DISPUTE RESPONSE</b>\n\n📝 <b>Please enter the Dispute ID to respond to:</b>\n\n📋 You can find the dispute ID in the notification or when viewing disputes.\n\n🔢 <b>Example:</b> 123, 456, etc."

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )]
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_response_start")

    async def handle_admin_response_message(self, message: Message) -> None:
        """Handle admin dispute ID input and response message"""
        try:
            user_id = message.from_user.id
            if user_id != ADMIN_ID:
                return

            state = self._get_user_state(user_id)
            if not state or state.get('step') not in ['admin_awaiting_dispute_id', 'admin_awaiting_response']:
                return

            if state['step'] == 'admin_awaiting_dispute_id':
                # Handle dispute ID input
                try:
                    dispute_id = int(message.text.strip())
                except ValueError:
                    await message.reply("❌ <b>Invalid Dispute ID</b>\n\nPlease enter a valid number.", parse_mode='HTML')
                    return

                # Verify dispute exists
                dispute = dispute_manager.get_dispute_by_id(dispute_id)
                if not dispute:
                    await message.reply(f"❌ <b>Dispute #{dispute_id} not found</b>\n\nPlease check the ID and try again.", parse_mode='HTML')
                    self._clear_user_state(user_id)
                    return

                # Move to response input
                self._update_user_state(user_id, {
                    'step': 'admin_awaiting_response',
                    'dispute_id': dispute_id,
                    'deal_code': dispute['deal_code']
                })

                # Show dispute info and ask for response
                buyer_name = dispute.get('buyer_username') or dispute.get('buyer_name') or f"ID:{dispute['buyer_id']}"
                seller_name = dispute.get('seller_username') or dispute.get('seller_name') or f"ID:{dispute['seller_id']}"

                text = f"✏️ <b>RESPOND TO DISPUTE #{dispute_id}</b>\n\n"
                text += f"📄 <b>Deal Code:</b> {dispute['deal_code']}\n"
                text += f"💰 <b>Amount:</b> {dispute['amount']} {dispute['currency']}\n"
                text += f"👤 <b>Buyer:</b> {buyer_name}\n"
                text += f"👤 <b>Seller:</b> {seller_name}\n"
                text += f"📝 <b>Problem:</b> {dispute['reason']}\n"
                text += f"⏰ <b>Created:</b> {dispute['created_at'][:19]}\n\n"
                text += "💬 <b>Enter your response:</b>\n\n"
                text += "• Be clear and specific\n"
                text += "• Include the deal code in your response\n"
                text += "• Provide actionable steps or resolution"

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="❌ Cancel",
                        callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                    )]
                ])

                await message.reply(text, reply_markup=keyboard, parse_mode='HTML')

            elif state['step'] == 'admin_awaiting_response':
                # Handle response text input
                response_text = message.text.strip()
                if len(response_text) < 10:
                    await message.reply("❌ <b>Response too short</b>\n\nPlease provide a more detailed response (at least 10 characters).", parse_mode='HTML')
                    return

                if len(response_text) > 1000:
                    await message.reply("❌ <b>Response too long</b>\n\nPlease keep your response under 1000 characters.", parse_mode='HTML')
                    return

                dispute_id = state['dispute_id']
                deal_code = state['deal_code']

                # Add response to dispute
                success = dispute_manager.add_dispute_response(dispute_id, user_id, response_text)
                if not success:
                    await message.reply("❌ <b>Error adding response</b>\n\nPlease try again.", parse_mode='HTML')
                    return

                # Update dispute status
                dispute_manager.update_dispute_status(dispute_id, 'resolved')

                # Update deal status
                db.update_deal_status(deal_code, 'dispute_resolved')

                # Send response to buyer
                try:
                    dispute = dispute_manager.get_dispute_by_id(dispute_id)
                    if dispute:
                        from html import escape as _html_escape

                        def _format_dispute_response(target_language: str) -> tuple[str, str]:
                            title = localization.get_text(
                                'dispute_response_title',
                                target_language,
                                deal_code=deal_code,
                            )
                            safe_response_text = _html_escape(response_text, quote=False)
                            message = (
                                f"{safe_response_text}\n\n"
                                f"🆔 <b>{localization.get_text('admin_dispute_id', target_language)}:</b> #{dispute_id}\n"
                                f"📄 <b>{localization.get_text('admin_deal_code', target_language)}:</b> {deal_code}\n\n"
                                f"ℹ️ {localization.get_text('dispute_resolved_note', target_language)}"
                            )
                            return title, message

                        buyer_language = db.get_user_language(dispute['buyer_id']) or 'en'
                        buyer_title, buyer_message = _format_dispute_response(buyer_language)
                        await notification_manager.create_notification(
                            user_id=dispute['buyer_id'],
                            notification_type="dispute_response",
                            title=buyer_title,
                            message=buyer_message,
                            action_url=f"/deal/{deal_code}"
                        )

                except Exception as e:
                    logger.error(f"Error notifying buyer {dispute['buyer_id']}: {e}")

                # Send response to seller
                try:
                    if dispute and dispute['seller_id']:
                        seller_language = db.get_user_language(dispute['seller_id']) or 'en'
                        seller_title, seller_message = _format_dispute_response(seller_language)
                        await notification_manager.create_notification(
                            user_id=dispute['seller_id'],
                            notification_type="dispute_response",
                            title=seller_title,
                            message=seller_message,
                            action_url=f"/deal/{deal_code}"
                        )

                except Exception as e:
                    logger.error(f"Error notifying seller {dispute['seller_id']}: {e}")

                # Clear state and show success
                self._clear_user_state(user_id)

                success_text = f"✅ <b>Response sent successfully!</b>\n\n🆔 <b>Dispute ID:</b> #{dispute_id}\n📄 <b>Deal Code:</b> {deal_code}\n\n💬 <b>Response sent to:</b>\n• Buyer\n• Seller (if applicable)\n\n📝 <b>Status:</b> Dispute marked as resolved\n📊 <b>Deal Status:</b> Updated to 'dispute_resolved'"

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🏛️ Back to Admin",
                        callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                    )]
                ])

                await message.reply(success_text, reply_markup=keyboard, parse_mode='HTML')

                logger.info(f"Admin {user_id} responded to dispute {dispute_id} for deal {deal_code}")

        except Exception as e:
            await self.error_handler.handle_error(message, e, "admin_response")
            self._clear_user_state(user_id)

    async def handle_admin_dispute_stats(self, callback: CallbackQuery) -> None:
        """Show admin dispute statistics"""
        try:
            user_id = callback.from_user.id
            if user_id != ADMIN_ID:
                await callback.answer("Access denied", show_alert=True)
                return

            counts = dispute_manager.get_dispute_count_by_status()
            total = sum(counts.values())

            # Get recent disputes for trends
            recent_disputes = dispute_manager.get_all_disputes(limit=5)

            text = "📊 <b>DISPUTE STATISTICS</b>\n\n"
            text += "📈 <b>Overview:</b>\n"
            text += f"• Total disputes: {total}\n"
            text += f"• Active (open): {counts.get('open', 0)}\n"
            text += f"• Resolved: {counts.get('resolved', 0)}\n\n"

            if total > 0:
                resolution_rate = (counts.get('resolved', 0) / total) * 100
                text += f"📊 <b>Resolution Rate:</b> {resolution_rate:.1f}%\n\n"

            text += "🕐 <b>Recent Activity:</b>\n"
            if recent_disputes:
                for dispute in recent_disputes:
                    status_emoji = "🔴" if dispute['status'] == 'open' else "✅"
                    text += f"{status_emoji} #{dispute['dispute_id']} - {dispute['deal_code']} ({dispute['status']})\n"
            else:
                text += "No recent disputes\n"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🏛️ Back to Admin",
                    callback_data=f"{UNIFIED_PREFIXES['admin']}disputes"
                )]
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            await self.error_handler.handle_error(callback, e, "admin_stats")


# Global handler instance
unified_handler = UnifiedBotHandler()


# ===== REGISTRATION FUNCTION =====

async def register_all_handlers(dispatcher: Dispatcher) -> None:
    """Register all unified handlers with the dispatcher."""
    try:
        # Register callback query handlers
        dispatcher.register_callback_query_handler(
            unified_handler.handle_create_deal_start,
            lambda c: c.data in (f"{UNIFIED_PREFIXES['deal']}create_deal_start", f"{UNIFIED_PREFIXES['deal']}action_create_deal")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_join_deal_start,
            lambda c: c.data == f"{UNIFIED_PREFIXES['deal']}join_deal_start"
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_currency_selected,
            lambda c: c.data in ('ud_currency_usdt', 'ud_currency_ton')
        )
        # New compact deal creation handlers
        dispatcher.register_callback_query_handler(
            lambda c: unified_handler._handle_compact_deal_action(c, 'skip_description'),
            lambda c: c.data == 'ud_skip_description'
        )
        dispatcher.register_callback_query_handler(
            lambda c: unified_handler._handle_compact_deal_action(c, 'back_to_currency'),
            lambda c: c.data == 'ud_back_to_currency'
        )
        dispatcher.register_callback_query_handler(
            lambda c: unified_handler._handle_compact_deal_action(c, 'back_to_amount'),
            lambda c: c.data == 'ud_back_to_amount'
        )
        dispatcher.register_callback_query_handler(
            lambda c: unified_handler._handle_compact_deal_action(c, 'back_to_description'),
            lambda c: c.data == 'ud_back_to_description'
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_create_confirm,
            lambda c: c.data == 'ud_create_confirm' or c.data == f"{UNIFIED_PREFIXES['deal']}create_confirm"
        )
        dispatcher.register_callback_query_handler(
            lambda c: unified_handler.handle_create_deal_start(c),
            lambda c: c.data == f"{UNIFIED_PREFIXES['deal']}skip_description"
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_cancel_deal_creation,
            lambda c: c.data == "un_main"
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_my_deals,
            lambda c: c.data == f"{UNIFIED_PREFIXES['deal']}my_deals" or (isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}my_deals_page:"))
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_view_deal,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}view_deal:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_cancel_deal,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}cancel_deal:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_confirm_cancel_deal,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}confirm_cancel_deal:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_open_dispute,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}open_dispute:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_confirm_open_dispute,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}confirm_open_dispute:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_confirm_delivery,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}confirm_delivery:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_confirm_receipt,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}confirm_receipt:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_confirm_join_deal,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}confirm_join:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_payment_method_selection,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}payment_method:")
        )

        dispatcher.register_callback_query_handler(
            unified_handler.handle_payment_sent,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}payment_sent:")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_withdraw_choice,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}withdraw_")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_share_deal,
            lambda c: isinstance(c.data, str) and c.data.startswith(f"{UNIFIED_PREFIXES['deal']}share_deal:")
        )

        # Support chat handlers
        dispatcher.register_callback_query_handler(
            unified_handler.handle_support_exit,
            lambda c: c.data == f"{UNIFIED_PREFIXES['support']}exit"
        )
        
        # Profile handlers
        dispatcher.register_callback_query_handler(
            unified_handler.handle_profile_view,
            lambda c: c.data == f"{UNIFIED_PREFIXES['profile']}view"
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_language_selection,
            lambda c: c.data == f"{UNIFIED_PREFIXES['start']}language"
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_language_change,
            lambda c: c.data.startswith(f"{UNIFIED_PREFIXES['start']}lang_")
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_login_website,
            lambda c: c.data == f"{UNIFIED_PREFIXES['start']}login_website"
        )
        dispatcher.register_callback_query_handler(
            unified_handler.handle_back_to_main,
            lambda c: c.data == f"{UNIFIED_PREFIXES['nav']}main"
        )

        # Register message handlers
        dispatcher.register_message_handler(unified_handler.handle_start, commands=['start'])
        dispatcher.register_message_handler(unified_handler.handle_help, commands=['help'])
        dispatcher.register_message_handler(unified_handler.handle_create_deal_command, commands=['create'])
        dispatcher.register_message_handler(unified_handler.handle_my_deals_command, commands=['my_deals'])
        dispatcher.register_message_handler(unified_handler.handle_profile_command, commands=['profile'])
        dispatcher.register_message_handler(unified_handler.handle_support_command, commands=['support'])

        # Register conversational message handlers
        dispatcher.register_message_handler(
            unified_handler.handle_amount_message,
            lambda m: m.from_user and m.from_user.id in unified_handler.conversation_states and
                       unified_handler.conversation_states[m.from_user.id].get('step') == 'awaiting_amount'
        )
        dispatcher.register_message_handler(
            unified_handler.handle_description_message,
            lambda m: m.from_user and m.from_user.id in unified_handler.conversation_states and
                       unified_handler.conversation_states[m.from_user.id].get('step') == 'awaiting_description'
        )
        dispatcher.register_message_handler(
            unified_handler.handle_join_code_message,
            lambda m: m.from_user and m.from_user.id in unified_handler.conversation_states and
                       unified_handler.conversation_states[m.from_user.id].get('step') == 'awaiting_join_code'
        )
        dispatcher.register_message_handler(
            unified_handler.handle_dispute_description_message,
            lambda m: m.from_user and m.from_user.id in unified_handler.conversation_states and
                       unified_handler.conversation_states[m.from_user.id].get('step') == 'awaiting_dispute_description'
        )

        # Support chat message handlers
        dispatcher.register_message_handler(
            unified_handler.handle_support_message,
            lambda m: m.from_user and m.from_user.id in unified_handler.conversation_states and
                       unified_handler.conversation_states[m.from_user.id].get('support_mode')
        )

        # Get all available languages for reply keyboard handlers
        available_languages = localization.get_available_languages().keys()

        # Register reply keyboard button handlers for all languages
        for lang in available_languages:
            # Create deal button
            dispatcher.register_message_handler(
                unified_handler.handle_create_deal_button,
                Text(equals=localization.get_text('create_deal', lang))
            )
            # Join deal button
            dispatcher.register_message_handler(
                unified_handler.handle_join_deal_button,
                Text(equals=localization.get_text('join_deal', lang))
            )
            # My deals button
            dispatcher.register_message_handler(
                unified_handler.handle_my_deals_button,
                Text(equals=localization.get_text('my_deals', lang))
            )
            # Profile button
            dispatcher.register_message_handler(
                unified_handler.handle_profile_button,
                Text(equals=localization.get_text('profile', lang))
            )

        # Additional fallback for English "Join deal" variations
        dispatcher.register_message_handler(
            unified_handler.handle_join_deal_button,
            Text(equals='Join deal')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_join_deal_button,
            Text(equals='Join Deal')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_join_deal_button,
            Text(equals='join deal')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_join_deal_button,
            Text(equals='join_deal')
        )

        # Additional fallback for English "My deals" variations
        dispatcher.register_message_handler(
            unified_handler.handle_my_deals_button,
            Text(equals='My deals')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_my_deals_button,
            Text(equals='My Deals')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_my_deals_button,
            Text(equals='my deals')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_my_deals_button,
            Text(equals='my_deals')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_my_deals_button,
            Text(equals='My Deal')
        )
        dispatcher.register_message_handler(
            unified_handler.handle_my_deals_button,
            Text(equals='my deal')
        )

        # Register handler for withdrawal wallet address input
        dispatcher.register_message_handler(
            unified_handler.handle_withdrawal_wallet_address,
            lambda m: m.text and not m.text.startswith('/') and
                       m.from_user and m.from_user.id in unified_handler.conversation_states and
                       unified_handler.conversation_states[m.from_user.id].get('step') == 'awaiting_withdrawal_wallet'
        )

        # Fallback handler for free text (no active conversation state)
        dispatcher.register_message_handler(
            unified_handler.handle_fallback_text_message,
            lambda m: m.text and not m.text.startswith('/') and
                       m.from_user and m.from_user.id not in unified_handler.conversation_states
        )

        # Register noop handler for non-actionable buttons
        dispatcher.register_callback_query_handler(
            lambda c: c.answer(),
            lambda c: c.data == 'noop'
        )

        # ADMIN fast-path for "deal_paid:{deal_code}" button:
        # Only ADMIN_ID is allowed; regular users are rejected inside handler.
        dispatcher.register_callback_query_handler(
            unified_handler.handle_admin_deal_paid_callback,
            lambda c: isinstance(c.data, str) and c.data.startswith("deal_paid:")
        )

        logger.info("✅ All unified handlers registered successfully")

    except Exception as e:
        logger.error(f"❌ Error registering unified handlers: {e}")
        raise

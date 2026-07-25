import logging
import hmac
import hashlib
import json
import uuid
import time
from typing import Dict, Any, Optional, Callable, Union, List, Awaitable
from functools import wraps
from enum import Enum

from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher.middlewares import BaseMiddleware

from shared.database import db
from shared.config import BOT_TOKEN
from shared.constants import ADMIN_ID

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for different operations."""
    PUBLIC = "public"           # No authentication required
    USER = "user"              # User authentication required
    DEAL_PARTICIPANT = "deal_participant"  # Must be deal participant
    DEAL_BUYER = "deal_buyer"   # Must be deal buyer
    DEAL_SELLER = "deal_seller"  # Must be deal seller
    ADMIN = "admin"            # Admin privileges required


class SecurityError(Exception):
    """Base security exception."""
    pass


class AuthenticationError(SecurityError):
    """Authentication failed."""
    pass


class AuthorizationError(SecurityError):
    """Authorization failed."""
    pass


class StateValidationError(SecurityError):
    """State validation failed."""
    pass


class CallbackValidationError(SecurityError):
    """Callback data validation failed."""
    pass


class SecurityManager:
    """Central security manager for all security operations."""
    
    def __init__(self):
        self.secret_key = BOT_TOKEN.encode('utf-8')
        self.state_timeout = 300  # 5 minutes
        self.max_callback_age = 300  # 5 minutes
        self.rate_limit_window = 60  # 1 minute
        self.max_requests_per_window = 10
        
        # Rate limiting storage
        self.rate_limits: Dict[str, List[float]] = {}
        
        # State storage
        self.user_states: Dict[int, Dict[str, Any]] = {}
        
        logger.info("🔒 Security Manager initialized")

    def generate_signed_callback_data(self, action: str, payload: Dict[str, Any], 
                                    user_id: int, expires_in: int = 3600) -> str:
        """
        Generate cryptographically signed callback data.
        
        Args:
            action: The action to perform
            payload: Additional payload data
            user_id: User ID for binding
            expires_in: Expiration time in seconds
            
        Returns:
            Signed callback data string
        """
        try:
            # Generate unique ID to prevent replay attacks
            nonce = str(uuid.uuid4())
            timestamp = int(time.time())
            expires_at = timestamp + expires_in
            
            # Create payload
            data = {
                'action': action,
                'payload': payload,
                'user_id': user_id,
                'nonce': nonce,
                'timestamp': timestamp,
                'expires_at': expires_at
            }
            
            # Serialize and sign
            data_str = json.dumps(data, sort_keys=True)
            signature = hmac.new(
                self.secret_key,
                data_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Return signed data
            return f"{data_str}:{signature}"
            
        except Exception as e:
            logger.error(f"Error generating signed callback data: {e}")
            raise SecurityError(f"Failed to generate signed callback data: {e}")

    def validate_signed_callback_data(self, signed_data: str, 
                                    expected_user_id: int) -> Dict[str, Any]:
        """
        Validate and parse signed callback data.
        
        Args:
            signed_data: Signed callback data string
            expected_user_id: Expected user ID
            
        Returns:
            Parsed payload data
            
        Raises:
            CallbackValidationError: If validation fails
        """
        try:
            if ':' not in signed_data:
                raise CallbackValidationError("Invalid callback data format")
            
            data_str, signature = signed_data.rsplit(':', 1)
            
            # Verify signature
            expected_signature = hmac.new(
                self.secret_key,
                data_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                raise CallbackValidationError("Invalid callback signature")
            
            # Parse data
            data = json.loads(data_str)
            
            # Validate timestamp and expiration
            current_time = int(time.time())
            if current_time > data['expires_at']:
                raise CallbackValidationError("Callback data has expired")
            
            if abs(current_time - data['timestamp']) > self.max_callback_age:
                raise CallbackValidationError("Callback data is too old")
            
            # Validate user binding
            if data['user_id'] != expected_user_id:
                raise CallbackValidationError("Callback data is not bound to this user")
            
            # Check for replay attack (nonce reuse)
            nonce = data['nonce']
            if self._is_nonce_used(nonce):
                raise CallbackValidationError("Potential replay attack detected")
            
            # Mark nonce as used
            self._mark_nonce_used(nonce)
            
            return data
            
        except json.JSONDecodeError:
            raise CallbackValidationError("Invalid callback data format")
        except Exception as e:
            raise CallbackValidationError(f"Callback validation failed: {e}")

    def _is_nonce_used(self, nonce: str) -> bool:
        """Check if nonce has been used (basic replay protection)."""
        # In production, this should use a persistent store with TTL
        return hasattr(self, '_used_nonces') and nonce in getattr(self, '_used_nonces', set())

    def _mark_nonce_used(self, nonce: str) -> None:
        """Mark nonce as used."""
        if not hasattr(self, '_used_nonces'):
            self._used_nonces = set()
        self._used_nonces.add(nonce)

    def check_rate_limit(self, user_id: int) -> bool:
        """
        Check if user has exceeded rate limits.
        
        Args:
            user_id: User ID to check
            
        Returns:
            True if within limits, False if exceeded
        """
        current_time = time.time()
        user_key = str(user_id)
        
        if user_key not in self.rate_limits:
            self.rate_limits[user_key] = []
        
        # Clean old entries
        self.rate_limits[user_key] = [
            t for t in self.rate_limits[user_key] 
            if current_time - t < self.rate_limit_window
        ]
        
        # Check limit
        if len(self.rate_limits[user_key]) >= self.max_requests_per_window:
            return False
        
        # Add current request
        self.rate_limits[user_key].append(current_time)
        return True

    def set_user_state(self, user_id: int, state_type: str, data: Dict[str, Any]) -> None:
        """
        Set user state for FSM validation.
        
        Args:
            user_id: User ID
            state_type: Type of state
            data: State data
        """
        self.user_states[user_id] = {
            'type': state_type,
            'data': data,
            'timestamp': time.time()
        }

    def get_user_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user state for FSM validation.
        
        Args:
            user_id: User ID
            
        Returns:
            State data if valid, None otherwise
        """
        if user_id not in self.user_states:
            return None
        
        state = self.user_states[user_id]
        
        # Check timeout
        if time.time() - state['timestamp'] > self.state_timeout:
            del self.user_states[user_id]
            return None
        
        return state

    def clear_user_state(self, user_id: int) -> None:
        """Clear user state."""
        if user_id in self.user_states:
            del self.user_states[user_id]

    def validate_deal_access(self, user_id: int, deal_code: str, 
                           required_role: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate user access to a deal.
        
        Args:
            user_id: User ID
            deal_code: Deal code
            required_role: Required role (buyer, seller, participant)
            
        Returns:
            Deal data if access granted
            
        Raises:
            AuthorizationError: If access denied
        """
        try:
            deal = db.get_deal(deal_code)
            if not deal:
                raise AuthorizationError(f"Deal {deal_code} not found")
            
            # Check if user is participant
            is_buyer = deal.get('buyer_id') == user_id
            is_seller = deal.get('seller_id') == user_id
            
            if not (is_buyer or is_seller):
                logger.warning(f"IDOR attempt: user {user_id} tried to access deal {deal_code}")
                raise AuthorizationError("Access denied - not a deal participant")
            
            # Check required role
            if required_role == 'buyer' and not is_buyer:
                raise AuthorizationError("Access denied - must be buyer")
            elif required_role == 'seller' and not is_seller:
                raise AuthorizationError("Access denied - must be seller")
            elif required_role == 'participant' and not (is_buyer or is_seller):
                raise AuthorizationError("Access denied - must be participant")
            
            return deal
            
        except AuthorizationError:
            raise
        except Exception as e:
            logger.error(f"Error validating deal access: {e}")
            raise AuthorizationError(f"Failed to validate deal access: {e}")

    def validate_deal_state(self, deal: Dict[str, Any], 
                          allowed_states: List[str]) -> None:
        """
        Validate deal state for operation.
        
        Args:
            deal: Deal data
            allowed_states: List of allowed states
            
        Raises:
            StateValidationError: If state not allowed
        """
        current_state = deal.get('status', '').lower()
        if current_state not in allowed_states:
            raise StateValidationError(
                f"Deal state '{current_state}' not allowed. "
                f"Expected one of: {', '.join(allowed_states)}"
            )

    def validate_user_balance(self, user_id: int, currency: str, 
                            amount: float) -> bool:
        """
        Validate user has sufficient balance.
        
        Args:
            user_id: User ID
            currency: Currency type
            amount: Required amount
            
        Returns:
            True if sufficient balance
        """
        try:
            user = db.get_user(user_id)
            if not user:
                return False
            
            balance_field = f"{currency.lower()}_balance"
            balance = getattr(user, balance_field, 0.0) or 0.0
            
            return balance >= amount
            
        except Exception as e:
            logger.error(f"Error validating user balance: {e}")
            return False


# Global security manager instance
security_manager = SecurityManager()


def require_authentication(security_level: SecurityLevel = SecurityLevel.USER):
    """
    Decorator to require user authentication.
    
    Args:
        security_level: Required security level
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Union[Message, CallbackQuery], *args, **kwargs):
            try:
                user_id = update.from_user.id
                
                # Check rate limiting
                if not security_manager.check_rate_limit(user_id):
                    logger.warning(f"Rate limit exceeded for user {user_id}")
                    if isinstance(update, CallbackQuery):
                        await update.answer("Rate limit exceeded. Please wait before trying again.", show_alert=True)
                    return
                
                # Basic user validation
                user = db.get_user(user_id)
                if not user:
                    if isinstance(update, CallbackQuery):
                        await update.answer("Please start the bot with /start", show_alert=True)
                    return
                
                # Admin check for admin operations
                if security_level == SecurityLevel.ADMIN and user_id != ADMIN_ID:
                    if isinstance(update, CallbackQuery):
                        await update.answer("Access denied - admin privileges required", show_alert=True)
                    return
                
                # Execute the function
                return await func(update, *args, **kwargs)
                
            except AuthenticationError as e:
                logger.warning(f"Authentication failed for user {user_id}: {e}")
                if isinstance(update, CallbackQuery):
                    await update.answer(str(e), show_alert=True)
            except Exception as e:
                logger.error(f"Security check failed: {e}")
                if isinstance(update, CallbackQuery):
                    await update.answer("Security validation failed", show_alert=True)
        
        return wrapper
    return decorator


def require_deal_access(required_role: Optional[str] = None):
    """
    Decorator to require deal access.
    
    Args:
        required_role: Required role (buyer, seller, participant)
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(callback: CallbackQuery, *args, **kwargs):
            try:
                user_id = callback.from_user.id
                
                # Extract deal code from callback data (this will be updated in the actual implementation)
                # For now, we'll assume the deal code is passed as a parameter
                deal_code = kwargs.get('deal_code')
                if not deal_code:
                    await callback.answer("Invalid callback data", show_alert=True)
                    return
                
                # Validate deal access
                deal = security_manager.validate_deal_access(user_id, deal_code, required_role)
                
                # Add deal to kwargs for the function
                kwargs['deal'] = deal
                
                # Execute the function
                return await func(callback, *args, **kwargs)
                
            except AuthorizationError as e:
                logger.warning(f"Deal access denied for user {user_id}: {e}")
                await callback.answer(str(e), show_alert=True)
            except Exception as e:
                logger.error(f"Deal access validation failed: {e}")
                await callback.answer("Deal access validation failed", show_alert=True)
        
        return wrapper
    return decorator


def require_deal_state(allowed_states: List[str]):
    """
    Decorator to require specific deal state.
    
    Args:
        allowed_states: List of allowed deal states
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(callback: CallbackQuery, *args, **kwargs):
            try:
                deal = kwargs.get('deal')
                if not deal:
                    await callback.answer("Deal data not available", show_alert=True)
                    return
                
                # Validate deal state
                security_manager.validate_deal_state(deal, allowed_states)
                
                # Execute the function
                return await func(callback, *args, **kwargs)
                
            except StateValidationError as e:
                logger.warning(f"Deal state validation failed: {e}")
                await callback.answer(str(e), show_alert=True)
            except Exception as e:
                logger.error(f"Deal state validation failed: {e}")
                await callback.answer("Deal state validation failed", show_alert=True)
        
        return wrapper
    return decorator


class SecureCallbackFactory:
    """Factory for creating secure callback data."""
    
    @staticmethod
    def create_deal_action(action: str, deal_code: str, user_id: int) -> str:
        """
        Create secure callback data for deal actions.
        
        Args:
            action: Action type
            deal_code: Deal code
            user_id: User ID
            
        Returns:
            Secure callback data string
        """
        payload = {
            'deal_code': deal_code,
            'action': action
        }
        
        return security_manager.generate_signed_callback_data(
            action=f"deal_{action}",
            payload=payload,
            user_id=user_id
        )
    
    @staticmethod
    def create_navigation_action(action: str, user_id: int, **kwargs) -> str:
        """
        Create secure callback data for navigation actions.
        
        Args:
            action: Action type
            user_id: User ID
            **kwargs: Additional payload data
            
        Returns:
            Secure callback data string
        """
        payload = {
            'action': action,
            **kwargs
        }
        
        return security_manager.generate_signed_callback_data(
            action=f"nav_{action}",
            payload=payload,
            user_id=user_id
        )


class SecureKeyboardFactory:
    """Factory for creating secure keyboards."""
    
    @staticmethod
    def create_deal_keyboard(deal_code: str, user_id: int, language: str = 'en') -> Any:
        """
        Create secure keyboard for deal actions.
        
        Args:
            deal_code: Deal code
            user_id: User ID
            language: User language
            
        Returns:
            InlineKeyboardMarkup with secure callbacks
        """
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        # Validate deal access first
        try:
            deal = security_manager.validate_deal_access(user_id, deal_code)
        except AuthorizationError:
            return InlineKeyboardMarkup()
        
        buttons = []
        
        # Add action buttons based on deal state and user role
        is_buyer = deal.get('buyer_id') == user_id
        is_seller = deal.get('seller_id') == user_id
        status = deal.get('status', '').lower()
        
        if status == 'active':
            if is_buyer:
                # Buyer actions
                buttons.append([
                    InlineKeyboardButton(
                        text="💳 Pay",
                        callback_data=SecureCallbackFactory.create_deal_action(
                            'payment_method', deal_code, user_id
                        )
                    )
                ])
            elif is_seller:
                # Seller actions (none for active state)
                pass
        
        elif status == 'funded':
            if is_seller:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ Confirm Delivery",
                        callback_data=SecureCallbackFactory.create_deal_action(
                            'confirm_delivery', deal_code, user_id
                        )
                    )
                ])
        
        elif status == 'delivery_pending':
            if is_seller:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ Confirm Delivery",
                        callback_data=SecureCallbackFactory.create_deal_action(
                            'confirm_delivery', deal_code, user_id
                        )
                    )
                ])
        
        elif status == 'receipt_pending':
            if is_buyer:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ Confirm Receipt",
                        callback_data=SecureCallbackFactory.create_deal_action(
                            'confirm_receipt', deal_code, user_id
                        )
                    )
                ])
        
        elif status == 'funds_pending':
            if is_seller:
                buttons.append([
                    InlineKeyboardButton(
                        text="💳 Withdraw",
                        callback_data=SecureCallbackFactory.create_deal_action(
                            'withdraw_wallet', deal_code, user_id
                        )
                    )
                ])
        
        # Add dispute button for active deals
        if status in ['active', 'funded', 'delivery_pending', 'receipt_pending']:
            buttons.append([
                InlineKeyboardButton(
                    text="🛡️ Open Dispute",
                    callback_data=SecureCallbackFactory.create_deal_action(
                        'open_dispute', deal_code, user_id
                    )
                )
            ])
        
        # Add back button
        buttons.append([
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data=SecureCallbackFactory.create_navigation_action(
                    'back_to_main', user_id
                )
            )
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)


class SecureMiddleware(BaseMiddleware):
    """Security middleware for all updates."""
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Process incoming updates with security checks."""
        try:
            user_id = event.from_user.id
            
            # Check rate limiting
            if not security_manager.check_rate_limit(user_id):
                logger.warning(f"Rate limit exceeded for user {user_id}")
                if isinstance(event, CallbackQuery):
                    await event.answer("Rate limit exceeded. Please wait before trying again.", show_alert=True)
                return
            
            # Basic user validation
            user = db.get_user(user_id)
            if not user:
                if isinstance(event, CallbackQuery):
                    await event.answer("Please start the bot with /start", show_alert=True)
                return
            
            # Process the handler
            return await handler(event, data)
            
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            if isinstance(event, CallbackQuery):
                await event.answer("Security validation failed", show_alert=True)
            return


# FSM State Management
class FSMState:
    """Finite State Machine state."""
    
    def __init__(self, state_type: str, data: Dict[str, Any]):
        self.state_type = state_type
        self.data = data
        self.timestamp = time.time()


class FSMManager:
    """Finite State Machine manager."""
    
    def __init__(self):
        self.states: Dict[int, FSMState] = {}
        self.state_transitions = {
            'deal_creation': ['select_currency', 'enter_amount', 'add_description', 'confirm'],
            'deal_join': ['awaiting_code', 'review_deal', 'confirm_join'],
            'payment': ['select_method', 'awaiting_payment', 'confirm_payment'],
            'dispute': ['awaiting_description', 'awaiting_resolution', 'resolved']
        }
    
    def set_state(self, user_id: int, state_type: str, data: Dict[str, Any]) -> None:
        """Set user state."""
        self.states[user_id] = FSMState(state_type, data)
    
    def get_state(self, user_id: int) -> Optional[FSMState]:
        """Get user state."""
        if user_id not in self.states:
            return None
        
        state = self.states[user_id]
        
        # Check timeout (10 minutes for FSM)
        if time.time() - state.timestamp > 600:
            del self.states[user_id]
            return None
        
        return state
    
    def validate_transition(self, current_state: str, next_state: str, 
                          state_type: str) -> bool:
        """Validate state transition."""
        if state_type not in self.state_transitions:
            return False
        
        states = self.state_transitions[state_type]
        current_index = states.index(current_state) if current_state in states else -1
        next_index = states.index(next_state) if next_state in states else -1
        
        return next_index == current_index + 1
    
    def clear_state(self, user_id: int) -> None:
        """Clear user state."""
        if user_id in self.states:
            del self.states[user_id]


# Global FSM manager instance
fsm_manager = FSMManager()

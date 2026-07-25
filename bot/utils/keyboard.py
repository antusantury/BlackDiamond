from typing import Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from shared.localization import localization
from shared.constants import SUPPORTED_CURRENCIES


def create_main_menu_keyboard(language: str = 'en') -> InlineKeyboardMarkup:
    """Create main menu keyboard with primary actions."""
    buttons = []

    # Primary actions
    buttons.append([InlineKeyboardButton(
        text=localization.get_text('create_deal', language),
        callback_data="action_create_deal"
    )])
    buttons.append([InlineKeyboardButton(
        text=localization.get_text('my_deals', language),
        callback_data="action_my_deals"
    )])
    buttons.append([InlineKeyboardButton(
        text=localization.get_text('profile', language),
        callback_data="action_profile"
    )])

    # Secondary actions
    buttons.append([InlineKeyboardButton(
        text=localization.get_text('language', language),
        callback_data="action_language"
    )])
    buttons.append([InlineKeyboardButton(
        text=localization.get_text('login_website', language),
        callback_data="action_login_website"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_navigation_keyboard(current_section: str, language: str = 'en',
                              context: Dict[str, Any] = None) -> InlineKeyboardMarkup:
    """Create context-aware navigation keyboard."""
    keyboard_buttons = []
    context = context or {}

    # Add section-specific buttons
    if current_section == "deals":
        keyboard_buttons.append([InlineKeyboardButton(
            text="📋 Active Deals",
            callback_data="nav_active_deals"
        )])
        keyboard_buttons.append([InlineKeyboardButton(
            text="✅ Completed",
            callback_data="nav_completed_deals"
        )])
        keyboard_buttons.append([InlineKeyboardButton(
            text="🔍 Search",
            callback_data="nav_search_deals"
        )])

    elif current_section == "profile":
        keyboard_buttons.append([InlineKeyboardButton(
            text="📊 Statistics",
            callback_data="nav_profile_stats"
        )])
        keyboard_buttons.append([InlineKeyboardButton(
            text="⚙️ Settings",
            callback_data="nav_settings"
        )])

    elif current_section == "create_deal":
        keyboard_buttons.append([InlineKeyboardButton(
            text=localization.get_text('button_set_amount', language),
            callback_data="create_set_amount"
        )])
        keyboard_buttons.append([InlineKeyboardButton(
            text=localization.get_text('button_add_description', language),
            callback_data="create_add_description"
        )])
        keyboard_buttons.append([InlineKeyboardButton(
            text=localization.get_text('button_create_now', language),
            callback_data="create_confirm"
        )])

    # Always add back button if not in main
    if current_section != "main":
        keyboard_buttons.append([InlineKeyboardButton(
            text=localization.get_text('back', language),
            callback_data="nav_main"
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_language_selection_keyboard(current_lang: str = 'en') -> InlineKeyboardMarkup:
    """Create language selection keyboard."""
    keyboard_buttons = []

    languages = localization.get_available_languages()

    for lang_code, lang_name in languages.items():
        # Add checkmark for current language
        display_name = f"✅ {lang_name}" if lang_code == current_lang else lang_name
        keyboard_buttons.append([InlineKeyboardButton(
            text=display_name,
            callback_data=f"lang_{lang_code}"
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_currency_selection_keyboard() -> InlineKeyboardMarkup:
    """Create currency selection keyboard for deals."""
    keyboard_buttons = []

    currency_labels = {
        'USDT': ("💵 USDT TRC20", "currency_usdt", "TRC20 network, instant confirmation"),
        'TON': ("💎 TON", "currency_ton", "The Open Network, fast network")
    }

    currencies = [currency_labels[c] for c in SUPPORTED_CURRENCIES if c in currency_labels]

    for display_name, callback_data, description in currencies:
        keyboard_buttons.append([InlineKeyboardButton(
            text=display_name,
            callback_data=callback_data
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


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
        [InlineKeyboardButton(text=confirm_text, callback_data=f"confirm_{action}"),
         InlineKeyboardButton(text=cancel_text, callback_data="cancel_action")]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_pagination_keyboard(current_page: int, total_pages: int,
                              prefix: str = "page") -> InlineKeyboardMarkup:
    """Create pagination keyboard for lists."""
    keyboard_buttons = []
    row = []

    # Previous button
    if current_page > 1:
        row.append(InlineKeyboardButton(
            text="⬅️ Previous",
            callback_data=f"{prefix}_{current_page - 1}"
        ))

    # Page indicator
    row.append(InlineKeyboardButton(
        text=f"{current_page}/{total_pages}",
        callback_data="noop"  # No operation
    ))

    # Next button
    if current_page < total_pages:
        row.append(InlineKeyboardButton(
            text="Next ➡️",
            callback_data=f"{prefix}_{current_page + 1}"
        ))
    
    if row:
        keyboard_buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_quick_actions_keyboard(language: str = 'en') -> InlineKeyboardMarkup:
    """Create quick actions keyboard for common tasks."""
    keyboard_buttons = []

    actions = [
        ("🚀 Create Deal", "quick_create_deal"),
        ("📋 My Deals", "quick_my_deals"),
        ("👤 Profile", "quick_profile"),
        ("💬 Support", "quick_support"),
        ("📊 Stats", "quick_stats")
    ]

    for display_name, callback_data in actions:
        keyboard_buttons.append([InlineKeyboardButton(
            text=display_name,
            callback_data=callback_data
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_admin_keyboard() -> InlineKeyboardMarkup:
    """Create admin panel keyboard."""
    keyboard_buttons = []

    admin_actions = [
        ("📊 Statistics", "admin_stats"),
        ("👥 Users", "admin_users"),
        ("🤝 Deals", "admin_deals"),
        ("⚙️ Settings", "admin_settings"),
        ("📝 Logs", "admin_logs")
    ]

    for display_name, callback_data in admin_actions:
        keyboard_buttons.append([InlineKeyboardButton(
            text=display_name,
            callback_data=callback_data
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_deal_actions_keyboard(deal_id: str, user_role: str,
                                deal_status: str) -> InlineKeyboardMarkup:
    """Create deal-specific actions keyboard."""
    keyboard_buttons = []

    # Common actions
    keyboard_buttons.append([InlineKeyboardButton(
        text="👁️ View Details",
        callback_data=f"deal_view_{deal_id}"
    )])

    # Role-specific actions
    if user_role == "buyer":
        if deal_status == "active":
            keyboard_buttons.append([InlineKeyboardButton(
                text="❌ Cancel Deal",
                callback_data=f"deal_cancel_{deal_id}"
            )])

    elif user_role == "seller":
        if deal_status == "pending":
            keyboard_buttons.append([InlineKeyboardButton(
                text="✅ Join Deal",
                callback_data=f"deal_join_{deal_id}"
            )])
        elif deal_status == "active":
            keyboard_buttons.append([InlineKeyboardButton(
                text="💰 Make Payment",
                callback_data=f"deal_pay_{deal_id}"
            )])

    # Moderator actions
    if user_role == "moderator":
        keyboard_buttons.append([InlineKeyboardButton(
            text="⚖️ Moderate",
            callback_data=f"deal_moderate_{deal_id}"
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def create_support_keyboard(language: str = 'en') -> InlineKeyboardMarkup:
    """Create support options keyboard."""
    keyboard_buttons = []

    support_options = [
        ("💳 Payment Issues", "support_payment"),
        ("🤝 Deal Problems", "support_deal"),
        ("🔧 Technical Help", "support_technical"),
        ("📋 General Questions", "support_general"),
        ("💬 Live Chat", "support_chat")
    ]

    for display_name, callback_data in support_options:
        keyboard_buttons.append([InlineKeyboardButton(
            text=display_name,
            callback_data=callback_data
        )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

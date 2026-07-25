import re
import html
from typing import Dict, Any, List
from shared.localization import localization
from shared.constants import BOT_NAME
from shared.commission import get_commission_rate, format_commission_percent


def format_welcome_message(language: str, user_name: str) -> str:
    """Format personalized welcome message using translation keys."""
    welcome_text = localization.get_text('welcome_message', language)
    if welcome_text:
        return welcome_text.format(user_name=user_name)
    else:
        # Fallback welcome message with modern design
        commission_percent = format_commission_percent(get_commission_rate())
        return f"""🤖 <b>Ласкаво просимо до {BOT_NAME}!</b>

👋 Привіт, {user_name}!

💼 <b>Ескроу-бот для безпечних угод</b>

🔒 <b>Як це працює:</b>
• Створюєте угоду та вказуєте суму
• Покупець сплачує на наш гаманець
• Продавець доставляє товар/послугу
• Покупець підтверджує отримання
• Продавець отримує кошти за вирахуванням комісії

💡 <b>Комісія:</b> {commission_percent}

🎯 <b>Оберіть дію:</b>"""


def format_profile_stats(user_id: int, stats: Dict[str, Any], language: str = 'en') -> str:
    """Format user profile statistics."""
    level_info = calculate_user_level(stats['completed_deals'], stats['success_rate'])

    templates = {
        'en': """👤 <b>Profile Statistics</b>

🆔 ID: <code>{user_id}</code>
🏅 Level: <b>{level_color} {level_name}</b>
📊 Deals: <b>{total_deals}</b> ({completed} ✅)
💰 Volume: <b>{total_volume:.2f} USDT</b>
🎯 Success Rate: <b>{success_rate:.1f}%</b>

{progress_bar}""",

        'ua': """👤 <b>Статистика профілю</b>

🆔 ID: <code>{user_id}</code>
🏅 Рівень: <b>{level_color} {level_name}</b>
📊 Угоди: <b>{total_deals}</b> ({completed} ✅)
💰 Обсяг: <b>{total_volume:.2f} USDT</b>
🎯 Успішність: <b>{success_rate:.1f}%</b>

{progress_bar}"""
    }

    template = templates.get(language, templates['en'])

    progress_bar = create_progress_bar(
        level_info['progress_percent'],
        length=15,
        filled_char='█',
        empty_char='░'
    )

    return template.format(
        user_id=user_id,
        level_color=level_info['color'],
        level_name=level_info['name'],
        total_deals=stats['total_deals'],
        completed=stats['completed_deals'],
        total_volume=stats['total_volume'],
        success_rate=stats['success_rate'],
        progress_bar=progress_bar
    )


def format_modern_profile(
    user: Dict[str, Any],
    user_deals: List[Dict[str, Any]],
    language: str = 'en',
    max_recent_deals: int = 5,
) -> str:
    """Format profile view used by the unified Telegram bot handler."""

    user_deals = user_deals or []

    user_id = user.get('user_id') or user.get('id') or "unknown"
    username = (user.get('username') or "").lstrip("@").strip()
    first_name = (user.get('first_name') or "").strip()

    if username:
        name_line = f"@{html.escape(username)}"
    elif first_name:
        name_line = html.escape(first_name)
    else:
        name_line = html.escape(str(user_id))

    language_names = localization.get_available_languages()
    language_display = language_names.get(language, language)

    title = localization.get_text('profile_title', language) or "Profile"
    recent_title = localization.get_text('profile_recent_deals', language) or "Recent Deals"

    header = (
        f"👤 <b>{html.escape(title)}</b>\n\n"
        f"📄 <b>{'User' if language == 'en' else 'Користувач'}</b>\n"
        f"├─ 📛 {name_line}\n"
        f"├─ 🌐 <b>{html.escape(localization.get_text('language', language) or 'Language')}:</b> {html.escape(language_display)}\n"
        f"└─ 🆔 <code>{html.escape(str(user_id))}</code>\n\n"
        f"📋 <b>{html.escape(recent_title)}</b>"
    )

    recent_deals = user_deals[:max_recent_deals]
    if not recent_deals:
        no_deals_text = "📭 <i>No deals yet</i>" if language == 'en' else "📭 <i>Ще немає угод</i>"
        return f"{header}\n\n{no_deals_text}"

    deal_lines = []
    for deal in recent_deals:
        deal_card_data = {
            'deal_code': deal.get('deal_code') or deal.get('code') or 'N/A',
            'amount': deal.get('amount', 0),
            'currency': deal.get('currency') or 'USDT',
            'status': deal.get('status') or 'unknown',
        }
        deal_lines.append(f"• {format_deal_card(deal_card_data, language)}")

    return f"{header}\n\n" + "\n".join(deal_lines)


def format_error_message(error_text: str, language: str = 'en') -> str:
    """Format error message with consistent styling."""
    templates = {
        'en': "❌ <b>Error:</b> {error_text}\n\nPlease try again or contact support.",

        'ua': "❌ <b>Помилка:</b> {error_text}\n\nСпробуйте ще раз або зверніться до підтримки."
    }

    template = templates.get(language, templates['en'])
    return template.format(error_text=error_text)


def format_success_message(message: str, language: str = 'en') -> str:
    """Format success message with consistent styling."""
    templates = {
        'en': "✅ <b>Success:</b> {message}",

        'ua': "✅ <b>Успішно:</b> {message}"
    }

    template = templates.get(language, templates['en'])
    return template.format(message=message)


def format_deal_timeline(deal: Dict[str, Any], language: str = 'en') -> str:
    """Format deal timeline progress with visual indicators.
    
    Shows:
    - 🔵 (blue) for completed stages
    - 🔵 (blue) for current/active stage
    - ⚪️ (white) for pending stages
    """
    
    status = deal.get('status', 'active')
    has_seller = bool(deal.get('seller_id'))
    has_payment = status in ['funded', 'delivery_pending', 'receipt_pending', 'funds_pending', 'completed']
    has_delivery = status in ['receipt_pending', 'funds_pending', 'completed']
    has_receipt = status in ['funds_pending', 'completed']
    is_completed = status == 'completed'
    
    # Get current stage based on status and progress
    current_stage = get_current_deal_stage(deal)
    
    # Localized step labels
    step_labels = {
        'en': {
            'deal_created': 'Deal Created',
            'seller_joined': 'Seller Joined',
            'waiting_seller': 'Waiting for Seller',
            'payment_received': 'Payment Received',
            'waiting_payment': 'Waiting for Payment',
            'payment': 'Payment',
            'delivery_confirmed': 'Delivery Confirmed',
            'waiting_delivery': 'Waiting for Delivery Confirmation',
            'delivery': 'Delivery',
            'receipt_confirmed': 'Receipt Confirmed',
            'waiting_receipt': 'Waiting for Receipt Confirmation',
            'receipt': 'Receipt Confirmation',
            'deal_completed': 'Deal Completed',
            'waiting_withdrawal': 'Waiting for Withdrawal',
            'withdrawal': 'Funds Withdrawal',
            'progress_title': 'Deal Progress:'
        },
        'ua': {
            'deal_created': 'Угода створена',
            'seller_joined': 'Продавець приєднався',
            'waiting_seller': 'Очікування продавця',
            'payment_received': 'Оплата отримана',
            'waiting_payment': 'Очікування оплати',
            'payment': 'Оплата',
            'delivery_confirmed': 'Доставка підтверджена',
            'waiting_delivery': 'Очікування підтвердження доставки',
            'delivery': 'Доставка',
            'receipt_confirmed': 'Отримання підтверджено',
            'waiting_receipt': 'Очікування підтвердження отримання',
            'receipt': 'Підтвердження отримання',
            'deal_completed': 'Угода завершена',
            'waiting_withdrawal': 'Очікування виведення коштів',
            'withdrawal': 'Виведення коштів',
            'progress_title': 'Прогрес угоди:'
        }
    }
    
    labels = step_labels.get(language, step_labels['en'])
    
    # Timeline steps - track which stages are completed
    steps = []
    
    # Localized "current" text
    current_labels = {
        'en': 'Current',

        'ua': 'Поточний'
    }
    current_text = current_labels.get(language, current_labels['en'])
    
    # Ensure consistent formatting (capitalized, not uppercase)
    if language == 'ua' and current_text == 'ПОТОЧНИЙ':
        current_text = 'Поточний'
    
    # Step 1: Deal Created
    # This stage is always completed once deal exists
    is_completed_stage = True
    is_active_stage = current_stage == 'seller_waiting' and not has_seller
    indicator = '🔵' if is_active_stage else '✅' if is_completed_stage else '⚪️'
    label = labels['deal_created']
    if is_active_stage:
        steps.append(f"{indicator} <b>{label}</b> ⬅️ {current_text}")
    else:
        steps.append(f"{indicator} <b>{label}</b>")
    
    # Step 2: Seller Joined
    # Completed when seller has joined
    is_completed_stage = has_seller
    is_active_stage = current_stage == 'payment_pending' and has_seller
    indicator = '🔵' if is_active_stage else '✅' if is_completed_stage else '⚪️'
    label = labels['seller_joined'] if has_seller else labels['waiting_seller']
    if is_active_stage:
        steps.append(f"{indicator} <b>{label}</b> ⬅️ {current_text}")
    else:
        steps.append(f"{indicator} <b>{label}</b>")
    
    # Step 3: Payment Received
    # Completed when payment is received (funded status or later)
    is_completed_stage = has_payment
    is_active_stage = current_stage == 'delivery_pending' and has_payment
    indicator = '🔵' if is_active_stage else '✅' if is_completed_stage else '⚪️'
    label = labels['payment_received'] if has_payment else (labels['waiting_payment'] if (has_seller and status == 'active') else labels['payment'])
    if is_active_stage:
        steps.append(f"{indicator} <b>{label}</b> ⬅️ {current_text}")
    else:
        steps.append(f"{indicator} <b>{label}</b>")
    
    # Step 4: Delivery Confirmed
    # Completed when delivery is confirmed
    is_completed_stage = has_delivery
    is_active_stage = current_stage == 'receipt_confirmed' and has_delivery
    indicator = '🔵' if is_active_stage else '✅' if is_completed_stage else '⚪️'
    label = labels['delivery_confirmed'] if has_delivery else (labels['waiting_delivery'] if status == 'delivery_pending' else labels['delivery'])
    if is_active_stage:
        steps.append(f"{indicator} <b>{label}</b> ⬅️ {current_text}")
    else:
        steps.append(f"{indicator} <b>{label}</b>")
    
    # Step 5: Receipt Confirmed
    # Completed when receipt is confirmed
    is_completed_stage = has_receipt
    is_active_stage = current_stage == 'withdrawal_pending' and has_receipt
    indicator = '🔵' if is_active_stage else '✅' if is_completed_stage else '⚪️'
    label = labels['receipt_confirmed'] if has_receipt else (labels['waiting_receipt'] if status == 'receipt_pending' else labels['receipt'])
    if is_active_stage:
        steps.append(f"{indicator} <b>{label}</b> ⬅️ {current_text}")
    else:
        steps.append(f"{indicator} <b>{label}</b>")
    
    # Step 6: Funds Withdrawal
    # Completed when deal is completed
    is_completed_stage = is_completed
    is_active_stage = current_stage == 'completed' and is_completed
    indicator = '🔵' if is_active_stage else '✅' if is_completed_stage else '⚪️'
    label = labels['deal_completed'] if is_completed else (labels['waiting_withdrawal'] if status == 'funds_pending' else labels['withdrawal'])
    if is_active_stage:
        steps.append(f"{indicator} <b>{label}</b> ⬅️ {current_text}")
    else:
        steps.append(f"{indicator} <b>{label}</b>")
    
    timeline_text = "\n".join(steps)
    
    return f"📊 <b>{labels['progress_title']}</b>\n\n{timeline_text}"


def format_deal_info(deal: Dict[str, Any], language: str = 'en') -> str:
    """Format deal information for display with enhanced visual appearance and timeline."""
    
    # Get status emoji and localized status text
    def get_status_visual(status: str, language: str) -> tuple:
        # Status emojis
        status_emojis = {
            'active': '🟢',
            'completed': '✅',
            'cancelled': '❌',
            'expired': '⏰',
            'pending': '🟡',
            'funded': '💰',
            'delivery_pending': '📦',
            'receipt_pending': '📥',
            'funds_pending': '💸',
            'dispute_open': '🔄'
        }

        emoji = status_emojis.get(status.lower(), '❓')

        # Get localized status text using translation keys
        status_key = f'status_{status.lower()}'
        try:
            status_text = localization.get_text(status_key, language)
        except:
            # Fallback to title case if translation fails
            status_text = status.title().replace('_', ' ')

        return emoji, status_text
    
    from html import escape as _html_escape

    def _escape_html(value) -> str:
        # Telegram messages use parse_mode='HTML' throughout the bot.
        return _html_escape(str(value), quote=False)

    # Get buyer/seller info (escape for Telegram HTML parse_mode)
    buyer_info = _escape_html(deal.get('buyer_name') or f"ID: {deal.get('buyer_id', 'N/A')}")
    
    # Localized "not assigned" text
    not_assigned = {
        'en': 'Not assigned',

        'ua': 'Не призначений'
    }
    seller_info = _escape_html(deal.get('seller_name') or deal.get('seller_id', not_assigned.get(language, not_assigned['en'])))
    
    # Format description with localized label (escape for Telegram HTML parse_mode)
    description = _escape_html(deal.get('description', ''))
    description_labels = {
        'en': 'Description',

        'ua': 'Опис'
    }
    desc_label = description_labels.get(language, description_labels['en'])
    desc_text = f"\n📄 <b>{desc_label}:</b>\n{description}" if description else ""
    
    # Localized field labels
    field_labels = {
        'en': {
            'deal_title': 'DEAL',
            'amount': 'Amount',
            'buyer': 'Buyer',
            'seller': 'Seller',
            'status': 'Status',
            'created': 'Created',
            'id': 'ID',
            'guaranteed': 'Guaranteed by Black Diamond'
        },

        'ua': {
            'deal_title': 'УГОДА',
            'amount': 'Сума',
            'buyer': 'Покупець',
            'seller': 'Продавець',
            'status': 'Статус',
            'created': 'Створено',
            'id': 'Код',
            'guaranteed': 'Гарантовано Black Diamond'
        }
    }
    
    labels = field_labels.get(language, field_labels['en'])
    status_emoji, status_text = get_status_visual(deal['status'], language)
    
    # Add timeline
    timeline = format_deal_timeline(deal, language)
    
    templates = {
        'en': f"""💎 <b>{labels['deal_title']} #{deal['deal_code']}</b> {status_emoji}

┌─ 💰 <b>{labels['amount']}:</b> <code>{deal['amount']} {deal['currency']}</code>
├─ 👤 <b>{labels['buyer']}:</b> {buyer_info}
├─ 🤝 <b>{labels['seller']}:</b> {seller_info}
├─ 📊 <b>{labels['status']}:</b> {status_text}
├─ 🕒 <b>{labels['created']}:</b> {deal.get('created_at', 'Unknown')[:10]}
└─ 🆔 <b>{labels['id']}:</b> <code>{deal['deal_code']}</code>{desc_text}

{timeline}

🔒 <b>{labels['guaranteed']}</b>""",

        'ua': f"""💎 <b>{labels['deal_title']} #{deal['deal_code']}</b> {status_emoji}

┌─ 💰 <b>{labels['amount']}:</b> <code>{deal['amount']} {deal['currency']}</code>
├─ 👤 <b>{labels['buyer']}:</b> {buyer_info}
├─ 🤝 <b>{labels['seller']}:</b> {seller_info}
├─ 📊 <b>{labels['status']}:</b> {status_text}
├─ 🕒 <b>{labels['created']}:</b> {deal.get('created_at', 'Unknown')[:10]}
└─ 🆔 <b>{labels['id']}:</b> <code>{deal['deal_code']}</code>{desc_text}

{timeline}

🔒 <b>{labels['guaranteed']}</b>"""
    }
    
    template = templates.get(language, templates['en'])
    return template


def format_deal_card(deal: Dict[str, Any], language: str = 'en', compact: bool = False) -> str:
    """Format deal as a compact card for lists."""

    def get_status_emoji(status: str) -> str:
        status_emojis = {
            'active': '🟢',
            'completed': '✅',
            'cancelled': '❌',
            'expired': '⏰',
            'pending': '🟡',
            'dispute_open': '🔄'
        }
        return status_emojis.get(status.lower(), '❓')

    status_emoji = get_status_emoji(deal['status'])

    # Get localized status text
    status_key = f'status_{deal.get("status", "unknown").lower()}'
    try:
        status_text = localization.get_text(status_key, language)
    except:
        status_text = deal.get('status', 'unknown').title()

    templates = {
        'en': f"{status_emoji} <code>{deal['deal_code']}</code> • {deal['amount']} {deal['currency']} • {status_text}",

        'ua': f"{status_emoji} <code>{deal['deal_code']}</code> • {deal['amount']} {deal['currency']} • {status_text}"
    }

    return templates.get(language, templates['en'])


def format_deal_summary(deals: List[Dict[str, Any]], language: str = 'en') -> str:
    """Format multiple deals as a summary list."""
    if not deals:
        templates = {
            'en': "📭 <b>No deals found</b>\n\nCreate a new deal or join an existing one!",

            'ua': "📭 <b>Угоди не знайдено</b>\n\nСтворіть нову угоду або приєднайтеся до існуючої!"
        }
        return templates.get(language, templates['en'])
    
    header = {
        'en': f"📋 <b>Your Deals ({len(deals)})</b>\n\n",

        'ua': f"📋 <b>Ваші угоди ({len(deals)})</b>\n\n"
    }
    
    deal_lines = []
    for i, deal in enumerate(deals, 1):
        deal_line = f"{i}. {format_deal_card(deal, language)}"
        deal_lines.append(deal_line)
    
    return header.get(language, header['en']) + "\n".join(deal_lines)



def create_progress_bar(percentage: float, length: int = 10,
                       filled_char: str = '█', empty_char: str = '░') -> str:
    """Create a visual progress bar."""
    if percentage < 0:
        percentage = 0
    if percentage > 100:
        percentage = 100

    filled = int(percentage / 100 * length)
    empty = length - filled

    return f"{filled_char * filled}{empty_char * empty}"


def format_currency_amount(amount: float, currency: str, decimals: int = 2) -> str:
    """Format currency amount with proper decimal places."""
    if currency in ['USDT', 'TON']:
        decimals = 2  # Stablecoins typically show 2 decimals
    elif currency == 'BTC':
        decimals = 8  # Bitcoin shows 8 decimals
    else:
        decimals = 2  # Default

    return f"{amount:.{decimals}f}"


def format_time_ago(timestamp: str, language: str = 'en') -> str:
    """Format timestamp as relative time (e.g., '2 hours ago')."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo)
        diff = now - dt

        # Calculate time difference
        seconds = diff.total_seconds()

        if seconds < 60:
            time_str = f"{int(seconds)} seconds ago"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            time_str = f"{days} day{'s' if days != 1 else ''} ago"
        else:
            time_str = dt.strftime("%Y-%m-%d")

        # Translate common terms
        translations = {
            'en': {
                'seconds ago': 'seconds ago',
                'minute ago': 'minute ago',
                'minutes ago': 'minutes ago',
                'hour ago': 'hour ago',
                'hours ago': 'hours ago',
                'day ago': 'day ago',
                'days ago': 'days ago'
            },

            'ua': {
                'seconds ago': 'секунд тому',
                'minute ago': 'хвилину тому',
                'minutes ago': 'хвилин тому',
                'hour ago': 'годину тому',
                'hours ago': 'годин тому',
                'day ago': 'день тому',
                'days ago': 'днів тому'
            }
        }

        lang_translations = translations.get(language, translations['en'])

        for eng, trans in lang_translations.items():
            time_str = time_str.replace(eng, trans)

        return time_str

    except Exception:
        return timestamp[:10]  # Fallback to date only


def sanitize_html(text: str) -> str:
    """Sanitize text for HTML display in Telegram."""
    if not text:
        return ""

    # Remove or escape HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Escape special characters that could be interpreted as HTML
    text = text.replace('&', '&')
    text = text.replace('<', '<')
    text = text.replace('>', '>')
    text = text.replace('"', '"')
    text = text.replace("'", '&#x27;')

    return text


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to specified length with suffix."""
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def format_number(num: float, decimals: int = 2) -> str:
    """Format number with thousand separators."""
    if decimals == 0:
        return f"{int(num):,}"
    else:
        return f"{num:,.{decimals}f}"


def calculate_user_level(total_deals: int, success_rate: float) -> Dict[str, Any]:
    """Calculate user level based on performance (duplicate for import)."""
    level_system = {
        'Novice': {'min_deals': 0, 'color': '🔰'},
        'Bronze': {'min_deals': 5, 'color': '🥉'},
        'Silver': {'min_deals': 10, 'color': '🥈'},
        'Gold': {'min_deals': 25, 'color': '🥇'},
        'Platinum': {'min_deals': 50, 'color': '🏆'},
        'Diamond': {'min_deals': 100, 'color': '💎'}
    }

    level_name = 'Novice'
    level_color = '🔰'

    for level, criteria in level_system.items():
        if total_deals >= criteria['min_deals']:
            level_name = level
            level_color = criteria['color']

    next_level_name = None
    progress_percent = 100

    levels = list(level_system.keys())
    if level_name in levels:
        current_index = levels.index(level_name)
        if current_index < len(levels) - 1:
            next_level_name = levels[current_index + 1]
            next_level_info = level_system[next_level_name]
            next_level_deals = next_level_info['min_deals']
            progress_percent = min(100, (total_deals / next_level_deals) * 100)

    return {
        'name': level_name,
        'color': level_color,
        'progress_percent': progress_percent,
        'next_level': next_level_name,
        'current_deals': total_deals,
        'deals_needed': level_system.get(next_level_name, {}).get('min_deals', 0) - total_deals
    }


def format_deal_creation_progress(current_step: int, language: str = 'en') -> str:
    """Format a compact 4-step progress indicator for the deal creation flow."""
    try:
        step = int(current_step or 1)
    except Exception:
        step = 1
    step = max(1, min(4, step))

    current_labels = {
        'en': 'Current',
        'ua': 'Поточний',
    }
    labels = {
        'en': [
            'Choose currency',
            'Enter amount',
            'Add description',
            'Confirm',
        ],
        'ua': [
            'Вибір валюти',
            'Введення суми',
            'Опис угоди',
            'Підтвердження',
        ],
    }
    steps = labels.get(language, labels['en'])
    current_text = current_labels.get(language, current_labels['en'])

    out = []
    for idx, title in enumerate(steps, start=1):
        if idx < step:
            out.append(f"✅ <b>{title}</b>")
        elif idx == step:
            out.append(f"🔵 <b>{title}</b> ⬅️ {current_text}")
        else:
            out.append(f"⚪️ <b>{title}</b>")
    return "\n".join(out)


def format_deal_creation_success(deal_code: str, amount: float, currency: str,
                                commission_amount: float, seller_amount: float,
                                language: str = 'en') -> str:
    """Format deal creation success message with enhanced visual appearance."""
    
    currency_display = "USDT (TRC20)" if currency == "USDT" else currency.upper()
    commission_rate = get_commission_rate()
    if amount:
        try:
            commission_rate = commission_amount / amount
        except Exception:
            pass
    commission_percent = format_commission_percent(commission_rate)
    
    # Generate consistent progress bar
    current_labels = {
        'en': 'Current',

        'ua': 'Поточний'
    }
    current_labels.get(language, current_labels['en'])
    
    progress_steps = [
        "✅ <b>Deal Created</b>",
        "🔵 <b>Waiting for Seller</b> ⬅️ Current",
        "⚪️ <b>Payment</b>",
        "⚪️ <b>Delivery</b>", 
        "⚪️ <b>Receipt Confirmation</b>",
        "⚪️ <b>Funds Withdrawal</b>"
    ]
    
    progress_text = "\n".join(progress_steps)
    
    templates = {
        'en': f"""🎉 <b>DEAL CREATED SUCCESSFULLY!</b> 🎉

┌─ 💎 <b>Deal Code:</b> <code>{deal_code}</code>
├─ 💰 <b>Amount:</b> <code>{amount:.2f} {currency_display}</code>
├─ 💸 <b>Commission ({commission_percent}):</b> <code>{commission_amount:.2f} {currency_display}</code>
├─ 💵 <b>Seller Receives:</b> <code>{seller_amount:.2f} {currency_display}</code>
└─ 🏷️ <b>Platform:</b> Black Diamond

📊 <b>Deal Progress:</b>

{progress_text}

📋 <b>What to do next:</b>
1️⃣ Share code {deal_code} with seller
2️⃣ Seller will join the deal
3️⃣ Seller will make payment
4️⃣ After payment seller will send goods
5️⃣ You confirm receipt
6️⃣ Seller gets funds

🔒 <b>Your deal is protected by Black Diamond guarantee!</b>

⚡ <b>Tip:</b> Keep this message safe - you'll need the deal code!""",

        'ua': f"""🎉 <b>УГОДА СТВОРЕНА УСПІШНО!</b> 🎉

┌─ 💎 <b>Код угоди:</b> <code>{deal_code}</code>
├─ 💰 <b>Сума:</b> <code>{amount:.2f} {currency_display}</code>
├─ 💸 <b>Комісія ({commission_percent}):</b> <code>{commission_amount:.2f} {currency_display}</code>
├─ 💵 <b>Отримує продавець:</b> <code>{seller_amount:.2f} {currency_display}</code>
└─ 🏷️ <b>Платформа:</b> Black Diamond

📊 <b>Прогрес угоди:</b>

{progress_text}

📋 <b>Що далі:</b>
1️⃣ Поділіться кодом {deal_code} з продавцем
2️⃣ Продавець приєднається до угоди
3️⃣ Продавець внесе оплату
4️⃣ Після оплати продавець відправить товар
5️⃣ Ви підтвердите отримання
6️⃣ Продавець отримає кошти

🔒 <b>Ваша угода захищена гарантією Black Diamond!</b>

⚡ <b>Порада:</b> Збережіть це повідомлення - код угоди знадобиться!"""
    }
    
    return templates.get(language, templates['en'])


def format_deal_join_success(deal_code: str, amount: float, currency: str,
                           language: str = 'en') -> str:
    """Format deal join success message with enhanced visual appearance."""
    
    currency_display = "USDT (TRC20)" if currency == "USDT" else currency.upper()
    
    # Generate consistent progress bar
    current_labels = {
        'en': 'Current',

        'ua': 'Поточний'
    }
    current_labels.get(language, current_labels['en'])
    
    progress_steps = [
        "✅ <b>Deal Created</b>",
        "✅ <b>Seller Joined</b>",
        "🔵 <b>Payment</b> ⬅️ Current",
        "⚪️ <b>Delivery</b>",
        "⚪️ <b>Receipt Confirmation</b>",
        "⚪️ <b>Funds Withdrawal</b>"
    ]
    
    progress_text = "\n".join(progress_steps)
    
    templates = {
        'en': f"""🎯 <b>SUCCESSFULLY JOINED THE DEAL!</b> 🎯

┌─ 🤝 <b>Deal Code:</b> <code>{deal_code}</code>
├─ 💰 <b>Amount:</b> <code>{amount:.2f} {currency_display}</code>
├─ 👥 <b>Your Role:</b> <b>SELLER</b>
└─ 🔒 <b>Status:</b> <span class="tg-spoiler">Waiting for payment</span>

📊 <b>Deal Progress:</b>

{progress_text}

📋 <b>What's Next:</b>
1️⃣ Wait for the buyer to make payment
2️⃣ Payment will be monitored automatically
3️⃣ You'll receive notification when payment is confirmed
4️⃣ Deliver your goods/services
5️⃣ Get paid automatically after confirmation

🔒 <b>Protected by Black Diamond escrow system!</b>

💡 <b>Note:</b> You'll be notified when the buyer makes payment.""",

        'ua': f"""🎯 <b>УСПІШНО ПРИЄДНАЛИСЯ ДО УГОДИ!</b> 🎯

┌─ 🤝 <b>Код угоди:</b> <code>{deal_code}</code>
├─ 💰 <b>Сума:</b> <code>{amount:.2f} {currency_display}</code>
├─ 👥 <b>Ваша роль:</b> <b>ПРОДАВЕЦЬ</b>
└─ 🔒 <b>Статус:</b> <span class="tg-spoiler">Очікування платежу</span>

📊 <b>Прогрес угоди:</b>

{progress_text}

📋 <b>Що далі:</b>
1️⃣ Дочекайтеся платежу від покупця
2️⃣ Платіж буде відстежуватися автоматично
3️⃣ Ви отримаєте сповіщення при підтвердженні платежу
4️⃣ Доставте ваш товар/послугу
5️⃣ Отримайте оплату автоматично після підтвердження

🔒 <b>Захищено системою ескроу Black Diamond!</b>

💡 <b>Примітка:</b> Ви отримаєте сповіщення, коли покупець внесе платіж."""
    }
    
    return templates.get(language, templates['en'])

def format_dynamic_deal_progress(deal: Dict[str, Any], language: str = 'en') -> str:
    """Format dynamic deal progress message with real-time stage indicators."""
    
    deal_code = deal['deal_code']
    amount = float(deal['amount'])
    currency = deal['currency']
    status = deal['status']
    has_seller = bool(deal.get('seller_id'))
    
    # Calculate amounts
    commission_rate = get_commission_rate()
    
    commission_amount = amount * commission_rate
    seller_amount = amount - commission_amount
    
    # Get current stage based on status and progress
    current_stage = get_current_deal_stage(deal)
    
    # Format currency display
    currency_display = "TON" if currency == "TON" else f"{currency} (TRC20)" if currency == "USDT" else currency.upper()
    
    # Stage definitions with localized labels
    stages = get_deal_stages(language)
    
    # Generate progress indicators
    progress_indicators = []
    for stage_key, stage_data in stages.items():
        is_completed = is_stage_completed(stage_key, current_stage, status, has_seller)
        is_active = is_stage_active(stage_key, current_stage, status, has_seller)
        
        # Localized "current" text
        current_labels = {
            'en': 'Current',

            'ua': 'Поточний'
        }
        current_text = current_labels.get(language, current_labels['en'])
        
        if is_completed:
            indicator = "✅"
            stage_text = f"<b>{stage_data}</b>"
        elif is_active:
            indicator = "🔵"
            stage_text = f"<b>{stage_data}</b> ⬅️ {current_text}"
        else:
            indicator = "⚪️"
            stage_text = stage_data
        
        progress_indicators.append(f"{indicator} {stage_text}")
    
    progress_text = "\n".join(progress_indicators)
    
    # Generate next steps based on current stage
    next_steps = get_next_steps(current_stage, deal, language)
    
    templates = {
        'en': f"""💎 <b>DEAL PROGRESS</b> - <code>{deal_code}</code>

┌─ 💎 <b>Deal Code:</b> <code>{deal_code}</code>
├─ 💰 <b>Amount:</b> <code>{amount:.2f} {currency_display}</code>
├─ 💸 <b>Commission:</b> <code>{commission_amount:.2f} {currency_display}</code>
└─ 💵 <b>Seller Receives:</b> <code>{seller_amount:.2f} {currency_display}</code>

📊 <b>Deal Progress:</b>

{progress_text}

📋 <b>Next Steps:</b>
{next_steps}

🔒 <b>Deal protected by Black Diamond guarantee!</b>""",

        'ua': f"""💎 <b>ПРОГРЕС УГОДИ</b> - <code>{deal_code}</code>

┌─ 💎 <b>Код угоди:</b> <code>{deal_code}</code>
├─ 💰 <b>Сума:</b> <code>{amount:.2f} {currency_display}</code>
├─ 💸 <b>Комісія:</b> <code>{commission_amount:.2f} {currency_display}</code>
└─ 💵 <b>Продавець отримає:</b> <code>{seller_amount:.2f} {currency_display}</code>

📊 <b>Прогрес угоди:</b>

{progress_text}

📋 <b>Що далі:</b>
{next_steps}

🔒 <b>Угода захищена гарантією Black Diamond!</b>"""
    }
    
    return templates.get(language, templates['en'])


def get_current_deal_stage(deal: Dict[str, Any]) -> str:
    """Determine current stage of deal based on status and progress."""
    status = deal['status']
    has_seller = bool(deal.get('seller_id'))
    
    stage_mapping = {
        'pending': 'seller_waiting',
        'active': 'payment_pending' if has_seller else 'seller_waiting',
        'funded': 'delivery_pending',
        'delivery_pending': 'delivery_confirmed',
        'receipt_pending': 'receipt_confirmed',
        'funds_pending': 'withdrawal_pending',
        'completed': 'completed',
        'cancelled': 'cancelled',
        'expired': 'expired'
    }
    
    return stage_mapping.get(status, 'seller_waiting')


def get_deal_stages(language: str = 'en') -> Dict[str, str]:
    """Get localized deal stage labels."""
    stages = {
        'en': {
            'deal_created': 'Deal Created',
            'seller_waiting': 'Waiting for Seller',
            'payment_pending': 'Payment',
            'delivery_pending': 'Delivery',
            'receipt_confirmed': 'Receipt Confirmation',
            'withdrawal_pending': 'Funds Withdrawal',
            'completed': 'Deal Completed',
            'cancelled': 'Deal Cancelled',
            'expired': 'Deal Expired'
        },

        'ua': {
            'deal_created': 'Угода створена',
            'seller_waiting': 'Очікування продавця',
            'payment_pending': 'Оплата',
            'delivery_pending': 'Доставка',
            'receipt_confirmed': 'Підтвердження отримання',
            'withdrawal_pending': 'Виведення коштів',
            'completed': 'Угода завершена',
            'cancelled': 'Угода скасована',
            'expired': 'Угода застаріла'
        }
    }
    
    return stages.get(language, stages['en'])


def is_stage_completed(stage_key: str, current_stage: str, status: str, has_seller: bool) -> bool:
    """Check if a stage is completed based on current progress."""
    stage_order = [
        'deal_created',
        'seller_waiting', 
        'payment_pending',
        'delivery_pending',
        'receipt_confirmed',
        'withdrawal_pending',
        'completed'
    ]
    
    try:
        current_index = stage_order.index(current_stage)
        stage_index = stage_order.index(stage_key)
        return stage_index <= current_index
    except ValueError:
        return False


def is_stage_active(stage_key: str, current_stage: str, status: str, has_seller: bool) -> bool:
    """Check if a stage is currently active."""
    return stage_key == current_stage


def get_next_steps(current_stage: str, deal: Dict[str, Any], language: str = 'en') -> str:
    """Generate next steps text based on current stage."""
    has_seller = bool(deal.get('seller_id'))
    
    steps_mapping = {
        'en': {
            'deal_created': "1️⃣ Share code with seller\n2️⃣ Wait for seller to join",
            'seller_waiting': "1️⃣ Wait for seller to join the deal\n2️⃣ Seller will receive payment instructions" if not has_seller else "1️⃣ Buyer will make payment\n2️⃣ Payment will be monitored automatically",
            'payment_pending': "1️⃣ Buyer makes payment to escrow\n2️⃣ System monitors payment automatically\n3️⃣ Seller delivers goods after payment",
            'delivery_pending': "1️⃣ Seller delivers goods/services\n2️⃣ Wait for buyer confirmation\n3️⃣ Funds released after confirmation",
            'receipt_confirmed': "1️⃣ Funds released to seller\n2️⃣ Deal completed successfully",
            'withdrawal_pending': "1️⃣ Seller withdraws funds\n2️⃣ Deal completed",
            'completed': "🎉 Deal completed successfully!",
            'cancelled': "❌ Deal was cancelled",
            'expired': "⏰ Deal has expired"
        },

        'ua': {
            'deal_created': "1️⃣ Поділіться кодом з продавцем\n2️⃣ Дочекайтеся приєднання продавця",
            'seller_waiting': "1️⃣ Очікуйте приєднання продавця\n2️⃣ Продавець отримає інструкції з оплати" if not has_seller else "1️⃣ Покупець внесе оплату\n2️⃣ Оплата буде відстежуватися автоматично",
            'payment_pending': "1️⃣ Покупець внесе оплату на ескроу\n2️⃣ Система відстежує оплату автоматично\n3️⃣ Продавець доставить товар після оплати",
            'delivery_pending': "1️⃣ Продавець доставить товар/послугу\n2️⃣ Очікування підтвердження від покупця\n3️⃣ Кошти виплачуються після підтвердження",
            'receipt_confirmed': "1️⃣ Кошти виплачуються продавцю\n2️⃣ Угода успішно завершена",
            'withdrawal_pending': "1️⃣ Продавець виведе кошти\n2️⃣ Угода завершена",
            'completed': "🎉 Угода успішно завершена!",
            'cancelled': "❌ Угода була скасована",
            'expired': "⏰ Угода застаріла"
        }
    }
    
    steps = steps_mapping.get(language, steps_mapping['en'])
    default_steps = list(steps.values())[0] if steps else "Steps not available"
    return steps.get(current_stage, default_steps)


def format_deal_creation_success_dynamic(deal_code: str, amount: float, currency: str,
                                       commission_amount: float, seller_amount: float,
                                       language: str = 'en') -> str:
    """Format deal creation success message with dynamic progress indicators."""
    
    currency_display = "TON" if currency == "TON" else f"{currency} (TRC20)" if currency == "USDT" else currency.upper()
    
    # Generate consistent progress bar
    current_labels = {
        'en': 'Current',

        'ua': 'Поточний'
    }
    current_labels.get(language, current_labels['en'])
    
    progress_steps = [
        "✅ <b>Deal Created</b>",
        "🔵 <b>Waiting for Seller</b> ⬅️ Current",
        "⚪️ <b>Payment</b>",
        "⚪️ <b>Delivery</b>",
        "⚪️ <b>Receipt Confirmation</b>",
        "⚪️ <b>Funds Withdrawal</b>"
    ]
    
    progress_text = "\n".join(progress_steps)
    
    templates = {
        'en': f"""🎉 <b>DEAL CREATED SUCCESSFULLY!</b> 🎉

┌─ 💎 <b>Deal Code:</b> <code>{deal_code}</code>
├─ 💰 <b>Amount:</b> <code>{amount:.2f} {currency_display}</code>
├─ 💸 <b>Commission:</b> <code>{commission_amount:.2f} {currency_display}</code>
└─ 💵 <b>Seller Receives:</b> <code>{seller_amount:.2f} {currency_display}</code>

📊 <b>Deal Progress:</b>

{progress_text}

📋 <b>What to do next:</b>
1️⃣ Share code {deal_code} with seller
2️⃣ Seller will join the deal
3️⃣ Seller will make payment
4️⃣ After payment seller will send goods
5️⃣ You confirm receipt
6️⃣ Seller gets funds

🔒 <b>Deal protected by Black Diamond guarantee!</b>""",

        'ua': f"""🎉 <b>УГОДА СТВОРЕНА УСПІШНО!</b> 🎉

┌─ 💎 <b>Код угоди:</b> <code>{deal_code}</code>
├─ 💰 <b>Сума:</b> <code>{amount:.2f} {currency_display}</code>
├─ 💸 <b>Комісія:</b> <code>{commission_amount:.2f} {currency_display}</code>
└─ 💵 <b>Продавець отримає:</b> <code>{seller_amount:.2f} {currency_display}</code>

📊 <b>Прогрес угоди:</b>

{progress_text}

📋 <b>Що далі:</b>
1️⃣ Поділіться кодом {deal_code} з продавцем
2️⃣ Продавець приєднається до угоди
3️⃣ Продавець внесе оплату
4️⃣ Після оплати продавець відправить товар
5️⃣ Ви підтвердите отримання
6️⃣ Продавець отримає кошти

🔒 <b>Угода захищена гарантією Black Diamond!</b>"""
    }
    
    return templates.get(language, templates['en'])


def get_deal_progress_percentage(deal: Dict[str, Any]) -> float:
    """Calculate deal progress percentage (0-100)."""
    current_stage = get_current_deal_stage(deal)
    deal['status']
    
    stage_percentages = {
        'deal_created': 10,
        'seller_waiting': 25,
        'payment_pending': 40,
        'delivery_pending': 60,
        'receipt_confirmed': 80,
        'withdrawal_pending': 95,
        'completed': 100,
        'cancelled': 0,
        'expired': 0
    }
    
    return stage_percentages.get(current_stage, 0)


def update_existing_message_with_progress(existing_message: str, deal: Dict[str, Any], language: str = 'en') -> str:
    """Update an existing message with new progress indicators."""
    deal_code = deal['deal_code']
    current_stage = get_current_deal_stage(deal)
    
    # Extract deal code from existing message
    if deal_code in existing_message:
        # Generate new progress indicators
        stages = get_deal_stages(language)
        progress_indicators = []
        
        for stage_key, stage_data in stages.items():
            is_completed = is_stage_completed(stage_key, current_stage, deal['status'], bool(deal.get('seller_id')))
            is_active = is_stage_active(stage_key, current_stage, deal['status'], bool(deal.get('seller_id')))
            
            # Localized "current" text
            current_labels = {
                'en': 'Current',

                'ua': 'Поточний'
            }
            current_text = current_labels.get(language, current_labels['en'])
            
            if is_completed:
                indicator = "✅"
                stage_text = f"<b>{stage_data}</b>"
            elif is_active:
                indicator = "🔵"
                stage_text = f"<b>{stage_data}</b> ⬅️ {current_text}"
            else:
                indicator = "⚪️"
                stage_text = stage_data
            
            progress_indicators.append(f"{indicator} {stage_text}")
        
        progress_text = "\n".join(progress_indicators)
        
        # Find and replace the progress section
        import re
        pattern = r"📊 .*?:\s*\n(.*?)(?=\n📋|\n🔒|$)"
        match = re.search(pattern, existing_message, re.DOTALL)
        
        if match:
            # Replace progress section
            new_progress_section = f"📊 <b>{'Progress' if language == 'en' else 'Прогресс' 'Прогрес'}:\n\n{progress_text}"
            updated_message = existing_message.replace(match.group(0), new_progress_section)
            
            # Update next steps based on current stage
            next_steps = get_next_steps(current_stage, deal, language)
            next_steps_pattern = r"📋 .*?:\s*\n(.*?)(?=\n🔒|$)"
            next_steps_match = re.search(next_steps_pattern, updated_message, re.DOTALL)
            
            if next_steps_match:
                new_next_steps_section = f"📋 <b>{'What next' if language == 'en' else 'Что дальше' 'Що далі'}:\n{next_steps}"
                updated_message = updated_message.replace(next_steps_match.group(0), new_next_steps_section)
            
            return updated_message
    
    return existing_message  # Return original if no update needed


def create_progress_update_notification(deal: Dict[str, Any], user_role: str, language: str = 'en') -> str:
    """Create a notification message for progress updates."""
    deal_code = deal['deal_code']
    current_stage = get_current_deal_stage(deal)
    progress_percentage = get_deal_progress_percentage(deal)
    
    stage_labels = get_deal_stages(language)
    current_stage_label = stage_labels.get(current_stage, current_stage)
    
    user_role_text = {
        'en': {'buyer': 'buyer', 'seller': 'seller'},

        'ua': {
            'profile_title': '👤 <b>МІЙ ПРОФІЛЬ</b>',
            'user_info': '📄 <b>Інформація про користувача</b>',
            'recent_deals': '📋 <b>Останні угоди</b>',
            'no_deals': '📭 <i>Поки що немає угод</i>',
            'username_label': 'Username',
            'language_label': 'Мова'
        }
    }
    
    text = templates.get(language, templates['en'])
    
    # Build profile header
    profile_text = f"""{text['profile_title']}

{text['user_info']}
├─ 📛 @{username}
├─ 🌐 {language_display}
└─ 🔢 <code>{user_id}</code>

{text['recent_deals']}"""
    
    # Add recent deals
    if recent_deals:
        deal_cards = []
        for deal in recent_deals:
            deal_card_data = {
                'deal_code': deal.get('code') or deal.get('deal_code', 'N/A'),
                'amount': deal.get('amount', 0),
                'currency': deal.get('currency', 'USDT'),
                'status': deal.get('status', 'unknown')
            }
            deal_card = format_deal_card(deal_card_data, language)
            deal_cards.append(f"• {deal_card}")
        
        profile_text += "\n" + "\n".join(deal_cards)
    else:
        profile_text += f"\n{text['no_deals']}"
    
    return profile_text

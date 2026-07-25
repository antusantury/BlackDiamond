#!/usr/bin/env python3
from flask import Blueprint, jsonify, request, session, flash, redirect, url_for, render_template
import logging

logger = logging.getLogger(__name__)

# Import shared modules
try:
    from shared.database import db
    from shared.localization import localization
    from shared.notifications import notification_manager
    from shared.url_utils import get_deal_url
    logger.info("Join deal routes module loaded successfully")
except ImportError as e:
    logger.warning(f"Join deal routes module: {e}")
    
    # Fallback for diagnostics
    class MockDB:
        def get_deal(self, deal_code): return None
        def join_deal(self, *args): return True
        def update_deal_status(self, *args): return True
        def get_user(self, user_id): return {'user_id': user_id, 'first_name': 'Test', 'username': 'test'}
        def get_user_language(self, user_id): return 'en'
    
    class MockLocalization:
        def get_text(self, key, language='en', **kwargs): return f"[{key}]"
    
    class MockNotificationManager:
        def create_notification(self, *args, **kwargs): pass
    
    class MockUrlUtils:
        def get_deal_url(self, deal_code): return f"/deal/{deal_code}"
    
    db = MockDB()
    localization = MockLocalization()
    notification_manager = MockNotificationManager()
    get_deal_url = MockUrlUtils().get_deal_url

# Create blueprint
join_deal_bp = Blueprint('join_deal', __name__)


def _notify_buyer_seller_joined(deal: dict, deal_code_upper: str, seller_id: int) -> dict:
    """Build buyer notification payload when a seller joins."""
    from shared.commission import get_commission_breakdown
    from shared.config import TON_SYSTEM_ADDRESS, USDT_SYSTEM_ADDRESS
    from shared.decentralized_payments import decentralized_payment_processor

    buyer_id = deal['buyer_id']
    buyer_language = db.get_user_language(buyer_id)

    currency = str(deal.get('currency') or '').upper()
    amount = float(deal.get('amount') or 0)

    payment = None
    try:
        payment = db.get_decentralized_payment_by_deal_code(deal_code_upper)
    except Exception:
        payment = None

    if not payment:
        payment = decentralized_payment_processor.create_payment(
            deal_code=deal_code_upper,
            amount=amount,
            currency=currency,
            buyer_address=f"buyer_{buyer_id}",
            seller_address=f"seller_{seller_id}",
        )
        if not payment:
            logger.warning(
                f"Failed to create payment record for deal {deal_code_upper}; sending notification without escrow details"
            )

    escrow_address = None
    payment_memo = None
    if payment:
        escrow_address = payment.get('escrow_address') or payment.get('address')
        payment_memo = payment.get('payment_memo') or payment.get('memo')

    if not escrow_address:
        if currency == "TON":
            escrow_address = TON_SYSTEM_ADDRESS
        elif currency == "USDT":
            escrow_address = USDT_SYSTEM_ADDRESS

    if not escrow_address:
        logger.warning(f"Escrow address not configured for currency {currency} (deal {deal_code_upper})")

    rate, commission_amount, seller_amount = get_commission_breakdown(amount)
    if payment:
        try:
            commission_amount = float(payment.get('commission_amount', commission_amount))
            seller_amount = float(payment.get('seller_amount', seller_amount))
        except Exception:
            pass

    def _fmt_amount(value: float) -> str:
        if currency == "TON":
            return f"{value:.4f}"
        if currency == "USDT":
            return f"{value:.2f}"
        return f"{value:.4f}".rstrip("0").rstrip(".")

    currency_display = "USDT (TRC20)" if currency == "USDT" else (currency or deal.get('currency') or '').upper()
    formatted_address = (
        f"<code>{escrow_address}</code>\n{localization.get_text('click_to_copy', buyer_language)}"
        if escrow_address else
        localization.get_text('not_specified', buyer_language)
    )

    buyer_info = (
        f"{localization.get_text('seller_joined_deal_title', buyer_language)}\n\n"
        f"{localization.get_text('seller_joined_deal_code', buyer_language, code=deal_code_upper)}\n"
        f"{localization.get_text('seller_joined_deal_amount', buyer_language, amount=_fmt_amount(amount), currency=currency_display)}\n"
        f"{localization.get_text('seller_joined_deal_commission', buyer_language, commission=_fmt_amount(commission_amount), currency=currency_display)}\n"
        f"{localization.get_text('seller_joined_deal_seller_receives', buyer_language, seller_amount=_fmt_amount(seller_amount), currency=currency_display)}\n\n"
        f"{localization.get_text('seller_joined_payment_address', buyer_language)}\n"
        f"{formatted_address}\n"
    )

    if currency == "TON" and payment_memo:
        buyer_info += (
            f"\n{localization.get_text('payment_memo_label', buyer_language)}: <code>{payment_memo}</code>\n"
            f"{localization.get_text('payment_memo_hint', buyer_language)}\n"
        )

    buyer_info += (
        f"\n{localization.get_text('seller_joined_instructions', buyer_language)}\n"
        f"{localization.get_text('seller_joined_instruction_1', buyer_language, amount=_fmt_amount(amount), currency=currency_display)}\n"
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
        f"{localization.get_text('seller_joined_deal_next_receive_funds', buyer_language, seller_amount=_fmt_amount(seller_amount), currency=currency_display)}\n\n"
        f"{localization.get_text('seller_joined_deal_guarantee', buyer_language)}"
    )

    deal_url = get_deal_url(deal_code_upper)
    custom_keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "💳 Pay",
                    "callback_data": f"ud_payment_method:{deal_code_upper}",
                }
            ],
            [
                {
                    "text": localization.get_text('button_view_deal', buyer_language),
                    "callback_data": f"ud_view_deal:{deal_code_upper}",
                }
            ],
        ]
    }

    # Title intentionally empty: buyer_info already includes a localized title.
    return {
        "user_id": buyer_id,
        "title": "",
        "message": buyer_info,
        "action_url": deal_url,
        "custom_keyboard": custom_keyboard,
    }


def _get_current_language():
    """Get current language from session"""
    lang = session.get('lang', None) or 'en'
    if lang not in localization.languages:
        lang = localization.default_language
    return lang

def validate_deal_code(code):
    """Validate deal code format"""
    if not code or len(code.strip()) == 0:
        return False, localization.get_text('alert_empty_description', language=_get_current_language())
    
    if len(code) != 8:
        return False, localization.get_text('invalid_deal_code_format', language=_get_current_language())
    
    # Allow alphanumeric characters only
    if not code.isalnum():
        return False, localization.get_text('invalid_deal_code_format', language=_get_current_language())
    
    return True, None

@join_deal_bp.route('/join-deal')
def join_deal_page():
    """Render the join deal page"""
    # Check if user is authenticated
    user_id = session.get('user_id')
    if not user_id:
        flash(localization.get_text('login_required_join_deal', language=_get_current_language()), 'error')
        return redirect(url_for('index'))
    
    return render_template('join-deal.html')

@join_deal_bp.route('/api/deals/verify/<deal_code>')
def verify_deal_code(deal_code):
    """API endpoint to verify deal code"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401
        
        # Validate deal code format
        is_valid, error_msg = validate_deal_code(deal_code)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Get deal information
        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'error': localization.get_text('deal_not_found', language=_get_current_language())}), 404
        
        # Check if user is already a participant
        if deal['buyer_id'] == user_id or deal.get('seller_id') == user_id:
            return jsonify({'error': localization.get_text('cannot_join_own_deal', language=_get_current_language())}), 400
        
        # Check if deal is active and has no seller
        if deal['status'] != 'active':
            return jsonify({'error': localization.get_text('deal_not_active', language=_get_current_language())}), 400
        
        if deal.get('seller_id'):
            return jsonify({'error': localization.get_text('deal_already_has_seller', language=_get_current_language())}), 400
        
        # Return deal preview data
        return jsonify({
            'code': deal['deal_code'],
            'amount': deal['amount'],
            'currency': deal['currency'],
            'status': deal['status'],
            'description': deal.get('description', ''),
            'created_at': deal['created_at']
        })
        
    except Exception as e:
        logger.error(f"Error verifying deal code {deal_code}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

@join_deal_bp.route('/api/deals/join', methods=['POST'])
def join_deal():
    """API endpoint to join a deal"""
    try:
        # Check authentication
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': localization.get_text('login_required', language=_get_current_language())}), 401
        
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': localization.get_text('invalid_data', language=_get_current_language())}), 400
        
        deal_code = data.get('dealCode', '').strip()
        
        # Validate deal code
        is_valid, error_msg = validate_deal_code(deal_code)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Get deal information
        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify({'error': localization.get_text('deal_not_found', language=_get_current_language())}), 404
        
        # Check if user is already a participant
        if deal['buyer_id'] == user_id or deal.get('seller_id') == user_id:
            return jsonify({'error': localization.get_text('cannot_join_own_deal', language=_get_current_language())}), 400
        
        # Check if deal is active and has no seller
        if deal['status'] != 'active':
            return jsonify({'error': localization.get_text('deal_not_active', language=_get_current_language())}), 400
        
        if deal.get('seller_id'):
            return jsonify({'error': localization.get_text('deal_already_has_seller', language=_get_current_language())}), 400
        
        # Join the deal
        success = db.join_deal(deal_code.upper(), user_id)
        if not success:
            return jsonify({'error': localization.get_text('join_deal_failed', language=_get_current_language())}), 500

        # IMPORTANT: Do not mark the deal as funded here.
        # Funding happens only after the buyer completes payment and it is confirmed.
        
        # Get user information for notifications
        db.get_user(user_id)
        db.get_user(deal['buyer_id'])
        
        logger.info("JOIN: seller=%s joined deal=%s buyer=%s", user_id, deal_code.upper(), deal.get('buyer_id'))

        # Notify buyer that seller joined (and provide payment instructions)
        try:
            deal_code_upper = deal_code.upper()
            payload = _notify_buyer_seller_joined(deal, deal_code_upper, user_id)

            try:
                db.create_notification(
                    payload["user_id"],
                    "seller_joined",
                    payload["title"],
                    payload["message"],
                    payload["action_url"],
                )
            except Exception as db_notify_error:
                logger.warning(f"Failed to persist seller-joined notification for deal {deal_code_upper}: {db_notify_error}")

            sent = notification_manager.send_telegram_notification_sync(
                user_id=payload["user_id"],
                title=payload["title"],
                message=payload["message"],
                action_url=payload["action_url"],
                custom_keyboard=payload["custom_keyboard"],
            )
            logger.info("JOIN: telegram notify buyer=%s deal=%s sent=%s", payload["user_id"], deal_code_upper, sent)

            if not sent:
                try:
                    from shared.async_utils import fire_and_forget
                    fire_and_forget(notification_manager._send_telegram_notification(  # type: ignore[attr-defined]
                        payload["user_id"],
                        payload["title"],
                        payload["message"],
                        payload["action_url"],
                        payload["custom_keyboard"],
                    ))
                except Exception as fallback_error:
                    logger.warning(f"Failed to schedule fallback Telegram send for deal {deal_code_upper}: {fallback_error}")
        except Exception as notify_error:
            logger.warning(f"Failed to send seller joined notification for deal {deal_code}: {notify_error}")
        
        # Return success response with redirect URL
        return jsonify({
            'success': True,
            'message': localization.get_text('join_deal_success', language=_get_current_language()),
            'redirect_url': get_deal_url(deal_code.upper())
        })
        
    except Exception as e:
        logger.error(f"Error joining deal {deal_code}: {e}")
        return jsonify({'error': localization.get_text('server_error', language=_get_current_language())}), 500

def register_join_deal_routes(app):
    """Register join deal routes with the Flask app"""
    app.register_blueprint(join_deal_bp)
    logger.info("Join deal routes registered successfully")


@join_deal_bp.route('/api/join-deal/<deal_code>', methods=['POST'])
def join_deal_from_detail(deal_code: str):
    """Join a deal from the deal detail page (legacy endpoint used by deal_detail.html)."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': localization.get_text('login_required', language=_get_current_language())}), 401

        code = (deal_code or "").strip().upper()
        is_valid, error_msg = validate_deal_code(code)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400

        deal = db.get_deal(code)
        if not deal:
            return jsonify({'success': False, 'message': localization.get_text('deal_not_found', language=_get_current_language())}), 404

        if deal['buyer_id'] == user_id or deal.get('seller_id') == user_id:
            return jsonify({'success': False, 'message': localization.get_text('cannot_join_own_deal', language=_get_current_language())}), 400

        if deal['status'] != 'active':
            return jsonify({'success': False, 'message': localization.get_text('deal_not_active', language=_get_current_language())}), 400

        if deal.get('seller_id'):
            return jsonify({'success': False, 'message': localization.get_text('deal_already_has_seller', language=_get_current_language())}), 400

        success = db.join_deal(code, user_id)
        if not success:
            return jsonify({'success': False, 'message': localization.get_text('join_deal_failed', language=_get_current_language())}), 500

        logger.info("JOIN(legacy): seller=%s joined deal=%s buyer=%s", user_id, code, deal.get('buyer_id'))

        try:
            payload = _notify_buyer_seller_joined(deal, code, user_id)

            try:
                db.create_notification(
                    payload["user_id"],
                    "seller_joined",
                    payload["title"],
                    payload["message"],
                    payload["action_url"],
                )
            except Exception as db_notify_error:
                logger.warning(f"Failed to persist seller-joined notification for deal {code}: {db_notify_error}")

            sent = notification_manager.send_telegram_notification_sync(
                user_id=payload["user_id"],
                title=payload["title"],
                message=payload["message"],
                action_url=payload["action_url"],
                custom_keyboard=payload["custom_keyboard"],
            )
            logger.info("JOIN(legacy): telegram notify buyer=%s deal=%s sent=%s", payload["user_id"], code, sent)

            if not sent:
                try:
                    from shared.async_utils import fire_and_forget
                    fire_and_forget(notification_manager._send_telegram_notification(  # type: ignore[attr-defined]
                        payload["user_id"],
                        payload["title"],
                        payload["message"],
                        payload["action_url"],
                        payload["custom_keyboard"],
                    ))
                except Exception as fallback_error:
                    logger.warning(f"Failed to schedule fallback Telegram send for deal {code}: {fallback_error}")
        except Exception as notify_error:
            logger.warning(f"Failed to send seller joined notification for deal {code}: {notify_error}")

        return jsonify({'success': True, 'message': localization.get_text('join_deal_success', language=_get_current_language())})

    except Exception as e:
        logger.error(f"Error joining deal {deal_code}: {e}")
        return jsonify({'success': False, 'message': localization.get_text('server_error', language=_get_current_language())}), 500

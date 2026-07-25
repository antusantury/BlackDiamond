from flask import Blueprint, request, jsonify, session
import logging

from shared.database import db
from shared.platform_sync import (
    cross_platform_sync, notify_deal_created, notify_deal_joined,
    notify_deal_status_changed
)
from shared.notifications import notification_manager
from shared.async_utils import fire_and_forget
from web.utils import validation_utils, deal_utils, response_utils
from shared.constants import (
    CREATE_DEAL_RATE_LIMIT, JOIN_DEAL_RATE_LIMIT, RATE_LIMIT_WINDOW, DEFAULT_COMMISSION_RATE
)

logger = logging.getLogger(__name__)

# Create blueprint
cross_platform_bp = Blueprint('cross_platform', __name__, url_prefix='/api/cross-platform')


def _get_current_language() -> str:
    """Get current UI language"""
    try:
        lang = session.get('lang', None) or 'en'
        if lang not in ['en', 'ua']:
            lang = 'en'
        return lang
    except Exception:
        return 'en'


def _get_current_user_id() -> int:
    """Get current user ID from session"""
    return session.get('user_id')


@cross_platform_bp.route('/deal/create', methods=['POST'])
def api_create_deal_cross_platform():
    """Cross-platform deal creation API"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Rate limiting
        if not db.check_rate_limit(f"create_deal:{user_id}", limit=CREATE_DEAL_RATE_LIMIT, window=RATE_LIMIT_WINDOW):
            return jsonify(response_utils.error_response('Rate limit exceeded')), 429

        data = request.get_json()
        if not data:
            return jsonify(response_utils.error_response('Invalid request data')), 400

        # Validate required fields
        currency = data.get('currency', '').upper().strip()
        amount_str = data.get('amount', '').strip()
        description = data.get('description', '').strip()
        product_link = data.get('product_link', '').strip()

        # Validate currency
        if not validation_utils.validate_currency(currency):
            return jsonify(response_utils.error_response('Invalid currency')), 400

        # Validate amount (range is enforced in USD terms)
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(response_utils.error_response('Invalid amount')), 400

        from shared.currency_conversion import convert_amount_to_usd
        from shared.constants import MIN_DEAL_AMOUNT, MAX_DEAL_AMOUNT
        amount_usd = convert_amount_to_usd(amount, currency)
        if not (MIN_DEAL_AMOUNT <= amount_usd <= MAX_DEAL_AMOUNT):
            return jsonify(response_utils.error_response('Invalid amount range')), 400

        if currency == 'TON':
            amount = round(amount, 4)
        elif currency == 'USDT':
            amount = round(amount, 2)

        # Generate deal code
        deal_code = deal_utils.generate_deal_code()

        # Create deal in database
        success = db.create_deal(
            deal_code=deal_code,
            buyer_id=user_id,
            amount=amount,
            currency=currency,
            description=description if description else None,
            product_link=product_link if product_link else None
        )

        if not success:
            return jsonify(response_utils.error_response('Failed to create deal')), 500

        # Create payment checkout
        from shared.payments import payment_processor
        checkout = payment_processor.process_deal_payment(
            deal_code=deal_code,
            amount=amount,
            currency=currency,
            description=description
        )

        if not checkout:
            db.update_deal_status(deal_code, 'cancelled')
            return jsonify(response_utils.error_response('Failed to create payment')), 500

        # Notify cross-platform sync
        deal_data = {
            'deal_code': deal_code,
            'amount': amount,
            'currency': currency,
            'description': description,
            'product_link': product_link,
            'checkout_id': checkout['checkout_id']
        }

        fire_and_forget(notify_deal_created(
            deal_code=deal_code,
            user_id=user_id,
            platform='web',
            deal_data=deal_data
        ))

        return jsonify(response_utils.success_response({
            'deal_code': deal_code,
            'checkout_id': checkout['checkout_id'],
            'message': 'Deal created successfully',
            'deal_data': deal_data
        }))

    except Exception as e:
        logger.error(f"Error in cross-platform deal creation: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/deal/<deal_code>/join', methods=['POST'])
def api_join_deal_cross_platform(deal_code):
    """Cross-platform deal joining API"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Rate limiting
        if not db.check_rate_limit(f"join_deal:{user_id}", limit=JOIN_DEAL_RATE_LIMIT, window=RATE_LIMIT_WINDOW):
            return jsonify(response_utils.error_response('Rate limit exceeded')), 429

        # Validate deal code
        if not validation_utils.validate_deal_code(deal_code.upper()):
            return jsonify(response_utils.error_response('Invalid deal code')), 400

        # Check deal exists
        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify(response_utils.error_response('Deal not found')), 404

        if deal['status'] != 'active':
            return jsonify(response_utils.error_response('Deal not active')), 400

        if deal['buyer_id'] == user_id:
            return jsonify(response_utils.error_response('Cannot join own deal')), 400

        if deal.get('seller_id') is not None:
            return jsonify(response_utils.error_response('Deal already has seller')), 400

        # Join deal
        success = db.join_deal(deal_code.upper(), user_id)
        if not success:
            return jsonify(response_utils.error_response('Failed to join deal')), 500

        # Calculate commission
        settings = db.get_settings()
        commission_rate = settings.get('commission_rate', DEFAULT_COMMISSION_RATE)
        commission_amount, seller_amount = deal_utils.calculate_commission(deal['amount'], commission_rate)

        # Notify cross-platform sync
        join_data = {
            'deal_code': deal_code.upper(),
            'amount': deal['amount'],
            'currency': deal['currency'],
            'commission_rate': commission_rate,
            'commission_amount': commission_amount,
            'seller_amount': seller_amount
        }

        fire_and_forget(notify_deal_joined(
            deal_code=deal_code.upper(),
            user_id=user_id,
            platform='web',
            deal_data=join_data
        ))

        # Notify buyer
        fire_and_forget(notification_manager.notify_deal_joined(
            user_id=deal['buyer_id'],
            deal_code=deal_code.upper(),
            amount=deal['amount'],
            currency=deal['currency']
        ))

        return jsonify(response_utils.success_response({
            'message': 'Successfully joined deal',
            'deal_data': join_data
        }))

    except Exception as e:
        logger.error(f"Error joining deal {deal_code}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/deal/<deal_code>/status', methods=['PUT'])
def api_update_deal_status_cross_platform(deal_code):
    """Cross-platform deal status update API"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Validate deal code
        if not validation_utils.validate_deal_code(deal_code.upper()):
            return jsonify(response_utils.error_response('Invalid deal code')), 400

        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify(response_utils.error_response('Status required')), 400

        new_status = data['status']
        valid_statuses = ['active', 'pending', 'completed', 'cancelled', 'expired']

        if new_status not in valid_statuses:
            return jsonify(response_utils.error_response('Invalid status')), 400

        # Check deal exists and user has permission
        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify(response_utils.error_response('Deal not found')), 404

        # Check permissions
        is_participant = (deal['buyer_id'] == user_id or deal.get('seller_id') == user_id)
        if not is_participant:
            return jsonify(response_utils.error_response('No permission')), 403

        # Additional permission checks
        if new_status == 'cancelled' and deal['buyer_id'] != user_id:
            return jsonify(response_utils.error_response('Only buyer can cancel')), 403

        if new_status == 'completed' and deal.get('seller_id') != user_id:
            return jsonify(response_utils.error_response('Only seller can complete')), 403

        # Update status
        old_status = deal['status']
        success = db.update_deal_status(deal_code.upper(), new_status)
        if not success:
            return jsonify(response_utils.error_response('Failed to update status')), 500

        # Notify cross-platform sync
        fire_and_forget(notify_deal_status_changed(
            deal_code=deal_code.upper(),
            user_id=user_id,
            platform='web',
            old_status=old_status,
            new_status=new_status
        ))

        return jsonify(response_utils.success_response({
            'message': f'Deal status updated to {new_status}',
            'old_status': old_status,
            'new_status': new_status
        }))

    except Exception as e:
        logger.error(f"Error updating deal status {deal_code}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/deal/<deal_code>/sync', methods=['GET'])
def api_get_deal_sync_status(deal_code):
    """Get deal synchronization status"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Validate deal code
        if not validation_utils.validate_deal_code(deal_code.upper()):
            return jsonify(response_utils.error_response('Invalid deal code')), 400

        # Check deal exists and user has access
        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify(response_utils.error_response('Deal not found')), 404

        is_participant = (deal['buyer_id'] == user_id or deal.get('seller_id') == user_id)
        if not is_participant:
            return jsonify(response_utils.error_response('No access')), 403

        # Get sync information
        sync_info = {
            'deal_code': deal['deal_code'],
            'status': deal['status'],
            'last_updated': deal.get('updated_at'),
            'participants': {
                'buyer_id': deal['buyer_id'],
                'seller_id': deal.get('seller_id'),
                'has_seller': deal.get('seller_id') is not None
            },
            'subscribed_sessions': cross_platform_sync.get_deal_subscriptions(deal_code.upper())
        }

        return jsonify(response_utils.success_response(sync_info))

    except Exception as e:
        logger.error(f"Error getting sync status for {deal_code}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/session/create', methods=['POST'])
def api_create_sync_session():
    """Create a synchronization session for real-time updates"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Create session
        session_id = cross_platform_sync.create_session(user_id, 'web')

        return jsonify(response_utils.success_response({
            'session_id': session_id,
            'message': 'Sync session created'
        }))

    except Exception as e:
        logger.error(f"Error creating sync session: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/session/<session_id>/subscribe/<deal_code>', methods=['POST'])
def api_subscribe_to_deal(session_id, deal_code):
    """Subscribe to deal updates"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Validate session belongs to user
        session_info = cross_platform_sync.get_session_info(session_id)
        if not session_info or session_info['user_id'] != user_id:
            return jsonify(response_utils.error_response('Invalid session')), 403

        # Validate deal code and access
        if not validation_utils.validate_deal_code(deal_code.upper()):
            return jsonify(response_utils.error_response('Invalid deal code')), 400

        deal = db.get_deal(deal_code.upper())
        if not deal:
            return jsonify(response_utils.error_response('Deal not found')), 404

        is_participant = (deal['buyer_id'] == user_id or deal.get('seller_id') == user_id)
        if not is_participant:
            return jsonify(response_utils.error_response('No access')), 403

        # Subscribe
        success = cross_platform_sync.subscribe_to_deal(session_id, deal_code.upper())

        if success:
            return jsonify(response_utils.success_response({
                'message': f'Subscribed to deal {deal_code.upper()}'
            }))
        else:
            return jsonify(response_utils.error_response('Failed to subscribe')), 500

    except Exception as e:
        logger.error(f"Error subscribing to deal {deal_code}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/session/<session_id>/unsubscribe/<deal_code>', methods=['POST'])
def api_unsubscribe_from_deal(session_id, deal_code):
    """Unsubscribe from deal updates"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Validate session belongs to user
        session_info = cross_platform_sync.get_session_info(session_id)
        if not session_info or session_info['user_id'] != user_id:
            return jsonify(response_utils.error_response('Invalid session')), 403

        # Unsubscribe
        success = cross_platform_sync.unsubscribe_from_deal(session_id, deal_code.upper())

        if success:
            return jsonify(response_utils.success_response({
                'message': f'Unsubscribed from deal {deal_code.upper()}'
            }))
        else:
            return jsonify(response_utils.error_response('Failed to unsubscribe')), 500

    except Exception as e:
        logger.error(f"Error unsubscribing from deal {deal_code}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


@cross_platform_bp.route('/session/<session_id>', methods=['DELETE'])
def api_remove_sync_session(session_id):
    """Remove a synchronization session"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Validate session belongs to user
        session_info = cross_platform_sync.get_session_info(session_id)
        if not session_info or session_info['user_id'] != user_id:
            return jsonify(response_utils.error_response('Invalid session')), 403

        # Remove session
        cross_platform_sync.remove_session(session_id)

        return jsonify(response_utils.success_response({
            'message': 'Session removed'
        }))

    except Exception as e:
        logger.error(f"Error removing sync session {session_id}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


# WebSocket/SSE endpoint for real-time updates (simplified)
@cross_platform_bp.route('/events/<session_id>', methods=['GET'])
def api_events_stream(session_id):
    """Server-Sent Events endpoint for real-time deal updates"""
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return jsonify(response_utils.error_response('Authentication required')), 401

        # Validate session
        session_info = cross_platform_sync.get_session_info(session_id)
        if not session_info or session_info['user_id'] != user_id:
            return jsonify(response_utils.error_response('Invalid session')), 403

        def generate():
            """Generate SSE events"""
            try:
                # This is a simplified implementation
                # In production, you'd use proper SSE or WebSocket
                while True:
                    # Check for new events (simplified polling)
                    # In real implementation, this would be event-driven
                    import time
                    time.sleep(5)  # Poll every 5 seconds

                    # Send heartbeat
                    yield f"data: {{\"type\": \"heartbeat\", \"timestamp\": {int(time.time())}}}\n\n"

            except GeneratorExit:
                # Client disconnected
                cross_platform_sync.remove_session(session_id)
            except Exception as e:
                logger.error(f"Error in event stream: {e}")

        # Import Flask app for response
        from flask import Response
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'}
        )

    except Exception as e:
        logger.error(f"Error setting up event stream for {session_id}: {e}")
        return jsonify(response_utils.error_response('Internal server error')), 500


# Initialize cross-platform sync when module is imported
async def init_cross_platform_sync():
    """Initialize cross-platform synchronization"""
    try:
        await cross_platform_sync.start_sync()
        logger.info("Cross-platform synchronization initialized")
    except Exception as e:
        logger.error(f"Failed to initialize cross-platform sync: {e}")

# Removed automatic initialization on import to prevent event loop issues
# Initialization will be handled by the Flask app startup code instead

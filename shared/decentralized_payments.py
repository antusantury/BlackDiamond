import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import requests
import qrcode
import base64
import io
from PIL import Image, ImageDraw, ImageFont
import string
import random

# Import new error handling and logging systems
from shared.error_handling import (
    handle_errors
)
from shared.circuit_breaker import (
    circuit_breaker, ExternalServiceCircuitBreaker
)
from shared.logging_system import (
    structured_logger, log_operation, LogCategory, create_log_context
)

from .config import (
    COMMISSION_RATE, TRONGRID_API_KEY, TONCENTER_API_KEY,
    USDT_SYSTEM_ADDRESS, TON_SYSTEM_ADDRESS
)
from .database import db

logger = logging.getLogger(__name__)


def create_blockchain_circuits():
    """Create circuit breakers for blockchain APIs"""
    return {
        'trongrid': ExternalServiceCircuitBreaker.create_blockchain_circuit("trongrid"),
        'toncenter': ExternalServiceCircuitBreaker.create_blockchain_circuit("toncenter")
    }


class EnhancedBlockchainProcessor:
    """Enhanced blockchain processor with comprehensive error handling and fallbacks"""
    
    def __init__(self):
        # Circuit breakers for external APIs
        self.circuits = create_blockchain_circuits()
        
        # System wallet addresses for escrow
        self.system_wallets = {
            'USDT': {
                'address': USDT_SYSTEM_ADDRESS,
                'api_url': 'https://api.trongrid.io',
                'explorer': 'https://tronscan.org',
                'circuit_name': 'trongrid'
            },
            'TON': {
                'address': TON_SYSTEM_ADDRESS,
                'api_url': 'https://toncenter.com/api/v2',
                'explorer': 'https://tonscan.org',
                'circuit_name': 'toncenter'
            }
        }
        
        # API keys for blockchain monitoring
        self.api_keys = {
            'USDT': TRONGRID_API_KEY,
            'TON': TONCENTER_API_KEY
        }
        
        # Cache for payment verification results
        self.payment_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        # Fallback mechanisms
        self.fallback_apis = {
            'USDT': [
                'https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?contract_address={contract}&limit=100&min_block_timestamp={timestamp}&only_confirmed=true',
                'https://api.trongrid.io/v2/accounts/{address}/transactions/trc20?contract_address={contract}&limit=100&min_block_timestamp={timestamp}&only_confirmed=true'
            ],
            'TON': [
                'https://toncenter.com/api/v2',
                'https://toncenter.com/api/v2/getTransactions'  # Direct endpoint
            ]
        }
        
        # Validate configuration
        self._validate_config()
        
        structured_logger.info(
            "Enhanced blockchain processor initialized",
            category=LogCategory.BLOCKCHAIN,
            operation="initialization",
            currencies=list(self.system_wallets.keys())
        )

    def _validate_config(self):
        """Enhanced configuration validation with detailed logging"""
        try:
            for currency, config in self.system_wallets.items():
                address = config['address']
                if not address:
                    structured_logger.warning(
                        f"{currency} system address not configured",
                        category=LogCategory.SYSTEM,
                        operation="config_validation",
                        currency=currency
                    )
                else:
                    # Validate address format
                    if currency == 'USDT' and not address.startswith('T'):
                        structured_logger.error(
                            f"Invalid USDT address format: {address}",
                            category=LogCategory.SECURITY,
                            operation="config_validation",
                            currency=currency
                        )
                    elif currency == 'TON' and not (address.startswith('UQ') or address.startswith('EQ')):
                        structured_logger.error(
                            f"Invalid TON address format: {address}",
                            category=LogCategory.SECURITY,
                            operation="config_validation",
                            currency=currency
                        )
                    else:
                        structured_logger.info(
                            f"{currency} escrow address configured: {address[:10]}...",
                            category=LogCategory.SYSTEM,
                            operation="config_validation",
                            currency=currency
                        )
            
            # Check API keys
            for currency, api_key in self.api_keys.items():
                if not api_key:
                    structured_logger.warning(
                        f"{currency} API key not configured - using limited mode",
                        category=LogCategory.SYSTEM,
                        operation="config_validation",
                        currency=currency
                    )
                    
        except Exception as e:
            structured_logger.critical(
                f"Blockchain configuration validation failed: {e}",
                category=LogCategory.SECURITY,
                operation="config_validation",
                exception=e
            )
            raise RuntimeError(f"Blockchain configuration validation failed: {e}")

    def _normalize_ton_address(self, address: Optional[str]) -> str:
        """Normalize a TON address so different friendly formats compare equal."""
        if not address or not isinstance(address, str):
            return ""

        try:
            from tonsdk.utils import Address  # type: ignore

            # Raw format: "<workchain>:<64 hex>"
            return Address(address).to_string(is_user_friendly=False)
        except Exception:
            # Fallback: best-effort string compare
            return address

    @log_operation("generate_deal_memo", LogCategory.BLOCKCHAIN)
    def generate_deal_memo(self, deal_code: str) -> str:
        """Generate unique memo for deal payment"""
        try:
            if not deal_code or not isinstance(deal_code, str):
                raise ValueError("Invalid deal code")
            
            memo = f"DEAL-{deal_code}"
            
            structured_logger.debug(
                f"Generated payment memo: {memo}",
                category=LogCategory.BLOCKCHAIN,
                operation="generate_deal_memo",
                deal_code=deal_code,
                memo=memo
            )
            
            return memo
            
        except Exception as e:
            structured_logger.error(
                f"Error generating deal memo: {e}",
                category=LogCategory.BLOCKCHAIN,
                operation="generate_deal_memo",
                exception=e
            )
            # Return fallback memo
            return f"DEAL-{str(deal_code)[:10]}"

    @circuit_breaker(name="check_usdt_payment", failure_threshold=0.3, timeout=60.0)
    @log_operation("_check_usdt_payment", LogCategory.BLOCKCHAIN)
    def _check_usdt_payment(self, address: str, expected_amount: float, memo: str = None) -> Tuple[bool, Optional[str]]:
        """Enhanced USDT payment check with fallback mechanisms"""
        context = create_log_context(
            service="blockchain_processor",
            operation="check_usdt_payment",
            custom_fields={
                'address': address[:10] + "..." if len(address) > 10 else address,
                'expected_amount': expected_amount,
                'memo': memo
            }
        )
        
        try:
            structured_logger.debug(
                "Starting USDT payment verification",
                category=LogCategory.BLOCKCHAIN,
                context=context,
                operation="check_usdt_payment"
            )
            
            # Try multiple API endpoints for redundancy
            api_endpoints = self.fallback_apis['USDT']
            
            for api_url_template in api_endpoints:
                try:
                    structured_logger.debug(
                        f"Trying USDT API endpoint: {api_url_template}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_usdt_payment"
                    )
                    
                    # Prepare API request with proper URL formatting
                    contract_address = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
                    url = api_url_template.format(
                        address=address,
                        contract=contract_address,
                        timestamp=int((time.time() - 3600) * 1000)  # Last hour
                    )
                    params = {'limit': 100, 'only_confirmed': True}
                    headers = {}
                    
                    if self.api_keys['USDT']:
                        headers['TRON-PRO-API-KEY'] = self.api_keys['USDT']

                    # Make request with timeout
                    response = requests.get(
                        url, 
                        params=params, 
                        headers=headers, 
                        timeout=10
                    )
                    response.raise_for_status()

                    data = response.json()
                    transactions = data.get('data', [])

                    # Process transactions
                    for tx in transactions:
                        try:
                            amount_usdt = float(tx.get('value', '0')) / 1000000  # Convert from smallest unit

                            # Check amount with tolerance
                            if abs(amount_usdt - expected_amount) <= 0.01:
                                # For USDT, memo verification is not always reliable, so we skip it
                                if tx.get('confirmed', False):
                                    tx_id = tx.get('transaction_id')
                                    
                                    structured_logger.info(
                                        f"USDT payment confirmed: {amount_usdt} USDT, TX: {tx_id}",
                                        category=LogCategory.PAYMENT,
                                        context=context,
                                        operation="check_usdt_payment",
                                        amount=amount_usdt,
                                        tx_hash=tx_id
                                    )
                                    
                                    return True, tx_id
                                    
                        except Exception as tx_error:
                            structured_logger.warning(
                                f"Error processing USDT transaction: {tx_error}",
                                category=LogCategory.BLOCKCHAIN,
                                context=context,
                                operation="check_usdt_payment",
                                exception=tx_error
                            )
                            continue

                    # Move to next endpoint if no payment found
                    structured_logger.warning(
                        f"No USDT payment found at {api_url_template}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_usdt_payment"
                    )
                    
                except requests.exceptions.Timeout:
                    structured_logger.warning(
                        f"USDT API timeout at {api_url}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_usdt_payment",
                        api_url=api_url_template
                    )
                    continue

                except requests.exceptions.ConnectionError:
                    structured_logger.warning(
                        f"USDT API connection failed at {api_url}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_usdt_payment",
                        api_url=api_url_template
                    )
                    continue
                    
                except requests.exceptions.HTTPError as e:
                    structured_logger.warning(
                        f"USDT API HTTP error at {api_url}: {e}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_usdt_payment",
                        api_url=api_url_template,
                        status_code=e.response.status_code if hasattr(e, 'response') else None
                    )
                    continue
                    
                except Exception as api_error:
                    structured_logger.warning(
                        f"USDT API error at {api_url}: {api_error}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_usdt_payment",
                        api_url=api_url_template,
                        exception=api_error
                    )
                    continue

            # No payment found at any endpoint
            structured_logger.warning(
                "USDT payment not found at any API endpoint",
                category=LogCategory.BLOCKCHAIN,
                context=context,
                operation="check_usdt_payment"
            )
            
            return False, "Payment not found at any USDT API endpoint"

        except Exception as e:
            structured_logger.error(
                f"USDT payment check failed: {e}",
                category=LogCategory.ERROR,
                context=context,
                operation="check_usdt_payment",
                exception=e
            )
            return False, "USDT payment check error"

    @circuit_breaker(name="check_ton_payment", failure_threshold=0.3, timeout=60.0)
    @log_operation("_check_ton_payment", LogCategory.BLOCKCHAIN)
    def _check_ton_payment(self, address: str, expected_amount: float, memo: str = None) -> Tuple[bool, Optional[str]]:
        """Enhanced TON payment check with fallback mechanisms"""
        context = create_log_context(
            service="blockchain_processor",
            operation="check_ton_payment",
            custom_fields={
                'address': address[:10] + "..." if len(address) > 10 else address,
                'expected_amount': expected_amount,
                'memo': memo
            }
        )
        
        try:
            structured_logger.debug(
                "Starting TON payment verification",
                category=LogCategory.BLOCKCHAIN,
                context=context,
                operation="check_ton_payment"
            )

            normalized_address = self._normalize_ton_address(address)
            
            # Try multiple API endpoints for redundancy
            api_endpoints = self.fallback_apis['TON']
            
            for api_url in api_endpoints:
                try:
                    structured_logger.debug(
                        f"Trying TON API endpoint: {api_url}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_ton_payment"
                    )
                    
                    # Prepare API request - handle endpoints that already include the path
                    if '/getTransactions' in api_url:
                        url = api_url
                        params = {
                            'address': address,
                            'limit': 10,
                            'archival': 'true'
                        }
                    else:
                        url = f"{api_url}/getTransactions"
                        params = {
                            'address': address,
                            'limit': 10,
                            'archival': 'true'
                        }
                    
                    headers = {}
                    if self.api_keys['TON']:
                        headers['X-API-Key'] = self.api_keys['TON']

                    # Make request with timeout
                    response = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=10
                    )
                    response.raise_for_status()

                    data = response.json()
                    transactions = data.get('result', [])

                    # Process transactions
                    for tx in transactions:
                        try:
                            in_msg = tx.get('in_msg', {})
                            destination = in_msg.get('destination')
                            if not destination:
                                continue

                            normalized_destination = self._normalize_ton_address(destination)
                            if normalized_address and normalized_destination and normalized_destination != normalized_address:
                                # Not an incoming transfer to our escrow address
                                continue

                            value_nanotons = int(in_msg.get('value', '0'))
                            value_ton = value_nanotons / 1000000000

                            # Check amount with tolerance
                            if abs(value_ton - expected_amount) <= 0.001:
                                # Verify memo if provided
                                if memo:
                                    # Prefer TonCenter's already-decoded `in_msg.message` (plain text).
                                    decoded_comment = in_msg.get("message", "")
                                    if not decoded_comment:
                                        decoded_comment = self._decode_ton_message(in_msg)
                                    if isinstance(decoded_comment, dict):
                                        decoded_comment = self._decode_ton_message(decoded_comment)

                                    if memo not in str(decoded_comment or ""):
                                        continue

                                tx_id = tx.get('transaction_id', {}).get('hash')

                                structured_logger.info(
                                    f"TON payment confirmed: {value_ton} TON, TX: {tx_id}",
                                    category=LogCategory.PAYMENT,
                                    context=context,
                                    operation="check_ton_payment",
                                    amount=value_ton,
                                    tx_hash=tx_id
                                )

                                return True, tx_id
                                    
                        except Exception as tx_error:
                            structured_logger.warning(
                                f"Error processing TON transaction: {tx_error}",
                                category=LogCategory.BLOCKCHAIN,
                                context=context,
                                operation="check_ton_payment",
                                exception=tx_error
                            )
                            continue

                    # Move to next endpoint if no payment found
                    structured_logger.warning(
                        f"No TON payment found at {api_url}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_ton_payment"
                    )
                    
                except requests.exceptions.Timeout:
                    structured_logger.warning(
                        f"TON API timeout at {api_url}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_ton_payment",
                        api_url=api_url
                    )
                    continue

                except requests.exceptions.ConnectionError:
                    structured_logger.warning(
                        f"TON API connection failed at {api_url}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_ton_payment",
                        api_url=api_url
                    )
                    continue

                except requests.exceptions.HTTPError as e:
                    structured_logger.warning(
                        f"TON API HTTP error at {api_url}: {e}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_ton_payment",
                        api_url=api_url,
                        status_code=e.response.status_code if hasattr(e, 'response') else None
                    )
                    continue

                except Exception as api_error:
                    structured_logger.warning(
                        f"TON API error at {api_url}: {api_error}",
                        category=LogCategory.BLOCKCHAIN,
                        context=context,
                        operation="check_ton_payment",
                        api_url=api_url,
                        exception=api_error
                    )
                    continue

            # No payment found at any endpoint
            structured_logger.warning(
                "TON payment not found at any API endpoint",
                category=LogCategory.BLOCKCHAIN,
                context=context,
                operation="check_ton_payment"
            )
            
            return False, "Payment not found at any TON API endpoint"

        except Exception as e:
            structured_logger.error(
                f"TON payment check failed: {e}",
                category=LogCategory.ERROR,
                context=context,
                operation="check_ton_payment",
                exception=e
            )
            return False, "TON payment check error"

    def _decode_ton_message(self, message: dict) -> str:
        """Enhanced TON message decoding with error handling"""
        try:
            # TonCenter often provides an already-decoded comment here.
            direct_message = message.get("message")
            if isinstance(direct_message, str) and direct_message:
                return direct_message

            msg_data = message.get('msg_data', {})
            if msg_data.get('@type') == 'msg.dataText':
                text_value = msg_data.get('text')
                if text_value:
                    try:
                        if isinstance(text_value, str):
                            # TonCenter returns msg.dataText.text as base64; some endpoints may return hex/plain text.
                            try:
                                import base64

                                padded = text_value + ("=" * (-len(text_value) % 4))
                                decoded = base64.b64decode(padded, validate=True)
                                return decoded.decode("utf-8")
                            except Exception:
                                pass

                            try:
                                comment_bytes = bytes.fromhex(text_value)
                                return comment_bytes.decode('utf-8')
                            except (ValueError, UnicodeDecodeError):
                                return text_value

                        return str(text_value)
                    except (ValueError, UnicodeDecodeError):
                        pass
            
            # Try other decoding methods
            for field in ['message', 'text', 'payload']:
                if field in message:
                    try:
                        if isinstance(message[field], dict):
                            continue  # Skip dict types
                        
                        # Try hex decoding
                        if field == 'message':
                            try:
                                comment_bytes = bytes.fromhex(message[field])
                                return comment_bytes.decode('utf-8')
                            except (ValueError, UnicodeDecodeError):
                                return message[field]
                        
                        return str(message[field])
                    except:
                        continue
            
            return ""
            
        except Exception as e:
            structured_logger.warning(
                f"Error decoding TON message: {e}",
                category=LogCategory.BLOCKCHAIN,
                operation="_decode_ton_message",
                exception=e
            )
            return ""

    @handle_errors(
        fallback_on_error=True
    )
    @log_operation("check_incoming_payment", LogCategory.PAYMENT)
    def check_incoming_payment(self, address: str, expected_amount: float,
                              currency: str, memo: str = None) -> Tuple[bool, Optional[str]]:
        """Enhanced payment check with graceful degradation"""
        context = create_log_context(
            service="blockchain_processor",
            operation="check_incoming_payment",
            custom_fields={
                'address': address[:10] + "..." if len(address) > 10 else address,
                'expected_amount': expected_amount,
                'currency': currency,
                'memo': memo
            }
        )
        
        try:
            # Input validation
            if not address or not isinstance(address, str):
                raise ValueError("Invalid address: must be a non-empty string")

            if not isinstance(expected_amount, (int, float)) or expected_amount <= 0:
                raise ValueError("Invalid amount: must be a positive number")

            if currency.upper() not in ['USDT', 'TON']:
                raise ValueError(f"Unsupported currency: {currency}. Only USDT and TON are supported")

            structured_logger.info(
                f"Checking {currency.upper()} payment",
                category=LogCategory.PAYMENT,
                context=context,
                operation="check_incoming_payment",
                currency=currency.upper()
            )

            # Dispatch to appropriate currency handler
            if currency.upper() == 'USDT':
                result = self._check_usdt_payment(address, expected_amount, memo)
            elif currency.upper() == 'TON':
                result = self._check_ton_payment(address, expected_amount, memo)
            else:
                structured_logger.error(
                    f"Unsupported currency: {currency}",
                    category=LogCategory.ERROR,
                    context=context,
                    operation="check_incoming_payment"
                )
                return False, "Unsupported currency"

            if result[0]:  # Payment found
                structured_logger.info(
                    f"{currency.upper()} payment verified successfully",
                    category=LogCategory.PAYMENT,
                    context=context,
                    operation="check_incoming_payment",
                    tx_hash=result[1]
                )
            else:
                structured_logger.warning(
                    f"{currency.upper()} payment not found",
                    category=LogCategory.PAYMENT,
                    context=context,
                    operation="check_incoming_payment"
                )

            return result

        except Exception as e:
            structured_logger.error(
                f"Error checking {currency.upper()} payment: {e}",
                category=LogCategory.ERROR,
                context=context,
                operation="check_incoming_payment",
                exception=e
            )
            
            # Graceful degradation - return fallback response
            return False, f"Payment verification failed: {str(e)}"

    @log_operation("create_escrow_transaction", LogCategory.BLOCKCHAIN)
    def create_escrow_transaction(self, deal_code: str, buyer_address: str,
                                amount: float, currency: str) -> Tuple[bool, Optional[str]]:
        """Enhanced escrow transaction creation with comprehensive error handling"""
        context = create_log_context(
            service="blockchain_processor",
            custom_fields={
                'deal_code': deal_code,
                'buyer_address': buyer_address[:10] + "..." if len(buyer_address) > 10 else buyer_address,
                'amount': amount,
                'currency': currency
            }
        )
        
        try:
            structured_logger.info(
                f"Creating escrow transaction for deal {deal_code}",
                category=LogCategory.ESCROW,
                context=context,
                operation="create_escrow_transaction"
            )
            
            # Input validation
            if not deal_code or not isinstance(deal_code, str):
                raise ValueError("Invalid deal code")
            
            if not buyer_address or not isinstance(buyer_address, str):
                raise ValueError("Invalid buyer address")
            
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise ValueError("Invalid amount")
            
            if currency.upper() not in ['USDT', 'TON']:
                raise ValueError(f"Unsupported currency: {currency}")
            
            currency_upper = currency.upper()
            escrow_address = self.system_wallets[currency_upper]['address']
            if not escrow_address:
                structured_logger.error(
                    f"{currency_upper} escrow address not configured",
                    category=LogCategory.ESCROW,
                    context=context,
                    operation="create_escrow_transaction"
                )
                return False, "Escrow address not configured"

            if currency_upper == 'USDT' and not escrow_address.startswith('T'):
                structured_logger.error(
                    f"Invalid USDT escrow address format: {escrow_address}",
                    category=LogCategory.ESCROW,
                    context=context,
                    operation="create_escrow_transaction"
                )
                return False, "Invalid USDT escrow address"
            if currency_upper == 'TON' and not (escrow_address.startswith('UQ') or escrow_address.startswith('EQ')):
                structured_logger.error(
                    f"Invalid TON escrow address format: {escrow_address}",
                    category=LogCategory.ESCROW,
                    context=context,
                    operation="create_escrow_transaction"
                )
                return False, "Invalid TON escrow address"

            structured_logger.info(
                f"Escrow address validated for deal {deal_code}",
                category=LogCategory.ESCROW,
                context=context,
                operation="create_escrow_transaction"
            )

            return True, None
            
        except ValueError as e:
            structured_logger.warning(
                f"Validation error in escrow creation: {e}",
                category=LogCategory.ESCROW,
                context=context,
                operation="create_escrow_transaction"
            )
            return False, f"Invalid parameters: {e}"
            
        except Exception as e:
            structured_logger.error(
                f"Error creating escrow transaction: {e}",
                category=LogCategory.ESCROW,
                context=context,
                operation="create_escrow_transaction",
                exception=e
            )
            return False, "Escrow creation failed"

    @log_operation("release_escrow", LogCategory.BLOCKCHAIN)
    def release_escrow(self, deal_code: str, seller_address: str,
                      amount: float, currency: str) -> Tuple[bool, Optional[str]]:
        """Enhanced escrow release with comprehensive error handling"""
        context = create_log_context(
            service="blockchain_processor",
            operation="release_escrow",
            custom_fields={
                'deal_code': deal_code,
                'seller_address': seller_address[:10] + "..." if len(seller_address) > 10 else seller_address,
                'amount': amount,
                'currency': currency
            }
        )
        
        try:
            structured_logger.info(
                f"Releasing escrow for deal {deal_code}",
                category=LogCategory.ESCROW,
                context=context,
                operation="release_escrow"
            )
            
            # Input validation
            if not deal_code or not isinstance(deal_code, str):
                raise ValueError("Invalid deal code")
            
            if seller_address is not None and (not isinstance(seller_address, str) or not seller_address.strip()):
                raise ValueError("Invalid seller address")
            
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise ValueError("Invalid amount")
            
            if currency.upper() not in ['USDT', 'TON']:
                raise ValueError(f"Unsupported currency: {currency}")

            memo = f"RELEASE-{deal_code}"
            success, tx_hash = self.send_funds(
                to_address=seller_address,
                amount=amount,
                currency=currency,
                memo=memo,
            )

            if not success:
                structured_logger.error(
                    f"Escrow release failed for deal {deal_code}",
                    category=LogCategory.ESCROW,
                    context=context,
                    operation="release_escrow"
                )
                return False, "Escrow release failed"

            structured_logger.info(
                f"Escrow released successfully for deal {deal_code}: {tx_hash}",
                category=LogCategory.ESCROW,
                context=context,
                operation="release_escrow",
                tx_hash=tx_hash,
                amount=amount,
                currency=currency,
                seller_address=seller_address[:10] + "..."
            )

            return True, tx_hash
            
        except ValueError as e:
            structured_logger.warning(
                f"Validation error in escrow release: {e}",
                category=LogCategory.ESCROW,
                context=context,
                operation="release_escrow"
            )
            return False, f"Invalid parameters: {e}"
            
        except Exception as e:
            structured_logger.error(
                f"Error releasing escrow: {e}",
                category=LogCategory.ESCROW,
                context=context,
                operation="release_escrow",
                exception=e
            )
            return False, "Escrow release failed"

    def send_funds(
        self,
        to_address: str,
        amount: float,
        currency: str,
        private_key: Optional[str] = None,
        memo: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Send funds from the system wallet to a recipient address."""
        try:
            from .config import (
                USDT_PRIVATE_KEY,
                TON_PRIVATE_KEY,
                USDT_WALLET_ADDRESS,
                TON_WALLET_ADDRESS,
                USDT_SYSTEM_ADDRESS,
                TON_SYSTEM_ADDRESS,
            )

            currency_upper = str(currency).upper()
            if currency_upper not in ("USDT", "TON"):
                structured_logger.error(
                    f"Unsupported currency for sending: {currency}",
                    category=LogCategory.ERROR,
                    operation="send_funds",
                    currency=currency,
                )
                return False, None

            if currency_upper == "USDT":
                from_address = USDT_SYSTEM_ADDRESS or USDT_WALLET_ADDRESS
                private_key = private_key or USDT_PRIVATE_KEY
                if not from_address or not private_key:
                    structured_logger.error(
                        "USDT wallet private key or address not configured",
                        category=LogCategory.SECURITY,
                        operation="send_funds",
                    )
                    return False, None
                return self._send_usdt_trc20(from_address, to_address, float(amount), private_key)

            from_address = TON_SYSTEM_ADDRESS or TON_WALLET_ADDRESS
            private_key = private_key or TON_PRIVATE_KEY
            if not from_address or not private_key:
                structured_logger.error(
                    "TON wallet private key or address not configured",
                    category=LogCategory.SECURITY,
                    operation="send_funds",
                )
                return False, None
            return self._send_ton(from_address, to_address, float(amount), private_key, memo=memo)

        except Exception as e:
            structured_logger.error(
                f"Error sending funds: {e}",
                category=LogCategory.ERROR,
                operation="send_funds",
                exception=e,
            )
            return False, None

    def _send_usdt_trc20(
        self, from_address: str, to_address: str, amount: float, private_key: str
    ) -> Tuple[bool, Optional[str]]:
        """Send USDT (TRC20) via tronpy if available."""
        try:
            try:
                import tronpy  # type: ignore
                from tronpy.keys import PrivateKey  # type: ignore
                from tronpy.providers.http import HTTPProvider  # type: ignore
            except Exception as e:
                structured_logger.error(
                    f"tronpy is not available: {e}",
                    category=LogCategory.ERROR,
                    operation="_send_usdt_trc20",
                    exception=e,
                )
                return False, None

            provider = HTTPProvider(api_key=self.api_keys.get("USDT")) if self.api_keys.get("USDT") else HTTPProvider()
            client = tronpy.Tron(provider=provider)

            key = (private_key or "").strip()
            if key.startswith("0x"):
                key = key[2:]

            try:
                if len(key) == 64:
                    priv_key = PrivateKey(bytes.fromhex(key))
                else:
                    priv_key = PrivateKey(bytes.fromhex(key))
            except Exception as key_error:
                structured_logger.error(
                    f"Error loading TRON private key: {key_error}",
                    category=LogCategory.ERROR,
                    operation="_send_usdt_trc20",
                    exception=key_error,
                )
                return False, None

            usdt_contract = client.get_contract("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
            amount_sun = int(float(amount) * 1_000_000)

            txn = (
                usdt_contract.functions.transfer(to_address, amount_sun)
                .with_owner(from_address)
                .fee_limit(100_000_000)
                .build()
                .sign(priv_key)
            )

            result = txn.broadcast()
            if result.get("result"):
                tx_hash = result.get("txid")
                structured_logger.info(
                    f"USDT transaction sent: {tx_hash}",
                    category=LogCategory.BLOCKCHAIN,
                    operation="_send_usdt_trc20",
                    tx_hash=tx_hash,
                )
                return True, tx_hash

            structured_logger.error(
                f"Failed to broadcast USDT transaction: {result}",
                category=LogCategory.ERROR,
                operation="_send_usdt_trc20",
            )
            return False, None

        except Exception as e:
            structured_logger.error(
                f"Error sending USDT: {e}",
                category=LogCategory.ERROR,
                operation="_send_usdt_trc20",
                exception=e,
            )
            return False, None

    def _send_ton(
        self,
        from_address: str,
        to_address: str,
        amount: float,
        private_key: str,
        memo: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Send TON transaction using tonsdk and TonCenter sendBoc."""
        try:
            import base64
            from decimal import Decimal
            from nacl.signing import SigningKey  # type: ignore
            from tonsdk.contract.wallet import Wallets, WalletVersionEnum  # type: ignore
            from tonsdk.utils import Address  # type: ignore

            amount_nano = int(Decimal(str(amount)) * Decimal("1000000000"))
            if amount_nano <= 0:
                structured_logger.error(
                    "TON amount must be positive",
                    category=LogCategory.ERROR,
                    operation="_send_ton",
                )
                return False, None

            key_pair = self._parse_ton_keypair(private_key, SigningKey)
            if not key_pair:
                return False, None

            public_key, secret_key = key_pair
            from_address_obj = Address(from_address)

            configured_wallet_version = os.getenv("TON_WALLET_VERSION", "v3r2").lower()
            candidate_versions = []
            if configured_wallet_version in {v.value for v in WalletVersionEnum}:
                candidate_versions.append(configured_wallet_version)
            candidate_versions.extend([v.value for v in WalletVersionEnum if v.value not in candidate_versions])

            wallet = None
            matched_version = None
            for version in candidate_versions:
                try:
                    wallet_cls = Wallets.ALL[WalletVersionEnum(version)]
                    candidate_wallet = wallet_cls(public_key=public_key, private_key=secret_key, wc=from_address_obj.wc)
                except Exception:
                    continue
                if candidate_wallet.address.hash_part == from_address_obj.hash_part:
                    wallet = candidate_wallet
                    matched_version = version
                    break

            if wallet is None:
                structured_logger.error(
                    f"TON private key does not match wallet address (tried versions: {', '.join(candidate_versions)})",
                    category=LogCategory.SECURITY,
                    operation="_send_ton",
                )
                return False, None

            if matched_version and matched_version != configured_wallet_version:
                structured_logger.info(
                    f"Auto-detected TON wallet version {matched_version} for configured address (overrides TON_WALLET_VERSION={configured_wallet_version})",
                    category=LogCategory.BLOCKCHAIN,
                    operation="_send_ton",
                )

            seqno, balance, is_uninitialized = self._get_ton_wallet_info(from_address)
            if balance is not None and balance < amount_nano:
                structured_logger.error(
                    f"Insufficient TON balance: {balance} nanotons, need {amount_nano} nanotons",
                    category=LogCategory.ERROR,
                    operation="_send_ton",
                )
                return False, None

            state_init = None
            if is_uninitialized:
                try:
                    state_init = wallet.create_state_init().get("state_init")
                    structured_logger.info(
                        "TON wallet is uninitialized; sending with state_init to deploy on first transfer",
                        category=LogCategory.BLOCKCHAIN,
                        operation="_send_ton",
                    )
                except Exception as e:
                    structured_logger.error(
                        f"Failed to build TON wallet state_init: {e}",
                        category=LogCategory.ERROR,
                        operation="_send_ton",
                        exception=e,
                    )
                    return False, None

            transfer = wallet.create_transfer_message(
                to_addr=to_address,
                amount=amount_nano,
                seqno=seqno,
                payload=memo or None,
                state_init=state_init,
            )

            # TonCenter is picky about BOC index tables in some environments.
            # Prefer BOC without index (has_idx=0) and fall back to default if needed.
            try:
                boc = transfer["message"].to_boc(False)
            except TypeError:
                boc = transfer["message"].to_boc()
            boc_b64 = base64.b64encode(boc).decode("utf-8")

            params = {"api_key": self.api_keys.get("TON")} if self.api_keys.get("TON") else {}
            endpoint_candidates = ["sendBocReturnHash", "sendBoc"]
            last_error = None
            tx_hash = None

            for endpoint in endpoint_candidates:
                send_url = f"{self.system_wallets['TON']['api_url']}/{endpoint}"
                response = requests.post(send_url, params=params, json={"boc": boc_b64}, timeout=15)

                if response.status_code != 200:
                    # Some TonCenter deployments do not support sendBocReturnHash.
                    body_preview = (response.text or "")[:200]
                    if endpoint == "sendBocReturnHash" and (
                        response.status_code == 404 or "method not found" in body_preview.lower()
                    ):
                        continue
                    last_error = f"{response.status_code} {body_preview}"
                    break

                data = response.json()
                if not data.get("ok", False):
                    if endpoint == "sendBocReturnHash":
                        # Fall back if not supported.
                        message_text = str(data.get("error") or data)[:200].lower()
                        if "method not found" in message_text or "not found" in message_text:
                            continue
                    last_error = str(data)[:200]
                    break

                result = data.get("result")
                if isinstance(result, str):
                    tx_hash = result
                elif isinstance(result, dict):
                    tx_hash = (
                        result.get("hash")
                        or result.get("message_hash")
                        or result.get("transaction_id")
                        or result.get("tx_hash")
                    )

                # We consider it a success even if TonCenter doesn't return a hash (sendBoc).
                break

            if last_error is not None:
                structured_logger.error(
                    f"TON send failed: {last_error}",
                    category=LogCategory.ERROR,
                    operation="_send_ton",
                )
                return False, None

            structured_logger.info(
                f"TON transaction sent: {tx_hash or 'unknown'}",
                category=LogCategory.BLOCKCHAIN,
                operation="_send_ton",
                tx_hash=tx_hash,
            )
            return True, tx_hash

        except Exception as e:
            structured_logger.error(
                f"Error sending TON: {e}",
                category=LogCategory.ERROR,
                operation="_send_ton",
                exception=e,
            )
            return False, None

    def _parse_ton_keypair(self, private_key: str, signing_key_cls) -> Optional[Tuple[bytes, bytes]]:
        """Parse TON private key into (public_key, secret_key) bytes."""
        if not private_key:
            structured_logger.error(
                "TON private key not provided",
                category=LogCategory.SECURITY,
                operation="_parse_ton_keypair",
            )
            return None

        key = private_key.strip()
        if key.startswith("0x"):
            key = key[2:]

        key_bytes = None
        try:
            key_bytes = bytes.fromhex(key)
        except ValueError:
            try:
                import base64

                key_bytes = base64.b64decode(key)
            except Exception:
                structured_logger.error(
                    "TON private key must be hex or base64",
                    category=LogCategory.SECURITY,
                    operation="_parse_ton_keypair",
                )
                return None

        if len(key_bytes) == 64:
            secret_key = key_bytes
            public_key = key_bytes[32:]
            return public_key, secret_key

        if len(key_bytes) == 32:
            signing_key = signing_key_cls(key_bytes)
            public_key = signing_key.verify_key.encode()
            secret_key = signing_key.encode() + public_key
            return public_key, secret_key

        structured_logger.error(
            "Unsupported TON private key length",
            category=LogCategory.SECURITY,
            operation="_parse_ton_keypair",
            key_length=len(key_bytes),
        )
        return None

    def _get_ton_wallet_info(self, address: str) -> Tuple[int, Optional[int], bool]:
        """Fetch TON wallet seqno and balance from TonCenter."""
        try:
            url = f"{self.system_wallets['TON']['api_url']}/getWalletInformation"
            params = {"address": address}
            if self.api_keys.get("TON"):
                params["api_key"] = self.api_keys["TON"]

            response = requests.get(url, params=params, timeout=15)
            if response.status_code != 200:
                structured_logger.warning(
                    f"TON wallet info error: {response.status_code}",
                    category=LogCategory.BLOCKCHAIN,
                    operation="_get_ton_wallet_info",
                )
                return 0, None, False

            data = response.json()
            result = data.get("result", {}) if isinstance(data, dict) else {}
            seqno = int(result.get("seqno") or 0)
            balance_raw = result.get("balance")
            balance = int(balance_raw) if balance_raw is not None else None
            account_state = str(result.get("account_state") or "").lower()
            is_wallet = result.get("wallet")
            is_uninitialized = (account_state == "uninitialized") or (is_wallet is False)
            return seqno, balance, is_uninitialized
        except Exception as e:
            structured_logger.warning(
                f"TON wallet info failed: {e}",
                category=LogCategory.BLOCKCHAIN,
                operation="_get_ton_wallet_info",
                exception=e,
            )
            return 0, None, False


class EnhancedQRCodeGenerator:
    """Enhanced QR code generator with comprehensive error handling and fallbacks"""
    
    def __init__(self, qr_codes_dir: str = "static/qr_codes"):
        self.qr_codes_dir = qr_codes_dir
        
        # Ensure directory exists
        os.makedirs(self.qr_codes_dir, exist_ok=True)
        
        # QR code style configurations
        self.qr_styles = {
            'standard': {
                'version': 1,
                'error_correction': qrcode.constants.ERROR_CORRECT_L,
                'box_size': 10,
                'border': 4,
                'fill_color': 'black',
                'back_color': 'white'
            },
            'branded': {
                'version': 1,
                'error_correction': qrcode.constants.ERROR_CORRECT_H,
                'box_size': 10,
                'border': 4,
                'fill_color': '#1a1a1a',
                'back_color': 'white'
            },
            'mini': {
                'version': 1,
                'error_correction': qrcode.constants.ERROR_CORRECT_M,
                'box_size': 6,
                'border': 2,
                'fill_color': 'black',
                'back_color': 'white'
            }
        }
        
        structured_logger.info(
            "Enhanced QR code generator initialized",
            category=LogCategory.SYSTEM,
            operation="initialization",
            qr_dir=self.qr_codes_dir
        )

    @handle_errors(
        fallback_on_error=True
    )
    @log_operation("generate_payment_qr", LogCategory.SYSTEM)
    def generate_payment_qr(self, checkout_id: str, address: str, amount: float,
                           currency: str, format_type: str = "all",
                           memo: Optional[str] = None) -> Dict[str, str]:
        """Enhanced QR code generation with comprehensive error handling"""
        context = create_log_context(
            service="qr_generator",
            operation="generate_payment_qr",
            custom_fields={
                'checkout_id': checkout_id,
                'address': address[:10] + "..." if len(address) > 10 else address,
                'amount': amount,
                'currency': currency,
                'format_type': format_type
            }
        )
        
        try:
            # Input validation
            if not checkout_id or not isinstance(checkout_id, str):
                raise ValueError("Invalid checkout ID")
            
            if not address or not isinstance(address, str):
                raise ValueError("Invalid address")
            
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise ValueError("Invalid amount")
            
            if currency.upper() not in ['USDT', 'TON']:
                raise ValueError(f"Unsupported currency: {currency}")

            structured_logger.info(
                f"Generating QR codes for checkout {checkout_id}",
                category=LogCategory.SYSTEM,
                context=context,
                operation="generate_payment_qr"
            )
            
            # Create payment URI
            payment_uri = self._create_payment_uri(address, amount, currency, checkout_id, memo)
            
            qr_codes = {}
            formats_to_generate = []
            
            # Determine which formats to generate
            if format_type == "all":
                formats_to_generate = ["standard", "branded", "mini", "base64"]
            elif isinstance(format_type, str):
                formats_to_generate = [format_type]
            elif isinstance(format_type, list):
                formats_to_generate = format_type
            else:
                formats_to_generate = ["standard"]  # Default fallback

            # Generate QR codes for each format
            for format_name in formats_to_generate:
                try:
                    structured_logger.debug(
                        f"Generating {format_name} QR code",
                        category=LogCategory.SYSTEM,
                        context=context,
                        operation="generate_payment_qr",
                        format_type=format_name
                    )
                    
                    if format_name == "base64":
                        qr_codes[format_name] = self._generate_base64_qr(payment_uri)
                    else:
                        qr_codes[format_name] = self._generate_qr_format(
                            format_name, checkout_id, payment_uri
                        )
                        
                except Exception as format_error:
                    structured_logger.warning(
                        f"Error generating {format_name} QR code: {format_error}",
                        category=LogCategory.SYSTEM,
                        context=context,
                        operation="generate_payment_qr",
                        format_type=format_name,
                        exception=format_error
                    )
                    
                    # Continue with other formats even if one fails
                    continue

            # Check if any QR codes were generated successfully
            if not qr_codes:
                structured_logger.error(
                    f"No QR codes generated for checkout {checkout_id}",
                    category=LogCategory.ERROR,
                    context=context,
                    operation="generate_payment_qr"
                )
                return {}
            
            structured_logger.info(
                f"QR codes generated successfully for {checkout_id}: {list(qr_codes.keys())}",
                category=LogCategory.SYSTEM,
                context=context,
                operation="generate_payment_qr",
                generated_formats=list(qr_codes.keys())
            )
            
            return qr_codes

        except ValueError as e:
            structured_logger.warning(
                f"Validation error generating QR codes: {e}",
                category=LogCategory.SYSTEM,
                context=context,
                operation="generate_payment_qr"
            )
            return {}
            
        except Exception as e:
            structured_logger.error(
                f"Unexpected error generating QR codes: {e}",
                category=LogCategory.ERROR,
                context=context,
                operation="generate_payment_qr",
                exception=e
            )
            return {}

    @log_operation("_create_payment_uri", LogCategory.SYSTEM)
    def _create_payment_uri(self, address: str, amount: float, currency: str,
                            checkout_id: str, memo: Optional[str] = None) -> str:
        """Enhanced payment URI creation with validation"""
        try:
            if currency.upper() == 'USDT':
                memo_value = memo or f"DEAL-{checkout_id}"
                return f"tron://transfer?to={address}&amount={amount}&token=USDT&memo={memo_value}"
            elif currency.upper() == 'TON':
                text_value = memo or f"Payment-{checkout_id}"
                return f"ton://transfer/{address}?amount={amount}&text={text_value}"
            else:
                # Fallback - just return the address
                return address
                
        except Exception as e:
            structured_logger.warning(
                f"Error creating payment URI: {e}",
                category=LogCategory.SYSTEM,
                operation="_create_payment_uri",
                exception=e
            )
            # Return simple address as fallback
            return address

    @log_operation("_generate_qr_format", LogCategory.SYSTEM)
    def _generate_qr_format(self, format_name: str, checkout_id: str, uri: str) -> str:
        """Generate QR code for a specific format"""
        try:
            if format_name not in self.qr_styles:
                raise ValueError(f"Unknown QR format: {format_name}")
            
            style_config = self.qr_styles[format_name]
            
            # Create QR code
            qr = qrcode.QRCode(
                version=style_config['version'],
                error_correction=style_config['error_correction'],
                box_size=style_config['box_size'],
                border=style_config['border'],
            )
            qr.add_data(uri)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(
                fill_color=style_config['fill_color'],
                back_color=style_config['back_color']
            )
            
            # Add branding for branded format
            if format_name == "branded":
                img = self._add_branding(img)
            
            # Save file
            filename = f"{checkout_id}_{format_name}.png"
            filepath = os.path.join(self.qr_codes_dir, filename)
            img.save(filepath)
            
            return filepath
            
        except Exception as e:
            structured_logger.error(
                f"Error generating {format_name} QR code: {e}",
                category=LogCategory.SYSTEM,
                operation="_generate_qr_format",
                exception=e,
                format_type=format_name
            )
            raise

    @log_operation("_add_branding", LogCategory.SYSTEM)
    def _add_branding(self, img: Image.Image) -> Image.Image:
        """Add Black Diamond branding to QR code"""
        try:
            img = img.convert('RGB')
            draw = ImageDraw.Draw(img)
            
            try:
                font = ImageFont.truetype("arial.ttf", 12)
            except:
                font = ImageFont.load_default()
            
            # Add branding text
            text = "Black Diamond"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            img_width, img_height = img.size
            text_x = (img_width - text_width) // 2
            text_y = img_height - text_height - 5
            
            draw.text((text_x, text_y), text, fill="#666666", font=font)
            
            return img
            
        except Exception as e:
            structured_logger.warning(
                f"Error adding branding to QR code: {e}",
                category=LogCategory.SYSTEM,
                operation="_add_branding",
                exception=e
            )
            return img  # Return unbranded image as fallback

    @log_operation("_generate_base64_qr", LogCategory.SYSTEM)
    def _generate_base64_qr(self, uri: str) -> str:
        """Generate QR code as base64 string"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=8,
                border=2,
            )
            qr.add_data(uri)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return f"data:image/png;base64,{img_base64}"
            
        except Exception as e:
            structured_logger.error(
                f"Error generating base64 QR code: {e}",
                category=LogCategory.SYSTEM,
                operation="_generate_base64_qr",
                exception=e
            )
            # Return empty string as fallback
            return ""

    @log_operation("get_qr_code_urls", LogCategory.SYSTEM)
    def get_qr_code_urls(self, checkout_id: str, qr_codes: Dict[str, str]) -> Dict[str, str]:
        """Get URLs for generated QR codes with error handling"""
        try:
            urls = {}
            for format_type, filepath in qr_codes.items():
                try:
                    if format_type != 'base64' and filepath and os.path.exists(filepath):
                        filename = os.path.basename(filepath)
                        urls[format_type] = f"/static/qr_codes/{filename}"
                    elif format_type == 'base64':
                        urls[format_type] = filepath  # Already a data URL
                except Exception as format_error:
                    structured_logger.warning(
                        f"Error getting URL for {format_type} QR code: {format_error}",
                        category=LogCategory.SYSTEM,
                        operation="get_qr_code_urls",
                        exception=format_error,
                        format_type=format_type
                    )
                    continue
            
            structured_logger.debug(
                f"QR code URLs generated for {checkout_id}: {list(urls.keys())}",
                category=LogCategory.SYSTEM,
                operation="get_qr_code_urls"
            )
            
            return urls
            
        except Exception as e:
            structured_logger.error(
                f"Error getting QR code URLs: {e}",
                category=LogCategory.ERROR,
                operation="get_qr_code_urls",
                exception=e
            )
            return {}


class EnhancedDecentralizedPaymentProcessor:
    """Enhanced decentralized payment processor with comprehensive error handling"""
    
    def __init__(self):
        self.blockchain = EnhancedBlockchainProcessor()
        self.qr_generator = EnhancedQRCodeGenerator()
        self.commission_rate = COMMISSION_RATE
        
        structured_logger.info(
            "Enhanced decentralized payment processor initialized",
            category=LogCategory.SYSTEM,
            operation="initialization"
        )

    @handle_errors(
        fallback_on_error=True
    )
    @log_operation("generate_checkout_id", LogCategory.PAYMENT)
    def generate_checkout_id(self) -> str:
        """Generate unique checkout ID with validation"""
        try:
            chars = string.ascii_uppercase + string.digits
            checkout_id = f"BD-{''.join(random.choice(chars) for _ in range(8))}"
            
            structured_logger.debug(
                f"Generated checkout ID: {checkout_id}",
                category=LogCategory.PAYMENT,
                operation="generate_checkout_id"
            )
            
            return checkout_id
            
        except Exception as e:
            structured_logger.error(
                f"Error generating checkout ID: {e}",
                category=LogCategory.ERROR,
                operation="generate_checkout_id",
                exception=e
            )
            # Return fallback ID
            return f"BD-{int(time.time())}"

    @handle_errors(
        fallback_on_error=True
    )
    @log_operation("create_payment", LogCategory.PAYMENT)
    def create_payment(self, deal_code: str, amount: float, currency: str,
                      buyer_address: str, seller_address: str) -> Optional[Dict]:
        """Enhanced payment creation with comprehensive error handling"""
        context = create_log_context(
            service="payment_processor",
            custom_fields={
                'deal_code': deal_code,
                'amount': amount,
                'currency': currency,
                'buyer_address': buyer_address[:10] + "..." if buyer_address and isinstance(buyer_address, str) and len(buyer_address) > 10 else buyer_address,
                'seller_address': seller_address[:10] + "..." if seller_address and isinstance(seller_address, str) and len(seller_address) > 10 else seller_address
            }
        )
        
        try:
            structured_logger.info(
                f"Creating decentralized payment for deal {deal_code}",
                category=LogCategory.PAYMENT,
                context=context,
                operation="create_payment"
            )
            
            # Input validation
            if not deal_code or not isinstance(deal_code, str):
                raise ValueError("Invalid deal code")
            
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise ValueError("Invalid amount")
            
            if currency.upper() not in ['USDT', 'TON']:
                raise ValueError(f"Unsupported currency: {currency}")
            
            if not buyer_address or not isinstance(buyer_address, str):
                raise ValueError("Invalid buyer address")

            if seller_address is not None and (not isinstance(seller_address, str) or not seller_address.strip()):
                raise ValueError("Invalid seller address")
            
            # Generate checkout ID
            checkout_id = self.generate_checkout_id()

            # Generate unique memo for this deal
            payment_memo = self.blockchain.generate_deal_memo(deal_code)

            # Get system escrow address
            escrow_address = self.blockchain.system_wallets[currency.upper()]['address']

            # Create escrow transaction
            success, escrow_tx = self.blockchain.create_escrow_transaction(
                deal_code, buyer_address, amount, currency
            )

            if not success:
                structured_logger.error(
                    f"Failed to create escrow for deal {deal_code}",
                    category=LogCategory.ESCROW,
                    context=context,
                    operation="create_payment"
                )
                return None

            # Generate QR codes with fallback
            qr_codes = self.qr_generator.generate_payment_qr(
                checkout_id, escrow_address, amount, currency, format_type="all", memo=payment_memo
            )

            if not qr_codes:
                structured_logger.warning(
                    f"QR code generation failed for {checkout_id}, continuing without QR codes",
                    category=LogCategory.SYSTEM,
                    context=context,
                    operation="create_payment"
                )
                qr_codes = {}
            
            qr_urls = self.qr_generator.get_qr_code_urls(checkout_id, qr_codes)

            # Calculate commission
            commission_amount = round(amount * self.commission_rate, 8)
            seller_amount = round(amount - commission_amount, 8)

            # Save to database
            expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

            try:
                success = db.create_decentralized_payment(
                    deal_code=deal_code,
                    escrow_address=escrow_address,
                    amount=amount,
                    currency=currency,
                    payment_memo=payment_memo,
                    qr_code=qr_codes.get('standard', ''),
                    status='pending',
                    checkout_id=checkout_id,
                    created_at=datetime.now().isoformat(),
                    expires_at=expires_at
                )

                if not success:
                    structured_logger.error(
                        f"Failed to save decentralized payment for {deal_code}",
                        category=LogCategory.DATABASE,
                        context=context,
                        operation="create_payment"
                    )
                    return None
                    
            except Exception as db_error:
                structured_logger.error(
                    f"Database error saving payment: {db_error}",
                    category=LogCategory.DATABASE,
                    context=context,
                    operation="create_payment",
                    exception=db_error
                )
                return None

            structured_logger.info(
                f"Decentralized payment created successfully: {checkout_id}",
                category=LogCategory.PAYMENT,
                context=context,
                operation="create_payment",
                checkout_id=checkout_id,
                escrow_tx=escrow_tx
            )

            return {
                'checkout_id': checkout_id,
                'deal_code': deal_code,
                'escrow_address': escrow_address,
                'payment_memo': payment_memo,
                'amount': amount,
                'currency': currency,
                'commission_amount': commission_amount,
                'seller_amount': seller_amount,
                'qr_codes': qr_urls,
                'qr_code_base64': qr_codes.get('base64', ''),
                'expires_at': expires_at,
                'status': 'pending',
                'blockchain_tx': escrow_tx
            }

        except ValueError as e:
            structured_logger.warning(
                f"Validation error creating payment: {e}",
                category=LogCategory.PAYMENT,
                context=context,
                operation="create_payment"
            )
            return None
            
        except Exception as e:
            structured_logger.error(
                f"Unexpected error creating payment: {e}",
                category=LogCategory.ERROR,
                context=context,
                operation="create_payment",
                exception=e
            )
            return None

    @handle_errors(
        fallback_on_error=True
    )
    @log_operation("check_payment_status", LogCategory.PAYMENT)
    def check_payment_status(self, checkout_id: str, user_id: int = None) -> Tuple[bool, str]:
        """Enhanced payment status check with comprehensive error handling"""
        context = create_log_context(
            service="payment_processor",
            operation="check_payment_status",
            custom_fields={
                'checkout_id': checkout_id,
                'user_id': user_id
            }
        )

        try:
            structured_logger.debug(
                f"Checking payment status for {checkout_id}",
                category=LogCategory.PAYMENT,
                context=context,
                operation="check_payment_status"
            )

            # Get checkout information
            checkout = self.get_checkout(checkout_id)
            if not checkout:
                structured_logger.warning(
                    f"Checkout not found: {checkout_id}",
                    category=LogCategory.PAYMENT,
                    context=context,
                    operation="check_payment_status"
                )
                return False, "Checkout not found"

            # ADMIN BYPASS: If user is admin, skip blockchain verification and mark as paid
            from shared.constants import ADMIN_ID
            if user_id and user_id == ADMIN_ID:
                structured_logger.info(
                    f"ADMIN BYPASS: Payment confirmed for {checkout_id} without blockchain verification",
                    category=LogCategory.PAYMENT,
                    context=context,
                    operation="check_payment_status",
                    admin_id=user_id
                )

                # Update payment status
                try:
                    updated = db.update_decentralized_payment_status(
                        checkout['deal_code'], 'confirmed', 'ADMIN_CONFIRMED'
                    )
                    if not updated:
                        db.update_checkout_status(checkout_id, 'confirmed', 'ADMIN_CONFIRMED')

                    try:
                        deal = db.get_deal(str(checkout.get('deal_code', '')).upper())
                        if deal and deal.get('status') in ('active', 'pending'):
                            db.update_deal_status(
                                checkout['deal_code'],
                                'funded',
                                payment_confirmed_at=datetime.now().isoformat(),
                            )
                    except Exception:
                        pass
                    structured_logger.info(
                        f"Admin payment confirmed for {checkout_id}",
                        category=LogCategory.PAYMENT,
                        context=context,
                        operation="check_payment_status",
                        tx_hash='ADMIN_CONFIRMED'
                    )
                except Exception as db_error:
                    structured_logger.warning(
                        f"Database update failed for admin payment: {db_error}",
                        category=LogCategory.DATABASE,
                        context=context,
                        operation="check_payment_status",
                        exception=db_error
                    )

                return True, "Payment confirmed by admin (no blockchain verification)"

            # Check blockchain for payment
            try:
                is_paid, tx_hash = self.blockchain.check_incoming_payment(
                    checkout['escrow_address'],
                    checkout['amount'],
                    checkout['currency'],
                    checkout.get('payment_memo')
                )

                if is_paid:
                    # Update payment status
                    try:
                        updated = db.update_decentralized_payment_status(
                            checkout['deal_code'], 'confirmed', tx_hash
                        )
                        if not updated:
                            db.update_checkout_status(checkout_id, 'confirmed', tx_hash)

                        try:
                            deal = db.get_deal(str(checkout.get('deal_code', '')).upper())
                            if deal and deal.get('status') in ('active', 'pending'):
                                db.update_deal_status(
                                    checkout['deal_code'],
                                    'funded',
                                    payment_confirmed_at=datetime.now().isoformat(),
                                )
                        except Exception:
                            pass
                        structured_logger.info(
                            f"Payment confirmed for {checkout_id}: {tx_hash[:10]}...",
                            category=LogCategory.PAYMENT,
                            context=context,
                            operation="check_payment_status",
                            tx_hash=tx_hash
                        )
                    except Exception as db_error:
                        structured_logger.warning(
                            f"Database update failed but payment confirmed: {db_error}",
                            category=LogCategory.DATABASE,
                            context=context,
                            operation="check_payment_status",
                            exception=db_error
                        )

                    return True, f"Payment confirmed (TX: {tx_hash[:10]}...)"
                else:
                    structured_logger.debug(
                        f"Payment not received yet for {checkout_id}",
                        category=LogCategory.PAYMENT,
                        context=context,
                        operation="check_payment_status"
                    )
                    return False, "Payment not received yet"

            except Exception as blockchain_error:
                structured_logger.warning(
                    f"Blockchain check failed for {checkout_id}: {blockchain_error}",
                    category=LogCategory.BLOCKCHAIN,
                    context=context,
                    operation="check_payment_status",
                    exception=blockchain_error
                )

                # Return graceful degradation response
                return False, "Payment check temporarily unavailable"

        except Exception as e:
            structured_logger.error(
                f"Error checking payment status for {checkout_id}: {e}",
                category=LogCategory.ERROR,
                context=context,
                operation="check_payment_status",
                exception=e
            )
            return False, "Status check failed"

    @log_operation("get_checkout", LogCategory.PAYMENT)
    def get_checkout(self, checkout_id: str) -> Optional[Dict]:
        """Enhanced checkout retrieval with error handling"""
        try:
            # Try to get from decentralized payments table
            try:
                payment = db.get_decentralized_payment_by_checkout(checkout_id)
                if payment:
                    return dict(payment)
            except Exception as db_error:
                structured_logger.warning(
                    f"Error retrieving decentralized payment for {checkout_id}: {db_error}",
                    category=LogCategory.DATABASE,
                    operation="get_checkout",
                    exception=db_error
                )

            # Fallback to regular crypto checkout
            try:
                checkout = db.get_crypto_checkout(checkout_id)
                if checkout:
                    return dict(checkout)
            except Exception as db_error:
                structured_logger.warning(
                    f"Error retrieving crypto checkout for {checkout_id}: {db_error}",
                    category=LogCategory.DATABASE,
                    operation="get_checkout",
                    exception=db_error
                )

            structured_logger.warning(
                f"Checkout not found: {checkout_id}",
                category=LogCategory.PAYMENT,
                operation="get_checkout"
            )
            
            return None

        except Exception as e:
            structured_logger.error(
                f"Unexpected error getting checkout {checkout_id}: {e}",
                category=LogCategory.ERROR,
                operation="get_checkout",
                exception=e
            )
            return None


# Global instances (canonical names)
qr_code_generator = EnhancedQRCodeGenerator()
decentralized_payment_processor = EnhancedDecentralizedPaymentProcessor()

# Backwards-compatible aliases (keep while older code is still around)
enhanced_qr_code_generator = qr_code_generator
enhanced_decentralized_payment_processor = decentralized_payment_processor

# Public, non-"enhanced" type aliases
BlockchainProcessor = EnhancedBlockchainProcessor
DecentralizedPaymentProcessor = EnhancedDecentralizedPaymentProcessor
QRCodeGenerator = EnhancedQRCodeGenerator

__all__ = [
    "BlockchainProcessor",
    "DecentralizedPaymentProcessor",
    "QRCodeGenerator",
    "decentralized_payment_processor",
    "qr_code_generator",
    "enhanced_decentralized_payment_processor",
    "enhanced_qr_code_generator",
]

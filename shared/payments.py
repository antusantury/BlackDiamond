from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from .database import db
from .decentralized_payments import decentralized_payment_processor

logger = logging.getLogger(__name__)


def _normalize_checkout(checkout: Dict) -> Dict:
    """Normalize checkout dict to a stable shape for bot/web consumers."""
    normalized = dict(checkout)

    escrow_address = normalized.get("escrow_address")
    if escrow_address and not normalized.get("wallet_address"):
        normalized["wallet_address"] = escrow_address
    if escrow_address and not normalized.get("address"):
        normalized["address"] = escrow_address

    qr_code = normalized.get("qr_code")
    if qr_code and not normalized.get("qr_code_path"):
        normalized["qr_code_path"] = qr_code

    return normalized


class SystemWalletCheckout:
    """
    Checkout read/check wrapper used by the web app.

    Despite the name, this supports both legacy `crypto_checkouts` and newer `decentralized_payments`
    records (by `checkout_id`).
    """

    def get_checkout(self, checkout_id: str) -> Optional[Dict]:
        try:
            checkout = decentralized_payment_processor.get_checkout(checkout_id)
            if checkout:
                return _normalize_checkout(checkout)
        except Exception as e:
            logger.warning(f"get_checkout failed for {checkout_id}: {e}")

        # Fallback to legacy table directly
        try:
            checkout = db.get_crypto_checkout(checkout_id)
            return _normalize_checkout(checkout) if checkout else None
        except Exception as e:
            logger.error(f"Legacy checkout lookup failed for {checkout_id}: {e}")
            return None

    def get_checkout_by_deal(self, deal_code: str) -> Optional[Dict]:
        deal_code = (deal_code or "").strip().upper()
        if not deal_code:
            return None

        try:
            checkout = db.get_decentralized_payment_by_deal_code(deal_code)
            if checkout:
                return _normalize_checkout(checkout)
        except Exception:
            pass

        try:
            checkout = db.get_crypto_checkout_by_deal(deal_code)
            return _normalize_checkout(checkout) if checkout else None
        except Exception:
            return None

    def check_payment_status(self, checkout_id: str) -> Tuple[bool, str]:
        try:
            return decentralized_payment_processor.check_payment_status(checkout_id)
        except Exception as e:
            logger.error(f"check_payment_status failed for {checkout_id}: {e}")
            return False, "Status check failed"


class PaymentProcessor:
    """High-level payment operations used by bot/web and the actor system."""

    def process_deal_payment(
        self,
        deal_code: str,
        amount: float,
        currency: str,
        description: str | None = None,
    ) -> Optional[Dict]:
        deal_code = (deal_code or "").strip().upper()
        if not deal_code:
            return None

        # Reuse existing checkout if present to avoid duplicates.
        try:
            existing = db.get_decentralized_payment_by_deal_code(deal_code)
            if existing and existing.get("checkout_id"):
                return _normalize_checkout(existing)
        except Exception:
            pass

        try:
            checkout = decentralized_payment_processor.create_payment(
                deal_code=deal_code,
                amount=float(amount),
                currency=str(currency).upper(),
                buyer_address=f"buyer_{deal_code}",
                seller_address=f"seller_{deal_code}",
            )
            return _normalize_checkout(checkout) if checkout else None
        except Exception as e:
            logger.error(f"process_deal_payment failed for {deal_code}: {e}")
            return None

    # Backwards-compatible alias used by `shared/actor_system.py`.
    def process_payment(self, deal_code: str, amount: float, currency: str) -> Optional[Dict]:
        return self.process_deal_payment(deal_code=deal_code, amount=amount, currency=currency)

    def check_deal_payment(self, deal_code: str) -> Tuple[bool, str]:
        deal_code = (deal_code or "").strip().upper()
        if not deal_code:
            return False, "Deal code required"

        checkout_id: Optional[str] = None
        try:
            existing = db.get_decentralized_payment_by_deal_code(deal_code)
            checkout_id = (existing or {}).get("checkout_id")
        except Exception:
            checkout_id = None

        if not checkout_id:
            try:
                legacy_checkout = db.get_crypto_checkout_by_deal(deal_code)
                checkout_id = (legacy_checkout or {}).get("checkout_id")
            except Exception:
                checkout_id = None

        if not checkout_id:
            return False, "Payment not found"

        return system_wallet_checkout.check_payment_status(checkout_id)


system_wallet_checkout = SystemWalletCheckout()
payment_processor = PaymentProcessor()

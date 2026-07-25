from typing import Tuple

from shared.constants import DEFAULT_COMMISSION_RATE
from shared.database import db


def get_commission_rate() -> float:
    try:
        settings = db.get_settings()
    except Exception:
        return DEFAULT_COMMISSION_RATE

    try:
        rate = settings.get("commission_rate", DEFAULT_COMMISSION_RATE)
        return float(rate)
    except (TypeError, ValueError):
        return DEFAULT_COMMISSION_RATE


def get_commission_breakdown(amount: float) -> Tuple[float, float, float]:
    rate = get_commission_rate()
    commission_amount = amount * rate
    seller_amount = amount - commission_amount
    return rate, commission_amount, seller_amount


def format_commission_percent(rate: float) -> str:
    percent = rate * 100
    text = f"{percent:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"

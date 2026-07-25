import asyncio
import concurrent.futures
import logging
import threading
import time
from typing import Optional

from shared.exchange_rates import exchange_rate_fetcher
from shared.secure_exchange_rates import secure_exchange_rate_fetcher

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_RATE_CACHE = {"TON_USD": {"rate": None, "timestamp": 0.0}}
_CACHE_LOCK = threading.Lock()
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def _fetch_ton_usdt_rate_sync(timeout: float = 10.0) -> Optional[float]:
    def _run() -> Optional[float]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                secure_exchange_rate_fetcher.get_ton_usdt_rate()
            )
        finally:
            loop.close()

    future = _EXECUTOR.submit(_run)
    return future.result(timeout=timeout)


def get_ton_usd_rate() -> float:
    now = time.time()
    with _CACHE_LOCK:
        cached = _RATE_CACHE["TON_USD"]
        if cached["rate"] and now - cached["timestamp"] < _CACHE_TTL_SECONDS:
            return cached["rate"]

    cached_rate = exchange_rate_fetcher.get_cached_rate("TON_USDT")
    if cached_rate:
        with _CACHE_LOCK:
            _RATE_CACHE["TON_USD"] = {"rate": cached_rate, "timestamp": now}
        return cached_rate

    rate = None
    try:
        rate = _fetch_ton_usdt_rate_sync()
    except Exception as exc:
        logger.warning("Failed to fetch TON/USD rate: %s", exc)

    if rate:
        with _CACHE_LOCK:
            _RATE_CACHE["TON_USD"] = {"rate": rate, "timestamp": now}
        return rate

    with _CACHE_LOCK:
        if _RATE_CACHE["TON_USD"]["rate"]:
            return _RATE_CACHE["TON_USD"]["rate"]

    return 3.16


def convert_amount_to_usd(amount: Optional[float], currency: Optional[str]) -> float:
    if amount is None:
        return 0.0

    code = (currency or "").upper()
    if code in {"USD", "USDT"}:
        return float(amount)
    if code == "TON":
        return float(amount) * get_ton_usd_rate()

    logger.warning("Unknown currency for USD conversion: %s", code)
    return float(amount)

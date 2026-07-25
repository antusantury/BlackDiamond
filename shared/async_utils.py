from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


def fire_and_forget(coro: Coroutine[Any, Any, Any]) -> None:
    """
    Run a coroutine without awaiting it.

    - If we're already inside a running event loop, schedule it via create_task().
    - Otherwise (typical for sync Flask handlers), run it in a background daemon thread
      with its own event loop via asyncio.run().
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        threading.Thread(target=_run_in_new_loop, args=(coro,), daemon=True).start()
        return

    loop.create_task(coro)


def _run_in_new_loop(coro: Coroutine[Any, Any, Any]) -> None:
    try:
        asyncio.run(coro)
    except Exception as e:
        # Best-effort background execution: ensure failures are visible in logs.
        try:
            logger.exception("fire_and_forget coroutine failed: %s", e)
        except Exception:
            pass
    finally:
        try:
            coro.close()
        except Exception:
            pass

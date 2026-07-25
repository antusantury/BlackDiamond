import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


class QRCodeCleanupService:
    def __init__(self, qr_dir: str = "static/qr_codes",
                 cleanup_interval_seconds: int = 3600,
                 ttl_seconds: int = 86400):
        self.qr_dir = qr_dir
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.ttl_seconds = ttl_seconds
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("QR code cleanup service started")

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("QR code cleanup service stopped")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.cleanup()
            except Exception as e:
                logger.warning(f"QR code cleanup failed: {e}")
            self._stop_event.wait(self.cleanup_interval_seconds)

    def cleanup(self):
        if not os.path.isdir(self.qr_dir):
            return

        cutoff = time.time() - self.ttl_seconds
        deleted = 0

        for entry in os.scandir(self.qr_dir):
            if not entry.is_file():
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    os.remove(entry.path)
                    deleted += 1
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.debug(f"Failed to delete {entry.path}: {e}")

        if deleted:
            logger.info(f"QR code cleanup removed {deleted} file(s)")


qr_code_cleanup_service = QRCodeCleanupService()

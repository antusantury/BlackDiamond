import os
import time
import logging
import platform
from pathlib import Path
from threading import Lock
try:
    import msvcrt  # Windows-only
except ImportError:  # pragma: no cover
    msvcrt = None

logger = logging.getLogger(__name__)

class BotLock:
    """Bot lock mechanism to prevent multiple instances"""
    
    def __init__(self, lock_dir: str = None):
        self.lock_dir = Path(lock_dir) if lock_dir else Path(__file__).parent / "locks"
        self.lock_file = None
        self.lock_fd = None
        self._lock = Lock()  # Thread-safe lock
        
    def __enter__(self):
        return self.acquire()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        
    def acquire(self, timeout: int = 10) -> bool:
        """
        Acquire bot lock
        
        Args:
            timeout: Maximum seconds to wait for lock
            
        Returns:
            bool: True if lock acquired, False otherwise
        """
        with self._lock:  # Thread-safe acquisition
            try:
                # Create lock directory if it doesn't exist
                self.lock_dir.mkdir(exist_ok=True)
                
                # Create lock file path
                lock_file_path = self.lock_dir / "bot.lock"
                
                # Try to create and lock the file
                self.lock_fd = open(lock_file_path, 'w')
                
                # Try to acquire exclusive lock with timeout
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        # Platform-specific file locking
                        if platform.system() == 'Windows':
                            # Windows file locking
                            try:
                                if msvcrt is None:
                                    raise RuntimeError("msvcrt is not available on this platform")
                                msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                            except (IOError, OSError):
                                raise IOError("Lock already held")
                        else:
                            # Unix/Linux file locking using portalocker
                            try:
                                import fcntl
                                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except ImportError:
                                # Fallback to simple file check if fcntl not available
                                pass
                        
                        # Write PID to file
                        self.lock_fd.write(str(os.getpid()))
                        self.lock_fd.flush()
                        
                        self.lock_file = lock_file_path
                        logger.info(f"Bot lock acquired successfully (PID: {os.getpid()})")
                        return True
                        
                    except (IOError, OSError):
                        # Lock is held by another process, check if it's still alive
                        if self._is_lock_stale(lock_file_path):
                            logger.warning("Removing stale bot lock")
                            self._remove_stale_lock(lock_file_path)
                            # Close and reopen file after removing stale lock
                            if self.lock_fd:
                                try:
                                    self.lock_fd.close()
                                except:
                                    pass
                                self.lock_fd = open(lock_file_path, 'w')
                        else:
                            logger.info("Waiting for bot lock to be released...")
                            time.sleep(1)
                
                logger.error("Failed to acquire bot lock within timeout")
                return False
                
            except Exception as e:
                logger.error(f"Error acquiring bot lock: {e}")
                return False
    
    def release(self):
        """Release bot lock"""
        with self._lock:  # Thread-safe release
            try:
                if self.lock_fd:
                    # Platform-specific lock release
                    if platform.system() == 'Windows':
                        try:
                            if msvcrt is None:
                                raise RuntimeError("msvcrt is not available on this platform")
                            msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                        except (IOError, OSError):
                            pass
                    else:
                        try:
                            import fcntl
                            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                        except ImportError:
                            pass
                    
                    self.lock_fd.close()
                    self.lock_fd = None
                
                if self.lock_file and self.lock_file.exists():
                    try:
                        self.lock_file.unlink()
                        logger.info("Bot lock released successfully")
                    except PermissionError:
                        logger.warning("Could not remove lock file (may be in use)")
                    
            except Exception as e:
                logger.error(f"Error releasing bot lock: {e}")
    
    def _is_lock_stale(self, lock_file_path: Path) -> bool:
        """Check if lock file is stale (process no longer exists)"""
        try:
            if not lock_file_path.exists():
                return True
                
            with open(lock_file_path, 'r') as f:
                pid = int(f.read().strip())
                
            # Check if process exists
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return False
            except OSError:
                # Process doesn't exist, lock is stale
                return True
                
        except (ValueError, FileNotFoundError, OSError):
            return True
    
    def _remove_stale_lock(self, lock_file_path: Path):
        """Remove stale lock file"""
        try:
            if lock_file_path.exists():
                # Close any open file handles before removing
                try:
                    lock_file_path.unlink()
                    logger.info("Stale bot lock removed")
                except PermissionError:
                    # File is still locked, try to close the handle
                    if self.lock_fd:
                        try:
                            self.lock_fd.close()
                            self.lock_fd = None
                        except:
                            pass
                    # Retry removal after closing handles
                    lock_file_path.unlink()
                    logger.info("Stale bot lock removed after closing handles")
        except Exception as e:
            logger.error(f"Error removing stale lock: {e}")
    
    @staticmethod
    def check_bot_status() -> dict:
        """
        Check if bot is currently running
        
        Returns:
            dict: Status information
        """
        try:
            lock_dir = Path(__file__).parent / "locks"
            lock_file_path = lock_dir / "bot.lock"
            
            if not lock_file_path.exists():
                return {"running": False, "message": "No lock file found"}
            
            with open(lock_file_path, 'r') as f:
                try:
                    pid = int(f.read().strip())
                except ValueError:
                    return {"running": False, "message": "Invalid lock file"}
            
            # Check if process exists
            try:
                os.kill(pid, 0)
                return {
                    "running": True, 
                    "pid": pid, 
                    "message": f"Bot is running with PID {pid}"
                }
            except OSError:
                return {
                    "running": False, 
                    "message": f"Lock file exists but process {pid} not found (stale)"
                }
                
        except Exception as e:
            return {"running": False, "message": f"Error checking bot status: {e}"}

# Global lock instance
_bot_lock = None

def acquire_bot_lock(timeout: int = 10) -> bool:
    """Acquire bot lock"""
    global _bot_lock
    _bot_lock = BotLock()
    return _bot_lock.acquire(timeout)

def release_bot_lock():
    """Release bot lock"""
    global _bot_lock
    if _bot_lock:
        _bot_lock.release()
        _bot_lock = None

def get_bot_status() -> dict:
    """Get bot status"""
    return BotLock.check_bot_status()

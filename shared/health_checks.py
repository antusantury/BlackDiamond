import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import psutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from shared.config import DATABASE_URL
from shared.logging_system import structured_logger, LogCategory

logger = logging.getLogger(__name__)


class HealthCheck:
    """Base class for a health check."""

    def __init__(self, name: str, description: str = "", timeout: float = 5.0):
        self.name = name
        self.description = description or f"Health check for {name}"
        self.timeout = timeout
        self.last_check = None
        self.last_result = None
        self.last_error = None

    async def check(self) -> Dict[str, Any]:
        """Run the health check."""
        start_time = time.time()

        try:
            # Apply timeout
            result = await asyncio.wait_for(
                self._perform_check(),
                timeout=self.timeout
            )

            execution_time = time.time() - start_time
            self.last_check = datetime.now(timezone.utc)
            self.last_result = result
            self.last_error = None

            return {
                'name': self.name,
                'status': result.get('status', 'unknown'),
                'message': result.get('message', ''),
                'execution_time': round(execution_time, 3),
                'timestamp': self.last_check.isoformat(),
                'details': result.get('details', {})
            }

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            error_msg = f"Health check timeout after {self.timeout}s"
            self._record_error(error_msg)

            return {
                'name': self.name,
                'status': 'timeout',
                'message': error_msg,
                'execution_time': round(execution_time, 3),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'details': {}
            }

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Health check failed: {str(e)}"
            self._record_error(error_msg)

            return {
                'name': self.name,
                'status': 'error',
                'message': error_msg,
                'execution_time': round(execution_time, 3),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'details': {'error': str(e)}
            }

    async def _perform_check(self) -> Dict[str, Any]:
        """Implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _perform_check")

    def _record_error(self, error_msg: str):
        """Record an error."""
        self.last_error = error_msg
        self.last_check = datetime.now(timezone.utc)

        structured_logger.error(
            f"Health check failed: {self.name}",
            category=LogCategory.SYSTEM,
            operation="health_check",
            service=self.name,
            error=error_msg
        )


class DatabaseHealthCheck(HealthCheck):
    """Database health check."""

    def __init__(self):
        super().__init__(
            name="database",
            description="SQLite database connectivity and performance check"
        )
        self.db_path = DATABASE_URL.replace('sqlite:///', '')

    async def _perform_check(self) -> Dict[str, Any]:
        def db_check():
            try:
                # Check connectivity
                conn = sqlite3.connect(self.db_path, timeout=5.0)
                cursor = conn.cursor()

                # Check core tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]

                required_tables = ['users', 'deals', 'crypto_checkouts', 'payments']
                missing_tables = [t for t in required_tables if t not in tables]

                if missing_tables:
                    return {
                        'status': 'warning',
                        'message': f'Missing tables: {", ".join(missing_tables)}',
                        'details': {'missing_tables': missing_tables, 'existing_tables': tables}
                    }

                # Check row counts
                cursor.execute("SELECT COUNT(*) FROM users")
                users_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM deals WHERE status = 'active'")
                active_deals = cursor.fetchone()[0]

                # Check WAL mode
                cursor.execute("PRAGMA journal_mode")
                journal_mode = cursor.fetchone()[0]

                conn.close()

                return {
                    'status': 'healthy' if users_count >= 0 else 'warning',
                    'message': f'Database healthy. Users: {users_count}, Active deals: {active_deals}, WAL mode: {journal_mode}',
                    'details': {
                        'users_count': users_count,
                        'active_deals': active_deals,
                        'journal_mode': journal_mode,
                        'tables_count': len(tables)
                    }
                }

            except Exception as e:
                raise Exception(f"Database check failed: {str(e)}")

        # Run in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(executor, db_check)

        return result


class SystemHealthCheck(HealthCheck):
    """System health check."""

    def __init__(self):
        super().__init__(
            name="system",
            description="System resources and performance check"
        )

    async def _perform_check(self) -> Dict[str, Any]:
        def system_check():
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)

                # Memory
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                memory_used_gb = round(memory.used / (1024**3), 2)
                memory_total_gb = round(memory.total / (1024**3), 2)

                # Disk
                disk = psutil.disk_usage('/')
                disk_percent = disk.percent
                disk_free_gb = round(disk.free / (1024**3), 2)

                # System load
                load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None

                details = {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory_percent,
                    'memory_used_gb': memory_used_gb,
                    'memory_total_gb': memory_total_gb,
                    'disk_percent': disk_percent,
                    'disk_free_gb': disk_free_gb,
                    'load_average': load_avg
                }

                # Determine status
                if cpu_percent > 90 or memory_percent > 90 or disk_percent > 95:
                    status = 'critical'
                    message = 'System resources critically high'
                elif cpu_percent > 80 or memory_percent > 80 or disk_percent > 90:
                    status = 'warning'
                    message = 'System resources high'
                else:
                    status = 'healthy'
                    message = 'System resources normal'

                return {
                    'status': status,
                    'message': message,
                    'details': details
                }

            except Exception as e:
                raise Exception(f"System check failed: {str(e)}")

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(executor, system_check)

        return result


class NetworkHealthCheck(HealthCheck):
    """Network health check."""

    def __init__(self):
        super().__init__(
            name="network",
            description="Network connectivity check"
        )

    async def _perform_check(self) -> Dict[str, Any]:
        import socket
        import requests

        try:
            # Check DNS resolution
            dns_start = time.time()
            socket.gethostbyname('google.com')
            dns_time = time.time() - dns_start

            # Check HTTP connectivity
            http_start = time.time()
            response = requests.get('https://httpbin.org/status/200', timeout=5)
            http_time = time.time() - http_start

            if response.status_code == 200:
                return {
                    'status': 'healthy',
                    'message': 'Network connectivity OK',
                    'details': {
                        'dns_resolution_time': round(dns_time, 3),
                        'http_response_time': round(http_time, 3),
                        'http_status': response.status_code
                    }
                }
            else:
                return {
                    'status': 'warning',
                    'message': f'HTTP check failed with status {response.status_code}',
                    'details': {
                        'dns_resolution_time': round(dns_time, 3),
                        'http_response_time': round(http_time, 3),
                        'http_status': response.status_code
                    }
                }

        except socket.gaierror:
            return {
                'status': 'error',
                'message': 'DNS resolution failed',
                'details': {}
            }
        except requests.exceptions.RequestException as e:
            return {
                'status': 'error',
                'message': f'HTTP request failed: {str(e)}',
                'details': {}
            }
        except Exception as e:
            raise Exception(f"Network check failed: {str(e)}")


class BotHealthCheck(HealthCheck):
    """Telegram bot health check."""

    def __init__(self):
        super().__init__(
            name="telegram_bot",
            description="Telegram bot connectivity check"
        )

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            from shared.config import BOT_TOKEN
            import aiohttp

            if not BOT_TOKEN:
                return {
                    'status': 'error',
                    'message': 'Bot token not configured',
                    'details': {}
                }

            # Check Telegram API
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/getMe',
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            bot_info = data.get('result', {})
                            return {
                                'status': 'healthy',
                                'message': f'Bot @{bot_info.get("username", "unknown")} is operational',
                                'details': {
                                    'bot_id': bot_info.get('id'),
                                    'username': bot_info.get('username'),
                                    'first_name': bot_info.get('first_name')
                                }
                            }
                        else:
                            return {
                                'status': 'error',
                                'message': 'Bot API returned error',
                                'details': data
                            }
                    else:
                        return {
                            'status': 'error',
                            'message': f'Bot API returned HTTP {response.status}',
                            'details': {'http_status': response.status}
                        }

        except Exception as e:
            raise Exception(f"Bot health check failed: {str(e)}")


class WebHealthCheck(HealthCheck):
    """Web application health check."""

    def __init__(self, web_host: str = None, web_port: int = None):
        super().__init__(
            name="web_application",
            description="Web application health check"
        )

        if web_host is None or web_port is None:
            try:
                from shared.config import WEB_HOST, WEB_PORT
            except Exception:
                WEB_HOST = "localhost"
                WEB_PORT = 5000

            host = WEB_HOST if web_host is None else web_host
            port = WEB_PORT if web_port is None else web_port
        else:
            host = web_host
            port = web_port

        if not host or host == "0.0.0.0":
            host = "localhost"

        self.web_host = host
        self.web_port = port

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            import aiohttp

            urls = [
                f"http://{self.web_host}:{self.web_port}/health",
                f"http://{self.web_host}:{self.web_port}/api/stats"
            ]

            async with aiohttp.ClientSession() as session:
                for url in urls:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            data = await response.json()
                            return {
                                'status': 'healthy',
                                'message': 'Web application responding',
                                'details': {
                                    'response_time': round(time.time() - time.time(), 3),  # Will be overridden
                                    'stats_available': bool(data)
                                }
                            }

                        if response.status in (404, 405):
                            continue

                        return {
                            'status': 'error',
                            'message': f'Web app returned HTTP {response.status}',
                            'details': {'http_status': response.status}
                        }

            return {
                'status': 'error',
                'message': 'Web app health endpoint not found',
                'details': {}
            }

        except aiohttp.ClientError as e:
            return {
                'status': 'error',
                'message': f'Web app connection failed: {str(e)}',
                'details': {}
            }
        except Exception as e:
            raise Exception(f"Web health check failed: {str(e)}")


class BlockchainHealthCheck(HealthCheck):
    """Blockchain integration health check."""

    def __init__(self):
        super().__init__(
            name="blockchain",
            description="Blockchain API connectivity check"
        )

    async def _perform_check(self) -> Dict[str, Any]:
        try:
            from shared.config import (
                TRONGRID_API_KEY, TONCENTER_API_KEY,
                USDT_SYSTEM_ADDRESS, TON_SYSTEM_ADDRESS,
                ENABLED_CURRENCIES
            )
            import aiohttp

            results = {}
            tron_address = (USDT_SYSTEM_ADDRESS or 'T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuW9').strip()
            ton_address = (TON_SYSTEM_ADDRESS or 'UQBK3pY3rjY6mKv9k7KF8h8unkKHxuW9').strip()
            enabled = set(ENABLED_CURRENCIES)

            # Check TronGrid API
            if 'USDT' in enabled and TRONGRID_API_KEY:
                try:
                    async with aiohttp.ClientSession() as session:
                        headers = {'TRON-PRO-API-KEY': TRONGRID_API_KEY}
                        async with session.get(
                            f'https://api.trongrid.io/v1/accounts/{tron_address}',
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            results['tron'] = response.status == 200
                except Exception:
                    results['tron'] = False
            else:
                results['tron'] = None  # Not configured

            # Check TonCenter API
            if 'TON' in enabled and TONCENTER_API_KEY:
                try:
                    async with aiohttp.ClientSession() as session:
                        headers = {'X-API-Key': TONCENTER_API_KEY}
                        async with session.get(
                            f'https://toncenter.com/api/v2/getAddressInformation?address={ton_address}',
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            results['ton'] = response.status == 200
                except Exception:
                    results['ton'] = False
            else:
                results['ton'] = None  # Not configured

            # Determine status
            working_apis = sum(1 for v in results.values() if v is True)
            total_apis = sum(1 for v in results.values() if v is not None)

            if working_apis == total_apis and total_apis > 0:
                status = 'healthy'
                message = f'All blockchain APIs working ({working_apis}/{total_apis})'
            elif working_apis > 0:
                status = 'warning'
                message = f'Some blockchain APIs working ({working_apis}/{total_apis})'
            else:
                status = 'error'
                message = 'No blockchain APIs available'

            return {
                'status': status,
                'message': message,
                'details': results
            }

        except Exception as e:
            raise Exception(f"Blockchain health check failed: {str(e)}")


class HealthChecker:
    """Main class for running health checks."""

    def __init__(self):
        self.checks: Dict[str, HealthCheck] = {}
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="health_check")
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Register default checks
        self.register_check(DatabaseHealthCheck())
        self.register_check(SystemHealthCheck())
        self.register_check(NetworkHealthCheck())
        self.register_check(BotHealthCheck())
        self.register_check(WebHealthCheck())
        self.register_check(BlockchainHealthCheck())

    def register_check(self, check: HealthCheck):
        """Register a health check."""
        self.checks[check.name] = check
        logger.info(f"Registered health check: {check.name}")

    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        start_time = time.time()

        # Run checks in parallel
        tasks = [check.check() for check in self.checks.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        execution_time = time.time() - start_time

        # Process results
        checks_results = {}
        summary = {
            'total_checks': len(self.checks),
            'healthy': 0,
            'warning': 0,
            'error': 0,
            'timeout': 0,
            'execution_time': round(execution_time, 3),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        for i, result in enumerate(results):
            check_name = list(self.checks.keys())[i]

            if isinstance(result, Exception):
                # Exception handling
                checks_results[check_name] = {
                    'name': check_name,
                    'status': 'error',
                    'message': f'Check execution failed: {str(result)}',
                    'execution_time': 0,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'details': {}
                }
                summary['error'] += 1
            else:
                checks_results[check_name] = result
                summary[result['status']] += 1

        # Determine overall system status
        if summary['error'] > 0:
            overall_status = 'error'
        elif summary['warning'] > 0:
            overall_status = 'warning'
        else:
            overall_status = 'healthy'

        summary['overall_status'] = overall_status

        return {
            'summary': summary,
            'checks': checks_results
        }

    async def run_check(self, check_name: str) -> Optional[Dict[str, Any]]:
        """Run a specific check."""
        if check_name not in self.checks:
            return None

        return await self.checks[check_name].check()

    def get_registered_checks(self) -> List[str]:
        """Return the list of registered checks."""
        return list(self.checks.keys())

    async def start_monitoring(self, interval: int = 60):
        """Start background monitoring."""
        if self._running:
            return

        self._running = True

        async def monitoring_loop():
            while self._running:
                try:
                    results = await self.run_all_checks()

                    # Log problems
                    if results['summary']['overall_status'] != 'healthy':
                        structured_logger.warning(
                            f"Health check issues detected: {results['summary']}",
                            category=LogCategory.SYSTEM,
                            operation="health_monitoring",
                            health_status=results['summary']['overall_status'],
                            error_count=results['summary']['error'],
                            warning_count=results['summary']['warning']
                        )

                    await asyncio.sleep(interval)

                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
                    await asyncio.sleep(interval)

        self._task = asyncio.create_task(monitoring_loop())
        logger.info(f"Health monitoring started with {interval}s interval")

    async def stop_monitoring(self):
        """Stop monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitoring stopped")

    def get_check_status(self, check_name: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific check."""
        if check_name not in self.checks:
            return None

        check = self.checks[check_name]
        return {
            'name': check.name,
            'description': check.description,
            'last_check': check.last_check.isoformat() if check.last_check else None,
            'last_result': check.last_result,
            'last_error': check.last_error
        }


# Global health checker instance
health_checker = HealthChecker()


async def run_health_checks():
    """Run all health checks."""
    return await health_checker.run_all_checks()


async def get_health_status():
    """Get the current system health status."""
    return await health_checker.run_all_checks()


def start_health_monitoring(interval: int = 60):
    """Start health monitoring."""
    try:
        # Try to get the current event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Create and start the monitoring task
        task = loop.create_task(health_checker.start_monitoring(interval))
        logger.info(f"Health monitoring task created with {interval}s interval")
        return task
    except Exception as e:
        logger.warning(f"Failed to start health monitoring: {e}")
        return None


def stop_health_monitoring():
    """Stop health monitoring."""
    asyncio.create_task(health_checker.stop_monitoring())

# API endpoints for health checks
async def health_endpoint():
    """Endpoint for health checks."""
    try:
        results = await run_health_checks()
        status_code = 200 if results['summary']['overall_status'] == 'healthy' else 503
        return results, status_code
    except Exception as e:
        logger.error(f"Health endpoint error: {e}")
        return {
            'summary': {'overall_status': 'error', 'error': str(e)},
            'checks': {}
        }, 503


async def detailed_health_endpoint():
    """Detailed endpoint for health checks."""
    try:
        results = await run_health_checks()

        # Add extra metrics
        results['system_info'] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'version': '1.0.0',
            'environment': 'production'
        }

        return results, 200
    except Exception as e:
        logger.error(f"Detailed health endpoint error: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }, 503

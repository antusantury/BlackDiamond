import asyncio
import logging
import os
import sys
from typing import Optional

from aiogram import Bot, Dispatcher
try:
    from aiogram.exceptions import TelegramAPIError
except ImportError:
    # Fallback for older aiogram versions
    try:
        from aiogram.utils.exceptions import TelegramAPIError
    except ImportError:
        # If neither works, use base Exception
        TelegramAPIError = Exception

from shared.config import BOT_TOKEN, LOG_LEVEL, validate_config
from shared.logging_system import setup_logging
from bot.handlers.unified_handler import register_all_handlers
from bot.deal_integration import BotIntegration
from bot.platform_sync import init_bot_cross_platform_sync
from shared.database import db
from shared.notifications import notification_manager
from bot.bot_lock import acquire_bot_lock, release_bot_lock, get_bot_status

logger = logging.getLogger(__name__)

# Global bot instance for handlers
bot: Optional[Bot] = None


class BlackDiamondBot:
    """Main bot class with comprehensive initialization and lifecycle management."""

    def __init__(self):
        """Initialize bot with all components."""
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None
        self.integration: Optional[BotIntegration] = None

    async def initialize(self) -> bool:
        """
        Initialize all bot components.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("🚀 Starting Black Diamond Bot initialization...")

            # Validate configuration
            if not validate_config():
                logger.error("❌ Configuration validation failed")
                return False

            # Initialize bot instance
            self.bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
            global bot
            bot = self.bot

            # Create dispatcher with bot instance (aiogram 2.x expects positional bot arg)
            self.dispatcher = Dispatcher(self.bot)

            # Initialize notification manager with bot instance
            notification_manager.set_telegram_bot(self.bot)
            logger.info("🔔 Notification manager initialized with bot instance")

            # Setup middlewares
            await self._setup_middlewares()

            # Register global error handler (last line of defense)
            self._register_global_error_handler()

            # Register handlers
            await self._register_handlers()

            # Initialize integration system
            await self._initialize_integration()

            # Initialize cross-platform sync
            await init_bot_cross_platform_sync()

            # Start exchange rate updater
            from shared.exchange_rate_updater import exchange_rate_updater
            await exchange_rate_updater.start_updater()
            from shared.qr_code_cleanup import qr_code_cleanup_service
            qr_code_cleanup_service.start()

            logger.info("✅ Bot initialization completed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Bot initialization failed: {e}")
            return False

    def _register_global_error_handler(self) -> None:
        """Register a global dispatcher error handler for uncaught exceptions."""
        if not self.dispatcher:
            return

        async def _errors_handler(update, exception):
            try:
                logger.critical(
                    "Unhandled exception in dispatcher",
                    exc_info=(type(exception), exception, exception.__traceback__),
                )
            except Exception:
                try:
                    logger.critical(f"Error in global error handler: {exception}")
                except Exception:
                    pass
            return True

        # aiogram 2.x API
        self.dispatcher.register_errors_handler(_errors_handler)

    async def _setup_middlewares(self):
        """Setup all middlewares for the bot."""
        try:
            # Security middleware (first in chain)
            from bot.middlewares import SecurityMiddleware
            security_middleware = SecurityMiddleware()
            self.dispatcher.middleware.setup(security_middleware)

            # Logging middleware
            from bot.middlewares import LoggingMiddleware
            logging_middleware = LoggingMiddleware()
            self.dispatcher.middleware.setup(logging_middleware)

            logger.info("🛡️ Middlewares setup completed")

        except Exception as e:
            logger.error(f"❌ Middlewares setup failed: {e}")
            raise

    async def _register_handlers(self):
        """Register all bot handlers."""
        try:
            await register_all_handlers(self.dispatcher)
            logger.info("🎯 Handlers registration completed")

        except Exception as e:
            logger.error(f"❌ Handlers registration failed: {e}")
            raise

    async def _initialize_integration(self):
        """Initialize system integration."""
        try:
            self.integration = BotIntegration()
            await self.integration.initialize()
            logger.info("🔗 System integration initialized")

        except Exception as e:
            logger.error(f"❌ System integration failed: {e}")
            raise

    async def start_polling(self):
        """Start bot polling with error handling."""
        if not self.bot or not self.dispatcher:
            logger.error("❌ Bot not properly initialized")
            return

        try:
            logger.info("🤖 Starting bot polling...")

            # Delete webhook if exists (for polling mode)
            await self.bot.delete_webhook(drop_pending_updates=True)

            # Start polling
            await self.dispatcher.start_polling(
                allowed_updates=["message", "callback_query", "inline_query", "chosen_inline_result"],
            )

        except TelegramAPIError as e:
            logger.error(f"❌ Telegram API error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Polling failed: {e}")
            raise

    async def start_webhook(self, webhook_url: str, webhook_path: str = "/webhook"):
        """Start bot with webhook mode."""
        if not self.bot or not self.dispatcher:
            logger.error("❌ Bot not properly initialized")
            return

        try:
            logger.info(f"🌐 Setting up webhook: {webhook_url}{webhook_path}")

            # Set webhook
            await self.bot.set_webhook(
                url=f"{webhook_url}{webhook_path}",
                allowed_updates=[
                    "message",
                    "callback_query",
                    "inline_query",
                    "chosen_inline_result"
                ],
                drop_pending_updates=True
            )

            logger.info("✅ Webhook setup completed")

        except Exception as e:
            logger.error(f"❌ Webhook setup failed: {e}")
            raise

    async def shutdown(self):
        """Gracefully shutdown bot and cleanup resources."""
        try:
            logger.info("🛑 Shutting down Black Diamond Bot...")

            # Stop exchange rate updater
            try:
                from shared.exchange_rate_updater import exchange_rate_updater
                await exchange_rate_updater.stop_updater()
            except Exception as e:
                logger.warning(f"Error stopping exchange rate updater: {e}")
            try:
                from shared.qr_code_cleanup import qr_code_cleanup_service
                qr_code_cleanup_service.stop()
            except Exception as e:
                logger.warning(f"Error stopping QR code cleanup: {e}")

            if self.integration:
                await self.integration.shutdown()

            if self.bot:
                await self.bot.session.close()

            logger.info("✅ Bot shutdown completed")

        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")

    async def health_check(self) -> dict:
        """
        Perform comprehensive health check.

        Returns:
            dict: Health status information
        """
        health_status = {
            "status": "healthy",
            "components": {},
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            # Check bot connectivity
            if self.bot:
                try:
                    bot_info = await self.bot.get_me()
                    health_status["components"]["bot"] = {
                        "status": "healthy",
                        "username": bot_info.username,
                        "id": bot_info.id
                    }
                except Exception as e:
                    health_status["components"]["bot"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
                    health_status["status"] = "degraded"

            # Check database connectivity
            try:
                stats = db.get_stats()
                health_status["components"]["database"] = {
                    "status": "healthy",
                    "stats": stats
                }
            except Exception as e:
                health_status["components"]["database"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health_status["status"] = "degraded"

            # Check integration system
            if self.integration:
                integration_health = await self.integration.health_check()
                health_status["components"]["integration"] = integration_health
                if integration_health.get("status") != "healthy":
                    health_status["status"] = "degraded"

            # Check exchange rate system
            try:
                from shared.exchange_rate_updater import exchange_rate_updater
                rate_status = exchange_rate_updater.get_status()
                health_status["components"]["exchange_rates"] = {
                    "status": "healthy" if rate_status.get("ton_usdt_rate") else "unhealthy",
                    "rate": rate_status.get("ton_usdt_rate"),
                    "age_seconds": rate_status.get("rate_age"),
                    "fresh": rate_status.get("rate_fresh")
                }
                if not rate_status.get("ton_usdt_rate"):
                    health_status["status"] = "degraded"
            except Exception as e:
                health_status["components"]["exchange_rates"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health_status["status"] = "degraded"

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)

        return health_status


async def main():
    """Main entry point for the bot."""
    # Setup logging
    setup_logging(log_level=LOG_LEVEL, log_dir=os.getenv("LOG_DIR", "logs"), service_name="bot")
    
    # Check if another bot instance is already running
    bot_status = get_bot_status()
    if bot_status.get("running"):
        logger.error(f"❌ Bot is already running: {bot_status['message']}")
        sys.exit(1)
    
    # Acquire bot lock to prevent multiple instances
    if not acquire_bot_lock(timeout=10):
        logger.error("❌ Failed to acquire bot lock - another instance may be starting")
        sys.exit(1)

    # Create bot instance
    bot_instance = BlackDiamondBot()

    try:
        # Initialize bot
        if not await bot_instance.initialize():
            logger.error("❌ Bot initialization failed")
            sys.exit(1)

        # Start bot (polling mode for development)
        await bot_instance.start_polling()

    except KeyboardInterrupt:
        logger.info("⚠️ Received shutdown signal")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        # Release bot lock and graceful shutdown
        release_bot_lock()
        await bot_instance.shutdown()


if __name__ == "__main__":
    # Run bot
    asyncio.run(main())

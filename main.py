"""
Main entry point for Antigravity Telegram Bridge.
Initializes the database, builds the Telegram bot application, and runs the polling loop.
"""

import asyncio
import logging
import signal
import sys
from config import settings
from database import db
from telegram_bot import build_application

# Configure structured logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("antigravity_bridge")


async def main():
    logger.info("==================================================")
    logger.info("Starting Antigravity Telegram Bridge Daemon...")
    logger.info(f"Workspace: {settings.DEFAULT_WORKSPACE}")
    logger.info(f"CLI Binary: {settings.AGY_BIN_PATH}")
    logger.info(f"Default Model: {settings.DEFAULT_MODEL}")
    logger.info(f"Database Path: {settings.DB_PATH}")
    logger.info("==================================================")

    # 1. Initialize SQLite Database
    await db.init()

    # 2. Build Telegram Application
    app = build_application()

    # 3. Setup lifecycle and polling
    await app.initialize()
    await app.start()
    
    bot_info = await app.bot.get_me()
    logger.info(f"Bot successfully authenticated as @{bot_info.username} (ID: {bot_info.id})")
    logger.info("Starting update poller...")

    await app.updater.start_polling(allowed_updates=["message", "callback_query"])

    # Graceful stop event
    stop_event = asyncio.Event()

    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        # Keep running until stop signal received
        while not stop_event.is_set():
            await asyncio.sleep(1)
    finally:
        logger.info("Stopping updater and bot application...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Antigravity Telegram Bridge stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)

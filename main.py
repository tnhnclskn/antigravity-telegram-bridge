"""
Main entry point for Antigravity Hub Bridge.
Coordinates SQLite database, FastAPI WebUI server, and Telegram Bot services.
Allows running Telegram, WebUI, or both concurrently based on .env configuration.
"""

import asyncio
import logging
import signal
import sys
import uvicorn
from config import settings
from database import db

# Configure structured logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("antigravity_hub")


async def main():
    logger.info("==================================================")
    logger.info("Starting Antigravity Hub Bridge Daemon...")
    logger.info(f"Workspace: {settings.DEFAULT_WORKSPACE}")
    logger.info(f"CLI Binary: {settings.AGY_BIN_PATH}")
    logger.info(f"Default Model: {settings.DEFAULT_MODEL}")
    logger.info(f"Database Path: {settings.DB_PATH}")
    logger.info(f"Services Enabled -> WebUI: {settings.ENABLE_WEBUI} (Port {settings.WEBUI_PORT}) | Telegram: {settings.ENABLE_TELEGRAM}")
    logger.info("==================================================")

    # 1. Initialize SQLite Database
    await db.init()

    tasks = []
    stop_event = asyncio.Event()

    # Graceful shutdown handler
    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # 2. Start WebUI Server if enabled
    web_server = None
    if settings.ENABLE_WEBUI:
        from web_server import app as fastapi_app
        config = uvicorn.Config(
            app=fastapi_app,
            host=settings.WEBUI_HOST,
            port=settings.WEBUI_PORT,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=False
        )
        web_server = uvicorn.Server(config=config)
        logger.info(f"Starting WebUI server on http://{settings.WEBUI_HOST}:{settings.WEBUI_PORT} ...")
        tasks.append(asyncio.create_task(web_server.serve()))

    # 3. Start Telegram Bot if enabled
    tg_app = None
    if settings.ENABLE_TELEGRAM:
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.error("ENABLE_TELEGRAM is True but TELEGRAM_BOT_TOKEN is not set in .env!")
        else:
            from telegram_bot import build_application
            tg_app = build_application()
            await tg_app.initialize()
            await tg_app.start()

            bot_info = await tg_app.bot.get_me()
            logger.info(f"Telegram Bot authenticated as @{bot_info.username} (ID: {bot_info.id})")
            logger.info("Starting Telegram update poller...")

            await tg_app.updater.start_polling(allowed_updates=["message", "callback_query"])

    if not settings.ENABLE_WEBUI and not settings.ENABLE_TELEGRAM:
        logger.warning("Neither WebUI nor Telegram is enabled! Please set ENABLE_WEBUI=true or ENABLE_TELEGRAM=true in .env")
        return

    try:
        # Wait until stop signal received
        while not stop_event.is_set():
            await asyncio.sleep(1)
    finally:
        logger.info("Initiating cleanup and stopping services...")

        # 1. Terminate all active agy CLI subprocesses
        from agy_client import agy_client
        agy_client.cancel_all()

        if web_server:
            logger.info("Stopping WebUI server...")
            web_server.should_exit = True

        if tg_app:
            logger.info("Stopping Telegram poller and bot application...")
            try:
                if tg_app.updater and tg_app.updater.running:
                    await tg_app.updater.stop()
                if tg_app.running:
                    await tg_app.stop()
                await tg_app.shutdown()
            except Exception as e:
                logger.warning(f"Error while shutting down Telegram app: {e}")

        # Cancel remaining background tasks
        for t in tasks:
            if not t.done():
                t.cancel()

        logger.info("Antigravity Hub Bridge stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)

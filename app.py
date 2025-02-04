import configparser
import os
import sys
import time
import asyncio
import logging
import signal

from handlers import EventHandler
from utils.structured_logging import get_structured_logger
from utils.logging_config import setup_logging, cleanup_logging

sys.stdout.reconfigure(encoding='utf-8')

config = configparser.ConfigParser()
config.read("config.ini")

async def init_logging():
    """Initialize logging system."""
    await setup_logging('mongobate')
    return get_structured_logger('mongobate.app')

async def shutdown(event_handler, signal=None):
    """Cleanup function for graceful shutdown."""
    if signal:
        logger.info("app.shutdown", 
                   message=f"Received exit signal {signal.name}")
    
    logger.info("app.shutdown", message="Shutting down application")
    
    # Stop the event handler
    event_handler.stop()
    
    # Cleanup logging
    await cleanup_logging()
    
    logger.info("app.shutdown.complete", message="Application has shut down")

def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    logger.error("app.error", 
                message="Caught exception in event loop",
                data={"error": str(msg)})

async def main():
    # Setup logging first
    global logger
    logger = await init_logging()
    
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)
    
    # For graceful shutdown
    signals = (signal.SIGTERM, signal.SIGINT)
    for s in signals:
        try:
            loop.add_signal_handler(
                s, 
                lambda s=s: asyncio.create_task(shutdown(event_handler, signal=s))
            )
        except NotImplementedError:
            # Windows doesn't support SIGTERM
            pass

    mongo_username = config.get("MongoDB", "username")
    mongo_password = config.get("MongoDB", "password")
    mongo_host = config.get("MongoDB", "host")
    mongo_port = config.getint("MongoDB", "port")
    mongo_db = config.get("MongoDB", "db")
    event_collection = config.get("MongoDB", "event_collection")
    user_collection = config.get("MongoDB", "user_collection")
    vip_refresh_interval = config.getint("General", "vip_refresh_interval")
    admin_refresh_interval = config.getint("General", "admin_refresh_interval")

    aws_key = (
        config.get("MongoDB", "aws_key")
        if len(config.get("MongoDB", "aws_key")) > 0
        else None
    )
    aws_secret = (
        config.get("MongoDB", "aws_secret")
        if len(config.get("MongoDB", "aws_secret")) > 0
        else None
    )

    logger.debug("app.init",
                message="Initializing event handler",
                data={
                    "mongo": {
                        "host": mongo_host,
                        "port": mongo_port,
                        "db": mongo_db,
                        "event_collection": event_collection,
                        "user_collection": user_collection
                    },
                    "intervals": {
                        "vip_refresh": vip_refresh_interval,
                        "admin_refresh": admin_refresh_interval
                    },
                    "aws_auth": bool(aws_key and aws_secret)
                })

    event_handler = EventHandler(
        mongo_username,
        mongo_password,
        mongo_host,
        mongo_port,
        mongo_db,
        event_collection,
        user_collection=user_collection,
        vip_refresh_interval=vip_refresh_interval,
        admin_refresh_interval=admin_refresh_interval,
        aws_key=aws_key,
        aws_secret=aws_secret
    )

    logger.info("app.start", message="Starting event handler")
    event_handler.run()

    try:
        # Keep the main task running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown(event_handler)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Handled by signal handlers

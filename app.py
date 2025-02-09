import configparser
import sys
import asyncio
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

async def shutdown():
    """Cleanup and shutdown the application."""
    try:
        # Disable logging after cleanup to prevent new messages during shutdown
        if event_handler:
            await event_handler.stop()
            
        # Now cleanup logging
        await cleanup_logging()
    except Exception as exc:
        logger.error("app.error",
                     message="Error during shutdown",
                     data={"error": str(exc)})


def handle_exception(loop, context):
    # Don't log if we're shutting down
    if not shutdown_event.is_set():
        msg = context.get("exception", context["message"])
        logger.error("app.error", 
                    message="Caught exception in event loop",
                    data={"error": str(msg)})

async def main():
    try:
        # Setup logging first
        global logger, event_handler, shutdown_event
        shutdown_event = asyncio.Event()  # Create this first so handle_exception can use it
        logger = await init_logging()
        
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(handle_exception)
        
        # For graceful shutdown
        signals = (signal.SIGTERM, signal.SIGINT)
        for s in signals:
            try:
                loop.add_signal_handler(
                    s, 
                    lambda s=s: shutdown_event.set()
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

        # Wait for shutdown signal
        await shutdown_event.wait()
        
    except Exception as exc:
        if not shutdown_event.is_set():
            logger.exception("app.error", exc=exc,
                            message="Application error")
        raise
    finally:
        # Always perform cleanup in the finally block
        try:
            logger.info("app.shutdown", message="Shutting down...")
            # Set shutdown event first to prevent new logs
            shutdown_event.set()
            # Small delay to allow any pending logs to complete
            await asyncio.sleep(0.1)
            if event_handler:

                await event_handler.stop()
            # Cleanup logging last
            await cleanup_logging()
        except Exception as exc:
            logger.error("app.error",
                         message="Error during shutdown",
                         data={"error": str(exc)})


if __name__ == '__main__':
    try:
        # Run main application
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Don't print anything, it's handled in main()
    except Exception as exc:
        logger.error("app.error",
                     message="Error in main",
                     data={"error": str(exc)})
    finally:
        pass  # Cleanup is handled in main()

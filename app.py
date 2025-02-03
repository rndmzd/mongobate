import configparser
import os
import sys
import time

from handlers import EventHandler
from utils.logging_config import setup_logging

sys.stdout.reconfigure(encoding='utf-8')

config = configparser.ConfigParser()
config.read("config.ini")

logger = setup_logging(component='app')

if __name__ == '__main__':
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

    logger.debug('Initializing event handler.')
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

    logger.debug('Running event handler.')
    event_handler.run()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        event_handler.stop()
    finally:
        logger.info("Application has shut down.")

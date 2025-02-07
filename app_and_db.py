import configparser
import os
import sys
import time
from multiprocessing import Event, Process

from handlers import DBHandler, EventHandler
from utils.structured_logging import get_structured_logger

sys.stdout.reconfigure(encoding='utf-8')

config = configparser.ConfigParser()
config.read("config.ini")

logger = get_structured_logger('mongobate.app_and_db')

if __name__ == '__main__':
    events_api_url = config.get("Events API", "url")
    requests_per_minute = config.getint(
        "Events API", "max_requests_per_minute")
    
    mongo_username = config.get("MongoDB", "username")
    mongo_password = config.get("MongoDB", "password")
    mongo_host = config.get("MongoDB", "host")
    mongo_port = config.getint("MongoDB", "port")
    mongo_db = config.get("MongoDB", "db")
    mongo_collection = config.get("MongoDB", "collection")

    logger.debug("app.db.init",
                message="Initializing database handler",
                data={
                    "api": {
                        "url": events_api_url,
                        "rate_limit": requests_per_minute
                    },
                    "mongo": {
                        "host": mongo_host,
                        "port": mongo_port,
                        "db": mongo_db,
                        "collection": mongo_collection
                    }
                })
    db_handler = DBHandler(
        mongo_username, mongo_password, mongo_host, mongo_port, mongo_db, mongo_collection,
        events_api_url=events_api_url,
        requests_per_minute=requests_per_minute)
    
    logger.debug("app.event.init",
                message="Initializing event handler")
    event_handler = EventHandler(
        mongo_username,
        mongo_password,
        mongo_host,
        mongo_port,
        mongo_db,
        mongo_collection)

    logger.info("app.db.start",
                message="Starting database handler process")
    db_process = Process(target=db_handler.run, args=())
    db_process.start()

    logger.info("app.event.start",
                message="Starting event handler")
    event_handler.run()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("app.shutdown",
                   message="Shutting down application")
        db_handler.stop()
        event_handler.stop()
    finally:
        logger.info("app.shutdown.complete",
                   message="Application has shut down")

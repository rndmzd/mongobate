import configparser
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time

from multiprocessing import Event, Process

from handlers import DBHandler, EventHandler

sys.stdout.reconfigure(encoding='utf-8')

config = configparser.ConfigParser()
config.read("config.ini")

log_file = config.get("Logging", "log_file")
log_max_size_mb = config.getint("Logging", "log_max_size_mb")
log_backup_count = config.getint("Logging", "log_backup_count")

if not os.path.exists(os.path.dirname(log_file)):
    os.makedirs(os.path.dirname(log_file))

logger = logging.getLogger('mongobate')
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=log_max_size_mb * 1024 * 1024,
    backupCount=log_backup_count,
    encoding='utf-8'
)

formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger.addHandler(stream_handler)
logger.addHandler(file_handler)


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

    logger.debug('Initializing database handler.')
    db_handler = DBHandler(
        mongo_username, mongo_password, mongo_host, mongo_port, mongo_db, mongo_collection,
        events_api_url=events_api_url,
        requests_per_minute=requests_per_minute)
    
    logger.debug('Initializing event handler.')
    event_handler = EventHandler(
        mongo_username,
        mongo_password,
        mongo_host,
        mongo_port,
        mongo_db,
        mongo_collection)

    logger.debug('Spawning process for database handler.')
    db_process = Process(target=db_handler.run, args=())
    db_process.start()

    logger.debug('Calling event handler start.')
    event_handler.run()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        db_handler.stop()
        event_handler.stop()
    finally:
        logger.info("Application has shut down.")

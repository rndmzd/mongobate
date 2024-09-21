import configparser
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
import time

from handlers import DBHandler

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

db_handler = None


def reload_config(signum, frame):
    if db_handler:
        logger.info("Stopping database handler.")
        db_handler.stop()
        while db_handler.is_alive:
            time.sleep(0.1)
    while True:
        logger.info("Reinitializing database handler.")
        initialize_status = initialize_handler()
        logger.debug(f"Initialize status: {initialize_status}")
        if initialize_status:
            logger.info("Database handler reinitialized.")
            break
        else:
            logger.error("Failed to reinitialize database handler. Retrying in 5 seconds.")
            time.sleep(5)


# Register the signal handler
signal.signal(signal.SIGHUP, reload_config)


def initialize_handler():
    global db_handler

    try:
        logger.info("Loading configuration from file.")
        config.read("config.ini")

        mongo_username = config.get("MongoDB", "username")
        mongo_password = config.get("MongoDB", "password")
        mongo_host = config.get("MongoDB", "host")
        mongo_port = config.getint("MongoDB", "port")
        mongo_db = config.get("MongoDB", "db")
        mongo_collection = config.get("MongoDB", "event_collection")

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

        events_api_url = config.get("Events API", "url")
        requests_per_minute = config.getint(
            "Events API", "max_requests_per_minute")
        
        db_handler = DBHandler(
            mongo_username, mongo_password, mongo_host, mongo_port, mongo_db, mongo_collection,
            events_api_url=events_api_url,
            requests_per_minute=requests_per_minute,
            aws_key=aws_key, aws_secret=aws_secret)
        
        return True
    
    except Exception as e:
        logger.exception("Failed to initialize database handler.", exc_info=e)
        logger.exception(e)
        return False


if __name__ == '__main__':
    while True:
        try:
            if not db_handler or not db_handler.is_alive:
                logger.info('Database handler is not running. Attempting to reinitialize...')
                initialize_status = initialize_handler()
                logger.debug(f'Initialize status: {initialize_status}')
                if not initialize_status:
                    logger.error('Failed to reinitialize database handler. Retrying in 5 seconds.')
                    time.sleep(5)
                    continue
            logger.debug('Running database handler.')
            # Execution blocks here until the DBHandler is stopped.
            db_handler.run()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            db_handler.stop()
            while db_handler.is_alive:
                time.sleep(0.1)
            logger.info("Done.")
            break
        except Exception as e:
            logger.exception("An unexpected error occurred.", exc_info=e)
            logger.error("Restarting in 5 seconds...")
            time.sleep(5)
            continue

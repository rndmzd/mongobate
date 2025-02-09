import configparser
import sys

# Import the new DBHandler from handlers/dbhandler.py
from handlers.dbhandler import DBHandler
from utils.structured_logging import get_structured_logger
from utils.logging_config import setup_basic_logging

sys.stdout.reconfigure(encoding='utf-8')

config = configparser.ConfigParser()
config.read("config.ini")

# Initialize structured logger
logger = get_structured_logger('mongobate.db')

def main():
    setup_basic_logging()

    # Debug output to ensure config was loaded
    print("Loaded config sections:", config.sections())

    # Retrieve Events API configuration
    events_api_url = config.get("Events API", "url")
    requests_per_minute = config.getint("Events API", "max_requests_per_minute")

    # Retrieve MongoDB configuration
    mongo_username = config.get("MongoDB", "username")
    mongo_password = config.get("MongoDB", "password")
    mongo_host = config.get("MongoDB", "host")
    mongo_port = config.getint("MongoDB", "port")
    mongo_db = config.get("MongoDB", "db")

    # Try to get the proper collection name. Fallback to 'event_collection' if 'collection' is missing.
    try:
        mongo_collection = config.get("MongoDB", "collection")
    except configparser.NoOptionError:
        mongo_collection = config.get("MongoDB", "event_collection")

    # Read the replica set name from configuration; use "rs0" as default.
    replica_set = config.get("MongoDB", "replica_set", fallback="rs0")

    logger.info("dbhandler.init",
                message="Initializing database handler",
                data={
                    "api": {
                        "url": events_api_url,
                        "rate_limit": requests_per_minute
                    },
                    "mongo": {
                        "username": mongo_username,
                        "password": mongo_password,
                        "host": mongo_host,
                        "port": mongo_port,
                        "db": mongo_db,
                        "collection": mongo_collection
                    }
                })

    db_handler = DBHandler(
        mongo_username=mongo_username,
        mongo_password=mongo_password,
        mongo_host=mongo_host,
        mongo_port=mongo_port,
        mongo_db=mongo_db,
        mongo_collection=mongo_collection,
        events_api_url=events_api_url,
        requests_per_minute=requests_per_minute,
        replica_set=replica_set
    )

    try:
        print("Running DBHandler. Press Ctrl+C to stop...")
        db_handler.run()
    except KeyboardInterrupt:
        logger.info("dbhandler.shutdown",
                   message="Keyboard interrupt received")
    finally:
        db_handler.stop()
        logger.info("dbhandler.shutdown.complete",
                   message="Database handler stopped")

if __name__ == "__main__":
    main()

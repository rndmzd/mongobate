import configparser
import sys
import time

from utils.structured_logging import get_structured_logger

# Import the new DBHandler from handlers/dbhandler.py
from handlers.dbhandler import DBHandler

sys.stdout.reconfigure(encoding='utf-8')

config = configparser.ConfigParser()
config.read("config.ini")

# Initialize structured logger
logger = get_structured_logger('mongobate.db')

def main():
    from utils.logging_config import setup_basic_logging
    setup_basic_logging()

    # Debug output to ensure config was loaded
    print("Loaded config sections:", config.sections())
    
    # Retrieve Events API configuration
    events_api_url = config.get("Events API", "url")
    requests_per_minute = config.getint("Events API", "max_requests_per_minute")
    
    # Retrieve Stats API configuration
    stats_api_url = config.get("Stats API", "url")

    # Retrieve stats_collection from MongoDB config
    stats_collection = config.get("MongoDB", "stats_collection")

    # Retrieve MongoDB configuration
    mongo_username = config.get("MongoDB", "username")
    mongo_password = config.get("MongoDB", "password")
    mongo_host = config.get("MongoDB", "host")
    mongo_port = config.getint("MongoDB", "port")
    mongo_db = config.get("MongoDB", "db")

    # Retrieve event collection from MongoDB config
    event_collection = config.get("MongoDB", "event_collection")
    

    # Read the replica set name from configuration; use "rs0" as default.
    replica_set = config.get("MongoDB", "replica_set", fallback="rs0")
    
    # Retrieve Rooms Online API configuration
    rooms_api_url = config.get("Rooms Online API", "url")
    rooms_request_ip = config.get("Rooms Online API", "request_ip")
    rooms_limit = config.get("Rooms Online API", "room_count")
    
    # Retrieve rooms collection from MongoDB config
    rooms_collection = config.get("MongoDB", "rooms_collection")


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
                        "collection": event_collection,
                        "stats_collection": stats_collection,
                        "rooms_collection": rooms_collection
                    }
                })

    db_handler = DBHandler(
        mongo_username=mongo_username,
        mongo_password=mongo_password,
        mongo_host=mongo_host,
        mongo_port=mongo_port,
        mongo_db=mongo_db,
        events_collection=event_collection,
        events_api_url=events_api_url,
        requests_per_minute=requests_per_minute,
        replica_set=replica_set,
        stats_api_url=stats_api_url,
        stats_collection=stats_collection,
        rooms_api_url=rooms_api_url,
        rooms_request_ip=rooms_request_ip,
        rooms_limit=rooms_limit,
        rooms_collection=rooms_collection
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

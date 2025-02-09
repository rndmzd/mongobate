import datetime
import queue
import threading
import time
import json
import traceback

import requests
from requests.exceptions import RequestException

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

import urllib.parse

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.handlers.dbhandler')


def connect_to_database(mongo_connection_uri, mongo_db, mongo_collection):
    """
    Establish a connection to MongoDB and return the collection object
    for storing events.
    
    Args:
        mongo_connection_uri (str): MongoDB connection URI.
        mongo_db (str): The database name.
        mongo_collection (str): The collection name.
    
    Returns:
        A pymongo Collection object.
        
    Raises:
        ConnectionFailure: When unable to connect to MongoDB.
    """
    try:
        # Create the MongoClient with a short timeout for connection.
        client = MongoClient(mongo_connection_uri, serverSelectionTimeoutMS=5000)
        # Force connection on a request as the connect=True parameter is deprecated.
        client.admin.command("ping")
    except ConnectionFailure as e:
        raise ConnectionFailure(f"Could not connect to MongoDB: {e}")
    
    # Return the specific collection you'd like to use for storing events.
    return client[mongo_db][mongo_collection]


class DBHandler:
    def __init__(
            self,
            mongo_username,
            mongo_password,
            mongo_host,
            mongo_port,
            mongo_db,
            events_collection,
            events_api_url,
            requests_per_minute=1000,
            replica_set="rs0",
            stats_api_url=None,
            stats_collection=None,
            rooms_api_url=None,
            rooms_request_ip=None,
            rooms_limit=None,
            rooms_collection=None,
            aws_key=None,
            aws_secret=None):
        self.mongo_username = mongo_username
        self.mongo_password = mongo_password
        self.mongo_host = mongo_host
        self.mongo_port = mongo_port
        self.mongo_db = mongo_db
        self.mongo_collection = events_collection
        self.events_api_url = events_api_url
        self.stats_api_url = stats_api_url
        self.stats_collection_name = stats_collection
        self.rooms_api_url = rooms_api_url
        self.rooms_request_ip = rooms_request_ip
        self.rooms_limit = rooms_limit
        self.rooms_collection_name = rooms_collection
        self.interval = 60 / (requests_per_minute / 10)

        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()

        self.mongo_client = None

        self.mongo_replica_set = replica_set

        self.mongo_connection_uri = None
        if aws_key and aws_secret:
            logger.debug("mongodb.auth.aws",
                        message="Using AWS authentication for MongoDB")

            aws_key_pe = urllib.parse.quote_plus(aws_key)
            aws_secret_pe = urllib.parse.quote_plus(aws_secret)
            mongo_host_pe = urllib.parse.quote_plus(mongo_host)
            mongo_port_pe = urllib.parse.quote_plus(str(mongo_port))

            # Construct the URI with proper escaping and formatting
            self.mongo_connection_uri = (
                f"mongodb://{aws_key_pe}:****@"
                f"[{mongo_host_pe}]:{mongo_port_pe}/"
                f"?authMechanism=MONGODB-AWS&authSource=$external"
            )

        self.max_db_retry_attempts = 5  # Maximum attempts to connect to the database
        self.db_retry_backoff = 1  # initial backoff in seconds for DB connection retries

        # Attempt to connect to the database with retry logic
        self.connect_with_retry()

    def _sanitize_uri(self, uri):
        # Remove sensitive information from the URI
        parts = uri.split('@')
        if len(parts) == 2:
            sanitized_uri = parts[1]  # Keep only the part after '@'
            return f"mongodb://<credentials>@{sanitized_uri}"
        return uri

    def connect_with_retry(self):
        """Try to connect to the database with a retry strategy."""
        attempts = 0
        backoff = self.db_retry_backoff
        while attempts < self.max_db_retry_attempts:
            try:
                self.connect_to_mongodb()
                return
            except Exception as exc:
                attempts += 1
                logger.exception("database.connect.error",
                                 exc=exc,
                                 message=f"Failed to connect to database, attempt {attempts}/{self.max_db_retry_attempts}")
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
        logger.error("database.connect.fatal",
                     message="Exceeded maximum database reconnect attempts. Exiting.")
        raise Exception("Fatal error: Could not connect to database after retries.")

    def connect_to_mongodb(self):
        try:
            if self.mongo_connection_uri:
                # When using AWS-based connection, append query parameters.
                uri = f"{self.mongo_connection_uri}&replicaSet={self.mongo_replica_set}&directConnection=true"
            else:
                # Construct the standard MongoDB URI with authentication source.
                uri = (
                    f"mongodb://{self.mongo_username}:{self.mongo_password}@"
                    f"{self.mongo_host}:{self.mongo_port}/{self.mongo_db}"
                    f"?authSource=admin&replicaSet={self.mongo_replica_set}&directConnection=true"
                )
            logger.debug("connecting.uri", message="Connecting with MongoDB", data={"uri": self._sanitize_uri(uri)})
            self.mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            # Force a connection to check for errors.
            self.mongo_client.admin.command("ping")
            # Do not overwrite self.mongo_db: store the actual Database object in a new attribute.
            self.db = self.mongo_client[self.mongo_db]
            self.event_collection = self.db[self.mongo_collection]
            if self.stats_collection_name:
                self.stats_collection = self.db[self.stats_collection_name]
            if self.rooms_collection_name:
                self.rooms_collection = self.db[self.rooms_collection_name]
        except ConnectionFailure as e:
            logger.exception("database.connection.failure", exc=e, message=f"Could not connect to MongoDB: {e}")
            raise

    def archive_event(self, event):
        try:
            event['timestamp'] = datetime.datetime.now(tz=datetime.timezone.utc)
            logger.debug("event.archive",
                        message="Archiving event",
                        data={
                            "timestamp": event['timestamp'],
                            "event_type": event.get('method'),
                            "event_id": str(event.get('_id', ''))
                        })
                        
            result = self.event_collection.insert_one(event)
            logger.info("event.archive.success",
                       message="Archived event",
                       data={
                           "document_id": str(result.inserted_id),
                           "event_type": event.get('method')
                       })
                        
        except Exception as exc:
            logger.exception("event.archive.error",
                           message="Failed to archive event",
                           exc=exc,
                           data={
                               "event_type": event.get('method'),
                               "event_id": str(event.get('_id', ''))
                           })

    def event_processor(self):
        """
        Continuously process events from the event queue.
        """
        while not self._stop_event.is_set():
            try:
                # Timeout to check for stop signal
                event = self.event_queue.get(timeout=1)
                self.archive_event(event)
                self.event_queue.task_done()
            except queue.Empty:
                continue  # Resume loop if no event and check for stop signal
            except Exception as exc:
                logger.exception("event.process.error",
                               message="Failed to process event",
                               exc=exc)

    def long_polling(self):
        """
        Continuously poll the API and put events into the queue.
        """
        url_next = self.events_api_url

        while not self._stop_event.is_set():
            try:
                response = requests.get(url_next)
                if response.status_code == 200:
                    data = response.json()
                    for event in data["events"]:
                        self.event_queue.put(event)
                    url_next = data.get("nextUrl", url_next)
                else:
                    logger.error("api.response.error", message="Received non-200 status code", data={"status_code": response.status_code})
            except RequestException as e:
                logger.error("api.request.failed", message="Request failed", data={"error": str(e)})

            time.sleep(self.interval)

    def stats_polling(self):
        while not self._stop_event.is_set():
            try:
                response = requests.get(self.stats_api_url)
                if response.status_code == 200:
                    stats_data = response.json()
                    stats_data['fetched_at'] = datetime.datetime.now(tz=datetime.timezone.utc)
                    logger.info("stats.polling.success", message="Fetched stats", data=stats_data)
                    self.stats_collection.insert_one(stats_data)
                else:
                    logger.error("stats.api.error", message="Received non-200 response", data={"status_code": response.status_code})
            except Exception as exc:
                logger.exception("stats.polling.error", message="Failed to fetch stats", exc=exc)
            if self._stop_event.wait(300):
                break

    def rooms_online_polling(self):
        while not self._stop_event.is_set():
            try:
                constructed_url = f"{self.rooms_api_url}&client_ip={self.rooms_request_ip}&limit={self.rooms_limit}"
                response = requests.get(constructed_url)
                if response.status_code == 200:
                    data = response.json()
                    for room in data.get("results", []):
                        room['_id'] = room.get("username")
                        room['fetched_at'] = datetime.datetime.now(tz=datetime.timezone.utc)
                        self.rooms_collection.update_one({'_id': room['_id']}, {'$set': room}, upsert=True)
                    logger.info("rooms.polling.success", message="Fetched rooms online data", data={"count": len(data.get('results', []))})
                else:
                    logger.error("rooms.api.error", message="Received non-200 response", data={"status_code": response.status_code})
            except Exception as exc:
                logger.exception("rooms.polling.error", message="Failed to fetch rooms online data", exc=exc)
            if self._stop_event.wait(300):
                break

    def run(self):
        logger.info("dbhandler.start", message="Starting database handler")
        logger.debug("thread.processor.start", message="Starting event processor thread")
        processor_thread = threading.Thread(target=self.event_processor, daemon=True)
        processor_thread.start()

        logger.debug("thread.stats.start", message="Starting stats polling thread")
        stats_thread = threading.Thread(target=self.stats_polling, daemon=True)
        stats_thread.start()

        rooms_thread = None
        if self.rooms_api_url:
            logger.debug("thread.rooms.start", message="Starting rooms online polling thread")
            rooms_thread = threading.Thread(target=self.rooms_online_polling, daemon=True)
            rooms_thread.start()

        try:
            self.long_polling()
        except KeyboardInterrupt:
            logger.info("dbhandler.shutdown", message="Keyboard interrupt detected, cleaning up")
        finally:
            self._stop_event.set()
            processor_thread.join()
            stats_thread.join()
            if rooms_thread:
                rooms_thread.join()
            logger.info("dbhandler.shutdown.complete", message="Cleanup complete")

    def stop(self):
        self._stop_event.set()
        logger.info("dbhandler.stop",
                   message="Stopping database handler")


if __name__ == "__main__":
    import configparser
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    events_api_url = config.get("Events API", "url")
    requests_per_minute = config.getint(
        "Events API", "max_requests_per_minute")

    logger.info("dbhandler.init",
                message="Initializing database handler",
                data={
                    "api": {
                        "url": events_api_url,
                        "rate_limit": requests_per_minute
                    }
                })

    db_handler = DBHandler(
        mongo_username=config.get('MongoDB', 'username'),
        mongo_password=config.get('MongoDB', 'password'),
        mongo_host=config.get('MongoDB', 'host'),
        mongo_port=config.getint('MongoDB', 'port'),
        mongo_db=config.get('MongoDB', 'db'),
        mongo_collection=config.get('MongoDB', 'collection'),
        events_api_url=events_api_url,
        requests_per_minute=requests_per_minute
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

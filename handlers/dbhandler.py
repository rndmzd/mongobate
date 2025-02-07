import datetime
import queue
import threading
import time

import requests
from requests.exceptions import RequestException

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

import urllib.parse

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.handlers.dbhandler')


class DBHandler:
    def __init__(
            self,
            mongo_username,
            mongo_password,
            mongo_host,
            mongo_port,
            mongo_db,
            mongo_collection,
            events_api_url,
            requests_per_minute=1000,
            aws_key=None,
            aws_secret=None):
        self.mongo_username = mongo_username
        self.mongo_password = mongo_password
        self.mongo_host = mongo_host
        self.mongo_port = mongo_port
        self.mongo_db = mongo_db
        self.mongo_collection = mongo_collection
        self.events_api_url = events_api_url
        self.interval = 60 / (requests_per_minute / 10)

        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()

        self.mongo_client = None

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

    def _sanitize_uri(self, uri):
        # Remove sensitive information from the URI
        parts = uri.split('@')
        if len(parts) == 2:
            sanitized_uri = parts[1]  # Keep only the part after '@'
            return f"mongodb://<credentials>@{sanitized_uri}"
        return uri

    def connect_to_mongodb(self):
        try:
            if self.mongo_connection_uri:
                sanitized_uri = self._sanitize_uri(self.mongo_connection_uri)
                logger.debug("mongodb.connect.aws",
                           message="Connecting with AWS credentials",
                           data={"uri": sanitized_uri})
                self.mongo_client = MongoClient(self.mongo_connection_uri)
            else:
                logger.debug("mongodb.connect.standard",
                           message="Connecting with username/password",
                           data={
                               "host": self.mongo_host,
                               "port": self.mongo_port
                           })
                self.mongo_client = MongoClient(
                    host=self.mongo_host,
                    port=self.mongo_port,
                    username=self.mongo_username,
                    password=self.mongo_password,
                    directConnection=True)

            self.mongo_db = self.mongo_client[self.mongo_db]
            self.event_collection = self.mongo_db[self.mongo_collection]
            
            logger.info("mongodb.connect.success",
                       message="Connected to MongoDB",
                       data={
                           "database": self.mongo_db.name,
                           "collection": self.mongo_collection
                       })
                       
        except ConnectionFailure as exc:
            logger.exception("mongodb.connect.error",
                           exc=exc,
                           message="Failed to connect to MongoDB")
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
                logger.debug("api.poll",
                           message="Polling events API",
                           data={
                               "url": url_next,
                               "interval": self.interval
                           })
                           
                response = requests.get(url_next)
                if response.status_code == 200:
                    data = response.json()
                    logger.info("api.poll.success",
                              message="Retrieved events from API",
                              data={
                                  "event_count": len(data["events"]),
                                  "next_url": data["nextUrl"],
                                  "status_code": response.status_code
                              })
                              
                    for event in data["events"]:
                        self.event_queue.put(event)
                    url_next = data["nextUrl"]
                else:
                    logger.error("api.poll.error",
                               message="Failed to retrieve events",
                               data={
                                   "status_code": response.status_code,
                                   "url": url_next
                               })
                               
            except RequestException as exc:
                logger.exception("api.poll.error",
                               message="Failed to poll events API",
                               exc=exc,
                               data={"url": url_next})

            time.sleep(self.interval)

    def run(self):
        logger.info("dbhandler.start",
                   message="Starting database handler")
                   
        self.connect_to_mongodb()

        logger.debug("thread.processor.start",
                    message="Starting event processor thread")
        processor_thread = threading.Thread(
            target=self.event_processor, args=(), daemon=True
        )
        processor_thread.start()

        try:
            self.long_polling()
        except KeyboardInterrupt:
            logger.info("dbhandler.shutdown",
                       message="Keyboard interrupt detected, cleaning up")
            self._stop_event.set()
            processor_thread.join()
            logger.info("dbhandler.shutdown.complete",
                       message="Cleanup complete")

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
    db_handler.run()

    print("Running DBHandler. Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("dbhandler.shutdown",
                   message="Keyboard interrupt received")
    finally:
        db_handler.stop()
        logger.info("dbhandler.shutdown.complete",
                   message="Database handler stopped")

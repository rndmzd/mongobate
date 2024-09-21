import datetime
import logging
import queue
import threading
import time

import requests
from requests.exceptions import RequestException

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

import urllib.parse

logger = logging.getLogger('mongobate.handlers.dbhandler')
logger.setLevel(logging.DEBUG)


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
            logger.debug("Using AWS authentication for MongoDB.")

            aws_key_pe = urllib.parse.quote_plus(aws_key)
            aws_secret_pe = urllib.parse.quote_plus(aws_secret)
            mongo_host_pe = urllib.parse.quote_plus(mongo_host)
            mongo_port_pe = urllib.parse.quote_plus(str(mongo_port))

            # Construct the URI with proper escaping and formatting
            self.mongo_connection_uri = (
                f"mongodb://{aws_key_pe}:{aws_secret_pe}@"
                f"[{mongo_host_pe}]:{mongo_port_pe}/"
                f"?authMechanism=MONGODB-AWS&authSource=$external"
            )

            self.is_alive = False

    def connect_to_mongodb(self):
        try:
            if self.mongo_connection_uri:
                logger.debug(f"Connecting with URI: {self.mongo_connection_uri}")
                self.mongo_client = MongoClient(self.mongo_connection_uri)
            else:
                self.mongo_client = MongoClient(
                    host=self.mongo_host,
                    port=self.mongo_port,
                    username=self.mongo_username,
                    password=self.mongo_password,
                    directConnection=True)

            self.mongo_db = self.mongo_client[self.mongo_db]
            self.event_collection = self.mongo_db[self.mongo_collection]
        except ConnectionFailure as e:
            logger.exception(f"Could not connect to MongoDB: {e}")
            raise

    def archive_event(self, event):
        try:
            event['timestamp'] = datetime.datetime.now(tz=datetime.timezone.utc)
            logger.debug(f"event['timestamp']: {event['timestamp']}")
            result = self.event_collection.insert_one(event)
            logger.debug(f"result.inserted_id: {result.inserted_id}")
        except Exception as e:
            logger.exception(f"Error archiving event: {event}", exc_info=e)

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
            except Exception as e:
                logger.exception("Error in event processor", exc_info=e)

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
                    url_next = data["nextUrl"]
                else:
                    logger.error(
                        f"Error: Received status code {response.status_code}")
            except RequestException as e:
                logger.error(f"Request failed: {e}")

            time.sleep(self.interval)

    def run(self):
        self.connect_to_mongodb()

        processor_thread = threading.Thread(
            target=self.event_processor, args=(), daemon=True
        )
        processor_thread.start()

        """network_thread = threading.Thread(
            target=self.long_polling, args=(), daemon=True
        )
        network_thread.start()"""

        try:
            self.is_alive = True
            self.long_polling()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt detected. Cleaning up...")
            self._stop_event.set()
            processor_thread.join()
            # network_thread.join()
            logger.info("Done.")
        finally:
            self.is_alive = False

    def stop(self):
        self._stop_event.set()
        logger.info("Stopping DBHandler...")


if __name__ == "__main__":
    import configparser
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    events_api_url = config.get("Events API", "url")
    requests_per_minute = config.getint(
        "Events API", "max_requests_per_minute")

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
        logger.info('KeyboardInterrupt received. Stopping database handler...')
    finally:
        db_handler.stop()
        logger.info("Done.")

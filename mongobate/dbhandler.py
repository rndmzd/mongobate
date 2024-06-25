import logging
import queue
import threading
import time

import requests
from requests.exceptions import RequestException

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger()
# logging.basicConfig()
# logger.setLevel(logging.DEBUG)


class DBHandler:
    def __init__(
            self,
            mongo_host,
            mongo_port,
            mongo_db,
            mongo_collection,
            events_api_url,
            requests_per_minute=1000):
        self.events_api_url = events_api_url
        self.interval = 60 / (requests_per_minute / 10)

        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()

        try:
            self.mongo_client = MongoClient(host=mongo_host, port=mongo_port)
            self.mongo_db = self.mongo_client[mongo_db]
            self.event_collection = self.mongo_db[mongo_collection]
        except ConnectionFailure as e:
            print("Could not connect to MongoDB:", e)
            raise

    def archive_event(self, event):
        try:
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
        processor_thread = threading.Thread(
            target=self.event_processor, args=(), daemon=True
        )
        processor_thread.start()

        network_thread = threading.Thread(
            target=self.long_polling, args=(), daemon=True
        )
        network_thread.start()

        try:
            self.long_polling()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt detected. Cleaning up...")
            self._stop_event.set()
            processor_thread.join()
            network_thread.join()
            logger.info("Done.")

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

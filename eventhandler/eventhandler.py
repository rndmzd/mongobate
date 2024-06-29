import logging
import queue
import threading

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger('mongobate.eventhandler.eventhandler')
logger.setLevel(logging.DEBUG)


class EventHandler:
    def __init__(
            self,
            mongo_host,
            mongo_port,
            mongo_db,
            mongo_collection):
        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()

        self.cb_events = CBEvents()
        
        try:
            self.mongo_client = MongoClient(host=mongo_host, port=mongo_port)
            self.mongo_db = self.mongo_client[mongo_db]
            self.event_collection = self.mongo_db[mongo_collection]
        except ConnectionFailure as e:
            logger.exception("Could not connect to MongoDB:", e)
            raise

    def event_processor(self):
        """
        Continuously process events from the event queue.
        """
        while not self._stop_event.is_set():
            try:
                event = self.event_queue.get(timeout=1)  # Timeout to check for stop signal
                process_result = self.cb_events.process_event(event)
                logger.debug(f"process_result: {process_result}")
                self.event_queue.task_done()
            except queue.Empty:
                continue  # Resume loop if no event and check for stop signal
            except Exception as e:
                logger.exception("Error in event processor", exc_info=e)

    def watch_changes(self):
        try:
            with self.event_collection.watch(max_await_time_ms=1000) as stream:
                while not self._stop_event.is_set():
                    change = stream.try_next()
                    if change is None:
                        continue
                    if change["operationType"] == "insert":
                        doc = change["fullDocument"]
                        self.event_queue.put(doc)
        except Exception as e:
            logger.exception("An error occurred while watching changes: %s", e)
        finally:
            if not self._stop_event.is_set():
                self.cleanup()

    def run(self):
        logger.info("Starting change stream watcher thread...")
        self.watcher_thread = threading.Thread(
            target=self.watch_changes, args=(), daemon=True
        )
        self.watcher_thread.start()

        logger.info("Starting event processing thread...")
        self.event_thread = threading.Thread(
            target=self.event_processor, args=(), daemon=True
        )
        self.event_thread.start()

    def stop(self):
        logger.debug("Setting stop event.")
        self._stop_event.set()
        if self.watcher_thread.is_alive():
            logger.debug("Joining watcher thread.")
            self.watcher_thread.join()
        if self.event_thread.is_alive():
            logger.debug("Joining event thread.")
            self.event_thread.join()
        logger.debug("Checking if MongoDB connection still active.")
        self.cleanup()

    def cleanup(self):
        if self.mongo_client:
            logger.info("Closing MongoDB connection...")
            self.mongo_client.close()
        
        logger.info("Clean-up complete.")

if __name__ == "__main__":
    import configparser
    import time

    config = configparser.ConfigParser()
    config.read("config.ini")

    event_handler = EventHandler(
        mongo_host=config.get('MongoDB', 'host'),
        mongo_port=config.getint('MongoDB', 'port'),
        mongo_db=config.get('MongoDB', 'db'),
        mongo_collection=config.get('MongoDB', 'collection'))
    event_handler.run()

    print("Watching for changes. Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt received. Stopping threads...')
    finally:
        event_handler.stop()
        logger.info("Done.")

import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import threading

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)


class EventHandler:
    def __init__(self, mongo_uri, mongo_collection):
        try:
            self.mongo_client = MongoClient(mongo_uri)
            self.mongo_collection = self.mongo_client[mongo_collection]
            self._stop_event = threading.Event()
        except ConnectionFailure as e:
            print("Could not connect to MongoDB:", e)
            raise

    def process_event(self, event):
        print("Processing event:", event)

    def watch_changes(self):
        try:
            with self.mongo_collection.watch(max_await_time_ms=1000) as stream:
                while not self._stop_event.is_set():
                    change = stream.try_next()
                    if change is None:
                        continue
                    if change["operationType"] == "insert":
                        doc = change["fullDocument"]
                        self.process_event(doc)
        except Exception as e:
            logger.exception("An error occurred while watching changes: %s", e)
        finally:
            if not self._stop_event.is_set():
                self.cleanup()

    def run(self):
        self.processor_thread = threading.Thread(
            target=self.watch_changes, args=(), daemon=True
        )
        self.processor_thread.start()

    def stop(self):
        self._stop_event.set()
        if self.processor_thread.is_alive():
            self.processor_thread.join()
        self.cleanup()

    def cleanup(self):
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("MongoDB connection closed.")


if __name__ == "__main__":
    import configparser
    import time

    config = configparser.ConfigParser()
    config.read("config.ini")

    mongo_uri = f"mongodb://{config.get('MongoDB', 'host')}:{config.getint('MongoDB', 'port')}/{config.get('MongoDB', 'db')}"
    events_collection = config.get("MongoDB", "collection")

    watcher = EventHandler(mongo_uri=mongo_uri, mongo_collection=events_collection)
    watcher.run()

    try:
        current_time = time.time()
        while time.time() - current_time < 5:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt received. Stopping watcher...')
    finally:
        watcher.stop()
        logger.info("Done.")

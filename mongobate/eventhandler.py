import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import threading

logger = logging.getLogger()
# logging.basicConfig(level=logging.INFO)


class EventHandler:
    def __init__(
            self,
            mongo_host,
            mongo_port,
            mongo_db,
            mongo_collection):
        try:
            self.mongo_client = MongoClient(host=mongo_host, port=mongo_port)
            self.mongo_db = self.mongo_client[mongo_db]
            self.event_collection = self.mongo_db[mongo_collection]
            self._stop_event = threading.Event()
        except ConnectionFailure as e:
            print("Could not connect to MongoDB:", e)
            raise

    def process_event(self, event):
        print("Processing event:", event)

    def watch_changes(self):
        try:
            with self.event_collection.watch(max_await_time_ms=1000) as stream:
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
        self.watcher_thread = threading.Thread(
            target=self.watch_changes, args=(), daemon=True
        )
        self.watcher_thread.start()

    def stop(self):
        self._stop_event.set()
        if self.watcher_thread.is_alive():
            self.watcher_thread.join()
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

    watcher = EventHandler(
        mongo_host=config.get('MongoDB', 'host'),
        mongo_port=config.getint('MongoDB', 'port'),
        mongo_db=config.get('MongoDB', 'db'),
        mongo_collection=config.get('MongoDB', 'collection'))
    watcher.run()

    print("Watching for changes. Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt received. Stopping watcher...')
    finally:
        watcher.stop()
        logger.info("Done.")

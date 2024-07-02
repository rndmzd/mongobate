import logging
import queue
import threading

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

import urllib.parse

logger = logging.getLogger('mongobate.eventhandler.eventhandler')
logger.setLevel(logging.DEBUG)


class EventHandler:

    def __init__(
        self,
        mongo_host,
        mongo_port,
        mongo_db,
        mongo_collection,
        vip_collection=None,
        vip_refresh_interval=300,
        audio_device=None,
        aws_key=None,
        aws_secret=None):
        from .cbevents import CBEvents

        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()

        self.cb_events = CBEvents()

        self.mongo_connection_uri = None
        if aws_key and aws_secret:
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

        try:
            if self.mongo_connection_uri:
                logger.debug(f"Connecting with URI: {self.mongo_connection_uri}")
                self.mongo_client = MongoClient(self.mongo_connection_uri)
            else:
                self.mongo_client = MongoClient(host=mongo_host, port=mongo_port)

            self.mongo_db = self.mongo_client[mongo_db]
            self.event_collection = self.mongo_db[mongo_collection]

            if "vip_audio" in self.cb_events.active_components:
                self.vip_collection = (
                    self.mongo_db[vip_collection] if vip_collection else None
                )
            else:
                self.vip_collection = None
        except ConnectionFailure as e:
            logger.exception("Could not connect to MongoDB:", exc_info=e)
            raise

        if 'vip_audio' in self.cb_events.active_components:
            # if not audio_device:
            #     logger.error("VIP audio is enabled. Must provide audio device name for output.")
            #     raise ValueError("audio_device must be provided when VIP audio is enabled.")
            from chataudio import AudioPlayer
            ##  TODO: AudioPlayer
            self.audio_player = AudioPlayer(audio_device)
            self.vip_users = {}
            self.vip_refresh_interval = vip_refresh_interval
            self.load_vip_users()

    def load_vip_users(self):
        try:
            vip_users = self.vip_collection.find()
            self.vip_users = {user['username']: user['audio_file'] for user in vip_users}
            logger.info(f"Loaded {len(self.vip_users)} VIP users.")
        except Exception as e:
            logger.exception("Error loading VIP users:", exc_info=e)

    def vip_refresh_loop(self):
        while not self._stop_event.is_set():
            time.sleep(self.vip_refresh_interval)
            self.load_vip_users()

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
                logger.exception("Error in event processor:" , exc_info=e)

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
            logger.exception("An error occurred while watching changes: %s", exc_info=e)
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

        logger.info("Starting VIP refresh thread...")
        self.vip_refresh_thread = threading.Thread(
            target=self.vip_refresh_loop, args=(), daemon=True
        )

    def stop(self):
        logger.debug("Setting stop event.")
        self._stop_event.set()
        for thread in [self.watcher_thread, self.event_thread, self.vip_refresh_thread]:
            if thread.is_alive():
                logger.debug(f"Joining {thread.name} thread.")
                thread.join()
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

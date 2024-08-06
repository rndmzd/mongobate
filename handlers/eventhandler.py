import logging
import queue
import threading
import time

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

import urllib.parse

logger = logging.getLogger('mongobate.handlers.eventhandler')
logger.setLevel(logging.DEBUG)


class EventHandler:

    def __init__(
        self,
        mongo_username,
        mongo_password,
        mongo_host,
        mongo_port,
        mongo_db,
        mongo_collection,
        user_collection=None,
        vip_refresh_interval=300,
        admin_refresh_interval=300,
        audio_device=None,
        aws_key=None,
        aws_secret=None):
        from helpers.cbevents import CBEvents

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
                self.mongo_client = MongoClient(
                    host=mongo_host,
                    port=mongo_port,
                    username=mongo_username,
                    password=mongo_password,
                    directConnection=True)

            self.mongo_db = self.mongo_client[mongo_db]
            self.event_collection = self.mongo_db[mongo_collection]

            if "vip_audio" in self.cb_events.active_components or "command_parser" in self.cb_events.active_components:
                self.user_collection = (
                    self.mongo_db[user_collection] if user_collection else None
                )
            else:
                self.user_collection = None
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
        
        if 'command_parser' in self.cb_events.active_components:
            self.admin_users = {}
            self.admin_refresh_interval = admin_refresh_interval
            self.load_admin_users()

    def load_vip_users(self):
        try:
            vip_users = self.user_collection.find({'vip': True, 'active': True})
            for user in vip_users:
                logger.debug(f"user: {user}")
                self.vip_users[user['username']] = user['audio_file']
            logger.info(f"Loaded {len(self.vip_users)} VIP users.")
        except Exception as e:
            logger.exception("Error loading VIP users:", exc_info=e)
    
    def load_admin_users(self):
        try:
            admin_users = self.user_collection.find({'admin': True, 'active': True})
            for user in admin_users:
                logger.debug(f"user: {user}")
                self.admin_users[user['username']] = True
            logger.info(f"Loaded {len(self.admin_users)} admin users.")
        except Exception as e:
            logger.exception("Error loading admin users:", exc_info=e)

    def privileged_user_refresh(self):
        last_load_vip = time.time()
        last_load_admin = time.time()
        while not self._stop_event.is_set():
            if time.time() - last_load_vip > self.vip_refresh_interval:
                self.load_vip_users()
                last_load_vip = time.time()
            if time.time() - last_load_admin > self.admin_refresh_interval:
                self.load_admin_users()
                last_load_admin = time.time()

            time.sleep(1)

    def song_queue_check(self):
        while not self._stop_event.is_set():
            song_queue_status = self.cb_events.actions.auto_dj.check_queue_status()
            logger.debug(f"song_queue_status: {song_queue_status}")
            time.sleep(5)

    def event_processor(self):
        """
        Continuously process events from the event queue.
        """
        while not self._stop_event.is_set():
            try:
                event = self.event_queue.get(timeout=1)  # Timeout to check for stop signal
                privileged_users = {
                    "vip": self.vip_users,
                    "admin": self.admin_users
                }
                process_result = self.cb_events.process_event(event, privileged_users, self.audio_player)
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

        logger.info("Starting admin user refresh thread...")
        self.privileged_user_refresh_thread = threading.Thread(
            target=self.privileged_user_refresh, args=(), daemon=True
        )
        self.privileged_user_refresh_thread.start()

        if "chat_auto_dj" in self.cb_events.active_components:
            logger.info("Starting song queue check thread...")
            self.song_queue_check_thread = threading.Thread(
                target=self.song_queue_check, args=(), daemon=True
            )
            self.song_queue_check_thread.start()

    def stop(self):
        logger.debug("Setting stop event.")
        self._stop_event.set()
        for thread in [self.watcher_thread, self.event_thread, self.privileged_user_refresh_thread]:
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
        mongo_username=config.get('MongoDB', 'username'),
        mongo_password=config.get('MongoDB', 'password'),
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

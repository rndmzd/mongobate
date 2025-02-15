import queue
import threading
import time
import urllib.parse

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.handlers.eventhandler')


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
        action_refresh_interval=300,
        aws_key=None,
        aws_secret=None):

        logger.info("handler.init", message="Initializing event handler")

        from helpers.cbevents import CBEvents

        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()
        self.cb_events = CBEvents()

        # Setup MongoDB connection
        self.mongo_connection_uri = None
        if aws_key and aws_secret:
            logger.debug("mongodb.auth", message="Using AWS authentication")
            aws_key_pe = urllib.parse.quote_plus(aws_key)
            aws_secret_pe = urllib.parse.quote_plus(aws_secret)
            mongo_host_pe = urllib.parse.quote_plus(mongo_host)
            mongo_port_pe = urllib.parse.quote_plus(str(mongo_port))

            self.mongo_connection_uri = (
                f"mongodb://{aws_key_pe}:****@"
                f"[{mongo_host_pe}]:{mongo_port_pe}/"
                f"?authMechanism=MONGODB-AWS&authSource=$external"
            )

        try:
            if self.mongo_connection_uri:
                sanitized_uri = self.mongo_connection_uri.replace(aws_secret_pe, "****")
                logger.debug("mongodb.connect",
                           message="Connecting with AWS credentials",
                           data={"uri": sanitized_uri})
                self.mongo_client = MongoClient(self.mongo_connection_uri)
            else:
                logger.debug("mongodb.connect",
                           message="Connecting with username/password",
                           data={
                               "host": mongo_host,
                               "port": mongo_port,
                               "username": mongo_username
                           })
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

            logger.info("mongodb.connect.success",
                       message="Connected to MongoDB",
                       data={
                           "database": mongo_db,
                           "collections": {
                               "events": mongo_collection,
                               "users": user_collection if user_collection else None
                           }
                       })

        except ConnectionFailure as exc:
            logger.exception("mongodb.connect.error", exc=exc,
                           message="Failed to connect to MongoDB")
            raise

        # Initialize user caches
        self.vip_users = None
        self.admin_users = None
        self.action_users = None

        if 'vip_audio' in self.cb_events.active_components:
            self.vip_users = {}
            self.vip_refresh_interval = vip_refresh_interval
            self.load_vip_users()

        if 'command_parser' in self.cb_events.active_components:
            self.admin_users = {}
            self.admin_refresh_interval = admin_refresh_interval
            self.load_admin_users()

        if 'custom_actions' in self.cb_events.active_components:
            self.action_users = {}
            self.action_refresh_interval = action_refresh_interval
            self.load_action_users()

    def load_vip_users(self):
        try:
            vip_users = self.user_collection.find({'vip': True, 'active': True})
            self.vip_users.clear()

            for user in vip_users:
                logger.debug("users.vip.load",
                           message="Loading VIP user",
                           data={"user": user})
                self.vip_users[user['username']] = user['audio_file']

            logger.info("users.vip.loaded",
                       message="Loaded VIP users",
                       data={"count": len(self.vip_users)})

        except Exception as exc:
            logger.exception("users.vip.error", exc=exc,
                           message="Failed to load VIP users")

    def load_admin_users(self):
        try:
            admin_users = self.user_collection.find({'admin': True, 'active': True})
            self.admin_users.clear()

            for user in admin_users:
                logger.debug("users.admin.load",
                           data={"user": user})
                self.admin_users[user['username']] = True

            logger.info("users.admin.loaded",
                       message="Loaded admin users",
                       data={"count": len(self.admin_users)})

        except Exception as exc:
            logger.exception("users.admin.error", exc=exc,
                           message="Failed to load admin users")

    def load_action_users(self):
        try:
            action_users = self.user_collection.find({'action': True, 'active': True})
            self.action_users.clear()

            for user in action_users:
                logger.debug("users.action.load",
                           data={"user": user})
                self.action_users[user['username']] = user['custom']

            logger.info("users.action.loaded",
                       message="Loaded action users",
                       data={"count": len(self.action_users)})

        except Exception as exc:
            logger.exception("users.action.error", exc=exc,
                           message="Failed to load action users")

    def privileged_user_refresh(self):
        last_load_vip = time.time()
        last_load_admin = time.time()
        last_load_action = time.time()

        while not self._stop_event.is_set():
            current_time = time.time()

            if current_time - last_load_vip > self.vip_refresh_interval:
                logger.debug("users.vip.refresh",
                           message="Refreshing VIP users")
                self.load_vip_users()
                last_load_vip = current_time

            if current_time - last_load_admin > self.admin_refresh_interval:
                logger.debug("users.admin.refresh",
                           message="Refreshing admin users")
                self.load_admin_users()
                last_load_admin = current_time

            if current_time - last_load_action > self.action_refresh_interval:
                logger.debug("users.action.refresh",
                           message="Refreshing action users")
                self.load_action_users()
                last_load_action = current_time

            time.sleep(1)

    def song_queue_check(self):
        """Continuously check the song queue status."""
        while not self._stop_event.is_set():
            try:
                song_queue_status = self.cb_events.actions.auto_dj.check_queue_status()
            except Exception as exc:
                logger.exception("song.queue.check.error", exc=exc, message="Error occurred during auto_dj.check_queue_status")
            time.sleep(5)
        logger.info("song.queue.check.shutdown",
                    message="Shutting down song queue check")
        # One final check in silent mode during shutdown
        try:
            # Check queue status silently
            self.cb_events.actions.auto_dj.check_queue_status(silent=True)
            # If there are any remaining tracks, clear them silently
            if self.cb_events.actions.auto_dj.queued_tracks:
                self.cb_events.actions.auto_dj.clear_playback_context(silent=True)

        except Exception:
            pass  # Ignore any errors during shutdown

    def event_processor(self):
        """Continuously process events from the event queue."""
        while not self._stop_event.is_set():
            try:
                event = self.event_queue.get(timeout=1)  # Timeout to check for stop signal

                logger.debug("event.process",
                           message="Processing event",
                           data={"event": event})

                privileged_users = {}
                if "vip_audio" in self.cb_events.active_components and self.vip_users is not None:
                    privileged_users["vip"] = self.vip_users
                if "command_parser" in self.cb_events.active_components and self.admin_users is not None:
                    privileged_users["admin"] = self.admin_users
                if "custom_actions" in self.cb_events.active_components and self.action_users is not None:
                    privileged_users["custom_actions"] = self.action_users

                process_result = self.cb_events.process_event(event, privileged_users)
                logger.debug("event.process.result",
                           data={"success": process_result})

                self.event_queue.task_done()

            except queue.Empty:
                continue  # Resume loop if no event and check for stop signal
            except Exception as exc:
                logger.exception("event.process.error", exc=exc,
                               message="Failed to process event")

    def watch_changes(self):
        try:
            logger.info("mongodb.watch.start",
                       message="Starting change stream watch")

            with self.event_collection.watch(max_await_time_ms=1000) as stream:
                while not self._stop_event.is_set():
                    change = stream.try_next()
                    if change is None:
                        continue

                    if change["operationType"] == "insert":
                        doc = change["fullDocument"]
                        logger.debug("mongodb.watch.event",
                                   message="New event detected",
                                   data={"document": doc})
                        self.event_queue.put(doc)

        except Exception as exc:
            logger.exception("mongodb.watch.error", exc=exc,
                           message="Failed to watch for changes")
        finally:
            if not self._stop_event.is_set():
                self.cleanup()

    def run(self):
        logger.info("handler.start",
                   message="Starting event handler threads")

        logger.debug("thread.watch.start",
                    message="Starting change stream watcher thread")
        self.watcher_thread = threading.Thread(
            target=self.watch_changes, args=(), daemon=True
        )
        self.watcher_thread.start()

        logger.debug("thread.event.start",
                    message="Starting event processor thread")
        self.event_thread = threading.Thread(
            target=self.event_processor, args=(), daemon=True
        )
        self.event_thread.start()

        logger.debug("thread.users.start",
                    message="Starting privileged user refresh thread")
        self.privileged_user_refresh_thread = threading.Thread(
            target=self.privileged_user_refresh, args=(), daemon=True
        )
        self.privileged_user_refresh_thread.start()

        if "chat_auto_dj" in self.cb_events.active_components:
            logger.debug("thread.queue.start",
                        message="Starting song queue check thread")
            self.song_queue_check_thread = threading.Thread(
                target=self.song_queue_check, args=(), daemon=True
            )
            self.song_queue_check_thread.start()

    async def stop(self):
        """Stop the event handler and cleanup resources."""
        # Set stop event first to signal all threads to stop
        self._stop_event.set()

        # Stop all threads
        threads = [
            self.watcher_thread,
            self.event_thread,
            self.privileged_user_refresh_thread
        ]

        if hasattr(self, 'song_queue_check_thread'):
            threads.append(self.song_queue_check_thread)

        # Then stop each thread with a timeout
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=5)  # Give each thread 5 seconds to stop

        # Clean up MongoDB connection
        if self.mongo_client:
            self.mongo_client.close()

        # Stop any active Spotify playback silently
        if hasattr(self, 'cb_events') and hasattr(self.cb_events, 'actions'):
            if hasattr(self.cb_events.actions, 'auto_dj'):
                try:
                    self.cb_events.actions.auto_dj.clear_playback_context(silent=True)
                except Exception:
                    # Ignore Spotify errors during shutdown
                    pass

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


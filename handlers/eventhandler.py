import logging
import queue
import threading
import time
import urllib.parse

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from helpers.cbevents import CBEvents

logger = logging.getLogger('mongobate.handlers.eventhandler')
logger.setLevel(logging.DEBUG)


class EventHandler:

    def __init__(self, **kwargs):
        """Initialize EventHandler with MongoDB connection settings.
        
        Args:
            **kwargs: Connection settings:
                - mongo_username (str): MongoDB username
                - mongo_password (str): MongoDB password
                - mongo_host (str): MongoDB host
                - mongo_port (int): MongoDB port
                - mongo_db (str): MongoDB database name
                - mongo_collection (str): MongoDB collection name
                - user_collection (str, optional): User collection name
                - vip_refresh_interval (int, optional): VIP refresh interval in seconds
                - admin_refresh_interval (int, optional): Admin refresh interval in seconds
                - action_refresh_interval (int, optional): Action refresh interval in seconds
                - aws_key (str, optional): AWS access key
                - aws_secret (str, optional): AWS secret key
        """
        self.event_queue = queue.Queue()
        self._stop_event = threading.Event()

        self.cb_events = CBEvents()
        self.checks = self.cb_events.checks
        self.commands = self.cb_events.commands

        self.mongo_connection_uri = None
        aws_key = kwargs.get('aws_key')
        aws_secret = kwargs.get('aws_secret')
        mongo_host = kwargs.get('mongo_host')
        mongo_port = kwargs.get('mongo_port')
        mongo_username = kwargs.get('mongo_username')
        mongo_password = kwargs.get('mongo_password')
        mongo_db = kwargs.get('mongo_db')
        mongo_collection = kwargs.get('mongo_collection')
        user_collection = kwargs.get('user_collection')

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

            # Initialize user collection if needed for VIP audio or command parser
            self.user_collection = None
            if "vip_audio" in self.cb_events.active_components or "command_parser" in self.cb_events.active_components:
                if user_collection is not None:
                    self.user_collection = self.mongo_db[user_collection]

        except ConnectionFailure as error:
            logger.exception(f"Could not connect to MongoDB: {error}")
            raise

        self.vip_users = None
        self.admin_users = None
        self.action_users = None

        if 'vip_audio' in self.cb_events.active_components and self.user_collection is not None:
            self.vip_users = {}
            self.vip_refresh_interval = kwargs.get('vip_refresh_interval', 300)
            self.load_vip_users()
        
        if 'command_parser' in self.cb_events.active_components and self.user_collection is not None:
            self.admin_users = {}
            self.admin_refresh_interval = kwargs.get('admin_refresh_interval', 300)
            self.load_admin_users()
        
        if 'custom_actions' in self.cb_events.active_components and self.user_collection is not None:
            self.action_users = {}
            self.action_refresh_interval = kwargs.get('action_refresh_interval', 300)
            self.load_action_users()

    def load_vip_users(self):
        try:
            vip_users = self.user_collection.find({'vip': True, 'active': True})
            for user in vip_users:
                logger.debug(f"user: {user}")
                self.vip_users[user['username']] = user['audio_file']
            logger.info(f"Loaded {len(self.vip_users)} VIP users.")
        except Exception as error:
            logger.exception("Error loading VIP users:", exc_info=error)
    
    def load_admin_users(self):
        try:
            admin_users = self.user_collection.find({'admin': True, 'active': True})
            for user in admin_users:
                logger.debug(f"user: {user}")
                self.admin_users[user['username']] = True
            logger.info(f"Loaded {len(self.admin_users)} admin users.")
        except Exception as error:
            logger.exception("Error loading admin users:", exc_info=error)

    def load_action_users(self):
        try:
            action_users = self.user_collection.find({'action': True, 'active': True})
            for user in action_users:
                logger.debug(f"user: {user}")
            
                self.action_users[user['username']] = user['custom']
            logger.info(f"Loaded {len(self.action_users)} action users.")
        except Exception as error:
            logger.exception("Error loading action users:", exc_info=error)

    def privileged_user_refresh(self):
        last_load_vip = time.time()
        last_load_admin = time.time()
        last_load_action = time.time()
        while not self._stop_event.is_set():
            if time.time() - last_load_vip > self.vip_refresh_interval:
                self.load_vip_users()
                last_load_vip = time.time()
            if time.time() - last_load_admin > self.admin_refresh_interval:
                self.load_admin_users()
                last_load_admin = time.time()
            if time.time() - last_load_action > self.action_refresh_interval:
                self.load_action_users()
                last_load_action = time.time()

            time.sleep(1)

    def song_queue_check(self):
        while not self._stop_event.is_set():
            song_queue_status = self.cb_events.actions.auto_dj.check_queue_status()
            #logger.debug(f"song_queue_status: {song_queue_status}")
            time.sleep(5)

    def process_event(self, _event):
        """Process an event from the queue."""
        try:
            logger.info("Processing event.")
            return True
        except Exception as error:
            logger.exception("Error processing event", exc_info=error)
            return False

    def event_processor(self):
        """
        Continuously process events from the event queue.
        """
        while not self._stop_event.is_set():
            try:
                # Timeout to check for stop signal
                event = self.event_queue.get(timeout=1)
                self.process_event(event)
                self.event_queue.task_done()
            except queue.Empty:
                continue  # Resume loop if no event and check for stop signal
            except Exception as error:
                logger.exception("Error in event processor", exc_info=error)

    def watch_changes(self):
        """
        Watch for changes in the MongoDB collection.
        """
        try:
            # Set up the change stream with a resume token
            with self.event_collection.watch() as stream:
                while not self._stop_event.is_set():
                    # Use a timeout to periodically check for stop signal
                    try:
                        change = next(stream, None)
                        if change:
                            logger.debug(f"Change detected: {change}")
                            self.event_queue.put(change)
                    except StopIteration:
                        continue
        except Exception as error:
            if not self._stop_event.is_set():  # Only log if not shutting down
                logger.exception("Error watching changes", exc_info=error)

    def update_user_list(self):
        """
        Update the list of users from MongoDB.
        """
        try:
            if self.user_collection is None:
                logger.warning("No user collection available")
                return False

            vip_users = []
            admin_users = []
            action_users = []

            for user in self.user_collection.find():
                if user.get('vip', False):
                    vip_users.append(user['username'])
                if user.get('admin', False):
                    admin_users.append(user['username'])
                if user.get('custom_actions', False):
                    action_users.append(user['username'])

            self.vip_users = vip_users
            self.admin_users = admin_users
            self.action_users = action_users

            logger.debug(f"VIP Users: {self.vip_users}")
            logger.debug(f"Admin Users: {self.admin_users}")
            logger.debug(f"Action Users: {self.action_users}")

            return True
        except Exception as error:
            logger.exception("Error updating user list", exc_info=error)
            return False

    def user_list_monitor(self):
        """
        Monitor and update the user list periodically.
        """
        while not self._stop_event.is_set():
            try:
                self.update_user_list()
            except Exception as error:
                logger.exception("Error in user list monitor", exc_info=error)
            time.sleep(60)  # Update every minute

    def run(self):
        """Start all monitoring threads."""
        logger.info("Starting event handler threads...")
        
        # Start the change stream watcher thread
        self.watcher_thread = threading.Thread(
            target=self.watch_changes,
            name="watch_changes",
            daemon=True
        )
        self.watcher_thread.start()

        # Start the event processor thread
        self.processor_thread = threading.Thread(
            target=self.event_processor,
            name="event_processor",
            daemon=True
        )
        self.processor_thread.start()

        # Start the user list monitor thread if needed
        if self.user_collection is not None:
            self.monitor_thread = threading.Thread(
                target=self.user_list_monitor,
                name="user_list_monitor",
                daemon=True
            )
            self.monitor_thread.start()

    def stop(self):
        """Stop all monitoring threads and cleanup resources."""
        logger.debug("Setting stop event.")
        self._stop_event.set()

        # Wait for threads to finish with a timeout
        if hasattr(self, 'watcher_thread'):
            logger.debug(f"Joining {self.watcher_thread.name} thread.")
            self.watcher_thread.join(timeout=5)
            if self.watcher_thread.is_alive():
                logger.warning(f"{self.watcher_thread.name} thread did not stop gracefully.")

        if hasattr(self, 'processor_thread'):
            logger.debug(f"Joining {self.processor_thread.name} thread.")
            self.processor_thread.join(timeout=5)
            if self.processor_thread.is_alive():
                logger.warning(f"{self.processor_thread.name} thread did not stop gracefully.")

        if hasattr(self, 'monitor_thread'):
            logger.debug(f"Joining {self.monitor_thread.name} thread.")
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                logger.warning(f"{self.monitor_thread.name} thread did not stop gracefully.")

        # Close MongoDB connection
        if hasattr(self, 'mongo_client'):
            logger.debug("Closing MongoDB connection.")
            self.mongo_client.close()

        logger.info("Event handler stopped.")

if __name__ == "__main__":
    import configparser

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

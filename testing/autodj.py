import structlog
import sys

from spotipy import Spotify, SpotifyOAuth, SpotifyException

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger('mongobate.chatdj.autodj')


class AutoDJ:
    def __init__(self, client_id, client_secret, redirect_uri):
        # Initialize Spotify OAuth
        sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-read-private",
            open_browser=False
        )

        # Get access token
        try:
            self.spotify = Spotify(auth_manager=sp_oauth)
        except SpotifyException as e:
            logger.exception("Spotify authentication failed", exc_info=e)
            raise

        # Get and set playback device
        try:
            spotify_devices = self.spotify.devices()
            logger.debug("Spotify devices", spotify_devices=spotify_devices)

            print("\n==[ Available Spotify Devices ]==\n")
            for idx, device in enumerate(spotify_devices['devices']):
                print(f"{idx+1} - {device['name']}\n")
            
            try:
                while True:
                    user_selection = int(input("Choose playback device: "))
                    logger.debug("User selection", user_selection=user_selection)

                    if user_selection not in range(0, len(spotify_devices['devices'])):
                        logger.error("Invalid device number. Try again.")
                        continue

                    self.playback_device = spotify_devices['devices'][user_selection-1]["id"]
                    logger.debug("Playback device", playback_device=self.playback_device)
                    break
                logger.info("Activating selected playback device.")
                self.spotify.transfer_playback(device_id=self.playback_device, force_play=False)
            except KeyboardInterrupt:
                logger.info('User aborted selection. Exiting.')
                sys.exit()
        except Exception as e:
            logger.exception("Spotify playback device selection failed", exc_info=e)
            raise

    def check_active_devices(self, device_id=None):
        try:
            devices = self.spotify.devices()
            for device in devices['devices']:
                logger.debug("Device", device=device)
                if device['is_active']:
                    logger.info("Active device", device_name=device['name'], device_id=device['id'])
                    if device_id and device['id'] != device_id:
                        logger.info("Device mismatch", device_id=device['id'], expected_device_id=device_id)
                        return False
                    return True
            return False
        except SpotifyException as e:
            logger.exception("Failed to check active devices", exc_info=e)
            return False

    def find_song(self, song_info):
        """Search Spotify for a specific song."""
        try:
            find_song_query = f"{song_info['artist']} - {song_info['song']}"
            logger.debug("Find song query", find_song_query=find_song_query)
            results = self.spotify.search(q=find_song_query, type='track', limit=1)
            logger.debug("Find song results", results=results)
            return results
        except SpotifyException as e:
            logger.exception("Failed to find song", exc_info=e)
            return None
    
    def get_user_market(self):
        try:
            user_info = self.spotify.me()
            logger.debug("User info", user_info=user_info)
            return user_info['country']
        except SpotifyException as e:
            logger.exception("Failed to get user market", exc_info=e)
    
    def get_song_markets(self, track_uri):
        try:
            track_info = self.spotify.track(track_uri)
            logger.debug("Track info", track_info=track_info)
            return track_info['available_markets']
        except SpotifyException as e:
            logger.exception("Failed to get song markets", exc_info=e)
    
    def get_device_info(self, device_id):
        try:
            devices = self.spotify.devices()
            for device in devices['devices']:
                if device['id'] == device_id:
                    return device
            else:
                logger.warning("Device not found", device_id=device_id)
                return None
        except Exception as e:
            logger.exception("Failed to retrieve device information", exc_info=e)
    
    def queue_length(self):
        try:
            spotify_queue = self.spotify.queue()
            queue_length = len(spotify_queue['queue'])
            if spotify_queue['currently_playing']:
                queue_length += 1
            logger.debug("Queue length", queue_length=queue_length)
            return queue_length
        except SpotifyException as e:
            logger.exception("Failed to get queue length", exc_info=e)
            return None

    def add_song_to_queue(self, track_uri):
        try:
            if not self.check_active_devices(device_id=self.playback_device):
                logger.info("Playback device inactive. Transferring playback to device.")
                self.spotify.transfer_playback(device_id=self.playback_device, force_play=False)

            logger.info("Adding song to active playback queue.")
            self.spotify.add_to_queue(track_uri, device_id=self.playback_device)

            playback_state = self.spotify.current_playback()
            logger.debug("Playback state", playback_state=playback_state)

            if self.playback_active():
                return True

            logger.info("Starting playback.")
            self.spotify.start_playback(device_id=self.playback_device)

            return True
            
        except SpotifyException as e:
            logger.exception("Failed to add song to queue", exc_info=e)
            return False
    
    def playback_active(self):
        try:
            playback_state = self.spotify.current_playback()
            logger.debug("Playback state", playback_state=playback_state)
            if not playback_state or not playback_state['is_playing']:
                return False
            return True
        except SpotifyException as e:
            logger.exception("Failed to check if song is playing", exc_info=e)
            return False

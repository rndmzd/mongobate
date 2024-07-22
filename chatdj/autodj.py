import logging
import sys
from spotipy import Spotify, SpotifyOAuth, SpotifyException

logger = logging.getLogger('mongobate.chatdj.autodj')
logger.setLevel(logging.DEBUG)

class AutoDJ:
    def __init__(self, client_id, client_secret, redirect_uri):
        self.spotify = self.authenticate(client_id, client_secret, redirect_uri)
        self.playback_device = self.select_playback_device()

    def authenticate(self, client_id, client_secret, redirect_uri):
        sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-read-private",
            open_browser=False
        )
        try:
            return Spotify(auth_manager=sp_oauth)
        except SpotifyException as e:
            logger.exception("Spotify authentication failed", exc_info=e)
            raise

    def select_playback_device(self):
        try:
            spotify_devices = self.spotify.devices()
            logger.debug(f"spotify_devices: {spotify_devices}")

            print("\n==[ Available Spotify Devices ]==\n")
            for idx, device in enumerate(spotify_devices['devices']):
                print(f"{idx+1} - {device['name']}\n")
            
            while True:
                try:
                    user_selection = int(input("Choose playback device: "))
                    logger.debug(f"user_selection: {user_selection}")

                    if user_selection in range(1, len(spotify_devices['devices']) + 1):
                        return spotify_devices['devices'][user_selection-1]["id"]
                    else:
                        logger.error("Invalid device number. Try again.")
                except ValueError:
                    logger.error("Invalid input. Please enter a number.")
                
        except SpotifyException as e:
            logger.exception("Failed to get playback devices", exc_info=e)
            raise

    def play_song(self, track_uri):
        try:
            logger.info(f"Playing song: {track_uri}")
            if not self.playback_active():
                logger.info("No active playback. Starting new playback.")
                self.spotify.start_playback(device_id=self.playback_device, uris=[track_uri])
            else:
                logger.info("Active playback detected. Adding song to queue.")
                self.spotify.add_to_queue(track_uri, device_id=self.playback_device)
            return True
        except SpotifyException as e:
            logger.exception("Failed to play song", exc_info=e)
            return False

    def playback_active(self):
        try:
            playback_state = self.spotify.current_playback()
            return playback_state and playback_state['is_playing']
        except SpotifyException as e:
            logger.exception("Failed to check if playback is active", exc_info=e)
            return False

    def skip_song(self):
        try:
            if not self.playback_active():
                logger.info("Playback is not active.")
                return True
            self.spotify.next_track(device_id=self.playback_device)
            return True
        except SpotifyException as e:
            logger.exception("Failed to skip song", exc_info=e)
            return False

    def clear_playback_context(self):
        try:
            logger.info("Clearing the playback context.")
            silent_track_uri = "spotify:track:1q0oo1RZ8YBWlhGQ7kA1uq"
            self.spotify.start_playback(device_id=self.playback_device, uris=[silent_track_uri])
            self.spotify.pause_playback(device_id=self.playback_device)
        except SpotifyException as e:
            logger.exception("Failed to clear playback context", exc_info=e)

    def search_song(self, query):
        try:
            results = self.spotify.search(q=query, type='track')
            tracks = results.get('tracks', {})
            if tracks:
                return tracks
            else:
                logger.warning(f"No song found for query: {query}")
                return None
        except SpotifyException as e:
            logger.exception("Failed to search for song", exc_info=e)
            return None

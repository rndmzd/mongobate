import logging
import time
from typing import List, Dict, Optional

import openai
from spotipy import Spotify, SpotifyOAuth, SpotifyException

logger = logging.getLogger('mongobate.chatdj')
logger.setLevel(logging.DEBUG)

class SongExtractor:
    def __init__(self, api_key):
        self.openai_client = openai.OpenAI(api_key=api_key)

    def extract_songs(self, message, song_count=1):
        """Use OpenAI GPT-4o to extract song titles from the message."""
        try:
            response = self.openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a music bot that can extract song titles from messages."
                    },
                    {
                        "role": "user",
                        "content": f"Extract exactly {song_count} song title{'s' if song_count > 1 else ''} from the following message: '{message}'. Respond with the artist and song title for each result with one per line."
                    }
                ],
                model="gpt-4o"
            )

            logger.debug(f"response: {response}")
            print(response)

            song_titles_response = response.choices[0].message.content.strip().split('\n')
            song_titles = []
            for idx, resp in enumerate(song_titles_response):
                if ' - ' in resp:
                    artist, song = resp.split(' - ', 1)
                    song_titles.append(
                        {
                            "artist": artist.strip(),
                            "song": song.strip(),
                            "gpt": True
                        }
                    )
                else:
                    logger.warning(f"Unexpected format in response: {resp}")
                    #if len(song_titles_response) == 1 and song_count == 1:
                    if song_count == 1:
                        logger.warning("Returning original request text as song title.")
                        song_titles.append(
                            {
                                "artist": "",
                                "song": message,
                                "gpt": False
                            }
                        )

            logger.debug(f'song_titles: {song_titles}')
            logger.debug(f"len(song_titles): {len(song_titles)}")

            return song_titles

        except openai.APIError as e:
            logger.exception("Failed to extract song titles", exc_info=e)
            return []


class AutoDJ:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-read-private",
            open_browser=False
        )
        self.spotify = Spotify(auth_manager=self.sp_oauth)
        self.playback_device = self._select_playback_device()
        self.queue_active = False
        self.queued_tracks = []

    def _select_playback_device(self) -> str:
        try:
            devices = self.spotify.devices()['devices']
            logger.debug(f"Available devices: {devices}")

            if not devices:
                raise ValueError("No available Spotify devices found.")

            print("\n==[ Available Spotify Devices ]==\n")
            for idx, device in enumerate(devices):
                print(f"{idx+1} - {device['name']}")

            while True:
                try:
                    selection = int(input("\nChoose playback device number: "))
                    device = devices[selection - 1]
                    logger.info(f"Selected device: {device['name']} ({device['id']})")
                    return device['id']
                except (ValueError, IndexError):
                    print("Invalid selection. Please try again.")

        except Exception as e:
            logger.exception("Failed to select playback device", exc_info=e)
            raise

    def find_song(self, song_info):
        """Search Spotify for a specific song."""
        try:
            find_song_query = f"{song_info['artist']} {song_info['song']}"
            logger.debug(f'find_song_query: {find_song_query}')
            results = self.spotify.search(q=find_song_query, type='track')#, limit=1)
            logger.debug(f'results: {results}')
            return results
        except SpotifyException as e:
            logger.exception("Failed to find song", exc_info=e)
            return None

    def add_song_to_queue(self, track_uri: str) -> bool:
        try:
            self.spotify.add_to_queue(track_uri, device_id=self.playback_device)
            self.queued_tracks.append(track_uri)
            logger.info(f"Added track to queue: {track_uri}")

            if not self.queue_active:
                self.queue_active = True
                self.spotify.start_playback(device_id=self.playback_device)
                logger.info("Started playback")

            return True

        except SpotifyException as e:
            logger.exception("Failed to add song to queue", exc_info=e)
            return False

    def check_queue_status(self) -> bool:
        try:
            if not self.queue_active:
                return False

            playback = self.spotify.current_playback()
            
            if not playback or not playback['is_playing']:
                if not self.queued_tracks:
                    logger.info("Playback ended and queue is empty")
                    self.clear_playback_context()
                    return True
            elif playback['item']:
                current_track = playback['item']['uri']
                if self.queued_tracks and current_track == self.queued_tracks[0]:
                    logger.info(f"Now playing queued track: {current_track}")
                    self.queued_tracks.pop(0)
                elif not self.queued_tracks:
                    logger.info("Playing non-queued track, clearing context")
                    self.clear_playback_context()
                    return True

            return False

        except SpotifyException as e:
            logger.exception("Failed to check queue status", exc_info=e)
            return False

    def clear_playback_context(self):
        try:
            logger.info("Clearing playback context")
            self.spotify.pause_playback(device_id=self.playback_device)
            self.queue_active = False
            self.queued_tracks.clear()
        except SpotifyException as e:
            logger.exception("Failed to clear playback context", exc_info=e)
    
    def get_user_market(self):
        try:
            user_info = self.spotify.me()
            logger.debug(f"user_info: {user_info}")
            return user_info['country']
        except SpotifyException as e:
            logger.exception("Failed to get user market", exc_info=e)
    
    def get_song_markets(self, track_uri):
        try:
            track_info = self.spotify.track(track_uri)
            logger.debug(f"track_info: {track_info}")
            return track_info['available_markets']
        except SpotifyException as e:
            logger.exception("Failed to get song markets", exc_info=e)
    
    def playback_active(self) -> bool:
        """
        Check if there's active playback on the user's Spotify account.
        
        Returns:
            bool: True if there's active playback, False otherwise.
        """
        try:
            playback_state = self.spotify.current_playback()
            if playback_state and playback_state['is_playing']:
                logger.debug("Playback is active")
                return True
            else:
                logger.debug("No active playback")
                return False
        except SpotifyException as e:
            logger.exception("Error checking playback state", exc_info=e)
            return False

"""if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    song_extractor = SongExtractor(os.getenv('OPENAI_API_KEY'))
    auto_dj = AutoDJ(
        os.getenv('SPOTIFY_CLIENT_ID'),
        os.getenv('SPOTIFY_CLIENT_SECRET'),
        os.getenv('SPOTIFY_REDIRECT_URI')
    )

    # Example usage
    message = "Play Dancing Queen by ABBA and Bohemian Rhapsody by Queen"
    songs = song_extractor.extract_songs(message, song_count=2)

    for song in songs:
        track_uri = auto_dj.find_song(song)
        if track_uri and auto_dj.is_available_in_market(track_uri):
            auto_dj.add_song_to_queue(track_uri)

    # Main loop to check queue status
    try:
        while True:
            if auto_dj.check_queue_status():
                break
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopping playback")
        auto_dj.clear_playback_context()"""
import structlog
from typing import List, Dict, Optional
import sys
import time

import openai
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

logger = structlog.get_logger('mongobate.chatdj')

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

            logger.debug('Extracted songs', response=response)

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
                    logger.warning('Unexpected format in response', response=resp)
                    if song_count == 1:
                        logger.warning("Returning original request text as song title.")
                        song_titles.append(
                            {
                                "artist": "",
                                "song": message,
                                "gpt": False
                            }
                        )

            logger.debug('Song titles extracted', song_titles=song_titles)

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
        logger.debug("Initializing Spotify client.")
        self.spotify = Spotify(auth_manager=self.sp_oauth)
        logger.debug("Prompting user for playback device selection.")
        self.playback_device = self._select_playback_device()
        logger.debug("Clearing playback context.")
        self.playing_first_track = False
        self.queued_tracks = []
        self.clear_playback_context()

        self._print_variables()

    def _print_variables(self, return_value=None):
        pass

    def _select_playback_device(self) -> str:
        try:
            devices = self.spotify.devices()['devices']
            logger.debug("Available devices", devices=devices)

            if not devices:
                raise ValueError("No available Spotify devices found.")

            print("\n==[ Available Spotify Devices ]==\n")
            for idx, device in enumerate(devices):
                print(f"{idx+1} - {device['name']}")

            while True:
                try:
                    selection = int(input("\nChoose playback device number: "))
                    device = devices[selection - 1]
                    logger.info("Selected device", device_name=device['name'], device_id=device['id'])
                    return device['id']
                except KeyboardInterrupt:
                    logger.info("User cancelled device selection.")
                    raise
                except (ValueError, IndexError):
                    print("Invalid selection. Please try again.")
                    sys.exit()

        except Exception as e:
            logger.exception("Failed to select playback device", exc_info=e)
            raise

    def find_song(self, song_info):
        """Search Spotify for a specific song."""
        try:
            find_song_query = f"{song_info['artist']} {song_info['song']}"
            logger.debug("Find song query", query=find_song_query)
            results = self.spotify.search(q=find_song_query, type='track')
            logger.debug("Find song results", results=results)
            return results
        except SpotifyException as e:
            logger.exception("Failed to find song", exc_info=e)
            return None

    def add_song_to_queue(self, track_uri: str) -> bool:
        try:
            logger.debug("Adding track to internal queue", track_uri=track_uri)
            self.queued_tracks.append(track_uri)

            if not self.playback_active() and len(self.queued_tracks) == 1:
                self.playing_first_track = True

            logger.debug("Queued tracks", queued_tracks=self.queued_tracks)

            self._print_variables(True)
            return True

        except SpotifyException as e:
            logger.exception("Failed to add song to queue", exc_info=e)
            return False

    def check_queue_status(self) -> bool:
        try:
            if not self.playback_active():
                if len(self.queued_tracks) > 0:
                    logger.info("Queue populated but playback is not active. Starting playback.")
                    popped_track = self.queued_tracks.pop(0)
                    logger.debug("Popped track", track_uri=popped_track)
                    self.spotify.start_playback(device_id=self.playback_device, uris=[popped_track])
                    logger.debug("Clearing playing_first_track flag.")
                    self.playing_first_track = False
                    self._print_variables(True)
                    return True

                self._print_variables(False)
                return False

            if self.queued_tracks:
                current_track = self.spotify.current_playback()['item']['uri']
                logger.debug("Current track", track_uri=current_track)
                if current_track == self.queued_tracks[0]:
                    logger.info("Now playing queued track", track_uri=current_track)
                    self.queued_tracks.pop(0)

            self._print_variables(True)
            return True

        except SpotifyException as e:
            logger.exception("Failed to check queue status", exc_info=e)
            return False

    def clear_playback_context(self):
        try:
            logger.info("Clearing playback context.")
            if self.playback_active():
                self.spotify.pause_playback(device_id=self.playback_device)
            previous_track = None
            attempts = 0
            max_attempts = 5

            while True:
                queue = self.spotify.queue()

                if len(queue['queue']) == 0:
                    print("Queue is now empty")
                    break

                current_track = queue['queue'][0]['uri']
                if current_track == previous_track:
                    attempts += 1
                    if attempts >= max_attempts:
                        print("Unable to clear the last track. Stopping.")
                        break
                else:
                    attempts = 0

                try:
                    self.spotify.next_track()
                    print(f"Skipped track: {queue['queue'][0]['name']}")
                    time.sleep(1)
                except SpotifyException as e:
                    logger.error("Error skipping track", exc_info=e)
                    break

                previous_track = current_track

            try:
                self.spotify.pause_playback()
                logger.info("Playback paused.")
            except SpotifyException as e:
                logger.error("Error pausing playback", exc_info=e)

            self.playing_first_track = False
            self.queued_tracks.clear()

            self._print_variables(True)
            return True

        except SpotifyException as e:
            logger.exception("Failed to clear playback context.", exc_info=e)
            return False

    def get_user_market(self):
        try:
            user_info = self.spotify.me()
            logger.debug("User info", user_info=user_info)
            return user_info['country']
        except SpotifyException as e:
            logger.exception("Failed to get user market.", exc_info=e)

    def get_song_markets(self, track_uri):
        try:
            if track_info := self.spotify.track(track_uri):
                logger.debug("Track info", track_info=track_info)
                return track_info['available_markets']
            return []
        except SpotifyException as e:
            logger.exception("Failed to get song markets.", exc_info=e)

    def playback_active(self) -> bool:
        try:
            if (playback_state := self.spotify.current_playback()) and playback_state['is_playing']:
                logger.debug("Playback is active.")
                return True
            else:
                return False
        except SpotifyException as e:
            logger.exception("Error checking playback state.", exc_info=e)
            return False

    def skip_song(self):
        try:
            if not self.playback_active():
                logger.info("Playback is not active.")
                return True
            self.spotify.next_track(device_id=self.playback_device)
            return True
        except SpotifyException as e:
            logger.exception("Failed to skip song.", exc_info=e)
            return False

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from pprint import pprint

    load_dotenv()

    song_extractor = SongExtractor(os.getenv('OPENAI_API_KEY'))
    auto_dj = AutoDJ(
        os.getenv('SPOTIFY_CLIENT_ID'),
        os.getenv('SPOTIFY_CLIENT_SECRET'),
        os.getenv('SPOTIFY_REDIRECT_URI')
    )

    queue = auto_dj.spotify.queue()
    print()
    print(len(queue['queue']))
    [print(i['name']) for i in queue['queue']]

    auto_dj.clear_playback_context()

    queue = auto_dj.spotify.queue()
    print()
    print(len(queue['queue']))
    [print(i['name']) for i in queue['queue']]

    message = "Play Dancing Queen by ABBA and Bohemian Rhapsody by Queen"
    songs = song_extractor.extract_songs(message, song_count=2)

    for song in songs:
        if track_uri := auto_dj.find_song(song)['tracks']['items'][0]['uri']:
            if auto_dj.get_user_market() in auto_dj.get_song_markets(track_uri):
                auto_dj.add_song_to_queue(track_uri)
            else:
                logger.warning("Song not available in user's market. Skipping.")

    try:
        while True:
            if not auto_dj.check_queue_status():
                break
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Exit signal received. Stopping playback.")
        auto_dj.clear_playback_context()

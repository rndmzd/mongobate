import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import openai

logger = logging.getLogger('mongobate.chatdj.chatdj')

class SongExtractor:
    def __init__(self, api_key):
        """Initialize the song extractor with OpenAI API key."""
        self.api_key = api_key
        openai.api_key = api_key

    def extract_songs(self, message, song_count=1):
        """Extract song titles from a message."""
        try:
            response = openai.Client().chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts song titles and artists from messages."},
                    {"role": "user", "content": f"Extract up to {song_count} song titles and artists from this message: {message}"}
                ],
                temperature=0.7,
                max_tokens=150
            )
            content = response.choices[0].message.content
            logger.debug(f"OpenAI response: {content}")
            return self._parse_response(content)
        except Exception as error:
            logger.exception(f"Error extracting songs: {error}")
            return []

    def _parse_response(self, content):
        """Parse the OpenAI response to extract song information."""
        try:
            songs = []
            lines = content.split('\n')
            for line in lines:
                if ' - ' in line:
                    artist, song = line.split(' - ', 1)
                    songs.append({
                        'artist': artist.strip(),
                        'song': song.strip()
                    })
            return songs
        except Exception as error:
            logger.exception(f"Error parsing response: {error}")
            return []

class AutoDJ:
    def __init__(self, client_id, client_secret, redirect_uri):
        """Initialize the AutoDJ with Spotify credentials."""
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.sp = None
        self.connect()

    def connect(self):
        """Connect to Spotify API."""
        try:
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope="user-modify-playback-state user-read-playback-state"
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            return True
        except Exception as error:
            logger.exception(f"Error connecting to Spotify: {error}")
            return False

    def find_song(self, song_info):
        """Find a song on Spotify."""
        try:
            query = f"artist:{song_info['artist']} track:{song_info['song']}"
            return self.sp.search(q=query, type='track', limit=20)
        except Exception as error:
            logger.exception(f"Error finding song: {error}")
            return None

    def get_user_market(self):
        """Get the user's market from Spotify."""
        try:
            user = self.sp.current_user()
            return user['country']
        except Exception as error:
            logger.exception(f"Error getting user market: {error}")
            return None

    def get_song_markets(self, song_uri):
        """Get available markets for a song."""
        try:
            track = self.sp.track(song_uri)
            return track['available_markets']
        except Exception as error:
            logger.exception(f"Error getting song markets: {error}")
            return []

    def add_song_to_queue(self, song_uri):
        """Add a song to the playback queue."""
        try:
            self.sp.add_to_queue(song_uri)
            return True
        except Exception as error:
            logger.exception(f"Error adding song to queue: {error}")
            return False

    def skip_song(self):
        """Skip the current song."""
        try:
            self.sp.next_track()
            return True
        except Exception as error:
            logger.exception(f"Error skipping song: {error}")
            return False

    def playback_active(self):
        """Check if playback is active."""
        try:
            playback = self.sp.current_playback()
            return playback is not None and playback['is_playing']
        except Exception as error:
            logger.exception(f"Error checking playback state: {error}")
            return False

    def check_queue_status(self):
        """Check the current queue status."""
        try:
            queue = self.sp.queue()
            if queue and 'queue' in queue:
                logger.info("Current queue:")
                for track in queue['queue']:
                    logger.info(f"- {track['name']}")
            return queue
        except Exception as error:
            logger.exception(f"Error checking queue status: {error}")
            return None

if __name__ == "__main__":
    # Example usage
    import configparser

    config = configparser.ConfigParser()
    config.read("config.ini")

    auto_dj = AutoDJ(
        client_id=config.get("Spotify", "client_id"),
        client_secret=config.get("Spotify", "client_secret"),
        redirect_uri=config.get("Spotify", "redirect_url")
    )

    queue = auto_dj.check_queue_status()
    if queue and 'queue' in queue:
        logger.info("Current queue:")
        for track in queue['queue']:
            logger.info(f"- {track['name']}")

    song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
    TEST_MESSAGE = "Can you play Shape of You by Ed Sheeran?"
    songs = song_extractor.extract_songs(TEST_MESSAGE)
    logger.info(f"Extracted songs: {songs}")

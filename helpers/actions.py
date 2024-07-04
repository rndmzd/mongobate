import configparser
import logging

from chatdj import SongExtractor, AutoDJ

logger = logging.getLogger('mongobate.helpers.actions')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")

class Actions:
    def __init__(self):
        self.song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
        self.auto_dj = AutoDJ(
            config.get("Spotify", "client_id"),
            config.get("Spotify", "client_secret"),
            config.get("Spotify", "redirect_url")
        )

    def extract_song_titles(self, message, song_count):
        return self.song_extractor.find_titles(message, song_count)
    
    def find_song_spotify(self, song_info):
        tracks = self.auto_dj.find_song(song_info)['tracks']
        logger.debug(f'tracks: {tracks}')
        if tracks:
            top_result = tracks['items'][0]
            logger.debug(f'top_result: {top_result}')
            return top_result['uri']
        logger.warning(f'No tracks found for {song_info}')
        return None
    
    def available_in_market(self, song_uri):
        user_market = self.auto_dj.get_user_market()
        logger.debug(f'user_market: {user_market}')
        song_markets = self.auto_dj.get_song_markets(song_uri)
        logger.debug(f'song_markets: {song_markets}')
        if user_market in song_markets:
            return True
        return False
    
    def add_song_to_queue(self, uri):
        return self.auto_dj.add_song_to_queue(uri)
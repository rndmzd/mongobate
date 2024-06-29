import configparser
import logging

from chatdj import SongExtractor, AutoDJ

logger = logging.getLogger('eventhandler.actions')
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
        tracks = self.auto_dj.find_song(song_info)
        logger.debug(f'tracks: {tracks}')
        if tracks:
            return tracks[0]['uri']
        return None
    
    def add_song_to_queue(self, uri):
        return self.auto_dj.add_song_to_queue(uri)
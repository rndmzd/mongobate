import configparser
import logging
from functools import lru_cache
import threading
import time

from rapidfuzz import fuzz

logger = logging.getLogger('mongobate.helpers.actions')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")

class Actions:
    def __init__(self, chatdj=False, vip_audio=False, command_parser=False):
        if chatdj:
            from chatdj import SongExtractor, AutoDJ

            self.song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
            self.auto_dj = AutoDJ(
                config.get("Spotify", "client_id"),
                config.get("Spotify", "client_secret"),
                config.get("Spotify", "redirect_url")
            )

            self._song_cache = {}

            self.queue_check_thread = None
            self.stop_queue_check = threading.Event()

            self.start_queue_check()
    
    def _cache_key(self, song_info):
        return f"{song_info['artist']}:{song_info['song']}"
    
    def _custom_score(self, query_artist, query_song, result_artist, result_song):
        artist_ratio = fuzz.ratio(query_artist.lower(), result_artist.lower())
        song_ratio = fuzz.ratio(query_song.lower(), result_song.lower())
        
        # Heavily weight exact artist matches
        if artist_ratio == 100:
            artist_score = 100
        else:
            artist_score = artist_ratio * 0.5  # Reduce weight of non-exact artist matches
        
        # Combine scores, prioritizing artist match
        combined_score = (artist_score * 0.7) + (song_ratio * 0.3)
        
        return combined_score

    def extract_song_titles(self, message, song_count):
        return self.song_extractor.find_titles(message, song_count)
    
    def get_playback_state(self):
        return self.auto_dj.playback_active()
    
    def find_song_spotify(self, song_info):
        cache_key = self._cache_key(song_info)
        if cache_key in self._song_cache:
            logger.debug(f"Cache hit for {cache_key}")
            return self._song_cache[cache_key]
        
        tracks = self.auto_dj.find_song(song_info)['tracks']
        logger.debug(f'tracks: {tracks}')
        if not tracks or not tracks['items']:
            logger.warning(f'No tracks found for {song_info}')
            return None

        results = []
        for track in tracks['items'][:20]:  # Increased to top 20 results for better coverage
            artist_name = track['artists'][0]['name']
            song_name = track['name']
            
            score = self._custom_score(song_info['artist'], song_info['song'], artist_name, song_name)
            
            results.append({
                'uri': track['uri'],
                'artist': artist_name,
                'song': song_name,
                'match_ratio': score
            })
        
        # Sort results by our custom score
        optimized_results = sorted(results, key=lambda x: x['match_ratio'], reverse=True)[:5]
        
        logger.debug(f'Custom match results: {optimized_results}')

        # Cache the results
        self._song_cache[cache_key] = optimized_results
        
        # Limit cache size to prevent memory issues
        if len(self._song_cache) > 1000:
            self._song_cache.pop(next(iter(self._song_cache)))

        # return optimized_results
        return optimized_results[0]['uri']
    
    def available_in_market(self, song_uri):
        user_market = self.auto_dj.get_user_market()
        logger.debug(f'user_market: {user_market}')
        song_markets = self.auto_dj.get_song_markets(song_uri)
        logger.debug(f'song_markets: {song_markets}')
        if user_market in song_markets:
            return True
        return False
    
    def add_song_to_queue(self, uri):
        logger.debug('Executing add song to queue action helper.')
        return self.auto_dj.add_song_to_queue(uri)
    
    def start_queue_check(self):
        if self.queue_check_thread is None or not self.queue_check_thread.is_alive():
            logger.debug("Clearning stop queue check event.")
            self.stop_queue_check.clear()
            self.queue_check_thread = threading.Thread(target=self.queue_check_loop)
            logger.debug("Starting queue check thread.")
            self.queue_check_thread.start()
            logger.info("Queue check thread started.")

    def stop_queue_check(self):
        if self.queue_check_thread and self.queue_check_thread.is_alive():
            logger.info("Stopping queue check thread.")
            self.stop_queue_check.set()
            logger.debug("Joining queue check thread.")
            self.queue_check_thread.join()
            logger.info("Queue check thread stopped.")

    def queue_check_loop(self):
        while not self.stop_queue_check.is_set():
            if self.auto_dj.check_queue_end():
                logger.info("Queue playback ended and cleared.")
            time.sleep(5)
    
    def skip_song(self):
        logger.debug('Executing skip song action helper.')
        return self.auto_dj.skip_song()
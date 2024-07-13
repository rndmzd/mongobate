import configparser
import logging
from functools import lru_cache

from rapidfuzz import fuzz, process

logger = logging.getLogger('mongobate.helpers.actions')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")

class Actions:
    def __init__(self, chatdj=False):
        if chatdj:
            from chatdj import SongExtractor, AutoDJ

            self.song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
            self.auto_dj = AutoDJ(
                config.get("Spotify", "client_id"),
                config.get("Spotify", "client_secret"),
                config.get("Spotify", "redirect_url")
            )

            self._song_cache = {}
    
    def _cache_key(self, song_info):
        return f"{song_info['artist']}:{song_info['song']}"

    def extract_song_titles(self, message, song_count):
        return self.song_extractor.find_titles(message, song_count)
    
    def get_playback_state(self):
        return self.auto_dj.playback_active()
    
    def find_song_spotify(self, song_info):
        cache_key = self._cache_key(song_info)
        if cache_key in self._song_cache:
            logger.debug(f"Cache hit for {cache_key}")
            return self._song_cache[cache_key]
        
        query = f"{song_info['artist']} {song_info['song']}"
        tracks = self.auto_dj.find_song({'song': query})['tracks']
        logger.debug(f'tracks: {tracks}')
        if not tracks or not tracks['items']:
            logger.warning(f'No tracks found for {song_info}')
            return None

        results = []
        for track in tracks['items'][:10]:
            artist_name = track['artists'][0]['name']
            song_name = track['name']
            
            combined_ratio = fuzz.WRatio(f"{song_info['artist']} {song_info['song']}",
                                         f"{artist_name} {song_name}")
            
            results.append({
                'uri': track['uri'],
                'artist': artist_name,
                'song': song_name,
                'match_ratio': combined_ratio
            })
        
        best_matches = process.extract(
            f"{song_info['artist']} {song_info['song']}",
            [(r['artist'] + ' ' + r['song'], r) for r in results],
            limit=5,
            scorer=fuzz.WRatio
        )
        
        optimized_results = [song_info for (matched_string, song_info, score) in best_matches]
        
        logger.debug(f'Fuzzy match results: {optimized_results}')

        self._song_cache[cache_key] = optimized_results
        
        # Limit cache size to prevent memory issues
        if len(self._song_cache) > 1000:
            self._song_cache.pop(next(iter(self._song_cache)))

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
    
    def skip_song(self):
        logger.debug('Executing skip song action helper.')
        return self.auto_dj.skip_song()
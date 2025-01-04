import logging
from typing import Dict, List, Optional

from rapidfuzz import fuzz
import requests

logger = logging.getLogger('mongobate.helpers.actions')
logger.setLevel(logging.DEBUG)

class Actions:
    def __init__(self,
                 chatdj: bool = False,
                 vip_audio: bool = False,
                 command_parser: bool = False,
                 custom_actions: bool = False,
                 spray_bottle: bool = False,
                 couch_buzzer: bool = False):
        self.chatdj_enabled = chatdj
        self.vip_audio_enabled = vip_audio
        self.command_parser_enabled = command_parser
        self.custom_actions_enabled = custom_actions
        self.spray_bottle_enabled = spray_bottle
        self.couch_buzzer_enabled = couch_buzzer

        if self.chatdj_enabled:
            from chatdj import SongExtractor, AutoDJ
            from . import config, song_cache_collection

            self.song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
            self.auto_dj = AutoDJ(
                config.get("Spotify", "client_id"),
                config.get("Spotify", "client_secret"),
                config.get("Spotify", "redirect_url")
            )
            self.song_cache_collection = song_cache_collection
        
        if self.spray_bottle_enabled:
            self.spray_bottle_url = config.get("General", "spray_bottle_url")

        if self.custom_actions_enabled:
            self.custom_action_url = config.get("Custom Actions", "url")
        
        if self.couch_buzzer_enabled:
            self.couch_buzzer_url = config.get("General", "couch_buzzer_url")
            self.couch_buzzer_username = config.get("General", "couch_buzzer_username")
            self.couch_buzzer_password = config.get("General", "couch_buzzer_password")

    def get_cached_song(self, song_info: Dict[str, str]) -> Optional[Dict]:
        """Retrieve a cached song from MongoDB."""
        try:
            cached_song = self.song_cache_collection.find_one({'artist': song_info['artist'].lower(), 'song': song_info['song'].lower()})
            logger.debug(f'Cached song: {cached_song}')
            return cached_song
        except Exception as e:
            logger.exception('Failed to retrieve cached song.', exc_info=e)
            return None

    def cache_song(self, song_info: Dict[str, str], optimized_results: List[Dict]) -> bool:
        """Cache a song and its optimized results in MongoDB."""
        try:
            doc = {
                'artist': song_info['artist'].lower(),
                'song': song_info['song'].lower(),
                'optimized_results': optimized_results
            }
            inserted_id = self.song_cache_collection.insert_one(doc).inserted_id
            logger.debug(f'Inserted cache document ID: {inserted_id}')
            return True
        except Exception as e:
            logger.exception('Failed to save cached song.', exc_info=e)
            return False

    def _custom_score(self, query_artist: str, query_song: str, result_artist: str, result_song: str) -> float:
        """Calculate a custom matching score for artist and song."""
        artist_ratio = fuzz.ratio(query_artist.lower(), result_artist.lower())
        song_ratio = fuzz.ratio(query_song.lower(), result_song.lower())
        
        artist_score = 100 if artist_ratio == 100 else artist_ratio * 0.5
        combined_score = (artist_score * 0.7) + (song_ratio * 0.3)
        
        logger.debug(f'Artist ratio: {artist_ratio}, Song ratio: {song_ratio}, Combined score: {combined_score}')
        return combined_score

    def extract_song_titles(self, message: str, song_count: int) -> List[Dict[str, str]]:
        """Extract song titles from a message."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return []
        return self.song_extractor.extract_songs(message, song_count)

    def get_playback_state(self) -> bool:
        """Get the current playback state."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return False
        try:
            return self.auto_dj.playback_active()
        except Exception as e:
            logger.exception("Error getting playback state", exc_info=e)
            return False

    def find_song_spotify(self, song_info: Dict[str, str]) -> Optional[str]:
        """Find a song on Spotify, using cache if available."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return None

        cached_song = self.get_cached_song(song_info)
        if cached_song:
            logger.debug(f"Cache hit for {song_info}.")
            return cached_song['optimized_results'][0]['uri']

        try:
            tracks = self.auto_dj.find_song(song_info)['tracks']
            if not tracks or not tracks['items']:
                logger.warning(f'No tracks found for {song_info}.')
                return None

            results = []
            for track in tracks['items'][:20]:
                artist_name = track['artists'][0]['name']
                song_name = track['name']
                score = self._custom_score(song_info['artist'], song_info['song'], artist_name, song_name)
                results.append({
                    'uri': track['uri'],
                    'artist': artist_name,
                    'song': song_name,
                    'match_ratio': score
                })

            optimized_results = sorted(results, key=lambda x: x['match_ratio'], reverse=True)[:5]
            logger.debug(f'Custom match results: {optimized_results}')

            if self.cache_song(song_info, optimized_results):
                logger.info(f"Cached optimized results for {song_info}.")
            else:
                logger.warning(f"Failed to cache optimized results for {song_info}.")

            return optimized_results[0]['uri']
        except Exception as e:
            logger.exception(f"Error finding song on Spotify: {e}")
            return None

    def available_in_market(self, song_uri: str) -> bool:
        """Check if a song is available in the user's market."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return False

        try:
            user_market = self.auto_dj.get_user_market()
            song_markets = self.auto_dj.get_song_markets(song_uri)
            logger.debug(f'User market: {user_market}, Song markets: {song_markets}')
            return user_market in song_markets
        except Exception as e:
            logger.exception(f"Error checking market availability: {e}")
            return False

    def add_song_to_queue(self, uri: str) -> bool:
        """Add a song to the playback queue."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return False

        logger.debug('Executing add song to queue action.')
        try:
            return self.auto_dj.add_song_to_queue(uri)
        except Exception as e:
            logger.exception(f"Error adding song to queue: {e}")
            return False

    def skip_song(self) -> bool:
        """Skip the currently playing song."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return False

        logger.debug('Executing skip song action.')
        try:
            return self.auto_dj.skip_song()
        except Exception as e:
            logger.exception(f"Error skipping song: {e}")
            return False
    
    ## TODO: Refactor to use a single function for post requests
    def trigger_spray(self) -> bool:
        """Trigger the spray bottle action."""
        # if not self.spray_bottle_enabled:
        #    logger.warning("Spray bottle is not enabled.")
        #    return False

        logger.debug('Executing spray bottle action.')
        try:
            data = {
                "sprayAction": True
            }
            response = requests.post(self.spray_bottle_url, data=data)
            if response.status_code == 200:
                logger.info("Success:", response.json())
                return True
            else:
                logger.error("Request failed with status code:", response.status_code)
                logger.error("Response:", response.text)
            return False
        except Exception as e:
            logger.exception(f"Error triggering spray bottle: {e}")
            return False
    
    ## TODO: Refactor to use a single function for post requests
    def trigger_couch_buzzer(self, duration=1) -> bool:
        """Send a post request to a specified URL."""
        try:
            data = {
                "duration": duration
            }
            response = requests.post(self.couch_buzzer_url, json=data, auth=(self.couch_buzzer_username, self.couch_buzzer_password))
            if response.status_code == 200:
                logger.info("Success:", response.json())
                return True
            else:
                logger.error("Request failed with status code:", response.status_code)
                logger.error("Response:", response.text)
            return False
        except Exception as e:
            logger.exception(f"Error triggering couch buzzer: {e}")
            return False


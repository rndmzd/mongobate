import logging
from typing import Dict, List, Optional

from rapidfuzz import fuzz
import requests
import base64

logger = logging.getLogger('mongobate.helpers.actions')
logger.setLevel(logging.DEBUG)

# Create a base HTTP request handler class to handle common request functionality
class HTTPRequestHandler:
    def make_request(self, url: str, data: dict, auth: tuple = None) -> bool:
        """Make a POST request with error handling and logging."""
        try:
            response = requests.post(url, data=data, auth=auth)
            if response.status_code == 200:
                logger.info(f"Success: {response.json() if response.text else 'No response body'}")
                return True
            else:
                logger.error(f"Request failed with status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
            return False
        except Exception as e:
            logger.exception(f"Error making HTTP request: {e}")
            return False

class Actions(HTTPRequestHandler):
    def __init__(self,
                 chatdj: bool = False,
                 vip_audio: bool = False,
                 command_parser: bool = False,
                 custom_actions: bool = False,
                 spray_bottle: bool = False,
                 couch_buzzer: bool = False,
                 obs_integration: bool = False):
        self.chatdj_enabled = chatdj
        logger.debug(f"ChatDJ enabled: {self.chatdj_enabled}")
        self.vip_audio_enabled = vip_audio
        logger.debug(f"VIP Audio enabled: {self.vip_audio_enabled}")
        self.command_parser_enabled = command_parser
        logger.debug(f"Command Parser enabled: {self.command_parser_enabled}")
        self.custom_actions_enabled = custom_actions
        logger.debug(f"Custom Actions enabled: {self.custom_actions_enabled}")
        self.spray_bottle_enabled = spray_bottle
        logger.debug(f"Spray Bottle enabled: {self.spray_bottle_enabled}")
        self.couch_buzzer_enabled = couch_buzzer
        logger.debug(f"Couch Buzzer enabled: {self.couch_buzzer_enabled}")
        self.obs_integration_enabled = obs_integration
        logger.debug(f"OBS Integration enabled: {self.obs_integration_enabled}")

        from . import config

        if self.chatdj_enabled:
            from chatdj import SongExtractor, AutoDJ
            from . import song_cache_collection

            self.song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
            self.auto_dj = AutoDJ(
                config.get("Spotify", "client_id"),
                config.get("Spotify", "client_secret"),
                config.get("Spotify", "redirect_url")
            )
            self.song_cache_collection = song_cache_collection
        
        if self.spray_bottle_enabled:
            self.spray_bottle_url = config.get("General", "spray_bottle_url")
            logger.debug(f"self.spray_bottle_url: {self.spray_bottle_url}")
        
        if self.couch_buzzer_enabled:
            self.couch_buzzer_url = config.get("General", "couch_buzzer_url")
            self.couch_buzzer_username = config.get("General", "couch_buzzer_username")
            self.couch_buzzer_password = config.get("General", "couch_buzzer_password")
            logger.debug(f"self.couch_buzzer_url: {self.couch_buzzer_url}")

        if self.obs_integration_enabled:
            from handlers.obshandler import OBSHandler
            self.obs = OBSHandler(
                host=config.get("OBS", "host"),
                port=config.getint("OBS", "port"),
                password=config.get("OBS", "password")
            )
            if self.obs.connect_sync():
                logger.info("Successfully connected to OBS")
            else:
                logger.error("Failed to connect to OBS")
            
            if self.chatdj_enabled:
                self.request_overlay_duration = config.getint("General", "request_overlay_duration")

    def __del__(self):
        if hasattr(self, 'obs') and self.obs_integration_enabled:
            self.obs.disconnect_sync()

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

    def add_song_to_queue(self, uri: str, requester_name: str, song_details: str) -> bool:
        """Add a song to the playback queue and trigger the song requester overlay."""
        if not self.chatdj_enabled:
            logger.warning("ChatDJ is not enabled.")
            return False

        logger.debug('Executing add song to queue action.')
        try:
            if self.auto_dj.add_song_to_queue(uri):
                self.trigger_song_requester_overlay(requester_name, song_details, self.request_overlay_duration if self.request_overlay_duration else 10)
                return True
            return False
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
    
    def trigger_spray(self) -> bool:
        """Trigger the spray bottle action."""
        logger.debug('Executing spray bottle action.')
        return self.make_request(self.spray_bottle_url, {"sprayAction": True})
    
    def trigger_couch_buzzer(self, duration=1) -> bool:
        """Trigger the couch buzzer action."""
        credentials = f"{self.couch_buzzer_username}:****"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return self.make_request(
            self.couch_buzzer_url,
            {"duration": duration, "auth": encoded_credentials}
        )

    def set_scene(self, scene_name: str) -> bool:
        """Set the current OBS scene."""
        if not self.obs_integration_enabled:
            logger.warning("OBS Handler is not enabled.")
            return False
        return self.obs.set_scene_sync(scene_name)

    def get_current_scene(self) -> Optional[str]:
        """Get the current OBS scene name."""
        if not self.obs_integration_enabled:
            logger.warning("OBS Handler is not enabled.")
            return None
        return self.obs.get_current_scene_sync()

    def set_source_visibility(self, scene_name: str, source_name: str, visible: bool) -> bool:
        """Set the visibility of an OBS source."""
        if not self.obs_integration_enabled:
            logger.warning("OBS Handler is not enabled.")
            return False
        return self.obs.set_source_visibility_sync(scene_name, source_name, visible)

    def get_source_visibility(self, scene_name: str, source_name: str) -> Optional[bool]:
        """Get the visibility state of an OBS source."""
        if not self.obs_integration_enabled:
            logger.warning("OBS Handler is not enabled.")
            return None
        return self.obs.get_source_visibility_sync(scene_name, source_name)

    def trigger_song_requester_overlay(self, requester_name: str, song_details: str, display_duration: int = 10) -> None:
        """Trigger the song requester overlay to show and then hide after a duration."""
        if not self.obs_integration_enabled:
            logger.warning("OBS Handler is not enabled.")
            return
        self.obs.trigger_song_requester_overlay_sync(requester_name, song_details, display_duration)

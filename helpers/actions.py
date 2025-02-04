from typing import Dict, List, Optional

from rapidfuzz import fuzz
import requests
import base64

from utils.structured_logging import get_structured_logger
from helpers.checks import Checks  # Import the Checks class instead of individual method

logger = get_structured_logger('mongobate.helpers.actions')

# Create a base HTTP request handler class to handle common request functionality
class HTTPRequestHandler:
    def make_request(self, url: str, data: dict, auth: tuple = None) -> bool:
        """Make a POST request with error handling and logging."""
        try:
            response = requests.post(url, data=data, auth=auth)
            if response.status_code == 200:
                logger.info("http.request.success",
                          message="Request successful",
                          data={"response": response.json() if response.text else None})
                return True
            else:
                logger.error("http.request.error",
                           message="Request failed",
                           data={
                               "status_code": response.status_code,
                               "response": response.text
                           })
            return False
        except Exception as exc:
            logger.exception("http.request.error", exc=exc,
                           message="Error making HTTP request")
            return False

class Actions(HTTPRequestHandler):
    def __init__(self,
                 chatdj: bool = False,
                 vip_audio: bool = False,
                 command_parser: bool = False,
                 custom_actions: bool = False,
                 spray_bottle: bool = False,
                 couch_buzzer: bool = False,
                 obs_integration: bool = False,
                 event_audio: bool = False):
        
        logger.info("actions.init", 
                   message="Initializing actions",
                   data={
                       "components": {
                           "chatdj": chatdj,
                           "vip_audio": vip_audio,
                           "command_parser": command_parser,
                           "custom_actions": custom_actions,
                           "spray_bottle": spray_bottle,
                           "couch_buzzer": couch_buzzer,
                           "obs_integration": obs_integration,
                           "event_audio": event_audio
                       }
                   })
        
        from . import config, Checks

        self.config = config
        self.checks = Checks()  # Create an instance of Checks

        # Initialize components based on flags
        self.chatdj_enabled = chatdj
        self.vip_audio_enabled = vip_audio
        self.command_parser_enabled = command_parser
        self.custom_actions_enabled = custom_actions
        self.spray_bottle_enabled = spray_bottle
        self.couch_buzzer_enabled = couch_buzzer
        self.obs_integration_enabled = obs_integration
        self.event_audio_enabled = event_audio

        if self.chatdj_enabled:
            logger.debug("actions.chatdj.init", message="Initializing ChatDJ")
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
            logger.debug("actions.spray.init",
                        data={"url": self.spray_bottle_url})
        
        if self.couch_buzzer_enabled:
            self.couch_buzzer_url = config.get("General", "couch_buzzer_url")
            self.couch_buzzer_username = config.get("General", "couch_buzzer_username")
            self.couch_buzzer_password = config.get("General", "couch_buzzer_password")
            logger.debug("actions.buzzer.init",
                        data={"url": self.couch_buzzer_url})

        if self.obs_integration_enabled:
            logger.debug("actions.obs.init", message="Initializing OBS integration")
            from handlers.obshandler import OBSHandler
            self.obs = OBSHandler(
                host=config.get("OBS", "host"),
                port=config.getint("OBS", "port"),
                password=config.get("OBS", "password")
            )
            if self.obs.connect_sync():
                logger.info("actions.obs.connect", message="Successfully connected to OBS")
            else:
                logger.error("actions.obs.connect", message="Failed to connect to OBS")
            
            if self.chatdj_enabled:
                self.request_overlay_duration = config.getint("General", "request_overlay_duration")

    def __del__(self):
        if hasattr(self, 'obs') and self.obs_integration_enabled:
            self.obs.disconnect_sync()

    def get_cached_song(self, song_info: Dict[str, str]) -> Optional[Dict]:
        """Retrieve a cached song from MongoDB."""
        try:
            cached_song = self.song_cache_collection.find_one(
                {'artist': song_info['artist'].lower(), 'song': song_info['song'].lower()}
            )
            logger.debug("cache.song.get",
                        message="Retrieved cached song",
                        data={"song": cached_song})
            return cached_song
        except Exception as exc:
            logger.exception("cache.song.error", exc=exc,
                           message="Failed to retrieve cached song")
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
            logger.debug("cache.song.add",
                        message="Cached song",
                        data={"document_id": str(inserted_id)})
            return True
        except Exception as exc:
            logger.exception("cache.song.error", exc=exc,
                           message="Failed to cache song")
            return False

    def _custom_score(self, query_artist: str, query_song: str, result_artist: str, result_song: str) -> float:
        """Calculate a custom matching score for artist and song."""
        artist_ratio = fuzz.ratio(query_artist.lower(), result_artist.lower())
        song_ratio = fuzz.ratio(query_song.lower(), result_song.lower())
        
        artist_score = 100 if artist_ratio == 100 else artist_ratio * 0.5
        combined_score = (artist_score * 0.7) + (song_ratio * 0.3)
        
        logger.debug("song.match.score",
                    message="Calculated match score",
                    data={
                        "artist_ratio": artist_ratio,
                        "song_ratio": song_ratio,
                        "combined_score": combined_score
                    })
        return combined_score

    def extract_song_titles(self, message: str, song_count: int) -> List[Dict[str, str]]:
        """Extract song titles from a message."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot extract song titles - ChatDJ is not enabled")
            return []
        return self.song_extractor.extract_songs(message, song_count)

    def get_playback_state(self) -> bool:
        """Get the current playback state."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot get playback state - ChatDJ is not enabled")
            return False
        try:
            return self.auto_dj.playback_active()
        except Exception as exc:
            logger.exception("spotify.playback.error", exc=exc,
                           message="Failed to get playback state")
            return False

    def find_song_spotify(self, song_info: Dict[str, str]) -> Optional[str]:
        """Find a song on Spotify, using cache if available."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot search for song - ChatDJ is not enabled")
            return None

        cached_song = self.get_cached_song(song_info)
        if cached_song:
            logger.info("cache.song.hit",
                       message="Found song in cache",
                       data={"song_info": song_info})
            return cached_song['optimized_results'][0]['uri']

        try:
            tracks = self.auto_dj.find_song(song_info)['tracks']
            if not tracks or not tracks['items']:
                logger.warning("spotify.search.empty",
                             message="No tracks found",
                             data={"song_info": song_info})
                return None

            results = []
            for track in tracks['items'][:20]:
                artist_name = track['artists'][0]['name']
                song_name = track['name']
                score = self._custom_score(song_info['artist'], song_info['song'], 
                                        artist_name, song_name)
                results.append({
                    'uri': track['uri'],
                    'artist': artist_name,
                    'song': song_name,
                    'match_ratio': score
                })

            optimized_results = sorted(results, key=lambda x: x['match_ratio'], reverse=True)[:5]
            logger.debug("spotify.search.results",
                        message="Found matching tracks",
                        data={"matches": optimized_results})

            if self.cache_song(song_info, optimized_results):
                logger.info("cache.song.add",
                          message="Cached search results",
                          data={"song_info": song_info})
            else:
                logger.warning("cache.song.error",
                             message="Failed to cache search results",
                             data={"song_info": song_info})

            return optimized_results[0]['uri']
        except Exception as exc:
            logger.exception("spotify.search.error", exc=exc,
                           message="Failed to search for song")
            return None

    def available_in_market(self, song_uri: str) -> bool:
        """Check if a song is available in the user's market."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot check market availability - ChatDJ is not enabled")
            return False

        try:
            user_market = self.auto_dj.get_user_market()
            song_markets = self.auto_dj.get_song_markets(song_uri)
            logger.debug("spotify.market.check",
                        message="Checking market availability",
                        data={
                            "user_market": user_market,
                            "available_markets": song_markets
                        })
            return user_market in song_markets
        except Exception as exc:
            logger.exception("spotify.market.error", exc=exc,
                           message="Failed to check market availability")
            return False

    def add_song_to_queue(self, uri: str, requester_name: str, song_details: str) -> bool:
        """Add a song to the playback queue and trigger the song requester overlay."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot add song to queue - ChatDJ is not enabled")
            return False

        logger.info("spotify.queue.add",
                   message="Adding song to queue",
                   data={
                       "uri": uri,
                       "requester": requester_name,
                       "song": song_details
                   })
        
        try:
            if self.auto_dj.add_song_to_queue(uri):
                self.trigger_song_requester_overlay(
                    requester_name,
                    song_details,
                    self.request_overlay_duration if self.request_overlay_duration else 10
                )
                return True
            return False
        except Exception as exc:
            logger.exception("spotify.queue.error", exc=exc,
                           message="Failed to add song to queue")
            return False

    def skip_song(self) -> bool:
        """Skip the currently playing song."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot skip song - ChatDJ is not enabled")
            return False

        logger.info("spotify.playback.skip", message="Skipping current song")
        try:
            return self.auto_dj.skip_song()
        except Exception as exc:
            logger.exception("spotify.playback.error", exc=exc,
                           message="Failed to skip song")
            return False
    
    def trigger_spray(self) -> bool:
        """Trigger the spray bottle action."""
        logger.info("spray.trigger", message="Triggering spray bottle")
        return self.make_request(self.spray_bottle_url, {"sprayAction": True})
    
    def trigger_couch_buzzer(self, duration=1) -> bool:
        """Trigger the couch buzzer action."""
        logger.info("buzzer.trigger",
                   message="Triggering couch buzzer",
                   data={"duration": duration})
        
        credentials = f"{self.couch_buzzer_username}:{self.couch_buzzer_password}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return self.make_request(
            self.couch_buzzer_url,
            {"duration": duration, "auth": encoded_credentials}
        )

    def _ensure_obs_connected(self) -> bool:
        """Ensure OBS is connected, attempting to connect if not."""
        if not self.obs_integration_enabled:
            logger.warning("actions.obs.disabled",
                         message="Cannot connect - OBS integration is not enabled")
            return False
            
        if not hasattr(self, 'obs') or not self.obs:
            logger.error("actions.obs.error",
                        message="OBS handler not initialized")
            return False
            
        try:
            if not self.obs._connected:
                logger.info("actions.obs.connect",
                          message="Attempting to connect to OBS")
                return self.obs.connect_sync()
            return True
        except Exception as exc:
            logger.error("actions.obs.error",
                        message="Failed to connect to OBS",
                        data={"error": str(exc)})
            return False

    def set_scene(self, scene_key: str) -> bool:
        """Set the current OBS scene."""
        if not self.obs_integration_enabled:
            logger.warning("actions.obs.disabled",
                         message="Cannot set scene - OBS integration is not enabled")
            return False
        return self.obs.set_scene_sync(scene_key)

    def get_current_scene(self) -> Optional[str]:
        """Get the current OBS scene name."""
        if not self.obs_integration_enabled:
            logger.warning("actions.obs.disabled",
                         message="OBS integration is not enabled")
            return None
        return self.obs.get_current_scene_sync()

    def set_source_visibility(self, scene_name: str, source_name: str, visible: bool) -> bool:
        """Set the visibility of an OBS source."""
        if not self.obs_integration_enabled:
            logger.warning("actions.obs.disabled",
                         message="OBS integration is not enabled")
            return False
        return self.obs.set_source_visibility_sync(scene_name, source_name, visible)

    def get_source_visibility(self, scene_name: str, source_name: str) -> Optional[bool]:
        """Get the visibility state of an OBS source."""
        if not self.obs_integration_enabled:
            logger.warning("actions.obs.disabled",
                         message="OBS integration is not enabled")
            return None
        return self.obs.get_source_visibility_sync(scene_name, source_name)

    def trigger_song_requester_overlay(self, requester_name: str, song_details: str, display_duration: int = 10) -> None:
        """Trigger the song requester overlay to show and then hide after a duration."""
        if not self.obs_integration_enabled:
            logger.warning("actions.obs.disabled",
                         message="OBS integration is not enabled")
            return
        self.obs.trigger_song_requester_overlay_sync(requester_name, song_details, display_duration)

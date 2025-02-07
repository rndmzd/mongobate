from datetime import datetime as DateTime
from typing import Dict, List, Optional

import requests
import base64

from chatdj.chatdj import SongRequest


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
                if response.text:
                    try:
                        logger.info("http.request.success",
                                  message="Request successful",
                                  data={"response": response.json()})
                    except ValueError:
                        logger.info("http.request.success",
                                  message="Request successful",
                                  data={"response": response.text})
                else:
                    logger.info("http.request.success",
                              message="Request successful with empty response")
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
            from . import spotify_client, song_cache_collection

            self.song_extractor = SongExtractor(
                config.get("OpenAI", "api_key"), 
                spotify_client=spotify_client,
                google_api_key=config.get("Search","google_api_key"),
                google_cx=config.get("Search", "google_cx")
            )
            self.auto_dj = AutoDJ(spotify_client)
            self.song_cache_collection = song_cache_collection
        

        if self.custom_actions_enabled:
            from . import user_collection
            self.user_collection = user_collection

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
            # Don't connect here - let the first actual OBS operation handle connection
            logger.info("actions.obs.init.complete", message="OBS handler initialized")
            
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

    def find_song_spotify(self, song_info: SongRequest) -> Optional[str]:
        """Return the spotify_uri provided in the song_info."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot search for song - ChatDJ is not enabled")
            return None
        
        logger.debug("spotify.search.start",
                    message="Starting Spotify song search",
                    data={
                        "song": song_info.song,
                        "artist": song_info.artist
                    })
        
        search_result = self.auto_dj.search_track_uri(song_info.song, song_info.artist)
        if search_result:
            logger.debug("spotify.search.success",
                        message="Found Spotify track",
                        data={
                            "uri": search_result,
                            "song": song_info.song,
                            "artist": song_info.artist
                        })
            return search_result
        else:
            logger.warning("spotify.search.notfound",
                         message="No Spotify URI found for song",
                         data={
                             "song": song_info.song,
                             "artist": song_info.artist
                         })
            return None

    def available_in_market(self, song_uri: str) -> bool:
        """Check if a song is available in the user's market."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot check market availability - ChatDJ is not enabled")
            return False

        try:
            logger.debug("spotify.market.check.start",
                        message="Checking market availability",
                        data={"uri": song_uri})
            
            user_market = self.auto_dj.get_user_market()
            song_markets = self.auto_dj.get_song_markets(song_uri)
            
            is_available = user_market in song_markets
            logger.debug("spotify.market.check.complete",
                        message="Market availability check complete",
                        data={
                            "uri": song_uri,
                            "user_market": user_market,
                            "available_markets": song_markets,
                            "is_available": is_available
                        })
            return is_available
            
        except Exception as exc:
            logger.exception("spotify.market.error",
                           message="Failed to check market availability",
                           exc=exc,
                           data={
                               "uri": song_uri,
                               "error_type": type(exc).__name__
                           })
            return False

    def add_song_to_queue(self, uri: str, requester_name: str, song_details: str) -> bool:
        """Add a song to the playback queue and trigger the song requester overlay."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot add song to queue - ChatDJ is not enabled")
            return False

        logger.debug("spotify.queue.add.start",
                    message="Adding song to queue",
                    data={
                        "uri": uri,
                        "requester": requester_name,
                        "song": song_details
                    })
        
        try:
            queue_result = self.auto_dj.add_song_to_queue(uri)
            if queue_result:
                logger.debug("spotify.queue.add.success",
                           message="Successfully added song to queue",
                           data={
                               "uri": uri,
                               "song": song_details
                           })
                           
                logger.debug("spotify.queue.overlay.start",
                           message="Triggering song requester overlay",
                           data={
                               "requester": requester_name,
                               "song": song_details,
                               "duration": self.request_overlay_duration
                           })
                           
                self.trigger_song_requester_overlay(
                    requester_name,
                    song_details,
                    self.request_overlay_duration if self.request_overlay_duration else 10
                )
                return True
                
            logger.error("spotify.queue.add.failed",
                        message="Failed to add song to queue",
                        data={
                            "uri": uri,
                            "song": song_details
                        })
            return False
            
        except Exception as exc:
            logger.exception("spotify.queue.error",
                           message="Failed to add song to queue",
                           exc=exc,
                           data={
                               "uri": uri,
                               "song": song_details,
                               "error_type": type(exc).__name__
                           })
            return False

    def skip_song(self) -> bool:
        """Skip the currently playing song."""
        if not self.chatdj_enabled:
            logger.warning("chatdj.disabled",
                         message="Cannot skip song - ChatDJ is not enabled",
                         data={"component": "chatdj"})
            return False

        logger.debug("spotify.playback.skip.start",
                    message="Attempting to skip current song")
        try:
            skip_result = self.auto_dj.skip_song()
            if skip_result:
                logger.info("spotify.playback.skip.success",
                          message="Successfully skipped current song")
            else:
                logger.error("spotify.playback.skip.failed",
                           message="Failed to skip current song")
            return skip_result
            
        except Exception as exc:
            logger.exception("spotify.playback.error",
                           message="Failed to skip song",
                           exc=exc,
                           data={"error_type": type(exc).__name__})
            return False
    
    def trigger_spray(self) -> bool:
        """Trigger the spray bottle action."""
        logger.info("spray.trigger",
                   message="Triggering spray bottle",
                   data={"url": self.spray_bottle_url})
        return self.make_request(self.spray_bottle_url, {"sprayAction": True})
    
    def trigger_couch_buzzer(self, duration=1) -> bool:
        """Trigger the couch buzzer action."""
        logger.info("buzzer.trigger",
                   message="Triggering couch buzzer",
                   data={
                       "duration": duration,
                       "url": self.couch_buzzer_url
                   })
        
        credentials = f"{self.couch_buzzer_username}:{self.couch_buzzer_password}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return self.make_request(
            self.couch_buzzer_url,
            {"duration": duration, "auth": encoded_credentials}
        )

    def _ensure_obs_connected(self) -> bool:
        """Ensure OBS is connected, attempting to connect if not."""
        if not self.obs_integration_enabled:
            logger.warning("obs.disabled",
                         message="Cannot connect - OBS integration is not enabled",
                         data={"component": "obs"})
            return False
            
        if not hasattr(self, 'obs') or not self.obs:
            logger.error("obs.error",
                        message="OBS handler not initialized",
                        data={"component": "obs"})
            return False
            
        try:
            if not self.obs._connected:
                logger.info("obs.connect",
                          message="Attempting to connect to OBS",
                          data={"component": "obs"})
                return self.obs.connect_sync()
            return True
        except Exception as exc:
            logger.error("obs.error",
                        message="Failed to connect to OBS",
                        exc=exc,
                        data={"component": "obs"})
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
    
    def get_last_vip_audio_play(self, user: str) -> Optional[DateTime]:
        """Get the last VIP audio play time for a user."""
        user_data = self.user_collection.find_one({"username": user})
        if not user_data:
            logger.warning(f"User {user} not found.")
            return None
        return user_data.get("last_vip_audio_play")
    
    def set_last_vip_audio_play(self, user: str, timestamp: DateTime) -> bool:
        """Set the last VIP audio play time for a user."""
        return self.user_collection.update_one(
            {"username": user},
            {"$set": {"last_vip_audio_play": timestamp}}
        )

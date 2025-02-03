import asyncio
import simpleobsws
from typing import Optional, Dict, Any
import yaml
from pathlib import Path

from utils.logging_config import setup_logging

logger = setup_logging(component='handlers.obshandler')

class OBSHandler:
    def __init__(self, host: str = 'localhost', port: int = 4455, password: Optional[str] = None):
        """Initialize OBS WebSocket handler.
        
        Args:
            host: OBS WebSocket server host
            port: OBS WebSocket server port
            password: OBS WebSocket server password
        """
        self.host = host
        self.port = port
        self.password = password
        self.ws: Optional[simpleobsws.WebSocketClient] = None
        self._connected = False
        
        # Create event loop for async operations
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        # Load scene definitions
        self.scenes = self._load_scenes()
        if self.scenes:
            logger.info("Successfully loaded scene definitions")
        else:
            logger.warning("Failed to load scene definitions")

    def _load_scenes(self) -> Optional[Dict]:
        """Load scene definitions from YAML file."""
        try:
            scenes_file = Path(__file__).parent.parent / 'scenes.yaml'
            with open(scenes_file, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('scenes', {})
        except Exception as e:
            logger.exception("Error loading scene definitions", exc_info=e)
            return None

    def _get_scene_name(self, scene_key: str) -> Optional[str]:
        """Get the actual scene name from scene key.
        
        Args:
            scene_key: Key of the scene in the YAML config
            
        Returns:
            Actual scene name or None if not found
        """
        if not self.scenes or scene_key not in self.scenes:
            logger.warning(f"Scene key '{scene_key}' not found in scene definitions")
            return None
        return self.scenes[scene_key]['name']

    async def connect(self) -> bool:
        """Connect to OBS WebSocket server."""
        try:
            ws_url = f"ws://{self.host}:{self.port}"
            logger.debug(f"Connecting to OBS WebSocket at {ws_url}")
            
            ws_params = simpleobsws.IdentificationParameters(ignoreNonFatalRequestChecks=False)
            self.ws = simpleobsws.WebSocketClient(
                url=ws_url,
                password=self.password,
                identification_parameters=ws_params
            )
            
            await self.ws.connect()
            await self.ws.wait_until_identified()
            self._connected = True
            logger.info("Successfully connected to OBS WebSocket")
            return True
            
        except Exception as e:
            logger.exception("Failed to connect to OBS WebSocket", exc_info=e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from OBS WebSocket server."""
        if self.ws and self._connected:
            await self.ws.disconnect()
            self._connected = False
            logger.info("Disconnected from OBS WebSocket")

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect to OBS WebSocket server."""
        logger.info("Attempting to reconnect to OBS WebSocket...")
        return await self.connect()

    async def send_request(self, request_type: str, request_data: Optional[Dict] = None, max_retries: int = 2) -> Optional[Dict[str, Any]]:
        """Send a request to OBS WebSocket server with retry logic.
        
        Args:
            request_type: Type of request to send
            request_data: Data to send with request
            max_retries: Maximum number of retry attempts (default: 2)
            
        Returns:
            Response from OBS WebSocket server or None if request failed
        """
        retries = 0
        
        while retries <= max_retries:
            try:
                if not self.ws or not self._connected:
                    if retries < max_retries:
                        if await self._try_reconnect():
                            logger.info("Reconnected successfully")
                        else:
                            logger.error("Reconnection failed")
                            retries += 1
                            await asyncio.sleep(1)  # Wait before retry
                            continue
                    else:
                        logger.error("Not connected to OBS WebSocket and max retries exceeded")
                        return None
                
                request = simpleobsws.Request(request_type, request_data)
                response = await self.ws.call(request)
                
                if response and response.ok():
                    return response.responseData
                else:
                    logger.error(f"Request failed for {request_type}")
                    if retries < max_retries:
                        retries += 1
                        await asyncio.sleep(1)  # Wait before retry
                        continue
                    return None
                    
            except simpleobsws.NotIdentifiedError:
                logger.warning("Lost connection to OBS Websocket, attempting to reconnect...")
                self._connected = False
                if retries < max_retries:
                    if await self._try_reconnect():
                        logger.info("Reconnected successfully")
                        retries += 1
                        continue
                    else:
                        logger.error("Reconnection failed")
                        retries += 1
                        await asyncio.sleep(1)  # Wait before retry
                        continue
                return None
            except Exception as e:
                logger.exception(f"Error sending request {request_type}", exc_info=e)
                if retries < max_retries:
                    retries += 1
                    await asyncio.sleep(1)  # Wait before retry
                    continue
                return None
        
        return None

    # Convenience methods for common OBS operations
    async def set_scene(self, scene_key: str) -> bool:
        """Switch to the specified scene.
        
        Args:
            scene_key: Key of the scene in the YAML config
            
        Returns:
            True if successful, False otherwise
        """
        scene_name = self._get_scene_name(scene_key)
        if not scene_name:
            return False
            
        response = await self.send_request('SetCurrentProgramScene', {'sceneName': scene_name})
        return response is not None

    async def get_current_scene(self) -> Optional[str]:
        """Get the name of the current scene.
        
        Returns:
            Name of current scene or None if request failed
        """
        response = await self.send_request('GetCurrentProgramScene')
        if response:
            return response.get('currentProgramSceneName')
        return None

    async def set_source_visibility(self, scene_key: str, source_name: str, visible: bool) -> bool:
        """Set the visibility of a source in a scene.
        
        Args:
            scene_key: Key of the scene in the YAML config
            source_name: Name of source to modify
            visible: Whether source should be visible
            
        Returns:
            True if successful, False otherwise
        """
        scene_name = self._get_scene_name(scene_key)
        if not scene_name:
            return False
            
        # First get the scene item ID
        id_response = await self.send_request('GetSceneItemId', {
            'sceneName': scene_name,
            'sourceName': source_name
        })
        
        if not id_response:
            logger.error(f"Failed to get scene item ID for {source_name}")
            return False
            
        scene_item_id = id_response.get('sceneItemId')
        if scene_item_id is None:
            logger.error(f"Scene item ID not found for {source_name}")
            return False
            
        # Then set the visibility using the ID
        response = await self.send_request('SetSceneItemEnabled', {
            'sceneName': scene_name,
            'sceneItemId': scene_item_id,
            'sceneItemEnabled': visible
        })
        logger.debug(f"Set scene item visibility response: {response}")
        # return response is not None
        return True

    async def get_source_visibility(self, scene_key: str, source_name: str) -> Optional[bool]:
        """Get the visibility state of a source in a scene.
        
        Args:
            scene_key: Key of the scene in the YAML config
            source_name: Name of source to check
            
        Returns:
            True if source is visible, False if hidden, None if request failed
        """
        scene_name = self._get_scene_name(scene_key)
        if not scene_name:
            return None
            
        # First get the scene item ID
        id_response = await self.send_request('GetSceneItemId', {
            'sceneName': scene_name,
            'sourceName': source_name
        })
        
        if not id_response:
            logger.error(f"Failed to get scene item ID for {source_name}")
            return None
            
        scene_item_id = id_response.get('sceneItemId')
        if scene_item_id is None:
            logger.error(f"Scene item ID not found for {source_name}")
            return None
            
        response = await self.send_request('GetSceneItemEnabled', {
            'sceneName': scene_name,
            'sceneItemId': scene_item_id
        })
        if response:
            return response.get('sceneItemEnabled')
        return None

    async def show_song_requester(self, requester_name: str, song_details: str) -> bool:
        """Show the song requester name and song details on the overlay.
        
        Args:
            requester_name: Name of the user who requested the song
            song_details: Details of the requested song (artist and name)
            
        Returns:
            True if successful, False otherwise
        """
        # First set the text
        logger.debug("Setting song requester text...")
        await self.send_request('SetInputSettings', {
            'inputName': 'SongRequester',
            'inputSettings': {
                'text': f'Song requested by {requester_name}\n{song_details}'
            }
        })
            
        # Then make the source visible
        logger.debug("Making song requester source visible...")
        visibility_result = await self.set_source_visibility('main', 'SongRequester', True)
        logger.debug(f"Source visibility result: {visibility_result}")

        return visibility_result

    async def hide_song_requester(self) -> bool:
        """Hide the song requester name and song details from the overlay.
        
        Returns:
            True if successful, False otherwise
        """
        # First hide the source
        logger.debug("Hiding song requester source...")
        visibility_result = await self.set_source_visibility('main', 'SongRequester', False)
        logger.debug(f"Source visibility result: {visibility_result}")

        await asyncio.sleep(1)

        # Then clear the text
        logger.debug("Clearing song requester text...")
        await self.send_request('SetInputSettings', {
            'inputName': 'SongRequester',
            'inputSettings': {
                'text': ''
            }
        })
        
        return visibility_result

    async def trigger_song_requester_overlay(self, requester_name: str, song_details: str, display_duration: int = 10) -> None:
        """Trigger the song requester overlay to show and then hide after a duration.
        
        Args:
            requester_name: Name of the user who requested the song
            song_details: Details of the requested song (artist and name)
            display_duration: Duration to display the requester name and song details (in seconds)
        """
        if await self.show_song_requester(requester_name, song_details):
            await asyncio.sleep(display_duration)
            await self.hide_song_requester()

    def run_sync(self, coro):
        """Run a coroutine synchronously.
        
        Args:
            coro: Coroutine to run
            
        Returns:
            Result of coroutine execution
        """
        return self.loop.run_until_complete(coro)

    def connect_sync(self) -> bool:
        """Synchronous version of connect()."""
        return self.run_sync(self.connect())

    def disconnect_sync(self) -> None:
        """Synchronous version of disconnect()."""
        self.run_sync(self.disconnect())

    def set_scene_sync(self, scene_key: str) -> bool:
        """Synchronous version of set_scene()."""
        return self.run_sync(self.set_scene(scene_key))

    def get_current_scene_sync(self) -> Optional[str]:
        """Synchronous version of get_current_scene()."""
        return self.run_sync(self.get_current_scene())

    def set_source_visibility_sync(self, scene_key: str, source_name: str, visible: bool) -> bool:
        """Synchronous version of set_source_visibility()."""
        return self.run_sync(self.set_source_visibility(scene_key, source_name, visible))

    def get_source_visibility_sync(self, scene_key: str, source_name: str) -> Optional[bool]:
        """Synchronous version of get_source_visibility()."""
        return self.run_sync(self.get_source_visibility(scene_key, source_name))

    def trigger_song_requester_overlay_sync(self, requester_name: str, song_details: str, display_duration: int = 10) -> None:
        """Synchronous version of trigger_song_requester_overlay()."""
        self.run_sync(self.trigger_song_requester_overlay(requester_name, song_details, display_duration))

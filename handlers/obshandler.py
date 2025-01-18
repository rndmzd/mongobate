import logging
import asyncio
import simpleobsws
from typing import Optional, Dict, Any
import yaml
from pathlib import Path

logger = logging.getLogger('mongobate.handlers.obshandler')
logger.setLevel(logging.DEBUG)

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
            
            try:
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
            
        response = await self.send_request('SetSceneItemEnabled', {
            'sceneName': scene_name,
            'sceneItemName': source_name,
            'sceneItemEnabled': visible
        })
        return response is not None

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
            
        response = await self.send_request('GetSceneItemEnabled', {
            'sceneName': scene_name,
            'sceneItemName': source_name
        })
        if response:
            return response.get('sceneItemEnabled')
        return None

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
import asyncio
import simpleobsws
from typing import Optional, Dict, Any
import yaml
from pathlib import Path

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.handlers.obshandler')

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
        
        # Get the current event loop or create a new one
        try:
            self.loop = asyncio.get_event_loop()
            logger.debug("obs.init.loop",
                        message="Using existing event loop",
                        data={"running": self.loop.is_running()})
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            logger.debug("obs.init.loop",
                        message="Created new event loop")
        
        # Load scene definitions
        self.scenes = self._load_scenes()
        if self.scenes:
            logger.info("obs.scenes.load",
                       message="Successfully loaded scene definitions",
                       data={"scene_count": len(self.scenes)})
        else:
            logger.warning("obs.scenes.error",
                         message="Failed to load scene definitions")

    def _load_scenes(self) -> Optional[Dict]:
        """Load scene definitions from YAML file."""
        try:
            scenes_file = Path(__file__).parent.parent / 'scenes.yaml'
            with open(scenes_file, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('scenes', {})
        except Exception as exc:
            logger.exception("obs.scenes.error",
                           exc=exc,
                           message="Failed to load scene definitions")
            return None

    def _get_scene_name(self, scene_key: str) -> Optional[str]:
        """Get the actual scene name from scene key.
        
        Args:
            scene_key: Key of the scene in the YAML config
            
        Returns:
            Actual scene name or None if not found
        """
        if not self.scenes or scene_key not in self.scenes:
            logger.warning("obs.scene.notfound",
                         message="Scene key not found",
                         data={"scene_key": scene_key})
            return None
        return self.scenes[scene_key]['name']

    async def connect(self) -> bool:
        """Connect to OBS WebSocket server."""
        try:
            ws_url = f"ws://{self.host}:{self.port}"
            logger.info("obs.connect.start",
                       message="Starting OBS WebSocket connection",
                       data={
                           "url": ws_url,
                           "password_set": bool(self.password),
                           "host": self.host,
                           "port": self.port
                       })
            
            ws_params = simpleobsws.IdentificationParameters(ignoreNonFatalRequestChecks=False)
            self.ws = simpleobsws.WebSocketClient(
                url=ws_url,
                password=self.password,
                identification_parameters=ws_params
            )
            
            try:
                logger.info("obs.connect.step", message="Initiating WebSocket connection")
                await self.ws.connect()
                logger.info("obs.connect.step", message="WebSocket connected, waiting for identification")
                await self.ws.wait_until_identified()
                logger.info("obs.connect.step", message="WebSocket identified successfully")
                
                self._connected = True
                logger.info("obs.connect.success",
                           message="Connected to OBS WebSocket",
                           data={"url": ws_url})
                return True
                
            except asyncio.TimeoutError:
                logger.error("obs.connect.timeout",
                           message="Connection attempt timed out",
                           data={"url": ws_url})
                self._connected = False
                return False
            except ConnectionRefusedError:
                logger.error("obs.connect.refused",
                           message="Connection refused - is OBS running and WebSocket server enabled?",
                           data={"url": ws_url})
                self._connected = False
                return False
            except simpleobsws.ConnectionFailure as exc:
                logger.error("obs.connect.error",
                           message="WebSocket connection failed",
                           data={"error": str(exc), "url": ws_url})
                self._connected = False
                return False
            
        except Exception as exc:
            logger.exception("obs.connect.error",
                           exc=exc,
                           message="Failed to connect to OBS WebSocket",
                           data={"url": ws_url})
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from OBS WebSocket server."""
        if self.ws and self._connected:
            await self.ws.disconnect()
            self._connected = False
            logger.info("obs.disconnect",
                       message="Disconnected from OBS WebSocket")

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect to OBS WebSocket server."""
        logger.info("obs.reconnect",
                   message="Attempting to reconnect to OBS WebSocket")
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
                            logger.info("obs.reconnect.success",
                                      message="Reconnected successfully")
                        else:
                            logger.error("obs.reconnect.error",
                                       message="Reconnection failed")
                            retries += 1
                            await asyncio.sleep(1)  # Wait before retry
                            continue
                    else:
                        logger.error("obs.request.error",
                                   message="Not connected and max retries exceeded",
                                   data={"request_type": request_type})
                        return None
                
                request = simpleobsws.Request(request_type, request_data)
                response = await self.ws.call(request)
                
                if response and response.ok():
                    logger.debug("obs.request.success",
                               message="Request successful",
                               data={
                                   "type": request_type,
                                   "data": request_data
                               })
                    return response.responseData
                else:
                    logger.error("obs.request.failed",
                               message="Request failed",
                               data={
                                   "type": request_type,
                                   "retry": retries + 1,
                                   "max_retries": max_retries
                               })
                    if retries < max_retries:
                        retries += 1
                        await asyncio.sleep(1)  # Wait before retry
                        continue
                    return None
                    
            except simpleobsws.NotIdentifiedError:
                logger.warning("obs.connection.lost",
                             message="Lost connection to OBS WebSocket")
                self._connected = False
                if retries < max_retries:
                    if await self._try_reconnect():
                        logger.info("obs.reconnect.success",
                                  message="Reconnected successfully")
                        retries += 1
                        continue
                    else:
                        logger.error("obs.reconnect.error",
                                   message="Reconnection failed")
                        retries += 1
                        await asyncio.sleep(1)  # Wait before retry
                        continue
                return None
            except Exception as exc:
                logger.exception("obs.request.error",
                               exc=exc,
                               message="Failed to send request",
                               data={"request_type": request_type})
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
            
        logger.debug("obs.scene.set",
                    message="Setting current scene",
                    data={
                        "scene_key": scene_key,
                        "scene_name": scene_name
                    })
            
        response = await self.send_request('SetCurrentProgramScene', {'sceneName': scene_name})
        success = response is not None
        
        if success:
            logger.info("obs.scene.set.success",
                       message="Set current scene",
                       data={"scene_name": scene_name})
        else:
            logger.error("obs.scene.set.error",
                        message="Failed to set scene",
                        data={"scene_name": scene_name})
            
        return success

    async def get_current_scene(self) -> Optional[str]:
        """Get the name of the current scene.
        
        Returns:
            Name of current scene or None if request failed
        """
        response = await self.send_request('GetCurrentProgramScene')
        if response:
            scene_name = response.get('currentProgramSceneName')
            logger.debug("obs.scene.get",
                        message="Retrieved current scene",
                        data={"scene": scene_name})
            return scene_name
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
            
        logger.debug("obs.source.visibility",
                    message="Setting source visibility",
                    data={
                        "scene": scene_name,
                        "source": source_name,
                        "visible": visible
                    })
            
        # First get the scene item ID
        id_response = await self.send_request('GetSceneItemId', {
            'sceneName': scene_name,
            'sourceName': source_name
        })
        
        if not id_response:
            logger.error("obs.source.error",
                        message="Failed to get scene item ID",
                        data={"source": source_name})
            return False
            
        scene_item_id = id_response.get('sceneItemId')
        if scene_item_id is None:
            logger.error("obs.source.notfound",
                        message="Scene item ID not found",
                        data={"source": source_name})
            return False
            
        # Then set the visibility using the ID
        response = await self.send_request('SetSceneItemEnabled', {
            'sceneName': scene_name,
            'sceneItemId': scene_item_id,
            'sceneItemEnabled': visible
        })
        
        success = response is not None
        if success:
            logger.info("obs.source.visibility.success",
                       message="Set source visibility",
                       data={
                           "scene": scene_name,
                           "source": source_name,
                           "visible": visible
                       })
        else:
            logger.error("obs.source.visibility.error",
                        message="Failed to set source visibility",
                        data={
                            "scene": scene_name,
                            "source": source_name,
                            "visible": visible
                        })
        
        return success

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
            
        logger.debug("obs.source.get",
                    message="Getting source visibility",
                    data={
                        "scene": scene_name,
                        "source": source_name
                    })
            
        # First get the scene item ID
        id_response = await self.send_request('GetSceneItemId', {
            'sceneName': scene_name,
            'sourceName': source_name
        })
        
        if not id_response:
            logger.error("obs.source.error",
                        message="Failed to get scene item ID",
                        data={"source": source_name})
            return None
            
        scene_item_id = id_response.get('sceneItemId')
        if scene_item_id is None:
            logger.error("obs.source.notfound",
                        message="Scene item ID not found",
                        data={"source": source_name})
            return None
            
        # Then get the visibility using the ID
        response = await self.send_request('GetSceneItemEnabled', {
            'sceneName': scene_name,
            'sceneItemId': scene_item_id
        })
        
        if response is not None:
            visible = response.get('sceneItemEnabled', False)
            logger.debug("obs.source.visibility.get",
                        message="Retrieved source visibility",
                        data={
                            "scene": scene_name,
                            "source": source_name,
                            "visible": visible
                        })
            return visible
            
        return None

    async def show_song_requester(self, requester_name: str, song_details: str) -> bool:
        """Show the song requester overlay with specified details.
        
        Args:
            requester_name: Name of the person requesting the song
            song_details: Details of the requested song
            
        Returns:
            True if successful, False otherwise
        """
        logger.debug("obs.overlay.show",
                    message="Showing song requester overlay",
                    data={
                        "requester": requester_name,
                        "song": song_details
                    })
        
        request_content = {
            'inputName': 'SongRequester',
            'inputSettings': {
                'text': f'Song requested by {requester_name}\n{song_details}'
            }
        }
        logger.debug("obs.overlay.show.request",
                    message="Sending request to set input settings",
                    data={"request": request_content})
        await self.send_request('SetInputSettings', request_content)

        await asyncio.sleep(1)

        success = True
        success &= await self.set_source_visibility('main', 'SongRequester', True)

        if success:
            logger.info("obs.overlay.show.success",
                       message="Song requester overlay shown")
        else:
            logger.error("obs.overlay.show.error",
                        message="Failed to show song requester overlay")
            
        return success

    async def hide_song_requester(self) -> bool:
        """Hide the song requester overlay.
        
        Returns:
            True if successful, False otherwise
        """
        logger.debug("obs.overlay.hide",
                    message="Hiding song requester overlay")
        
        success = True
        success &= await self.set_source_visibility('main', 'SongRequester', False)
        
        if success:
            logger.info("obs.overlay.hide.success",
                       message="Song requester overlay hidden")
        else:
            logger.error("obs.overlay.hide.error",
                        message="Failed to hide song requester overlay")
        
        await asyncio.sleep(1)
        
        request_content = {
            'inputName': 'SongRequester',
            'inputSettings': {
                'text': ''
            }
        }
        logger.debug("obs.overlay.hide.request",
                    message="Sending request to set input settings",
                    data={"request": request_content})
        await self.send_request('SetInputSettings', request_content)
            
        return success

    async def trigger_song_requester_overlay(self, requester_name: str, song_details: str, display_duration: int = 10) -> None:
        """Show the song requester overlay for a specified duration.
        
        Args:
            requester_name: Name of the person requesting the song
            song_details: Details of the requested song
            display_duration: How long to display the overlay in seconds
        """
        logger.debug("obs.overlay.trigger",
                    message="Triggering song requester overlay",
                    data={
                        "requester": requester_name,
                        "song": song_details,
                        "duration": display_duration
                    })
                    
        await self.show_song_requester(requester_name, song_details)
        await asyncio.sleep(display_duration)
        await self.hide_song_requester()

    async def initialize(self) -> bool:
        """Initialize the OBS handler and connect to WebSocket.
        This should be called after instantiation.
        """
        try:
            return await self.connect()
        except Exception as exc:
            logger.exception("obs.init.error",
                           exc=exc,
                           message="Failed to initialize OBS handler")
            return False

    def run_sync(self, coro):
        """Run a coroutine synchronously using the dedicated event loop.
        
        Args:
            coro: Coroutine to run
        """
        try:
            # If we're in a running event loop, use run_coroutine_threadsafe
            if self.loop.is_running():
                logger.debug("obs.sync.run",
                           message="Using run_coroutine_threadsafe")
                future = asyncio.run_coroutine_threadsafe(coro, self.loop)
                return future.result(timeout=10)  # 10 second timeout
            else:
                # If loop isn't running, use run_until_complete
                logger.debug("obs.sync.run",
                           message="Using run_until_complete")
                return self.loop.run_until_complete(coro)
        except Exception as exc:
            logger.exception("obs.sync.error",
                           exc=exc,
                           message="Error running coroutine")
            return None

    def connect_sync(self) -> bool:
        """Synchronous version of connect()."""
        return self.run_sync(self.connect())

    def disconnect_sync(self) -> None:
        """Synchronous version of disconnect()."""
        self.run_sync(self.disconnect())

    def set_scene_sync(self, scene_key: str) -> bool:
        """Set scene synchronously."""
        result = self.run_sync(self.set_scene(scene_key))
        return bool(result)

    def get_current_scene_sync(self) -> Optional[str]:
        """Get current scene synchronously."""
        return self.run_sync(self.get_current_scene())

    def set_source_visibility_sync(self, scene_key: str, source_name: str, visible: bool) -> bool:
        """Set source visibility synchronously."""
        result = self.run_sync(self.set_source_visibility(scene_key, source_name, visible))
        return bool(result)

    def get_source_visibility_sync(self, scene_key: str, source_name: str) -> Optional[bool]:
        """Get source visibility synchronously."""
        return self.run_sync(self.get_source_visibility(scene_key, source_name))

    def trigger_song_requester_overlay_sync(self, requester_name: str, song_details: str, display_duration: int = 10) -> None:
        """Trigger song requester overlay synchronously."""
        # Use display_duration + 1 second as timeout to ensure full display
        self.run_sync(self.trigger_song_requester_overlay(requester_name, song_details, display_duration))

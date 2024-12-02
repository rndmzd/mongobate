import asyncio
import logging
import json
from obswebsocket import obsws, requests
import configparser
from aiohttp import web
import os

logger = logging.getLogger('mongobate.obshandler')
logger.setLevel(logging.DEBUG)

class OBSHandler:
    def __init__(self, obs_host, obs_port, password, http_host, http_port):
        self.obs_host = obs_host
        self.obs_port = obs_port
        self.password = password
        self.http_host = http_host
        self.http_port = http_port
        self.ws = None
        self.app = web.Application()
        self.app.router.add_static('/overlays', 'overlays')
        self.app.router.add_get('/', self.handle_index)
        self.overlay_duration = 5

    async def handle_index(self, request):
        return web.Response(text="OBS Integration Server is running")

    async def start_http_server(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.http_host, self.http_port)
        await site.start()
        logger.info(f"HTTP server started on http://{self.http_host}:{self.http_port}")

    async def connect(self):
        try:
            self.ws = obsws(self.obs_host, self.obs_port, self.password)
            await asyncio.to_thread(self.ws.connect)
            logger.info("Connected to OBS WebSocket")
        except Exception as e:
            logger.exception("Failed to connect to OBS WebSocket")
            raise

    async def disconnect(self):
        if self.ws:
            await asyncio.to_thread(self.ws.disconnect)
            logger.info("Disconnected from OBS WebSocket")

    async def _make_request(self, request_type, **kwargs):
        """Helper method to make OBS WebSocket requests asynchronously."""
        try:
            request = request_type(**kwargs)  # Create request object
            response = await asyncio.to_thread(self.ws.call, request)  # Pass request object
            return response if response.status else None
        except Exception as e:
            logger.exception(f"Error making OBS request: {request_type.__name__}")
            return None

    async def get_scene_list(self):
        """Get a list of all available scenes and current scene info."""
        response = await self._make_request(requests.GetSceneList)
        if response:
            scenes = [scene['sceneName'] for scene in response.getScenes()]
            logger.info(f"Available scenes: {scenes}")
            return scenes
        return []

    async def get_current_scene(self):
        """Get the name of the current program scene."""
        response = await self._make_request(requests.GetSceneList)
        if response:
            scene_name = response.getCurrentProgramSceneName()
            logger.info(f"Current scene: {scene_name}")
            return scene_name
        return None

    async def switch_scene(self, scene_name):
        """Switch to the specified scene."""
        response = await self._make_request(
            requests.SetCurrentProgramScene,
            sceneName=scene_name
        )
        if response:
            logger.info(f"Switched to scene: {scene_name}")
            return True
        logger.error(f"Failed to switch to scene: {scene_name}")
        return False

    async def create_browser_source(self, scene_name, source_name, url):
        try:
            # First, check if the source already exists
            scene_items = await self._make_request(
                requests.GetSceneItemList,
                sceneName=scene_name
            )
            
            source_exists = False
            if scene_items:
                source_exists = any(item['sourceName'] == source_name 
                                  for item in scene_items.getSceneItems())

            if not source_exists:
                logger.info(f"Browser source not found: {source_name}. Creating new source.")
                response = await self._make_request(
                    requests.CreateInput,
                    sceneName=scene_name,
                    inputName=source_name,
                    inputKind="browser_source",
                    inputSettings={
                        "url": url,
                        "width": 1920,
                        "height": 1080
                    }
                )
                if not response:
                    logger.error(f"Failed to create browser source: {source_name}")
                    return False

            # Update the source settings
            response = await self._make_request(
                requests.SetInputSettings,
                inputName=source_name,
                inputSettings={
                    "url": url,
                    "width": 1920,
                    "height": 1080
                }
            )
            if response:
                logger.info(f"Updated browser source settings: {source_name}")
                return True
            logger.error(f"Failed to update browser source settings: {source_name}")
            return False

        except Exception as e:
            logger.exception(f"Error creating/updating browser source: {e}")
            return False

    async def show_source(self, scene_name, source_name):
        try:
            # Get the scene item ID
            response = await self._make_request(
                requests.GetSceneItemId,
                sceneName=scene_name,
                sourceName=source_name
            )
            if not response:
                logger.error(f"Failed to get scene item ID for: {source_name}")
                return False
            
            scene_item_id = response.getSceneItemId()
            
            # Set the source visibility
            response = await self._make_request(
                requests.SetSceneItemEnabled,
                sceneName=scene_name,
                sceneItemId=scene_item_id,
                sceneItemEnabled=True
            )
            if response:
                logger.info(f"Showed source: {source_name}")
                return True
            logger.error(f"Failed to show source: {source_name}")
            return False
            
        except Exception as e:
            logger.exception(f"Error showing source: {e}")
            return False

    async def hide_source(self, scene_name, source_name):
        try:
            # Get the scene item ID
            response = await self._make_request(
                requests.GetSceneItemId,
                sceneName=scene_name,
                sourceName=source_name
            )
            if not response:
                logger.error(f"Failed to get scene item ID for: {source_name}")
                return False
            
            scene_item_id = response.getSceneItemId()
            
            # Set the source visibility
            response = await self._make_request(
                requests.SetSceneItemEnabled,
                sceneName=scene_name,
                sceneItemId=scene_item_id,
                sceneItemEnabled=False
            )
            if response:
                logger.info(f"Hid source: {source_name}")
                return True
            logger.error(f"Failed to hide source: {source_name}")
            return False
            
        except Exception as e:
            logger.exception(f"Error hiding source: {e}")
            return False

    async def trigger_overlay(self, scene_name, source_name, data, duration=None):
        """Trigger an overlay with the specified data."""
        try:
            # Create/update the browser source
            source_url = f"http://{self.http_host}:{self.http_port}/overlays/{source_name}.html"
            if not await self.create_browser_source(scene_name, source_name, source_url):
                return False

            # Show the source
            if not await self.show_source(scene_name, source_name):
                return False

            # Update the browser source with the new data
            data_params = '?' + '&'.join(f"{k}={v}" for k, v in data.items())
            response = await self._make_request(
                requests.SetInputSettings,
                inputName=source_name,
                inputSettings={
                    "url": source_url + data_params,
                    "width": 1920,
                    "height": 1080,
                    "refresh": True
                }
            )
            if not response:
                logger.error(f"Failed to update overlay content: {source_name}")
                return False

            logger.info(f"Triggered overlay: {source_name}")

            # Schedule hiding the source after the specified duration
            hide_after = duration if duration is not None else self.overlay_duration
            if hide_after > 0:
                await asyncio.sleep(hide_after)
                await self.hide_source(scene_name, source_name)

            return True

        except Exception as e:
            logger.exception(f"Error triggering overlay: {e}")
            return False

async def setup_obs_integration(config):
    if not config.getboolean('Components', 'obs_integration', fallback=False):
        logger.info("OBS integration is disabled in config")
        return None

    try:
        obs_handler = OBSHandler(
            obs_host=config.get('OBS', 'host'),
            obs_port=config.getint('OBS', 'port'),
            password=config.get('OBS', 'password'),
            http_host=config.get('HTTPServer', 'host'),
            http_port=config.getint('HTTPServer', 'port')
        )
        await obs_handler.connect()
        await obs_handler.start_http_server()

        # Create overlays directory if needed
        if not os.path.exists('overlays'):
            logger.warning("Creating overlays directory - must add HTML files")
            os.makedirs('overlays')

        return obs_handler

    except Exception as e:
        logger.exception("Failed to setup OBS integration")
        return None

async def run_tests(handler):
    """Run integration tests for the OBS handler."""
    try:
        # Test scene management
        scenes = await handler.get_scene_list()
        print("Available scenes:", scenes)

        if scenes:
            current = await handler.get_current_scene()
            print("Current scene:", current)
            
            # Test scene switching
            print(f"Switching to scene: {scenes[0]}")
            await handler.switch_scene(scenes[0])
            
            # Test overlay
            print("Testing overlay...")
            await handler.trigger_overlay(
                scenes[0],
                "TestOverlay",
                {"message": "Test overlay"},
                duration=3
            )

    except Exception as e:
        logger.exception("Test failed")
    finally:
        await handler.disconnect()

if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("config.ini")

    async def main():
        handler = await setup_obs_integration(config)
        if handler:
            await run_tests(handler)

    asyncio.run(main())
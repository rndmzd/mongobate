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
    def __init__(self, obs_host, obs_port, obs_password, http_host, http_port):
        self.obs_host = obs_host
        self.obs_port = obs_port
        self.obs_password = obs_password
        self.http_host = http_host
        self.http_port = http_port
        self.ws = None
        self.app = web.Application()
        self.app.router.add_static('/overlays', 'overlays')
        self.app.router.add_get('/', self.handle_index)

    async def handle_index(self, request):
        return web.Response(text="OBS Integration Server is running")

    async def start_http_server(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.http_host, self.http_port)
        await site.start()
        logger.info(f"HTTP server started on http://{self.http_host}:{self.http_port}")

    async def connect(self):
        self.ws = obsws(self.obs_host, self.obs_port, self.obs_password)
        self.ws.connect()
        logger.info("Connected to OBS WebSocket")

    async def disconnect(self):
        if self.ws:
            self.ws.disconnect()
            logger.info("Disconnected from OBS WebSocket")

    async def create_browser_source(self, scene_name, source_name, url):
        try:
            # First, check if the source already exists
            scene_items = self.ws.call(requests.GetSceneItemList(sceneName=scene_name))
            logger.debug(f"scene_items: {scene_items}")
            source_exists = False
            if scene_items:
                source_exists = any(item['sourceName'] == source_name for item in scene_items.getSceneItemList())

            if not source_exists:
                logger.info(f"Browser source not found: {source_name}. Creating new source.")
                # Create the source if it doesn't exist
                create_source = requests.CreateInput(
                    sceneName=scene_name,
                    inputName=source_name,
                    inputKind="browser_source",
                    inputSettings={
                        "url": url,
                        "width": 1920,
                        "height": 1080
                    }
                )
                response = self.ws.call(create_source)
                if response.status:
                    logger.info(f"Created browser source: {source_name}")
                else:
                    logger.error(f"Failed to create browser source: {source_name}")
                    return

            # Update the source settings
            update_source = requests.SetInputSettings(
                inputName=source_name,
                inputSettings={
                    "url": url,
                    "width": 1920,
                    "height": 1080
                }
            )
            response = self.ws.call(update_source)
            if response.status:
                logger.info(f"Updated browser source settings: {source_name}")
            else:
                logger.error(f"Failed to update browser source settings: {source_name}")

        except Exception as e:
            logger.exception(f"Error creating/updating browser source: {e}")

    async def show_source(self, scene_name, source_name):
        try:
            set_visible = requests.SetSceneItemProperties(
                scene_name=scene_name,
                item=source_name,
                visible=True
            )
            response = self.ws.call(set_visible)
            if response.status:
                logger.info(f"Showed source: {source_name}")
            else:
                logger.error(f"Failed to show source: {source_name}")
        except Exception as e:
            logger.exception(f"Error showing source: {e}")

    async def hide_source(self, scene_name, source_name):
        try:
            set_invisible = requests.SetSceneItemProperties(
                scene_name=scene_name,
                item=source_name,
                visible=False
            )
            response = self.ws.call(set_invisible)
            if response.status:
                logger.info(f"Hid source: {source_name}")
            else:
                logger.error(f"Failed to hide source: {source_name}")
        except Exception as e:
            logger.exception(f"Error hiding source: {e}")

    async def trigger_overlay(self, scene_name, source_name, data):
        try:
            # First, ensure the source exists and is up to date
            await self.create_browser_source(scene_name, source_name, f"http://{self.http_host}:{self.http_port}/overlays/{source_name}.html")

            # Then, show the source
            await self.show_source(scene_name, source_name)

            # Finally, trigger the overlay with the data
            send_data = requests.SendBrowserSourceNavigate(
                sourceName=source_name,
                url=f"javascript:triggerOverlay({json.dumps(data)})"
            )
            response = self.ws.call(send_data)
            if response.status:
                logger.info(f"Triggered overlay: {source_name}")
            else:
                logger.error(f"Failed to trigger overlay: {source_name}")

            # Hide the source after a delay
            await asyncio.sleep(5)  # Adjust this delay as needed
            await self.hide_source(scene_name, source_name)

        except Exception as e:
            logger.exception(f"Error triggering overlay: {e}")

async def setup_obs_integration(config):
    if config.getboolean('Components', 'obs_integration', fallback=False):
        obs_handler = OBSHandler(
            obs_host=config.get('OBS', 'host'),
            obs_port=config.getint('OBS', 'port'),
            obs_password=config.get('OBS', 'password'),
            http_host=config.get('HTTPServer', 'host'),
            http_port=config.getint('HTTPServer', 'port')
        )
        await obs_handler.connect()
        await obs_handler.start_http_server()

        # Create the overlays directory if it doesn't exist
        if not os.path.exists('overlays'):
            logger.warning("Overlays directory not found, creating it. Must add html to function.")
            os.makedirs('overlays')

        # We don't need to create the browser source here anymore,
        # as it will be created or updated when triggered

        return obs_handler
    else:
        logger.info("OBS integration is disabled in the config")
        return None

# Example usage
if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("config.ini")

    asyncio.run(setup_obs_integration(config))
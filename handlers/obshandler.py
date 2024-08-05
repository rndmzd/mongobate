import asyncio
import logging
import json
from obswebsocket import obsws, requests
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
        return web.Response(text="OBS Integration Server is running.")

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

    async def show_source(self, scene_name, source_name):
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

    async def hide_source(self, scene_name, source_name):
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

    async def trigger_overlay(self, scene_name, source_name, data):
        send_data = requests.SendBrowserSourceNavigate(
            sourceName=source_name,
            url=f"javascript:triggerOverlay({json.dumps(data)})"
        )
        response = self.ws.call(send_data)
        if response.status:
            logger.info(f"Triggered overlay: {source_name}")
        else:
            logger.error(f"Failed to trigger overlay: {source_name}")

async def setup_obs_integration(config):
    obs_handler = OBSHandler(
        obs_host=config.get('OBS', 'host'),
        obs_port=config.getint('OBS', 'port'),
        obs_password=config.get('OBS', 'password'),
        http_host=config.get('HTTPServer', 'host'),
        http_port=config.getint('HTTPServer', 'port')
    )
    await obs_handler.connect()
    await obs_handler.start_http_server()

    if not os.path.exists('overlays'):
        os.makedirs('overlays')

    # Create a browser source for tips
    await obs_handler.create_browser_source(
        "Main", "TipOverlay", f"http://{config.get('HTTPServer', 'host')}:{config.get('HTTPServer', 'port')}/overlays/tip_overlay.html")

    return obs_handler

# Example usage
if __name__ == "__main__":
    asyncio.run(setup_obs_integration())
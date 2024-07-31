import asyncio
import logging
import json
from obswebsocket import obsws, requests

logger = logging.getLogger('mongobate.obshandler')
logger.setLevel(logging.DEBUG)

class OBSHandler:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.ws = None

    async def connect(self):
        self.ws = obsws(self.host, self.port, self.password)
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
        # Assuming the browser source is listening for a 'trigger' message
        send_data = requests.SendBrowserSourceNavigate(
            sourceName=source_name,
            url=f"javascript:triggerOverlay({json.dumps(data)})"
        )
        response = self.ws.call(send_data)
        if response.status:
            logger.info(f"Triggered overlay: {source_name}")
        else:
            logger.error(f"Failed to trigger overlay: {source_name}")

# Example usage
async def main():
    from . import config

    obs_handler = OBSHandler(
        host=config.get('OBS', 'host'),
        port=config.getint('OBS', 'port'),
        password=config.get('OBS', 'password')
    )

    await obs_handler.connect()

    # Create a browser source for tips
    await obs_handler.create_browser_source(
        "Main", "TipOverlay", "http://localhost:8000/tip_overlay.html")

    # Trigger the overlay when a tip is received
    await obs_handler.trigger_overlay("Main", "TipOverlay", {
        "username": "user123",
        "amount": 50,
        "message": "Great stream!"
    })

    # Hide the overlay after a few seconds
    await asyncio.sleep(5)
    await obs_handler.hide_source("Main", "TipOverlay")

    await obs_handler.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
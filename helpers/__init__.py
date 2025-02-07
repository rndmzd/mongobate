import configparser
import os
from pathlib import Path
from pymongo import MongoClient
from spotipy import Spotify, SpotifyOAuth

from helpers.actions import Actions
from helpers.checks import Checks
from helpers.cbevents import CBEvents
from helpers.commands import Commands
from utils.logging_config import setup_basic_logging

logger = setup_basic_logging(component='helpers')

config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)

logger.debug("mongodb.client.create",
            message="Creating MongoDB client")
mongo_config = config['MongoDB']
mongo_client = MongoClient(
    host=os.getenv('MONGO_HOST', mongo_config.get('host', 'localhost')),
    port=int(os.getenv('MONGO_PORT', mongo_config.getint('port', 27017))),
    username=os.getenv('MONGO_USERNAME', mongo_config.get('username')),
    password=os.getenv('MONGO_PASSWORD', mongo_config.get('password')),
    directConnection=True)
mongo_db = mongo_client[os.getenv('MONGO_DATABASE', mongo_config.get('db'))]

song_cache_collection = mongo_db[mongo_config.get('song_cache_collection')]
user_collection = mongo_db[mongo_config.get('user_collection')]

sp_oauth = SpotifyOAuth(
    client_id=config.get("Spotify", "client_id"),
    client_secret=config.get("Spotify", "client_secret"),
    redirect_uri=config.get("Spotify", "redirect_url"),
    scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-read-private",
    open_browser=False
)
spotify_client = Spotify(auth_manager=sp_oauth)
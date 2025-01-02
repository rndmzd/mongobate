import configparser
import structlog
import os
from pathlib import Path
from pymongo import MongoClient

from helpers.actions import Actions
from helpers.checks import Checks
from helpers.cbevents import CBEvents
from helpers.commands import Commands

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger('mongobate.helpers.__init__')

config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)

logger.debug('Creating MongoDB client.')
mongo_config = config['MongoDB']
mongo_client = MongoClient(
    host=os.getenv('MONGO_HOST', mongo_config.get('host', 'localhost')),
    port=int(os.getenv('MONGO_PORT', mongo_config.getint('port', 27017))),
    username=os.getenv('MONGO_USERNAME', mongo_config.get('username')),
    password=os.getenv('MONGO_PASSWORD', mongo_config.get('password')),
    directConnection=True)
mongo_db = mongo_client[os.getenv('MONGO_DATABASE', mongo_config.get('db'))]

song_cache_collection = mongo_db['song_cache_collection']

from handlers.dbhandler import DBHandler
from handlers.eventhandler import EventHandler

import configparser
import os
from pathlib import Path

config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)
from utils.jsonencoders import MongoJSONEncoder

import configparser
from pathlib import Path

config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)

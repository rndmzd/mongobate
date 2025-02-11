from .chatdj import SongExtractor
import configparser
from pathlib import Path
from .chatdj import AutoDJ


config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)

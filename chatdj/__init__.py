from .chatdj import SongExtractor  # Expose SongExtractor for external imports
import configparser
from pathlib import Path
from .chatdj import AutoDJ  # Expose AutoDJ for external imports


config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)

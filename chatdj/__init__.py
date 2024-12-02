#from chatdj.autodj import AutoDJ
#from chatdj.songextractor import SongExtractor
from chatdj.chatdj import AutoDJ, SongExtractor

import configparser
from pathlib import Path

config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)
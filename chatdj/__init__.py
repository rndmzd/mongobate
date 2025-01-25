#from chatdj.autodj import AutoDJ
#from chatdj.songextractor import SongExtractor
from chatdj.chatdj import AutoDJ, SongExtractor

import configparser
from pathlib import Path

config_path = Path(__file__).parent.parent / 'config.ini'

config = configparser.ConfigParser()
config.read(config_path)

from .chatdj import SongExtractor, AutoDJ

__all__ = [
    'SongExtractor',
    'AutoDJ'
]

__version__ = '0.1.0'
__author__ = 'Your Name'
__email__ = 'your.email@example.com'
"""Helpers package initialization."""
import logging

logger = logging.getLogger('mongobate.helpers')
logger.setLevel(logging.DEBUG)

# Import config first since other modules depend on it
from .config import config, song_cache_collection

# Then import the classes that use the config
from .commands import Commands
from .checks import Checks
from .actions import Actions
from .cbevents import CBEvents

__all__ = [
    'Actions',
    'Checks',
    'CBEvents',
    'Commands',
    'config',
    'song_cache_collection'
]

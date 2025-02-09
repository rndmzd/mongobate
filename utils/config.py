# Create a centralized config manager
import configparser
from pathlib import Path


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance

    def _init_config(self):
        self.config = configparser.ConfigParser()
        config_path = Path(__file__).parent.parent / 'config.ini'
        self.config.read(config_path)

    def get(self, section: str, key: str, fallback=None):
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback=None):
        return self.config.getint(section, key, fallback=fallback)

    def getboolean(self, section: str, key: str, fallback=None):
        return self.config.getboolean(section, key, fallback=fallback)

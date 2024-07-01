import configparser
import logging

logger = logging.getLogger('mongobate.eventhandler.actions')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")

class Checks:
    def __init__(self):
        self.song_cost = config.getint("General", "song_cost")
    
    def get_active_components(self):
        active_components = []
        for component in [comp for comp in config['Components']]:
            component_val = config.getboolean('Components', component)
            logger.debug(f"{component} -> {component_val}")
            if component_val:
                active_components.append(component)
        return active_components

    def is_song_request(self, tip_amount):
        if tip_amount % self.song_cost == 0:
            return True
        return False
    
    def get_request_count(self, tip_amount):
        return tip_amount // self.song_cost
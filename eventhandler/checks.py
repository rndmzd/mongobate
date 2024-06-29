import configparser
import logging

logger = logging.getLogger('eventhandler.actions')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")

class Checks:
    def __init__(self):
        self.song_cost = config.getint("Song", "song_cost")

    def is_song_request(self, tip_amount):
        if tip_amount % self.song_cost == 0:
            return True
        return False
    
    def get_request_count(self, tip_amount):
        return tip_amount // self.song_cost
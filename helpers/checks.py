import logging

logger = logging.getLogger('mongobate.helpers.checks')
logger.setLevel(logging.DEBUG)

class Checks:
    def __init__(self):
        from . import config

        self.config = config

        self.song_cost = self.config.getint("General", "song_cost")
        self.skip_song_cost = self.config.getint("General", "skip_song_cost")
        self.command_symbol = self.config.get("General", "command_symbol")
        self.spray_bottle_cost = self.config.getint("General", "spray_bottle_cost")
    
    def get_active_components(self):
        active_components = []
        for component in [comp for comp in self.config['Components']]:
            component_val = self.config.getboolean('Components', component)
            logger.debug(f"{component} -> {component_val}")
            if component_val:
                active_components.append(component)
        return active_components
    
    def is_skip_song_request(self, tip_amount):
        if tip_amount % self.skip_song_cost == 0:
            return True
        return False

    def is_song_request(self, tip_amount):
        if tip_amount % self.song_cost == 0:
            return True
        return False
    
    def get_request_count(self, tip_amount):
        return tip_amount // self.song_cost
    
    def get_command(self, message):
        # if message.startswith(self.command_symbol):
        if self.command_symbol in message:
            # command_elements = message.lstrip(self.command_symbol).split(" ")
            command_elements = message.split(self.command_symbol)[1].split(" ")
            command = {
                "command": command_elements[0],
                "args": command_elements[1:] if len(command_elements) > 1 else []
            }
            return command
        return None
    
    def is_spray_bottle_tip(self, tip_amount):
        if tip_amount == self.spray_bottle_cost:
            return True
        return False
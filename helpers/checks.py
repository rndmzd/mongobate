from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.helpers.checks')

class Checks:
    def __init__(self):
        from . import config

        self.config = config

        self.song_cost = self.config.getint("General", "song_cost")
        self.skip_song_cost = self.config.getint("General", "skip_song_cost")
        self.command_symbol = self.config.get("General", "command_symbol")
        self.spray_bottle_cost = self.config.getint("General", "spray_bottle_cost")
        
        logger.debug("checks.init",
                    message="Initialized checks",
                    data={
                        "song_cost": self.song_cost,
                        "skip_song_cost": self.skip_song_cost,
                        "command_symbol": self.command_symbol,
                        "spray_bottle_cost": self.spray_bottle_cost
                    })
    
    def get_active_components(self):
        active_components = []
        for component in [comp for comp in self.config['Components']]:
            component_val = self.config.getboolean('Components', component)
            logger.debug("checks.component",
                        message="Checking component status",
                        data={
                            "component": component,
                            "active": component_val
                        })
            if component_val:
                active_components.append(component)
                
        logger.info("checks.components",
                   message="Retrieved active components",
                   data={"active_components": active_components})
        return active_components
    
    def is_skip_song_request(self, tip_amount):
        is_skip = tip_amount % self.skip_song_cost == 0
        logger.debug("checks.skip_song",
                    message="Checking if tip is skip song request",
                    data={
                        "tip_amount": tip_amount,
                        "skip_cost": self.skip_song_cost,
                        "is_skip": is_skip
                    })
        return is_skip

    def is_song_request(self, tip_amount):
        is_request = tip_amount % self.song_cost == 0
        logger.debug("checks.song_request",
                    message="Checking if tip is song request",
                    data={
                        "tip_amount": tip_amount,
                        "song_cost": self.song_cost,
                        "is_request": is_request
                    })
        return is_request
    
    def get_request_count(self, tip_amount):
        count = tip_amount // self.song_cost
        logger.debug("checks.request_count",
                    message="Calculating song request count",
                    data={
                        "tip_amount": tip_amount,
                        "song_cost": self.song_cost,
                        "request_count": count
                    })
        return count
    
    def get_command(self, message):
        if self.command_symbol in message:
            command_elements = message.split(self.command_symbol)[1].split(" ")
            command = {
                "command": command_elements[0],
                "args": command_elements[1:] if len(command_elements) > 1 else []
            }
            logger.debug("checks.command",
                        message="Extracted command from message",
                        data={
                            "command": command["command"],
                            "args": command["args"]
                        })
            return command
            
        logger.debug("checks.command.none",
                    message="No command found in message",
                    data={"message": message})
        return None
    
    def is_spray_bottle_tip(self, tip_amount):
        is_spray = tip_amount == self.spray_bottle_cost
        logger.debug("checks.spray_bottle",
                    message="Checking if tip is spray bottle request",
                    data={
                        "tip_amount": tip_amount,
                        "spray_cost": self.spray_bottle_cost,
                        "is_spray": is_spray
                    })
        return is_spray
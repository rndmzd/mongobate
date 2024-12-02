import configparser
import logging

import yaml

logger = logging.getLogger('mongobate.helpers.commands')
logger.setLevel(logging.DEBUG)


class Commands:
    def __init__(self):
        from . import config
        
        self.commands_file = config.get('General', 'commands_file')
        self.commands = {}

    def refresh_commands(self):
        logger.debug("Refreshing commands.")
        with open(self.commands_file, 'r') as yaml_file:
            try:
                self.commands = yaml.safe_load(yaml_file)
                return True
            except yaml.YAMLError as exc:
                logger.error(exc)
                return False
                #raise exc
    
    def get_command_action(self, command):
        logger.debug(f"command: {command}")
        if not self.refresh_commands():
            return None
        if command['command'] not in self.commands:
            logger.warning(f"Unrecognized command: {command['command']}.")
            return None
        logger.debug(f"self.commands[command['command']]: {self.commands[command['command']]}")
        if "switchScene" in self.commands[command['command']].keys():
            return ('switchScene', self.commands[command['command']]['switchScene'])        
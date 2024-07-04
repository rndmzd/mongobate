import configparser
import logging

import yaml

logger = logging.getLogger('mongobate.helpers.commands')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")


class Commands:
    def __init__(self):
        self.commands = {}

    def refresh_commands(self):
        with open(config.get('General', 'commands_file'), 'r') as yaml_file:
            try:
                self.commands = yaml.safe_load(yaml_file)
                return True
            except yaml.YAMLError as exc:
                logger.error(exc)
                return False
                #raise exc
    
    def try_command(self, command):
        logger.debug(f"command: {command}")
        if not self.refresh_commands():
            return False
        if command not in self.commands:
            logger.warning(f'Unrecognized command: {command}.')
            return False
        # PROCESS COMMAND HERE
        ## TODO: User management commands, WTFU command?
        logger.debug(f"self.commands[command]: {self.commands[command]}")
        return True
        
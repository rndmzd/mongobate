import configparser
import logging

import yaml

logger = logging.getLogger('mongobate.helpers.commands')
logger.setLevel(logging.DEBUG)


class Commands:
    def __init__(self, actions=None):
        from . import config
        
        self.commands_file = config.get('General', 'commands_file')
        self.commands = {}

        self.actions = actions

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
    
    def try_command(self, command):
        try:
            logger.debug(f"command: {command}")
            if not self.refresh_commands():
                return False
            if command['command'] not in self.commands:
                logger.warning(f"Unrecognized command: {command['command']}.")
                return False
            # Process Commands
            logger.debug(f"self.commands[command['command']]: {self.commands[command['command']]}")
            if command['command'] == "WTFU":
                trigger_result = self.actions.trigger_couch_buzzer(duration=self.commands[command['command']]['duration'])
                logger.debug(f"trigger_result: {trigger_result}")
            elif command['command'] == "BRB":
                scene_result = self.actions.set_scene('brb')
                logger.debug(f"scene_result: {scene_result}")
            elif command['command'] == "LIVE":
                scene_result = self.actions.set_scene('main')
                logger.debug(f"scene_result: {scene_result}")
            return True
        except Exception as e:
            logger.exception('Failed to process command.', exc_info=e)
            return False
        
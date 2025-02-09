
import yaml

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.helpers.commands')


class Commands:
    def __init__(self, actions=None):
        from . import config

        self.commands_file = config.get('General', 'commands_file')
        self.commands = {}
        self.actions = actions

        logger.debug("commands.init",
                    message="Initialized commands handler",
                    data={"commands_file": self.commands_file})

    def refresh_commands(self):
        logger.debug("commands.refresh",
                    message="Refreshing commands from file")
        with open(self.commands_file, 'r') as yaml_file:
            try:
                self.commands = yaml.safe_load(yaml_file)
                logger.info("commands.refresh.success",
                          message="Successfully refreshed commands",
                          data={"command_count": len(self.commands)})
                return True
            except yaml.YAMLError as exc:
                logger.exception("commands.refresh.error",
                               exc=exc,
                               message="Failed to refresh commands")
                return False

    def try_command(self, command):
        try:
            logger.debug("commands.process",
                        message="Processing command",
                        data={"command": command})

            if not self.refresh_commands():
                return False

            if command['command'] not in self.commands:
                logger.warning("commands.unknown",
                             message="Unrecognized command",
                             data={"command": command['command']})
                return False

            # Process Commands
            logger.debug("commands.execute",
                        message="Executing command",
                        data={
                            "command": command['command'],
                            "config": self.commands[command['command']]
                        })

            if command['command'] == "WTFU":
                duration = self.commands[command['command']]['duration']
                trigger_result = self.actions.trigger_couch_buzzer(duration=duration)
                logger.info("commands.buzzer",
                          message="Triggered couch buzzer",
                          data={
                              "duration": duration,
                              "success": trigger_result
                          })

            elif command['command'] == "BRB":
                scene_result = self.actions.set_scene('brb')
                logger.info("commands.scene",
                          message="Set BRB scene",
                          data={"success": scene_result})

            elif command['command'] == "LIVE":
                scene_result = self.actions.set_scene('main')
                logger.info("commands.scene",
                          message="Set LIVE scene",
                          data={"success": scene_result})

            return True

        except Exception as exc:
            logger.exception("commands.error",
                           exc=exc,
                           message="Failed to process command",
                           data={"command": command})
            return False

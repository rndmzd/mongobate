import configparser
import structlog
import yaml

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger('mongobate.helpers.commands')


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
    
    def try_command(self, command):
        logger.debug("Trying command", command=command)
        if not self.refresh_commands():
            return False
        if command['command'] not in self.commands:
            logger.warning("Unrecognized command", command=command['command'])
            return False
        # PROCESS COMMAND HERE
        ## TODO: User management commands, WTFU command?
        logger.debug("Command details", command_details=self.commands[command['command']])
        return True

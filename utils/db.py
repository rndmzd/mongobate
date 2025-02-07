# Create a database connection manager
from pymongo import MongoClient
import urllib.parse
from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.utils.db')

class DatabaseManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            logger.debug("database.singleton.create",
                        message="Creating new DatabaseManager instance")
            cls._instance = super().__new__(cls)
            cls._instance._init_connection()
        return cls._instance
    
    def _init_connection(self):
        from utils.config import ConfigManager
        config = ConfigManager()
        
        # Build connection URI
        if aws_key := config.get('MongoDB', 'aws_key'):
            logger.debug("database.connect.aws",
                        message="Using AWS authentication for MongoDB connection")
            self.client = self._get_aws_connection(config)
        else:
            logger.debug("database.connect.standard",
                        message="Using standard authentication for MongoDB connection")
            self.client = self._get_standard_connection(config)
            
        self.db = self.client[config.get('MongoDB', 'db')]
        logger.info("database.connect.success",
                   message="Database connection established",
                   data={"database": config.get('MongoDB', 'db')})
        
    def _get_aws_connection(self, config):
        try:
            aws_key = urllib.parse.quote_plus(config.get('MongoDB', 'aws_key'))
            aws_secret = urllib.parse.quote_plus(config.get('MongoDB', 'aws_secret'))
            host = urllib.parse.quote_plus(config.get('MongoDB', 'host'))
            port = urllib.parse.quote_plus(config.get('MongoDB', 'port'))
            
            uri = f"mongodb://{aws_key}:****@[{host}]:{port}/?authMechanism=MONGODB-AWS&authSource=$external"
            logger.debug("database.connect.aws.uri",
                        message="Built AWS connection URI",
                        data={"host": host, "port": port})
            return MongoClient(uri)
        except Exception as exc:
            logger.exception("database.connect.aws.error",
                           exc=exc,
                           message="Failed to establish AWS MongoDB connection")
            raise
        
    def _get_standard_connection(self, config):
        try:
            host = config.get('MongoDB', 'host')
            port = config.getint('MongoDB', 'port')
            logger.debug("database.connect.standard.params",
                        message="Building standard connection",
                        data={"host": host, "port": port})
            return MongoClient(
                host=host,
                port=port,
                username=config.get('MongoDB', 'username'),
                password="****",  # Don't log the actual password
                directConnection=True
            )
        except Exception as exc:
            logger.exception("database.connect.standard.error",
                           exc=exc,
                           message="Failed to establish standard MongoDB connection")
            raise 

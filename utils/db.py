# Create a database connection manager
from pymongo import MongoClient
import urllib.parse

class DatabaseManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_connection()
        return cls._instance
    
    def _init_connection(self):
        from utils.config import ConfigManager
        config = ConfigManager()
        
        # Build connection URI
        if aws_key := config.get('MongoDB', 'aws_key'):
            self.client = self._get_aws_connection(config)
        else:
            self.client = self._get_standard_connection(config)
            
        self.db = self.client[config.get('MongoDB', 'db')]
        
    def _get_aws_connection(self, config):
        aws_key = urllib.parse.quote_plus(config.get('MongoDB', 'aws_key'))
        aws_secret = urllib.parse.quote_plus(config.get('MongoDB', 'aws_secret'))
        host = urllib.parse.quote_plus(config.get('MongoDB', 'host'))
        port = urllib.parse.quote_plus(config.get('MongoDB', 'port'))
        
        uri = f"mongodb://{aws_key}:{aws_secret}@[{host}]:{port}/?authMechanism=MONGODB-AWS&authSource=$external"
        return MongoClient(uri)
        
    def _get_standard_connection(self, config):
        return MongoClient(
            host=config.get('MongoDB', 'host'),
            port=config.getint('MongoDB', 'port'),
            username=config.get('MongoDB', 'username'),
            password=config.get('MongoDB', 'password'),
            directConnection=True
        ) 
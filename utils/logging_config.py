import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

from utils.elastic import AsyncElasticsearchHandler
from utils.config import ConfigManager

def setup_logging(logger_name='mongobate', component=None):
    """
    Set up logging configuration for the application.
    
    Args:
        logger_name: Base name for the logger
        component: Optional component name to append to logger name
    """
    config = ConfigManager()
    
    # Create logger
    logger_name = f"{logger_name}.{component}" if component else logger_name
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    
    # Create formatters
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Add console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    # Add file handler
    log_file = config.get("Logging", "log_file")
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.getint("Logging", "log_max_size_mb") * 1024 * 1024,
        backupCount=config.getint("Logging", "log_backup_count"),
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Add Elasticsearch handler if enabled
    if config.getboolean("Logging", "elasticsearch_enabled", fallback=False):
        try:
            # Get Elasticsearch config
            es_host = config.get("Elasticsearch", "host")
            es_port = config.getint("Elasticsearch", "port")
            es_index = config.get("Elasticsearch", "index_prefix")
            es_use_ssl = config.getboolean("Elasticsearch", "use_ssl")
            es_api_key = config.get("Elasticsearch", "api_key", fallback=None)
            
            # Create and add Elasticsearch handler
            es_handler = AsyncElasticsearchHandler(
                host=es_host,
                port=es_port,
                index_prefix=es_index,
                api_key=es_api_key,
                use_ssl=es_use_ssl
            )
            es_handler.setFormatter(formatter)
            logger.addHandler(es_handler)
            
            logger.info("Elasticsearch logging enabled with API key authentication")
        except Exception as e:
            logger.error(f"Failed to initialize Elasticsearch logging: {str(e)}")
    
    return logger 
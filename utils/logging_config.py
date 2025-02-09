import datetime
import json
import logging
import os
import socket
import traceback
from logging.handlers import RotatingFileHandler

from bson import ObjectId

from utils.config import ConfigManager
from utils.elastic import AsyncElasticsearchHandler


class MongoAwareJSONEncoder(json.JSONEncoder):
    """JSON encoder that can handle MongoDB types and OpenAI objects."""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, (datetime.date, datetime.time)):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        # Handle OpenAI ChatCompletion and related objects
        if hasattr(obj, 'model_dump'):  # For Pydantic models (OpenAI response objects)
            return obj.model_dump()
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def __init__(self):
        super().__init__()
        self.hostname = socket.gethostname()

    def format(self, record):
        # Base log record
        log_obj = {
            "@timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "host": self.hostname,
            "process": {
                "id": record.process,
                "name": record.processName
            },
            "thread": {
                "id": record.thread,
                "name": record.threadName
            },
            "code": {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName
            }
        }

        # Handle structured logging records
        if isinstance(record.msg, dict):
            # Add all fields from the structured log
            log_obj.update(record.msg)
        else:
            # Legacy string messages
            log_obj["message"] = record.getMessage()

        # Add exception info if present
        if record.exc_info:
            log_obj["error"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "stack_trace": traceback.format_exception(*record.exc_info)
            }

        return json.dumps(log_obj, cls=MongoAwareJSONEncoder)

def setup_basic_logging(logger_name='mongobate', component=None):
    """
    Set up basic logging configuration without Elasticsearch.
    This is safe to use at module level initialization.

    Args:
        logger_name: Base name for the logger
        component: Optional component name to append to logger name
    """
    config = ConfigManager()

    # Set up root logger first
    root_logger = logging.getLogger(logger_name)
    if not root_logger.handlers:  # Only set up root logger once
        root_logger.setLevel(logging.DEBUG)

        # Create JSON formatter
        json_formatter = JSONFormatter()

        # Add console handler with JSON formatting
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(json_formatter)
        root_logger.addHandler(stream_handler)

        # Add file handler with JSON formatting
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
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

    # Create component logger if needed
    if component:
        logger = logging.getLogger(f"{logger_name}.{component}")
        logger.setLevel(logging.DEBUG)
        # Don't add handlers to component loggers, let them propagate to root
        return logger

    return root_logger

async def setup_logging(logger_name='mongobate', component=None):
    """
    Set up full logging configuration including Elasticsearch.
    Must be called from an async context.

    Args:
        logger_name: Base name for the logger
        component: Optional component name to append to logger name
    """
    # First set up basic logging
    logger = setup_basic_logging(logger_name, component)

    config = ConfigManager()

    # Add Elasticsearch handler if enabled - only to root logger
    if config.getboolean("Logging", "elasticsearch_enabled", fallback=False):
        root_logger = logging.getLogger(logger_name)
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
            es_handler.setFormatter(JSONFormatter())

            # Initialize the handler
            await es_handler.initialize()

            # Only add ES handler to root logger
            if es_handler not in root_logger.handlers:
                root_logger.addHandler(es_handler)

            logger.info({
                "event_type": "elasticsearch.init",
                "message": "Elasticsearch logging enabled with API key authentication"
            })
        except Exception as e:
            logger.error({
                "event_type": "elasticsearch.init.error",
                "message": "Failed to initialize Elasticsearch logging",
                "error": {
                    "type": type(e).__name__,
                    "message": str(e)
                }
            })

    return logger

async def cleanup_logging():
    """Cleanup function to properly close async logging handlers."""
    try:
        root_logger = logging.getLogger()

        # Disable all logging first
        logging.disable(logging.CRITICAL)

        # Close all handlers
        for handler in root_logger.handlers[:]:
            try:
                if hasattr(handler, 'aclose'):
                    await handler.aclose()
                else:
                    handler.close()
                root_logger.removeHandler(handler)
            except Exception as exc:
                print(f"Error handling logger {handler}: {exc}")

    except Exception as exc:
        print(f"Critical error during logging cleanup: {exc}")
    finally:
        # Re-enable logging
        logging.disable(logging.NOTSET)

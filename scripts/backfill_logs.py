import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import datetime
import glob
import re
import socket
from typing import Dict, List, Optional
import time

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from elasticsearch.exceptions import ApiError, ConnectionError, TransportError

from utils.config import ConfigManager
from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.scripts.backfill')

# Regular expression to parse log lines
LOG_PATTERN = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})'
    r' - (?P<logger>[\w\.]+)'
    r' - (?P<level>\w+)'
    r' - (?P<message>.*)'
)

async def parse_log_file(file_path: str) -> List[Dict]:
    """Parse a log file and return a list of log entries."""
    documents = []
    hostname = socket.gethostname()
    
    try:
        logger.debug("backfill.parse.start",
                    message="Starting to parse log file",
                    data={"file": file_path})
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                match = LOG_PATTERN.match(line.strip())
                if match:
                    timestamp = datetime.datetime.strptime(
                        match.group('timestamp'),
                        '%Y-%m-%d %H:%M:%S,%f'
                    )
                    
                    # Create the document
                    doc = {
                        '@timestamp': timestamp.isoformat(),
                        'host': hostname,
                        'level': match.group('level'),
                        'logger': match.group('logger'),
                        'message': match.group('message'),
                        'source_file': os.path.basename(file_path),
                        'backfilled': True
                    }
                    
                    # Get the index name based on the log timestamp
                    index_name = f"mongobate-{timestamp.strftime('%Y.%m.%d')}"
                    
                    documents.append({
                        '_index': index_name,
                        '_source': doc
                    })
                
                # Handle multi-line entries (like stack traces)
                else:
                    if documents:  # Append to the last message if it exists
                        documents[-1]['_source']['message'] += f"\n{line.strip()}"
        
        logger.info("backfill.parse.complete",
                   message="Completed parsing log file",
                   data={
                       "file": file_path,
                       "documents": len(documents)
                   })
    
    except Exception as exc:
        logger.exception("backfill.parse.error",
                        exc=exc,
                        message="Failed to parse log file",
                        data={"file": file_path})
    
    return documents

async def retry_with_backoff(func, max_retries=3, initial_backoff=1):
    """Execute a function with exponential backoff retry logic."""
    backoff = initial_backoff
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func()
        except (ConnectionError, TransportError) as exc:
            last_exception = exc
            if attempt == max_retries - 1:
                logger.exception("backfill.retry.failed",
                               exc=exc,
                               message="Max retries exceeded",
                               data={
                                   "attempt": attempt + 1,
                                   "max_retries": max_retries
                               })
                raise
            
            logger.warning("backfill.retry.attempt",
                         message="Retrying after connection error",
                         data={
                             "attempt": attempt + 1,
                             "max_retries": max_retries,
                             "backoff_seconds": backoff
                         })
            await asyncio.sleep(backoff)
            backoff *= 2
    
    raise last_exception

async def bulk_index_with_retry(es_client, documents, chunk_size=500):
    """Bulk index documents with retry logic."""
    async def _do_bulk():
        return await async_bulk(
            es_client,
            documents,
            chunk_size=chunk_size,
            max_retries=3,
            raise_on_error=False
        )
    
    return await retry_with_backoff(_do_bulk)

async def backfill_logs():
    """Main function to backfill logs into Elasticsearch."""
    config = ConfigManager()
    
    # Get Elasticsearch configuration
    es_host = config.get("Elasticsearch", "host")
    es_port = config.getint("Elasticsearch", "port")
    es_use_ssl = config.getboolean("Elasticsearch", "use_ssl")
    es_api_key = config.get("Elasticsearch", "api_key")
    
    logger.info("backfill.init",
                message="Initializing Elasticsearch client",
                data={
                    "host": es_host,
                    "port": es_port,
                    "use_ssl": es_use_ssl,
                    "has_api_key": bool(es_api_key)
                })
    
    # Initialize Elasticsearch client
    # Force HTTPS since the server requires it
    hosts = [f"https://{es_host}:{es_port}"]
    client_kwargs = {
        'verify_certs': False,  # Skip certificate verification if using self-signed certs
        'ssl_show_warn': False  # Suppress SSL warnings
    }
    
    # Handle authentication
    if es_api_key:
        logger.debug("backfill.auth",
                    message="Using API key authentication")
        client_kwargs['api_key'] = es_api_key
    else:
        logger.warning("backfill.auth.missing",
                      message="No API key provided for Elasticsearch authentication")
        
    es_client = AsyncElasticsearch(
        hosts,
        retry_on_timeout=True,
        max_retries=3,
        **client_kwargs
    )
    
    try:
        # Test connection
        logger.debug("backfill.connect.test",
                    message="Testing Elasticsearch connection")
        try:
            info = await es_client.info()
            logger.info("backfill.connect.success",
                       message="Connected to Elasticsearch",
                       data={"version": info['version']['number']})
        except Exception as exc:
            logger.exception("backfill.connect.error",
                           exc=exc,
                           message="Failed to connect to Elasticsearch")
            return
        
        # Get all log files
        log_dir = Path(config.get("Logging", "log_file")).parent
        log_files = glob.glob(str(log_dir / "*.log*"))
        
        logger.info("backfill.files",
                   message="Found log files to process",
                   data={"count": len(log_files)})
        
        # Process each log file
        total_docs = 0
        for log_file in log_files:
            logger.info("backfill.process.start",
                       message="Processing log file",
                       data={"file": log_file})
            
            documents = await parse_log_file(log_file)
            
            if documents:
                # Split documents into smaller chunks
                chunk_size = 100
                for i in range(0, len(documents), chunk_size):
                    chunk = documents[i:i + chunk_size]
                    try:
                        success, failed = await bulk_index_with_retry(es_client, chunk)
                        logger.info("backfill.index.success",
                                  message="Indexed documents from file",
                                  data={
                                      "file": log_file,
                                      "chunk": i//chunk_size + 1,
                                      "success": success,
                                      "failed": len(failed) if failed else 0
                                  })
                        total_docs += success
                    except Exception as exc:
                        logger.exception("backfill.index.error",
                                       exc=exc,
                                       message="Failed to index documents",
                                       data={
                                           "file": log_file,
                                           "chunk": i//chunk_size + 1
                                       })
            
            logger.info("backfill.process.complete",
                       message="Completed processing file",
                       data={"file": log_file})
        
        logger.info("backfill.complete",
                   message="Backfill process completed",
                   data={"total_documents": total_docs})
    
    finally:
        await es_client.close()

if __name__ == "__main__":
    logger.info("backfill.start", message="Starting log backfill process")
    asyncio.run(backfill_logs()) 
import asyncio
import datetime
import glob
import os
import re
from pathlib import Path
import socket
from typing import Dict, List, Optional

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from utils.config import ConfigManager

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
    
    except Exception as e:
        print(f"Error processing file {file_path}: {str(e)}")
    
    return documents

async def backfill_logs():
    """Main function to backfill logs into Elasticsearch."""
    config = ConfigManager()
    
    # Get Elasticsearch configuration
    es_host = config.get("Elasticsearch", "host")
    es_port = config.getint("Elasticsearch", "port")
    es_use_ssl = config.getboolean("Elasticsearch", "use_ssl")
    es_api_key = config.get("Elasticsearch", "api_key")
    
    # Initialize Elasticsearch client
    es_client = AsyncElasticsearch(
        [{'host': es_host, 'port': es_port}],
        api_key=es_api_key,
        use_ssl=es_use_ssl,
        verify_certs=es_use_ssl
    )
    
    try:
        # Get all log files
        log_dir = Path(config.get("Logging", "log_file")).parent
        log_files = glob.glob(str(log_dir / "*.log*"))
        
        print(f"Found {len(log_files)} log files to process")
        
        # Process each log file
        total_docs = 0
        for log_file in log_files:
            print(f"Processing {log_file}...")
            documents = await parse_log_file(log_file)
            
            if documents:
                # Bulk index the documents
                try:
                    success, failed = await async_bulk(
                        es_client,
                        documents,
                        chunk_size=500,
                        max_retries=3,
                        raise_on_error=False
                    )
                    print(f"Indexed {success} documents from {log_file}")
                    if failed:
                        print(f"Failed to index {len(failed)} documents")
                    total_docs += success
                except Exception as e:
                    print(f"Error bulk indexing documents from {log_file}: {str(e)}")
            
            print(f"Completed processing {log_file}")
        
        print(f"\nBackfill complete. Total documents indexed: {total_docs}")
    
    finally:
        await es_client.close()

if __name__ == "__main__":
    print("Starting log backfill process...")
    asyncio.run(backfill_logs()) 
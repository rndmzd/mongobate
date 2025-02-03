import logging
import datetime
import asyncio
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ElasticsearchException
import socket
import json
from typing import Optional

class AsyncElasticsearchHandler(logging.Handler):
    def __init__(self, host: str, port: int, index_prefix: str = 'mongobate', 
                 api_key: Optional[str] = None, use_ssl: bool = False):
        super().__init__()
        
        # Initialize Elasticsearch client
        self.es_client = AsyncElasticsearch(
            [{'host': host, 'port': port}],
            api_key=api_key,
            use_ssl=use_ssl,
            verify_certs=use_ssl
        )
        
        self.index_prefix = index_prefix
        self.hostname = socket.gethostname()
        self._queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._worker_task = None
        
        # Set default formatter
        self.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

        # Start the background worker
        self._start_worker()

    def _get_index_name(self) -> str:
        """Generate index name with date suffix."""
        return f"{self.index_prefix}-{datetime.datetime.now().strftime('%Y.%m.%d')}"

    def _start_worker(self):
        """Start the background worker task."""
        loop = asyncio.get_event_loop()
        self._worker_task = loop.create_task(self._worker())

    async def _worker(self):
        """Background worker that processes the log queue."""
        while not self._stop_event.is_set():
            try:
                # Get batch of records (up to 100) with 1 second timeout
                batch = []
                try:
                    while len(batch) < 100:
                        record = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                        batch.append(record)
                except asyncio.TimeoutError:
                    pass

                if batch:
                    # Process batch
                    actions = []
                    for record in batch:
                        actions.append({
                            '_index': self._get_index_name(),
                            '_source': record
                        })

                    # Bulk index the documents
                    if actions:
                        await self.es_client.bulk(body=actions)

            except Exception as e:
                print(f"Error in Elasticsearch worker: {str(e)}")
                await asyncio.sleep(1)  # Prevent tight loop on persistent errors

    def emit(self, record):
        """Put log record into the async queue."""
        try:
            # Format the record
            msg = self.format(record)
            
            # Prepare the document
            doc = {
                '@timestamp': datetime.datetime.utcnow().isoformat(),
                'host': self.hostname,
                'level': record.levelname,
                'logger': record.name,
                'message': msg,
                'path': record.pathname,
                'function': record.funcName,
                'line_number': record.lineno,
            }
            
            # Add exception info if present
            if record.exc_info:
                doc['exception'] = {
                    'type': str(record.exc_info[0].__name__),
                    'message': str(record.exc_info[1]),
                    'traceback': self.formatter.formatException(record.exc_info)
                }
            
            # Add extra fields if present
            if hasattr(record, 'extra_fields'):
                doc.update(record.extra_fields)

            # Add to queue
            asyncio.get_event_loop().call_soon_threadsafe(
                self._queue.put_nowait, doc
            )
            
        except Exception as e:
            print(f"Error queueing log message: {str(e)}")

    async def close(self):
        """Gracefully shut down the handler."""
        self._stop_event.set()
        if self._worker_task:
            # Wait for worker to complete with timeout
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                print("Timeout waiting for Elasticsearch worker to complete")
        
        # Close the client
        await self.es_client.close()

    def __del__(self):
        """Ensure resources are cleaned up."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.close())
            else:
                loop.run_until_complete(self.close())
        except Exception as e:
            print(f"Error closing Elasticsearch handler: {str(e)}") 
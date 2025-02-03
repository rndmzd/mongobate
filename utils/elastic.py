import logging
import datetime
import asyncio
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ApiError
import socket
import json
from typing import Optional
import atexit
import threading
from queue import Queue
import signal

class AsyncElasticsearchHandler(logging.Handler):
    def __init__(self, host: str, port: int, index_prefix: str = 'mongobate', 
                 api_key: Optional[str] = None, use_ssl: bool = False):
        super().__init__()
        
        # Initialize Elasticsearch client
        hosts = [f'{"https" if use_ssl else "http"}://{host}:{port}']
        client_kwargs = {}
        if api_key:
            client_kwargs['api_key'] = api_key
        if use_ssl:
            client_kwargs['verify_certs'] = True
            
        self.es_client = AsyncElasticsearch(
            hosts,
            **client_kwargs
        )
        
        self.index_prefix = index_prefix
        self.hostname = socket.gethostname()
        self._queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._worker_task = None
        self._closed = False
        self._main_loop = asyncio.get_event_loop()
        self._thread_queues = {}
        self._thread_workers = set()
        
        # Set default formatter
        self.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

        # Start the background worker
        self._start_worker()
        
        # Register signal handlers
        try:
            self._main_loop.add_signal_handler(signal.SIGINT, lambda: self._main_loop.create_task(self._handle_shutdown()))
            self._main_loop.add_signal_handler(signal.SIGTERM, lambda: self._main_loop.create_task(self._handle_shutdown()))
        except NotImplementedError:
            # Windows doesn't support SIGTERM
            pass

    async def _handle_shutdown(self):
        """Handle shutdown gracefully."""
        if not self._closed:
            print("Shutting down Elasticsearch handler...")
            await self.close()
            print("Elasticsearch handler shutdown complete.")

    def _cleanup(self):
        """Cleanup handler on program exit"""
        if not self._closed:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.close())
                loop.close()
            except Exception as e:
                print(f"Error during Elasticsearch handler cleanup: {str(e)}")

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

            # Get current thread ID
            thread_id = threading.get_ident()
            
            # If we're in the main thread, we can use the event loop directly
            if thread_id == threading.main_thread().ident:
                self._main_loop.call_soon_threadsafe(
                    self._queue.put_nowait, doc
                )
            else:
                # For other threads, use a thread-safe queue
                if thread_id not in self._thread_queues:
                    self._thread_queues[thread_id] = Queue()
                    # Start a thread-specific worker
                    self._start_thread_worker(thread_id)
                
                self._thread_queues[thread_id].put(doc)
            
        except Exception as e:
            print(f"Error queueing log message: {str(e)}")

    def _start_thread_worker(self, thread_id):
        """Start a worker for a specific thread."""
        async def thread_worker():
            thread_queue = self._thread_queues[thread_id]
            while not self._stop_event.is_set():
                try:
                    while not thread_queue.empty() and not self._stop_event.is_set():
                        doc = thread_queue.get_nowait()
                        await self._queue.put(doc)
                except Exception as e:
                    if not self._stop_event.is_set():
                        print(f"Error in thread worker: {str(e)}")
                await asyncio.sleep(0.1)

        worker_task = self._main_loop.create_task(thread_worker())
        self._thread_workers.add(worker_task)
        worker_task.add_done_callback(lambda t: self._thread_workers.remove(t))

    async def close(self):
        """Gracefully shut down the handler."""
        if self._closed:
            return
            
        self._closed = True
        self._stop_event.set()
        
        # Wait for thread workers to complete
        if self._thread_workers:
            await asyncio.gather(*self._thread_workers, return_exceptions=True)
        
        # Wait for main worker
        if self._worker_task:
            try:
                # Process remaining items in queue
                while not self._queue.empty():
                    try:
                        await asyncio.wait_for(self._process_queue(), timeout=1.0)
                    except asyncio.TimeoutError:
                        break
                    
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                print("Timeout waiting for Elasticsearch worker to complete")
            except Exception as e:
                print(f"Error waiting for worker task: {str(e)}")
        
        # Close Elasticsearch client
        try:
            await self.es_client.close()
        except Exception as e:
            print(f"Error closing Elasticsearch client: {str(e)}")

    async def _process_queue(self):
        """Process items in the queue."""
        batch = []
        while not self._queue.empty() and len(batch) < 100:
            try:
                record = self._queue.get_nowait()
                batch.append(record)
            except asyncio.QueueEmpty:
                break

        if batch:
            actions = [{
                '_index': self._get_index_name(),
                '_source': record
            } for record in batch]
            
            try:
                await self.es_client.bulk(body=actions)
            except Exception as e:
                print(f"Error bulk indexing documents: {str(e)}")

    def __del__(self):
        """Ensure resources are cleaned up."""
        self._cleanup() 
import logging
import datetime
import asyncio
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ApiError, ConnectionError, TransportError
from elasticsearch.transport import AsyncTransport
import socket
import json
from typing import Optional
import atexit
import threading
from queue import Queue
import signal
import backoff
import warnings
import aiohttp
import sys
import ssl
from bson import ObjectId

class MongoJsonEncoder(json.JSONEncoder):
    """JSON encoder that can handle MongoDB types."""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8')
        return super().default(obj)

class AsyncElasticsearchHandler(logging.Handler):
    def __init__(self, host: str, port: int, index_prefix: str = 'mongobate', 
                 api_key: Optional[str] = None, use_ssl: bool = False,
                 retry_max_time: int = 60):
        super().__init__()
        
        # Store initialization parameters
        self.host = host
        self.port = port
        self.index_prefix = index_prefix
        self.api_key = api_key
        self.use_ssl = use_ssl
        self.retry_max_time = retry_max_time
        
        self.hostname = socket.gethostname()
        self._queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._worker_task = None
        self._closed = False
        self._initialized = False
        self._main_loop = None
        self._thread_queues = {}
        self._thread_workers = set()
        self._reconnect_delay = 1  # Start with 1 second delay
        self.es_client = None
        self._http_session = None
        self.json_encoder = MongoJsonEncoder()
        
        # Set default formatter
        self.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        
        # Register cleanup on interpreter shutdown
        atexit.register(self._sync_cleanup)

    def _sync_cleanup(self):
        """Synchronous cleanup for interpreter shutdown."""
        if self._main_loop and not self._main_loop.is_closed():
            try:
                self._main_loop.run_until_complete(self.close())
            except Exception:
                pass

    async def initialize(self):
        """Initialize the handler and start the worker."""
        if self._initialized:
            return
            
        # Get or create event loop
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._main_loop)

        # Create shared HTTP session with TCP connector settings
        connector = aiohttp.TCPConnector(
            force_close=True,
            enable_cleanup_closed=True
        )
        self._http_session = aiohttp.ClientSession(connector=connector)
        
        await self._connect_to_elasticsearch()

        # Start the background worker
        self._worker_task = self._main_loop.create_task(self._worker())
        self._initialized = True

    async def _connect_to_elasticsearch(self):
        """Connect to Elasticsearch with retry logic."""
        # Close existing client if any
        if self.es_client:
            try:
                await self.es_client.close()
            except Exception:
                pass
            self.es_client = None
            
        while True:
            try:
                # Initialize Elasticsearch client
                scheme = "https"  # Always use HTTPS since server requires it
                hosts = [{"host": self.host, "port": self.port, "scheme": scheme}]
                
                # Create SSL context that accepts self-signed certificates
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                client_kwargs = {
                    'hosts': hosts,
                    'request_timeout': 30,
                    'retry_on_timeout': True,
                    'max_retries': 3,
                    'connections_per_node': 10,
                    'ssl_context': ssl_context,  # Use our custom SSL context
                }
                if self.api_key:
                    client_kwargs['api_key'] = self.api_key
                
                self.es_client = AsyncElasticsearch(**client_kwargs)
                
                # Test the connection
                await self.es_client.info()
                print(f"Successfully connected to Elasticsearch at {self.host}:{self.port}")
                self._reconnect_delay = 1  # Reset delay on successful connection
                return
                
            except Exception as e:
                print(f"Failed to connect to Elasticsearch: {str(e)}", file=sys.stderr)
                if self._stop_event.is_set():
                    return
                    
                # Exponential backoff with max delay of 30 seconds
                await asyncio.sleep(min(self._reconnect_delay, 30))
                self._reconnect_delay *= 2

    async def _ensure_connection(self):
        """Ensure Elasticsearch connection is active."""
        if not self.es_client:
            await self._connect_to_elasticsearch()
            return False
            
        try:
            await self.es_client.info()
            return True
        except Exception:
            await self._connect_to_elasticsearch()
            return False

    @backoff.on_exception(backoff.expo, 
                         (ConnectionError, TransportError),
                         max_time=60)
    async def _bulk_index(self, actions):
        """Send bulk index request with retry logic."""
        if not self.es_client:
            return
            
        try:
            if not await self._ensure_connection():
                return
            # Convert actions to NDJSON format
            body = '\n'.join(json.dumps(action, cls=MongoJsonEncoder) for action in actions) + '\n'
            await self.es_client.bulk(body=body)
        except Exception as e:
            print(f"Error bulk indexing to Elasticsearch: {str(e)}", file=sys.stderr)
            raise

    async def _worker(self):
        """Background worker that processes the log queue."""
        while not self._stop_event.is_set():
            try:
                # Get batch of records (up to 100) with 1 second timeout
                batch = []
                try:
                    while len(batch) < 100:
                        record = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                        if record:  # Skip None records
                            batch.append(record)
                except asyncio.TimeoutError:
                    pass

                if batch and self.es_client:
                    # Process batch
                    actions = []
                    for record in batch:
                        # Add the action type in the metadata line
                        index_name = self._get_index_name()
                        actions.extend([
                            {'index': {'_index': index_name}},
                            record
                        ])

                    # Bulk index the documents with retry
                    if actions:
                        try:
                            await self._bulk_index(actions)
                        except Exception as e:
                            if not self._stop_event.is_set():
                                print(f"Error bulk indexing to Elasticsearch: {str(e)}", file=sys.stderr)
                                # Store failed records for retry
                                for record in batch:
                                    await self._queue.put(record)

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"Error in Elasticsearch worker: {str(e)}", file=sys.stderr)
                    await asyncio.sleep(1)  # Prevent tight loop on persistent errors

    def _serialize_record(self, record):
        """Serialize a record, handling MongoDB types."""
        try:
            # Prepare the document
            doc = {
                '@timestamp': datetime.datetime.utcnow().isoformat(),
                'host': self.hostname,
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'path': record.pathname,
                'function': record.funcName,
                'line_number': record.lineno,
                'process': {
                    'id': record.process,
                    'name': record.processName
                },
                'thread': {
                    'id': record.thread,
                    'name': record.threadName
                }
            }
            
            # Add exception info if present
            if record.exc_info:
                doc['exception'] = {
                    'type': str(record.exc_info[0].__name__),
                    'message': str(record.exc_info[1]),
                    'traceback': self.formatter.formatException(record.exc_info)
                }
            
            # Add extra fields if present
            if hasattr(record, 'event_type'):
                doc['event_type'] = record.event_type
            if hasattr(record, 'data'):
                doc['data'] = record.data
            
            return doc
        except Exception as e:
            print(f"Error serializing record: {str(e)}", file=sys.stderr)
            return None

    def emit(self, record):
        """Put log record into the async queue."""
        if not self._initialized:
            warnings.warn("Elasticsearch handler not initialized", RuntimeWarning)
            return
            
        try:
            doc = self._serialize_record(record)
            if doc is None:
                return

            # Get current thread ID
            thread_id = threading.get_ident()
            
            # If we're in the main thread, we can use the event loop directly
            if thread_id == threading.main_thread().ident and self._main_loop:
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
            print(f"Error queueing log message: {str(e)}", file=sys.stderr)

    def _start_thread_worker(self, thread_id):
        """Start a worker for a specific thread."""
        if not self._initialized or not self._main_loop:
            return
            
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

    def close(self):
        """Synchronous close method that Python's logging system expects."""
        if not self._closed:
            self._closed = True
            self._initialized = False
            self._stop_event.set()
            
            # Close Elasticsearch client if it exists
            if self.es_client:
                self.es_client = None
            
            # Clear any remaining items in queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except:
                    break

    async def aclose(self):
        """Async close method for proper cleanup."""
        if self._closed or not self._initialized:
            return
            
        try:
            await self._async_close()
        except Exception as e:
            print(f"Error during handler close: {e}", file=sys.stderr)

    async def _async_close(self):
        """Gracefully shut down the handler."""
        if self._closed or not self._initialized:
            return
            
        self._closed = True
        self._stop_event.set()
        self._initialized = False  # Stop accepting new logs immediately
        
        try:
            # Cancel worker task first
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._worker_task = None
            
            # Clear any remaining items in queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            # Close Elasticsearch client
            if self.es_client:
                try:
                    await self.es_client.close()
                except Exception as e:
                    print(f"Error closing Elasticsearch client: {str(e)}", file=sys.stderr)
                finally:
                    self.es_client = None
            
            # Close HTTP session last
            if self._http_session:
                if not self._http_session.closed:
                    try:
                        await self._http_session.close()
                    except Exception as e:
                        print(f"Error closing HTTP session: {str(e)}", file=sys.stderr)
                self._http_session = None
                    
        except Exception as e:
            print(f"Error during async close: {str(e)}", file=sys.stderr)
        finally:
            self._closed = True
            self._initialized = False

    async def _process_queue(self):
        """Process items in the queue."""
        if not self.es_client:
            return
            
        batch = []
        while not self._queue.empty() and len(batch) < 100:
            try:
                record = self._queue.get_nowait()
                if record:  # Skip None records
                    batch.append(record)
            except asyncio.QueueEmpty:
                break

        if batch:
            actions = []
            index_name = self._get_index_name()
            for record in batch:
                # Add the action type in the metadata line
                actions.extend([
                    {'index': {'_index': index_name}},
                    record
                ])
            
            try:
                await self._bulk_index(actions)
            except Exception as e:
                print(f"Error bulk indexing documents: {str(e)}", file=sys.stderr)

    def _get_index_name(self) -> str:
        """Generate index name with date suffix."""
        return f"{self.index_prefix}-{datetime.datetime.now().strftime('%Y.%m.%d')}"

    def __del__(self):
        """Ensure resources are cleaned up."""
        if not self._closed:
            self.close()  # Use synchronous close in __del__

# Patch the close method in logging.Handler to handle coroutines
original_handler_close = logging.Handler.close

def patched_handler_close(self):
    """Patched close method that properly handles coroutines."""
    if hasattr(self, 'close') and asyncio.iscoroutinefunction(self.close):
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # If no loop exists or it's closed, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                loop.create_task(self.close())
            else:
                try:
                    loop.run_until_complete(self.close())
                finally:
                    if loop != asyncio.get_event_loop():
                        loop.close()
        except Exception:
            # If all else fails, just ignore the coroutine
            pass
    else:
        original_handler_close(self)

logging.Handler.close = patched_handler_close 
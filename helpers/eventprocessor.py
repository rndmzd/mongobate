import logging
from typing import Any, Dict
from collections.abc import Callable

# Create a base event processor class
class BaseEventProcessor:
    """Base class for processing events with dynamic method dispatch.
    
    This class provides a template method pattern for processing events. It dynamically
    dispatches events to methods named 'process_<event_method>' based on the event's
    method field.
    """
    
    def process_event(self, event: Dict[str, Any]) -> bool:
        """Process an event using dynamic method dispatch.
        
        Args:
            event: A dictionary containing event data with at least a 'method' key
                  and optionally an 'object' key with the event payload.
        
        Returns:
            bool: True if the event was processed successfully, False otherwise.
        """
        try:
            event_method = event.get("method")
            if not event_method:
                logging.warning("No event method found")
                return False
                
            processor_name = f"process_{event_method.lower()}"
            processor = getattr(self, processor_name, None)
            
            if not isinstance(processor, Callable):
                logging.warning(f"No valid processor found for method: {event_method}")
                return False
                
            return processor(event.get("object", {}))
            
        except Exception as error:
            logging.exception("Error processing event", exc_info=error)
            return False 

# Create a base event processor class
class BaseEventProcessor:
    def process_event(self, event: dict) -> bool:
        """Template method for processing events"""
        try:
            event_method = event.get("method")
            if not event_method:
                logger.warning("No event method found")
                return False
                
            processor = getattr(self, f"process_{event_method.lower()}", None)
            if not processor:
                logger.warning(f"No processor found for method: {event_method}")
                return False
                
            return processor(event.get("object", {}))
            
        except Exception as e:
            logger.exception("Error processing event", exc_info=e)
            return False 
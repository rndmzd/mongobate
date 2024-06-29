import logging
import simplejson as json

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


class CBEvents:
    def __init__(self):
        pass

    def process_event(self, event):
        try:
            logger.info(json.dumps(event, sort_keys=True, indent=4))

            event_method = event["method"]
            logger.debug(f"event_method: {event_method}")
            event_object = event["object"]
            logger.debug(f"event_object: {event_object}")

            if event_method == "tip":
                process_result = self.tip(event_object)
            elif event_method == "follow":
                process_result = self.follow(event_object)
            elif event_method == "unfollow":
                process_result = self.unfollow(event_object)
            elif event_method == "media_purchase":
                process_result = self.media_purchase(event_object)
            elif event_method == "chat_message":
                process_result = self.chat_message(event_object)
            elif event_method == "broadcast":
                process_result = self.broadcast(event_object)
            else:
                logger.warning(f"Unknown event method: {event_method}")
                process_result = False

        except Exception as e:
            logger.exception("Error processing event", exc_info=e)
            process_result = False
        
        return process_result

    def tip(self):
        try:
            logger.info("Tip event received.")
            # Process tip event
        except Exception as e:
            logger.exception("Error processing tip event", exc_info=e)
            return False
        return True
    
    def follow(self):
        try:
            logger.info("Follow event received.")
            # Process follow event
        except Exception as e:
            logger.exception("Error processing follow event", exc_info=e)
            return False
        return True

    def unfollow(self):
        try:
            logger.info("Unfollow event received.")
            # Process unfollow event
        except Exception as e:
            logger.exception("Error processing unfollow event", exc_info=e)
            return False
        return True

    def media_purchase(self):
        try:
            logger.info("Media purchase event received.")
            # Process media purchase event
        except Exception as e:
            logger.exception("Error processing media purchase event", exc_info=e)
            return False
        return True

    def chat_message(self):
        try:
            logger.info("Chat message event received.")
            # Process chat message event
        except Exception as e:
            logger.exception("Error processing chat message event", exc_info=e)
            return False
        return True
    
    def broadcast(self):
        try:
            logger.info("Broadcast event received.")
            # Process broadcast event
        except Exception as e:
            logger.exception("Error processing broadcast event", exc_info=e)
            return False
        return True
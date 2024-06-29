from bson import ObjectId
import logging
import simplejson as json

from eventhandler import Actions

logger = logging.getLogger('mongobate.eventhandler.cbevents')
logger.setLevel(logging.DEBUG)


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


class CBEvents:
    def __init__(self):
        self.actions = Actions()

    def process_event(self, event):
        try:
            print(json.dumps(event, sort_keys=True, indent=4, cls=MongoJSONEncoder))

            event_method = event["method"]
            logger.debug(f"event_method: {event_method}")
            event_object = event["object"]
            logger.debug(f"event_object: {event_object}")

            if event_method == "tip":
                process_result = self.tip(event_object)
            elif event_method == "broadcastStart":
                process_result = self.broadcast_start(event_object)
            elif event_method == "broadcastStop":
                process_result = self.broadcast_stop(event_object)
            elif event_method == "fanclubJoin":
                process_result = self.fanclub_join(event_object)
            elif  event_method == "privateMessage":
                process_result = self.private_message(event_object)
            elif event_method == "roomSubjectChange":
                process_result = self.room_subject_change(event_object)
            elif event_method == "userEnter":
                process_result = self.user_enter(event_object)
            elif event_method == "userLeave":
                process_result = self.user_leave(event_object)
            elif event_method == "follow":
                process_result = self.follow(event_object)
            elif event_method == "unfollow":
                process_result = self.unfollow(event_object)
            elif event_method == "media_purchase":
                process_result = self.media_purchase(event_object)
            elif event_method == "chat_message":
                process_result = self.chat_message(event_object)
            else:
                logger.warning(f"Unknown event method: {event_method}")
                process_result = False

        except Exception as e:
            logger.exception("Error processing event", exc_info=e)
            process_result = False
        
        return process_result

    def tip(self, event):
        """
        {
            "broadcaster": "testuser",
            "tip": {
                "tokens": 25,
                "isAnon": false,
                "message": ""
            },
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "f",
                "hasTokens": true,
                "recentTips": "some",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Tip event received.")
            # Process tip event
        except Exception as e:
            logger.exception("Error processing tip event", exc_info=e)
            return False
        return True
    
    def broadcast_start(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Broadcast start event received.")
            # Process broadcast start event
        except Exception as e:
            logger.exception("Error processing broadcast start event", exc_info=e)
            return False
        return True
    
    def broadcast_stop(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Broadcast stop event received.")
            # Process broadcast stop event
        except Exception as e:
            logger.exception("Error processing broadcast stop event", exc_info=e)
            return False
        return True
    
    def fanclub_join(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": true,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Fanclub join event received.")
            # Process fanclub join event
        except Exception as e:
            logger.exception("Error processing fanclub join event", exc_info=e)
            return False
        return True
    
    def private_message(self, event):
        """
        {
            "message": {
                "color": "",
                "toUser": "testuser",
                "bgColor": null,
                "fromUser": "testuser1",
                "message": "hello",
                "font": "default",
            },
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Private message event received.")
            # Process private message event
        except Exception as e:
            logger.exception("Error processing private message event", exc_info=e)
            return False
        return True
    
    def room_subject_change(self, event):
        """
        {
            "broadcaster": "testuser",
            "subject": "Testuser's room"
        }
        """
        try:
            logger.info("Room subject change event received.")
            # Process room subject change event
        except Exception as e:
            logger.exception("Error processing room subject change event", exc_info=e)
            return False
        return True
    
    def user_enter(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("User enter event received.")
            # Process user enter event
        except Exception as e:
            logger.exception("Error processing user enter event", exc_info=e)
            return False
        return True
    
    def user_leave(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("User leave event received.")
            # Process user leave event
        except Exception as e:
            logger.exception("Error processing user leave event", exc_info=e)
            return False
        return True
    
    def follow(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Follow event received.")
            # Process follow event
        except Exception as e:
            logger.exception("Error processing follow event", exc_info=e)
            return False
        return True

    def unfollow(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Unfollow event received.")
            # Process unfollow event
        except Exception as e:
            logger.exception("Error processing unfollow event", exc_info=e)
            return False
        return True

    def media_purchase(self, event):
        """
        {
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            },
            "media": {
                "id": 1,
                "name": "photoset1",
                "type": "photos",
                "tokens": 25
            }
        }
        """
        try:
            logger.info("Media purchase event received.")
            # Process media purchase event
        except Exception as e:
            logger.exception("Error processing media purchase event", exc_info=e)
            return False
        return True

    def chat_message(self, event):
        """
        {
            "message": {
                "color": "#494949",
                "bgColor": null,
                "message": "hello",
                "font": "default",
            },
            "broadcaster": "testuser",
            "user": {
                "username": "testuser1",
                "inFanclub": false,
                "gender": "m",
                "hasTokens": true,
                "recentTips": "none",
                "isMod": false
            }
        }
        """
        try:
            logger.info("Chat message event received.")
            # Process chat message event
        except Exception as e:
            logger.exception("Error processing chat message event", exc_info=e)
            return False
        return True
    
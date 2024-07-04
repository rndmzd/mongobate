import configparser
import datetime
from bson import ObjectId
import logging
import simplejson as json
import time

from utils import MongoJSONEncoder

logger = logging.getLogger('mongobate.helpers.cbevents')
logger.setLevel(logging.DEBUG)

config = configparser.RawConfigParser()
config.read("config.ini")


class CBEvents:
    def __init__(self):
        from . import Actions, Checks

        self.actions = Actions()
        self.checks = Checks()

        self.active_components = self.checks.get_active_components()
        logger.info(f"Active Components: {self.active_components}")

        self.vip_cooldown_seconds = config.getint("General", "vip_audio_cooldown_hours") * 60 * 60
        logger.debug(f"self.vip_cooldown_seconds: {self.vip_cooldown_seconds}")

        self.vip_cooldown = {}
        # self.vip_users = {}
        self.vip_audio_directory = config.get("General", "vip_audio_directory")

    def process_event(self, event, vip_users, audio_player):
        try:
            print(json.dumps(event, sort_keys=True, indent=4, cls=MongoJSONEncoder))

            event_method = event["method"]
            logger.debug(f"event_method: {event_method}")
            event_object = event["object"]
            logger.debug(f"event_object: {event_object}")

            # self.vip_users = vip_users
            # logger.debug(f"self.vip_users: {self.vip_users}")

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
                process_result = self.user_enter(event_object, vip_users, audio_player)
            elif event_method == "userLeave":
                process_result = self.user_leave(event_object)
            elif event_method == "follow":
                process_result = self.follow(event_object)
            elif event_method == "unfollow":
                process_result = self.unfollow(event_object)
            elif event_method == "mediaPurchase":
                process_result = self.media_purchase(event_object)
            elif event_method == "chatMessage":
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
            # Process tip event
            logger.info("Tip event received.")
            
            ## Chat Auto DJ ##
            if 'chat_auto_dj' in self.active_components:
                logger.info("Checking if song request.")
                if not self.checks.is_song_request(event["tip"]["tokens"]):
                    return False
                logger.info("Song request detected.")
                request_count = self.checks.get_request_count(event["tip"]["tokens"])
                logger.info(f"Request count: {request_count}")
                song_extracts = self.actions.extract_song_titles(event["tip"]["message"], request_count)
                logger.debug(f'song_extracts:  {song_extracts}')
                for song_info in song_extracts:
                    song_uri = self.actions.find_song_spotify(song_info)
                    logger.debug(f'song_uri: {song_uri}')
                    if song_uri:
                        if not self.actions.available_in_market(song_uri):
                            logger.warning(f"Song not available in user market: {song_info}")
                            continue
                        add_queue_result = self.actions.add_song_to_queue(song_uri)
                        logger.debug(f'add_queue_result: {add_queue_result}')
                        if not add_queue_result:
                            logger.error(f"Failed to add song to queue: {song_info}")
                        else:
                            logger.info(f"Song added to queue: {song_info}")

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
    
    def user_enter(self, event, vip_users, audio_player):
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
            # Process user enter event
            logger.info("User enter event received.")

            if 'vip_audio' in self.active_components:
                username = event['user']['username']
                if username in vip_users.keys():
                    logger.info(f"VIP user {username} entered the room.")
                    current_time = time.time()
                    if username not in self.vip_cooldown or (current_time - self.vip_cooldown[username]) > self.vip_cooldown_seconds:
                        logger.info(f"VIP user {username} not in cooldown period. Playing user audio.")    
                        audio_file = vip_users[username]
                        logger.debug(f"audio_file: {audio_file}")
                        audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                        logger.debug(f"audio_file_path: {audio_file_path}")
                        logger.info(f"Playing VIP audio for user: {username}")
                        audio_player.play_audio(audio_file_path)
                        logger.info(f"VIP audio played for user: {username}. Resetting cooldown.")
                        self.vip_cooldown[username] = current_time
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
    
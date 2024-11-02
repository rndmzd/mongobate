import datetime
from bson import ObjectId
import logging
import simplejson as json
import threading
import time

from utils import MongoJSONEncoder

logger = logging.getLogger('mongobate.helpers.cbevents')
logger.setLevel(logging.DEBUG)


class CBEvents:
    def __init__(self):
        from . import Actions, Checks, Commands
        from . import config

        self.checks = Checks()

        self.active_components = self.checks.get_active_components()
        logger.info(f"Active Components: {self.active_components}")

        actions_args = {}
        if 'chat_auto_dj' in self.active_components:
            actions_args['chatdj'] = True
        if 'vip_audio' in self.active_components:
            actions_args['vip_audio'] = True
            self.vip_audio_cooldown_seconds = config.getint("General", "vip_audio_cooldown_hours") * 60 * 60
            logger.debug(f"self.vip_audio_cooldown_seconds: {self.vip_audio_cooldown_seconds}")
            self.vip_cooldown = {}
            self.vip_audio_directory = config.get("General", "vip_audio_directory")
        if 'command_parser' in self.active_components:
            actions_args['command_parser'] = True
            self.commands = Commands()
        if 'custom_actions' in self.active_components:
            actions_args['custom_actions'] = True
        if 'spray_bottle' in self.active_components:
            actions_args['spray_bottle'] = True

        self.actions = Actions(actions_args)

    def process_event(self, event, privileged_users, audio_player):
        try:
            print(json.dumps(event, sort_keys=True, indent=4, cls=MongoJSONEncoder))

            event_method = event["method"]
            logger.debug(f"event_method: {event_method}")
            event_object = event["object"]
            logger.debug(f"event_object: {event_object}")

            vip_users = privileged_users["vip"]
            admin_users = privileged_users["admin"]
            action_users = privileged_users["custom_actions"]

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
                process_result = self.chat_message(event_object, admin_users, action_users, audio_player)
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
                ## Perform checks for tip event items ##
                logger.info("Checking if skip song request.")
                if self.checks.is_skip_song_request(event["tip"]["tokens"]):
                    logger.info("Skip song request detected. Checking current playback state.")
                    if self.actions.get_playback_state():
                        logger.info("Playback active. Executing skip song.")
                        skip_song_result = self.actions.skip_song()
                        logger.debug(f'skip_song_result: {skip_song_result}')

                logger.info("Checking if song request.")
                if self.checks.is_song_request(event["tip"]["tokens"]):
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
            if 'spray_bottle' in self.active_components:
                logger.info("Checking if spray bottle tip.")
                if self.checks.is_spray_bottle_tip(event["tip"]["tokens"]):
                    logger.info("Spray bottle tip detected.")
                    spray_bottle_result = self.actions.trigger_spray()
                    logger.debug(f'spray_bottle_result: {spray_bottle_result}')
            return True
        except Exception as e:
            logger.exception("Error processing tip event", exc_info=e)
            return False
    
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
            # Process broadcast start event
            logger.info("Broadcast start event received.")
            return True
        except Exception as e:
            logger.exception("Error processing broadcast start event", exc_info=e)
            return False
    
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
            # Process broadcast stop event
            logger.info("Broadcast stop event received.")
            return True
        except Exception as e:
            logger.exception("Error processing broadcast stop event", exc_info=e)
            return False
    
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
            # Process fanclub join event
            logger.info("Fanclub join event received.")
            return True
        except Exception as e:
            logger.exception("Error processing fanclub join event", exc_info=e)
            return False
    
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
            # Process private message event
            logger.info("Private message event received.")
            return True
        except Exception as e:
            logger.exception("Error processing private message event", exc_info=e)
            return False
    
    def room_subject_change(self, event):
        """
        {
            "broadcaster": "testuser",
            "subject": "Testuser's room"
        }
        """
        try:
            # Process room subject change event
            logger.info("Room subject change event received.")
            return True
        except Exception as e:
            logger.exception("Error processing room subject change event", exc_info=e)
            return False
    
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
                    if username not in self.vip_cooldown or (current_time - self.vip_cooldown[username]) > self.vip_audio_cooldown_seconds:
                        logger.info(f"VIP user {username} not in cooldown period. Playing user audio.")    
                        audio_file = vip_users[username]
                        logger.debug(f"audio_file: {audio_file}")
                        audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                        logger.debug(f"audio_file_path: {audio_file_path}")
                        logger.info(f"Playing VIP audio for user: {username}")
                        audio_player.play_audio(audio_file_path)
                        logger.info(f"VIP audio played for user: {username}. Resetting cooldown.")
                        self.vip_cooldown[username] = current_time
            return True
        except Exception as e:
            logger.exception("Error processing user enter event", exc_info=e)
            return False
    
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
            # Process user leave event
            logger.info("User leave event received.")
            return True
        except Exception as e:
            logger.exception("Error processing user leave event", exc_info=e)
            return False
    
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
            # Process follow event
            logger.info("Follow event received.")
            return True
        except Exception as e:
            logger.exception("Error processing follow event", exc_info=e)
            return False

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
            # Process unfollow event
            logger.info("Unfollow event received.")
            return True
        except Exception as e:
            logger.exception("Error processing unfollow event", exc_info=e)
            return False

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
            # Process media purchase event
            logger.info("Media purchase event received.")
            return True
        except Exception as e:
            logger.exception("Error processing media purchase event", exc_info=e)
            return False

    def chat_message(self, event, admin_users, action_users, audio_player):
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
            # Process chat message event
            logger.info("Chat message event received.")

            if 'command_parser' in self.active_components:
                if event["user"]["username"] in admin_users:
                    logger.info(f"Admin message: {event['message']['message']}")
                    command = self.checks.get_command(event["message"]["message"])
                    if command:
                        logger.info("Trying command: {command}")
                        command_result = self.commands.try_command(command)
                        logger.debug(f"command_result: {command_result}")
            if 'custom_actions' in self.active_components:
                username = event['user']['username']
                if username in action_users.keys():
                    logger.info(f"Message from action user {username}.")
                    action_messages = action_users[username]
                    message = event['message']['message'].strip()
                    for action_message in action_messages.keys():
                        if action_message in message:
                            logger.info(f"Message matches action message for user {username}. Executing action.")
                            audio_file = action_messages[message]
                            logger.debug(f"audio_file: {audio_file}")
                            audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                            logger.debug(f"audio_file_path: {audio_file_path}")
                            logger.info(f"Playing custom action audio for user: {username}")
                            audio_player.play_audio(audio_file_path)
            return True
        except Exception as e:
            logger.exception("Error processing chat message event", exc_info=e)
            return False
    
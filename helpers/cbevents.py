import datetime
from bson import ObjectId
import simplejson as json
import threading
import time

from utils import MongoJSONEncoder
from chataudio.audioplayer import AudioPlayer
from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.helpers.cbevents')


class CBEvents:
    def __init__(self):
        from . import Actions, Checks, Commands
        from . import config

        self.checks = Checks()

        self.active_components = self.checks.get_active_components()
        logger.info("component.init", message="Initializing CBEvents", 
                   data={"active_components": self.active_components})

        actions_args = {}
        if 'chat_auto_dj' in self.active_components:
            actions_args['chatdj'] = True
        if 'vip_audio' in self.active_components:
            actions_args['vip_audio'] = True
            self.vip_audio_cooldown_seconds = config.getint("General", "vip_audio_cooldown_hours") * 60 * 60
            logger.debug("component.init", message="Setting VIP audio cooldown", 
                        data={"cooldown_seconds": self.vip_audio_cooldown_seconds})
            self.vip_cooldown = {}
            self.vip_audio_directory = config.get("General", "vip_audio_directory")
        if 'command_parser' in self.active_components:
            actions_args['command_parser'] = True
        if 'custom_actions' in self.active_components:
            actions_args['custom_actions'] = True
        if 'spray_bottle' in self.active_components:
            actions_args['spray_bottle'] = True
        if 'couch_buzzer' in self.active_components:
            actions_args['couch_buzzer'] = True
        if 'obs_integration' in self.active_components:
            actions_args['obs_integration'] = True
        if 'event_audio' in self.active_components:
            actions_args['event_audio'] = True
            self.fanclub_join_audio_path = config.get("EventAudio", "fanclub_join")

        self.actions = Actions(**actions_args)
        self.audio_player = AudioPlayer()
        self.commands = Commands(actions=self.actions)

    def process_event(self, event, privileged_users):
        try:
            event_method = event.get('method')
            event_object = event.get('object')
            
            if not event_method:
                logger.warning("event.process.error", message="No event method found")
                return False
                
            # Map event methods to handler methods
            method_map = {
                'chatMessage': lambda obj: self.chat_message(obj, privileged_users.get('admin_users', []), privileged_users.get('action_users', {})),
                'privateMessage': lambda obj: self.private_message(obj, privileged_users.get('admin_users', []), privileged_users.get('action_users', {})),
                'tip': lambda obj: self.tip(obj),
                'broadcastStart': lambda obj: self.broadcast_start(obj),
                'broadcastStop': lambda obj: self.broadcast_stop(obj),
                'fanclubJoin': lambda obj: self.fanclub_join(obj),
                'userEnter': lambda obj: self.user_enter(obj, privileged_users.get('vip_users', {})),
                'userLeave': lambda obj: self.user_leave(obj),
                'follow': lambda obj: self.follow(obj),
                'unfollow': lambda obj: self.unfollow(obj),
                'mediaPurchase': lambda obj: self.media_purchase(obj),
                'roomSubjectChange': lambda obj: self.room_subject_change(obj)
            }
            
            # Convert method name to handler method name
            handler = method_map.get(event_method)
            if not handler:
                logger.warning("event.process.error", 
                             message="No processor found for method",
                             data={"method": event_method})
                return False
                
            logger.debug("event.process", message="Processing event", 
                        data={
                            "method": event_method,
                            "object": event_object
                        })
                
            process_result = handler(event_object)
            return process_result
            
        except Exception as exc:
            logger.exception("event.process.error", exc=exc, 
                           message="Error processing event")
            return False

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
            logger.info("event.tip", message="Tip event received")
            
            # Extract tip amount once for all checks
            tip_amount = event.get('tip', {}).get('tokens', 0)
            
            if 'chat_auto_dj' in self.active_components:
                logger.info("event.tip.song", message="Checking if skip song request")
                
                if self.checks.is_skip_song_request(tip_amount):
                    logger.info("event.tip.song.skip", message="Skip song request detected")
                    
                    if self.actions.is_playback_active():
                        logger.info("event.tip.song.skip", message="Executing skip song")
                        skip_song_result = self.actions.skip_song()
                        logger.debug("event.tip.song.skip", data={"result": skip_song_result})
                
                logger.info("event.tip.song", message="Checking if song request")
                
                if self.checks.is_song_request(tip_amount):
                    logger.info("event.tip.song.request", message="Song request detected")
                    
                    request_count = self.checks.get_request_count(tip_amount)
                    logger.info("event.tip.song.request", 
                              message="Processing song request",
                              data={"request_count": request_count})
                    
                    song_extracts = self.actions.extract_song_titles(event.get('tip', {}).get('message', ''), request_count)
                    logger.debug("event.tip.song.request", data={"song_extracts": song_extracts})
                    
                    song_uri = self.actions.find_song_spotify(song_extracts[0] if song_extracts else None)
                    logger.debug("event.tip.song.request", data={"song_uri": song_uri})
                    
                    if not self.actions.available_in_market(song_uri):
                        logger.warning("event.tip.song.error", 
                                     message="Song not available in user market",
                                     data={"song_info": song_extracts})
                        return True
                    
                    # Get requester name from the event
                    requester_name = event.get('user', {}).get('username', 'Anonymous')
                    # Get song details from the first extracted song
                    song_details = f"{song_extracts[0]['artist']} - {song_extracts[0]['song']}" if song_extracts else "Unknown Song"
                    
                    add_queue_result = self.actions.add_song_to_queue(song_uri, requester_name, song_details)
                    logger.debug("event.tip.song.queue", data={"result": add_queue_result})
                    
                    if not add_queue_result:
                        logger.error("event.tip.song.error",
                                   message="Failed to add song to queue",
                                   data={"song_info": song_extracts})
                    else:
                        logger.info("event.tip.song.queue",
                                  message="Song added to queue",
                                  data={"song_info": song_extracts})
            
            if 'spray_bottle' in self.active_components:
                logger.info("event.tip.spray", message="Checking if spray bottle tip")
                
                if self.checks.is_spray_bottle_tip(tip_amount):
                    logger.info("event.tip.spray", message="Spray bottle tip detected")
                    spray_bottle_result = self.actions.trigger_spray_bottle()
                    logger.debug("event.tip.spray", data={"result": spray_bottle_result})
            
            return True
            
        except Exception as exc:
            logger.exception("event.tip.error", exc=exc,
                           message="Error processing tip event")
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
            logger.info("event.broadcast.start", message="Broadcast start event received")
            return True
        except Exception as exc:
            logger.exception("event.broadcast.error", exc=exc,
                           message="Error processing broadcast start event")
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
            logger.info("event.broadcast.stop", message="Broadcast stop event received")
            return True
        except Exception as exc:
            logger.exception("event.broadcast.error", exc=exc,
                           message="Error processing broadcast stop event")
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
            logger.info("event.fanclub.join", message="Fanclub join event received")
            if 'event_audio' in self.active_components:
                self.audio_player.play_audio(self.fanclub_join_audio_path)
            return True
        except Exception as exc:
            logger.exception("event.fanclub.error", exc=exc,
                           message="Error processing fanclub join event")
            return False
    
    def private_message(self, event, admin_users, action_users):
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
            
            if 'command_parser' in self.active_components:
                if event["user"]["username"] in admin_users:
                    logger.info("event.chat.admin", 
                              message="Admin message received",
                              data={
                                  "username": event["user"]["username"],
                                  "message": event['message']['message']
                              })
                    command = self.checks.get_command(event["message"]["message"])
                    if command:
                        logger.info("event.command.process", 
                                  message="Processing admin command",
                                  data={"command": command})
                        command_result = self.commands.try_command(command)
                        logger.debug("event.command.result",
                                   data={"result": command_result})

            if 'custom_actions' in self.active_components:
                username = event['user']['username']
                if username in action_users.keys():
                    logger.info("event.chat.action", 
                              message="Action user message received",
                              data={"username": username})
                    logger.info(f"Message from action user {username}.")
                    action_messages = action_users[username]
                    message = event['message']['message'].strip()
                    for action_message in action_messages.keys():
                        if action_message in message:
                            logger.info("event.action.trigger",
                                      message="Action message matched",
                                      data={"username": username})
                            logger.info(f"Message matches action message for user {username}. Executing action.")
                            audio_file = action_messages[message]
                            logger.debug("event.action.audio",
                                       data={"audio_file": audio_file})
                            audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                            logger.debug("event.action.audio",
                                       data={"audio_file_path": audio_file_path})
                            logger.info("event.action.audio.play",
                                      message="Playing action audio",
                                      data={
                                          "username": username,
                                          "audio_file": audio_file
                                      })
                            self.audio_player.play_audio(audio_file_path)
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
    
    def user_enter(self, event, vip_users):
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
            logger.info("event.user.enter", message="User enter event received")
            
            if 'vip_audio' in self.active_components:
                username = event['user']['username']
                
                if username in vip_users:
                    logger.info("event.user.enter.vip", 
                              message="VIP user entered",
                              data={"username": username})
                    
                    current_time = time.time()
                    last_entry = self.vip_cooldown.get(username, 0)
                    
                    if current_time - last_entry > self.vip_audio_cooldown_seconds:
                        logger.info("event.user.enter.vip.audio",
                                  message="Playing VIP audio",
                                  data={"username": username})
                        
                        audio_file = vip_users[username]
                        logger.debug("event.user.enter.vip.audio",
                                   data={"audio_file": audio_file})
                        
                        audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                        logger.debug("event.user.enter.vip.audio",
                                   data={"audio_file_path": audio_file_path})
                        
                        self.audio_player.play_audio(audio_file_path)
                        logger.info("event.user.enter.vip.audio",
                                  message="VIP audio played, resetting cooldown",
                                  data={"username": username})
                        
                        self.vip_cooldown[username] = current_time
            
            return True
            
        except Exception as exc:
            logger.exception("event.user.enter.error", exc=exc,
                           message="Error processing user enter event")
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
            logger.info("event.user.leave", message="User leave event received")
            return True
        except Exception as exc:
            logger.exception("event.user.leave.error", exc=exc,
                           message="Error processing user leave event")
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
            logger.info("event.follow", message="Follow event received")
            return True
        except Exception as exc:
            logger.exception("event.follow.error", exc=exc,
                           message="Error processing follow event")
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
            logger.info("event.unfollow", message="Unfollow event received")
            return True
        except Exception as exc:
            logger.exception("event.unfollow.error", exc=exc,
                           message="Error processing unfollow event")
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
            logger.info("event.media.purchase", message="Media purchase event received")
            return True
        except Exception as exc:
            logger.exception("event.media.purchase.error", exc=exc,
                           message="Error processing media purchase event")
            return False

    def chat_message(self, event, admin_users, action_users):
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
            logger.info("event.chat.message", message="Chat message event received")
            username = event['user']['username']
            
            if username in admin_users:
                logger.info("event.chat.admin", 
                          message="Admin message received",
                          data={
                              "username": username,
                              "message": event['message']['message']
                          })
                
                # Process admin commands
                command = self.checks.get_command(event['message']['message'])
                if command:
                    logger.info("event.command.process", 
                              message="Processing admin command",
                              data={"command": command})
                    command_result = self.commands.try_command(command)
                    logger.debug("event.command.result",
                               data={"result": command_result})
            
            elif username in action_users.keys():
                logger.info("event.chat.action", 
                          message="Action user message received",
                          data={"username": username})
                
                # Process action user messages
                if self._matches_action_message(event['message']['message'], username):
                    logger.info("event.action.trigger",
                              message="Action message matched",
                              data={"username": username})
                    
                    audio_file = action_users[username]
                    logger.debug("event.action.audio",
                               data={"audio_file": audio_file})
                    
                    audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                    logger.debug("event.action.audio",
                               data={"audio_file_path": audio_file_path})
                    
                    logger.info("event.action.audio.play",
                              message="Playing action audio",
                              data={
                                  "username": username,
                                  "audio_file": audio_file
                              })
                    self.audio_player.play_audio(audio_file_path)
            
            return True
        except Exception as e:
            logger.exception("Error processing chat message event", exc_info=e)
            return False

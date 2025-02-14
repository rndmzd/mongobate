import time

from chataudio.audioplayer import AudioPlayer
from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.helpers.cbevents')


class CBEvents:
    def __init__(self):
        from . import Actions, Checks, Commands, config

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
                'chatMessage': lambda obj: self.chat_message(obj, privileged_users.get('admin', []), privileged_users.get('custom_actions', {})),
                'privateMessage': lambda obj: self.private_message(obj, privileged_users.get('admin', []), privileged_users.get('custom_actions', {})),
                'tip': lambda obj: self.tip(obj),
                'broadcastStart': lambda obj: self.broadcast_start(obj),
                'broadcastStop': lambda obj: self.broadcast_stop(obj),
                'fanclubJoin': lambda obj: self.fanclub_join(obj),
                'userEnter': lambda obj: self.user_enter(obj, privileged_users.get('vip', {})),
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

            logger.debug("event.process.start",
                        message="Processing event",
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
            logger.info("event.tip.received",
                       message="Tip event received",
                       data={
                           "broadcaster": event.get("broadcaster"),
                           "tokens": event.get("tip", {}).get("tokens"),
                           "username": event.get("user", {}).get("username"),
                           "is_anon": event.get("tip", {}).get("isAnon", False)
                       })

            # Extract tip amount once for all checks
            tip_amount = event.get('tip', {}).get('tokens', 0)
            logger.debug("event.tip.amount",
                         message="Tip amount",
                         data={"tip_amount": tip_amount})
            tip_message = event.get('tip', {}).get('message', '').strip()
            logger.debug("event.tip.message",
                         message="Tip message",
                         data={"tip_message": tip_message})


            if 'chat_auto_dj' in self.active_components:
                logger.debug("event.tip.song.check",
                           message="Checking song-related tip actions",
                           data={
                               "tip_amount": tip_amount,
                               "message": tip_message
                           })

                if self.checks.is_skip_song_request(tip_amount):
                    logger.info("event.tip.song.skip.detected",
                              message="Skip song request detected",
                              data={"tip_amount": tip_amount})

                    if self.actions.is_playback_active():
                        logger.info("event.tip.song.skip.execute",
                                  message="Executing skip song request")
                        skip_song_result = self.actions.skip_song()
                        logger.debug("event.tip.song.skip.result",
                                   message="Skip song execution complete",
                                   data={"success": skip_song_result})

                logger.debug("event.tip.song.request.check",
                           message="Checking for song request")
                if self.checks.is_song_request(tip_amount):
                    # Validate message length
                    if len(tip_message) < 3:
                        logger.warning("event.tip.song.request.short",
                                     message="Message short and will be padded for song request",
                                     data={
                                         "message": tip_message,
                                         "length": len(tip_message)
                                     })
                        padded_message = f"The song name is \"{tip_message}\". I don't know the artist."
                        logger.info("event.tip.song.request.padded",
                                   message="Message padded for song request",
                                   data={
                                       "original_message": tip_message,
                                       "padded_message": padded_message
                                   })
                        tip_message = padded_message                    

                    logger.info("event.tip.song.request.detected",
                              message="Song request detected",
                              data={
                                  "tip_amount": tip_amount,
                                  "message": tip_message
                              })

                    request_count = self.checks.get_request_count(tip_amount)
                    logger.debug("event.tip.song.request.count",
                               message="Determined request count",
                               data={"count": request_count})

                    song_extracts = self.actions.extract_song_titles(
                        tip_message,
                        request_count
                    )

                    if not song_extracts:
                        logger.warning("event.tip.song.request.empty",
                                     message="No songs could be extracted from message",
                                     data={
                                         "message": tip_message,
                                         "tip_amount": tip_amount
                                     })
                        return True

                    logger.debug("event.tip.song.request.extracts",
                               message="Extracted song information",
                               data={"extracts": [s.dict() for s in song_extracts]})

                    songs_processed = 0
                    for song_info in song_extracts:
                        logger.debug("event.tip.song.request.process",
                                   message="Processing song request",
                                   data={"song_info": str(song_info)})

                        if song_info.spotify_uri:
                            song_uri = song_info.spotify_uri
                            logger.debug("event.tip.song.request.uri.existing",
                                       message="Using existing Spotify URI",
                                       data={"uri": song_uri})
                        else:
                            song_uri = self.actions.find_song_spotify(song_info)
                            logger.debug("event.tip.song.request.uri.search",
                                       message="Searched for Spotify URI",
                                       data={
                                           "song_info": str(song_info),
                                           "found_uri": song_uri
                                       })

                        if not song_uri:
                            logger.warning("event.tip.song.request.notfound",
                                         message="Could not find song on Spotify",
                                         data={"song_info": str(song_info)})
                            continue

                        if not self.actions.available_in_market(song_uri):
                            logger.warning("event.tip.song.request.market",
                                        message="Song not available in market",
                                        data={
                                            "song_info": str(song_info),
                                            "uri": song_uri
                                        })
                            continue

                        song_details = f"{song_info.artist} - {song_info.song}"
                        logger.debug("event.tip.song.request.queue.attempt",
                                   message="Attempting to add song to queue",
                                   data={
                                       "song_details": song_details,
                                       "uri": song_uri,
                                       "username": event["user"]["username"]
                                   })

                        add_queue_result = self.actions.add_song_to_queue(
                            song_uri,
                            event["user"]["username"],
                            song_details
                        )

                        if add_queue_result:
                            songs_processed += 1
                            logger.info("event.tip.song.request.queue.success",
                                      message="Successfully added song to queue",
                                      data={
                                          "song_details": song_details,
                                          "uri": song_uri,
                                          "username": event["user"]["username"]
                                      })
                        else:
                            logger.error("event.tip.song.request.queue.failed",
                                       message="Failed to add song to queue",
                                       data={
                                           "song_info": str(song_info),
                                           "uri": song_uri
                                       })

                    if songs_processed == 0:
                        logger.warning("event.tip.song.request.allfailed",
                                     message="Failed to process any songs from request",
                                     data={
                                         "message": tip_message,
                                         "tip_amount": tip_amount,
                                         "requested_count": request_count
                                     })

            if 'spray_bottle' in self.active_components:
                logger.debug("event.tip.spray.check",
                           message="Checking for spray bottle tip",
                           data={"tip_amount": tip_amount})

                if self.checks.is_spray_bottle_tip(tip_amount):
                    logger.info("event.tip.spray.detected",
                              message="Spray bottle tip detected",
                              data={"tip_amount": tip_amount})

                    spray_bottle_result = self.actions.trigger_spray_bottle()
                    logger.debug("event.tip.spray.result",
                               message="Spray bottle trigger complete",
                               data={"success": spray_bottle_result})

            return True

        except Exception as exc:
            logger.exception("event.tip.error",
                           message="Error processing tip event",
                           exc=exc,
                           data={
                               "event": event,
                               "error_type": type(exc).__name__
                           })
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
                    logger.info("event.chat.action.message",
                              message="Received message from action user",
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
            logger.exception("event.message.private.error",
                            message="Error processing private message event",
                            exc=e)
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
            logger.info("event.room.subject.change",
                        message="Room subject change event received")
            return True
        except Exception as e:
            logger.exception("event.room.subject.error",
                            message="Error processing room subject change event",
                            exc=e)
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
                    last_vip_audio_play = self.actions.get_last_vip_audio_play(username)
                    if not last_vip_audio_play or (current_time - last_vip_audio_play) > self.vip_audio_cooldown_seconds:
                        logger.info("event.user.vip.audio.play",
                                    message="VIP user not in cooldown, playing audio",
                                    data={"username": username})
                        audio_file = vip_users[username]
                        logger.debug("event.user.enter.vip.audio",
                                   data={"audio_file": audio_file})

                        audio_file_path = f"{self.vip_audio_directory}/{audio_file}"
                        logger.debug("event.user.enter.vip.audio",
                                   data={"audio_file_path": audio_file_path})

                        self.audio_player.play_audio(audio_file_path)
                        logger.info("event.user.vip.audio.played",
                                    message="VIP audio played and cooldown reset",
                                    data={"username": username})
                        if not self.actions.set_last_vip_audio_play(username, current_time):
                            logger.error("event.user.vip.audio.cooldown.error",
                                        message="Failed to set VIP audio cooldown time",
                                        data={"username": username})
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

            if username in admin_users['admin_users']:
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

            if 'custom_actions' in self.active_components:
                username = event['user']['username']
                if username in action_users.keys():
                    logger.info("event.chat.action.message",
                              message="Received message from action user",
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
            logger.exception("event.chat.message.error",
                            message="Error processing chat message event",
                            exc=e)
            return False

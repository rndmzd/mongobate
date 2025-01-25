import logging
from chataudio.audioplayer import AudioPlayer
from .config import config
from .actions import Actions
from .checks import Checks
from .commands import Commands

logger = logging.getLogger('mongobate.helpers.cbevents')

class CBEvents:
    def __init__(self, active_checks=None):
        """Initialize CBEvents."""
        self.active_checks = active_checks or []
        self.actions = Actions()
        self.checks = Checks()
        self.commands = Commands()
        self.audio_player = AudioPlayer()
        self.tip_threshold = config.get('settings', 'tip_threshold', fallback=100)
        self.tip_audio_path = config.get('settings', 'tip_audio_path', fallback=None)
        self.fanclub_join_audio_path = config.get('settings', 'fanclub_join_audio_path', fallback=None)

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

    def process_event(self, event):
        """Process an event."""
        try:
            process_result = False
            if event['type'] == 'tip':
                process_result = self.process_tip(event)
            elif event['type'] == 'broadcastStart':
                process_result = self.process_broadcast_start(event)
            elif event['type'] == 'broadcastStop':
                process_result = self.process_broadcast_stop(event)
            elif event['type'] == 'fanclubJoin':
                process_result = self.process_fanclub_join(event)
            elif event['type'] == 'follow':
                process_result = self.process_follow(event)
            elif event['type'] == 'unfollow':
                process_result = self.process_unfollow(event)
            elif event['type'] == 'mediaPurchase':
                process_result = self.process_media_purchase(event)
            elif event['type'] == 'message':
                process_result = self.process_message(event)
            elif event['type'] == 'privateMessage':
                process_result = self.process_private_message(event)
            elif event['type'] == 'roomSubject':
                process_result = self.process_room_subject(event)
            elif event['type'] == 'roomEnter':
                process_result = self.process_room_enter(event)
            elif event['type'] == 'roomLeave':
                process_result = self.process_room_leave(event)
            elif event['type'] == 'userUpdate':
                process_result = self.process_user_update(event)
            return process_result
        except Exception as error:
            logger.exception("Error processing event", exc_info=error)
            return False

    def process_tip(self, event):
        """Process tip event."""
        try:
            logger.info("Tip event received.")
            if event['amount'] >= self.tip_threshold:
                if self.tip_audio_path:
                    self.audio_player.play_audio(self.tip_audio_path)
            return True
        except Exception as error:
            logger.exception("Error processing tip event", exc_info=error)
            return False

    def process_broadcast_start(self, _event):
        """Process broadcast start event."""
        try:
            logger.info("Broadcast start event received.")
            return True
        except Exception as error:
            logger.exception("Error processing broadcast start event", exc_info=error)
            return False

    def process_broadcast_stop(self, _event):
        """Process broadcast stop event."""
        try:
            logger.info("Broadcast stop event received.")
            return True
        except Exception as error:
            logger.exception("Error processing broadcast stop event", exc_info=error)
            return False

    def process_fanclub_join(self, _event):
        """Process fanclub join event."""
        try:
            logger.info("Fanclub join event received.")
            if self.fanclub_join_audio_path:
                self.audio_player.play_audio(self.fanclub_join_audio_path)
            return True
        except Exception as error:
            logger.exception("Error processing fanclub join event", exc_info=error)
            return False

    def process_follow(self, _event):
        """Process follow event."""
        try:
            logger.info("Follow event received.")
            return True
        except Exception as error:
            logger.exception("Error processing follow event", exc_info=error)
            return False

    def process_unfollow(self, _event):
        """Process unfollow event."""
        try:
            logger.info("Unfollow event received.")
            return True
        except Exception as error:
            logger.exception("Error processing unfollow event", exc_info=error)
            return False

    def process_media_purchase(self, _event):
        """Process media purchase event."""
        try:
            logger.info("Media purchase event received.")
            return True
        except Exception as error:
            logger.exception("Error processing media purchase event", exc_info=error)
            return False

    def process_message(self, event):
        """Process message event."""
        try:
            logger.info("Message event received.")
            if event['type'] == 'message':
                self.process_chat_message(event)
            elif event['type'] == 'privateMessage':
                self.process_private_message(event)
            return True
        except Exception as error:
            logger.exception("Error processing message event", exc_info=error)
            return False

    def process_chat_message(self, event):
        """Process chat message event."""
        try:
            logger.info("Chat message event received.")
            if event['message'].startswith('!'):
                audio_file_path = self.commands.try_command(event)
                if audio_file_path:
                    self.audio_player.play_audio(audio_file_path)
            return True
        except Exception as error:
            logger.exception("Error processing chat message event", exc_info=error)
            return False

    def process_private_message(self, event):
        """Process private message event."""
        try:
            logger.info("Private message event received.")
            if event['message'].startswith('!'):
                audio_file_path = self.commands.try_command(event)
                if audio_file_path:
                    self.audio_player.play_audio(audio_file_path)
            return True
        except Exception as error:
            logger.exception("Error processing private message event", exc_info=error)
            return False

    def process_room_subject(self, _event):
        """Process room subject event."""
        try:
            logger.info("Room subject change event received.")
            return True
        except Exception as error:
            logger.exception("Error processing room subject change event", exc_info=error)
            return False

    def process_room_enter(self, _event):
        """Process room enter event."""
        try:
            logger.info("User enter event received.")
            return True
        except Exception as error:
            logger.exception("Error processing user enter event", exc_info=error)
            return False

    def process_room_leave(self, _event):
        """Process room leave event."""
        try:
            logger.info("User leave event received.")
            return True
        except Exception as error:
            logger.exception("Error processing user leave event", exc_info=error)
            return False

    def process_user_update(self, _event):
        """Process user update event."""
        try:
            logger.info("User update event received.")
            return True
        except Exception as error:
            logger.exception("Error processing user update event", exc_info=error)
            return False

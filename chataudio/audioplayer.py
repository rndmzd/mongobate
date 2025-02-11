import sys
from threading import Event, Thread

import pygame
import pygame._sdl2.audio as sdl2_audio

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.chataudio.audioplayer')

class AudioPlayer:
    def __init__(self, device_name=None):
        pygame.mixer.init()
        self.device_name = device_name
        self.current_device = None
        if not self.device_name:
            self.device_name = self.user_select_audio_device()
        device_select_result = self.set_output_device(self.device_name)
        logger.debug("audio.device.select",
                    message="Device selection result",
                    data={"success": device_select_result})
        self.play_thread = None
        self.stop_event = Event()

    def get_output_devices(self, capture_devices=False):
        init_by_me = not pygame.mixer.get_init()
        if init_by_me:
            pygame.mixer.init()
        devices = tuple(sdl2_audio.get_audio_device_names(capture_devices))
        logger.debug("audio.devices.list",
                    message="Retrieved available audio devices",
                    data={"devices": devices})
        if init_by_me:
            pygame.mixer.quit()
        return devices

    def user_select_audio_device(self):
        pygame.mixer.init()
        pygame.mixer.quit()
        pygame.mixer.init(44100, -16, 2, 1024)
        output_devices = self.get_output_devices()
        print("Available audio devices:\n")
        for i in range(len(output_devices)):
            device_name = output_devices[i]
            print(f"{i+1} => {device_name}")
        try:
            user_selection = int(input(f"\nSelect an audio device (1-{len(output_devices)}): "))
        except KeyboardInterrupt:
            logger.info("audio.device.abort",
                       message="User aborted device selection")
            sys.exit()

        logger.debug("audio.device.select",
                    message="User selected audio device",
                    data={
                        "selection": user_selection,
                        "device_index": user_selection - 1
                    })
        device_num = user_selection - 1
        return output_devices[device_num]

    def set_output_device(self, device_name):
        output_devices = self.get_output_devices()
        for i in range(len(output_devices)):
            if output_devices[i] == device_name:
                pygame.mixer.quit()
                pygame.mixer.init(devicename=device_name)
                self.current_device = device_name
                logger.info("audio.device.set",
                          message="Set output device",
                          data={"device": device_name})
                return True

        logger.warning("audio.device.error",
                      message="Device not found, using default",
                      data={"requested_device": device_name})
        return False

    def play_audio(self, file_path):
        if self.play_thread and self.play_thread.is_alive():
            logger.warning("audio.playback.busy",
                         message="Audio is already playing, stopping current playback")
            self.stop_playback()

        self.stop_event.clear()
        self.play_thread = Thread(target=self._play_audio_thread, args=(file_path,))
        self.play_thread.start()

        logger.info("audio.playback.start",
                   message="Started audio playback",
                   data={"file": file_path})

    def _play_audio_thread(self, file_path):
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                pygame.time.Clock().tick(10)
        except Exception as exc:
            logger.exception("audio.playback.error",
                           exc=exc,
                           message="Failed to play audio file",
                           data={"file": file_path})
        finally:
            pygame.mixer.music.stop()
            logger.debug("audio.playback.stop",
                        message="Stopped audio playback",
                        data={"file": file_path})

    def stop_playback(self):
        self.stop_event.set()
        if self.play_thread:
            self.play_thread.join()
        pygame.mixer.music.stop()
        logger.info("audio.playback.stop",
                   message="Manually stopped audio playback")

    def cleanup(self):
        self.stop_playback()
        pygame.mixer.quit()
        logger.info("audio.cleanup",
                   message="Audio player cleaned up")

import logging
from threading import Thread, Event

import pygame
import pygame._sdl2.audio as sdl2_audio

logger = logging.getLogger('mongobate.chataudio.audioplayer')
logger.setLevel(logging.DEBUG)

class AudioPlayer:
    def __init__(self, device_name=None):
        pygame.mixer.init()
        self.device_name = device_name
        self.current_device = None
        if not self.device_name:
            self.device_name = self.user_select_audio_device()
        device_select_result = self.set_output_device(self.device_name)
        logger.debug(f"device_select_result: {device_select_result}")
        self.play_thread = None
        self.stop_event = Event()
    
    def get_output_devices(self, capture_devices=False):
        init_by_me = not pygame.mixer.get_init()
        if init_by_me:
            pygame.mixer.init()
        devices = tuple(sdl2_audio.get_audio_device_names(capture_devices))
        logger.debug(f"devices: {devices}")
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
        user_selection = int(input(f"\nSelect an audio device (1-{len(output_devices)}): ")) # or press Enter to use the default device: ")
        logger.debug(f"user_selection: {user_selection}")
        device_num = user_selection - 1
        logger.debug(f"device_num: {device_num}")
        return output_devices[device_num]

    def set_output_device(self, device_name):
        output_devices = self.get_output_devices()
        for i in range(len(output_devices)):
            if output_devices[i] == device_name:
                pygame.mixer.quit()
                pygame.mixer.init(devicename=device_name)
                self.current_device = device_name
                logger.info(f"Set output device to: {device_name}")
                return True
        logger.warning(f"Device '{device_name}' not found. Using default device.")
        return False

    def play_audio(self, file_path):
        if self.play_thread and self.play_thread.is_alive():
            logger.warning("Audio is already playing. Stopping current playback.")
            self.stop_playback()
        
        self.stop_event.clear()
        self.play_thread = Thread(target=self._play_audio_thread, args=(file_path,))
        self.play_thread.start()

    def _play_audio_thread(self, file_path):
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                pygame.time.Clock().tick(10)
        except Exception as e:
            logger.exception(f"Error playing audio file: {file_path}", exc_info=e)
        finally:
            pygame.mixer.music.stop()

    def stop_playback(self):
        self.stop_event.set()
        if self.play_thread:
            self.play_thread.join()
        pygame.mixer.music.stop()

    def cleanup(self):
        self.stop_playback()
        pygame.mixer.quit()
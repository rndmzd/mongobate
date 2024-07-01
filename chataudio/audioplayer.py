import pygame
import logging
from threading import Thread, Event

logger = logging.getLogger('mongobate.chataudio.audioplayer')
logger.setLevel(logging.DEBUG)

class AudioPlayer:
    def __init__(self, device_name):
        pygame.mixer.init()
        self.device_name = device_name
        self.current_device = None
        self.set_output_device(device_name)
        self.play_thread = None
        self.stop_event = Event()

    def set_output_device(self, device_name):
        devices = pygame.mixer.get_init()
        for i in range(pygame.mixer.get_num_devices()):
            if pygame.mixer.get_device_name(i) == device_name:
                pygame.mixer.quit()
                pygame.mixer.init(devicename=device_name)
                self.current_device = device_name
                logger.info(f"Set output device to: {device_name}")
                return
        logger.warning(f"Device '{device_name}' not found. Using default device.")

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
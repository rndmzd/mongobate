import logging
import os
import queue
import threading
import time
import pygame

logger = logging.getLogger('mongobate.chataudio.audioplayer')

class AudioPlayer:
    def __init__(self):
        """Initialize the audio player."""
        self.audio_queue = queue.Queue()
        self._stop_event = threading.Event()
        self.audio_thread = None
        self.current_audio = None
        self.audio_files = []
        self.audio_channels = []
        self.max_channels = 8

        pygame.mixer.init()
        pygame.mixer.set_num_channels(self.max_channels)
        for i in range(self.max_channels):
            self.audio_channels.append(pygame.mixer.Channel(i))

    def play_audio(self, audio_file_path):
        """Add an audio file to the queue."""
        if not os.path.exists(audio_file_path):
            logger.error(f"Audio file not found: {audio_file_path}")
            return False

        try:
            # Check if audio file is already loaded
            for i, audio in enumerate(self.audio_files):
                if audio['path'] == audio_file_path:
                    logger.debug(f"Audio file already loaded: {audio_file_path}")
                    self.audio_queue.put(audio['sound'])
                    return True

            # Load new audio file
            sound = pygame.mixer.Sound(audio_file_path)
            self.audio_files.append({'path': audio_file_path, 'sound': sound})
            self.audio_queue.put(sound)
            return True
        except Exception as error:
            logger.exception(f"Error loading audio file: {error}")
            return False

    def play_queued_audio(self):
        """Play audio files from the queue."""
        while not self._stop_event.is_set():
            try:
                # Check for available channel
                for i, channel in enumerate(self.audio_channels):
                    if not channel.get_busy():
                        sound = self.audio_queue.get_nowait()
                        channel.play(sound)
                        self.audio_queue.task_done()
                        break
                time.sleep(0.1)
            except queue.Empty:
                time.sleep(0.1)
            except Exception as error:
                logger.exception(f"Error playing audio: {error}")
                time.sleep(0.1)

    def start(self):
        """Start the audio player thread."""
        if not self.audio_thread or not self.audio_thread.is_alive():
            self._stop_event.clear()
            self.audio_thread = threading.Thread(target=self.play_queued_audio, daemon=True)
            self.audio_thread.start()

    def stop(self):
        """Stop the audio player thread."""
        self._stop_event.set()
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join()
        pygame.mixer.quit()

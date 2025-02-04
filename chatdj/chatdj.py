from typing import List, Dict, Optional
import sys
import time

import openai
from spotipy import Spotify, SpotifyOAuth, SpotifyException

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.chatdj')

class SongExtractor:
    def __init__(self, api_key):
        self.openai_client = openai.OpenAI(api_key=api_key)

    def extract_songs(self, message, song_count=1):
        """Use OpenAI GPT-4 to extract song titles from the message."""
        try:
            response = self.openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a music bot that can extract song titles from messages."
                    },
                    {
                        "role": "user",
                        "content": f"Extract exactly {song_count} song title{'s' if song_count > 1 else ''} from the following message: '{message}'. Respond with the artist and song title for each result with one per line."
                    }
                ],
                model="gpt-4"
            )

            logger.debug("song.extract.response", 
                        message="Received response from OpenAI",
                        data={"response": response})

            song_titles = []
            song_titles_response = response.choices[0].message.content.strip().split('\n')
            
            for idx, resp in enumerate(song_titles_response):
                if ' - ' in resp:
                    artist, song = resp.split(' - ', 1)
                    song_titles.append({
                        "artist": artist.strip(),
                        "song": song.strip(),
                        "gpt": True
                    })
                else:
                    logger.warning("song.extract.format", 
                                 message="Unexpected format in response",
                                 data={"response": resp})
                    
                    if song_count == 1:
                        logger.warning("song.extract.fallback",
                                     message="Using original message as song title")
                        song_titles.append({
                            "artist": "",
                            "song": message,
                            "gpt": False
                        })

            logger.debug("song.extract.result",
                        message="Extracted song titles",
                        data={
                            "titles": song_titles,
                            "count": len(song_titles)
                        })

            return song_titles

        except openai.APIError as exc:
            logger.exception("song.extract.error", exc=exc,
                           message="Failed to extract song titles")
            return []


class AutoDJ:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-read-private",
            open_browser=False
        )
        
        logger.info("spotify.init", message="Initializing Spotify client")
        self.spotify = Spotify(auth_manager=self.sp_oauth)
        
        logger.info("spotify.device", message="Selecting playback device")
        self.playback_device = self._select_playback_device()
        
        logger.debug("spotify.playback", message="Initializing playback state")
        self.playing_first_track = False
        self.queued_tracks = []
        self.clear_playback_context()

    def _select_playback_device(self) -> str:
        try:
            devices = self.spotify.devices()['devices']
            logger.debug("spotify.devices", 
                        message="Retrieved available devices",
                        data={"devices": devices})

            if not devices:
                logger.error("spotify.devices.error",
                           message="No Spotify devices found")
                raise ValueError("No available Spotify devices found.")

            print("\n==[ Available Spotify Devices ]==\n")
            for idx, device in enumerate(devices):
                print(f"{idx+1} - {device['name']}")

            while True:
                try:
                    selection = int(input("\nChoose playback device number: "))
                    device = devices[selection - 1]
                    logger.info("spotify.device.selected",
                              message="Device selected",
                              data={
                                  "name": device['name'],
                                  "id": device['id']
                              })
                    return device['id']
                except KeyboardInterrupt:
                    logger.info("spotify.device.cancel",
                              message="User cancelled device selection")
                    raise
                except (ValueError, IndexError):
                    logger.error("spotify.device.error",
                               message="Invalid device selection")
                    print("Invalid selection. Please try again.")
                    sys.exit()

        except Exception as exc:
            logger.exception("spotify.device.error", exc=exc,
                           message="Failed to select playback device")
            raise

    def find_song(self, song_info):
        """Search Spotify for a specific song."""
        try:
            query = f"{song_info['artist']} {song_info['song']}"
            logger.debug("spotify.search",
                        message="Searching for song",
                        data={"query": query})
            
            results = self.spotify.search(q=query, type='track')
            logger.debug("spotify.search.result",
                        data={"results": results})
            return results
            
        except SpotifyException as exc:
            logger.exception("spotify.search.error", exc=exc,
                           message="Failed to find song")
            return None

    def add_song_to_queue(self, track_uri: str) -> bool:
        try:
            logger.debug("spotify.queue.add",
                        message="Adding track to queue",
                        data={"track_uri": track_uri})
            
            self.queued_tracks.append(track_uri)

            if not self.playback_active() and len(self.queued_tracks) == 1:
                logger.info("spotify.playback.start",
                          message="Starting playback of first track")
                self.playing_first_track = True

            logger.debug("spotify.queue.status",
                        data={"queued_tracks": self.queued_tracks})
            return True

        except SpotifyException as exc:
            logger.exception("spotify.queue.error", exc=exc,
                           message="Failed to add song to queue")
            return False

    def check_queue_status(self) -> bool:
        try:
            if not self.playback_active():
                if len(self.queued_tracks) > 0:
                    logger.info("spotify.queue.resume",
                              message="Resuming playback from queue")
                    
                    track = self.queued_tracks.pop(0)
                    logger.debug("spotify.playback.track",
                               data={"track": track})
                    
                    self.spotify.start_playback(
                        device_id=self.playback_device,
                        uris=[track]
                    )
                    
                    self.playing_first_track = False
                    return True
                
                return False
            
            if self.queued_tracks:
                current_track = self.spotify.current_playback()['item']['uri']
                logger.debug("spotify.playback.status",
                           data={
                               "current_track": current_track,
                               "next_in_queue": self.queued_tracks[0]
                           })
                
                if current_track == self.queued_tracks[0]:
                    logger.info("spotify.playback.track",
                              message="Now playing queued track",
                              data={"track": current_track})
                    self.queued_tracks.pop(0)
                    
            return True
            
        except Exception as exc:
            logger.exception("spotify.queue.error", exc=exc,
                           message="Failed to check queue status")
            return False

    def clear_playback_context(self):
        try:
            logger.info("spotify.playback.clear",
                       message="Clearing playback context")
            self.spotify.pause_playback(device_id=self.playback_device)
            self.queued_tracks = []
            self.playing_first_track = False
            return True
            
        except SpotifyException as exc:
            logger.exception("spotify.playback.error", exc=exc,
                           message="Failed to clear playback context")
            return False

    def get_user_market(self):
        try:
            user_info = self.spotify.me()
            logger.debug("spotify.user.market",
                        data={"user_info": user_info})
            return user_info.get('country')
            
        except SpotifyException as exc:
            logger.exception("spotify.user.error", exc=exc,
                           message="Failed to get user market")
            return None

    def get_song_markets(self, track_uri):
        try:
            track_info = self.spotify.track(track_uri)
            logger.debug("spotify.track.markets",
                        data={"track_info": track_info})
            return track_info.get('available_markets', [])
            
        except SpotifyException as exc:
            logger.exception("spotify.track.error", exc=exc,
                           message="Failed to get track markets")
            return []

    def playback_active(self) -> bool:
        try:
            playback = self.spotify.current_playback()
            if playback and playback['is_playing']:
                logger.debug("spotify.playback.active",
                           message="Playback is active")
                return True
                
            logger.info("spotify.playback.inactive",
                       message="Playback is not active")
            return False
            
        except SpotifyException as exc:
            logger.exception("spotify.playback.error", exc=exc,
                           message="Failed to check playback status")
            return False

    def skip_song(self):
        try:
            logger.info("spotify.playback.skip",
                       message="Skipping current track")
            self.spotify.next_track(device_id=self.playback_device)
            return True
            
        except SpotifyException as exc:
            logger.exception("spotify.playback.error", exc=exc,
                           message="Failed to skip track")
            return False

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from pprint import pprint

    load_dotenv()

    song_extractor = SongExtractor(os.getenv('OPENAI_API_KEY'))
    auto_dj = AutoDJ(
        os.getenv('SPOTIFY_CLIENT_ID'),
        os.getenv('SPOTIFY_CLIENT_SECRET'),
        os.getenv('SPOTIFY_REDIRECT_URI')
    )

    queue = auto_dj.spotify.queue()
    print()
    #pprint(queue)
    #print()
    #pprint(queue['currently_playing'])
    #print()
    #pprint(queue['queue'])
    print()
    print(len(queue['queue']))
    [print(i['name']) for i in queue['queue']]

    auto_dj.clear_playback_context()

    queue = auto_dj.spotify.queue()
    print()
    #pprint(queue)
    #print()
    #pprint(queue['currently_playing'])
    #print()
    #pprint(queue['queue'])
    print()
    print(len(queue['queue']))
    [print(i['name']) for i in queue['queue']]
    
    # sys.exit()

    # Example usage
    message = "Play Dancing Queen by ABBA and Bohemian Rhapsody by Queen"
    songs = song_extractor.extract_songs(message, song_count=2)

    for song in songs:
        if track_uri := auto_dj.find_song(song)['tracks']['items'][0]['uri']:
            if auto_dj.get_user_market() in auto_dj.get_song_markets(track_uri):
                auto_dj.add_song_to_queue(track_uri)
            else:
                logger.warning("Song not available in user's market. Skipping.")

    # Main loop to check queue status
    try:
        while True:
            if not auto_dj.check_queue_status():
                break
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Exit signal received. Stopping playback.")
        auto_dj.clear_playback_context()

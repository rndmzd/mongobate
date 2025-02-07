from typing import List, Dict, Optional
import logging
from typing import List, Optional
import sys
import time
import json
import re

import openai
from pydantic import BaseModel
from spotipy import Spotify, SpotifyException

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.chatdj')


class SongRequest(BaseModel):
    """Pydantic model for structured song request output.
    The spotify_uri is optional so it can be filled in later."""
    artist: str
    song: str
    spotify_uri: Optional[str] = None

class SongExtractor:
    """SongExtractor using Chat Completions API to extract song/artist pairs."""
    def __init__(self, api_key: str, spotify_client: Optional[Spotify] = None):
        self.openai_client = openai.OpenAI(api_key=api_key)
        self.spotify_client = spotify_client

    def extract_songs(self, message: str, song_count: int = 1) -> List[SongRequest]:
        """
        Extract song requests from the provided message.
        
        If the message contains a properly formatted Spotify URI and a spotify_client is provided,
        this method retrieves the track's song name and primary artist via the Spotify API and returns
        a list of SongRequest objects containing 'song', 'artist', and 'spotify_uri'.
        
        Otherwise, it falls back to using the Chat Completions API to extract exactly song_count song
        request(s) (with only 'song' and 'artist' keys) from the message.
        """
        # Check if the message contains any Spotify track URIs.
        spotify_uri_pattern = r"(spotify:track:[a-zA-Z0-9]+|https?://open\.spotify\.com/track/[a-zA-Z0-9]+)"
        found_uris = re.findall(spotify_uri_pattern, message)
        if found_uris and self.spotify_client:
            # Remove duplicates and limit the number to song_count.
            unique_uris = list(dict.fromkeys(found_uris))[:song_count]
            songs = []
            for uri in unique_uris:

                try:
                    track_info = self.spotify_client.track(uri)
                    song_name = track_info.get('name', '')
                    # Assume the first listed artist is the primary artist.
                    artist_name = track_info.get('artists', [{}])[0].get('name', '')

                    songs.append(SongRequest(song=song_name, artist=artist_name, spotify_uri=uri))
                except Exception as e:
                    logger.exception(f"Error retrieving track info for URI {uri}: {e}")
            if songs:
                return songs

        # If no valid Spotify URI is found, fall back to Chat Completions API extraction.
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a music bot that processes song requests. "
                    "Extract exactly {} song request(s) from the following message. "
                    "Return a JSON array of objects with exactly two keys: 'song' and 'artist'. "
                    "If the user does not specify an artist, make a guess based on the song name. "
                    "Do not include any additional commentary."
                ).format(song_count)
            },
            {
                "role": "user",
                "content": f"Extract exactly {song_count} song request(s) from the following message: '{message}'"
            }
        ]
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # or use gpt-3.5-turbo if desired
                messages=messages,
                temperature=0
            )
            content = response.choices[0].message.content.strip()
            # Remove markdown code fences if present.
            if content.startswith("```"):
                lines = content.splitlines()
                lines = [line for line in lines if not line.strip().startswith("```")]
                content = "\n".join(lines).strip()
            data = json.loads(content)
            songs = [SongRequest(**item) for item in data]
            logger.debug(f"Extracted songs using Chat API: {songs}")
            return songs
        except Exception as e:
            logger.exception("Failed to extract song requests via Chat API.", exc_info=e)
            return []

class AutoDJ:
    """AutoDJ class using Spotify APIs.
    The search_track_uri method applies filtering to only return tracks available in the US market,
    avoids live versions, and returns the most popular match for an exact artist match."""
    def __init__(self, spotify: Spotify):
        self.spotify = spotify
        logger.debug("Prompting user for playback device selection.")
        self.playback_device = self._select_playback_device()
        
        logger.debug("spotify.playback", message="Initializing playback state")
        self.playing_first_track = False

        self.queued_tracks = []
        self.clear_playback_context()
        self._print_variables()

    def _print_variables(self, return_value=None):
        """Stub function for logging internal state."""
        pass

    def _select_playback_device(self) -> str:
        try:
            devices = self.spotify.devices()['devices']
            logger.debug(f"Available devices: {devices}")
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
        except Exception as e:
            logger.exception("Failed to select playback device", exc_info=e)
            raise

    def search_track_uri(self, song: str, artist: str) -> Optional[str]:
        """
        Searches Spotify for a track using the given song and artist names.
        The query is restricted to the US market. Tracks that do not contain an
        exact match for the artist are ignored, and tracks with 'live' in their
        name are filtered out whenever possible. The most popular matching track is returned.
        """
        try:
            query = f"track:{song} artist:{artist}"
            logger.debug(f"Searching Spotify with query: {query}")
            results = self.spotify.search(q=query, type='track', market="US", limit=50)
            tracks = results.get('tracks', {}).get('items', [])
            filtered_tracks = []
            for track in tracks:
                track_name = track.get('name', '')
                track_artists = [a.get('name', '').strip().lower() for a in track.get('artists', [])]
                if artist.strip().lower() not in track_artists:
                    continue
                if "live" in track_name.lower():
                    continue
                filtered_tracks.append(track)
            # Fallback: if filtering removed all candidates, try again without filtering "live".
            if not filtered_tracks and tracks:
                for track in tracks:
                    track_artists = [a.get('name', '').strip().lower() for a in track.get('artists', [])]
                    if artist.strip().lower() in track_artists:
                        filtered_tracks.append(track)
            if not filtered_tracks:
                logger.warning(f"No matching track found for {artist} - {song}")
                return None
            best_track = max(filtered_tracks, key=lambda x: x.get('popularity', 0))
            return best_track.get('uri')
        except SpotifyException as e:
            logger.exception("Failed to search for track", exc_info=e)
            return None

    def add_song_to_queue(self, track_uri: str, silent=False) -> bool:
        try:
            if not silent:
                logger.debug("spotify.queue.add",
                            message="Adding track to queue",
                            data={"track_uri": track_uri})
            
            self.queued_tracks.append(track_uri)
            # Start playback if not already active.
            if not self.playback_active() and len(self.queued_tracks) == 1:
                self.playing_first_track = True
            logger.debug(f"Current queued tracks: {self.queued_tracks}")
            self._print_variables(True)
            return True
        except SpotifyException as e:
            logger.exception("Failed to add song to queue", exc_info=e)
            return False

    def check_queue_status(self, silent=False) -> bool:
        try:
            if not self.playback_active():
                if len(self.queued_tracks) > 0:
                    logger.info("Queue populated but playback is not active. Starting playback.")
                    popped_track = self.queued_tracks.pop(0)
                    logger.debug(f"Popped track: {popped_track}")
                    self.spotify.start_playback(device_id=self.playback_device, uris=[popped_track])
                    logger.debug("Clearing playing_first_track flag.")
                    self.playing_first_track = False
                    return True
                self._print_variables(False)
                return False

            if self.queued_tracks:
                current_track = self.spotify.current_playback()['item']['uri']
                logger.debug(f"Current playing track: {current_track}")
                if current_track == self.queued_tracks[0]:
                    logger.info(f"Now playing queued track: {current_track}")
                    self.queued_tracks.pop(0)
            self._print_variables(True)
            return True
        except SpotifyException as e:
            logger.exception("Failed to check queue status", exc_info=e)
            return False

    def clear_playback_context(self) -> bool:
        try:
            logger.info("Clearing playback context.")
            if self.playback_active():
                self.spotify.pause_playback(device_id=self.playback_device)
            previous_track = None
            attempts = 0
            max_attempts = 5
            while True:
                queue = self.spotify.queue()
                if len(queue['queue']) == 0:
                    print("Queue is now empty")
                    break
                current_track = queue['queue'][0]['uri']
                if current_track == previous_track:
                    attempts += 1
                    if attempts >= max_attempts:
                        print("Unable to clear the last track. Stopping.")
                        break
                else:
                    attempts = 0
                try:
                    self.spotify.next_track()
                    print(f"Skipped track: {queue['queue'][0]['name']}")
                    time.sleep(1)
                except SpotifyException as e:
                    logger.error(f"Error skipping track: {e}")
                    break
                previous_track = current_track
            try:
                self.spotify.pause_playback()
                logger.info("Playback paused.")
            except SpotifyException as e:
                logger.error(f"Error pausing playback: {e}")
            self.playing_first_track = False
            self.queued_tracks.clear()
            self._print_variables(True)
            return True
        except SpotifyException as e:
            logger.exception("Failed to clear playback context.", exc_info=e)
            return False

    def get_user_market(self) -> Optional[str]:
        try:
            user_info = self.spotify.me()
            logger.debug("spotify.user.info",
                        message="Retrieved user market information",
                        data={"user_info": user_info})
            return user_info['country']
        except SpotifyException as exc:
            logger.exception("spotify.user.error",
                           message="Failed to get user market",
                           exc=exc)
            return None

    def get_song_markets(self, track_uri: str) -> List[str]:
        try:
            track_info = self.spotify.track(track_uri)
            logger.debug("spotify.track.info",
                        message="Retrieved track market information",
                        data={
                            "track_uri": track_uri,
                            "track_info": track_info
                        })
            return track_info.get('available_markets', []) or []
        except SpotifyException as exc:
            logger.exception("spotify.track.error",
                           message="Failed to get song markets",
                           exc=exc,
                           data={"track_uri": track_uri})
            return []

    def playback_active(self) -> bool:
        try:
            playback_state = self.spotify.current_playback()
            if playback_state and playback_state.get('is_playing'):
                logger.debug("spotify.playback.status",
                           message="Playback is active",
                           data={"is_playing": True})
                return True
            return False
        except SpotifyException as exc:
            logger.exception("spotify.playback.error",
                           message="Error checking playback state",
                           exc=exc)
            return False

    def skip_song(self, silent=False) -> bool:
        try:
            if not silent:
                logger.info("spotify.playback.skip",
                           message="Skipping current track",
                           data={
                               "device_id": self.playback_device
                           })
            self.spotify.next_track(device_id=self.playback_device)
            return True
            
        except SpotifyException as exc:
            if not silent:
                logger.exception("spotify.playback.error",
                               message="Failed to skip track",
                               exc=exc,
                               data={
                                   "device_id": self.playback_device
                               })
            return False
        
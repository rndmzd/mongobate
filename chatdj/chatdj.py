import json
import re
import time
from typing import List, Optional

import openai
import requests
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
    """
    Extracts song and artist information from a message.

    If a Spotify URI is found and a spotify_client is provided, it uses the Spotify API.
    Otherwise, it uses the ChatGPT completions API to extract song requests.
    If an extracted song request has no artist, it uses a hybrid approach (Google Custom Search + ChatGPT)
    to look up the artist name.
    """
    def __init__(
        self,
        openai_api_key: str,
        spotify_client: Optional[object] = None,
        google_api_key: Optional[str] = None,
        google_cx: Optional[str] = None
    ):
        # Set up the OpenAI API key.
        openai.api_key = openai_api_key
        self.spotify_client = spotify_client
        self.google_api_key = google_api_key
        self.google_cx = google_cx

    def extract_songs(self, message: str, song_count: int = 1) -> List[SongRequest]:
        try:
            logger.debug("song.extract.start",
                        message="Starting song extraction",
                        data={
                            "message": message,
                            "requested_count": song_count
                        })
            # Look for Spotify track URIs
            spotify_uri_pattern = r"(spotify:track:[a-zA-Z0-9]+|https?://open\.spotify\.com/track/[a-zA-Z0-9]+)"
            found_uris = re.findall(spotify_uri_pattern, message)
            logger.debug("song.extract.spotify.uris",
                        message="Found Spotify URIs in message",
                        data={
                            "found_uris": found_uris,
                            "uri_count": len(found_uris)
                        })

            songs = []
            if found_uris and self.spotify_client:
                unique_uris = list(dict.fromkeys(found_uris))[:song_count]
                logger.debug("song.extract.spotify.process",
                           message="Processing Spotify URIs",
                           data={
                               "unique_uris": unique_uris,
                               "processing_count": len(unique_uris)
                           })
                for uri in unique_uris:
                    try:
                        track_info = self.spotify_client.track(uri)
                        song_name = track_info.get('name', '')
                        artist_name = track_info.get('artists', [{}])[0].get('name', '')
                        logger.debug("song.extract.spotify.track",
                                   message="Retrieved track information",
                                   data={
                                       "uri": uri,
                                       "song": song_name,
                                       "artist": artist_name,
                                       "track_info": track_info
                                   })
                        songs.append(SongRequest(song=song_name, artist=artist_name, spotify_uri=uri))
                    except Exception as exc:
                        logger.exception("spotify.track.error",
                                       message="Error retrieving track info",
                                       exc=exc,
                                       data={
                                           "uri": uri,
                                           "error_type": type(exc).__name__
                                       })
                if songs:
                    logger.debug("song.extract.spotify.complete",
                               message="Completed Spotify URI extraction",
                               data={"extracted_songs": [s.dict() for s in songs]})
                    return songs

            # Fallback to ChatGPT
            logger.debug("song.extract.chat.start",
                        message="Starting ChatGPT extraction",
                        data={"message": message})
            messages_payload = [
                {
                    "role": "system",
                    "content": (
                        "You are a music bot that processes song requests. "
                        "Extract exactly {} song request(s) from the following message. "
                        "Return a JSON array of objects with exactly two keys: 'song' and 'artist'. "
                        "If you can identify a song name but no artist is specified, include the song "
                        "with an empty artist field. Treat single terms or phrases as potential song "
                        "titles if they could be song names. For example, 'mucka blucka' would be "
                        "extracted as {{'song': 'Mucka Blucka', 'artist': ''}}."
                    ).format(song_count)
                },
                {
                    "role": "user",
                    "content": f"Extract exactly {song_count} song request(s) from the following message: '{message}'"
                }
            ]
            try:
                logger.debug("song.extract.chat.request",
                           message="Sending request to ChatGPT",
                           data={"messages": messages_payload})
                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_payload,
                    temperature=0
                )
                content = response.choices[0].message.content.strip()
                logger.debug("song.extract.chat.response",
                           message="Received ChatGPT response",
                           data={"raw_content": content})

                # Remove markdown code fences if present
                if content.startswith("```"):
                    lines = content.splitlines()
                    lines = [line for line in lines if not line.strip().startswith("```")]
                    content = "\n".join(lines).strip()
                    logger.debug("song.extract.chat.clean",
                               message="Cleaned markdown from response",
                               data={"cleaned_content": content})

                data = json.loads(content)
                songs = [SongRequest(**item) for item in data]
                logger.debug("song.extract.chat.success",
                           message="Successfully parsed ChatGPT response",
                           data={"parsed_songs": [s.dict() for s in songs]})
            except Exception as exc:
                logger.exception("song.extract.chat.error",
                               message="Failed to extract songs via ChatGPT",
                               exc=exc,
                               data={
                                   "message": message,
                                   "error_type": type(exc).__name__
                               })
                return []

            # Artist lookup for missing artists
            for song_request in songs:
                if not song_request.artist.strip():
                    logger.debug("song.extract.artist.lookup",
                               message="Looking up missing artist",
                               data={"song": song_request.song})
                    found_artist = self.lookup_artist_hybrid(song_request.song)
                    song_request.artist = found_artist if found_artist else "Unknown Artist"
                    logger.debug("song.extract.artist.result",
                               message="Artist lookup complete",
                               data={
                                   "song": song_request.song,
                                   "found_artist": song_request.artist
                               })

            logger.debug("song.extract.complete",
                        message="Song extraction complete",
                        data={"final_songs": [s.dict() for s in songs]})
            return songs
        except Exception as exc:
            logger.exception("song.extract.error",
                           message="Failed to extract songs",
                           exc=exc,
                           data={
                               "message": message,
                               "error_type": type(exc).__name__
                           })
            return []

    def lookup_artist_hybrid(self, song_name: str) -> str:
        """
        Hybrid approach: first uses Google Custom Search to fetch a snippet,
        then uses ChatGPT to confirm the artist.
        """
        logger.debug("artist.lookup.start",
                    message="Starting hybrid artist lookup",
                    data={"song": song_name})

        snippet = self.lookup_artist_by_song_via_google(song_name)
        if snippet:
            logger.debug("artist.lookup.google.success",
                        message="Found Google search snippet",
                        data={
                            "song": song_name,
                            "snippet": snippet
                        })
            artist = self.lookup_artist_with_chat(song_name, snippet)
            if artist:
                logger.debug("artist.lookup.chat.success",
                           message="Successfully extracted artist from snippet",
                           data={
                               "song": song_name,
                               "artist": artist,
                               "snippet": snippet
                           })
                return artist
            else:
                logger.warning("artist.lookup.chat.failed",
                             message="Failed to extract artist from snippet",
                             data={
                                 "song": song_name,
                                 "snippet": snippet
                             })
        else:
            logger.warning("artist.lookup.google.failed",
                         message="No Google search results found",
                         data={"song": song_name})
        return ""

    def lookup_artist_by_song_via_google(self, song_name: str) -> str:
        """
        Uses the Google Custom Search API to fetch a snippet regarding the song.
        """
        if not self.google_api_key or not self.google_cx:
            logger.error("artist.lookup.google.config",
                        message="Google API key or custom search engine ID (CX) not provided")
            return ""

        query = f"Who is the song '{song_name}' by?"
        endpoint = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.google_api_key,
            "cx": self.google_cx,
            "q": query,
        }

        logger.debug("artist.lookup.google.request",
                    message="Sending Google search request",
                    data={
                        "song": song_name,
                        "query": query
                    })

        try:
            response = requests.get(endpoint, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            # Use the first item's snippet if available.
            if "items" in data and data["items"]:
                snippet = data["items"][0].get("snippet", "")
                logger.debug("artist.lookup.google.response",
                           message="Received Google search response",
                           data={
                               "song": song_name,
                               "snippet": snippet,
                               "total_results": len(data["items"])
                           })
                return snippet

            logger.warning("artist.lookup.google.empty",
                         message="No search results found",
                         data={"song": song_name})
            return ""

        except Exception as exc:
            logger.exception("artist.lookup.google.error",
                           message="Error during Google search",
                           exc=exc,
                           data={
                               "song": song_name,
                               "error_type": type(exc).__name__
                           })
            return ""

    def lookup_artist_with_chat(self, song_name: str, snippet: str) -> str:
        """
        Uses the ChatGPT completions API with the search snippet to confirm the artist.
        """
        messages_payload = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant specialized in music information. "
                    "Your task is to extract the artist name from the provided information. "
                    "Return ONLY the artist name, nothing else. If you cannot determine "
                    "the artist with certainty, return an empty string."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Based on the following information: '{snippet}', "
                    f"who is the artist for the song '{song_name}'? "
                    "Provide only the artist's name."
                )
            }
        ]

        logger.debug("artist.lookup.chat.request",
                    message="Sending artist extraction request to ChatGPT",
                    data={
                        "song": song_name,
                        "snippet": snippet
                    })

        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=messages_payload,
                temperature=0
            )
            content = response.choices[0].message.content.strip()

            # Assume the artist's name is on the first line.
            artist_name = content.splitlines()[0].strip()

            logger.debug("artist.lookup.chat.response",
                        message="Received artist extraction response",
                        data={
                            "song": song_name,
                            "artist": artist_name,
                            "raw_response": content
                        })
            return artist_name

        except Exception as exc:
            logger.exception("artist.lookup.chat.error",
                           message="Error during artist extraction",
                           exc=exc,
                           data={
                               "song": song_name,
                               "error_type": type(exc).__name__
                           })
            return ""

class AutoDJ:
    """AutoDJ class using Spotify APIs.
    The search_track_uri method applies filtering to only return tracks available in the US market,
    avoids live versions, and returns the most popular match for an exact artist match."""
    def __init__(self, spotify: Spotify):
        self.spotify = spotify
        logger.debug("Prompting user for playback device selection.")
        self.playback_device = self._select_playback_device()

        logger.debug("spotify.playback.init", message="Initializing playback state")
        self.playing_first_track = False

        self.queued_tracks = []
        self.clear_playback_context()
        self._print_variables()

    def _print_variables(self, return_value=None):
        """Stub function for logging internal state."""

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
        except Exception as e:
            logger.exception("spotify.device.error",
                            message="Failed to select playback device",
                            exc=e)

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
                logger.warning("spotify.search.no_match",
                               message=f"No matching track found for {artist} - {song}")
                return None
            best_track = max(filtered_tracks, key=lambda x: x.get('popularity', 0))
            return best_track.get('uri')

        except SpotifyException as exc:
            logger.exception("spotify.search.error",
                            message="Failed to search for track",
                            exc=exc)
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
            logger.debug("spotify.queue.status",
                        message="Current queue status",
                        data={"queued_tracks": self.queued_tracks})
            self._print_variables(True)
            return True
        except SpotifyException as e:
            logger.exception("spotify.queue.add.error",
                message="Failed to add song to queue",
                exc=e)
            return False

    def check_queue_status(self, silent=False) -> bool:
        try:
            if not self.playback_active():
                if len(self.queued_tracks) > 0:
                    logger.info("queue.check.start",
                                message="Queue populated but playback is not active. Starting playback.")
                    popped_track = self.queued_tracks.pop(0)
                    logger.debug("queue.check.popped",
                                message=f"Popped track: {popped_track}")
                    self.spotify.start_playback(device_id=self.playback_device, uris=[popped_track])
                    logger.debug("queue.check.playing_first_track",
                                message="Clearing playing_first_track flag.")
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
        except SpotifyException as exc:
            logger.exception("queue.check.error",
                            message="Failed to check queue status",
                            exc=exc)
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
                    logger.info("queue.clear.empty",
                                message="Queue is now empty")
                    break
                current_track = queue['queue'][0]['uri']
                if current_track == previous_track:

                    attempts += 1
                    if attempts >= max_attempts:
                        logger.info("queue.clear.max_attempts",
                                    message="Unable to clear the last track. Stopping.")
                        break
                else:

                    attempts = 0
                try:
                    self.spotify.next_track()
                    logger.info("queue.clear.skipped",
                                message=f"Skipped track: {queue['queue'][0]['name']}")
                    time.sleep(1)
                except SpotifyException as exc:
                    logger.error("queue.clear.error",
                                message=f"Error skipping track: {exc}")
                    break

                previous_track = current_track

            try:
                self.spotify.pause_playback()
                logger.info("queue.clear.pause",
                            message="Playback paused.")
            except SpotifyException as exc:
                logger.error("queue.clear.error",
                            message=f"Error pausing playback: {exc}")
            self.playing_first_track = False

            self.queued_tracks.clear()
            self._print_variables(True)
            return True


        except SpotifyException as exc:
            logger.exception("queue.clear.error",
                            message="Failed to clear playback context.",
                            exc=exc)

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


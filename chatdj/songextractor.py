import logging
import openai
from openai import OpenAI

logger = logging.getLogger('mongobate.chatdj.songextractor')
logger.setLevel(logging.DEBUG)

class SongExtractor:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)

    def find_titles(self, message, song_count=1):
        try:
            response = self.client.chat.completions.create(model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a music bot that can extract song titles from messages."
                },
                {
                    "role": "user",
                    "content": f"Extract exactly {song_count} song title{'s' if song_count > 1 else ''} from the following message: '{message}'. Respond with the artist and song title for each result with one per line."
                }
            ])

            logger.debug(f"response: {response}")

            song_titles_response = response.choices[0].message.content.strip().split('\n')
            song_titles = []
            for resp in song_titles_response:
                if ' - ' in resp:
                    artist, song = resp.split(' - ', 1)
                    song_titles.append({"artist": artist.strip(), "song": song.strip(), "gpt": True})
                else:
                    logger.warning(f"Unexpected format in response: {resp}")
                    if song_count == 1:
                        song_titles.append({"artist": "", "song": message, "gpt": False})

            logger.debug(f'song_titles: {song_titles}')
            return song_titles

        except openai.OpenAIError as e:
            logger.exception("Failed to extract song titles", exc_info=e)
            return []

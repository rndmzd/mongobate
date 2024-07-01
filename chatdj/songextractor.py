import logging
import openai

logger = logging.getLogger('mongobate.chatdj.songextractor')
logger.setLevel(logging.DEBUG)


class SongExtractor:
    def __init__(self, api_key):
        self.openai_client = openai.OpenAI(api_key=api_key)

    def find_titles(self, message, song_count=1):
        """Use OpenAI GPT-4o to extract song titles from the message."""
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
                model="gpt-4o"
            )

            logger.debug(f"response: {response}")
            print(response)

            song_titles_response = response.choices[0].message.content.strip().split('\n')
            song_titles = []
            for idx, resp in enumerate(song_titles_response):
                if ' - ' in resp:
                    artist, song = resp.split(' - ', 1)
                    song_titles.append(
                        {
                            "artist": artist.strip(),
                            "song": song.strip(),
                            "gpt": True
                        }
                    )
                else:
                    logger.warning(f"Unexpected format in response: {resp}")
                    #if len(song_titles_response) == 1 and song_count == 1:
                    if song_count == 1:
                        logger.warning("Returning original request text as song title.")
                        song_titles.append(
                            {
                                "artist": "",
                                "song": message,
                                "gpt": False
                            }
                        )

            logger.debug(f'song_titles: {song_titles}')
            logger.debug(f"len(song_titles): {len(song_titles)}")

            return song_titles

        except openai.APIError as e:
            logger.exception("Failed to extract song titles", exc_info=e)
            return []


if __name__ == '__main__':
    import configparser

    config = configparser.RawConfigParser()
    config.read("config.ini")

    song_extractor = SongExtractor(config.get("OpenAI", "api_key"))
    message = "Play 'Dancing Queen' by ABBA and hit me baby one more time by britney spears"
    song_count = 2
    song_titles = song_extractor.find_titles(message, song_count)
    print(song_titles)
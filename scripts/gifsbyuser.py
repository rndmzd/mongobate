import configparser
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import random

from utils.structured_logging import get_structured_logger

logger = get_structured_logger('mongobate.scripts.gifsbyuser')

config = configparser.ConfigParser()
config.read('config.ini')

mongo_username = config.get("MongoDB", "username")
mongo_password = config.get("MongoDB", "password")
mongo_host = config.get("MongoDB", "host")
mongo_port = config.getint("MongoDB", "port")
mongo_db = config.get("MongoDB", "db")
mongo_collection = config.get("MongoDB", "event_collection")

QUERY_USER = 'EXAMPLE_USER'

logger.info("gifsbyuser.init",
           message="Initializing GIFs by user analysis",
           data={
               "user": QUERY_USER,
               "mongo": {
                   "host": mongo_host,
                   "port": mongo_port,
                   "db": mongo_db,
                   "collection": mongo_collection
               }
           })

try:
    logger.debug("mongodb.connect",
                message="Connecting to MongoDB")
    client = MongoClient(f'mongodb://{mongo_username}:{mongo_password}@{mongo_host}:27017/?directConnection=true')
    
    logger.debug("mongodb.aggregate",
                message="Running aggregation pipeline")
    result = client['mongobate']['events'].aggregate([
        {
            '$match': {
                'object.user.username': QUERY_USER
            }
        }, {
            '$match': {
                '$or': [
                    {
                        'method': {
                            '$eq': 'chatMessage'
                        }
                    }, {
                        'method': {
                            '$eq': 'privateMessage'
                        }
                    }
                ]
            }
        }, {
            '$addFields': {
                'cleanedMessage': {
                    '$replaceOne': {
                        'input': '$object.message.message', 
                        'find': ':mtlhnre3 ', 
                        'replacement': ''
                    }
                }
            }
        }, {
            '$addFields': {
                'cleanedMessage': {
                    '$replaceOne': {
                        'input': '$cleanedMessage', 
                        'find': ':mtlhnre4 ', 
                        'replacement': ''
                    }
                }
            }
        }, {
            '$addFields': {
                'cleanedMessage': {
                    '$replaceOne': {
                        'input': '$cleanedMessage', 
                        'find': ':mtlhnre5 ', 
                        'replacement': ''
                    }
                }
            }
        }, {
            '$addFields': {
                'cleanedMessage': {
                    '$replaceOne': {
                        'input': '$cleanedMessage', 
                        'find': ':matng-fanclubmod-14 ', 
                        'replacement': ''
                    }
                }
            }
        }, {
            '$addFields': {
                'extractedSubstring': {
                    '$regexFind': {
                        'input': '$cleanedMessage', 
                        'regex': ':[A-Za-z0-9]{2,}'
                    }
                }
            }
        }, {
            '$match': {
                'extractedSubstring': {
                    '$ne': None
                }
            }
        }, {
            '$addFields': {
                'emoji': '$extractedSubstring.match'
            }
        }, {
            '$match': {
                'emoji': {
                    '$not': {
                        '$regex': '!omg:[A-Za-z0-9]{2,}'
                    }
                }
            }
        }, {
            '$match': {
                'emoji': {
                    '$not': {
                        '$regex': ':[0-9]{2}(am|AM|pm|PM)?'
                    }
                }
            }
        }, {
            '$group': {
                '_id': '$emoji', 
                'count': {
                    '$sum': 1
                }
            }
        }, {
            '$sort': {
                'count': -1
            }
        }
    ])

    # Prepare data for the word cloud
    word_frequencies = {doc['_id'].lstrip(':'): doc['count'] for doc in result if doc['_id']}
    
    logger.info("gifsbyuser.data",
                message="Retrieved GIF usage data",
                data={
                    "unique_gifs": len(word_frequencies),
                    "total_uses": sum(word_frequencies.values())
                })

    # Function for bright contrasting colors
    def bright_color_func(word=None, font_size=None, position=None, orientation=None, **kwargs):
        return f"hsl({random.randint(0, 360)}, 100%, 80%)"  # High saturation and lightness for visibility

    # Generate word cloud
    logger.debug("wordcloud.generate",
                message="Generating word cloud")
    wordcloud = WordCloud(
        width=800,
        height=400,
        background_color='black',
        color_func=bright_color_func,
        margin=5  # Add spacing between words
    ).generate_from_frequencies(word_frequencies)

    # Display the word cloud
    plt.figure(figsize=(20, 10), facecolor='black')
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.title(f"{QUERY_USER}'s Most Used Gifs", fontsize=28, color='#00ffff', pad=20, usetex=False, y=1.02)

    output_file = f'{QUERY_USER}_wordcloud.png'
    logger.info("wordcloud.save",
                message="Saving word cloud image",
                data={"file": output_file})
                
    # Save the plot with high DPI for quality
    plt.savefig(output_file, 
                dpi=300, 
                bbox_inches='tight', 
                facecolor='black',
                edgecolor='none',
                pad_inches=0.5)

    plt.show()
    
    logger.info("gifsbyuser.complete",
                message="Analysis completed successfully")

except Exception as exc:
    logger.exception("gifsbyuser.error",
                    exc=exc,
                    message="Failed to analyze GIF usage")
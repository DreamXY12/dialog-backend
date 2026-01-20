import redis
import time
import json
from config import get_parameter


DEBUG = get_parameter("dev", "debug") == "1"

if DEBUG ==False:
    HOST_NAME = "localhost"
    PORT = 6379
    DB = 0
else:
    HOST_NAME = get_parameter("redis", "host_name")
    PORT = int(get_parameter("redis", "port"))
    DB = int(get_parameter("redis", "db"))


# HOST_NAME = get_parameter("redis", "host_name")
# PORT = int(get_parameter("redis", "port"))
# DB = int(get_parameter("redis", "db"))


# DEBUG = True
# if DEBUG:
#     HOST_NAME = "localhost"
#     PORT = 6379
#     DB = 0


# Connect to Redis
r = redis.Redis(host=HOST_NAME, port=PORT, db=DB)
# comment out this line for production in aws
# r = redis.Redis(host=HOST_NAME, port=PORT, db=0, ssl=True)

def store_message(chat_id, message: tuple):
    # Serialize the tuple to a JSON string
    message_str = json.dumps(message)
    
    # Use a unique key for each chat message
    key = f"chat:{chat_id}:{int(time.time())}"
    # Store the message with an expiration time of 600 seconds (10 minutes)
    r.setex(key, 600, message_str)
    

# def get_chat_history(chat_id):
#     # Get all keys related to the chat_id
#     keys = r.keys(f"chat:{chat_id}:*")
#     sorted_keys = sorted(keys, key=lambda k: int(k.decode('utf-8').split(':')[-1]))
#     # Retrieve and deserialize all messages
#     messages = [tuple(json.loads(r.get(key).decode('utf-8'))) for key in sorted_keys]
    
#     return messages

def get_chat_history(chat_id):
    # Initialize Redis client

    # Use SCAN to get all keys related to the chat_id
    cursor = '0'
    keys = []
    pattern = f"chat:{chat_id}:*"

    while cursor != 0:
        cursor, batch_keys = r.scan(cursor=cursor, match=pattern, count=100)
        keys.extend(batch_keys)

    # Sort keys based on the numeric part after the last colon
    sorted_keys = sorted(keys, key=lambda k: int(k.decode('utf-8').split(':')[-1]))

    # Retrieve and deserialize all messages
    messages = [tuple(json.loads(r.get(key).decode('utf-8'))) for key in sorted_keys]

    return messages


def test_redis_connection():
    try:
        r = redis.Redis(
            host=HOST_NAME,
            port=PORT,
            db=DB,
            ssl=True
        )

        # Test the connection
        r.ping()
        print("Connected to Redis successfully with TLS!")
    except redis.ConnectionError as e:
        print(f"Failed to connect to Redis: {e}")

if __name__ == "__main__":
    test_redis_connection()

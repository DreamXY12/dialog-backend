import redis

def test_redis_connection(host='dialog-reids-pj78b4.serverless.apse1.cache.amazonaws.com', port=6379, db=0):
    try:
        # Create a Redis client
        client = redis.Redis(
            host=host,
            port=6379,
            db=0,
            ssl=True
        )
        
        # Ping the Redis server
        response = client.ping()
        
        if response:
            print("Successfully connected to Redis!")
        else:
            print("Failed to connect to Redis.")
    
    except redis.ConnectionError as e:
        print(f"Connection error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

# Test the connection
test_redis_connection()
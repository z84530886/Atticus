import redis
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("REDIS_HOST", "localhost")
port = int(os.getenv("REDIS_PORT", 6379))
password = os.getenv("REDIS_PASSWORD")

print(f"Testing connection to Redis at {host}:{port} (Password: {'***' if password else 'None'})...")

try:
    r = redis.Redis(host=host, port=port, password=password, socket_timeout=5)
    if r.ping():
        print("✅ Successfully connected to Redis!")
    else:
        print("❌ Connected but PING failed.")
except redis.AuthenticationError:
    print("❌ Authentication failed. Check REDIS_PASSWORD.")
except redis.ConnectionError as e:
    print(f"❌ Connection Error: {e}")
except Exception as e:
    print(f"❌ Unexpected Error: {e}")

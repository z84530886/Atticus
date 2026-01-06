"""
Redis client management for Atticus.

Provides a centralized Redis client instance for task state management
and caching across the application.
"""
import redis
from app.core.config import settings

# Global Redis client instance
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)

def get_redis_client() -> redis.Redis:
    """Get the Redis client instance."""
    return redis_client

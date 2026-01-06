from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "Atticus"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    BLENDER_PATH: str = "blender"
    BLENDER_SCRIPTS_PATH: str = "./blender_scripts"

    DATABASE_URL: str = "sqlite:///./atticus.db"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 3600

    STORAGE_PATH: str = "./storage"
    UPLOAD_PATH: str = "./storage/uploads"
    TEMP_PATH: str = "./storage/temp"
    RESULTS_PATH: str = "./storage/results"
    MAX_FILE_SIZE: int = 104857600

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    TASK_CLEANUP_INTERVAL: int = 3600
    TEMP_FILE_TTL: int = 86400

    TENCENTCLOUD_SECRET_ID: str = ""
    TENCENTCLOUD_SECRET_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

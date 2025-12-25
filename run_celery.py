import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tasks.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start()

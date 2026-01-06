"""
Generation service for managing 3D model generation tasks.

Handles task creation, status tracking, and file management for
the 3D generation pipeline.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.orm import Generation
from app.models.schemas import Generate3DRequest, TaskStatus, File3D
from app.core.redis import get_redis_client
import json

class GenerationService:
    def __init__(self, db: Session):
        self.db = db
        self.redis_client = get_redis_client()

    def create_generation_task(self, request: Generate3DRequest, task_id: str) -> None:
        """
        Create a new generation task and save to database if project_id is present.
        """
        if request.project_id:
            db_gen = Generation(
                id=task_id,
                project_id=request.project_id,
                type=request.generation_type.value,
                input_params=request.dict(),
                status=TaskStatus.PENDING.value
            )
            self.db.add(db_gen)
            self.db.commit()

    def submit_task(self, task_id: str, request_dict: dict) -> None:
        """
        Submit generation task to background workers.
        """
        from app.tasks.generation_tasks import submit_generation_task, monitor_generation_task
        submit_generation_task.delay(task_id, request_dict)
        monitor_generation_task.delay(task_id, "")

    def get_task_status(self, task_id: str) -> dict:
        """
        Get task status from Redis.
        
        Returns:
            dict with keys: status, progress, result_files, error
        """
        task_data = self.redis_client.hgetall(f"task:{task_id}")
        
        if not task_data:
            return None
        
        status = TaskStatus(task_data.get("status", TaskStatus.PROCESSING.value))
        progress = float(task_data.get("progress", "0.0"))
        error = task_data.get("error")
        
        result_files = None
        if task_data.get("result_files"):
            try:
                result_files = [File3D(**f) for f in json.loads(task_data["result_files"])]
            except:
                pass
        
        return {
            "status": status,
            "progress": progress,
            "result_files": result_files,
            "error": error
        }

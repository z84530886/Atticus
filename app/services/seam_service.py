"""
Seam service for managing seam generation tasks.

Handles file upload, model path resolution, task creation and status tracking
for the seam processing pipeline.
"""
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from app.models.orm import Generation
from app.models.schemas import TaskStatus, File3D
from app.core.redis import get_redis_client
from app.core.config import settings
import json

class SeamService:
    def __init__(self, db: Session):
        self.db = db
        self.redis_client = get_redis_client()

    def _resolve_storage_path(self, p: str) -> str:
        """Resolve storage path to absolute path."""
        path = Path(p)
        if path.is_absolute():
            return str(path)
        # Relative to Atticus root
        base = Path(__file__).resolve().parents[2]
        return str((base / path).resolve())

    async def process_model_file(
        self, 
        task_id: str,
        model_file: Optional[UploadFile],
        model_task_id: Optional[str],
        model_file_type: str,
        model_filename: Optional[str]
    ) -> Path:
        """
        Process model file: either save uploaded file or resolve existing file path.
        
        Returns:
            Path to the model file
        """
        results_root = Path(self._resolve_storage_path(settings.RESULTS_PATH))
        out_dir = results_root / task_id / "seams"
        
        if model_file is not None:
            # Upload case
            suffix = Path(model_file.filename or "model.glb").suffix
            if not suffix:
                suffix = ".glb"
            model_path = out_dir / f"model{suffix}"
            model_bytes = await model_file.read()
            model_path.write_bytes(model_bytes)
            return model_path
        else:
            # Reference case
            if not model_task_id or not model_filename:
                raise HTTPException(
                    status_code=400,
                    detail="Either upload model_file or provide model_task_id + model_filename"
                )
            
            model_path = results_root / str(model_task_id) / str(model_file_type) / str(model_filename)
            if not model_path.exists():
                raise HTTPException(status_code=404, detail=f"Model not found: {model_path}")
            
            return model_path

    async def save_points_file(self, task_id: str, points_file: UploadFile) -> Path:
        """Save uploaded points JSON file."""
        results_root = Path(self._resolve_storage_path(settings.RESULTS_PATH))
        out_dir = results_root / task_id / "seams"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        points_path = out_dir / "seam_points.json"
        points_bytes = await points_file.read()
        points_path.write_bytes(points_bytes)
        return points_path

    def create_task_record(
        self,
        task_id: str,
        project_id: Optional[str],
        model_file_type: str,
        model_filename: Optional[str]
    ) -> None:
        """Create database record for the seam task."""
        if project_id:
            db_gen = Generation(
                id=task_id,
                project_id=project_id,
                pipeline_step="seam_generation",
                input_params={
                   "model_file_type": model_file_type,
                   "model_filename": model_filename or "uploaded",
                },
                status=TaskStatus.PENDING.value
            )
            self.db.add(db_gen)
            self.db.commit()

    def init_task_status(self, task_id: str) -> None:
        """Initialize task status in Redis."""
        self.redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.PROCESSING.value,
                "progress": "0.0",
            },
        )

    def submit_seam_task(self, task_id: str, model_path: Path, points_path: Path) -> None:
        """Submit seam processing task to background worker."""
        from app.tasks.seam_tasks import run_seam_task
        run_seam_task.delay(
            task_id,
            {
                "model_path": str(model_path),
                "points_path": str(points_path),
            },
        )

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
                parsed = json.loads(task_data["result_files"])
                if isinstance(parsed, list):
                    result_files = [File3D(**f) for f in parsed if isinstance(f, dict)]
            except Exception:
                result_files = None

        return {
            "status": status,
            "progress": progress,
            "result_files": result_files,
            "error": error
        }

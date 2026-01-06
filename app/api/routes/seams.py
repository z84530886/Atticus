import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db

from app.core.config import settings
from app.models.schemas import QueryTaskResponse, SeamSubmitResponse, TaskStatus
from app.services import SeamService

router = APIRouter(prefix="/api/v1/seams", tags=["seams"])


def _resolve_storage_path(p: str) -> str:
    """Helper function for file download."""
    path = Path(p)
    if path.is_absolute():
        return str(path)
    base = Path(__file__).resolve().parents[3]
    return str((base / path).resolve())


@router.post("/submit", response_model=SeamSubmitResponse)
async def submit_seams(
    background_tasks: BackgroundTasks,
    points_file: UploadFile = File(..., description="缝合线坐标点JSON文件，包含OBJ原始坐标"),
    model_file: Optional[UploadFile] = File(None, description="模型文件（OBJ/GLB格式），如果不上传则需要提供model_task_id"),
    model_task_id: Optional[str] = Form(None, description="之前生成任务的ID，用于引用已生成的模型"),
    model_file_type: str = Form("topologized", description="模型文件类型：original或topologized"),
    model_filename: Optional[str] = Form(None, description="模型文件名"),
    project_id: Optional[str] = Form(None, description="项目ID"),
    db: Session = Depends(get_db),
):
    try:
        task_id = str(uuid.uuid4())
        service = SeamService(db)

        # Create DB record
        service.create_task_record(task_id, project_id, model_file_type, model_filename)

        # Save points file
        points_path = await service.save_points_file(task_id, points_file)

        # Process model file (upload or reference)
        model_path = await service.process_model_file(
            task_id, model_file, model_task_id, model_file_type, model_filename
        )

        # Initialize task status in Redis
        service.init_task_status(task_id)

        # Submit to background worker
        service.submit_seam_task(task_id, model_path, points_path)

        return SeamSubmitResponse(
            task_id=task_id,
            status=TaskStatus.PROCESSING,
            message="Seam generation task submitted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/files/{task_id}/{filename}")
async def download_seam_file(task_id: str, filename: str):
    try:
        base = Path(_resolve_storage_path(settings.RESULTS_PATH))
        file_path = base / task_id / "seams" / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            str(file_path),
            filename=str(filename),
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/task/{task_id}", response_model=QueryTaskResponse)
async def get_seam_task_status(task_id: str, db: Session = Depends(get_db)):
    try:
        service = SeamService(db)
        task_status = service.get_task_status(task_id)

        if task_status is None:
            raise HTTPException(status_code=404, detail="Task not found")

        return QueryTaskResponse(
            task_id=task_id,
            status=task_status["status"],
            progress=task_status["progress"],
            result_files=task_status["result_files"],
            error=task_status["error"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

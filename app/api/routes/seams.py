import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.models.schemas import File3D, QueryTaskResponse, SeamSubmitResponse, TaskStatus
from app.tasks.seam_tasks import run_seam_task

import redis

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True,
)

router = APIRouter(prefix="/api/v1/seams", tags=["seams"])


def _resolve_storage_path(p: str) -> str:
    path = Path(p)
    if path.is_absolute():
        return str(path)
    base = Path(__file__).resolve().parents[3]
    return str((base / path).resolve())


@router.post("/submit", response_model=SeamSubmitResponse)
async def submit_seams(
    background_tasks: BackgroundTasks,
    points_file: UploadFile = File(...),
    model_file: Optional[UploadFile] = File(None),
    model_task_id: Optional[str] = Form(None),
    model_file_type: str = Form("topologized"),
    model_filename: Optional[str] = Form(None),
    axis: str = Form("three_to_blender_a"),
    points_origin: str = Form("model_bbox_center"),
    do_imprint: int = Form(1),
):
    try:
        task_id = str(uuid.uuid4())

        results_root = Path(_resolve_storage_path(settings.RESULTS_PATH))
        out_dir = results_root / task_id / "seams"
        out_dir.mkdir(parents=True, exist_ok=True)

        points_path = out_dir / "seam_points.json"
        points_bytes = await points_file.read()
        points_path.write_bytes(points_bytes)

        if model_file is not None:
            suffix = Path(model_file.filename or "model.glb").suffix
            if not suffix:
                suffix = ".glb"
            model_path = out_dir / f"model{suffix}"
            model_bytes = await model_file.read()
            model_path.write_bytes(model_bytes)
        else:
            if not model_task_id or not model_filename:
                raise HTTPException(
                    status_code=400,
                    detail="Either upload model_file or provide model_task_id + model_filename",
                )

            results_root = Path(_resolve_storage_path(settings.RESULTS_PATH))
            model_path = results_root / str(model_task_id) / str(model_file_type) / str(model_filename)
            if not model_path.exists():
                raise HTTPException(status_code=404, detail=f"Model not found: {model_path}")

        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.PROCESSING.value,
                "progress": "0.0",
            },
        )

        run_seam_task.delay(
            task_id,
            {
                "model_path": str(model_path),
                "points_path": str(points_path),
                "axis": str(axis),
                "points_origin": str(points_origin),
                "do_imprint": int(do_imprint),
            },
        )

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
async def get_seam_task_status(task_id: str):
    try:
        task_data = redis_client.hgetall(f"task:{task_id}")

        if not task_data:
            raise HTTPException(status_code=404, detail="Task not found")

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

        return QueryTaskResponse(
            task_id=task_id,
            status=status,
            progress=progress,
            result_files=result_files,
            error=error,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

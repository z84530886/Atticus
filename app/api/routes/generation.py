import uuid
import os
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from app.models.schemas import (
    Generate3DRequest,
    Generate3DResponse,
    QueryTaskResponse,
    TaskStatus,
    File3D
)
from app.tasks.generation_tasks import submit_generation_task, monitor_generation_task
from app.core.config import settings
import redis

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


@router.post("/generate", response_model=Generate3DResponse)
async def generate_3d_model(request: Generate3DRequest, background_tasks: BackgroundTasks):
    try:
        task_id = str(uuid.uuid4())
        
        submit_generation_task.delay(task_id, request.dict())
        
        monitor_generation_task.delay(task_id, "")
        
        return Generate3DResponse(
            task_id=task_id,
            status=TaskStatus.PROCESSING,
            message="3D model generation task submitted successfully"
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/files/{task_id}/{file_type}/{filename}")
async def download_file(task_id: str, file_type: str, filename: str):
    try:
        file_path = os.path.join(settings.RESULTS_PATH, task_id, file_type, filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/task/{task_id}", response_model=QueryTaskResponse)
async def get_task_status(task_id: str):
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
                result_files = [File3D(**f) for f in json.loads(task_data["result_files"])]
            except:
                pass
        
        return QueryTaskResponse(
            task_id=task_id,
            status=status,
            progress=progress,
            result_files=result_files,
            error=error
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

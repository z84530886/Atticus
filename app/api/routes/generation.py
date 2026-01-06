import uuid
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from fastapi.responses import FileResponse
from app.models.schemas import (
    Generate3DRequest,
    Generate3DResponse,
    QueryTaskResponse,
    TaskStatus
)
from app.services import GenerationService
from app.core.config import settings

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


@router.post("/generate", response_model=Generate3DResponse)
async def generate_3d_model(
    request: Generate3DRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        task_id = str(uuid.uuid4())
        service = GenerationService(db)
        
        # Save to DB if project_id is present
        service.create_generation_task(request, task_id)
        
        # Submit to background workers
        service.submit_task(task_id, request.dict())

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
async def get_task_status(task_id: str, db: Session = Depends(get_db)):
    try:
        service = GenerationService(db)
        task_status = service.get_task_status(task_id)
        
        if task_status is None:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return QueryTaskResponse(
            task_id=task_id,
            status=task_status["status"],
            progress=task_status["progress"],
            result_files=task_status["result_files"],
            error=task_status["error"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

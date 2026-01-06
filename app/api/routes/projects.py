from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.schemas import ProjectCreate, ProjectResponse
from app.services import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


# Mock User dependency (replace with real auth later)
def get_current_user_id():
    # In a real app, this comes from the JWT token
    # For now, we reuse a specific UUID or create one if not exists
    return "demo-user-id"


@router.post("/", response_model=ProjectResponse)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    service = ProjectService(db)
    return service.create_project(project, user_id)


@router.get("/", response_model=List[ProjectResponse])
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    service = ProjectService(db)
    return service.get_user_projects(user_id, skip, limit)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    service = ProjectService(db)
    project = service.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

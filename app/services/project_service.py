from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.orm import Project, User
from app.models.schemas import ProjectCreate

class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def _ensure_user_exists(self, user_id: str) -> User:
        """
        Ensure the user exists in the database.
        For the demo, we create a mock user if not found.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            # Mock user creation logic
            user = User(
                id=user_id, 
                email="demo@example.com", 
                display_name="Demo User"
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user

    def create_project(self, project_data: ProjectCreate, user_id: str) -> Project:
        """
        Create a new project.
        """
        self._ensure_user_exists(user_id)

        db_project = Project(
            title=project_data.title,
            description=project_data.description,
            is_public=project_data.is_public,
            user_id=user_id,
            status="concept"
        )
        self.db.add(db_project)
        self.db.commit()
        self.db.refresh(db_project)
        return db_project

    def get_user_projects(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Project]:
        """
        Get all projects for a specific user.
        """
        return self.db.query(Project).filter(Project.user_id == user_id)\
                      .offset(skip).limit(limit).all()

    def get_project(self, project_id: str, user_id: str) -> Optional[Project]:
        """
        Get a single project by ID and user ID.
        """
        return self.db.query(Project).filter(
            Project.id == project_id, 
            Project.user_id == user_id
        ).first()

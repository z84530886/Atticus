import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    display_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    title = Column(String)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    cover_image_url = Column(String, nullable=True)
    status = Column(String, default="concept")  # concept, modeling, pattern_ready
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="projects")
    generations = relationship("Generation", back_populates="project")
    assets = relationship("Asset", back_populates="project")
    patterns = relationship("Pattern", back_populates="project")


class Generation(Base):
    __tablename__ = "generations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    pipeline_step = Column(String)  # hunyuan_3d, seam_extraction...
    external_job_id = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    type = Column(String)  # text_to_3d, image_to_3d
    input_params = Column(JSON, nullable=True)
    result_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="generations")
    assets = relationship("Asset", back_populates="generation")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    generation_id = Column(String, ForeignKey("generations.id"), nullable=True)
    type = Column(String)  # model_glb, image_png...
    role = Column(String)  # front_view, final_mesh...
    storage_path = Column(String)
    url = Column(String)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="assets")
    generation = relationship("Generation", back_populates="assets")
    patterns = relationship("Pattern", back_populates="base_asset")


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    base_asset_id = Column(String, ForeignKey("assets.id"))
    name = Column(String)
    pieces_data = Column(JSON)
    seams_data = Column(JSON)
    assembly_instructions = Column(JSON, nullable=True)
    annotations = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="patterns")
    base_asset = relationship("Asset", back_populates="patterns")

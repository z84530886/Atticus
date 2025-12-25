from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List


class GenerationType(str, Enum):
    text = "text"
    image = "image"
    multi_image = "multi_image"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    TOPOLOGIZING = "topologizing"
    COMPLETED = "completed"
    FAILED = "failed"


class TextRequest(BaseModel):
    prompt: str = Field(..., description="Text description for 3D model generation")


class ImageRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded image")
    prompt: Optional[str] = Field(None, description="Optional text prompt")


class MultiImageRequest(BaseModel):
    images: List[str] = Field(..., min_length=1, max_length=4, description="List of 1-4 base64 encoded images")
    prompt: Optional[str] = Field(None, description="Optional text prompt")


class Generate3DRequest(BaseModel):
    generation_type: GenerationType = Field(..., description="Type of generation: text, image, or multi_image")
    text_request: Optional[TextRequest] = Field(None, description="Text generation request")
    image_request: Optional[ImageRequest] = Field(None, description="Single image generation request")
    multi_image_request: Optional[MultiImageRequest] = Field(None, description="Multi-image generation request")
    result_format: str = Field("obj", description="Output format: obj or glb")
    enable_pbr: bool = Field(True, description="Enable PBR materials")
    enable_geometry: bool = Field(True, description="Enable geometry optimization")


class File3D(BaseModel):
    preview_image_url: str = Field(..., description="Preview image URL")
    type: str = Field(..., description="File type")
    url: str = Field(..., description="Download URL")


class Generate3DResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Task status")
    message: str = Field(..., description="Response message")


class QueryTaskResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Task status")
    progress: float = Field(..., ge=0.0, le=100.0, description="Progress percentage")
    result_files: Optional[List[File3D]] = Field(None, description="Generated 3D files")
    error: Optional[str] = Field(None, description="Error message if failed")

import sys
import os
import aiohttp
import asyncio
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from typing import Optional, List
from app.core.config import settings
from tencent_hunyuan_3d.client import (
    TencentHunyuan3DClient,
    SubmitJobRequest,
    SubmitProJobRequest,
    ViewImage,
    File3D,
    SubmitReduceFaceJobRequest,
    DescribeReduceFaceJobRequest
)
from app.models.schemas import (
    Generate3DRequest,
    TaskStatus
)


class HunyuanService:
    def __init__(self):
        self.client = TencentHunyuan3DClient(
            secret_id=settings.TENCENTCLOUD_SECRET_ID,
            secret_key=settings.TENCENTCLOUD_SECRET_KEY
        )

    async def submit_generation_task(self, request: Generate3DRequest) -> str:
        try:
            if request.generation_type.value == "text":
                submit_request = SubmitJobRequest(
                    Prompt=request.text_request.prompt,
                    ResultFormat=request.result_format,
                    EnablePBR=request.enable_pbr,
                    EnableGeometry=request.enable_geometry
                )
                response = self.client.submit_hunyuan_to_3d_rapid_job(submit_request)
            
            elif request.generation_type.value == "image":
                submit_request = SubmitJobRequest(
                    ImageBase64=request.image_request.image_base64,
                    Prompt=request.image_request.prompt,
                    ResultFormat=request.result_format,
                    EnablePBR=request.enable_pbr,
                    EnableGeometry=request.enable_geometry
                )
                response = self.client.submit_hunyuan_to_3d_rapid_job(submit_request)
            
            elif request.generation_type.value == "multi_image":
                multi_view_images = []
                for img in request.multi_image_request.images:
                    multi_view_images.append(ViewImage(View="front", ImageBase64=img))
                
                submit_request = SubmitProJobRequest(
                    MultiViewImages=multi_view_images,
                    Prompt=request.multi_image_request.prompt,
                    EnablePBR=request.enable_pbr,
                    FaceCount=500000,
                    GenerateType="Normal",
                    PolygonType="triangle"
                )
                response = self.client.submit_hunyuan_to_3d_pro_job(submit_request)
            
            return response.JobId
        
        except Exception as e:
            raise ValueError(f"Failed to submit generation task: {str(e)}")

    async def query_task_status(self, job_id: str) -> dict:
        try:
            response = self.client.query_hunyuan_to_3d_rapid_job(job_id)
            
            status_map = {
                "Pending": TaskStatus.PENDING,
                "Processing": TaskStatus.PROCESSING,
                "Completed": TaskStatus.COMPLETED,
                "Failed": TaskStatus.FAILED
            }
            
            result_files = []
            if response.ResultFile3Ds:
                for file_3d in response.ResultFile3Ds:
                    result_files.append(File3D(
                        PreviewImageUrl=file_3d.PreviewImageUrl,
                        Type=file_3d.Type,
                        Url=file_3d.Url
                    ))
            
            return {
                "status": status_map.get(response.Status, TaskStatus.PROCESSING),
                "result_files": result_files,
                "error": response.ErrorMessage if response.ErrorMessage else None
            }
        
        except Exception as e:
            raise ValueError(f"Failed to query task status: {str(e)}")

    async def topologize_model(self, result_files: list) -> dict:
        try:
            if not result_files:
                return {
                    "success": False,
                    "error": "No 3D model files to topologize"
                }
            
            primary_file = result_files[0]
            
            topologize_file = File3D(
                PreviewImageUrl="",
                Type=primary_file.Type,
                Url=primary_file.Url
            )
            
            submit_request = SubmitReduceFaceJobRequest(
                File3D=topologize_file,
                PolygonType="triangle",
                FaceLevel="high"
            )
            
            response = self.client.submit_reduce_face_job(submit_request)
            job_id = response.JobId
            
            max_attempts = 30
            attempt = 0
            
            while attempt < max_attempts:
                query_request = DescribeReduceFaceJobRequest(JobId=job_id)
                query_response = self.client.describe_reduce_face_job(query_request)
                
                if query_response.Status == "DONE":
                    topologized_files = []
                    for file_3d in query_response.ResultFile3Ds:
                        topologized_files.append(File3D(
                            PreviewImageUrl=file_3d.PreviewImageUrl,
                            Type=file_3d.Type,
                            Url=file_3d.Url
                        ))
                    
                    return {
                        "success": True,
                        "result_files": topologized_files
                    }
                
                elif query_response.Status == "FAIL":
                    return {
                        "success": False,
                        "error": f"Topologization failed: {query_response.ErrorMessage}"
                    }
                
                elif query_response.Status in ["WAIT", "RUN"]:
                    await asyncio.sleep(10)
                    attempt += 1
                else:
                    await asyncio.sleep(10)
                    attempt += 1
            
            return {
                "success": False,
                "error": "Topologization timeout"
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Topologization failed: {str(e)}"
            }

    async def download_file(self, url: str, save_path: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        return True
                    return False
        except Exception as e:
            print(f"Download failed: {str(e)}")
            return False

    async def download_and_store_files(self, result_files: list, task_id: str, file_type: str = "original") -> list:
        try:
            if not result_files:
                return []
            
            stored_files = []
            base_path = os.path.join(settings.RESULTS_PATH, task_id, file_type)
            
            for idx, file_3d in enumerate(result_files):
                file_extension = file_3d.Type.lower()
                if not file_extension.startswith('.'):
                    file_extension = '.' + file_extension
                
                local_filename = f"model_{idx}{file_extension}"
                local_path = os.path.join(base_path, local_filename)
                
                download_success = await self.download_file(file_3d.Url, local_path)
                
                if download_success:
                    preview_filename = f"preview_{idx}.png"
                    preview_path = os.path.join(base_path, preview_filename)
                    await self.download_file(file_3d.PreviewImageUrl, preview_path)
                    
                    stored_files.append(File3D(
                        PreviewImageUrl=f"/api/v1/files/{task_id}/{file_type}/{preview_filename}",
                        Type=file_3d.Type,
                        Url=f"/api/v1/files/{task_id}/{file_type}/{local_filename}"
                    ))
            
            return stored_files
        
        except Exception as e:
            print(f"Download and store failed: {str(e)}")
            return []

import asyncio
import json
from app.tasks.celery_app import celery_app
from app.services.hunyuan_service import HunyuanService
from app.models.schemas import TaskStatus, File3D
from app.core.config import settings
import redis

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)


@celery_app.task(name="app.tasks.topology_tasks.topologize_model_task")
def topologize_model_task(task_id: str, result_files_data: list):
    hunyuan_service = HunyuanService()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result_files = []
        for f in result_files_data:
            if isinstance(f, dict):
                result_files.append(File3D(**f))
            else:
                result_files.append(f)
        
        topo_result = loop.run_until_complete(
            hunyuan_service.topologize_model(result_files)
        )
        
        if topo_result["success"]:
            topologized_files = loop.run_until_complete(
                hunyuan_service.download_and_store_files(
                    topo_result["result_files"],
                    task_id,
                    "topologized"
                )
            )
            
            if topologized_files:
                redis_client.hset(
                    f"task:{task_id}",
                    "result_files",
                    json.dumps([f.dict() for f in topologized_files])
                )
            else:
                original_files_str = redis_client.hget(f"task:{task_id}", "original_files")
                if original_files_str:
                    redis_client.hset(
                        f"task:{task_id}",
                        "result_files",
                        original_files_str
                    )
            
            redis_client.hset(
                f"task:{task_id}",
                mapping={
                    "status": TaskStatus.COMPLETED.value,
                    "progress": "100.0"
                }
            )
            
            return {"status": "completed", "files": len(topologized_files)}
        
        else:
            redis_client.hset(
                f"task:{task_id}",
                mapping={
                    "status": TaskStatus.FAILED.value,
                    "error": topo_result["error"]
                }
            )
            
            return {"status": "failed", "error": topo_result["error"]}
    
    except Exception as e:
        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.FAILED.value,
                "error": str(e)
            }
        )
        raise
    finally:
        loop.close()

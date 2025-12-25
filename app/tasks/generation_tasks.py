import asyncio
from app.tasks.celery_app import celery_app
from app.services.hunyuan_service import HunyuanService
from app.models.schemas import TaskStatus
from app.core.config import settings
import redis

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True
)


@celery_app.task(name="app.tasks.generation_tasks.submit_generation_task")
def submit_generation_task(task_id: str, request_data: dict):
    hunyuan_service = HunyuanService()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        from app.models.schemas import Generate3DRequest
        request = Generate3DRequest(**request_data)
        
        job_id = loop.run_until_complete(
            hunyuan_service.submit_generation_task(request)
        )
        
        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "job_id": job_id,
                "status": TaskStatus.PROCESSING.value,
                "progress": "0.0"
            }
        )
        
        return {"job_id": job_id, "status": "submitted"}
    
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


@celery_app.task(name="app.tasks.generation_tasks.monitor_generation_task")
def monitor_generation_task(task_id: str):
    hunyuan_service = HunyuanService()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        job_id = redis_client.hget(f"task:{task_id}", "job_id")
        
        if not job_id:
            redis_client.hset(
                f"task:{task_id}",
                mapping={
                    "status": TaskStatus.FAILED.value,
                    "error": "Job ID not found"
                }
            )
            return {"status": "failed", "error": "Job ID not found"}
        
        max_attempts = 60
        attempt = 0
        
        while attempt < max_attempts:
            result = loop.run_until_complete(
                hunyuan_service.query_task_status(job_id)
            )
            
            progress = min((attempt + 1) * 1.5, 60.0)
            
            redis_client.hset(
                f"task:{task_id}",
                mapping={
                    "status": result["status"].value,
                    "progress": str(progress)
                }
            )
            
            if result["status"] == TaskStatus.COMPLETED:
                original_files = loop.run_until_complete(
                    hunyuan_service.download_and_store_files(
                        result["result_files"],
                        task_id,
                        "original"
                    )
                )
                
                if original_files:
                    redis_client.hset(
                        f"task:{task_id}",
                        "original_files",
                        str([f.dict() for f in original_files])
                    )
                
                redis_client.hset(
                    f"task:{task_id}",
                    mapping={
                        "status": TaskStatus.TOPOLOGIZING.value,
                        "progress": "60.0"
                    }
                )
                
                from app.tasks.topology_tasks import topologize_model_task
                topologize_model_task.delay(task_id, [f.dict() for f in result["result_files"]])
                
                return {"status": "completed", "next_step": "topologizing"}
            
            elif result["status"] == TaskStatus.FAILED:
                redis_client.hset(
                    f"task:{task_id}",
                    mapping={
                        "status": TaskStatus.FAILED.value,
                        "error": result["error"]
                    }
                )
                return {"status": "failed", "error": result["error"]}
            
            attempt += 1
            loop.run_until_complete(asyncio.sleep(5))
        
        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.FAILED.value,
                "error": "Task timeout"
            }
        )
        return {"status": "failed", "error": "Task timeout"}
    
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

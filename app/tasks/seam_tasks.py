import json
import subprocess
from pathlib import Path

from app.core.config import settings
from app.models.schemas import TaskStatus
from app.tasks.celery_app import celery_app

import redis

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=True,
)


def _resolve_path_relative_to_atticus(p: str) -> str:
    path = Path(p)
    if path.is_absolute():
        return str(path)
    atticus_root = Path(__file__).resolve().parents[2]
    return str((atticus_root / path).resolve())


def _run_blender(*, blender_exe: str, script_path: str, argv: list, log_path: Path) -> None:
    cmd = [str(blender_exe), "-b", "-noaudio", "--python", str(script_path), "--", *[str(a) for a in argv]]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(f"Blender failed (code={proc.returncode}). See log: {log_path}")


@celery_app.task(name="app.tasks.seam_tasks.run_seam_task")
def run_seam_task(task_id: str, payload: dict):
    """
    处理缝合线标记任务。
    
    直接使用前端传来的OBJ原始坐标，通过Blender的imprint_seams_from_points.py脚本
    标记缝合线（对于已有边直接标记，对于不存在的边先创建再标记）。
    
    Args:
        task_id: 任务ID
        payload: 包含以下字段的字典
            - model_path: 模型文件路径（OBJ或GLB/GLTF格式）
            - points_path: 缝合线坐标点JSON文件路径
    """
    try:
        model_path = str(payload["model_path"])
        points_path = str(payload["points_path"])

        results_root = Path(_resolve_path_relative_to_atticus(settings.RESULTS_PATH))
        out_dir = results_root / str(task_id) / "seams"
        out_dir.mkdir(parents=True, exist_ok=True)

        blender_exe = _resolve_path_relative_to_atticus(settings.BLENDER_PATH)
        scripts_dir = Path(_resolve_path_relative_to_atticus(settings.BLENDER_SCRIPTS_PATH))

        imprint_script = scripts_dir / "imprint_seams_from_points.py"

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if not Path(points_path).exists():
            raise FileNotFoundError(f"Points file not found: {points_path}")
        if not imprint_script.exists():
            raise FileNotFoundError(f"Blender script not found: {imprint_script}")

        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.PROCESSING.value,
                "progress": "10.0",
            },
        )

        # 直接使用原始坐标进行缝合线标记
        imprint_blend = out_dir / "seam_imprinted.blend"
        imprint_log = out_dir / "blender_imprint.log"

        _run_blender(
            blender_exe=blender_exe,
            script_path=str(imprint_script),
            argv=[
                "--input_model",
                model_path,
                "--points_json",
                points_path,
                "--out_blend",
                str(imprint_blend),
                "--curve_name",
                "SeamCurve",
                "--preview_name",
                "SeamPreviewEdges",
                "--preview_in_front",
                "1",
                "--quit",
            ],
            log_path=imprint_log,
        )

        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.PROCESSING.value,
                "progress": "80.0",
            },
        )

        result_files = [
            {
                "preview_image_url": "",
                "type": "blend",
                "url": f"/api/v1/seams/files/{task_id}/{imprint_blend.name}",
            },
            {
                "preview_image_url": "",
                "type": "log",
                "url": f"/api/v1/seams/files/{task_id}/{imprint_log.name}",
            },
        ]

        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.COMPLETED.value,
                "progress": "100.0",
                "result_files": json.dumps(result_files),
            },
        )

        return {"status": "completed"}

    except Exception as e:
        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.FAILED.value,
                "error": str(e),
            },
        )
        raise

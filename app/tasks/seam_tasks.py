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
    try:
        model_path = str(payload["model_path"])
        points_path = str(payload["points_path"])
        axis = str(payload.get("axis", "three_to_blender_a"))
        points_origin = str(payload.get("points_origin", "model_bbox_center"))
        do_imprint = int(payload.get("do_imprint", 1))

        results_root = Path(_resolve_path_relative_to_atticus(settings.RESULTS_PATH))
        out_dir = results_root / str(task_id) / "seams"
        out_dir.mkdir(parents=True, exist_ok=True)

        blender_exe = _resolve_path_relative_to_atticus(settings.BLENDER_PATH)
        scripts_dir = Path(_resolve_path_relative_to_atticus(settings.BLENDER_SCRIPTS_PATH))

        snap_script = scripts_dir / "snap_points_and_draw_curve.py"
        imprint_script = scripts_dir / "imprint_seams_from_points.py"

        if not Path(model_path).exists():
            raise FileNotFoundError(model_path)
        if not Path(points_path).exists():
            raise FileNotFoundError(points_path)
        if not snap_script.exists():
            raise FileNotFoundError(str(snap_script))
        if do_imprint != 0 and not imprint_script.exists():
            raise FileNotFoundError(str(imprint_script))

        snapped_json = out_dir / "snapped_points.json"
        curve_blend = out_dir / "curve_snapped.blend"
        snap_log = out_dir / "blender_snap.log"

        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.PROCESSING.value,
                "progress": "10.0",
            },
        )

        _run_blender(
            blender_exe=blender_exe,
            script_path=str(snap_script),
            argv=[
                "--input_model",
                model_path,
                "--points_json",
                points_path,
                "--out_points_json",
                str(snapped_json),
                "--out_blend",
                str(curve_blend),
                "--axis",
                axis,
                "--points_origin",
                points_origin,
                "--quit",
            ],
            log_path=snap_log,
        )

        redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": TaskStatus.PROCESSING.value,
                "progress": "50.0",
            },
        )

        result_files = [
            {
                "preview_image_url": "",
                "type": "blend",
                "url": f"/api/v1/seams/files/{task_id}/{curve_blend.name}",
            },
            {
                "preview_image_url": "",
                "type": "json",
                "url": f"/api/v1/seams/files/{task_id}/{snapped_json.name}",
            },
            {
                "preview_image_url": "",
                "type": "log",
                "url": f"/api/v1/seams/files/{task_id}/{snap_log.name}",
            },
        ]

        if do_imprint != 0:
            imprint_blend = out_dir / "seam_imprinted_preview.blend"
            imprint_log = out_dir / "blender_imprint.log"

            _run_blender(
                blender_exe=blender_exe,
                script_path=str(imprint_script),
                argv=[
                    "--input_model",
                    model_path,
                    "--points_json",
                    str(snapped_json),
                    "--out_blend",
                    str(imprint_blend),
                    "--curve_name",
                    "SeamCurve_Imprint",
                    "--preview_name",
                    "SeamPreviewEdges",
                    "--preview_in_front",
                    "1",
                    "--quit",
                ],
                log_path=imprint_log,
            )

            result_files.insert(
                0,
                {
                    "preview_image_url": "",
                    "type": "blend",
                    "url": f"/api/v1/seams/files/{task_id}/{imprint_blend.name}",
                },
            )

            result_files.insert(
                1,
                {
                    "preview_image_url": "",
                    "type": "log",
                    "url": f"/api/v1/seams/files/{task_id}/{imprint_log.name}",
                },
            )

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

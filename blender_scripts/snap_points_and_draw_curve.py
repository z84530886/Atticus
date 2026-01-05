import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input_model", required=True)
    parser.add_argument("--points_json", required=True)
    parser.add_argument("--out_points_json", required=True)
    parser.add_argument("--out_blend", default=None)
    parser.add_argument("--curve_name", default="SeamCurve_Snapped")
    parser.add_argument("--curve_bevel", type=float, default=0.002)
    parser.add_argument("--dist_threshold", type=float, default=0.001)
    parser.add_argument("--max_snap_dist", type=float, default=1000.0)
    parser.add_argument(
        "--axis",
        default="auto",
        choices=["auto", "identity", "three_to_blender_a", "three_to_blender_b"],
    )
    parser.add_argument(
        "--points_origin",
        default="auto",
        choices=["auto", "as_is", "model_bbox_center"],
    )
    parser.add_argument("--quit", action="store_true")
    return parser.parse_args(argv)


def _reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _import_obj(obj_path: str) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)

    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=obj_path)
    else:
        bpy.ops.import_scene.obj(filepath=obj_path)

    after = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in after if obj.type == "MESH"]
    if not meshes:
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh objects imported")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]

    if len(meshes) > 1:
        try:
            bpy.ops.object.join()
        except Exception:
            pass

    obj = bpy.context.view_layer.objects.active
    if obj is None or obj.type != "MESH":
        raise RuntimeError("Failed to get active mesh")
    return obj


def _import_gltf(path: str) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)

    bpy.ops.import_scene.gltf(filepath=path)

    after = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in after if obj.type == "MESH"]
    if not meshes:
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh objects imported")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]

    if len(meshes) > 1:
        try:
            bpy.ops.object.join()
        except Exception:
            pass

    obj = bpy.context.view_layer.objects.active
    if obj is None or obj.type != "MESH":
        raise RuntimeError("Failed to get active mesh")

    return obj


def _import_model(model_path: str) -> bpy.types.Object:
    p = Path(model_path)
    ext = p.suffix.lower()
    if ext in {".glb", ".gltf"}:
        return _import_gltf(str(p))
    return _import_obj(str(p))


def _load_points(points_json: Path) -> List[Vector]:
    data = json.loads(points_json.read_text(encoding="utf-8"))

    if isinstance(data, dict) and isinstance(data.get("points"), list):
        pts_raw = data["points"]
    elif isinstance(data, list):
        pts_raw = data
    else:
        raise ValueError("points_json must be either a list of {x,y,z} or an object with a 'points' list")

    pts: List[Vector] = []
    for item in pts_raw:
        if not isinstance(item, dict):
            continue
        x = item.get("x")
        y = item.get("y")
        z = item.get("z")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
            continue
        pts.append(Vector((float(x), float(y), float(z))))

    if len(pts) < 2:
        raise ValueError("Not enough points to create a curve (need >= 2)")

    return pts


def _create_curve(name: str, points: List[Vector], bevel: float) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = float(bevel)

    spline = curve.splines.new(type="POLY")
    spline.points.add(len(points) - 1)
    for i, p in enumerate(points):
        spline.points[i].co = (float(p.x), float(p.y), float(p.z), 1.0)

    obj_curve = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj_curve)
    return obj_curve


def _stats(values: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not values:
        return None, None, None
    mn = min(values)
    mx = max(values)
    mean = sum(values) / float(len(values))
    return float(mn), float(mx), float(mean)


Transform = Callable[[Vector], Vector]


def _tf_identity(p: Vector) -> Vector:
    return Vector((float(p.x), float(p.y), float(p.z)))


def _tf_three_to_blender_a(p: Vector) -> Vector:
    return Vector((float(p.x), float(-p.z), float(p.y)))


def _tf_three_to_blender_b(p: Vector) -> Vector:
    return Vector((float(p.x), float(p.z), float(-p.y)))


def _get_bbox_center_world(obj: bpy.types.Object) -> Vector:
    me = obj.data
    if not me.vertices:
        return Vector((0.0, 0.0, 0.0))

    min_v = Vector((float("inf"), float("inf"), float("inf")))
    max_v = Vector((float("-inf"), float("-inf"), float("-inf")))
    mw = obj.matrix_world
    for v in me.vertices:
        p = mw @ v.co
        min_v.x = min(min_v.x, float(p.x))
        min_v.y = min(min_v.y, float(p.y))
        min_v.z = min(min_v.z, float(p.z))
        max_v.x = max(max_v.x, float(p.x))
        max_v.y = max(max_v.y, float(p.y))
        max_v.z = max(max_v.z, float(p.z))

    return (min_v + max_v) * 0.5


def _apply_origin(points: List[Vector], *, origin_mode: str, bbox_center_world: Vector) -> List[Vector]:
    if origin_mode == "as_is":
        return [p.copy() for p in points]
    if origin_mode == "model_bbox_center":
        c = bbox_center_world
        return [p + c for p in points]
    raise ValueError(f"Unknown points_origin: {origin_mode}")


def _select_axis(axis: str) -> Tuple[str, Transform]:
    if axis == "identity":
        return "identity", _tf_identity
    if axis == "three_to_blender_a":
        return "three_to_blender_a", _tf_three_to_blender_a
    if axis == "three_to_blender_b":
        return "three_to_blender_b", _tf_three_to_blender_b
    raise ValueError(f"Unknown axis: {axis}")


def _eval_mean_dist(*, bvh: BVHTree, points: List[Vector], max_snap: float) -> Tuple[float, int]:
    dsum = 0.0
    cnt = 0
    missed = 0
    for p in points:
        hit = bvh.find_nearest(p, max_snap)
        if hit is None or hit[0] is None:
            missed += 1
            continue
        loc = hit[0]
        dsum += float((p - loc).length)
        cnt += 1
    mean = float(dsum / float(cnt)) if cnt > 0 else float("inf")
    return mean, int(missed)


def _auto_choose(
    *,
    bvh: BVHTree,
    raw_points: List[Vector],
    bbox_center_world: Vector,
    axis_arg: str,
    origin_arg: str,
    max_snap: float,
) -> Tuple[str, str, Transform, List[Vector], float, int]:
    axis_candidates = ["identity", "three_to_blender_a", "three_to_blender_b"] if axis_arg == "auto" else [axis_arg]
    origin_candidates = ["as_is", "model_bbox_center"] if origin_arg == "auto" else [origin_arg]

    best = {
        "axis": "identity",
        "origin": "as_is",
        "tf": _tf_identity,
        "points": [p.copy() for p in raw_points],
        "mean": float("inf"),
        "missed": 0,
    }

    for a in axis_candidates:
        a_name, tf = _select_axis(a)
        pts_tf = [tf(p) for p in raw_points]
        for o in origin_candidates:
            pts = _apply_origin(pts_tf, origin_mode=o, bbox_center_world=bbox_center_world)
            mean, missed = _eval_mean_dist(bvh=bvh, points=pts, max_snap=max_snap)
            if missed < int(best["missed"]) or (missed == int(best["missed"]) and mean < float(best["mean"])):
                best = {
                    "axis": a_name,
                    "origin": o,
                    "tf": tf,
                    "points": pts,
                    "mean": float(mean),
                    "missed": int(missed),
                }

    return (
        str(best["axis"]),
        str(best["origin"]),
        best["tf"],
        best["points"],
        float(best["mean"]),
        int(best["missed"]),
    )


def main() -> None:
    args = _parse_args()

    model_path = str(Path(args.input_model).resolve())
    points_path = Path(args.points_json).resolve()
    out_points_path = Path(args.out_points_json).resolve()

    if not Path(model_path).exists():
        raise FileNotFoundError(model_path)
    if not points_path.exists() or not points_path.is_file():
        raise FileNotFoundError(str(points_path))

    _reset_scene()
    obj = _import_model(model_path)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, depsgraph)

    raw_pts = _load_points(points_path)

    bbox_center_world = _get_bbox_center_world(obj)
    max_snap = float(args.max_snap_dist)

    chosen_axis, chosen_origin, _, pts, pre_mean, pre_missed = _auto_choose(
        bvh=bvh,
        raw_points=raw_pts,
        bbox_center_world=bbox_center_world,
        axis_arg=str(args.axis),
        origin_arg=str(args.points_origin),
        max_snap=max_snap,
    )

    dists_before: List[float] = []
    snapped: List[Vector] = []
    missed = 0

    for p in pts:
        hit = bvh.find_nearest(p, max_snap)
        if hit is None or hit[0] is None:
            missed += 1
            snapped.append(p.copy())
            continue
        loc = hit[0]
        d = float((p - loc).length)
        dists_before.append(d)
        snapped.append(loc.copy())

    thr = float(args.dist_threshold)
    over_thr = [d for d in dists_before if d > thr]

    mn, mx, mean = _stats(dists_before)
    print(
        "[SNAP] points=%d missed=%d dist_before_mean=%s dist_before_max=%s over_thr=%d thr=%g"
        % (
            int(len(pts)),
            int(missed),
            ("%.6g" % mean) if mean is not None else "None",
            ("%.6g" % mx) if mx is not None else "None",
            int(len(over_thr)),
            float(thr),
        )
    )

    out_payload = {
        "schema_version": 1,
        "input": {"model": str(model_path), "points_json": str(points_path)},
        "chosen": {
            "axis": str(chosen_axis),
            "points_origin": str(chosen_origin),
            "bbox_center_world": [float(bbox_center_world.x), float(bbox_center_world.y), float(bbox_center_world.z)],
            "mean_dist_before_eval": float(pre_mean),
            "missed_eval": int(pre_missed),
        },
        "snap": {
            "max_snap_dist": float(max_snap),
            "dist_threshold": float(thr),
            "missed": int(missed),
            "stats_before": {"min": mn, "max": mx, "mean": mean, "count": int(len(dists_before))},
            "over_threshold": {"count": int(len(over_thr))},
        },
        "points": [{"x": float(p.x), "y": float(p.y), "z": float(p.z)} for p in snapped],
    }

    out_points_path.parent.mkdir(parents=True, exist_ok=True)
    out_points_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote snapped points: {out_points_path}")

    _create_curve(str(args.curve_name), snapped, float(args.curve_bevel))

    if args.out_blend:
        out_blend = str(Path(args.out_blend).resolve())
        Path(out_blend).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out_blend)
        print(f"[OK] saved blend: {out_blend}")

    if bool(args.quit):
        bpy.ops.wm.quit_blender()


if __name__ == "__main__":
    main()

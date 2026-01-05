import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--input_model", required=True)
    p.add_argument("--points_json", required=True)
    p.add_argument("--out_blend", required=True)
    p.add_argument("--curve_name", default="SeamCurve_Imprint")
    p.add_argument("--curve_bevel", type=float, default=0.002)
    p.add_argument("--preview_name", default="SeamPreviewEdges")
    p.add_argument("--preview_in_front", type=int, default=1)
    p.add_argument("--vertex_snap_eps", type=float, default=1e-6)
    p.add_argument("--quit", action="store_true")
    return p.parse_args(argv)


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
        raise ValueError("Not enough points (need >=2)")

    return pts


def _create_curve(name: str, points_world: List[Vector], bevel: float) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = float(bevel)

    spline = curve.splines.new(type="POLY")
    spline.points.add(len(points_world) - 1)
    for i, p in enumerate(points_world):
        spline.points[i].co = (float(p.x), float(p.y), float(p.z), 1.0)

    obj_curve = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj_curve)
    return obj_curve


def _ensure_collection(name: str) -> bpy.types.Collection:
    existing = bpy.data.collections.get(name)
    if existing is not None:
        if bpy.context.scene.collection.children.get(existing.name) is None:
            bpy.context.scene.collection.children.link(existing)
        return existing

    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def _get_edge_seam_flag(e: bpy.types.MeshEdge) -> bool:
    if hasattr(e, "use_seam"):
        return bool(e.use_seam)
    if hasattr(e, "seam"):
        return bool(e.seam)
    return False


def _create_seam_preview_object(
    obj: bpy.types.Object,
    edge_indices: List[int],
    *,
    name: str,
    in_front: bool,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    me = obj.data
    verts = me.vertices
    edges = me.edges

    seam_edges = [int(ei) for ei in edge_indices if 0 <= int(ei) < len(edges)]
    if not seam_edges:
        raise RuntimeError("No seam edges to preview")

    used_verts: Dict[int, int] = {}
    new_verts: List[Tuple[float, float, float]] = []
    new_edges: List[Tuple[int, int]] = []

    for ei in seam_edges:
        e = edges[int(ei)]
        v0_old = int(e.vertices[0])
        v1_old = int(e.vertices[1])

        if v0_old not in used_verts:
            used_verts[v0_old] = len(new_verts)
            co = verts[v0_old].co
            new_verts.append((float(co.x), float(co.y), float(co.z)))
        if v1_old not in used_verts:
            used_verts[v1_old] = len(new_verts)
            co = verts[v1_old].co
            new_verts.append((float(co.x), float(co.y), float(co.z)))

        new_edges.append((int(used_verts[v0_old]), int(used_verts[v1_old])))

    preview_me = bpy.data.meshes.new(name)
    preview_me.from_pydata(new_verts, new_edges, [])
    preview_me.update()

    preview_obj = bpy.data.objects.new(name, preview_me)
    preview_obj.matrix_world = obj.matrix_world.copy()
    preview_obj.display_type = "WIRE"
    preview_obj.show_in_front = bool(in_front)
    collection.objects.link(preview_obj)
    return preview_obj


def _build_vertex_kd_local(bm: bmesh.types.BMesh) -> KDTree:
    bm.verts.ensure_lookup_table()
    kd = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert((float(v.co.x), float(v.co.y), float(v.co.z)), i)
    kd.balance()
    return kd


def _insert_vertex_on_face(bm: bmesh.types.BMesh, *, face: bmesh.types.BMFace, co: Vector) -> bmesh.types.BMVert:
    res = bmesh.ops.poke(bm, faces=[face])
    verts = res.get("verts") or []
    if not verts:
        raise RuntimeError("poke did not create a vertex")
    v = verts[0]
    v.co = co
    return v


def main() -> None:
    args = _parse_args()

    model_path = str(Path(args.input_model).resolve())
    points_path = Path(args.points_json).resolve()
    out_blend = str(Path(args.out_blend).resolve())

    if not Path(model_path).exists():
        raise FileNotFoundError(model_path)
    if not points_path.exists() or not points_path.is_file():
        raise FileNotFoundError(str(points_path))

    _reset_scene()
    obj = _import_model(model_path)

    pts_world = _load_points(points_path)
    _create_curve(str(args.curve_name), pts_world, float(args.curve_bevel))

    mw_inv = obj.matrix_world.inverted()
    pts_local = [mw_inv @ p for p in pts_world]

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    eps = float(args.vertex_snap_eps)

    point_verts: List[bmesh.types.BMVert] = []
    inserted = 0
    reused = 0
    missed = 0

    for p in pts_local:
        kd = _build_vertex_kd_local(bm)
        _, vidx, vdist = kd.find((float(p.x), float(p.y), float(p.z)))
        if vdist is not None and float(vdist) <= eps:
            bm.verts.ensure_lookup_table()
            point_verts.append(bm.verts[int(vidx)])
            reused += 1
            continue

        bm.faces.ensure_lookup_table()
        bvh = BVHTree.FromBMesh(bm)
        hit = bvh.find_nearest(p)
        if hit is None or hit[0] is None:
            missed += 1
            continue
        loc, _normal, face_index, _dist = hit
        if face_index is None:
            missed += 1
            continue

        bm.faces.ensure_lookup_table()
        if int(face_index) < 0 or int(face_index) >= len(bm.faces):
            missed += 1
            continue

        f = bm.faces[int(face_index)]
        v = _insert_vertex_on_face(bm, face=f, co=loc)
        point_verts.append(v)
        inserted += 1

    failed_connect = 0

    for i in range(len(point_verts) - 1):
        v0 = point_verts[i]
        v1 = point_verts[i + 1]
        if v0 == v1:
            continue
        try:
            res = bmesh.ops.connect_vert_pair(bm, verts=[v0, v1])
            edges = res.get("edges") or []
            if not edges:
                failed_connect += 1
                continue
            for e in edges:
                e.seam = True
        except Exception:
            failed_connect += 1

    bm.to_mesh(me)
    bm.free()
    me.update()

    seam_edge_indices: List[int] = []
    for i, e in enumerate(me.edges):
        if _get_edge_seam_flag(e):
            seam_edge_indices.append(int(i))

    if seam_edge_indices:
        preview_col = _ensure_collection("SeamPreview")
        _create_seam_preview_object(
            obj,
            seam_edge_indices,
            name=str(args.preview_name),
            in_front=int(args.preview_in_front) != 0,
            collection=preview_col,
        )

    print(
        "[IMPRINT] points=%d inserted=%d reused=%d missed=%d connect_failed=%d seam_edges=%d"
        % (
            int(len(pts_world)),
            int(inserted),
            int(reused),
            int(missed),
            int(failed_connect),
            int(len(seam_edge_indices)),
        )
    )

    Path(out_blend).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)

    if bool(args.quit):
        bpy.ops.wm.quit_blender()


if __name__ == "__main__":
    main()

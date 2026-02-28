#!/usr/bin/env python3
"""
URDF to USD Converter for Wuji Hand

Parses URDF and generates a USD file preserving:
- Link hierarchy (parent-child via joints)
- Mesh references (STL files)
- Joint transforms (origin xyz/rpy)
- Joint types and limits
- Basic materials (from URDF color)

Usage:
    python scripts/urdf_to_usd.py --side right
    python scripts/urdf_to_usd.py --side left
    python scripts/urdf_to_usd.py --side both
"""

import argparse
import math
import os
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade


def parse_xyz(text):
    """Parse 'x y z' string to tuple of floats."""
    return tuple(float(v) for v in text.strip().split())


def rpy_to_quaternion(roll, pitch, yaw):
    """Convert roll-pitch-yaw (XYZ extrinsic) to quaternion (w, x, y, z)."""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return (w, x, y, z)


def rpy_to_matrix(roll, pitch, yaw):
    """Convert RPY to 4x4 transformation matrix."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return Gf.Matrix4d(
        cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, 0,
        sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, 0,
        -sp, cp * sr, cp * cr, 0,
        0, 0, 0, 1,
    )


def read_stl_binary(filepath):
    """Read a binary STL file and return vertices and face indices."""
    with open(filepath, "rb") as f:
        header = f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]

        vertices = []
        face_vertex_counts = []
        face_vertex_indices = []

        vertex_map = {}
        vertex_idx = 0

        for i in range(num_triangles):
            normal = struct.unpack("<3f", f.read(12))
            v1 = struct.unpack("<3f", f.read(12))
            v2 = struct.unpack("<3f", f.read(12))
            v3 = struct.unpack("<3f", f.read(12))
            attr = struct.unpack("<H", f.read(2))

            tri_indices = []
            for v in (v1, v2, v3):
                # Round to avoid floating point key issues
                key = (round(v[0], 6), round(v[1], 6), round(v[2], 6))
                if key not in vertex_map:
                    vertex_map[key] = vertex_idx
                    vertices.append(Gf.Vec3f(*v))
                    vertex_idx += 1
                tri_indices.append(vertex_map[key])

            face_vertex_counts.append(3)
            face_vertex_indices.extend(tri_indices)

    return vertices, face_vertex_counts, face_vertex_indices


def create_material(stage, mat_path, color_rgba):
    """Create a simple USD Preview Surface material."""
    mat = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(color_rgba[0], color_rgba[1], color_rgba[2])
    )
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(color_rgba[3])
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def parse_urdf(urdf_path):
    """Parse URDF and return links, joints, and the root link name."""
    tree = ET.parse(urdf_path)
    root = tree.getroot()

    links = {}
    joints = []

    for link_elem in root.findall("link"):
        name = link_elem.get("name")
        link_data = {"name": name, "visual": None, "collision": None, "inertial": None}

        visual = link_elem.find("visual")
        if visual is not None:
            mesh_elem = visual.find("geometry/mesh")
            origin = visual.find("origin")
            material = visual.find("material")
            link_data["visual"] = {
                "mesh": mesh_elem.get("filename") if mesh_elem is not None else None,
                "origin_xyz": parse_xyz(origin.get("xyz", "0 0 0")) if origin is not None else (0, 0, 0),
                "origin_rpy": parse_xyz(origin.get("rpy", "0 0 0")) if origin is not None else (0, 0, 0),
            }
            if material is not None:
                color = material.find("color")
                if color is not None:
                    link_data["visual"]["color"] = parse_xyz(color.get("rgba", "0.5 0.5 0.5 1"))

        links[name] = link_data

    for joint_elem in root.findall("joint"):
        joint_data = {
            "name": joint_elem.get("name"),
            "type": joint_elem.get("type"),
            "parent": joint_elem.find("parent").get("link"),
            "child": joint_elem.find("child").get("link"),
        }
        origin = joint_elem.find("origin")
        if origin is not None:
            joint_data["origin_xyz"] = parse_xyz(origin.get("xyz", "0 0 0"))
            joint_data["origin_rpy"] = parse_xyz(origin.get("rpy", "0 0 0"))
        else:
            joint_data["origin_xyz"] = (0, 0, 0)
            joint_data["origin_rpy"] = (0, 0, 0)

        axis = joint_elem.find("axis")
        if axis is not None:
            joint_data["axis"] = parse_xyz(axis.get("xyz", "0 0 1"))
        else:
            joint_data["axis"] = (0, 0, 1)

        limit = joint_elem.find("limit")
        if limit is not None:
            joint_data["limit"] = {
                "lower": float(limit.get("lower", "0")),
                "upper": float(limit.get("upper", "0")),
                "effort": float(limit.get("effort", "0")),
                "velocity": float(limit.get("velocity", "0")),
            }

        joints.append(joint_data)

    # Find root link (not a child of any joint)
    child_links = {j["child"] for j in joints}
    root_link = None
    for name in links:
        if name not in child_links:
            root_link = name
            break

    return links, joints, root_link


def convert_urdf_to_usd(urdf_path, stl_dir, output_usd_path, side):
    """Convert a URDF file to USD format."""
    print(f"Converting {side} hand: {urdf_path} -> {output_usd_path}")

    links, joints, root_link = parse_urdf(urdf_path)
    print(f"  Links: {len(links)}, Joints: {len(joints)}, Root: {root_link}")

    # Create USD stage
    stage = Usd.Stage.CreateNew(str(output_usd_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    # Root xform
    root_path = f"/WujiHand_{side}"
    root_xform = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(root_xform.GetPrim())

    # Materials scope
    mat_scope = UsdGeom.Scope.Define(stage, f"{root_path}/Materials")

    # Create default material (URDF gray)
    default_color = (0.89804, 0.91765, 0.92941, 1.0)
    default_mat = create_material(stage, f"{root_path}/Materials/DefaultGray", default_color)

    # Build parent-child map
    parent_map = {}  # child_link -> (joint, parent_link)
    for j in joints:
        parent_map[j["child"]] = j

    # Create link prims with hierarchy
    link_prims = {}

    def create_link_prim(link_name, parent_usd_path):
        """Recursively create link prims following the joint chain."""
        link = links[link_name]

        if link_name in parent_map:
            joint = parent_map[link_name]
            # Joint xform (carries the transform)
            joint_path = f"{parent_usd_path}/{joint['name']}"
            joint_xform = UsdGeom.Xform.Define(stage, joint_path)

            # Apply joint transform
            xyz = joint["origin_xyz"]
            rpy = joint["origin_rpy"]
            xform_ops = joint_xform.AddTranslateOp()
            xform_ops.Set(Gf.Vec3d(*xyz))

            if any(abs(v) > 1e-10 for v in rpy):
                mat = rpy_to_matrix(*rpy)
                orient_op = joint_xform.AddOrientOp()
                rotation = mat.ExtractRotation()
                quat = rotation.GetQuat()
                orient_op.Set(Gf.Quatf(
                    float(quat.GetReal()),
                    float(quat.GetImaginary()[0]),
                    float(quat.GetImaginary()[1]),
                    float(quat.GetImaginary()[2]),
                ))

            # USD Physics joint
            if joint["type"] == "revolute":
                phys_joint = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
                axis_vec = joint["axis"]
                if abs(axis_vec[0]) > 0.5:
                    phys_joint.CreateAxisAttr("X")
                elif abs(axis_vec[1]) > 0.5:
                    phys_joint.CreateAxisAttr("Y")
                else:
                    phys_joint.CreateAxisAttr("Z")

                if "limit" in joint:
                    phys_joint.CreateLowerLimitAttr(math.degrees(joint["limit"]["lower"]))
                    phys_joint.CreateUpperLimitAttr(math.degrees(joint["limit"]["upper"]))

            link_usd_path = f"{joint_path}/{link_name}"
        else:
            # Root link - directly under root
            link_usd_path = f"{parent_usd_path}/{link_name}"

        link_xform = UsdGeom.Xform.Define(stage, link_usd_path)
        link_prims[link_name] = link_usd_path

        # Add visual mesh if present
        if link["visual"] and link["visual"]["mesh"]:
            mesh_filename = os.path.basename(link["visual"]["mesh"])
            stl_path = os.path.join(stl_dir, mesh_filename)

            if os.path.exists(stl_path):
                mesh_path = f"{link_usd_path}/visual"
                mesh_prim = UsdGeom.Mesh.Define(stage, mesh_path)

                vertices, face_counts, face_indices = read_stl_binary(stl_path)
                mesh_prim.CreatePointsAttr(vertices)
                mesh_prim.CreateFaceVertexCountsAttr(face_counts)
                mesh_prim.CreateFaceVertexIndicesAttr(face_indices)

                # Bind material
                UsdShade.MaterialBindingAPI.Apply(mesh_prim.GetPrim())
                UsdShade.MaterialBindingAPI(mesh_prim.GetPrim()).Bind(default_mat)

                print(f"    {link_name}: {len(vertices)} verts, {len(face_counts)} tris")
            else:
                print(f"    WARNING: STL not found: {stl_path}")

        # Recursively create children
        for j in joints:
            if j["parent"] == link_name:
                create_link_prim(j["child"], link_usd_path)

    # Start from root
    create_link_prim(root_link, root_path)

    stage.GetRootLayer().Save()
    print(f"  Saved: {output_usd_path}")
    print(f"  File size: {os.path.getsize(output_usd_path) / 1024:.1f} KB")

    return output_usd_path


def main():
    parser = argparse.ArgumentParser(description="Convert Wuji Hand URDF to USD")
    parser.add_argument("--side", choices=["right", "left", "both"], default="both",
                        help="Which hand to convert")
    parser.add_argument("--base-dir", default=None,
                        help="Base directory of wuji-hand-baseline repo")
    args = parser.parse_args()

    if args.base_dir:
        base_dir = Path(args.base_dir)
    else:
        base_dir = Path(__file__).parent.parent

    sides = ["right", "left"] if args.side == "both" else [args.side]

    for side in sides:
        urdf_path = base_dir / "urdf" / f"{side}.urdf"
        stl_dir = base_dir / "stl" / side
        output_path = base_dir / "usd" / side / f"wujihand_{side}.usda"

        if not urdf_path.exists():
            print(f"ERROR: URDF not found: {urdf_path}")
            sys.exit(1)

        if not stl_dir.exists():
            print(f"ERROR: STL directory not found: {stl_dir}")
            sys.exit(1)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        convert_urdf_to_usd(str(urdf_path), str(stl_dir), str(output_path), side)

    print("\nDone! USD files generated.")


if __name__ == "__main__":
    main()

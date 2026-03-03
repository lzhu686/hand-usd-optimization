#!/usr/bin/env python3
"""
Blender Python script: Build Wuji Hand with PBR materials and export USD.

Imports all STL parts, assembles per URDF hierarchy, UV unwraps,
creates black glove + red logo materials, exports as USD.

Usage:
    "C:\\Program Files\\Blender Foundation\\Blender 3.3\\blender.exe" ^
        --background --python scripts/blender_build_hand.py -- --side right

    Options after "--":
        --side right|left       Which hand to build (required)
        --base-dir PATH         Project root (default: script's parent.parent)
        --stl-dir PATH          Override STL directory
        --urdf PATH             Override URDF file path
        --output PATH           Override output USD path
        --save-blend            Also save .blend file for debugging
"""

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector


# =============================================================================
# URDF Parsing (adapted from urdf_to_usd.py)
# =============================================================================


def parse_xyz(text):
    return tuple(float(v) for v in text.strip().split())


def parse_urdf(urdf_path):
    tree = ET.parse(urdf_path)
    root = tree.getroot()

    links = {}
    joints = []

    for link_elem in root.findall("link"):
        name = link_elem.get("name")
        link_data = {"name": name, "visual": None}

        visual = link_elem.find("visual")
        if visual is not None:
            mesh_elem = visual.find("geometry/mesh")
            origin = visual.find("origin")
            link_data["visual"] = {
                "mesh": mesh_elem.get("filename") if mesh_elem is not None else None,
                "origin_xyz": (
                    parse_xyz(origin.get("xyz", "0 0 0"))
                    if origin is not None
                    else (0, 0, 0)
                ),
                "origin_rpy": (
                    parse_xyz(origin.get("rpy", "0 0 0"))
                    if origin is not None
                    else (0, 0, 0)
                ),
            }

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

    # Find root link
    child_links = {j["child"] for j in joints}
    root_link = None
    for name in links:
        if name not in child_links:
            root_link = name
            break

    return links, joints, root_link


# =============================================================================
# Transform Utilities
# =============================================================================


def rpy_to_blender_matrix(roll, pitch, yaw):
    """Convert URDF RPY (extrinsic XYZ) to Blender 4x4 rotation matrix."""
    # URDF: extrinsic XYZ = intrinsic ZYX
    # Compose: R = Rz(yaw) * Ry(pitch) * Rx(roll)
    rot_x = Matrix.Rotation(roll, 4, "X")
    rot_y = Matrix.Rotation(pitch, 4, "Y")
    rot_z = Matrix.Rotation(yaw, 4, "Z")
    return rot_z @ rot_y @ rot_x


# =============================================================================
# Scene Building
# =============================================================================


def clear_scene():
    """Remove all default objects and start clean."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def create_empty(name, collection):
    """Create an Empty object for joint/hierarchy."""
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.005
    collection.objects.link(empty)
    return empty


def import_stl(filepath, name, collection):
    """Import a single STL file, rename it, and move to target collection."""
    bpy.ops.import_mesh.stl(filepath=str(filepath))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "_mesh"

    # Move from default collection to our collection
    for col in obj.users_collection:
        col.objects.unlink(obj)
    collection.objects.link(obj)

    return obj


def build_hand(links, joints, root_link, stl_dir, side):
    """
    Build hand hierarchy in Blender scene.

    Hierarchy mirrors URDF:
      WujiHand_{side} (Empty)
        {side}_palm_link (Mesh)
          {side}_finger1_joint1 (Empty with transform)
            {side}_finger1_link1 (Mesh)
              {side}_finger1_joint2 (Empty with transform)
                {side}_finger1_link2 (Mesh) ...
    """
    # Create collection
    collection = bpy.data.collections.new(f"WujiHand_{side}")
    bpy.context.scene.collection.children.link(collection)

    # Root empty
    root_empty = create_empty(f"WujiHand_{side}", collection)

    # Build parent-child maps
    parent_map = {}  # child_link_name -> joint_data
    children_map = {}  # parent_link_name -> [joint_data, ...]
    for j in joints:
        parent_map[j["child"]] = j
        children_map.setdefault(j["parent"], []).append(j)

    link_objects = {}

    def create_link(link_name, parent_obj):
        link = links[link_name]

        if link_name in parent_map:
            # This link has a parent joint — create joint empty
            joint = parent_map[link_name]
            joint_empty = create_empty(joint["name"], collection)
            joint_empty.parent = parent_obj

            # Apply joint transform (translation + rotation)
            xyz = joint["origin_xyz"]
            rpy = joint["origin_rpy"]
            translation = Matrix.Translation(Vector(xyz))
            rotation = rpy_to_blender_matrix(*rpy)
            joint_empty.matrix_local = translation @ rotation

            mesh_parent = joint_empty
        else:
            # Root link — directly under root empty
            mesh_parent = parent_obj

        # Import STL mesh
        if link.get("visual") and link["visual"].get("mesh"):
            mesh_filename = os.path.basename(link["visual"]["mesh"])
            stl_path = Path(stl_dir) / mesh_filename

            if stl_path.exists():
                mesh_obj = import_stl(stl_path, link_name, collection)
                mesh_obj.parent = mesh_parent
                link_objects[link_name] = mesh_obj
                print(f"  Imported: {link_name} ({stl_path.stat().st_size // 1024} KB)")
            else:
                print(f"  WARNING: STL not found: {stl_path}")

        # Recurse to child links
        for child_joint in children_map.get(link_name, []):
            # Child mesh parents to the current link's mesh object if it exists,
            # otherwise to mesh_parent
            next_parent = link_objects.get(link_name, mesh_parent)
            create_link(child_joint["child"], next_parent)

    create_link(root_link, root_empty)
    return link_objects, collection


# =============================================================================
# UV Unwrapping
# =============================================================================


def uv_unwrap_all(link_objects, palm_link_name):
    """UV unwrap all meshes using Smart UV Project."""
    # Deselect everything first
    bpy.ops.object.select_all(action="DESELECT")

    for link_name, obj in link_objects.items():
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")

        if link_name == palm_link_name:
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(66),
                island_margin=0.02,
                correct_aspect=True,
                scale_to_bounds=False,
            )
        else:
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(66),
                island_margin=0.01,
                correct_aspect=True,
                scale_to_bounds=False,
            )

        bpy.ops.object.mode_set(mode="OBJECT")
        obj.select_set(False)

    print(f"  UV unwrap complete for {len(link_objects)} meshes")


# =============================================================================
# Material Creation
# =============================================================================


def create_black_glove_material():
    """Create near-black matte rubber/fabric material."""
    mat = bpy.data.materials.new(name="BlackGlove")
    mat.use_nodes = True
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)

    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (0, 0)
    principled.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1.0)
    principled.inputs["Roughness"].default_value = 0.7
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Specular"].default_value = 0.3

    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return mat


def create_palm_logo_material(logo_texture_path):
    """
    Create palm material: black base with red logo composited via alpha.

    If logo texture exists, blends it over black using MixRGB + alpha.
    Otherwise falls back to plain black.
    """
    mat = bpy.data.materials.new(name="PalmWithLogo")
    mat.use_nodes = True
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (600, 0)

    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (300, 0)
    principled.inputs["Roughness"].default_value = 0.7
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Specular"].default_value = 0.3

    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    logo_path = str(logo_texture_path)
    if os.path.exists(logo_path):
        # Load logo image
        img = bpy.data.images.load(logo_path)

        tex_image = nodes.new("ShaderNodeTexImage")
        tex_image.location = (-600, 0)
        tex_image.image = img

        # MixRGB: blend logo (Color2) over black base (Color1) using alpha
        mix = nodes.new("ShaderNodeMixRGB")
        mix.location = (0, 0)
        mix.blend_type = "MIX"
        mix.inputs["Color1"].default_value = (0.02, 0.02, 0.02, 1.0)

        links.new(tex_image.outputs["Color"], mix.inputs["Color2"])
        links.new(tex_image.outputs["Alpha"], mix.inputs["Fac"])
        links.new(mix.outputs["Color"], principled.inputs["Base Color"])

        print(f"  Logo texture loaded: {logo_path}")
    else:
        # No logo — plain black
        principled.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1.0)
        print(f"  WARNING: Logo not found at {logo_path}, using plain black")

    return mat


def assign_materials(link_objects, palm_link_name, mat_glove, mat_palm):
    """Assign materials to all mesh objects."""
    for link_name, obj in link_objects.items():
        obj.data.materials.clear()
        if link_name == palm_link_name:
            obj.data.materials.append(mat_palm)
        else:
            obj.data.materials.append(mat_glove)

    print(f"  Materials assigned: {len(link_objects)} objects")


# =============================================================================
# Export
# =============================================================================


def export_usd(output_path):
    """Export scene to USD format."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.usd_export(
        filepath=str(output_path),
        selected_objects_only=False,
        visible_objects_only=True,
        export_animation=False,
        export_hair=False,
        export_uvmaps=True,
        export_normals=True,
        export_materials=True,
        use_instancing=False,
        evaluation_mode="RENDER",
        generate_preview_surface=True,
        export_textures=True,
        overwrite_textures=True,
        relative_paths=True,
    )
    print(f"  USD exported: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")


def save_blend(output_path):
    """Save .blend file for debugging."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print(f"  Blend saved: {output_path}")


# =============================================================================
# Main
# =============================================================================


def main():
    # Parse args after "--" separator
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Build Wuji Hand USD in Blender")
    parser.add_argument(
        "--side", choices=["right", "left"], required=True, help="Which hand to build"
    )
    parser.add_argument("--base-dir", default=None, help="Project root directory")
    parser.add_argument("--stl-dir", default=None, help="Override STL directory")
    parser.add_argument("--urdf", default=None, help="Override URDF file path")
    parser.add_argument("--output", default=None, help="Override output USD path")
    parser.add_argument(
        "--save-blend", action="store_true", help="Also save .blend file"
    )
    args = parser.parse_args(argv)

    # Resolve paths
    if args.base_dir:
        base_dir = Path(args.base_dir)
    else:
        base_dir = Path(__file__).parent.parent  # hand-usd-optimization/

    # Default: look for STL/URDF in sibling wuji-hand-baseline repo
    baseline_dir = base_dir.parent / "wuji-hand-baseline"
    if not baseline_dir.exists():
        # Fall back to baseline/ within project
        baseline_dir = base_dir / "baseline"

    side = args.side
    urdf_path = Path(args.urdf) if args.urdf else baseline_dir / "urdf" / f"{side}.urdf"
    stl_dir = Path(args.stl_dir) if args.stl_dir else baseline_dir / "stl" / side
    output_usd = (
        Path(args.output)
        if args.output
        else base_dir / "usd" / side / f"wuji_hand_{side}.usdc"
    )
    logo_path = base_dir / "textures" / "logo" / "wuji_logo_placeholder.png"

    print(f"\n{'='*60}")
    print(f"  Wuji Hand USD Builder — {side} hand")
    print(f"{'='*60}")
    print(f"  URDF:   {urdf_path}")
    print(f"  STL:    {stl_dir}")
    print(f"  Logo:   {logo_path}")
    print(f"  Output: {output_usd}")
    print()

    # Validate inputs
    if not urdf_path.exists():
        print(f"ERROR: URDF not found: {urdf_path}")
        sys.exit(1)
    if not stl_dir.exists():
        print(f"ERROR: STL directory not found: {stl_dir}")
        sys.exit(1)

    # 1. Clear scene
    print("[1/6] Clearing scene...")
    clear_scene()

    # 2. Parse URDF
    print("[2/6] Parsing URDF...")
    links, joints, root_link = parse_urdf(str(urdf_path))
    print(f"  Links: {len(links)}, Joints: {len(joints)}, Root: {root_link}")

    # 3. Import STL and build hierarchy
    print("[3/6] Importing STL meshes and building hierarchy...")
    link_objects, collection = build_hand(links, joints, root_link, stl_dir, side)
    print(f"  Imported {len(link_objects)} mesh objects")

    # 4. UV unwrap
    print("[4/6] UV unwrapping all meshes...")
    palm_name = f"{side}_palm_link"
    uv_unwrap_all(link_objects, palm_name)

    # 5. Create and assign materials
    print("[5/6] Creating PBR materials...")
    mat_glove = create_black_glove_material()
    mat_palm = create_palm_logo_material(logo_path)
    assign_materials(link_objects, palm_name, mat_glove, mat_palm)

    # 6. Set scene metadata and export
    print("[6/6] Exporting USD...")
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    # Optionally save .blend for debugging
    if args.save_blend:
        blend_path = output_usd.parent / f"wuji_hand_{side}_debug.blend"
        save_blend(blend_path)

    export_usd(output_usd)

    print(f"\n{'='*60}")
    print(f"  BUILD COMPLETE: {side} hand")
    print(f"  Output: {output_usd}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

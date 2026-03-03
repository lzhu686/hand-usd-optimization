#!/usr/bin/env python3
"""
Post-process Blender-exported USD:
1. Add UsdPhysics joint properties from URDF
2. Verify scene hierarchy
3. Set stage metadata
4. Package deliverable to exports/

Usage:
    C:\\Python312\\python.exe scripts/post_process_usd.py --side right
    C:\\Python312\\python.exe scripts/post_process_usd.py --side both
"""

import argparse
import math
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, UsdUtils


# =============================================================================
# URDF Parsing (shared logic)
# =============================================================================


def parse_xyz(text):
    return tuple(float(v) for v in text.strip().split())


def parse_urdf_joints(urdf_path):
    """Parse URDF and return joints list with physics data."""
    tree = ET.parse(urdf_path)
    root = tree.getroot()

    links = {}
    for link_elem in root.findall("link"):
        links[link_elem.get("name")] = True

    joints = []
    for joint_elem in root.findall("joint"):
        joint_data = {
            "name": joint_elem.get("name"),
            "type": joint_elem.get("type"),
            "parent": joint_elem.find("parent").get("link"),
            "child": joint_elem.find("child").get("link"),
        }

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
        else:
            joint_data["limit"] = None

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
# USD Prim Search
# =============================================================================


def find_prim_by_name(stage, name):
    """Find a prim anywhere in the stage by its name."""
    for prim in stage.Traverse():
        if prim.GetName() == name:
            return prim
    return None


# =============================================================================
# Physics Joint Addition
# =============================================================================


def add_physics_joints(stage, joints):
    """Add UsdPhysics properties to joint prims."""
    added = 0
    for joint in joints:
        prim = find_prim_by_name(stage, joint["name"])
        if prim is None:
            print(f"    WARNING: Joint prim not found: {joint['name']}")
            continue

        if joint["type"] == "revolute":
            phys_joint = UsdPhysics.RevoluteJoint.Define(stage, prim.GetPath())

            axis_vec = joint["axis"]
            if abs(axis_vec[0]) > 0.5:
                phys_joint.CreateAxisAttr("X")
            elif abs(axis_vec[1]) > 0.5:
                phys_joint.CreateAxisAttr("Y")
            else:
                phys_joint.CreateAxisAttr("Z")

            if joint["limit"]:
                phys_joint.CreateLowerLimitAttr(
                    math.degrees(joint["limit"]["lower"])
                )
                phys_joint.CreateUpperLimitAttr(
                    math.degrees(joint["limit"]["upper"])
                )
                # Store effort/velocity as custom attributes
                prim.CreateAttribute("wuji:maxEffort", Sdf.ValueTypeNames.Double).Set(
                    joint["limit"]["effort"]
                )
                prim.CreateAttribute(
                    "wuji:maxVelocity", Sdf.ValueTypeNames.Double
                ).Set(joint["limit"]["velocity"])

            added += 1

        elif joint["type"] == "fixed":
            UsdPhysics.FixedJoint.Define(stage, prim.GetPath())
            added += 1

    print(f"    Physics joints added: {added}/{len(joints)}")
    return added


# =============================================================================
# Stage Metadata
# =============================================================================


def set_stage_metadata(stage):
    """Ensure correct stage-level metadata."""
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    print("    Stage metadata set: upAxis=Z, metersPerUnit=1.0")


# =============================================================================
# Verification
# =============================================================================


def verify_usd(stage, expected_links):
    """Run verification checks and print report."""
    mesh_count = 0
    material_count = 0
    has_uvs = 0
    shader_types = set()

    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            mesh_count += 1
            mesh = UsdGeom.Mesh(prim)
            # Check for UV primvar (Blender uses "st" or "UVMap")
            primvars = UsdGeom.PrimvarsAPI(prim)
            for pv in primvars.GetPrimvars():
                if pv.GetPrimvarName() in ("st", "UVMap"):
                    has_uvs += 1
                    break
        elif prim.IsA(UsdShade.Material):
            material_count += 1
        elif prim.IsA(UsdShade.Shader):
            shader = UsdShade.Shader(prim)
            id_attr = shader.GetIdAttr()
            if id_attr:
                shader_types.add(str(id_attr.Get()))

    up_axis = UsdGeom.GetStageUpAxis(stage)
    meters = UsdGeom.GetStageMetersPerUnit(stage)

    print(f"\n    === Verification Report ===")
    print(f"    Up Axis:          {up_axis}")
    print(f"    Meters Per Unit:  {meters}")
    print(f"    Meshes:           {mesh_count} (expected: {len(expected_links)})")
    print(f"    Meshes with UVs:  {has_uvs}")
    print(f"    Materials:        {material_count}")
    print(f"    Shader types:     {shader_types or 'none found'}")

    # Check for missing links
    found_links = set()
    for prim in stage.Traverse():
        found_links.add(prim.GetName())

    missing = [name for name in expected_links if name not in found_links]
    if missing:
        print(f"    MISSING links:    {missing}")

    non_preview = shader_types - {"UsdPreviewSurface"}
    if non_preview:
        print(f"    WARNING: Non-UsdPreviewSurface shaders: {non_preview}")

    ok = mesh_count >= len(expected_links) - 2 and has_uvs >= 1  # allow some tolerance
    print(f"    Status:           {'PASS' if ok else 'NEEDS REVIEW'}")
    print()
    return ok


# =============================================================================
# Packaging
# =============================================================================


def package_deliverable(usd_path, exports_dir, side):
    """Copy USD + textures to exports/ directory."""
    package_dir = exports_dir / f"wuji_hand_{side}"
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy main USD file
    dest_usd = package_dir / usd_path.name
    shutil.copy2(usd_path, dest_usd)

    # Copy textures directory if it exists next to the USD
    textures_src = usd_path.parent / "textures"
    if textures_src.exists() and any(textures_src.iterdir()):
        textures_dst = package_dir / "textures"
        if textures_dst.exists():
            shutil.rmtree(textures_dst)
        shutil.copytree(textures_src, textures_dst)
        print(f"    Textures copied to: {textures_dst}")

    print(f"    Packaged to: {package_dir}")
    return package_dir


def try_create_usdz(package_dir, side):
    """Attempt to create USDZ single-file archive."""
    usd_file = package_dir / f"wuji_hand_{side}.usdc"
    if not usd_file.exists():
        # Try .usda
        usd_file = package_dir / f"wuji_hand_{side}.usda"
    if not usd_file.exists():
        print(f"    USDZ: USD file not found in {package_dir}")
        return None

    usdz_file = package_dir.parent / f"wuji_hand_{side}.usdz"

    try:
        result = UsdUtils.CreateNewUsdzPackage(
            Sdf.AssetPath(str(usd_file)), str(usdz_file)
        )
        if result:
            size_kb = usdz_file.stat().st_size / 1024
            print(f"    USDZ created: {usdz_file} ({size_kb:.1f} KB)")
            return usdz_file
        else:
            print(f"    USDZ creation returned False")
    except Exception as e:
        print(f"    USDZ packaging not available: {e}")

    return None


# =============================================================================
# Main
# =============================================================================


def process_side(side, base_dir):
    """Process one hand side."""
    print(f"\n{'='*60}")
    print(f"  Post-processing: {side} hand")
    print(f"{'='*60}")

    # Resolve paths
    baseline_dir = base_dir.parent / "wuji-hand-baseline"
    if not baseline_dir.exists():
        baseline_dir = base_dir / "baseline"

    urdf_path = baseline_dir / "urdf" / f"{side}.urdf"
    usd_path = base_dir / "usd" / side / f"wuji_hand_{side}.usdc"
    exports_dir = base_dir / "exports"

    if not usd_path.exists():
        # Try .usda extension
        usd_path = usd_path.with_suffix(".usda")
    if not usd_path.exists():
        print(f"  ERROR: USD file not found. Run blender_build_hand.py first.")
        return False

    if not urdf_path.exists():
        print(f"  ERROR: URDF not found: {urdf_path}")
        return False

    print(f"  USD:  {usd_path}")
    print(f"  URDF: {urdf_path}")

    # Parse URDF for physics data
    print("\n  [1/4] Parsing URDF physics data...")
    links, joints, root_link = parse_urdf_joints(str(urdf_path))
    print(f"    Links: {len(links)}, Joints: {len(joints)}")

    # Open USD stage
    print("\n  [2/4] Adding physics joints to USD...")
    stage = Usd.Stage.Open(str(usd_path))
    if not stage:
        print(f"  ERROR: Could not open USD stage: {usd_path}")
        return False

    set_stage_metadata(stage)
    add_physics_joints(stage, joints)
    stage.GetRootLayer().Save()
    print(f"    USD saved: {usd_path}")

    # Verify
    print("\n  [3/4] Verifying USD structure...")
    verify_usd(stage, links)

    # Package
    print("  [4/4] Packaging deliverable...")
    package_dir = package_deliverable(usd_path, exports_dir, side)
    try_create_usdz(package_dir, side)

    print(f"\n  DONE: {side} hand")
    return True


def main():
    parser = argparse.ArgumentParser(description="Post-process Wuji Hand USD")
    parser.add_argument(
        "--side",
        choices=["right", "left", "both"],
        default="both",
        help="Which hand to process",
    )
    parser.add_argument("--base-dir", default=None, help="Project root directory")
    args = parser.parse_args()

    if args.base_dir:
        base_dir = Path(args.base_dir)
    else:
        base_dir = Path(__file__).parent.parent

    sides = ["right", "left"] if args.side == "both" else [args.side]
    results = {}
    for side in sides:
        results[side] = process_side(side, base_dir)

    print(f"\n{'='*60}")
    print("  Summary:")
    for side, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"    {side}: {status}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

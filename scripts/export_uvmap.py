#!/usr/bin/env python3
"""
export_uvmap.py
Export UV wireframe overlay on texture image for visual inspection.

Usage:
    python scripts/export_uvmap.py --usd usd/left.usdz --link palm_link --texture textures/logo/wuji_logo_placeholder.png --output uvmap.png
    python scripts/export_uvmap.py --usd usd_final/configuration/wujihand_base.usd --link left_palm_link --output uvmap_output.png
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from pxr import Usd, UsdGeom


def export_uvmap(usd_path: str, link_name: str, texture_path: str = None,
                 output_path: str = "uvmap.png", uv_primvar: str = None,
                 canvas_size: int = 1024):
    """Export UV wireframe overlaid on texture (or blank canvas)."""
    stage = Usd.Stage.Open(usd_path)

    # Find mesh matching link_name
    mesh_prim = None
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        if link_name in prim.GetPath().pathString:
            pvapi = UsdGeom.PrimvarsAPI(prim)
            # Try to find UV primvar
            for name in ([uv_primvar] if uv_primvar else ["st", "UVMap"]):
                pv = pvapi.GetPrimvar(name)
                if pv and pv.IsDefined() and pv.Get() and len(pv.Get()) > 0:
                    mesh_prim = prim
                    uv_primvar = name
                    break
            if mesh_prim:
                break

    if not mesh_prim:
        print(f"ERROR: No mesh with UV found for '{link_name}' in {usd_path}")
        return

    mesh = UsdGeom.Mesh(mesh_prim)
    fvc = np.array(mesh.GetFaceVertexCountsAttr().Get())
    uv = np.array(UsdGeom.PrimvarsAPI(mesh_prim).GetPrimvar(uv_primvar).Get())

    print(f"Mesh: {mesh_prim.GetPath()}")
    print(f"UV primvar: {uv_primvar}, items: {len(uv)}, faces: {len(fvc)}")

    # Create canvas
    if texture_path and Path(texture_path).exists():
        canvas = Image.open(texture_path).convert("RGBA")
        w, h = canvas.size
    else:
        w, h = canvas_size, canvas_size
        canvas = Image.new("RGBA", (w, h), (39, 39, 39, 255))

    draw = ImageDraw.Draw(canvas)

    # Draw UV wireframe
    idx = 0
    for count in fvc:
        face_uvs = []
        for i in range(count):
            if idx + i < len(uv):
                u, v = uv[idx + i]
                face_uvs.append((int(u * (w - 1)), int((1 - v) * (h - 1))))
        for i in range(len(face_uvs)):
            j = (i + 1) % len(face_uvs)
            draw.line([face_uvs[i], face_uvs[j]], fill=(0, 255, 0, 128), width=1)
        idx += count

    canvas.save(output_path)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Export UV wireframe overlay")
    parser.add_argument("--usd", required=True, help="USD/USDZ file path")
    parser.add_argument("--link", required=True, help="Link name to find (e.g. palm_link)")
    parser.add_argument("--texture", default=None, help="Texture image path (optional)")
    parser.add_argument("--output", default="uvmap.png", help="Output image path")
    parser.add_argument("--uv-primvar", default=None, help="UV primvar name (auto-detect if omitted)")
    parser.add_argument("--size", type=int, default=1024, help="Canvas size if no texture")
    args = parser.parse_args()

    export_uvmap(args.usd, args.link, args.texture, args.output, args.uv_primvar, args.size)


if __name__ == "__main__":
    main()

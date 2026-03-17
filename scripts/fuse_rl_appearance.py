#!/usr/bin/env python3
"""
Fuse RL training USD with visual appearance (BlackGlove + PalmWithLogo).

Strategy:
  1. Copy RL USD structure to fused/ output directory
  2. Modify base layer: replace materials + add UV to palm mesh
  3. Keep physics/robot/sensor layers untouched
  4. Copy logo texture

Materials are authored with dual context:
  - OmniPBR (MDL)        -> outputs:mdl:surface   (Isaac Sim / Omniverse)
  - UsdPreviewSurface     -> outputs:surface       (Blender / usdview / universal)

Input:  wujihand_usd_rl/ (extracted from wujihand_usd_filtered.zip)
Output: hand-usd-optimization/fused/{side}/

Usage:
  python fuse_rl_appearance.py --side right
  python fuse_rl_appearance.py --side left
  python fuse_rl_appearance.py --side both
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

try:
    from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt
except ImportError:
    print("ERROR: pxr (usd-core) not available. Use Python 3.12 with usd-core.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_paths(side: str) -> dict:
    """Return all relevant paths for a given side."""
    base_dir = Path(__file__).resolve().parent.parent  # hand-usd-optimization/
    wuji_dir = base_dir.parent  # wuji/

    return {
        "rl_dir": wuji_dir / "wujihand_usd_rl",
        "our_usd": base_dir / "usd" / side / f"wuji_hand_{side}_debug.usdc",
        "texture_src": base_dir / "usd" / side / "textures" / "wuji_logo_placeholder.png",
        "fused_dir": base_dir / "fused" / side,
        "side": side,
    }


# ---------------------------------------------------------------------------
# File copy
# ---------------------------------------------------------------------------

def copy_rl_structure(paths: dict) -> Path:
    """Copy RL USD files to fused/ directory."""
    rl_dir = paths["rl_dir"]
    fused_dir = paths["fused_dir"]
    side = paths["side"]

    if fused_dir.exists():
        shutil.rmtree(fused_dir)
    fused_dir.mkdir(parents=True)
    (fused_dir / "configuration").mkdir()
    (fused_dir / "textures").mkdir()

    # Root USD
    rl_root = f"wujihand_{side}_filtered.usd"
    shutil.copy2(rl_dir / rl_root, fused_dir / rl_root)

    # 4 configuration layers
    for layer_type in ["base", "physics", "robot", "sensor"]:
        src = rl_dir / "configuration" / f"wujihand_{side}_filtered_{layer_type}.usd"
        dst = fused_dir / "configuration" / f"wujihand_{side}_filtered_{layer_type}.usd"
        shutil.copy2(src, dst)

    # Logo texture
    shutil.copy2(paths["texture_src"], fused_dir / "textures" / "wuji_logo_placeholder.png")

    print(f"  Copied RL structure to {fused_dir}")
    return fused_dir


# ---------------------------------------------------------------------------
# UV data extraction (from Blender export or JSON fallback)
# ---------------------------------------------------------------------------

def get_palm_uv_from_json(json_path: Path):
    """Load UV data from JSON file (Blender bpy API export, bypasses USD exporter bug)."""
    if not json_path.exists():
        return None, None, None

    with open(json_path, "r") as f:
        data = json.load(f)

    uvs = data.get("uvs", [])
    if not uvs:
        print(f"    WARNING: JSON has no UV data")
        return None, None, None

    uv_data = Vt.Vec2fArray([(u, v) for u, v in uvs])
    print(f"    UV source: {json_path.name} (JSON fallback)")
    print(f"    UV items: {len(uv_data)}, interpolation: faceVarying")
    print(f"    Mesh info: {data.get('vertices', '?')} verts, "
          f"{data.get('polygons', '?')} polys, {data.get('loops', '?')} loops")
    return uv_data, "faceVarying", None


def get_palm_uv_from_usd(stage, side: str):
    """Extract UV primvar from palm mesh in a Blender-exported USD stage."""
    target_name = f"{side}_palm_link_mesh"
    palm_prim = None

    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        if prim.GetName() == target_name:
            palm_prim = prim
            break
        path_str = prim.GetPath().pathString
        if (f"{side}_palm_link" in path_str
                and "finger" not in prim.GetName().lower()
                and "joint" not in prim.GetName().lower()):
            palm_prim = prim
            break

    if palm_prim is None:
        print(f"    WARNING: No palm mesh found in USD")
        return None, None, None

    uv_attr = palm_prim.GetAttribute("primvars:UVMap")
    if uv_attr and uv_attr.HasValue():
        uv_data = uv_attr.Get()
        if uv_data and len(uv_data) > 0:
            interp = uv_attr.GetMetadata("interpolation")
            indices_attr = palm_prim.GetAttribute("primvars:UVMap:indices")
            indices = indices_attr.Get() if indices_attr and indices_attr.HasValue() else None
            print(f"    UV source: {palm_prim.GetPath()}")
            print(f"    UV items: {len(uv_data)}, interpolation: {interp}")
            if indices:
                print(f"    UV indices: {len(indices)}")
            return uv_data, interp, indices

    print(f"    WARNING: No UV data at {palm_prim.GetPath()}")
    return None, None, None


def get_palm_uv_data(our_usd_path: Path, side: str):
    """Get palm UV data. Priority: JSON file > USD primvar > None (will auto-generate later)."""
    # JSON fallback first (works around Blender 3.3 USD export bug on left hand)
    json_path = our_usd_path.parent / "palm_uv_data.json"
    if json_path.exists():
        print(f"    Found JSON UV file: {json_path}")
        uv_data, interp, indices = get_palm_uv_from_json(json_path)
        if uv_data is not None:
            return uv_data, interp, indices

    # Standard USD extraction
    stage = Usd.Stage.Open(str(our_usd_path))
    return get_palm_uv_from_usd(stage, side)


# ---------------------------------------------------------------------------
# Material creation (dual context: OmniPBR + UsdPreviewSurface)
# ---------------------------------------------------------------------------

def _add_omnipbr_shader(stage, mat, mat_path: str, color, roughness: float,
                        metallic: float, texture_path: str = None):
    """Add OmniPBR (MDL) shader to material -> outputs:mdl:surface.
    Visible in Isaac Sim / Omniverse.
    """
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/OmniPBR")
    shader.CreateIdAttr("OmniPBR")
    shader.GetPrim().CreateAttribute(
        "info:implementationSource", Sdf.ValueTypeNames.Token).Set("sourceAsset")
    shader.GetPrim().CreateAttribute(
        "info:mdl:sourceAsset", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("OmniPBR.mdl"))
    shader.GetPrim().CreateAttribute(
        "info:mdl:sourceAsset:subIdentifier", Sdf.ValueTypeNames.Token).Set("OmniPBR")

    shader.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*color))
    shader.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(metallic)

    if texture_path:
        shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath(texture_path))

    mat.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")


def _add_preview_surface_shader(stage, mat, mat_path: str, color, roughness: float,
                                metallic: float, texture_path: str = None):
    """Add UsdPreviewSurface shader to material -> outputs:surface.
    Visible in Blender / usdview / any standard USD viewer.
    """
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")

    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)

    if texture_path:
        # Create texture reader node
        tex_reader = UsdShade.Shader.Define(stage, f"{mat_path}/DiffuseTexture")
        tex_reader.CreateIdAttr("UsdUVTexture")
        tex_reader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath(texture_path))
        tex_reader.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
        tex_reader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

        # Connect texture -> diffuseColor
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex_reader.ConnectableAPI(), "rgb")

        # ST coordinate reader
        st_reader = UsdShade.Shader.Define(stage, f"{mat_path}/STReader")
        st_reader.CreateIdAttr("UsdPrimvarReader_float2")
        st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("UVMap")
        st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

        tex_reader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            st_reader.ConnectableAPI(), "result")
    else:
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*color))

    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")


def create_dual_material(stage, mat_path: str, color, roughness=0.7, metallic=0.0,
                         texture_path: str = None):
    """Create a material with both OmniPBR and UsdPreviewSurface shaders.

    This ensures the material is visible in:
      - Isaac Sim / Omniverse (reads outputs:mdl:surface -> OmniPBR)
      - Blender / usdview    (reads outputs:surface -> UsdPreviewSurface)
    """
    mat = UsdShade.Material.Define(stage, mat_path)
    _add_omnipbr_shader(stage, mat, mat_path, color, roughness, metallic, texture_path)
    _add_preview_surface_shader(stage, mat, mat_path, color, roughness, metallic, texture_path)
    return mat


# ---------------------------------------------------------------------------
# UV injection into palm mesh
# ---------------------------------------------------------------------------

def inject_uv_to_palm(palm_mesh_prim, uv_data, uv_indices):
    """Inject UV primvar into a palm mesh prim, handling count mismatches."""
    mesh = UsdGeom.Mesh(palm_mesh_prim)
    fvi = mesh.GetFaceVertexIndicesAttr().Get()
    rl_fvi_count = len(fvi) if fvi else 0

    if uv_data is not None:
        our_uv_count = len(uv_data)
        print(f"    RL palm faceVertexIndices: {rl_fvi_count}")
        print(f"    Our UV data items: {our_uv_count}")

        pv_api = UsdGeom.PrimvarsAPI(palm_mesh_prim)
        uv_pv = pv_api.CreatePrimvar(
            "UVMap", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)

        if uv_indices is not None:
            uv_pv.Set(uv_data)
            uv_pv.SetIndices(Vt.IntArray(uv_indices))
            print(f"    Injected indexed UV: {len(uv_data)} coords, {len(uv_indices)} indices")
        elif our_uv_count == rl_fvi_count:
            uv_pv.Set(uv_data)
            print(f"    Injected UV data: {our_uv_count} items (exact match)")
        else:
            print(f"    WARNING: UV count mismatch ({our_uv_count} vs {rl_fvi_count})")
            uv_list = list(uv_data)
            if our_uv_count < rl_fvi_count:
                uv_list.extend([(0.0, 0.0)] * (rl_fvi_count - our_uv_count))
                print(f"    Padded UV: {our_uv_count} -> {rl_fvi_count}")
            else:
                uv_list = uv_list[:rl_fvi_count]
                print(f"    Truncated UV: {our_uv_count} -> {rl_fvi_count}")
            uv_pv.Set(Vt.Vec2fArray(uv_list))
        return

    # No UV from our version — generate planar projection as fallback
    print(f"    No UV from our version, generating planar projection...")
    points = mesh.GetPointsAttr().Get()
    if not points or rl_fvi_count == 0:
        return

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x if max_x != min_x else 1.0
    range_y = max_y - min_y if max_y != min_y else 1.0

    uv_list = []
    for idx in fvi:
        p = points[idx]
        uv_list.append(((p[0] - min_x) / range_x, (p[1] - min_y) / range_y))

    pv_api = UsdGeom.PrimvarsAPI(palm_mesh_prim)
    uv_pv = pv_api.CreatePrimvar(
        "UVMap", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
    uv_pv.Set(Vt.Vec2fArray(uv_list))
    print(f"    Generated planar UV: {len(uv_list)} items from {len(points)} points")


# ---------------------------------------------------------------------------
# Material binding for visual meshes
# ---------------------------------------------------------------------------

def bind_visual_meshes(stage, side: str, black_mat_path: str, palm_mat_path: str):
    """Bind visual meshes to materials. Returns the palm mesh prim (if found).

    Also cleans up old material bindings on parent Xform prims under /visuals/
    which may use bindMaterialAs="strongerThanDescendants" and block child bindings.
    """
    prefix = side  # "right" or "left"
    black_mat = UsdShade.Material(stage.GetPrimAtPath(black_mat_path))
    palm_mat = UsdShade.Material(stage.GetPrimAtPath(palm_mat_path))

    # Step 1: Clean up old bindings on ALL prims under /visuals/ scope
    # The RL USD has strongerThanDescendants bindings on Xform prims that override
    # any child mesh bindings. We must rebind these to our new materials.
    visuals_prim = stage.GetPrimAtPath("/visuals")
    old_bindings_fixed = 0
    if visuals_prim:
        for prim in Usd.PrimRange(visuals_prim):
            binding_rel = prim.GetRelationship("material:binding")
            if binding_rel and binding_rel.HasAuthoredTargets():
                path_str = prim.GetPath().pathString
                is_palm = f"{prefix}_palm_link" in path_str
                target_mat = palm_mat if is_palm else black_mat
                binding_api = UsdShade.MaterialBindingAPI.Apply(prim)
                binding_api.Bind(target_mat)
                old_bindings_fixed += 1
    if old_bindings_fixed:
        print(f"    Fixed old bindings in /visuals/: {old_bindings_fixed}")

    # Step 2: Bind material on actual Mesh prims
    rebound = 0
    palm_mesh_prim = None

    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        path_str = prim.GetPath().pathString
        if "/visuals/" not in path_str:
            continue

        is_palm = f"{prefix}_palm_link" in path_str
        binding_api = UsdShade.MaterialBindingAPI.Apply(prim)
        binding_api.Bind(palm_mat if is_palm else black_mat)
        rebound += 1

        if is_palm:
            palm_mesh_prim = prim
            print(f"    Palm mesh: {prim.GetPath()} -> PalmWithLogo")

    print(f"    Visual meshes rebound: {rebound}")
    return palm_mesh_prim


# ---------------------------------------------------------------------------
# Base layer modification (orchestrator)
# ---------------------------------------------------------------------------

def modify_base_layer(fused_dir: Path, side: str, uv_data, uv_interp, uv_indices):
    """Modify the base layer: replace materials, rebind meshes, inject UV."""
    base_path = fused_dir / "configuration" / f"wujihand_{side}_filtered_base.usd"
    stage = Usd.Stage.Open(str(base_path))

    hand_name = f"wujihand_{side}"
    looks_path = f"/{hand_name}/Looks"

    # Step 1: Remove old materials
    looks_prim = stage.GetPrimAtPath(looks_path)
    if looks_prim:
        for child in looks_prim.GetChildren():
            if child.GetTypeName() == "Material":
                print(f"    Removing old material: {child.GetName()}")
                stage.RemovePrim(child.GetPath())

    # Step 2: Create dual-context materials
    create_dual_material(
        stage, f"{looks_path}/BlackGlove",
        color=(0.02, 0.02, 0.02), roughness=0.7, metallic=0.0)
    print(f"    Created material: BlackGlove (OmniPBR + PreviewSurface)")

    create_dual_material(
        stage, f"{looks_path}/PalmWithLogo",
        color=(0.02, 0.02, 0.02), roughness=0.7, metallic=0.0,
        texture_path="../../textures/wuji_logo_placeholder.png")
    print(f"    Created material: PalmWithLogo (OmniPBR + PreviewSurface)")

    # Step 3: Disable instanceable on visual Xforms
    # instanceable=true creates USD instances whose material bindings
    # Blender cannot resolve across instance boundaries. Removing it
    # converts them to regular references which work in all DCC tools.
    # Isaac Sim still works fine without instanceable.
    deinstanced = 0
    for prim in stage.Traverse():
        if prim.GetName() in ("visuals", "collisions"):
            if prim.IsInstanceable():
                prim.SetInstanceable(False)
                deinstanced += 1
    if deinstanced:
        print(f"    Disabled instanceable on {deinstanced} prims")

    # Step 4: Rebind visual meshes
    palm_mesh_prim = bind_visual_meshes(
        stage, side,
        black_mat_path=f"{looks_path}/BlackGlove",
        palm_mat_path=f"{looks_path}/PalmWithLogo")

    # Step 5: Inject UV into palm mesh
    if palm_mesh_prim:
        inject_uv_to_palm(palm_mesh_prim, uv_data, uv_indices)

    stage.GetRootLayer().Save()
    print(f"    Saved: {base_path}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_fused(fused_dir: Path, side: str) -> bool:
    """Verify the fused USD loads correctly."""
    root_path = fused_dir / f"wujihand_{side}_filtered.usd"
    base_path = fused_dir / "configuration" / f"wujihand_{side}_filtered_base.usd"

    root_stage = Usd.Stage.Open(str(root_path))
    base_stage = Usd.Stage.Open(str(base_path))

    # Count meshes and materials from base layer
    meshes, materials = [], []
    for prim in base_stage.Traverse():
        t = prim.GetTypeName()
        if t == "Mesh":
            meshes.append(prim)
        elif t == "Material":
            materials.append(prim)

    # Count joints from root (composed with physics layer)
    joints = [p for p in root_stage.Traverse() if "Joint" in p.GetTypeName()]

    # Variant sets
    hand_name = f"wujihand_{side}"
    root_prim = root_stage.GetPrimAtPath(f"/{hand_name}")
    vsets = root_prim.GetVariantSets()
    vs_info = {n: vsets.GetVariantSet(n).GetVariantSelection() for n in vsets.GetNames()}

    # Top-level material names
    mat_names = [m.GetName() for m in materials
                 if m.GetPath().pathString.startswith(f"/{hand_name}/Looks/")
                 and m.GetPath().pathString.count("/") == 3]

    print(f"\n  === Verification: {side} ===")
    print(f"  Meshes: {len(meshes)} (expected: 78)")
    print(f"  Joints: {len(joints)} (expected: 26)")
    print(f"  Top materials: {mat_names}")
    print(f"  Variant sets: {vs_info}")

    # Check palm mesh UV and material binding
    prefix = side
    for m in meshes:
        path_str = m.GetPath().pathString
        if f"{prefix}_palm_link" in path_str and "/visuals/" in path_str:
            pv_api = UsdGeom.PrimvarsAPI(m)
            uv = pv_api.GetPrimvar("UVMap")
            if uv and uv.IsDefined():
                print(f"  Palm UV: {len(uv.Get())} items OK")
            else:
                print(f"  Palm UV: MISSING")

            binding = UsdShade.MaterialBindingAPI(m)
            mat, _ = binding.ComputeBoundMaterial()
            if mat:
                print(f"  Palm material: {mat.GetPath()} OK")
            break

    # Check dual shader outputs on BlackGlove
    bg_prim = base_stage.GetPrimAtPath(f"/{hand_name}/Looks/BlackGlove")
    if bg_prim:
        bg_mat = UsdShade.Material(bg_prim)
        has_mdl = bg_mat.GetSurfaceOutput("mdl").HasConnectedSource()
        has_surface = bg_mat.GetSurfaceOutput().HasConnectedSource()
        print(f"  Dual context: mdl={'OK' if has_mdl else 'MISSING'}, "
              f"surface={'OK' if has_surface else 'MISSING'}")

    tex = fused_dir / "textures" / "wuji_logo_placeholder.png"
    print(f"  Texture: {'exists' if tex.exists() else 'MISSING'}")

    ok = len(meshes) >= 50 and len(joints) >= 25 and "BlackGlove" in mat_names
    print(f"  Status: {'PASS' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def fuse_side(side: str) -> bool:
    """Run the full fusion pipeline for one side."""
    print(f"\n{'='*60}")
    print(f"  Fusing: {side} hand")
    print(f"{'='*60}")

    paths = get_paths(side)

    # Validate inputs
    for key, label in [("rl_dir", "RL directory"), ("our_usd", "Our USD"), ("texture_src", "Texture")]:
        if not paths[key].exists():
            print(f"  ERROR: {label} not found: {paths[key]}")
            return False

    # Step 1: Copy RL structure
    print(f"\n  [1/4] Copying RL structure...")
    fused_dir = copy_rl_structure(paths)

    # Step 2: Extract UV from our version
    print(f"\n  [2/4] Extracting UV data from our USD...")
    uv_data, uv_interp, uv_indices = get_palm_uv_data(paths["our_usd"], side)

    # Step 3: Modify base layer
    print(f"\n  [3/4] Modifying base layer...")
    modify_base_layer(fused_dir, side, uv_data, uv_interp, uv_indices)

    # Step 4: Verify
    print(f"\n  [4/4] Verifying fused output...")
    return verify_fused(fused_dir, side)


def main():
    parser = argparse.ArgumentParser(description="Fuse RL USD with visual appearance")
    parser.add_argument("--side", choices=["left", "right", "both"], default="both",
                        help="Which hand to process")
    args = parser.parse_args()

    sides = ["right", "left"] if args.side == "both" else [args.side]
    results = {}

    for side in sides:
        results[side] = fuse_side(side)

    print(f"\n{'='*60}")
    print(f"  Summary:")
    for side, ok in results.items():
        print(f"    {side}: {'OK' if ok else 'FAIL'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

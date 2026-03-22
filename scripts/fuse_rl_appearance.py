#!/usr/bin/env python3
"""
Fuse IsaacLab-generated USD with visual appearance from Blender exports.

Strategy:
  1. Copy IsaacLab raw USD structure to usd_final/ output directory
  2. Extract UV data from Blender debug USD (usd/{side}/) for textured links
  3. Transfer UV to IsaacLab mesh via KDTree nearest-neighbor matching
  4. Create dual-context materials (OmniPBR + UsdPreviewSurface)
  5. Bake composite textures (original centered on grey canvas for UV Clip workaround)
  6. Bind materials: textured dual material for links with textures, BlackGlove for rest

Materials are authored with dual context:
  - OmniPBR (MDL)        -> outputs:mdl:surface   (Isaac Sim / Omniverse)
  - UsdPreviewSurface     -> outputs:surface       (Blender / usdview / universal)

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

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

try:
    from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt
except ImportError:
    print("ERROR: pxr (usd-core) not available.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_paths(side: str) -> dict:
    """Return all relevant paths for a given side."""
    base_dir = Path(__file__).resolve().parent.parent  # hand-usd-optimization/

    return {
        "raw_usd_dir": base_dir / "usd_raw",
        "uv_source": base_dir / "usd" / side / f"wuji_hand_{side}_debug.usdc",
        "texture_src": base_dir / "textures" / "logo" / "wuji_logo_placeholder.png",
        "blender_texture_dir": base_dir / "usd" / side / "textures",
        "fused_dir": base_dir / "fused" / side,
        "side": side,
    }


# ---------------------------------------------------------------------------
# File copy
# ---------------------------------------------------------------------------

def copy_rl_structure(paths: dict) -> Path:
    """Copy IsaacLab raw USD files to usd_final/ directory."""
    raw_dir = paths["raw_usd_dir"]
    fused_dir = paths["fused_dir"]

    if fused_dir.exists():
        shutil.rmtree(fused_dir)
    shutil.copytree(raw_dir, fused_dir)

    # Ensure textures directory
    (fused_dir / "textures").mkdir(exist_ok=True)

    print(f"  Copied IsaacLab USD to {fused_dir}")
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


def get_palm_uv_from_usd(stage, side: str, link_name: str = None):
    """Extract UV primvar and mesh prim from a Blender-exported USD stage.

    Args:
        stage: Blender USD stage
        side: "left" or "right"
        link_name: specific link to find (e.g. "left_palm_link"). If None, uses palm.

    Returns:
        (uv_data, interpolation, indices, mesh_prim) or (None, None, None, None)
    """
    if link_name is None:
        link_name = f"{side}_palm_link"

    target_prim = None
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        path_str = prim.GetPath().pathString
        if link_name in path_str:
            target_prim = prim
            break

    if target_prim is None:
        return None, None, None, None

    # Try common UV primvar names
    for uv_name in ["primvars:UVMap", "primvars:st"]:
        uv_attr = target_prim.GetAttribute(uv_name)
        if uv_attr and uv_attr.HasValue():
            uv_data = uv_attr.Get()
            if uv_data and len(uv_data) > 0:
                interp = uv_attr.GetMetadata("interpolation")
                indices_attr = target_prim.GetAttribute(f"{uv_name}:indices")
                indices = indices_attr.Get() if indices_attr and indices_attr.HasValue() else None
                print(f"    UV source: {target_prim.GetPath()} ({uv_name})")
                print(f"    UV items: {len(uv_data)}, interpolation: {interp}")
                return uv_data, interp, indices, target_prim

    # No UV but mesh prim exists — return prim for KDTree vertex positions
    return None, None, None, target_prim


def get_palm_uv_data(our_usd_path: Path, side: str, link_name: str = None):
    """Get UV data for a link. Priority: JSON file > USD primvar > None.

    Returns:
        (uv_data, interpolation, indices, blender_mesh_prim)
    """
    if link_name is None:
        link_name = f"{side}_palm_link"

    # Standard USD extraction first (gets both UV and mesh prim)
    stage = Usd.Stage.Open(str(our_usd_path))
    uv_data, interp, indices, mesh_prim = get_palm_uv_from_usd(stage, side, link_name)
    if uv_data is not None:
        return uv_data, interp, indices, mesh_prim

    # JSON fallback (works around Blender 3.3 USD export bug on left hand)
    # mesh_prim may still be valid for KDTree vertex positions
    json_path = our_usd_path.parent / "palm_uv_data.json"
    if "palm_link" in link_name and json_path.exists():
        print(f"    Found JSON UV file: {json_path}")
        uv_data, interp, indices = get_palm_uv_from_json(json_path)
        if uv_data is not None:
            return uv_data, interp, indices, mesh_prim

    return None, None, None, mesh_prim


# ---------------------------------------------------------------------------
# Composite texture baking
# ---------------------------------------------------------------------------

def bake_composite_texture(
    src_texture: Path,
    target_texture_dir: Path,
    bg_color: tuple = (160, 160, 160),
) -> str:
    """Bake composite texture: original centered on 3x grey canvas.

    OmniPBR doesn't support UV Clip mode, so out-of-range UVs hit grey
    instead of repeating the logo. Returns the composite filename.
    """
    src = Image.open(src_texture)
    w, h = src.size
    canvas = Image.new("RGB", (w * 3, h * 3), bg_color)
    canvas.paste(src, (w, h))  # center 1/3

    composite_name = f"composite_{src_texture.name}"
    target_texture_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(target_texture_dir / composite_name, quality=95)
    print(f"    Composite texture: {composite_name} ({w * 3}x{h * 3})")
    return composite_name


def remap_uvs_for_composite(uvs: np.ndarray) -> np.ndarray:
    """Remap UV [0,1] -> [1/3, 2/3] for composite texture coordinates."""
    remapped = uvs / 3.0 + 1.0 / 3.0
    return np.clip(remapped, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Texture extraction from Blender USD
# ---------------------------------------------------------------------------



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
        # Clamp texture instead of repeat to avoid sampling bleed at UV island edges
        shader.CreateInput("texture_translate", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(0, 0))
        shader.CreateInput("texture_scale", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(1, 1))

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
        # Clamp texture: UV outside [0,1] returns edge pixel instead of wrapping
        tex_reader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex_reader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        tex_reader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

        # Connect texture -> diffuseColor
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex_reader.ConnectableAPI(), "rgb")

        # ST coordinate reader
        st_reader = UsdShade.Shader.Define(stage, f"{mat_path}/STReader")
        st_reader.CreateIdAttr("UsdPrimvarReader_float2")
        st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
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
# KDTree UV transfer
# ---------------------------------------------------------------------------

def inject_uv_to_palm(target_mesh_prim, source_mesh_prim, uv_data, uv_indices,
                       use_composite: bool = False):
    """Replace target mesh geometry with source mesh, preserving UV.

    Instead of transferring UV between different meshes (error-prone due to
    different triangulations), we replace the entire visual mesh geometry
    with the source mesh. This guarantees mesh + UV consistency.

    Args:
        target_mesh_prim: Target mesh prim in IsaacLab USD (will be overwritten)
        source_mesh_prim: Source mesh prim from KeyShot USDZ (with UV)
        uv_data: UV coordinate data from source
        uv_indices: UV index data (or None)
        use_composite: Whether to remap UVs (not needed for KeyShot textures)
    """
    target_mesh = UsdGeom.Mesh(target_mesh_prim)
    source_mesh = UsdGeom.Mesh(source_mesh_prim)

    # Read source geometry
    src_points = np.array(source_mesh.GetPointsAttr().Get())
    src_fvi = np.array(source_mesh.GetFaceVertexIndicesAttr().Get())
    src_fvc = np.array(source_mesh.GetFaceVertexCountsAttr().Get())

    # Coordinate alignment: auto-detect Y-axis negation (KeyShot Y-up vs IsaacLab Z-up)
    target_points = np.array(target_mesh.GetPointsAttr().Get())
    t_sample = target_points[::3]
    d_id = cKDTree(src_points[::3]).query(t_sample)[0].mean()
    d_ny = cKDTree(src_points[::3] * [1, -1, 1]).query(t_sample)[0].mean()
    if d_ny < d_id * 0.8:
        src_points = src_points * [1, -1, 1]
        print(f"    Coordinate fix: negated Y (dist {d_id:.6f} -> {d_ny:.6f})")

    # Replace geometry: points, faceVertexIndices, faceVertexCounts
    target_mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(src_points.astype(np.float32)))
    target_mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(src_fvi))
    target_mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(src_fvc))

    # Copy normals if available
    src_normals = source_mesh.GetNormalsAttr().Get()
    if src_normals and len(src_normals) > 0:
        normals = np.array(src_normals)
        if d_ny < d_id * 0.8:
            normals = normals * [1, -1, 1]
        target_mesh.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(normals.astype(np.float32)))
        target_mesh.SetNormalsInterpolation(source_mesh.GetNormalsInterpolation())

    # Write UV primvar
    uv_values = np.array(uv_data, dtype=np.float32)
    if uv_indices is not None:
        uv_idx = np.array(uv_indices)
        uv_values_expanded = uv_values[uv_idx]
    else:
        uv_values_expanded = uv_values


    if use_composite:
        uv_values_expanded = remap_uvs_for_composite(uv_values_expanded).astype(np.float32)

    primvar_api = UsdGeom.PrimvarsAPI(target_mesh_prim)
    uv_pv = primvar_api.CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, "faceVarying")
    uv_pv.Set(Vt.Vec2fArray.FromNumpy(uv_values_expanded.astype(np.float32)))

    print(f"    Mesh replaced: {len(target_points)} -> {len(src_points)} verts, "
          f"{len(src_fvc)} faces, {len(uv_values_expanded)} UVs")


# ---------------------------------------------------------------------------
# Material binding for visual meshes
# ---------------------------------------------------------------------------

def bind_visual_meshes(stage, side: str, black_mat_path: str,
                       textured_mat_paths: dict = None):
    """Bind visual meshes to materials. Returns dict of {link_name: mesh_prim}.

    Args:
        stage: Target USD stage
        side: "left" or "right"
        black_mat_path: Path to BlackGlove material
        textured_mat_paths: dict of {link_name: mat_path} for textured links

    Also cleans up old material bindings on parent Xform prims under /visuals/
    which may use bindMaterialAs="strongerThanDescendants" and block child bindings.
    """
    if textured_mat_paths is None:
        textured_mat_paths = {}

    prefix = side
    black_mat = UsdShade.Material(stage.GetPrimAtPath(black_mat_path))

    # Step 1: Rebind ALL prims with material:binding (visuals, meshes, any scope)
    # The IsaacLab USD has DefaultMaterial bindings on /meshes/ prims that are
    # referenced by /visuals/ prims. We must override these too, otherwise
    # USD composition rules let the referenced DefaultMaterial win.
    #
    # IMPORTANT: match textured links by "/visuals/{link_name}/" or "/meshes/{link_name}/"
    # NOT just "link_name in path", because palm_link appears as ancestor of all fingers.
    old_bindings_fixed = 0
    for prim in stage.Traverse():
        binding_rel = prim.GetRelationship("material:binding")
        if not (binding_rel and binding_rel.HasAuthoredTargets()):
            continue
        path_str = prim.GetPath().pathString
        # Skip colliders
        if "/colliders/" in path_str or "/collisions/" in path_str:
            continue
        # Determine which material to bind
        target_mat = black_mat
        for link_name, mat_path in textured_mat_paths.items():
            # Match only direct visuals/meshes of this link, not descendants
            if (f"/visuals/{link_name}/" in path_str or
                f"/meshes/{link_name}/" in path_str):
                target_mat = UsdShade.Material(stage.GetPrimAtPath(mat_path))
                break
        binding_api = UsdShade.MaterialBindingAPI.Apply(prim)
        binding_api.Bind(target_mat)
        old_bindings_fixed += 1
    print(f"    Rebound material on {old_bindings_fixed} prims (all scopes)")

    # Step 2: Collect textured mesh prims from /visuals/ for UV injection
    textured_mesh_prims = {}
    for prim in stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        path_str = prim.GetPath().pathString
        if "/visuals/" not in path_str:
            continue
        for link_name in textured_mat_paths:
            if f"/visuals/{link_name}/" in path_str:
                textured_mesh_prims[link_name] = prim
                print(f"    {link_name}: {prim.GetPath()} -> textured material")
                break

    return textured_mesh_prims


# ---------------------------------------------------------------------------
# Base layer modification (orchestrator)
# ---------------------------------------------------------------------------

def modify_base_layer(fused_dir: Path, side: str, blender_usd_path: Path,
                      texture_src: Path, blender_texture_dir: Path = None):
    """Modify the base layer: replace visual mesh + materials.

    Discovers textured links by checking material names in the source USD.
    Supports both KeyShot USDZ and Blender USDC as UV/mesh source.
    Texture priority: embedded in USDZ > blender texture dir > project textures/logo/.
    """
    # Find base USD (IsaacLab naming: wujihand_base.usd)
    base_candidates = list((fused_dir / "configuration").glob("*base*"))
    if not base_candidates:
        print("    ERROR: Base USD not found")
        return
    base_path = base_candidates[0]
    stage = Usd.Stage.Open(str(base_path))

    # Find Looks scope
    looks_path = None
    for prim in stage.Traverse():
        if prim.GetName() == "Looks" and prim.GetTypeName() == "Scope":
            path = prim.GetPath().pathString
            if path.count("/") > 1:
                looks_path = path
                break
    if looks_path is None:
        looks_path = "/Looks"
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)

    # Open KeyShot USDZ to extract UV data for textured links
    keyshot_stage = Usd.Stage.Open(str(blender_usd_path))
    textured_links = {}  # link_name -> {uv_data, uv_indices, keyshot_mesh_prim}
    target_texture_dir = fused_dir / "textures"

    # KeyShot USDZ has meshes like /lux_root/Default/{side}_palm_link/mesh
    # with UV primvar "st". Find all palm_link meshes with UV data.
    for prim in keyshot_stage.Traverse():
        if prim.GetTypeName() != "Mesh":
            continue
        path_str = prim.GetPath().pathString

        # Extract link name from path (e.g. "right_palm_link")
        link_name = None
        for part in path_str.split("/"):
            if "palm_link" in part:
                # Normalize to match target side (KeyShot may use "right_" for both)
                link_name = f"{side}_palm_link"
                break
        if not link_name or link_name in textured_links:
            continue

        # Extract UV from KeyShot mesh (primvar "st")
        pvapi = UsdGeom.PrimvarsAPI(prim)
        uv_pv = pvapi.GetPrimvar("st")
        if not (uv_pv and uv_pv.IsDefined()):
            continue
        uv_data = uv_pv.Get()
        if not uv_data or len(uv_data) == 0:
            continue

        uv_indices_attr = prim.GetAttribute("primvars:st:indices")
        uv_indices = uv_indices_attr.Get() if uv_indices_attr and uv_indices_attr.HasValue() else None

        print(f"    KeyShot UV: {prim.GetPath()} -> {len(uv_data)} items")

        textured_links[link_name] = {
            "uv_data": uv_data,
            "uv_indices": uv_indices,
            "keyshot_mesh_prim": prim,
        }

    print(f"    Textured links found: {list(textured_links.keys()) or 'none'}")

    # Step 1: Create BlackGlove material
    create_dual_material(
        stage, f"{looks_path}/BlackGlove",
        color=(0.02, 0.02, 0.02), roughness=0.7, metallic=0.0)
    print(f"    Created material: BlackGlove (OmniPBR + PreviewSurface)")

    # Step 2: Create textured materials.
    # Texture priority: USDZ embedded > Blender textures dir > project textures/logo/
    textured_mat_paths = {}
    for link_name in textured_links:
        tex_rel_path = None
        target_texture_dir.mkdir(parents=True, exist_ok=True)

        # Try 1: Blender textures directory (next to .usdc)
        if blender_texture_dir and blender_texture_dir.exists():
            for tex_file in blender_texture_dir.glob("*.png"):
                import shutil as _shutil
                _shutil.copy2(tex_file, target_texture_dir / tex_file.name)
                tex_rel_path = f"../textures/{tex_file.name}"
                print(f"    Texture from Blender: {tex_file.name}")
                break

        # Try 3: Project fallback
        if not tex_rel_path and texture_src.exists():
            import shutil as _shutil
            _shutil.copy2(texture_src, target_texture_dir / texture_src.name)
            tex_rel_path = f"../textures/{texture_src.name}"
            print(f"    Texture fallback: {texture_src.name}")

        mat_name = f"{link_name}_Material"
        mat_path = f"{looks_path}/{mat_name}"
        create_dual_material(
            stage, mat_path,
            color=(0.02, 0.02, 0.02), roughness=0.7, metallic=0.0,
            texture_path=tex_rel_path)
        textured_mat_paths[link_name] = mat_path
        print(f"    Created material: {mat_name} (OmniPBR + PreviewSurface)")

    # Step 3: Disable instanceable on visual Xforms
    deinstanced = 0
    for prim in stage.Traverse():
        if prim.GetName() in ("visuals", "collisions"):
            if prim.IsInstanceable():
                prim.SetInstanceable(False)
                deinstanced += 1
    if deinstanced:
        print(f"    Disabled instanceable on {deinstanced} prims")

    # Step 4: Rebind visual meshes
    textured_mesh_prims = bind_visual_meshes(
        stage, side,
        black_mat_path=f"{looks_path}/BlackGlove",
        textured_mat_paths=textured_mat_paths)

    # Step 5: Inject UV via KDTree for each textured link
    for link_name, mesh_prim in textured_mesh_prims.items():
        info = textured_links[link_name]
        print(f"    Injecting UV: {link_name}")
        inject_uv_to_palm(
            mesh_prim,
            info["keyshot_mesh_prim"],
            info["uv_data"],
            info["uv_indices"],
            use_composite=False)

    stage.GetRootLayer().Save()
    print(f"    Saved: {base_path}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_fused(fused_dir: Path, side: str) -> bool:
    """Verify the fused USD loads correctly."""
    # Find root USD
    root_candidates = list(fused_dir.glob("wujihand*.usd"))
    root_candidates = [f for f in root_candidates if "base" not in f.name
                       and "physics" not in f.name and "robot" not in f.name
                       and "sensor" not in f.name]
    if not root_candidates:
        print(f"  ERROR: No root USD found in {fused_dir}")
        return False
    root_path = root_candidates[0]

    base_candidates = list((fused_dir / "configuration").glob("*base*"))
    if not base_candidates:
        print(f"  ERROR: No base USD found")
        return False
    base_path = base_candidates[0]

    base_stage = Usd.Stage.Open(str(base_path))

    # Count meshes and materials from base layer
    meshes, materials = [], []
    for prim in base_stage.Traverse():
        t = prim.GetTypeName()
        if t == "Mesh":
            meshes.append(prim)
        elif t == "Material":
            materials.append(prim)

    # Material names at top level
    mat_names = [m.GetName() for m in materials]

    print(f"\n  === Verification: {side} ===")
    print(f"  Root USD: {root_path.name}")
    print(f"  Meshes: {len(meshes)}")
    print(f"  Materials: {[n for n in mat_names if n not in ('DefaultMaterial',)]}")

    # Check visual meshes with UV
    uv_count = 0
    for m in meshes:
        path_str = m.GetPath().pathString
        if "/visuals/" not in path_str:
            continue
        pv_api = UsdGeom.PrimvarsAPI(m)
        st = pv_api.GetPrimvar("st")
        if st and st.IsDefined():
            uv_count += 1

    print(f"  Visual meshes with UV: {uv_count}")

    # Check dual context on BlackGlove
    for m in materials:
        if m.GetName() == "BlackGlove":
            mat = UsdShade.Material(m)
            has_mdl = mat.GetSurfaceOutput("mdl").HasConnectedSource()
            has_surface = mat.GetSurfaceOutput().HasConnectedSource()
            print(f"  Dual context: mdl={'OK' if has_mdl else 'MISSING'}, "
                  f"surface={'OK' if has_surface else 'MISSING'}")
            break

    # Check textures
    tex_dir = fused_dir / "textures"
    tex_files = list(tex_dir.glob("*")) if tex_dir.exists() else []
    print(f"  Textures: {[f.name for f in tex_files] or 'none'}")

    ok = len(meshes) >= 20 and "BlackGlove" in mat_names
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
    if not paths["raw_usd_dir"].exists():
        print(f"  ERROR: IsaacLab USD not found: {paths['raw_usd_dir']}")
        return False
    if not paths["uv_source"]:
        print(f"  ERROR: No UV source (USDZ or USDC) found")
        return False
    if not paths["uv_source"].exists():
        print(f"  ERROR: UV source not found: {paths['uv_source']}")
        return False

    print(f"  UV source: {paths['uv_source']}")

    # Step 1: Copy IsaacLab raw USD
    print(f"\n  [1/3] Copying IsaacLab USD structure...")
    fused_dir = copy_rl_structure(paths)

    # Step 2: Modify base layer (mesh replacement + materials)
    print(f"\n  [2/3] Modifying base layer (mesh replace + dual materials)...")
    modify_base_layer(
        fused_dir, side,
        paths["uv_source"],
        paths["texture_src"],
        paths.get("blender_texture_dir"))

    # Step 3: Verify
    print(f"\n  [3/3] Verifying fused output...")
    return verify_fused(fused_dir, side)


def main():
    parser = argparse.ArgumentParser(description="Fuse IsaacLab USD with visual appearance")
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

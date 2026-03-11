
import bpy
import os

print("\n" + "="*60)
print("  VERIFY USD IN BLENDER - DIAGNOSTIC MODE")
print("="*60)

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Clear orphan data
for block in [bpy.data.meshes, bpy.data.materials, bpy.data.images]:
    for item in block:
        if item.users == 0:
            block.remove(item)

# Import USD
usd_path = r"c:\Users\zhuliang\Desktop\wuji\hand-usd-optimization\exports\wuji_hand_right\wuji_hand_right.usdc"
print(f"\n[1] Importing USD: {usd_path}")
print(f"    File exists: {os.path.exists(usd_path)}")
bpy.ops.wm.usd_import(filepath=usd_path)
print(f"    Objects imported: {len(bpy.data.objects)}")

# Fix PalmWithLogo material - Blender USD import may not load UsdUVTexture
tex_path = os.path.join(os.path.dirname(usd_path), "textures", "wuji_logo_placeholder.png")
print(f"\n[2] Texture path: {tex_path}")
print(f"    Texture exists: {os.path.exists(tex_path)}")

# Diagnostic: list ALL materials
print(f"\n[3] All materials ({len(bpy.data.materials)}):")
for mat in bpy.data.materials:
    print(f"    - '{mat.name}' (users={mat.users}, use_nodes={mat.use_nodes})")
    if mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            print(f"      node: {n.type} ({n.name})")
        for l in mat.node_tree.links:
            print(f"      link: {l.from_node.name}.{l.from_socket.name} -> {l.to_node.name}.{l.to_socket.name}")

# Find and fix PalmWithLogo
print(f"\n[4] Fixing PalmWithLogo material...")
palm_found = False
for mat in bpy.data.materials:
    if "PalmWithLogo" in mat.name:
        palm_found = True
        print(f"    Found: '{mat.name}'")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Find or create Principled BSDF
        bsdf = None
        for n in nodes:
            if n.type == 'BSDF_PRINCIPLED':
                bsdf = n
                break
        if not bsdf:
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            print(f"    Created new Principled BSDF")
        else:
            print(f"    Found existing Principled BSDF: {bsdf.name}")

        # Create Image Texture node
        tex_node = nodes.new('ShaderNodeTexImage')
        try:
            img = bpy.data.images.load(tex_path)
            tex_node.image = img
            tex_node.location = (-300, 300)
            print(f"    Loaded texture: {img.name} ({img.size[0]}x{img.size[1]})")
        except Exception as e:
            print(f"    ERROR loading texture: {e}")

        # Connect to Base Color
        try:
            links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
            print(f"    Connected: Image Texture -> Base Color")
        except Exception as e:
            print(f"    ERROR connecting: {e}")

        # Set roughness
        bsdf.inputs['Roughness'].default_value = 0.7
        bsdf.inputs['Metallic'].default_value = 0.0

        # Verify final node setup
        print(f"    Final nodes:")
        for n in nodes:
            print(f"      {n.type} ({n.name})")
        print(f"    Final links:")
        for l in links:
            print(f"      {l.from_node.name}.{l.from_socket.name} -> {l.to_node.name}.{l.to_socket.name}")

        print(f"    FIXED: {mat.name}")

if not palm_found:
    print("    WARNING: No material with 'PalmWithLogo' found!")
    print("    Available materials:")
    for mat in bpy.data.materials:
        print(f"      - '{mat.name}'")

# Diagnostic: check which objects use which materials
print(f"\n[5] Object-Material assignments:")
for obj in bpy.data.objects:
    if obj.type == 'MESH' and 'palm' in obj.name.lower():
        print(f"    {obj.name}:")
        for i, slot in enumerate(obj.material_slots):
            if slot.material:
                print(f"      slot[{i}]: {slot.material.name}")
            else:
                print(f"      slot[{i}]: <empty>")

# Disable overlays extras (hides debug lines from wuji: attributes)
print(f"\n[6] Setting viewport...")
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.shading.type = 'MATERIAL'
                space.overlay.show_extras = False
                space.overlay.show_relationship_lines = False
                print(f"    Viewport: MATERIAL mode, extras OFF")
                break

print(f"\n{'='*60}")
print("  DONE - Check Blender console for diagnostic output above")
print(f"{'='*60}\n")

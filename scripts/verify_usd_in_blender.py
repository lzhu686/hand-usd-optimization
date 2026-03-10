
import bpy
import os

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import USD
usd_path = r"c:\Users\zhuliang\Desktop\wuji\hand-usd-optimization\exports\wuji_hand_right\wuji_hand_right.usdc"
bpy.ops.wm.usd_import(filepath=usd_path)

# Fix PalmWithLogo material - Blender USD import may not load UsdUVTexture
tex_path = os.path.join(os.path.dirname(usd_path), "textures", "wuji_logo_placeholder.png")

for mat in bpy.data.materials:
    if "PalmWithLogo" in mat.name:
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
        
        # Create Image Texture node
        tex_node = nodes.new('ShaderNodeTexImage')
        img = bpy.data.images.load(tex_path)
        tex_node.image = img
        tex_node.location = (-300, 300)
        
        # Connect to Base Color
        links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Set roughness
        bsdf.inputs['Roughness'].default_value = 0.7
        bsdf.inputs['Metallic'].default_value = 0.0
        
        print(f"Fixed material: {mat.name}")

# Set viewport to Material Preview
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.shading.type = 'MATERIAL'
                break

print("Done! Check viewport for result.")

# Wuji Hand USD Optimization - Knowledge Base

## Project Overview

**Goal**: Make the Wuji dexterous hand USD model visually match the real physical hand.

**Owner**: zhuliang
**Date Created**: 2026-02-28

---

## 1. Current State Analysis

### Source Pipeline
```
Fusion 360 --> SolidWorks --> STEP + STL (mechanical export)
```

### Available Assets
| Asset | Location | Format | Notes |
|-------|----------|--------|-------|
| URDF (left/right) | `wuji-hand-description/urdf/` | `.urdf` | Relative path & ROS path variants |
| MJCF (MuJoCo) | `wuji-hand-description/mjcf/` | `.xml` | For simulation |
| STL Meshes | `wuji-hand-description/meshes/{left,right}/` | `.STL` | 26 parts per hand (palm + 5 fingers x 5 links) |
| Right Palm (full) | `wuji/右手手掌.STL` + `wuji/右手手掌.STEP` | `.STL/.STEP` | High-detail palm reference |
| USD | **NOT YET CREATED** | `.usd/.usda` | Needs to be generated from URDF |

### URDF Structure (per hand)
- **right_palm_link** - 手掌 (palm)
- **right_finger1_** - 大拇指 (thumb): link1-4 + tip_link
- **right_finger2_** - 食指 (index): link1-4 + tip_link
- **right_finger3_** - 中指 (middle): link1-4 + tip_link
- **right_finger4_** - 无名指 (ring): link1-4 + tip_link
- **right_finger5_** - 小指 (pinky): link1-4 + tip_link
- **Joints**: 20 revolute + 5 fixed (tip joints)
- **Current material**: Uniform gray `rgba(0.898, 0.918, 0.929, 1)` - no textures

### Key Finding: No Textures Exist
- All mesh parts use a **single flat gray color**
- No UV mapping on any STL meshes
- No texture image files (PNG/JPG) in the repo
- The STEP/STL export from SolidWorks is purely geometric

---

## 2. Target Specification

### Visual Requirements (from leadership)
1. **Overall appearance**: Match the real physical hand as closely as possible
2. **Color scheme**:
   - **Primary body**: Pure black (手戴了手套后是纯黑的 - gloved hand is pure black)
   - **Logo area**: Red Wuji (舞肌) logo on the hand dorsum (back of hand)
3. **Logo**: Wuji/舞肌 branding on the palm back
4. **Texture quality**: Acceptable range from simple flat coloring to full PBR materials

### Visual Fidelity Tiers (from simple to complex)

| Tier | Approach | Effort | Fidelity |
|------|----------|--------|----------|
| **T1 - Simple Color** | Flat black + red logo decal in USD material | Low | Basic |
| **T2 - Basic PBR** | Metallic/roughness materials, logo as texture | Medium | Good |
| **T3 - UV + Texture** | Full UV unwrap, painted textures, logo | High | High |
| **T4 - 3D Scan + Cloth** | 3D scan for base, Blender/UE cloth sim for glove | Very High | Photorealistic |

### Recommended Approach: T1 → T2 (progressive)
- Start with T1: Apply black material to all parts, add logo as a decal/overlay
- Upgrade to T2: Add roughness/metallic maps for glove-like appearance
- T3/T4 require specialized artist/ID designer collaboration

---

## 3. Technical Pipeline

### URDF → USD Conversion
```
Option A: Isaac Sim (NVIDIA) - urdf_importer
Option B: usd_from_gltf + urdf2gltf toolchain
Option C: Blender + USD export plugin
Option D: Python USD API (pxr) manual conversion
```

**Recommended**: NVIDIA Isaac Sim's URDF importer or Blender pipeline

### USD Material Application
```python
# USD Material structure for black glove + red logo
UsdShade.Material("BlackGlove")
  ├── diffuseColor: (0.02, 0.02, 0.02)  # near-black
  ├── roughness: 0.7                     # matte rubber/fabric
  ├── metallic: 0.0                      # non-metallic
  └── opacity: 1.0

UsdShade.Material("WujiLogo")
  ├── diffuseColor: (0.8, 0.05, 0.05)   # red
  ├── roughness: 0.3                     # slightly glossy
  ├── metallic: 0.1
  └── (or) texture: logo_texture.png     # if using texture map
```

### Asset Path Issues (纹理问题大概率是asset引用路径问题)
- USD uses `@path/to/asset@` syntax for asset references
- Relative paths must be correct relative to the `.usd` file
- Common issue: paths break when moving USD files between directories
- Solution: Use `./` relative paths or `omni://` for Omniverse

---

## 4. Mesh Part Inventory

### Right Hand (26 parts)
| Part | File | Description |
|------|------|-------------|
| right_palm_link.STL | Palm body | Main palm structure |
| right_finger1_link1-4.STL | Thumb segments | 4 articulating segments |
| right_finger1_tip_link.STL | Thumb tip | Fixed tip |
| right_finger2_link1-4.STL | Index segments | 4 articulating segments |
| right_finger2_tip_link.STL | Index tip | Fixed tip |
| right_finger3_link1-4.STL | Middle segments | 4 articulating segments |
| right_finger3_tip_link.STL | Middle tip | Fixed tip |
| right_finger4_link1-4.STL | Ring segments | 4 articulating segments |
| right_finger4_tip_link.STL | Ring tip | Fixed tip |
| right_finger5_link1-4.STL | Pinky segments | 4 articulating segments |
| right_finger5_tip_link.STL | Pinky tip | Fixed tip |

### Left Hand
Mirror of right hand with `left_` prefix.

---

## 5. Tools & Software

| Tool | Purpose | Notes |
|------|---------|-------|
| **Blender** | UV unwrap, texture painting, cloth sim | 布料系统，可视化效果好 |
| **NVIDIA Isaac Sim** | URDF→USD conversion, simulation | Native USD support |
| **Unreal Engine** | Cloth system, high-fidelity rendering | 布料系统 |
| **SolidWorks** | Source CAD (current pipeline) | Exports STEP/STL |
| **Fusion 360** | Original design source | Upstream of SolidWorks |
| **Python USD (pxr)** | Programmatic USD manipulation | Material assignment, path fixing |

---

## 6. Quick-Win Alternatives (if no UV/texture artist available)

1. **Simple coloring in USD**: Assign black material to all parts, red to logo area - can be done programmatically
2. **Blender approach**: Import STL → assign materials → export USD - visual workflow
3. **3D scanning**: Scan the real hand to get base textures (需要三维扫描获取基础素材)
4. **ID designer**: Find someone with industrial design experience for faster turnaround

---

## 7. Key Contacts & References

- **GitHub Repo**: https://github.com/wuji-technology/wuji-hand-description
- **Support**: support@wuji.tech
- **Local Assets**: `C:\Users\zhuliang\Desktop\wuji\`

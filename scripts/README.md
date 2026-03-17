# Scripts — Hand USD Optimization

## Pipeline Overview

```
URDF + STL ──→ urdf_to_usd.py ──→ 基础 USD (无材质)
                                        │
generate_logo_texture.py ──→ Logo PNG    │
                                 │       ▼
                           blender_build_hand.py ──→ 带材质/UV 的 USD + .blend
                                                          │
                                                          ▼
                                                  post_process_usd.py ──→ exports/ (含物理参数)
                                                          │
                                                          ▼
                                                  verify_usd_in_blender.py (调试验证)

RL Training USD (wujihand_usd_rl/) ──┐
                                      ├──→ fuse_rl_appearance.py ──→ fused/ (RL物理 + 外观)
Blender UV + Logo Texture ───────────┘
```

## Python 环境

- **Python 3.12** (`C:\Python312\python.exe`) — 用于 pxr (usd-core) 相关脚本
- **Blender 3.3+** — 用于 `blender_build_hand.py` 和 `verify_usd_in_blender.py`

## 脚本说明

### 1. `urdf_to_usd.py` — URDF 转 USD

将 URDF 机器人描述文件转换为 USD 格式，保留运动链层级、STL 网格引用、关节变换和基础材质。

```bash
C:\Python312\python.exe scripts/urdf_to_usd.py --side right
C:\Python312\python.exe scripts/urdf_to_usd.py --side both
```

- **输入**: URDF 文件 + STL 目录
- **输出**: `usd/{side}/wuji_hand_{side}.usda`
- **依赖**: pxr (usd-core)

### 2. `generate_logo_texture.py` — 生成 Logo 纹理

生成 1024x1024 的 PNG 纹理，红色 "舞肌" + "WUJI" 文字，背景色匹配 BlackGlove 材质 (sRGB 39,39,39)。

```bash
C:\Python312\python.exe scripts/generate_logo_texture.py
```

- **输入**: 无（从零生成）
- **输出**: `textures/logo/wuji_logo_placeholder.png`
- **依赖**: Pillow

### 3. `blender_build_hand.py` — Blender 构建手模型

Blender 脚本：导入 STL 部件、UV 展开、创建 PBR 材质（黑体 + Logo）、导出 USD。

```bash
blender --background --python scripts/blender_build_hand.py -- --side right
blender --background --python scripts/blender_build_hand.py -- --side left --save-blend
```

- **输入**: URDF + STL 目录 + Logo 纹理
- **输出**: `usd/{side}/wuji_hand_{side}_debug.usdc` + 可选 `.blend` 文件
- **依赖**: Blender 3.3+
- **注意**: 左手 palm mesh 在 Blender 3.3 USD 导出中有 bug（空几何体），需用 JSON 方式导出 UV

### 4. `post_process_usd.py` — USD 后处理

从 Blender 导出的 debug USD 自动复制并后处理：添加物理关节参数、修复材质绑定、打包到 exports/。

```bash
C:\Python312\python.exe scripts/post_process_usd.py --side right
```

- **输入**: `usd/{side}/wuji_hand_{side}_debug.usdc`
- **输出**: `exports/wuji_hand_{side}/` + `.usdz`
- **依赖**: pxr (usd-core)

### 5. `verify_usd_in_blender.py` — Blender 验证脚本

在 Blender 中导入 USD 并诊断材质问题，自动修复 PalmWithLogo 纹理连接，切换到 Material Preview 模式。

```bash
blender --python scripts/verify_usd_in_blender.py
```

- **输入**: 硬编码路径（需按需修改脚本中的路径）
- **输出**: Blender 场景（用于目视检查）
- **依赖**: Blender 3.3+
- **注意**: 使用 UsdPreviewSurface，Blender 可直接渲染

### 6. `fuse_rl_appearance.py` — 融合 RL USD + 外观

将 RL 训练用 USD（含完整物理参数）与视觉外观（BlackGlove + PalmWithLogo）融合。保留 physics/robot/sensor 层不变，仅修改 base 层的材质和 UV。

```bash
C:\Python312\python.exe scripts/fuse_rl_appearance.py --side right
C:\Python312\python.exe scripts/fuse_rl_appearance.py --side left
C:\Python312\python.exe scripts/fuse_rl_appearance.py --side both
```

- **输入**: `wujihand_usd_rl/` (RL USD) + `usd/{side}/` (Blender UV 数据) + Logo 纹理
- **输出**: `fused/{side}/` (4 层 USD 结构 + 纹理)
- **依赖**: pxr (usd-core)
- **UV 来源优先级**:
  1. `usd/{side}/palm_uv_data.json` (Blender bpy 直接导出，绕过导出 bug)
  2. Blender 导出的 USDC 中的 primvar
  3. 自动生成 planar projection UV（兜底方案）
- **材质**: 双上下文 (OmniPBR + UsdPreviewSurface)，Isaac Sim 和 Blender 均可渲染

#### 代码模块结构

| 函数 | 职责 |
|------|------|
| `get_paths()` | 路径解析 |
| `copy_rl_structure()` | 复制 RL USD 文件到 fused/ |
| `get_palm_uv_from_json()` | 从 JSON 读取 UV (Blender bpy 导出) |
| `get_palm_uv_from_usd()` | 从 USD primvar 读取 UV |
| `get_palm_uv_data()` | UV 获取调度 (JSON > USD > None) |
| `_add_omnipbr_shader()` | 创建 OmniPBR MDL shader (Isaac Sim) |
| `_add_preview_surface_shader()` | 创建 UsdPreviewSurface shader (Blender) |
| `create_dual_material()` | 创建双上下文材质 |
| `inject_uv_to_palm()` | UV 注入 (含 mismatch 处理) |
| `bind_visual_meshes()` | 材质绑定到 visual mesh |
| `modify_base_layer()` | base 层修改调度器 |
| `verify_fused()` | 验证输出完整性 |
| `fuse_side()` | 单手融合 pipeline |

## 材质兼容性说明

USD 有两套材质体系，本项目同时支持：

| | OmniPBR (MDL) | UsdPreviewSurface |
|---|---|---|
| **标准** | NVIDIA 私有 MDL | OpenUSD 官方标准 |
| **可见于** | Isaac Sim / Omniverse | Blender / usdview / 所有 DCC |
| **Shader ID** | `OmniPBR` | `UsdPreviewSurface` |
| **输出接口** | `outputs:mdl:surface` | `outputs:surface` |

`fuse_rl_appearance.py` 在同一个 Material 下同时创建两个 Shader，实现跨平台兼容。
参考: [NVIDIA SimReady Material Best Practices](https://docs.omniverse.nvidia.com/simready/latest/simready-asset-creation/material-best-practices.html)

## USD 材质兼容性详解（互联网调研结果）

### 问题：为什么 OmniPBR 材质在 Blender 中不显示？

USD 的 Material prim 通过 `outputs:surface` 连接 Shader 来定义表面外观。但存在两套不同的输出通道：

| 输出通道 | Shader 类型 | 谁能读 |
| --- | --- | --- |
| `outputs:surface` | UsdPreviewSurface | Blender, usdview, Houdini, Maya, 所有标准 DCC |
| `outputs:mdl:surface` | OmniPBR (MDL) | 仅 Isaac Sim / Omniverse |

- **OmniPBR** 是 NVIDIA 基于 MDL (Material Definition Language) 的私有 shader，引用 `OmniPBR.mdl` 文件
- **UsdPreviewSurface** 是 [OpenUSD 官方标准](https://openusd.org/release/spec_usdpreviewsurface.html) 定义的通用 PBR shader
- Blender 的 USD 导入器只识别 `outputs:surface` → `UsdPreviewSurface`，完全忽略 `outputs:mdl:surface`
- 因此仅有 OmniPBR 的 USD 文件在 Blender 中显示为默认灰色

### 解决方案：双上下文材质 (Dual Context Material)

[NVIDIA SimReady 最佳实践](https://docs.omniverse.nvidia.com/simready/latest/simready-asset-creation/material-best-practices.html)
和 [Omniverse Connect SDK](https://docs.omniverse.nvidia.com/kit/docs/connect-sdk/1.0.0/api/group__materials.html)
推荐在同一个 Material 下同时创建两个 Shader：

```
Material "/Looks/BlackGlove"
├── Shader "OmniPBR"          → outputs:mdl:surface     (Isaac Sim 读这个)
└── Shader "PreviewSurface"   → outputs:surface          (Blender 读这个)
```

这样一份 USD 文件在 Isaac Sim 和 Blender 中都能正确渲染，无需维护两套文件。

`fuse_rl_appearance.py` 中的 `create_dual_material()` 函数实现了这个方案。

### 参考链接

- [UsdPreviewSurface Specification (OpenUSD 官方)](https://openusd.org/release/spec_usdpreviewsurface.html)
- [SimReady Material Best Practices (NVIDIA)](https://docs.omniverse.nvidia.com/simready/latest/simready-asset-creation/material-best-practices.html)
- [Isaac Sim OpenUSD Fundamentals](https://docs.isaacsim.omniverse.nvidia.com/5.0.0/omniverse_usd/open_usd.html)
- [Convert OmniPBR to UsdPreviewSurface (NVIDIA 论坛)](https://forums.developer.nvidia.com/t/convert-omnipbr-to-usd-preview-surface/269706)
- [UsdPreviewSurface 与行业标准 PBR 的对齐讨论 (GitHub Issue)](https://github.com/PixarAnimationStudios/OpenUSD/issues/2119)

## 已知问题

- Blender 3.3 USD 导出 bug：左手 palm mesh 导出为空几何体，需用 JSON 方式从 Blender bpy API 导出 UV
- UV count 可能与 RL mesh 的 faceVertexIndices 有微小差异（自动 padding 处理）

## 左手 Palm UV JSON 导出方法

当 Blender USD 导出 bug 导致左手 palm mesh 为空时，在 Blender Python Console 中运行：

```python
import json; obj = bpy.data.objects['left_palm_link']; mesh = obj.data; uv_layer = mesh.uv_layers['UVMap']; uvs = [(d.uv[0], d.uv[1]) for d in uv_layer.data]; json.dump({"uv_count": len(uvs), "vertices": len(mesh.vertices), "polygons": len(mesh.polygons), "loops": len(mesh.loops), "uvs": uvs}, open(r"C:\Users\zhuliang\Desktop\wuji\hand-usd-optimization\usd\left\palm_uv_data.json", "w")); print(f"Exported {len(uvs)} UV coords")
```

# Scripts

## Pipeline

```
                        ┌─────────────────────────────┐
                        │  blender_build_hand.py       │
URDF + STL ────────────→│  Blender: 导入 STL, UV 展开, │──→ usd/{side}/*.usdc + textures/
(baseline/)             │  PBR 材质, 导出 USD          │
                        └─────────────────────────────┘
                                      │
                                      │  palm_link mesh + UV + texture
                                      ▼
┌─────────────────────┐    ┌──────────────────────────┐
│  urdf_to_usd.py     │    │  fuse_rl_appearance.py   │
│  IsaacLab            │───→│  替换 visual mesh 几何体  │──→ fused/{side}/
│  UrdfConverter       │    │  注入 UV + 双材质         │    (Isaac Sim 就绪)
│  (物理/关节/碰撞)     │    │  (OmniPBR + PreviewSurface)│
└─────────────────────┘    └──────────────────────────┘
                                      │
                                      ▼
                             ┌─────────────────┐
                             │  run_sim.py      │
                             │  IsaacSim 验证    │
                             └─────────────────┘
```

## 环境

- **conda**: `env_isaaclab` (IsaacLab + pxr + scipy + PIL)
- **Blender 3.3+**: 用于 `blender_build_hand.py`

## 脚本说明

### `blender_build_hand.py` — Blender 构建手模型

导入全部 STL 部件、按 URDF 层级组装、Smart UV Project 展开、创建 PBR 材质（BlackGlove + PalmWithLogo）、导出 USD。

```bash
blender --background --python scripts/blender_build_hand.py -- --side right
blender --background --python scripts/blender_build_hand.py -- --side left --save-blend
```

- **输入**: `baseline/urdf/` + `baseline/stl/` + `textures/logo/`
- **输出**: `usd/{side}/wuji_hand_{side}_debug.usdc` + `textures/`

### `urdf_to_usd.py` — URDF → USD (IsaacLab)

通过 IsaacLab UrdfConverter 将 URDF 转换为带物理/关节/碰撞的 USD。

```bash
conda run -n env_isaaclab python scripts/urdf_to_usd.py --side both
```

- **输入**: `wuji-hand-description/urdf/` (同级仓库)
- **输出**: `usd_raw/` (中间产物, gitignored)

### `fuse_rl_appearance.py` — 融合物理 USD + Blender 外观

将 IsaacLab 生成的 USD（有物理，无纹理）与 Blender 导出的 USD（有 UV + 纹理，无物理）合并。用 Blender mesh 直接替换 visual mesh 几何体，保证 mesh 与 UV 一致性。

```bash
conda run -n env_isaaclab python scripts/fuse_rl_appearance.py --side both
```

- **输入**: `usd_raw/` + `usd/{side}/*.usdc`
- **输出**: `fused/{side}/` (4 层 USD + textures)
- **材质**: 双上下文 (OmniPBR + UsdPreviewSurface), Isaac Sim 和 Blender 均可渲染

### `run_sim.py` — IsaacSim 仿真验证

端到端 pipeline: URDF → raw USD → fuse → IsaacSim 加载 + 轨迹回放。

```bash
conda run -n env_isaaclab python scripts/run_sim.py --side left --regenerate
```

### `export_uvmap.py` — UV 调试工具

导出 UV 线框叠加在纹理上的 PNG, 用于检查 UV 映射正确性。

```bash
conda run -n env_isaaclab python scripts/export_uvmap.py \
    --usd fused/left/configuration/wujihand_base.usd \
    --link left_palm_link \
    --texture fused/left/textures/wuji_logo_placeholder.png \
    --output uvmap.png
```

## 材质兼容性

USD 有两套材质体系，本项目同时支持：

| | OmniPBR (MDL) | UsdPreviewSurface |
|---|---|---|
| **可见于** | Isaac Sim / Omniverse | Blender / usdview |
| **输出接口** | `outputs:mdl:surface` | `outputs:surface` |

`create_dual_material()` 在同一 Material 下创建两个 Shader, 实现跨平台渲染。

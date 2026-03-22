# Wuji Hand USD Optimization

让 Wuji 灵巧手 USD 模型视觉匹配真机：黑色手套 + 红色 Logo。

https://github.com/user-attachments/assets/2f58ad84-7ed6-46fe-94c1-b4148068bec3

## 快速使用

`fused/{left,right}/` 包含可直接加载的 Isaac Sim USD：

```python
# IsaacLab ArticulationCfg
from scripts.urdf_to_usd import get_wujihand_config
cfg = get_wujihand_config("left")
```

或直接引用 USD 路径：`fused/left/wujihand.usd`

## 目录结构

```
hand-usd-optimization/
├── fused/                        # ★ 最终产物 (Isaac Sim 就绪)
│   ├── left/
│   │   ├── wujihand.usd         #   入口 (sublayer 引用)
│   │   ├── configuration/
│   │   │   ├── wujihand_base.usd    # 几何 + 材质 (BlackGlove + PalmWithLogo)
│   │   │   ├── wujihand_physics.usd # 物理碰撞
│   │   │   ├── wujihand_robot.usd   # 关节/驱动
│   │   │   └── wujihand_sensor.usd  # 传感器
│   │   └── textures/
│   │       └── wuji_logo_placeholder.png
│   └── right/                   #   (同结构)
│
├── baseline/                    # 源素材 (wuji-hand-description v0.2.2)
│   ├── stl/{left,right}/       #   52 个 STL 网格 (26/手)
│   ├── urdf/                    #   left.urdf + right.urdf
│   └── step/right/              #   右手掌 STEP 源文件
│
├── textures/logo/               # 品牌素材
│   ├── wuji_logo_official.png
│   ├── wuji_logo_official_hires.png
│   └── wuji_logo_placeholder.png  # ★ pipeline 使用的纹理
│
├── scripts/                     # 构建工具 (详见 scripts/README.md)
│   ├── blender_build_hand.py    #   Blender: STL → UV → 材质 → USDC
│   ├── fuse_rl_appearance.py    #   ★ 核心: IsaacLab USD + Blender 外观 → fused/
│   ├── urdf_to_usd.py           #   URDF → USD (IsaacLab UrdfConverter)
│   ├── run_sim.py               #   IsaacSim 仿真验证
│   └── export_uvmap.py          #   UV 调试工具
│
├── data/wave.npy                # 仿真轨迹数据
└── docs/tech-spec-wh110-logo.md # 技术规格文档
```

## 构建流程

```bash
# 0. 环境
conda activate env_isaaclab

# 1. Blender 构建带 UV 的手模型 (需 Blender 3.3+)
blender --background --python scripts/blender_build_hand.py -- --side left
blender --background --python scripts/blender_build_hand.py -- --side right

# 2. 一键生成 (URDF→USD + 融合外观 + IsaacSim 验证)
python scripts/run_sim.py --side left --regenerate
```

或分步执行：
```bash
# 2a. URDF → raw USD (物理/关节)
python scripts/urdf_to_usd.py --side both

# 2b. 融合 Blender 外观 → fused/
python scripts/fuse_rl_appearance.py --side both

# 2c. IsaacSim 验证
python scripts/run_sim.py --side left
```

## 视觉规格

| 部件 | 外观 |
|------|------|
| 手指/手掌主体 | 纯黑哑光 (roughness 0.7, metallic 0) |
| 手掌 Logo | 红色 Wuji 标识 (纹理贴图) |

材质系统：OmniPBR (Isaac Sim) + UsdPreviewSurface (Blender) 双上下文，一份 USD 跨平台渲染。

## Logo 更换

1. 替换 `textures/logo/wuji_logo_placeholder.png` (1024x1024, RGB, 深灰底红字)
2. 重跑 Blender 构建 + fuse pipeline
3. 如 Logo 形状/位置大幅变化，需在 Blender 中手动调整 palm UV

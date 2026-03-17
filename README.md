# Wuji Hand USD Optimization

让 Wuji 灵巧手 USD 模型视觉匹配真机：黑色手套 + 红色 Logo。

## 目录结构

```
hand-usd-optimization/
├── README.md                          # 本文件
│
├── fused/                             # ★ 产品级 USD (Isaac Sim 就绪)
│   ├── right/
│   │   ├── wujihand_right_filtered.usd          # 右手入口 (sublayer 引用)
│   │   └── configuration/
│   │       ├── wujihand_right_filtered_base.usd     # 几何 + 材质 (BlackGlove + PalmWithLogo)
│   │       ├── wujihand_right_filtered_physics.usd  # 物理碰撞
│   │       ├── wujihand_right_filtered_robot.usd    # 关节/驱动
│   │       └── wujihand_right_filtered_sensor.usd   # 传感器
│   └── left/
│       ├── wujihand_left_filtered.usd           # 左手入口
│       └── configuration/
│           ├── wujihand_left_filtered_base.usd
│           ├── wujihand_left_filtered_physics.usd
│           ├── wujihand_left_filtered_robot.usd
│           └── wujihand_left_filtered_sensor.usd
│
├── baseline/                          # 源素材 (来自 wuji-hand-description v0.2.2)
│   ├── VERSION.md                     # 版本溯源
│   ├── stl/{left,right}/             # 52 个 STL 网格 (26/手)
│   ├── urdf/                          # left.urdf + right.urdf
│   └── step/right/                    # 右手掌 STEP + STL 源文件
│
├── textures/logo/                     # 品牌素材
│   ├── wuji_logo_official.png         # 官方 Logo (小尺寸)
│   ├── wuji_logo_official_hires.png   # 官方 Logo (高清)
│   └── wuji_logo_placeholder.png      # 开发用占位纹理
│
├── references/                        # 参考数据
│   └── left_palm_uv_data.json        # 左手掌 UV 坐标 (28188 coords, Blender 导出)
│
├── scripts/                           # 构建工具
│   ├── README.md                      # 脚本使用文档
│   ├── fuse_rl_appearance.py          # ★ 核心: RL USD + 外观材质融合
│   ├── blender_build_hand.py          # Blender 自动构建 (STL→材质→USD)
│   ├── generate_logo_texture.py       # Logo 纹理生成 (PIL)
│   ├── post_process_usd.py            # USD 后处理
│   ├── urdf_to_usd.py                 # URDF→USD 转换 (pxr)
│   ├── verify_usd_in_blender.py       # Blender 验证脚本
│   └── build_all.bat                  # 一键构建
│
└── docs/                              # 文档
    ├── tech-spec-wh110-logo.md        # 当前技术规格 (v2.3)
    └── archive/                       # 历史文档
```

## 关键资产对照

### 1. 客户 RL USD (原版，无 Logo)

位置: `../wujihand_usd_rl/`

```
wujihand_usd_rl/
├── wujihand_right_filtered.usd        # 右手入口
├── wujihand_left_filtered.usd         # 左手入口
└── configuration/                     # 4层 sublayer × 2手 = 8文件
    ├── *_base.usd                     # 几何 (灰色默认材质)
    ├── *_physics.usd                  # 碰撞
    ├── *_robot.usd                    # 关节
    └── *_sensor.usd                   # 传感器
```

**状态**: Isaac Sim 可用，客户在用。外观为灰色默认材质。

### 2. Fused USD (加材质版)

位置: `fused/`

**状态**: 基于 RL USD 的 base 层注入了 OmniPBR 材质 (BlackGlove + PalmWithLogo)，
physics/robot/sensor 层保持不变。待 Isaac Sim 最终验证 + Logo 纹理。

### 3. 差异说明

| 对比项 | 客户 RL USD | Fused USD |
|--------|------------|-----------|
| 位置 | `wujihand_usd_rl/` | `fused/` |
| 材质 | 灰色 DefaultMaterial | BlackGlove (黑) + PalmWithLogo (红 Logo) |
| Logo | 无 | 占位纹理 (待正式素材) |
| 物理/关节 | 完整 | 同 RL (直接复制) |
| Isaac Sim | 已验证 | 待验证 |

## 视觉规格

| 部件 | 外观 |
|------|------|
| 手掌/手指主体 | 纯黑哑光 (roughness 0.7, metallic 0) |
| 手背 Logo | 红色 Wuji/舞肌 标识 (OmniPBR 纹理) |

## 技术要点

- **材质系统**: OmniPBR (Isaac Sim/Omniverse 原生)
- **UV**: 手掌 palm_link 已有 UV unwrap 数据; 其他零件无 UV (纯色不需要)
- **Blender 验证注意**: 导入 USD 时必须勾选 "Import USD Preview" (实验性功能)
- **Python 依赖**: usd-core 需要 Python 3.12 (`C:\Python312\python.exe`)

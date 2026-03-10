# WH110 USD 模型 Logo 贴图技术方案

| 字段 | 内容 |
|------|------|
| **文档编号** | WH110-USD-LOGO-001 |
| **版本** | v1.0 |
| **日期** | 2026-03-10 |
| **作者** | zhuliang |
| **状态** | Draft |

## 1. 需求描述

在 WH110 灵巧手的 USD 模型上添加 Wuji Logo 贴图，用于产品展示和对外发布场景。

### 1.1 验收标准

| # | 标准 | 量化指标 |
|---|------|---------|
| AC-1 | USD 模型正确显示 Wuji Logo 贴图 | Logo 位于手背（dorsum）中央区域 |
| AC-2 | 位置和比例符合品牌规范 | Logo 宽度占手背宽度 60%-80% |
| AC-3 | 贴图分辨率满足渲染需求 | ≥1024x1024 PNG，无模糊/拉伸 |
| AC-4 | 在主流 USD 查看器中正常显示 | Omniverse、usdview、Blender USD Import 均正常 |
| AC-5 | 手体颜色为纯黑（模拟手套质感） | Base Color ≤ (0.02, 0.02, 0.02)，Roughness ≈ 0.7 |
| AC-6 | Logo 颜色为品牌红 | RGB #DB0015 |

### 1.2 输入资产

| 资产 | 格式 | 来源 | 说明 |
|------|------|------|------|
| WH110 右手 CAD | STEP | Fusion 360 / SolidWorks | 仅右手手掌有 STEP 源文件 |
| WH110 左/右手 Mesh | STL × 52 | wuji-hand-description v0.2.2 | 26 个零件/手，无 UV、无纹理 |
| WH110 左/右手描述 | URDF × 2 | wuji-hand-description v0.2.2 | 含关节参数、运动学层级 |
| Wuji Logo | PNG 4267×4267 | 设计团队 | 红色文字，透明背景 |

---

## 2. 技术背景

### 2.1 关键格式说明

| 格式 | 全称 | 作用 | 能力 |
|------|------|------|------|
| **STL** | Stereolithography | 三角网格几何体 | 仅几何。无颜色、无 UV、无材质 |
| **DAE** | Collada | 带材质的网格 | 几何 + UV + 材质 + 贴图。URDF 官方支持的纹理格式 |
| **URDF** | Unified Robot Description Format | 机器人结构描述 | 关节层级 + 物理参数。视觉网格引用 STL 或 DAE |
| **USD** | Universal Scene Description | 通用 3D 场景格式 (Pixar) | 几何 + 材质 + 层级 + 物理 + 贴图。行业标准交付格式 |
| **USDC** | USD Crate (Binary) | USD 的二进制编码 | 体积小、加载快，生产交付用 |
| **USDA** | USD ASCII | USD 的文本编码 | 可读，调试用 |
| **USDZ** | USD Zip Archive | USD 单文件包 | USDC + 贴图打包为一个文件，便于分发 |
| **STEP** | Standard for the Exchange of Product Data | CAD 交换格式 | 精确几何 (B-Rep)，可编辑 |

### 2.2 材质体系

| 材质系统 | 适用范围 | 兼容性 |
|----------|---------|--------|
| **UsdPreviewSurface** | USD 标准 PBR 着色器 | usdview、Blender、Houdini、任意 USD 查看器均支持 |
| **OmniPBR** | NVIDIA Omniverse 专有 | 仅 Omniverse / Isaac Sim |
| **Principled BSDF** | Blender 内部着色器 | 仅 Blender。导出 USD 时可转为 UsdPreviewSurface |

**本项目选择 UsdPreviewSurface**，确保最大兼容性。

### 2.3 当前 STL 的局限性

现有 52 个 STL 文件（SolidWorks 导出）：
- **无 UV 坐标** — 无法直接映射贴图
- **无材质数据** — 无法携带颜色信息
- **无顶点色** — 纯几何数据

因此，任何涉及材质/贴图的方案都需要额外处理步骤。

---

## 3. 方案对比

### 方案 A：Blender 纹理管线（推荐）

```
STL + URDF ──→ Blender（导入、组装、UV 展开、PBR 材质）──→ USD 导出
                                                              ↓
                                                   post_process.py
                                                   （补 MaterialBindingAPI
                                                     + URDF 物理参数）
                                                              ↓
                                                        交付 USDC + 贴图
```

**核心流程**：
1. 解析 URDF 获取层级结构和关节参数
2. 在 Blender 中导入 26 个 STL，按 URDF 父子关系组装
3. 对所有零件执行 Smart UV Project（自动 UV 展开）
4. 对手掌（palm_link）手动调整 UV，将 Logo 投射到手背
5. 创建 PBR 材质（BlackGlove + PalmWithLogo）
6. 导出 USDC，Blender 自动将 Principled BSDF → UsdPreviewSurface
7. Python 后处理：补 MaterialBindingAPI schema + 写入 URDF 物理参数

**Logo 映射方式**：UV 贴图（Image Texture → UsdUVTexture）

**需要的软件**：
| 软件 | 版本 | 用途 |
|------|------|------|
| Blender | 3.3+ | STL 导入、UV 展开、材质创建、USD 导出 |
| Python | 3.12 | 后处理脚本（pxr/usd-core） |
| Pillow | 12.x | Logo 图片处理 |

---

### 方案 B：CAD 凸起 Logo + 分色导出

```
STEP ──→ Rhino/SolidWorks（凸起 0.05mm Logo 几何体）
              ↓
         分体导出 STL/DAE（手体 + Logo 两组 mesh）
              ↓
         更新 URDF（palm_link 引用 DAE 格式 mesh）
              ↓
         Isaac Sim / Blender 转 USD
```

**核心流程**：
1. 在 CAD 软件（Rhino 8 或 SolidWorks）中打开手掌 STEP
2. 在手背面创建 Logo 轮廓曲线（SVG 导入或手动绘制）
3. 凸起 0.05mm（Emboss/Extrude）生成 Logo 几何体
4. 将手体和 Logo 分别赋予不同颜色/材质
5. 导出为 DAE (Collada) 格式，携带材质和颜色信息
6. 在 URDF 中将 palm_link 的 visual mesh 从 STL 改为 DAE
7. Isaac Sim URDF Importer 导入 → 自动生成 USD

**Logo 映射方式**：几何凸起 + 面片着色（无需 UV 贴图）

**需要的软件**：
| 软件 | 版本 | 用途 |
|------|------|------|
| Rhino | 8（有原生 USD 导出） | Logo 凸起建模、DAE/USD 导出 |
| 或 SolidWorks | 2024+ | Logo 凸起建模、DAE 导出（需插件） |
| Blender | 3.3+（可选） | DAE 材质检查、USD 二次导出 |
| Isaac Sim | 4.1+ | URDF → USD 转换 |

---

### 3.1 方案对比表

| 维度 | 方案 A（Blender 纹理） | 方案 B（CAD 凸起） |
|------|----------------------|-------------------|
| **Logo 精度** | 取决于贴图分辨率（1024px+，非常清晰） | 取决于网格精度（0.05mm 凸起需极高细分） |
| **Logo 可替换性** | 替换 PNG 即可，无需改模型 | 需重新 CAD 建模 |
| **文件体积** | 贴图 ~20KB + 原始 mesh 不变 | STL/DAE 体积可能膨胀 10-100x（Logo 区域高密度三角面） |
| **UV 需求** | 需要 UV 展开（palm_link 需手动调整） | 不需要 UV |
| **材质兼容性** | UsdPreviewSurface，全平台兼容 | DAE 材质 → USD 转换存在已知 Bug（见 §3.2） |
| **手动操作量** | 手掌 UV 需手动调整（~10 分钟/手） | CAD Logo 建模需手动操作（~30 分钟/手） |
| **自动化程度** | 高（脚本化 pipeline，仅 UV 需手动） | 低（CAD 操作难以脚本化） |
| **URDF 兼容** | 不改 URDF mesh 引用 | 需更新 URDF（STL → DAE） |
| **适用场景** | 仿真展示、产品宣传 | 3D 打印、实体产品标识 |

### 3.2 方案 B 的已知风险

以下为经互联网检索确认的事实：

1. **0.05mm 凸起的网格问题**：STL 的 chordal tolerance 需设为 ≤0.01mm 才能捕捉 0.05mm 高度变化，导致 Logo 区域三角面密度极高，文件体积显著增长。（来源：BCN3D STL Resolution Guide, Markforged STL Quality Guide）

2. **Isaac Sim DAE 纹理导入 Bug**：Isaac Sim URDF Importer 使用 ASSIMP 库处理 DAE 文件。已知问题：
   - JPG 纹理可能无法正确导入（[GitHub Issue #37](https://github.com/isaac-sim/IsaacSim/issues/37)）
   - 多个 DAE 文件使用相同材质名称时会冲突（仅第一个生效）
   - NVIDIA 官方推荐做法：先用 URDF 导入获得 USD 骨架结构，再在 Omniverse 中手动赋材质

3. **Rhino 8 USD 导出限制**：Rhino 8 原生 USD 导出仅支持 Mesh 几何体，不支持 NURBS 曲面和 SubD。（来源：[Rhino 8 USD Documentation](https://docs.mcneel.com/rhino/8/help/en-us/fileio/usd_import_export.htm)）

4. **SolidWorks 无原生 USD 导出**：需要第三方插件（SimLab USDZ Exporter 或 CAD Exchanger）。（来源：SimLab, CAD Exchanger 官网）

5. **URDF 纹理格式**：URDF 规范官方支持 STL 和 DAE (Collada) 格式的 mesh 引用。DAE 可携带完整材质和贴图信息，STL 不能。（来源：[ROS URDF Tutorial](https://wiki.ros.org/urdf/XML/link)）

---

## 4. 推荐方案：方案 A（Blender 纹理管线）

### 4.1 推荐理由

| 理由 | 说明 |
|------|------|
| Logo 可热替换 | 设计团队更新 Logo 后，替换 PNG 重跑脚本即可 |
| 文件体积可控 | 不增加几何复杂度，贴图仅 ~20KB |
| 全查看器兼容 | UsdPreviewSurface 是 USD 标准材质，不依赖特定软件 |
| 自动化程度高 | 除手掌 UV 微调外，全流程脚本化 |
| 已验证可行 | 右手已完成端到端构建，验证通过 |

### 4.2 交付物

```
exports/
├── wuji_hand_right/
│   ├── wuji_hand_right.usdc          # 主 USD (binary)
│   └── textures/
│       └── wuji_logo_placeholder.png # Logo 贴图 (1024x1024, 黑底红字)
├── wuji_hand_right.usdz              # 单文件包
├── wuji_hand_left/
│   ├── wuji_hand_left.usdc
│   └── textures/
│       └── wuji_logo_placeholder.png
└── wuji_hand_left.usdz
```

### 4.3 Pipeline 脚本

| 脚本 | 运行环境 | 功能 |
|------|---------|------|
| `generate_logo_texture.py` | Python 3.12 + Pillow | 生成/处理 Logo 贴图（透明→黑底） |
| `blender_build_hand.py` | Blender 3.3 headless | 导入 STL、组装层级、UV 展开、材质创建、USD 导出 |
| `post_process_usd.py` | Python 3.12 + pxr | 补 MaterialBindingAPI、写物理参数、验证、打包 |
| `build_all.bat` | Windows CMD | 一键串联以上 3 个脚本 |

### 4.4 已知问题与解决方案

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Blender 3.3 USD 导出缺少 MaterialBindingAPI | Blender Bug | `post_process_usd.py` 自动补充 `UsdShade.MaterialBindingAPI.Apply()` |
| Logo 透明背景在 USD 查看器中显示为白色 | UsdPreviewSurface 不支持 alpha 混合 diffuseColor | 将 Logo 贴图改为黑底红字（RGB，无 alpha） |
| 手掌 UV 需手动调整 | Smart UV Project 不知道 Logo 应贴在哪里 | 在 Blender GUI 中手动 Project from View |
| 左右手 URDF 变换不同 | 不是简单镜像 | 左右手分别用 `--side` 参数独立构建 |

---

## 5. 方案 B 备注（CAD 凸起路径）

若未来需要在实体产品上标识 Logo（3D 打印/注塑），方案 B 更适合。推荐流程：

1. **Rhino 8** 打开 STEP → 导入 Logo SVG → 投影到手背曲面 → Emboss 0.05mm
2. 将手体和 Logo 分为两个 mesh group，赋不同颜色
3. **导出路径选择**：
   - 若目标是 USD 展示：直接用 Rhino 8 原生 USD 导出（仅 mesh + 材质）
   - 若目标是仿真：导出 DAE → 更新 URDF → Isaac Sim 导入（注意 §3.2 中的已知 Bug）
4. 建议 Emboss 高度 ≥ 0.5mm（0.05mm 对网格精度要求过高，仅仿真场景无必要）

---

## 6. 参考资料

| 来源 | URL |
|------|-----|
| USD 规范 | https://openusd.org/release/api/index.html |
| UsdPreviewSurface 规范 | https://openusd.org/release/spec_usdpreviewsurface.html |
| Rhino 8 USD 导出文档 | https://docs.mcneel.com/rhino/8/help/en-us/fileio/usd_import_export.htm |
| Isaac Sim URDF Importer | https://docs.isaacsim.omniverse.nvidia.com/4.5.0/robot_setup/ext_isaacsim_asset_importer_urdf.html |
| Isaac Sim DAE 纹理 Bug | https://github.com/isaac-sim/IsaacSim/issues/37 |
| ROS URDF Link 规范 | https://wiki.ros.org/urdf/XML/link |
| Blender USD 导出文档 | https://docs.blender.org/manual/en/3.3/files/import_export/usd.html |
| STL 精度指南 | https://support.bcn3d.com/knowledge/resolution-stl |

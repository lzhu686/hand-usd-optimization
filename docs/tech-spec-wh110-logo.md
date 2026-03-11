# WH110 USD 模型 Logo 贴图 — 技术方案

| 字段 | 内容 |
|------|------|
| **文档编号** | WH110-USD-LOGO-001 |
| **版本** | v2.3 |
| **日期** | 2026-03-11 |
| **作者** | zhuliang |
| **状态** | Implemented — 右手已验证通过 |

> **变更记录**
> - v1.0 (2026-03-10): 初版技术方案，两方案对比
> - v2.0 (2026-03-10): 融合调查报告、知识库、实施经验，确定最终方案
> - v2.1 (2026-03-11): 新增带 Logo 凸起的 STEP 源文件；右手 USD 从 Blender 重新导出并后处理
> - v2.2 (2026-03-11): 修复 post_process 覆盖 Xform 类型导致手指坍缩 Bug；修复 physics: 属性导致 Blender 调试线；右手最终验证通过
> - v2.3 (2026-03-11): 新增完整左右手 STEP 文件（`right_hand_full.STEP`, `left_hand_full.STEP`），更新输入资产清单

---

## 1. 需求描述

在 WH110 灵巧手的 USD 模型上添加 Wuji Logo 贴图，用于产品展示和对外发布场景。

### 1.1 验收标准

| # | 标准 | 量化指标 | 状态 |
|---|------|---------|------|
| AC-1 | USD 模型正确显示 Wuji Logo | Logo 位于手背（dorsum）中央区域 | ✅ 右手已实现 |
| AC-2 | 位置和比例符合品牌规范 | Logo 宽度占手背宽度 60%-80% | ✅ 手动 UV 调整 |
| AC-3 | 贴图分辨率满足渲染需求 | ≥1024×1024 PNG，无模糊/拉伸 | ✅ 1024×1024 |
| AC-4 | 主流 USD 查看器正常显示 | Omniverse / Blender USD Import | ✅ 修复 MaterialBindingAPI 后通过 |
| AC-5 | 手体颜色为纯黑（模拟手套质感） | Base Color (0.02, 0.02, 0.02)，Roughness 0.7 | ✅ |
| AC-6 | Logo 颜色为品牌红 | RGB #DB0015 | ✅ |

### 1.2 输入资产

| 资产 | 格式 | 来源 | 存放路径 |
|------|------|------|----------|
| WH110 完整右手 CAD | STEP | CAD 团队 (D5 simplified URDF v29) | `wuji-hand-baseline/step/right/right_hand_full.STEP` (12 MB) |
| WH110 完整左手 CAD | STEP | CAD 团队 (无软体版) | `wuji-hand-baseline/step/left/left_hand_full.STEP` (9.8 MB) |
| WH110 手 Mesh | STL | wuji-hand-description v0.2.2 | `wuji-hand-baseline/stl/{left,right}/` (52 个) |
| WH110 手描述 | URDF | wuji-hand-description v0.2.2 | `wuji-hand-baseline/urdf/{left,right}.urdf` |
| WH110 右手掌 CAD（原版） | STEP | SolidWorks 导出 | `wuji-hand-baseline/step/right/right_palm_link.STEP` (4.8 MB) |
| WH110 右手掌 CAD（带 Logo 凸起） | STP | CAD 建模（方案 B 备用） | `wuji-hand-baseline/step/right/right_palm_link_with_logo.stp` (7.7 MB) |
| Wuji Logo | PNG 1024×1024 | 设计团队 | `hand-usd-optimization/textures/logo/` |

---

## 2. 前期调查结论

> 来源：`archive/investigation-report.md` (2026-02-28)

### 2.1 USD 文件现状

| 仓库 | USD 状态 |
|------|---------|
| `wuji-hand-description` | 无 USD，从未有过 |
| `wuji-description` | 空仓库（规划中的 USD 存放地） |
| `isaaclab-sim` | USD 由 Isaac Sim 从 URDF 自动生成，gitignored |

**结论**：USD 不是静态资产，而是运行时由 Isaac Sim 的 URDF Importer 动态生成。生成的 USD 继承 URDF 的灰色单色材质，无纹理。

### 2.2 STL 的根本局限

现有 52 个 STL 文件（SolidWorks 导出）：
- **无 UV 坐标** — 无法直接映射贴图
- **无材质数据** — 无法携带颜色信息
- **无顶点色** — 纯几何数据

任何涉及材质/贴图的方案都需要额外处理步骤。

### 2.3 URDF 结构（每只手）

```
{side}_palm_link                    ← 手掌（Logo 贴在这里）
├── {side}_finger1_ (大拇指)         link1 → link2 → link3 → link4 → tip_link
├── {side}_finger2_ (食指)           link1 → link2 → link3 → link4 → tip_link
├── {side}_finger3_ (中指)           link1 → link2 → link3 → link4 → tip_link
├── {side}_finger4_ (无名指)         link1 → link2 → link3 → link4 → tip_link
└── {side}_finger5_ (小指)           link1 → link2 → link3 → link4 → tip_link

关节：20 revolute + 5 fixed (tip) = 25 joints
零件：1 palm + 5 × 5 links = 26 meshes
```

---

## 3. 方案评估与决策

### 3.1 评估过的方案

| 方案 | 路径 | 结论 |
|------|------|------|
| Isaac Sim 直接改材质 | URDF → Isaac Sim 生成 USD → Python 脚本改材质 | **放弃**：STL 无 UV，Logo 无法精确贴图 |
| 3D 扫描 | 扫描真实手 → 提取纹理 → retopo | **暂缓**：需扫描硬件和 3D 艺术家 |
| **Blender 纹理管线** | STL → Blender UV 展开 → PBR 材质 → USD 导出 | **采用**：已实施并验证 |
| CAD 凸起 Logo | STEP → Rhino 凸起 0.05mm → DAE → URDF → USD | **备选**：适合实体产品，不适合仿真展示 |

### 3.2 最终方案：Blender 纹理管线

**选择理由**：

| 理由 | 说明 |
|------|------|
| Logo 可热替换 | 替换 PNG 重跑脚本即可，无需改模型 |
| 文件体积可控 | 不增加几何复杂度，贴图仅 ~20KB |
| 全查看器兼容 | UsdPreviewSurface 是 USD 标准，不依赖特定软件 |
| 高自动化 | 除手掌 UV 微调外，全流程脚本化 |
| 已验证 | 右手端到端构建通过 |

### 3.3 CAD 凸起方案的已知风险

以下为经互联网检索确认的事实（非臆测）：

1. **0.05mm 凸起的网格问题**：STL chordal tolerance 需 ≤0.01mm，Logo 区域三角面密度极高，文件体积膨胀 10-100x。
   来源：[BCN3D STL Resolution Guide](https://support.bcn3d.com/knowledge/resolution-stl)

2. **Isaac Sim DAE 纹理导入 Bug**：ASSIMP 库处理 DAE 时，JPG 纹理可能丢失，相同材质名称冲突。
   来源：[GitHub Issue #37](https://github.com/isaac-sim/IsaacSim/issues/37)

3. **SolidWorks 无原生 USD 导出**：需 SimLab 或 CAD Exchanger 第三方插件。

4. **Rhino 8 USD 导出限制**：仅支持 Mesh，不支持 NURBS/SubD。
   来源：[Rhino 8 USD Docs](https://docs.mcneel.com/rhino/8/help/en-us/fileio/usd_import_export.htm)

5. **URDF 纹理格式**：URDF 官方支持 STL 和 DAE (Collada) 格式。DAE 可携带完整材质和贴图，STL 不能。
   来源：[ROS URDF Link](https://wiki.ros.org/urdf/XML/link)

> **备注**：已收到带 Logo 凸起的 STEP 文件（`right_palm_link_with_logo.stp`, 7.7MB, 2026-03-11），
> 已归档至 `wuji-hand-baseline/step/right/`。若未来需走方案 B 路径，此文件可直接使用。

---

## 4. 实施方案详细设计

### 4.1 技术架构

```
generate_logo_texture.py     blender_build_hand.py       post_process_usd.py
  (Python 3.12 + PIL)        (Blender 3.3 headless)      (Python 3.12 + pxr)
         ↓                            ↓                           ↓
  textures/logo/*.png     usd/{side}/*.usdc + .blend     exports/ (final)

                    总控：build_all.bat 串联三步
```

### 4.2 关键格式说明

| 格式 | 全称 | 作用 |
|------|------|------|
| **STL** | Stereolithography | 纯三角网格，无颜色/UV/材质 |
| **DAE** | Collada | 带材质的网格，URDF 官方支持的纹理格式 |
| **URDF** | Unified Robot Description Format | 机器人关节层级 + 物理参数 |
| **USD** | Universal Scene Description (Pixar) | 通用 3D 场景格式（几何+材质+层级+物理） |
| **USDC** | USD Crate (Binary) | 体积小、加载快，生产交付用 |
| **USDZ** | USD Zip Archive | USDC + 贴图打包为单文件 |

### 4.3 材质设计

| 材质名 | 应用对象 | 参数 |
|--------|---------|------|
| **BlackGlove** | 25 个手指零件 | diffuseColor: (0.02, 0.02, 0.02), roughness: 0.7, metallic: 0.0 |
| **PalmWithLogo** | 1 个手掌零件 | diffuseColor → UsdUVTexture (Logo 贴图), roughness: 0.7, metallic: 0.0 |

材质系统选择 **UsdPreviewSurface**（非 OmniPBR），确保跨平台兼容。

Logo 贴图规格：
- 格式：PNG 1024×1024
- 颜色模式：**RGB（黑底红字，无 alpha）**
- Logo 颜色：品牌红 #DB0015
- 背景色：(5, 5, 5)（匹配 BlackGlove 的近黑色）

> **重要**：不使用 RGBA 透明背景。原因：UsdPreviewSurface 将透明像素渲染为白色，导致手掌显示白色而非黑色。

### 4.4 Pipeline 脚本

| 脚本 | 运行环境 | 功能 |
|------|---------|------|
| `generate_logo_texture.py` | Python 3.12 + Pillow | 处理 Logo PNG：去白底/透明底 → 黑底红字 |
| `blender_build_hand.py` | Blender 3.3 `--background` | URDF 解析 → STL 导入组装 → UV 展开 → PBR 材质 → USDC 导出 |
| `post_process_usd.py` | Python 3.12 + pxr | 补 MaterialBindingAPI → 写物理关节 → 验证 → 打包 exports |
| `build_all.bat` | Windows CMD | 一键串联：Logo → 右手 → 左手 → 后处理 |

### 4.5 手动步骤（无法自动化）

**手掌 UV 调整**（每只手约 10 分钟）：

Smart UV Project 自动展开无法知道 "Logo 应贴在手背哪个位置"，需在 Blender GUI 中：
1. 选中 `{side}_palm_link` → Edit Mode
2. UV Editor 全选 → 缩小到角落（避免 Logo 着色到错误面）
3. 3D 视图中仅选手背面 → `U` → Project from View
4. UV Editor 中调整大小和位置，对准 Logo 图案
5. 退出 Edit Mode → 检查 Material Preview 效果

---

## 5. 实施结果

### 5.1 构建验证

| 检查项 | 右手 | 左手 |
|--------|------|------|
| Mesh 数量 | 26/26 ✅ | 26/26 ✅ |
| UV Maps | 26/26 ✅ | 26/26 ✅ |
| 材质绑定 | 2 材质 ✅ | 2 材质 ✅ |
| Shader 类型 | UsdPreviewSurface ✅ | UsdPreviewSurface ✅ |
| 物理关节 | 25/25 ✅ | 25/25 ✅ |
| MaterialBindingAPI | 已补全 ✅ | 已补全 ✅ |
| USDZ 打包 | 3.5 MB ✅ | 3.8 MB ✅ |
| 手掌 Logo UV | **手动调好** ✅ (Blender 重新导出 2026-03-11) | 待手动调整 |

### 5.2 交付物

```
exports/
├── wuji_hand_right/
│   ├── wuji_hand_right.usdc            # 主 USD (binary, 3.5 MB)
│   └── textures/
│       └── wuji_logo_placeholder.png   # Logo 贴图 (1024×1024, 黑底红字)
├── wuji_hand_right.usdz                # 单文件包 (3.5 MB)
├── wuji_hand_left/
│   ├── wuji_hand_left.usdc             # 主 USD (binary, 3.8 MB)
│   └── textures/
│       └── wuji_logo_placeholder.png
└── wuji_hand_left.usdz                 # 单文件包 (3.8 MB)
```

调试文件：
```
usd/{side}/wuji_hand_{side}_debug.blend   # Blender 工程文件，可手动微调
```

### 5.3 已踩坑与解决

| 问题 | 根因 | 解决方案 |
|------|------|---------|
| USD 导入后全灰/白，无材质 | Blender 3.3 导出 USD 缺少 `MaterialBindingAPI` schema 声明 | `post_process_usd.py` 自动调用 `UsdShade.MaterialBindingAPI.Apply()` |
| 手掌在 USD 查看器中显示白色 | Logo PNG 为透明背景 RGBA，UsdPreviewSurface 透明=白色 | 将 Logo 贴图改为 RGB 黑底红字，不使用 alpha |
| Logo 红色散落到手掌各处 | Smart UV Project 随机分布 UV 岛，部分 UV 落在 Logo 红色区域 | 先缩小全部 UV 到角落，再仅对手背面 Project from View |
| 左右手不能简单镜像 | URDF 中左右手的 joint origin xyz/rpy 值不同 | 用 `--side` 参数分别构建 |
| usd-core (pip) 不含 usdview | pip 版 usd-core 只有 Python API，不含 GUI 查看器 | 用 Blender Import USD 或 Omniverse 验证 |
| 手指坍缩到手掌根部 | `post_process` 用 `UsdPhysics.RevoluteJoint.Define()` 覆盖了关节 Xform 类型，破坏变换链 | 改为在 Xform prim 上直接写 `wuji:` 前缀自定义属性，不改 prim 类型 |
| Blender 中出现大量黑色线条 | `physics:` 前缀属性被 Blender 解析为物理约束并显示调试线 | 属性前缀改为 `wuji:`；Blender 中关闭 Overlays → Extras |
| Blender USD Import 不加载 UsdUVTexture 贴图 | Blender 3.3 USD 导入器不完全支持 UsdPreviewSurface 纹理节点 | 提供 `verify_usd_in_blender.py` 脚本自动修复材质节点 |

---

## 6. 环境依赖

| 软件 | 版本 | 用途 | 安装方式 |
|------|------|------|---------|
| Python | 3.12 | 后处理脚本 | `C:\Python312\python.exe` |
| pxr (usd-core) | 26.3 | USD 读写 | `pip install usd-core` |
| Pillow | 12.x | Logo 图片处理 | `pip install Pillow` |
| Blender | 3.3.21 | STL 导入、UV、材质、USD 导出 | `C:\Program Files\Blender Foundation\Blender 3.3\` |
| Isaac Sim | 4.1.0 (可选) | USD 仿真验证 | Omniverse Launcher |

---

## 7. Logo 更换流程

设计团队提供新 Logo 后：

1. 准备 PNG 文件：**1024×1024，RGB，黑底红字，无 alpha**
2. 替换 `textures/logo/wuji_logo_placeholder.png`
3. 运行 `build_all.bat`（或仅重跑需要更新的手）
4. 手动调整手掌 UV（如 Logo 形状/比例变化大）
5. 重跑 `post_process_usd.py`

如果 Logo 形状不变（仅细节调整），跳过步骤 4。

---

## 8. 后续迭代方向

| 方向 | 说明 | 优先级 |
|------|------|--------|
| 左手 Logo UV 调整 | 按右手同样流程手动调整 | P0 |
| 法线贴图 | 添加织物/橡胶微纹理增加手套质感 | P2 |
| Isaac Sim 集成 | 修改 `isaaclab-sim` 加载自定义 USD 替代自动生成 | P1 |
| `wuji-description` 仓库 | 将最终 USD 推送到该仓库作为官方资产 | P1 |
| CAD 凸起 Logo | 若需实体产品标识，走 Rhino 8 建模路径 | P3 |
| 3D 扫描精修 | 扫描真实手获取基础纹理，提升至照片级 | P3 |

---

## 9. 参考资料

| 来源 | URL |
|------|-----|
| USD 规范 | https://openusd.org/release/api/index.html |
| UsdPreviewSurface 规范 | https://openusd.org/release/spec_usdpreviewsurface.html |
| Blender USD 导出 | https://docs.blender.org/manual/en/3.3/files/import_export/usd.html |
| Rhino 8 USD 导出 | https://docs.mcneel.com/rhino/8/help/en-us/fileio/usd_import_export.htm |
| Isaac Sim URDF Importer | https://docs.isaacsim.omniverse.nvidia.com/4.5.0/robot_setup/ext_isaacsim_asset_importer_urdf.html |
| Isaac Sim DAE 纹理 Bug | https://github.com/isaac-sim/IsaacSim/issues/37 |
| ROS URDF Link 规范 | https://wiki.ros.org/urdf/XML/link |
| STL 精度指南 | https://support.bcn3d.com/knowledge/resolution-stl |

---

## 附录 A：历史文档索引

以下文档已归档至 `docs/archive/`，仅供追溯：

| 文档 | 日期 | 内容 |
|------|------|------|
| `investigation-report.md` | 2026-02-28 | USD 文件位置调查 |
| `knowledge-base.md` | 2026-02-28 | 项目早期知识库 |
| `plan-v1-textured-usd.md` | 2026-02-28 | 三路径方案评估（A/B/C）|
| `tech-spec-wh110-logo-v1-draft.md` | 2026-03-10 | 技术方案初版 |

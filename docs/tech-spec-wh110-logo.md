# WH110 USD 模型 Logo 贴图 — 技术方案

| 字段 | 内容 |
|------|------|
| **版本** | v3.0 |
| **日期** | 2026-03-22 |
| **状态** | Implemented — 左右手 IsaacSim 验证通过 |

> **变更记录**
> - v1.0~v2.3: 初版方案、调查、Blender 构建、后处理验证（见 git history）
> - v3.0 (2026-03-22): 重构为 IsaacLab 工作流，Blender mesh 直接替换方案

---

## 1. 需求

在 WH110 灵巧手 USD 模型的手掌上添加 Wuji Logo 贴图，用于 IsaacSim 仿真展示。

| 验收标准 | 指标 |
|---------|------|
| Logo 位置 | 手掌中央区域 |
| 分辨率 | 1024x1024 PNG |
| 手体颜色 | 纯黑哑光 (0.02, 0.02, 0.02), roughness 0.7 |
| 跨平台 | Isaac Sim + Blender 均可渲染 |

---

## 2. 技术架构

```
baseline/stl/ + baseline/urdf/
         │
         ├── blender_build_hand.py (Blender 3.3+)
         │   STL 导入 → URDF 层级组装 → Smart UV Project
         │   → PBR 材质 (BlackGlove + PalmWithLogo) → USDC 导出
         │   产物: usd/{side}/*.usdc + textures/  (gitignored)
         │
         ├── urdf_to_usd.py (IsaacLab UrdfConverter)
         │   URDF → USD (物理/关节/碰撞/驱动)
         │   产物: usd_raw/  (gitignored)
         │
         └── fuse_rl_appearance.py
             IsaacLab USD (物理) + Blender USDC (外观) → fused/{side}/
             核心操作:
               1. 复制 IsaacLab USD 结构
               2. 直接替换 palm_link visual mesh 为 Blender mesh (含 UV)
               3. 创建双材质 (OmniPBR + UsdPreviewSurface)
               4. 覆盖所有 scope 的材质绑定 (/visuals/ + /meshes/)
```

### 为什么替换 mesh 而不是映射 UV

IsaacLab UrdfConverter 和 Blender 对同一个 STL 做不同的三角化，产生不同的 mesh 拓扑：

| | IsaacLab | Blender |
|---|---|---|
| 唯一顶点 | 4694 | 4694 |
| 面数 | 9400 | 9396 |
| 面顶点 | 28200 | 28188 |

尝试过的 UV 映射方案及失败原因：
- **逐顶点 KDTree**: UV 缝合处跨岛，产生交叉线
- **面质心匹配**: 30% exact / 70% fallback，Logo 碎片化
- **重心坐标插值**: unrolled mesh 重复顶点导致 face_id 歧义

**直接替换 mesh = 零误差**。物理层在独立 sublayer 中，不受影响。

---

## 3. 材质系统

### 双上下文材质 (Dual Context Material)

```
Material "/Looks/BlackGlove"
├── Shader "OmniPBR"          → outputs:mdl:surface     (Isaac Sim)
└── Shader "PreviewSurface"   → outputs:surface          (Blender/usdview)
```

| | OmniPBR (MDL) | UsdPreviewSurface |
|---|---|---|
| 标准 | NVIDIA 私有 | OpenUSD 官方 |
| 可见于 | Isaac Sim / Omniverse | Blender / usdview |
| Wrap mode | — | wrapS=clamp, wrapT=clamp |

### 材质分配

| 材质 | 对象 | 参数 |
|------|------|------|
| BlackGlove | 25 个手指 visual mesh | diffuse (0.02, 0.02, 0.02), roughness 0.7 |
| PalmWithLogo | 1 个手掌 visual mesh | diffuse texture + roughness 0.7 |

材质绑定覆盖所有 scope（`/visuals/` + `/meshes/`），防止 IsaacLab 默认材质通过 USD reference 优先级覆盖。

---

## 4. 坐标系处理

Blender 和 IsaacLab 可能使用不同坐标系。代码自动检测：

```python
# 比较 identity vs Y-negation 的顶点对齐距离
d_id = KDTree(src_points).query(target_points).mean()
d_ny = KDTree(src_points * [1,-1,1]).query(target_points).mean()
if d_ny < d_id * 0.8:
    src_points *= [1, -1, 1]  # 自动修正
```

---

## 5. 环境依赖

| 软件 | 用途 |
|------|------|
| conda env `env_isaaclab` | IsaacLab + pxr + scipy + PIL |
| Blender 3.3+ | blender_build_hand.py |

---

## 6. URDF 结构（每只手）

```
{side}_palm_link                     ← 手掌 (Logo 贴在这里)
├── {side}_finger1_ (大拇指)          link1 → link2 → link3 → link4 → tip_link
├── {side}_finger2_ (食指)            ...
├── {side}_finger3_ (中指)            ...
├── {side}_finger4_ (无名指)          ...
└── {side}_finger5_ (小指)            ...

关节: 20 revolute + 5 fixed (tip) = 25 joints
零件: 1 palm + 5 × 5 links = 26 meshes
```

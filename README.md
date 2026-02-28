# Wuji Hand USD Optimization

让 Wuji 灵巧手的 USD 模型与真实物理手匹配的专项优化工程。

## Background

当前 Wuji Hand 的 3D 模型从 Fusion 360 → SolidWorks → STEP/STL 导出，仅包含几何数据，没有纹理和材质信息。URDF/MJCF 文件中所有零件使用统一的灰色 `rgba(0.898, 0.918, 0.929, 1)`。

**目标**：生成视觉上接近真机的 USD 格式模型。

## Target Visual Spec

| Element | Appearance |
|---------|------------|
| 手掌/手指主体 | 纯黑 (模拟手套质感) |
| 手背 Logo | 红色 Wuji/舞肌 标识 |
| 材质质感 | 哑光橡胶/织物 (roughness ~0.7) |

## Project Structure

```
hand-usd-optimization/
├── README.md                  # 本文件
├── docs/
│   └── knowledge-base.md      # 详细技术知识库
├── textures/
│   ├── logo/                  # Wuji logo 素材 (PNG/SVG)
│   └── base/                  # 基础纹理 (黑色材质贴图)
├── scripts/                   # 转换/处理脚本
├── usd/
│   ├── right/                 # 右手 USD 输出
│   └── left/                  # 左手 USD 输出
├── references/                # 参考图片/真机照片
└── exports/                   # 最终导出文件
```

## Source Assets

所有素材均可追溯至两个上游来源，确保版本一致。

### 1. 机械组提供 (CAD 原始文件)

由机械工程师从 SolidWorks 导出，包含完整参数化几何信息。

| File | Path | Format | Description |
|------|------|--------|-------------|
| 右手手掌.STEP | `C:\Users\zhuliang\Desktop\wuji\右手手掌.STEP` | STEP AP214 | 右手手掌 CAD 源文件，含完整 B-Rep 几何 |
| 右手手掌.STL | `C:\Users\zhuliang\Desktop\wuji\右手手掌.STL` | Binary STL | 右手手掌网格，SolidWorks 导出的 tessellated 版本 |

> **Pipeline**: Fusion 360 → SolidWorks → STEP + STL 导出

### 2. GitHub 仓库 (运动学 + 全零件网格)

| Source | Repo | Version | Local Path |
|--------|------|---------|------------|
| URDF/MJCF | [wuji-hand-description](https://github.com/wuji-technology/wuji-hand-description) | v0.2.2 (`88ee51d`) | `../wuji-hand-description/` |
| STL Meshes (52pcs) | 同上 `meshes/{left,right}/` | v0.2.2 | 同上 |
| Isaac Sim Demo | [isaaclab-sim](https://github.com/wuji-technology/isaaclab-sim) | main | `../isaaclab-sim/` |

### 3. Baseline 汇总仓库 (版本锁定, git 管理)

以上所有格式统一整理至 `../wuji-hand-baseline/`，含 STEP/STL/URDF/USD 四种格式，
均来自 wuji-hand-description **v0.2.2**，详见其 [VERSION.md](../wuji-hand-baseline/VERSION.md)。

### 格式关系图

```
机械组 (SolidWorks)                 GitHub (wuji-hand-description v0.2.2)
  │                                     │
  ├── 右手手掌.STEP (CAD 源)            ├── urdf/{left,right}.urdf
  └── 右手手掌.STL  (网格)             ├── meshes/ → 52x STL
                                        └── mjcf/{left,right}.xml
      │                                     │
      └───────── 汇总 ──────────────────────┘
                  │
         wuji-hand-baseline/ (git)
         ├── step/  ← 机械组 STEP
         ├── stl/   ← GitHub STL
         ├── urdf/  ← GitHub URDF
         └── usd/   ← urdf_to_usd.py 生成 (pxr usd-core)
```

## Implementation Roadmap

### Phase 1: Basic Coloring (Quick Win)
- [ ] URDF → USD 转换 (Isaac Sim or Blender)
- [ ] 全零件应用黑色 PBR 材质
- [ ] 手掌部分应用红色 Logo 区域
- [ ] 验证 asset 引用路径正确性

### Phase 2: Enhanced Materials
- [ ] 添加 roughness/metallic maps 模拟手套质感
- [ ] Logo 贴图制作 (PNG texture)
- [ ] UV unwrap 手掌区域用于 Logo 放置

### Phase 3: High Fidelity (Optional)
- [ ] 3D 扫描真机获取基础素材
- [ ] Blender/UE 布料系统模拟手套
- [ ] 完整 PBR 材质 pipeline
- [ ] 协同 ID 设计师完善

## Quick Start

```bash
# 1. 确保 wuji-hand-description 已 clone
cd C:\Users\zhuliang\Desktop\wuji
git clone https://github.com/wuji-technology/wuji-hand-description.git

# 2. 安装依赖 (选择一种)
# Option A: NVIDIA Isaac Sim (推荐)
# Option B: Blender 3.6+ with USD plugin
# Option C: pip install usd-core

# 3. 执行转换 (待实现)
# python scripts/urdf_to_usd.py
```

## Notes

- 纹理问题大概率是 asset 引用路径问题 — USD 中需注意 `@path@` 语法
- 如果当前没有纹理基础，最快的方式是做三维扫描或找 ID 设计师
- Blender / UE 的布料系统可以做出更好的手套可视化效果
- 现阶段建议从简单上色开始，逐步迭代

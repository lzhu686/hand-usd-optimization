# Plan: 出一版带有现实有效性纹理的 USD

## Executive Summary

当前现状：USD 由 Isaac Sim 从 URDF 自动转换生成，仅有几何+灰色材质，无纹理。
本方案分 3 条可执行路径，推荐 **路径 B (Blender Pipeline)** 作为主方案。

---

## 路径 A: Isaac Sim 内直接改材质 (最快出效果)

### 适用场景
仅需在 Isaac Sim 仿真中看到效果，不需要通用 USD 文件

### 步骤
1. 运行 `isaaclab-sim` 让 Isaac Sim 自动生成 `usd/wujihand.usd`
2. 用 Python USD API (pxr) 后处理脚本修改生成的 USD:
   - 替换所有 link 的材质为黑色 PBR
   - 为 palm_link 添加红色 Logo decal
3. 将修改后的 USD 设为 `force_usd_conversion=False` 避免被覆盖

### 优点
- 最快（~1天）
- 纯代码，可脚本化
- 直接在仿真环境验证

### 缺点
- Logo 只能做简单颜色区分（无法精确贴图，因为 STL 没有 UV）
- 质感有限（flat shading）
- 依赖 Isaac Sim 环境

### 所需工具
- Isaac Sim (已有 isaaclab-sim 项目)
- Python + pxr (USD API)

---

## 路径 B: Blender Pipeline (推荐 - 平衡效果与可行性)

### 适用场景
需要高质量、可复用的 USD 文件，视觉接近真机

### 步骤

#### Phase 1: 几何导入 (Day 1)
1. 将所有 STL 零件导入 Blender（26个零件/手）
2. 按 URDF joint hierarchy 组装（参考 right.urdf 中的 origin xyz/rpy）
3. 验证装配与 URDF 一致

#### Phase 2: UV 展开 (Day 1-2)
4. 对 **palm_link** 做手动 UV 展开（Logo 需要精确 UV）
5. 对其余零件做自动 UV 展开（Smart UV Project — 用于接收简单材质即可）
6. UV 不需要完美，因为主体是纯黑，只有 Logo 区域需要精度

#### Phase 3: 材质制作 (Day 2-3)
7. **黑色手套材质**:
   - Base Color: (0.02, 0.02, 0.02) 近黑
   - Roughness: 0.65-0.75 (哑光橡胶/尼龙手套质感)
   - Metallic: 0.0
   - Normal Map: 可选 — 细微织物纹理增加真实感
8. **红色 Logo 材质**:
   - 用 Blender Texture Paint 或导入 SVG 绘制舞肌 Logo
   - Base Color Texture: 在 palm 背面区域绘制红色 Logo
   - 红色 (0.8, 0.05, 0.05) + 略微光泽 roughness 0.3
9. **关节/金属部分** (可选):
   - 如果有外露金属部分: metallic=0.8, roughness=0.4

#### Phase 4: USD 导出 (Day 3)
10. Blender → 导出 USD (.usda/.usdc)
    - 确保材质/纹理正确打包
    - 验证 asset 引用路径为相对路径
11. 纹理文件组织:
    ```
    usd/
    ├── right_hand.usda          # 主 USD 文件
    ├── left_hand.usda
    └── textures/
        ├── glove_black_basecolor.png
        ├── glove_black_roughness.png
        ├── glove_black_normal.png   # 可选
        └── wuji_logo.png
    ```

#### Phase 5: 验证 (Day 3-4)
12. 在 Isaac Sim 中加载自定义 USD 验证效果
13. 修改 `wuji_hand.py` 指向新 USD 文件
14. 检查关节运动是否正常（link hierarchy 必须与 URDF 一致）

### 优点
- 质量高，最接近真机效果
- USD 文件可复用于 Isaac Sim / Omniverse / 其它渲染器
- Logo 精确可控
- 手套质感逼真（PBR 材质）

### 缺点
- 需要 Blender 操作经验
- UV 展开需要人工（~半天）
- 总工期 3-4 天

### 所需工具
- Blender 3.6+ (内置 USD 导出)
- GIMP/Photoshop (Logo 贴图制作)
- Isaac Sim (验证)

---

## 路径 C: 3D 扫描 + DCC 精修 (最高保真度)

### 适用场景
需要照片级真实感，有硬件和人力资源

### 步骤
1. 用结构光/激光扫描仪扫描真实手（戴手套状态）
2. 获取点云 → 重建 mesh → 提取纹理
3. 将扫描纹理 retopo 到 URDF 零件上
4. Blender/UE 精修 + 布料系统模拟手套褶皱
5. 导出 USD

### 优点
- 最高保真度
- 自动获取真实纹理

### 缺点
- 需要 3D 扫描硬件
- 需要 ID 设计师/3D 艺术家
- 工期 1-2 周

---

## 对比总结

| 维度 | 路径 A (Isaac Sim) | 路径 B (Blender) | 路径 C (3D Scan) |
|------|-------------------|-----------------|-----------------|
| 工期 | 1 天 | 3-4 天 | 1-2 周 |
| 视觉质量 | 基础 (纯色) | 良好 (PBR+Logo) | 极佳 (照片级) |
| Logo 精度 | 低 (颜色块) | 高 (UV贴图) | 最高 |
| 可复用性 | 仅 Isaac Sim | 通用 USD | 通用 USD |
| 技术门槛 | Python 脚本 | Blender 中级 | 扫描+专业DCC |
| 依赖 | Isaac Sim | Blender | 扫描仪+设计师 |

## 推荐决策

**立即启动路径 B**，因为：
1. 路径 A 质量不够（STL 无 UV，Logo 做不精确）
2. 路径 C 依赖太多外部资源
3. 路径 B 可以先出一版 reasonable 的效果，后续再用路径 C 升级

**可以并行**: 在执行路径 B 的同时，安排 3D 扫描采集基础素材，后续作为 Phase 2 迭代。

---

## 下一步 Action Items

- [ ] 确认方案选择 (A/B/C)
- [ ] 准备舞肌 Logo 矢量文件 (SVG/AI)
- [ ] 收集真机参考照片 (放入 references/ 文件夹)
- [ ] 确认是否有 Blender 环境
- [ ] 确认是否有 Isaac Sim 环境可用于验证

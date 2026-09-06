# 首批原生数据适配验收

本次完成原生表块、MAT/HDF5 数组、多通道 NPY、体素与刚度配对、
Gmsh 网格和晶粒图的配置驱动适配，并接入现有 SamplePackage 与 HDF5/NPZ 流程。
`pipeline adapt` 可在样本元数据准备阶段读取文件、列出语义条件并生成报告。

## 实现与测试

| 部分 | 本次交付 |
|---|---|
| 原生表 | LIS 编码/小数逗号、区段和列选择、XLSX 工作表块、多行 CSV、逐块证据分类、显式单位换算 |
| 数值数组 | MAT5 变量/struct/cell、HDF5 切片、NPY 存储序、组件轴、质量数组与状态间不同实体数 |
| 标签配对 | 固定 loader 的原始行号映射、文件名/行数一致性、原列顺序、张量与剪切约定要求 |
| 网格 | Gmsh 2.2 ASCII 指定类型/维度、原始 ID、CFG 引用、Neper Rodrigues 及显式矩阵转换 |
| 图 | 原始节点 ID 与边索引、目标来源、自环策略、零节点与 padding、结构分组 |
| 集成 | `imports` 配置、部分导入报告、完整样本接入、HDF5/NPZ 往返、安装包 |

项目 `.venv` 完整离线测试：**440 passed，2 skipped，52.17 秒**。
相对于任务开始的测试集新增 69 项测试，包含最小合成正例和错误输入。
两个默认跳过项分别是安装 wheel 和真实 Abaqus 集成。安装 wheel 单独启用后
**1 passed，7.44 秒**。本轮执行范围为离线适配、容器和安装验证。

检查覆盖来源类别、字符串/稀疏 ID、原始行序、源/目标单位、MATLAB 类对象识别、
空间与组件轴、取向值、质量信息、跨来源依赖、目标分组，以及新旧配置兼容性。
完整代码检查结束后，后续修改集中在说明文档的表达方式。

最终构建包含一个 wheel 和一个 sdist，已核对九个新增适配模块及 `native` 可选依赖。
分发包中的 51 个实现/资源文件与当前源码一致。35 个改动文件均属于通用代码、
测试、合成示例和说明文档，依赖检查及差异格式检查通过。

## 代表性真实文件

真实数据回归共有 **18 项区块或来源检查**：15 项完成数值读取，2 项为头部检查，
1 项为 MATLAB 类对象原生引用。来源材料与详细报告位于本地忽略的 runs 目录。

| 来源 | 实际结果 | 后续所需信息 |
|---|---|---|
| KupferDigital LIS | 2,064 行，力由 kN 转 N，与既有显式子表一致 | 完整样本与材料建模信息 |
| AZ31B 工作簿 | 实验/模拟/EBSD 区块分别读取，57 条 XRD 载荷记录 | 部分块的单位、取向和试样对应 |
| SAC305 CSV | 两个试样保留独立原始行和曲线 | 原生时间单位 |
| Al-Mg MAT5 | 230×590×6 参数及质量数组 | 角度/PC 单位与空间映射 |
| HR-EBSD MAT struct | 十二个应力/应变分量 | 单位、间距、参考态与有效区域 |
| 3DXRD MAT cell | 五状态实体数 285/224/223/227/130 | 跨状态身份与完整物理约定 |
| 两个 EBSD HDF5 布局 | 按实际路径读取所选数组 | 各数据字段的物理解释 |
| 体素与刚度 | 一个 45³×4 NPY、原始标签行及文件配对，核对 4,000/1,000 行标签表 | 刚度单位、剪切尺度和发布数据生成链 |
| FEPX 小例 | 4,008 节点、2,453 个二阶四面体、20 组 Rodrigues、配套 CFG | 面向完整求解的坐标和后端约定 |
| PolycrystalGraph | 197 节点、2,832 个有向邻接项、5×2 目标 | 全零节点意义、单位、数据许可与分组 |
| Magma / CrackMNIST | NPY 存储序和 HDF5 实际布局 | 数据体、物理尺度及相关语义 |
| Ti DICInstance | 识别为 MATLAB 类对象并保留原生引用 | 作者类定义下的数值属性导出 |

刚度行号配对来自固定作者版本中的
[PFM_Stiffness_Dataset3d](https://github.com/BerryWei/Foundation-Model-for-Polycrystalline-Material-Informatics/blob/de9ebb3a6cf3242d12354bc55e5bd3648dfb1155/util/datasets.py)。
读取器保留原始 CSV 列顺序。单位及剪切尺度仍列在该来源的待补信息中。

各来源的读取、语义转换、完整样本条件、Solver Readiness 和物理验证分别记录。
本轮真实文件证据覆盖离线解析与部分表格转换。物理验证和求解按后续案例单独开展。

## 复核入口

```text
python -m pytest -q
python -m pip check
python -m build --outdir <new-output-directory>
pipeline adapt --config examples/synthetic_native/imports.yaml --run-dir <new-run-directory>
```

通用配置示例见 [native-adapters.md](../native-adapters.md)。本地真实回归脚本位于
`runs/native-adapters-20260906/regression.py`，可用新的输出目录名复跑。
`real-regression-final` 保存 18 项详细结果，`cli-real-final` 保存八组数组导入的命令行结果。
核心实现沿用通用配置，公开内容包含代码、说明和微型合成素材。

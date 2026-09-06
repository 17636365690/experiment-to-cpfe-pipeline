# HDF5→NPZ/PyG 派生导出：2026-09-05

## 完成结果

NPZ/PyG 现在以已核验 SHA-256 的 canonical HDF5 为唯一数据来源，不再接受
“内存样本 + 任意声称的 HDF5 哈希”。流水线的派生阶段也不重新读取 normalized
样本或提取目录来拼装数据。

全量测试 **176 passed, 2 skipped**，独立 wheel 安装测试另运行 **1 passed**；
构建和 git diff --check 通过。使用 torch-geometric skill 的 Data/显式图映射规则，
并按 TDD 先复现缺失与错误行为后实现、再进行实际导出验证。

## 修改文件

- `src/experiment_to_cpfe/datasets/package.py`：HDF5 源验证、完整 NPZ 内容、图契约
  校验、真正的 PyG Data、派生 provenance。
- `src/experiment_to_cpfe/pipeline.py`：派生阶段直接读取 HDF5，缺图/缺可选依赖等
  记录 blocked，不伪造成功产物。
- `tests/unit/test_derived_exports.py`：17 项导出/图契约测试。
- `tests/unit/test_hdf5_roundtrip.py`：改用真实 canonical HDF5 作为 NPZ 来源。
- `tests/unit/test_stage_integrity.py`：验证不重读输入及缺图时的 blocked。
- 本文和忽略上传的本轮配置、报告、测试产物。

之前各轮修改保留。本轮 API 兼容性变化：write_npz/write_pyg 的第一个参数现在是
HDF5 路径，不再是 SamplePackage；CLI 命令形式不变。

## NPZ 内容与限制

普通数组按原名保存；内部元数据键以双下划线开头，保留键或不安全数组名会被拒绝。
可使用 `numpy.load(path, allow_pickle=False)` 读取。

- `__sample_metadata_json__`：ID、系统单位、坐标和其他样本元数据。
- `__tables_json__`：所有表，包括 simulation_records、逐字段单位及观测记录。
- `__solver_inputs_json__`、`__asset_manifest_json__`、`__source_manifest_json__`：契约和来源。
- `__array_metadata_json__`：dtype、shape 和可 JSON 表达的 dtype 元数据；字节 ID 的
  `001` 与编码信息保留。
- `__source_hdf5_sha256__`、`__derivation_json__`：核验过的 HDF5 哈希、父资产 ID、
  源/目标格式和省略信息。

字段序列目前保留为 JSON 记录，不自动生成固定拓扑的稠密训练张量。object 数组、
结构化 dtype 和不能 JSON 表达的元数据须先显式规范化，不使用 pickle 绕过限制。
HDF5 存储布局、压缩和未建模属性不保留，已记入派生说明；不是 HDF5 的字节级备份。

## PyG 契约

需要 HDF5 内明确提供 graph_node_features、graph_edge_index、graph_node_ids，
以及 solver_inputs.graph_contract。节点 ID 必须唯一、非空，与特征行对齐。
edge_index 必须为整数 [2,E] 且在节点范围内，不能把浮点索引静默截断成整数。
节点特征和可选 graph_edge_features 必须有限；特征名、单位必须逐列明确声明。

graph_contract 示例（仅用于合成小样本，不是材料参数）：

```json
{
  "directed": false,
  "node_feature_names": ["synthetic_feature"],
  "node_feature_units": ["1"]
}
```

无向拓扑必须显式提供数量匹配的反向边；不自动加边或自环，不推断边特征的物理
对称性。有 edge features 时还须提供 edge_feature_names 和 edge_feature_units。

结果是真正的 torch_geometric.data.Data，而不是一个命名为 `.pt` 的普通字典。
包含 x、edge_index、可选 edge_attr、num_nodes、源哈希与派生记录；package_npz
保存完整 NPZ 内容，保留未对齐的场、观测、单位、ID 和其他数组。
**不自动创建 y**：字段到图节点/晶粒的训练目标映射需另行显式定义。

`.pt` 使用 PyTorch 序列化，不能加载不可信文件。本轮只加载自己刚生成的测试文件。
NPZ 内部无需 pickle；PyG 的全内容附带包会增加内存和存储开销，当前针对单个小样本，
不是大规模数据集的流式存储方案。

## 实际命令与环境

为实际验证 Data 对象，在项目 `.venv` 中安装 CPU 依赖，没有修改系统 Python、
没有安装 CUDA/可选加速扩展、没有训练模型。PyTorch CPU wheel 下载约 619.4 MB。

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install torch-geometric==2.7.0
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
$env:EXP2CPFE_WHEEL_DIR = 'dist'
.\.venv\Scripts\python.exe -m pytest tests\integration\test_installed_wheel.py -q
git diff --check
```

实测 torch=2.8.0+cpu、torch-geometric=2.7.0、torch.version.cuda=None。
安装依据：[PyTorch 官方版本说明](https://pytorch.org/get-started/previous-versions/)、
[PyG 官方最小安装说明](https://pytorch-geometric.readthedocs.io/en/2.7.0/install/installation.html)。

初始新导出用例与旧 NPZ 用例共出现 12 failed / 5 passed，暴露未实现的 HDF5 来源
验证和内容保留；另先复现了流水线重读输入、缺少派生记录、空节点 ID 和 dtype
元数据丢失。修复后全量通过。缺 PyG 依赖用例通过受控 ImportError 验证，要求无输出文件；
无 ml 依赖时实际 Data 测试明确 skip，其余离线测试无需下载这些依赖。

## 独立 smoke、哈希和证据

本轮目录：`runs/derived-exports-20260905/`。

- fields.npz 来自上一轮合成字段 HDF5；逐表、逐资产比较一致，S/LE 单位及 parent
  conversion 信息保留。
- graph.h5 明确加入两个合成节点（ID 101、909）、一个无量纲特征和两个反向边条目。
- graph.pt 成功加载为 Data，num_nodes=2、验证通过、y=None；嵌入 NPZ 的表和节点 ID
  与 HDF5 一致。

SHA-256：

- fields.npz：`fc2fe35867f5c824c278d88221b4acfd6c7219532eb98fcb1ed0bd3ad8eb6fbc`
- graph.h5：`0b27dc902a62afbb4d0d212a7c959bce906c11093a8e3725d19b3d5c58f8d918`
- graph.pt：`99e1409150c7fb6cd9e0b063c690a98538c07990cbaef497f5f95b6dc59b10d8`

四类报告、manifest 和校验和保留在本轮目录，构建产物另行归档。
没有本机私有案例，没有新 measured/inferred 科学证据；simulated 标签来自明确的
合成夹具，不能当成真实求解结果。所有构图值都是显式 input 测试声明，无参数猜测。
没有新 Abaqus 求解，没有 Github 上传。

下一步进行整体 schema/QA 与公共仓库审计，核对尚未完成的跨模态注册、物理单位/材料
契约和发布前条件。本轮完成派生格式验证，不代表 NTNU 或整个真实 CPFE 数据闭环已就绪。

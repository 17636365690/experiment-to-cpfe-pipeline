# Experiment-to-CPFE Pipeline Design

> 设计版本：2026-09-02

## 1. 目标

建立一个与具体数据集、材料体系和本地目录无关的实验—仿真—数据集互操作流水线，将结构化实验数据、显微组织数据和加载记录转换为可审计的仿真输入，驱动 Abaqus 等求解器产生真实结果，再将结果导出为机器学习和后处理代码可以稳定读取的轻量数据包。

第一阶段的核心闭环是：

```text
实验/显微数据
    -> 统一数据契约
    -> 仿真输入配置与 INP
    -> Abaqus 真实求解
    -> ODB 结果提取
    -> HDF5/NPZ 数据包
    -> 数据质量与来源报告
```

项目的核心价值是数据契约、适配器、可复现执行和证据追溯，而不是为某一个本地案例写一次性脚本。

## 2. 非目标与边界

- 实验数据不能直接伪装成 ODB。ODB 必须由 Abaqus 实际求解生成，实验数据只能作为输入、参数校准依据或独立验证目标。
- 第一版不承诺从任意显微照片自动重建网格；图像分割和网格重建将通过可替换的上游适配器接入。
- 第一版不自动猜测缺失的材料常数、坐标系、单位制、晶体取向或边界条件。缺少关键字段时，流水线必须失败并报告原因。
- 第一版不把某个材料、某个晶粒数、某种加载路径或某个文件名写入核心逻辑。
- 本地案例只作为测试夹具、格式适配和回归验证来源，不作为公共项目的固定输入或唯一使用方式。
- 不把原始实验数据、大型 ODB、检查点、第三方 UMAT 或未经确认许可的课程资料提交到公共 GitHub 仓库。

## 3. 使用场景

流水线应支持以下通用场景：

1. 从 EBSD、晶粒表或其他微结构描述构造晶粒和取向输入。
2. 从 CSV、TXT、JSON、HDF5 等格式导入应力–应变、载荷–位移或加载历史。
3. 将实验测得的几何、边界、材料和加载信息注入可配置的 Abaqus INP 模板。
4. 在本地可用的 Abaqus 环境中执行单样本或受控批次求解。
5. 从不同版本或不同命名习惯的 ODB 中提取公共字段。
6. 将结果保存为跨语言的 HDF5，并按需导出 NumPy 或 PyTorch/PyG 兼容格式。
7. 为每个样本建立实测、推断、输入和模拟结果之间的可追溯关系。

## 4. 总体架构

```text
                    +----------------------+
                    | Experiment adapters  |
                    | EBSD / CSV / DIC ... |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Versioned data schema |
                    | units / frames / IDs |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Validation and merge  |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Solver input adapter  |
                    | Abaqus first; DAMASK |
                    | and others later      |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Real solver execution |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Result extractor      |
                    | ODB / VTI / future    |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Dataset exporters     |
                    | HDF5 / NPZ / PyG       |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | Provenance and QA     |
                    +----------------------+
```

核心代码只依赖统一接口，不依赖某个本地项目路径。求解器、实验文件格式和导出格式都通过适配器实现。

## 5. 数据契约

每个样本使用稳定的标识字段：

```text
sample_id
experiment_id
microstructure_id
load_path_id
increment_id
```

统一元数据还必须包含：

```text
coordinate_frame
unit_system
tensor_order
orientation_convention
crystal_symmetry
source_kind
source_uri_or_path
source_hash
schema_version
```

数据对象分为六类：

### 5.1 几何与网格

- 节点坐标和节点 ID；
- 单元连接和单元类型；
- 网格尺寸、空间维度和边界标记；
- 几何来源与重建方法。

### 5.2 微结构与晶粒

- 晶粒 ID、相 ID、体积/面积、质心和尺寸统计；
- Euler angles、四元数或旋转矩阵；
- 取向约定、角度单位、晶体对称性和样品坐标系；
- 晶粒到单元或积分点的映射来源。

### 5.3 晶界和邻接

- 两侧晶粒 ID；
- 晶界长度/面积、法向和质心；
- 错配角及其计算约定；
- 相界、自由表面和周期边界标记。

### 5.4 材料与载荷

- 材料模型名称和版本；
- `PROPS`/材料卡字段及单位；
- UMAT/VUMAT 或其他本构实现的来源哈希；
- 位移、力、应变率、温度、时间和加载增量；
- 边界条件、参考点和周期约束定义。

### 5.5 实测观测

- 力—位移或应力—应变记录；
- DIC 位移/应变场；
- EBSD/显微组织测量；
- 测量误差、缺失值和仪器信息；
- 观测是否参与参数校准、训练或独立验证。

### 5.6 模拟结果

- 帧时间和增量 ID；
- 位移、应力、应变、塑性变量和 STATEV；
- 晶粒/元素/积分点定位；
- 宏观均匀化结果；
- ODB 哈希、求解器版本和提取器版本。

所有字段必须区分 `measured`、`inferred`、`input` 和 `simulated`，避免把推断值误报为实验事实或 Abaqus 结果。

## 6. 组件职责和接口

### 6.1 Experiment adapter

实验适配器负责读取一种具体来源，并返回统一的 `SampleDraft`。适配器不能自行改变物理含义；所有单位和坐标转换都要产生转换记录。

第一版提供通用表格适配器，接受带列名和配置映射的 CSV/TXT/JSON。EBSD、DIC 和仪器专用格式通过后续独立适配器加入。

### 6.2 Validator

校验器负责：

- 必需字段和类型；
- ID 唯一性与引用完整性；
- 单位和维度；
- 坐标系与张量顺序；
- 取向归一化和四元数合法性；
- 晶粒—网格映射；
- 加载增量连续性；
- 缺失值、重复帧和一对多标签；
- 训练/验证/测试分组信息是否完整。

校验器输出机器可读的 `validation.json` 和人类可读的报告，并按 error、warning、info 分级。

### 6.3 Solver input adapter

求解器适配器接收通过校验的标准样本和一个显式模板，输出求解器输入包。Abaqus 适配器第一版支持：

- 网格和单元；
- 材料和晶粒分区；
- 取向与 `PROPS` 注入；
- 边界条件、PBC 和参考点；
- 载荷步和输出请求；
- 用户子程序引用；
- 生成文件的来源清单。

适配器必须在生成 INP 后执行静态检查，不应依赖 Abaqus 运行后才发现基本的 ID、节点集或材料映射错误。

### 6.4 Solver runner

runner 负责将输入包放入 ASCII-only 临时目录，执行 datacheck、编译/链接和 analysis 阶段，并记录：

- 完整命令；
- 解释器和求解器版本；
- 工作目录和环境变量摘要；
- 输入文件哈希；
- `.sta`、`.dat`、`.msg`、`.odb` 等产物；
- 每个阶段的状态和失败原因。

默认只运行单个 smoke job。批量运行必须显式指定规模、并发数和输出根目录。

### 6.5 Result extractor

Abaqus 提取器使用 `odbAccess` 读取真实 ODB，并转换为与求解器无关的中间结果对象。提取器需要适应字段缺失、不同位置和不同命名，但不能静默用零替代缺失物理量。

第一版优先支持：帧时间、U、S、LE、PEEQ、SDV、元素/积分点标签、晶粒 ID 和宏观读出。不存在的字段写入缺失报告，并由配置决定是 warning 还是 error。

### 6.6 Dataset exporter

HDF5 是正式跨语言格式，目录结构固定为：

```text
/meta
/geometry
/mesh
/grains
/grain_boundaries
/load_history
/measured
/simulation
/macro_response
/provenance
/quality
```

NPZ 和 PyTorch/PyG 导出属于派生格式，必须携带 HDF5 数据包的来源哈希，不允许成为唯一事实来源。

## 7. 命令行和配置

CLI 使用配置驱动，而不是把路径和材料名称写进代码：

```text
pipeline init
pipeline validate --config configs/sample.yaml
pipeline build-inp --config configs/sample.yaml
pipeline run-abaqus --run-dir runs/sample-001
pipeline extract-odb --run-dir runs/sample-001
pipeline export --run-dir runs/sample-001 --format hdf5
pipeline inspect --run-dir runs/sample-001
```

配置必须允许用户指定：

- 原始数据路径；
- 模板路径；
- 单位和坐标转换；
- 求解器命令；
- UMAT/VUMAT 路径；
- ASCII 临时目录；
- 输出目录；
- 需要提取的字段；
- 失败阈值和质量门。

任何会覆盖已有结果、启动 Abaqus 或产生大量输出的命令，都必须要求显式输出目录；默认不覆盖。

## 8. 运行产物和可追溯性

每次运行创建独立目录：

```text
runs/<sample_id>/<run_id>/
├── input/
│   ├── normalized_sample.json
│   ├── model.inp
│   └── input_manifest.json
├── solver/
│   ├── job.odb
│   ├── job.sta
│   ├── job.dat
│   └── job.msg
├── dataset/
│   ├── sample.h5
│   └── sample.npz
└── reports/
    ├── run_manifest.json
    ├── validation.json
    └── qa_report.md
```

`run_manifest.json` 至少记录：

- 原始输入哈希；
- 配置哈希；
- 模板哈希；
- UMAT/VUMAT 哈希；
- 求解器命令和版本；
- 提取器版本；
- 输出文件哈希；
- 每个阶段的开始、结束和状态；
- 仍未解决的限制。

## 9. 分阶段交付

### Milestone 0：通用项目骨架

建立 Python 包、配置加载、CLI、日志和运行目录管理。用合成样本验证，不依赖 Abaqus。

### Milestone 1：数据契约和表格导入

支持 CSV/TXT/JSON，完成单位、坐标、取向、ID、加载历史和证据类型校验。

### Milestone 2：Abaqus INP 适配器

完成模板注入、材料/取向映射、PBC 和输出请求，生成一个可静态检查的 INP。

### Milestone 3：单样本真实求解

实现 ASCII 临时目录、datacheck/analysis 阶段分离、真实 ODB 产物检查和失败收据。

### Milestone 4：ODB 到 HDF5

从一个真实 ODB 提取公共字段，生成可跨语言读取的数据包和宏观曲线回读检查。

### Milestone 5：适配器扩展和公共示例

增加 DAMASK/VTI 或其他求解器的接口设计；提供合成 fixture 和不含私有数据的示例。现有本地 Abaqus/DAMASK/EBSD 案例只用于本地回归，不进入核心假设。

### Milestone 6：批处理与下游接口

在单样本证据链稳定后，加入受控批处理、数据集分组清单和 PyG/其他训练框架导出。

论文级可视化不属于第一版核心，但后续可通过读取 HDF5、manifest 和模型输出增加独立的 `report` 模块。

## 10. 测试策略

### 无求解器测试

- schema 合法/非法样本；
- 单位和坐标转换；
- 取向归一化和对称性元数据；
- 晶粒/元素 ID 映射；
- INP 模板渲染；
- HDF5 写入和读取；
- manifest 哈希和重跑一致性；
- 缺失字段、重复增量和无效路径的错误报告。

### Abaqus 集成测试

- 最小线弹性模型；
- 最小单晶或双晶模型；
- UMAT datacheck；
- 一个真实 analysis job；
- ODB 字段提取；
- 从 ODB 恢复宏观响应并与求解器摘要核对。

### 科学边界测试

- 实测和模拟记录不可混淆；
- 源单位未知时必须阻止带单位结论；
- 缺少 STATEV 时不能默认为全零；
- 同一加载路径的增量不能被拆到不同分组；
- 旋转和取向表示必须带坐标/对称性说明；
- 求解器成功不自动等于材料验证成功。

## 11. 公共 GitHub 发布策略

公共仓库发布流水线代码、schema、配置模板、合成小样本、测试和文档，不发布：

- 原始实验数据；
- 大型 ODB/CAE/检查点；
- 未确认许可的 UMAT、课程文件或论文附件；
- 含本机路径、账号、令牌或内部文件名的 manifest。

CI 在没有 Abaqus 的环境中运行 schema、模板、导出和报告测试；Abaqus 集成测试标记为本地可选测试，并提供用户手工执行命令。

## 12. 成功标准

第一版完成时，用户可以用一份不属于现有本地案例的标准化样本完成：

```text
导入实验/微结构数据
→ 通过数据校验
→ 生成 INP
→ 真实运行 Abaqus
→ 产生 ODB
→ 导出 HDF5
→ 读取并核对关键字段
→ 获得完整 provenance 和 QA 报告
```

成功不以“所有脚本退出码为 0”定义，而以每个阶段都有明确输入、输出、证据、限制和可重复路径定义。

# 通用训练数据层设计

本任务的方向、范围和直接实施已获用户确认。开始实施时 main 工作区干净，未发现适用的 AGENTS.md。采用架构设计、自检、TDD 和完成前验证流程。复核完成后，用户已确认提交并推送到 origin/main，随后检查远端 CI。

## 方案与接口

采用独立构建阶段：规范化 HDF5 → 配置选取与身份对齐 → 训练 NPZ → 现有 MLP。把合并逻辑留在案例脚本会继续复制实现；把 HDF5 解释直接放入训练器会混合数据契约与优化过程。独立阶段复用 SamplePackage、资产来源和训练器，便于单独复核数据。

- `datasets/training_config.py`：严格配置模型，未知键报错。
- `datasets/training_columns.py`：提取表列或数组分量、解析单位和来源、验证行身份。
- `datasets/training.py`：`build_training_dataset(config, *, base_dir)` 返回内存 TrainingDataset；`run_dataset_build(config_path, output_dir)` 写出数据与记录。
- `learning/data_contract.py`：共享分组约束和训练包语义检查。
- `pipeline build-training-dataset --config ... --run-dir ...`：构建命令。

配置使用 version=1；features 是有序的 name/unit 列表，target 为单一 name/unit；layouts 定义按这些名字索引的列选择器和 alignment_evidence。inputs 显式列出相对配置文件的 HDF5 路径、预期 sample_id、layout、split，可在 explicit 分组时提供 group_id。group_by 为 sample_id、experiment_id 或 explicit，grouping_evidence 记录分组依据。所有配置内容写入机器记录。

## 选择、对齐和单位

表选择器指定保留表名、column、id_columns 和可选等值 where。通过行内 source_asset_id/source_kind 或选择器显式 asset_id 绑定来源，后者兼容现有 ODB 提取表；若同时存在两种绑定，必须一致。单位从资产 normalized_units 或 units 读取；ODB value 字段使用记录的 field/unit。数组选择器指定 array、asset_id、ids、row_axis 和其余轴的 component 索引；数组资产必须绑定 array_key。ids 是与记录轴同长的唯一整数/非空字符串向量。单分量只输出一个标量列。

每列声明 source_unit；unit_key 可选择已声明的资产单位键，已有 component/field 语义优先核对，不能借配置覆盖冲突。转换仅支持显式 affine：value * factor + offset，提供 reason，factor 非零且所有数值有限。源/目标单位不同必须声明转换，不推断单位换算。数值必须是实数，拒绝布尔、数字字符串、非有限值。

每个 layout 提供非空 alignment_evidence。列按显式行身份严格一对一对齐，保留第一特征的顺序；重复、缺失或额外身份报错。然后对所有列应用同一个 rows（start/stop/step，零起点、stop 不含，正向、有界）。记录原始行索引与身份。没有默认截短、插值、聚合、空间配准或展平。

## 分组和泄漏

全局拒绝重复 sample_id、重复文件路径或内容；多个样本可属于同一组，但组不能跨划分。所有 train/validation/test 均需至少两行，与 train_mlp 共用约束。输入已有 dataset_split 或原生目标 group_id/split 与新配置冲突时报错。

检查目标资产的根来源在不同划分间复用：按内容摘要匹配；同一 URI 的任一记录缺少摘要时，按共同 URI 匹配。共享特征或标定资产不自动视为目标复用。同一根来源的目标可在同一划分供多个样本使用，行身份仍各自唯一。无法识别未登记或被错误声明的共同来源；分组依据与上游资产身份必须由数据提供者正确给出。

## 产物与兼容性

新建输出目录包含 dataset.npz、dataset.json、training-config.json、build-manifest.json。NPZ 含 features、targets、groups、splits、sample_ids、row_ids 和版本化 JSON 元数据。JSON 保留字段顺序/单位、完整样本元数据/资产/source_manifest、列选择和转换、行位置与分组依据；文件摘要绑定配置、HDF5 与产物。训练包与普通无损 NPZ 导出使用不同格式标记。

training-config.json 可直接交给 train-surrogate。旧 NPZ 与旧训练配置继续可用；遇到新训练包时核对配置的字段顺序和单位，拒绝语义错配，将数据摘要和构建记录绑定到训练结果。所有输入检查在创建输出之前完成，已有路径拒绝覆盖。

## 验收与范围

Python >=3.12，使用项目 .venv；构建数据只依赖基础包，CPU 优化使用 training extra。测试先红后绿，两个独立合成布局均完成构建、实际 CPU 优化、checkpoint 读回与评估；覆盖表行重排、数组非首记录轴、单位转换、来源、分组冲突、身份错误、无效配置和语义篡改。增加 CPU 训练 CI，完成一次全量离线回归、wheel/sdist 构建与源码目录外安装验证。

保留公开 CuSn8Ni2 的 H_08/H_16/H_18 分工、0–0.8% 窗口及 12 个算例/84 阶段结果；不重新求解或训练。案例中的物理归约与插值仍属于案例处理。无多模型、批量求解、恢复、独立预测、发布或外部试用功能。Apache-2.0 与公开 tensile CC-BY-4.0 范围不变。

自检：接口与验收逐项对应；训练集只声明数据选取与已知对齐，不推断新的科学关系。重复来源判定限定目标来源，避免将共享标定参数误判为目标泄漏。

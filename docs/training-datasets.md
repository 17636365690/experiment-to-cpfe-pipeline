# 从规范化样本构建训练集

`build-training-dataset` 按配置合并多个项目 HDF5 文件，输出供标量回归 MLP 使用的 NPZ。特征和目标可以来自表列，也可以来自数组分量。构建器按行身份对齐数值，检查单位与分组，并保存选取过程和来源。

在当前源码安装基础依赖即可构建数据。训练需要 `training` extra：

```text
python -m pip install -e ".[training]"
pipeline build-training-dataset --config build.yaml --run-dir runs/dataset-001
pipeline train-surrogate --config runs/dataset-001/training-config.json --run-dir runs/model-001
```

每次使用新输出目录。输入路径相对配置文件所在目录解析，也支持绝对路径。生成的 `training-config.json` 可直接运行，或添加 `epochs`、`patience`、`seed`、`hidden` 和 `learning_rate`。训练器继续使用训练集拟合归一化参数，用 validation MSE 选择 checkpoint，最后报告各划分的误差和均值基线。

## 配置一组表数据

下面的配置读取三个规范化样本。表中每行有 `increment`、`extension`、`stiffness` 和 `force`，且绑定了 `source_asset_id` 与 `source_kind`。来源资产声明这三个数值字段的单位分别为 mm、N/mm 和 kN。

```yaml
version: 1
features:
  - {name: extension, unit: mm}
  - {name: stiffness, unit: N/mm}
target: {name: force, unit: N}
group_by: sample_id
grouping_evidence: 每个样本对应一个独立参数案例
layouts:
  curve:
    alignment_evidence: 同一增量的输入和响应使用相同 increment
    columns:
      extension:
        kind: table
        table: measured_observations
        column: extension
        id_columns: [increment]
        source_unit: mm
      stiffness:
        kind: table
        table: measured_observations
        column: stiffness
        id_columns: [increment]
        source_unit: N/mm
      force:
        kind: table
        table: measured_observations
        column: force
        id_columns: [increment]
        source_unit: kN
        conversion: {factor: 1000, offset: 0, reason: kN 转 N}
inputs:
  - {path: a.h5, sample_id: case-a, layout: curve, split: train}
  - {path: b.h5, sample_id: case-b, layout: curve, split: validation}
  - {path: c.h5, sample_id: case-c, layout: curve, split: test}
```

`features` 的顺序就是模型输入顺序。每个 layout 的 `columns` 必须完整对应特征名和目标名。不同文件可以指定不同 layout，因此字段改名或数组布局变化可通过配置处理。

表选择器的 `where` 按值筛选，例如 `where: {source_asset_id: sensor-A}`。`id_columns` 可以是复合身份，如 `[step, frame, node_label]`。每列的身份集合必须相同且唯一，输出保留第一特征的顺序。目标行顺序不同会按身份重排，缺行或多行会报错。

已有 ODB 提取表在资产清单中记录来源。这类表在选择器中填写 `asset_id`，指向
`odb-extraction-bundle` 资产，再用 `where` 选择 field/component。若行中已有来源绑定，
显式 asset_id 必须与它一致。`value` 列的单位同时核对资产字段单位和行内 unit。

表字段更名后，若资产单位表仍保留原键，可用 `unit_key` 显式关联。例如
`column: response, unit_key: load` 表示 response 使用已登记的 load 单位。
选中列已有的单位声明仍参与核对，别名不能覆盖冲突的单位。

在 layout 下添加 `rows: {start: 0, stop: 20, step: 2}`，可以从对齐后的数据中取每隔一行的前 20 行。索引从 0 开始，stop 不包含在内。该选择同时作用于全部特征和目标，越界或空选区会报错。

## 配置数组分量

对于形状为 `[channel, row]` 的 `channels`，可以这样选择第二个通道：

```yaml
kind: array
array: channels
asset_id: channels-normalized
ids: increment_ids
row_axis: 1
component: [1]
unit_key: gain
source_unit: V
```

`asset_id` 指向的资产必须通过 `descriptive_metadata.array_key` 绑定此数组。`ids` 指定唯一整数或字符串向量，其长度等于记录轴长度。`component` 按剩余轴的自然顺序给出索引，每个轴恰好选一个分量。一维数组使用 `row_axis: 0` 和空 component，这也是默认值。

`unit_key` 从资产单位表中选取单位，默认使用数组名。原生导入已登记的分量名称、entity_ids 和 entity_axis 会参与核对。多维场的聚合或空间配准应先在上游完成，并将处理结果和依据写回规范化包。

## 单位与分组

每列的 `source_unit` 必须与资产中的单位一致。表适配器已换算过的字段使用 `normalized_units`，ODB 的 `value` 列还会核对记录的 `field` 和 `unit`。输出单位由 features/target 声明，单位变化需要显式 conversion。转换执行 `value * factor + offset`，reason 记录依据。构建器不推算换算系数。

| group_by | 分组身份 |
| --- | --- |
| `sample_id` | SampleMetadata.sample_id，例如一个样本对应一个试样 |
| `experiment_id` | SampleMetadata.experiment_id，同一实验的多个样本共用一组 |
| `explicit` | 每个 input 提供 group_id，适用于跨文件试样身份或参数案例 |

同一组的所有行属于一个划分，train、validation、test 各至少两行。多个样本可以共用一组。重复样本身份、重复 HDF5 内容、同组跨划分，以及对已有 `dataset_split` 或原生目标 group/split 的冲突都会报错。

构建阶段还检查目标资产的根来源：同一目标根来源出现在不同划分时拒绝构建，共享特征和标定资产不触发此检查。这个规则按来源文件归组，尚未细分同一原始文件中的多个独立试样。内容摘要相同，或同一 URI 的任一记录缺少摘要时，都会检查来源复用。上游需要保留稳定的来源身份。

## 查看构建与训练记录

| 文件 | 内容 |
| --- | --- |
| `dataset.npz` | features、targets、groups、splits、sample_ids、row_ids，以及 JSON 元数据 |
| `dataset.json` | 字段单位、完整配置、样本元数据、资产链、源清单、原始行索引、转换和分组 |
| `training-config.json` | 数据路径、字段声明和数据内容绑定，可追加模型设置 |
| `build-manifest.json` | 构建状态、配置与输入记录、各输出文件校验信息 |

读取数值使用 `np.load(path, allow_pickle=False)`。`row_ids` 中每项都是一个 JSON 列表，保留复合身份及整数/字符串区别。训练后的 `dataset-receipt.json` 保存所用数据与配置的对应记录，`training.json` 给出收据位置。

训练 NPZ 的格式标记为 `experiment-to-cpfe-training-1`。它保留选中的数值和来源说明，未选字段留在原 HDF5。`pipeline export --format npz` 则保存单个完整 SamplePackage，二者用途不同。

旧的四数组训练 NPZ 和训练配置仍可使用。完整 SamplePackage NPZ 中若已包含 features、targets、groups 和 splits，也保留原有训练入口。对新训练包，`train-surrogate` 还会核对字段顺序、单位及内容记录，格式标记和元数据必须完整。构建器接收项目规范化 HDF5，厂商 HDF5 先通过相应适配器解释和规范化。

[合成示例](../examples/synthetic_training/README.md) 提供两套可直接生成的输入。公开 tensile 案例继续使用原有物理归约和插值步骤，已记录的应变窗口与评估分工保持不变。

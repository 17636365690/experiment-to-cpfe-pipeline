# 字段单位与提取 provenance：2026-09-05

## 完成结果

提取包标准化现在要求每个实际字段有明确单位，生成独立提取资产及 ODB 父资产，
并把文件哈希与格式转换记录写入 Asset 模型。HDF5 往返保留字段单位、记录值、
父子关系、源文件验证状态及转换信息。

测试结果：**157 passed, 2 skipped**；另外启用独立 wheel 安装测试得到 **1 passed**。
wheel/sdist 构建和 git diff --check 通过。本轮使用 TDD，先复现失败再实现；
最终运行全量、构建、安装及文件级校验，不把局部通过当作完整流水线通过。

## 修改文件

- `src/experiment_to_cpfe/assets/models.py`：新增可选 ConversionRecord；检查转换父资产、
  源哈希和格式一致性，拒绝父子环路。
- `src/experiment_to_cpfe/solvers/abaqus/extraction.py`：严格字段单位、父子资产、提取包
  独立哈希、本地源 ODB 哈希核验、未知许可保留 None。
- `src/experiment_to_cpfe/config.py`、`pipeline.py`：接入 `abaqus.field_units`，提取结果
  不符合数据契约时记录 failed，而不是进入可导出状态。
- `tests/unit/test_extraction_provenance.py`：14 项测试，含 HDF5 往返。
- 提取/pipeline 原测试及 `tests/fixtures/odb_extract_fixture/metadata.json`：合成夹具
  明确声明 S、LE 单位，不再依赖从全局单位自动推断。
- 本文和忽略上传的运行产物。HDF5 读写器无需新增特例，既有 JSON 元数据路径可保留新字段。

之前各轮修改和原始文件全部保留，没有覆盖历史运行目录。

## 单位契约

配置示例仅表示显式声明形式，不是对任何未知材料的单位建议：

```yaml
abaqus:
  field_units:
    S: MPa
    LE: "1"
    SDV_phi1: degree
```

上述映射必须由模型提供者确认；缺失、unknown 等占位符会失败。键必须对应实际输出
字段名：`SDV: "1"` 不能覆盖 SDV_phi1 或其他具名状态变量。
标准化的 simulation_records 每行有 unit，提取资产 units 按字段名记录；样本的
unit_system 继续保留系统级声明，但不能替代字段级声明。已有 CSV unit 列与声明
冲突时失败，不覆盖冲突值。

兼容性变化：旧提取包只有 unit_system 而没有 field_units 时，不能再直接标准化。
可继续检查原始 JSON/CSV，但必须补充有依据的声明，不能自动补签单位。
本轮没有实现量纲代数、单位别名转换或验证 SDV 的物理意义。

## 父子与哈希契约

- ODB 父资产保留原生 ODB URI、声明的文件 SHA-256 和 simulated 证据类别。
- 提取资产 parent_asset_id 指向该父资产，format 为 odb-extraction-bundle。
- 提取资产 SHA-256 不再复用 ODB 哈希，而是对按文件名排序的
  `{"frames.csv": 文件哈希, "metadata.json": 文件哈希}` 紧凑 JSON 计算 SHA-256
  （UTF-8、sort_keys=True、separators=(",", ":")）。因此同一 ODB 的不同提取内容可区分。
- ConversionRecord 记录 original_format、target_format、source_sha256、
  target_file_hashes 和 source_hash_verified。
- source_hash_verified 仅表示本地可访问原件的文件哈希匹配，不表示求解器真实性或
  材料科学验证。原件不在本机时为 False，父资产只是外部引用；原件存在却哈希不符则失败。
- 未知许可保留 None，不再默认声称 user-generated。
- 字段选择和展开的有损信息明确记录；它们不是完整 ODB 的无损替代。
- ConversionRecord 对旧资产是可选字段；不会替所有历史适配器自动补造转换记录。

## 实际执行与产物

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_extraction_provenance.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
$env:EXP2CPFE_WHEEL_DIR = 'dist'
.\.venv\Scripts\python.exe -m pytest tests\integration\test_installed_wheel.py -q
git diff --check
```

首批 10 项测试均先失败，随后通过；进一步复现单位列冲突、环路、来源校验状态和
配置字段缺失，再完成修复。另验证 SDV 组声明不会覆盖具名字段。

独立小样本运行在 `runs/field-provenance-20260905/`：复制明确标注为合成的中间提取
夹具，调用 load_extraction_bundle、write_hdf5、read_hdf5，比较完整 records 和以 ID
索引的全部 Asset 对象。S=Pa、LE=1，两个父子资产和转换记录均保持一致。
该夹具的 STATEV 缺失说明仍被保留，没有补零；外部 ODB 不存在，来源哈希验证为 False。

HDF5 SHA-256：
`192f524b9e92361695fc0a858fffc35549fcf6f16824b5bf35a8f381b1b0d929`。

四类报告、主 manifest、manifest 校验和与归档构建产物在该运行目录。
另外只读尝试标准化上一轮真实 U 提取结果，得到预期的
`missing or unresolved field unit: U`；没有为其创建 HDF5，也没有修改它的原始元数据。

## 证据、限制和下一步

本轮的 HDF5 是**合成序列化测试包**，不是 CPFE 训练数据。夹具中的 simulated 标签
仅用于验证证据分类；不代表真实求解。没有新增 measured 或 inferred 科学数据。
声明与测试配置属于 input；未使用本地私有实验案例，未运行新的 Abaqus 求解，未上传
GitHub。原件未知单位、未知许可、未验证来源均保持显式状态。

现阶段仍需完善字段的物理意义/量纲验证、所有适配器的转换记录、容器导出 provenance、
NPZ/PyG 对字段序列的完整承载。NTNU 单位问题没有通过默认值绕过。
下一阶段可优先完善 HDF5→NPZ/PyG 派生导出，确保模拟记录和单位不会在导出中丢失；
真实 CPFE 数据闭环仍须先取得明确的样本单位与材料契约。

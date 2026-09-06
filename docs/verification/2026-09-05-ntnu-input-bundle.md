# 固定版本公开输入包接入：2026-09-05

## 结果与范围

已下载并验证 NTNU Crystal Plasticity 项目固定提交
`27daafa01c0e0e916591371342de36e4bbdd6bb5` 的 14 个必要文件，共 271792 字节。
每个文件的实际 SHA-256 均与筛选阶段固定清单一致；固定提交的 LICENSE 明确为 MIT。
公开仓库只保存下载清单、通用代码、合成测试和本文，不保存下载的材料卡或 UMAT。

来源：[NTNU 固定版本](https://gitlab.com/ntnu-physmet/project_metplast/crystal_plasticity/-/tree/27daafa01c0e0e916591371342de36e4bbdd6bb5)、
[MIT 许可](https://gitlab.com/ntnu-physmet/project_metplast/crystal_plasticity/-/blob/27daafa01c0e0e916591371342de36e4bbdd6bb5/LICENSE)。

该示例的实际结构为 **1331 个节点、1000 个单元、30 个晶粒集合**。
检查确认：单元连接引用的节点均存在；所有单元恰好分配到一个晶粒集合。
RVE10 不是“10 个晶粒”。这些数字只属于此可选集成样本，未写入核心代码。

## 本轮新增文件

- `configs/public_sources/ntnu_ri_27daafa.json`：来源、固定提交、许可及逐文件哈希。
- `src/experiment_to_cpfe/solvers/abaqus/bundle.py`：通用递归 INCLUDE 依赖检查与原样暂存。
- `tests/unit/test_input_bundle.py`：21 项合成测试。
- 本文及忽略上传的 `runs/ntnu-bundle-20260905/reports/` 下的四类阶段报告。

上轮运行器及其测试的未提交修改保留，本轮没有覆盖这些修改。

## 暂存契约

`stage_input_bundle(entrypoint, source_root=..., submission_dir=..., destination=...,
license=..., auxiliary_files=...)` 返回实际暂存入口、提交目录和依赖回执路径。

```python
from pathlib import Path
from experiment_to_cpfe.solvers.abaqus.bundle import stage_input_bundle

source = Path("local-inputs").resolve()
bundle = stage_input_bundle(
    source / "Example/main.inp",
    source_root=source,
    submission_dir=source / "Example",
    destination=Path("runs/example-001/native-inputs"),
    license="unknown",  # Replace only with verified source license metadata.
    auxiliary_files=(),
)
```

- 嵌套相对路径一律相对于提交目录，遵循
  [Abaqus 输入语法](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEMODRefMap/simamod-c-inputsyntax.htm)，
  不相对于子 INP 所在目录。保留相对目录结构和全部原始字节。
- 支持完整拼写的 INCLUDE/INPUT、双引号、续行和未加引号路径的空格规则。
- 越界、绝对路径、驱动器相对路径、符号链接、循环、歧义/不支持的文件引用会报错。
- 目的目录即使为空也不能复用；源与目的树不能重叠。
- 默认上限：4096 个文件、32 MiB 输入、64 层嵌套；前两项可显式配置。
- 写入前完成依赖扫描；使用已经验证的字节快照。I/O 失败时保留部分目录，禁止复用。
- 回执为 `input-bundle-1` 依赖格式，不冒充完整 SamplePackage 或 Solver Readiness。
  每个复制文件有 raw 父资产、源/目标格式、输入证据类型、哈希和空的有损操作列表。
  字节复制不改变 raw 数据层级。Fortran、LICENSE 等辅助文件不冒充网格或实验表格。

## 执行和测试

通过 GitLab Repository Files API 读取固定提交的 base64 内容，在写入前核验哈希，
使用独占新建方式保存原文件。所有 14 个原件均在忽略上传的
`runs/public-data/ntnu-27daafa/raw/` 内。

暂存 API 已实际用于该包。首轮暂存保留在 `runs/ntnu-bundle-20260905/staged/`；
最终实现重新验证并写入全新的 `staged-final/`，没有覆盖首轮或原件。
最终回执含 28 条原件/副本资产记录和 10 条 INCLUDE 边。

实际测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_input_bundle.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
git diff --check
```

TDD：先执行 18 项失败测试；实现后 18 项通过。随后先复现缩写文件参数漏检、
容量上限缺失的 3 项失败，再修复为 21 项通过；另验证原样复制必须保持 raw 层级，
观察其失败后修复。最终全量 **97 passed, 1 skipped**。wheel/sdist 构建成功。
这些测试不需要网络、Abaqus 或公开原件。

阶段 manifest 关联固定来源清单、源/副本回执、代码、报告和逐文件 SHA-256；
manifest 自身校验和另存，避免自引用。私有绝对路径只存在于忽略上传的运行回执。

## 证据、假设与限制

- 本轮原件和副本均为 **input**，不是 measured；没有运行求解，因此没有本轮 simulated
  结果，也没有 inferred 材料参数。未使用本机私有实验案例。
- `umat_CPRI.for` 的 `euler2rotm` 明确注明角度为 degree；具体矩阵约定仍以该固定
  版本函数为依据，不未经验证映射为其他工具的 Bunge/主动旋转约定。
- 已检查的 README、输入文件未明确声明完整物理单位体系。不能根据 C11、密度等数值
  自动认定为 MPa/mm。检索关联论文时出版社正文返回 403，未获得可用于补齐该输入包
  单位的确证。没有绕过访问限制或向维护者发送消息。
- 无格式转换、无有损转换、无 INP 重写、无 ODB/HDF5/ML 数据生成。
- 辅助 Fortran 依赖尚不解析；此 UMAT 引用的 `aba_param.inc` 属于 Abaqus 安装环境。
  支持范围外的原生文件引用不能被认为依赖完整。
- 本 API 只负责暂存，尚未接入 CLI 的分阶段隔离目录和完整语义 Gate；材料、坐标、
  张量和单位映射仍须显式验证。此次未启动 datacheck/analysis，未上传 GitHub。

下一阶段：获取该示例明确的单位与坐标元数据，完成 SamplePackage 映射及 Gate，
再接入隔离的 datacheck/analysis。若无法确认原始物理单位，只能把它保留为原生输入
格式测试，不能标注为具备明确物理单位的 CPFE 训练样本。AZ31B 实验样本保持独立。

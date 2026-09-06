# 安装资源与 ODB 提取语义：2026-09-05

## 结果

本轮修复了安装后资源定位，扩充了真实 ODB 提取的字段身份和缺失检查。
常规测试 **143 passed, 2 skipped**；独立 wheel 安装测试单独启用后 **1 passed**；
wheel/sdist 构建成功。两个默认跳过项分别是可选真实 Abaqus 集成与需预先构建 wheel
的安装测试。

使用 Abaqus Python 对之前官方 DISP 小样本的真实 ODB 只读提取位移 U，得到
**105 条分量记录**。再次独立读取 ODB，按加载步、帧、实例、节点和分量逐条比对，
数值全部精确一致；最大绝对位移数值为 75.39368438720703，未附加未经确认的单位。
ODB SHA-256 前后一致：
`15063b989238f2d13663c270e3708e2ef32d90e7042f99f8ef4bbae56c77bbef`。

## Skills 和修改文件

采用 python-pypi-package-builder 的现有包布局与安装验证流程，保留 setuptools/src
和现有版本，不迁移后端、不发布 PyPI。采用 TDD 先观察失败，再实现修复；实际 Abaqus
API 差异按 systematic-debugging 排查，最后执行完成前验证。

- `_resources/abaqus_extract_odb.py`：随包安装的独立 Abaqus Python 脚本，仅依赖标准库
  和 Abaqus 自己的 odbAccess，不导入主环境 numpy/pandas。
- `_resources/validation_policy.yaml`、`_resources/__init__.py`、`pyproject.toml`：
  打包运行时资源。根目录 `configs/validation_policy.yaml` 仍是参考模板，运行时使用包内副本。
- `scripts/abaqus_extract_odb.py`：保留仓库使用方式的薄启动器，不复制实现。
- `solvers/abaqus/extraction.py`：从包内定位脚本，传递记录上限，保留文本标签与声明单位。
- `config.py`、`pipeline.py`：接入 extraction_position 和 extraction_max_records。
- `schema/validation.py`：多位置同帧字段不再误判为重复 increment；改为检查字段位置/分量键。
- 新增 `tests/unit/test_packaged_resources.py`、`test_odb_script_semantics.py` 和
  `tests/integration/test_installed_wheel.py`，扩充提取、pipeline、validation 测试。

## 提取契约

1. 支持 native、nodal、integration_point、element_nodal、element_face、centroid
   位置选择，仅筛选已有值，不触发自动外推或基底变换。
2. CSV 保留 step、frame、实际 increment_number、domain、frame_value、load_case、
   instance、position、node/element、积分点、截面点、face、precision、局部坐标矩阵、
   原始 component label 和 value。
3. frame_time 只用于 TIME 域，且明确为步内时间。频率/模态值保留在 frame_value，
   不虚构为全局时间。
4. 每个请求字段、每个帧都检查是否有对应位置的记录。缺失写入 missing_by_frame，
   返回非零，不补零。STATEV/SDV 按原生 SDV 名称展开。
5. 依据原生 precision 读取 data 或 dataDouble。Abaqus 2025 返回的 NumPy 数组通过
   序列接口处理；写入 CSV 前转为 Python float，以保留 float32 的精确提升值和 float64。
6. 脚本逐行输出，默认最多 1000000 条标量分量记录。达到上限返回失败，保留部分结果
   和错误报告。原有输出目录不复用。
7. 复数场尚不支持，明确报错，不能静默丢弃虚部。无效分量标签/非有限值也不能完成。
8. 可读取的字段组件/类型信息写入描述记录；isEngineeringTensor 不可读取时保留 null，
   不猜测其值。主环境不再把系统单位硬写成 Pa/s，也不把 `001` 之类的文本标签转成整数。

依据：[FieldValue 数据和精度接口](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-fieldvaluepyc.htm)、
[OdbFrame 时间/频率域](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-odbframepyc.htm)、
[FieldOutput 接口与外推行为](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-fieldoutputpyc.htm)。

## 实际命令与 TDD 证据

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
$env:EXP2CPFE_WHEEL_DIR = 'dist'
.\.venv\Scripts\python.exe -m pytest tests\integration\test_installed_wheel.py -q
git diff --check
```

资源与单位测试先出现 3 项失败；核心脚本语义测试先出现 8 项失败；随后复现标签、
记录上限、同帧多位置、重复字段和复数场的失败用例并修复。配置转发也先观察到
不支持新字段的失败。

真实运行额外发现两处夹具差异：FieldOutput 不提供 isEngineeringTensor 读取属性，
data 是 numpy.ndarray 而非 tuple/list。分别新增失败测试后修复。另以失败测试复现
float32 短字符串表示造成的额外数值舍入，再修复。

实际提取命令（通过已配置的本机 wrapper 执行）：

```powershell
& .\runs\toolchain\abaqus_with_oneapi.bat python .\src\experiment_to_cpfe\_resources\abaqus_extract_odb.py --odb runs\compiler-recheck-20260905\runner-analysis\toolchain_analysis.odb --output-dir runs\odb-extraction-20260905\real-u-validated --fields U --position nodal --max-records 10000
```

另用 Abaqus Python 独立构建 ODB 中全部 U 的位置/分量字典，与 CSV 字典及记录数比对。
wheel 测试用 pip --no-deps 安装到临时目录，在仓库外以隔离子进程导入安装包，
验证包来源、包内策略、CLI validate 和提取脚本 --help。依赖复用已有测试解释器，
不是从空白操作系统验证全部依赖安装。

## 产物、provenance 与限制

本地输出在 `runs/odb-extraction-20260905/`。失败尝试和较早试提取目录保留，
最终结果仅以 `real-u-validated/` 为准。报告包含主 manifest、validation、
solver_readiness、QA；manifest 关联源 ODB、脚本、最终 JSON/CSV、构建产物及哈希。
原始 ODB 没有覆盖；本轮没有启动新的求解，也未上传 GitHub。

真实位移记录属于 **simulated**，提取参数属于 **input**；没有新增 measured 或 inferred
材料数据。使用本机已有官方验证例只为可选集成验证，没有使用私有实验案例。
字段选择本身会省略未请求场、网格及其他 ODB 内容，因此不是完整 ODB 的无损替代；
选中的 105 个数值逐条验证未改变，选择/展开操作有记录。

未知单位未补齐，未将此 DISP 例导出为有物理单位的 HDF5/ML 样本。此次只实测了 U，
没有把 S/LE/PEEQ/STATEV 的合成测试当作真实 CPFE 提取通过。逐个 SDV 的物理意义与
单位、全部复杂元素位置、旧版 Abaqus Python 2、复数场均需后续专门验证。
通常 pip 解压安装 wheel 的方式已验证；不保证直接从 zip 导入资源后启动外部脚本。

下一步完善字段级单位与提取资产的父子 provenance，并以小样本验证 HDF5 round-trip；
NTNU 原生样本仍保持 blocked，直到其完整单位元数据有依据。

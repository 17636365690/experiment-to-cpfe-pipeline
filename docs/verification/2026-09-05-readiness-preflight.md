# 单位 Gate 与求解前检查：2026-09-05

## 结果

修复了两个实际缺口：单位未完整声明的 SamplePackage 原来仍可能被判定为
solver-ready 并生成 INP；`run-abaqus` 原来仅确认报告文件存在，没有再次执行数据
校验和 Readiness Gate。现在两条路径均检查前置条件，缺失项记录为 blocked，
在进入运行器之前返回，不依赖 Abaqus 自己报错。

## 修改文件与验证

- `schema/validation.py`：针对 `abaqus_cpfe` 要求 length、stress、time 的明确声明，
  拒绝空值及 unknown/native units/TBD 等占位符；要求坐标长度单位与样本声明一致，
  不自动做单位转换。
- `pipeline.py`：求解前重新组装样本，执行现有 validation 和 readiness，写入
  `reports/abaqus_<stage>_preflight.json`。失败阶段进入 manifest，但不调用运行器。
- `tests/unit/test_validation.py` 与 `tests/unit/test_pipeline.py`：新增 10 项回归用例，
  包含绕过 INP 生成、缺失材料参数以及求解前拦截。
- `configs/public_sources/ntnu_ri_27daafa_conventions.json`：固定版本的约定证据记录。
  它不是可执行 SamplePackage，未知物理单位保留 null。

实际先执行测试得到 **9 failed, 13 passed**；实现后 **22 passed**。
离线 smoke 又暴露出占位符单位在通用 validation 中仍显示 passed 的报告矛盾；
补充失败测试后统一检查，现在 validation 和 readiness 均拒绝占位符。
最终全量测试 **107 passed, 1 skipped**；wheel/sdist 构建成功。

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_validation.py tests\unit\test_pipeline.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
git diff --check
```

另用合成配置执行 validate 和 run-abaqus/datacheck：将该配置的 stress 单位设为
明确的缺失占位符 unknown，验证 blocked 状态、preflight 报告以及空求解目录。
首轮 smoke 保留在 `runs/readiness-preflight-20260905/`；最终实现使用新目录
`runs/readiness-preflight-final-20260905/`，两个 CLI 命令均按预期返回 1，QA 报告
显示 MISSING_UNIT，求解目录为空。这些配置不属于公开原件。
全部源代码和配置均沿用已有改动，没有覆盖之前的私有原件或运行目录。

## NTNU 元数据证据

固定提交与 UMAT 文件哈希参见约定 JSON；没有修改第三方 Fortran。

- 源码明确使用 degree。初始化将 `euler2rotm` 的 Q 转置为 R；后续通过
  `R^T A R` 将全局张量转入晶体基底。此处只记录源码定义，不假定与其他工具
  的同名 Euler 约定完全等价。
- 开头注释把 23 放在 13 前面，但主程序的 STRESS 组装和回写实际使用
  **11,22,33,12,13,23**；因此不能只复制注释中的顺序。
- UMAT 工程剪应变约定不应被盲目应用到所有 ODB/STATEV 字段。后续提取必须保留
  字段 componentLabels、位置和具体含义。参见
  [Abaqus UMAT 文档](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-umat.htm)。
- `_sets.inp` 的空 `*SYSTEM`、几何和角点定义提供原生全局坐标依据；完整物理
  单位体系仍没有确证。关联论文的其他几何尺寸不能直接移植到这个固定输入包。

## 证据分类、产物和限制

本轮只检查公开 **input** 源码；没有新增 measured、simulated 或 inferred 材料数据。
测试中的 measured 标签属于已有的合成夹具，不是真实测量。没有有损转换，没有
运行真实求解，没有新增 ODB/HDF5/ML 包，没有上传 GitHub。

阶段四类报告由离线 smoke 生成。其 manifest 关联配置、校验、readiness 和求解前
检查；代码、源约定 JSON 与 QA 另有本轮 evidence_manifest.json 校验清单。

限制必须保留：本次是**声明完整性和求解前检查**，不是完整的物理量维度分析。
尚未实现任意单位别名归一、完整材料参数量纲检查、不可变输入快照绑定、原生包
CLI 分阶段隔离，以及所有跨模态语义检查；不能据此宣称完整 Gate 已通过审计。
NTNU 样本仍不具备完整物理单位声明，保持不求解。

下一步可以继续完善不依赖该单位声明的输入快照绑定和分阶段隔离。真实 CPFE
数据生成前，必须取得来源支持的单位说明，或由模型提供者明确声明单位；不能
把基于常见数值的猜测包装成原始数据事实。

# 导出门槛修复：2026-09-06

## 本轮结果

已修复上一轮独立复现的两项导出缺陷：

1. `validation.passed=false` 的数据不能正式导出 HDF5、NPZ 或 PyG，即使存在旧版本
   错误生成且已登记的 HDF5，也不能继续派生。
2. manifest 中一旦有 extract-odb 记录，就必须满足提取完成及产物完整性条件。
   将目录移走不能使导出退回成不含模拟记录的包。未登记目录也仍然被拒绝。

数据有效性和 Solver Readiness 保持分开：只有缺少求解材料/网格等条件、但数据
校验通过的曲线-only 样本，仍允许 HDF5/NPZ 导出，不生成 INP 或模拟记录。

## 修改文件

- `src/experiment_to_cpfe/pipeline.py`：依据 manifest 和目录状态联合确定提取依赖；
  在所有正式导出前检查已绑定数据校验结果；校验固定提取产物的登记哈希。
- `tests/unit/test_export_gates.py`：13 项回归用例，覆盖三种格式、三种提取状态、
  原有校验/哈希证据不被改写，以及有效实验数据的正向导出。
- `docs/runbook.md`：解释导出数据门槛与 solver readiness 的区别。
- 本文；忽略上传的独立 smoke、报告及构建归档。

既有源文件、历史审计报告和运行目录均保留。本轮没有修改材料假设、单位、适配器
语义或第三方源文件。

## TDD 与实际验证

使用 test-driven-development 技能：首轮 **6 failed, 1 passed**，确认失败原因分别
是错误完成状态或缺少正确的 validation 拦截原因；实现后 7 项通过。随后将提取
状态/格式组合扩充为 13 项，全部通过。

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_export_gates.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
$env:EXP2CPFE_WHEEL_DIR = 'dist'
.\.venv\Scripts\python.exe -m pytest tests\integration\test_installed_wheel.py -q
.\.venv\Scripts\python.exe runs\export-gates-fixed-20260906\smoke.py
git diff --check
```

最终全量 **189 passed, 2 skipped**；独立 wheel 安装测试 **1 passed**；构建通过。
跳过项仍是默认关闭的真实 Abaqus 集成和需显式指定构建产物的 wheel 测试。

独立 smoke 新建三个合成 run，结果为：

| 场景 | HDF5 导出 | 其他核验 |
|---|---|---|
| 重复晶粒 ID、数据校验失败 | blocked | 没有生成 HDF5 |
| 已登记提取产物移走 | blocked | 原提取数据留在同一 smoke 目录内，未删除 |
| 有效曲线-only 数据 | completed | NPZ 也完成；readiness=false，无 INP |

## 产物、证据与限制

`runs/export-gates-fixed-20260906/` 保存 smoke.py、smoke_results.json、三个独立 run
和总报告。每个 run 都保留 validation、solver_readiness、qa_report 和 run_manifest；
总 manifest 记录报告与归档构建产物哈希，校验和单独保存。

所有案例都是合成测试，提取阶段使用明确的合成账本记录；没有真实求解，没有新增
measured/inferred/simulated 科学证据。没有使用本机私有实验数据，没有猜测单位、
补零或对原始数据做有损转换，没有上传 GitHub。

本次修复作用于 pipeline 的正式导出入口。低层 HDF5 序列化函数仍可用于保存待审查
测试对象，其成功不代表数据通过 validation。已绑定校验结果只代表当前校验器与策略
的覆盖范围，不等于完整材料物理正确性验证。

上一轮审计报告保持为修复前的历史证据。本轮仅关闭其中两个导出缺陷，整体发布审计
仍不通过：结构化 Readiness、原生 INCLUDE CLI 接线、维护性建议和文档路径清理仍待完成。
下一步优先推进原生输入包的依赖绑定/暂存接线，并继续保持未知单位的 NTNU 样本不求解。

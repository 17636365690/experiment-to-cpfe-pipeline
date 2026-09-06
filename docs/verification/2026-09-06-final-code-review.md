# 初版工作区双轴审查

以下两个报告由独立代理针对 `909fa2fca9f651c77176008341fd64abd34b38dc` 到工作区
的更改分别给出。行号是审查时快照；保留发现原文，修复状态单列。

## Standards

基准已确认：`origin/main=909fa2fca9f651c77176008341fd64abd34b38dc`；HEAD 未新增提交，本次检查工作区差异及未跟踪的新模块。未发现独立编码规范或 linter 配置，以项目 runbook 和 Fowler 基线评估。

硬性问题：

1. `src/experiment_to_cpfe/pipeline.py:511`：提取阶段忽略 `EXP2CPFE_ABAQUS_COMMAND`，违背 `docs/runbook.md:132` 的配置/环境命令约定。最小复现：配置 `command: [abaqus]`，设置环境变量为 `chosen-wrapper`，替代进程入口捕获参数；提取仍调用 `abaqus`，而分析阶段会调用环境指定命令。可能出现真实分析完成后无法提取。
2. `src/experiment_to_cpfe/pipeline.py:515`、`:522`：提取超时没有捕获 `subprocess.TimeoutExpired`。替代进程入口直接抛出该异常，`run_extract_odb` 随之退出，无法记录阶段失败；CLI 异常集合也不包含该类型。分析阶段已有进程组终止与超时收据，提取仍走独立实现。应复用一致的进程执行和失败记录逻辑。

判断性维护建议：

- **Duplicated Code / Data Clumps**：`pipeline.py:169`、`:259` 与 `provenance/binding.py:18` 重复组合 native bundle 的 source_root、entrypoint、submission_dir、auxiliary_files、限制参数。同一辅助依赖规则需要多处同步，建议归并为一个显式输入快照请求。此项属于维护性判断，不阻断发布。

本轴：2 项可复现硬性问题、1 项判断性建议；最严重问题为提取超时逃逸并遗漏阶段收据。审查全程只读，未启动求解器。

## Spec

1. P1 — Missing field units still pass table ingestion. Requirement: “源单位未知时必须阻止带单位结论”. adapters/tabular.py:40-61 checks mapped columns but not mapped units. Reproduced using public sample’s first source with units={'time':'s'}: stress_33/strain_33 rows normalize and validate reports passed=True/issues=[]. Export gate therefore accepts unit-incomplete data.
2. P1 — Source evidence can contradict canonical simulation records. Requirement: “所有字段必须区分 measured、inferred、input 和 simulated”. adapters/tabular.py:79-81 merges solely by table_name; datasets/hdf5.py:36 maps simulation_records to /simulation. Reproduced first source with source_kind=MEASURED, table_name='simulation_records': asset says measured, records occupy simulation table, validation still passes. Rows retain no source binding.

Documented partial capabilities (not newly found silent corruption): generalized registration/time synchronization, full vendor binary EBSD/DAMASK/Neper semantics, history-output/homogenization and arbitrary native Abaqus profiles remain explicitly limited in docs/limitations.md. No scope-creep finding. Summary: 2 confirmed Spec blockers, worst silent missing-unit/evidence acceptance.

## 修复后的验证

Standards 两项硬性问题均修复：提取与求解共用实际命令解析、批处理参数检查和
拥有进程组的执行入口。超时有终态记录和日志；环境命令回归测试先失败后通过。
native 参数聚合仍是后续维护建议，传递依赖和辅助文件完整性已有回归保护。

Spec 两项均修复：每个映射字段必须声明单位，表格逐行绑定原始来源和证据类别，
模拟记录与观察记录的来源冲突会失败。另补充原始表格到规范化子资产的转换记录
及 HDF5 双向逻辑载荷哈希验证，防止格式/字段选择损失没有 lineage。

修复后的完整本机测试为 **371 passed、2 opt-in skipped**；随后启用 wheel 和真实
Abaqus 集成，分别 **1 passed**。详细命令、真实求解解释与产物指纹见
[发布验收报告](2026-09-06-initial-release-acceptance.md)。

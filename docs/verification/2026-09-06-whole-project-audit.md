# 整体 QA 与公共仓库审计：2026-09-06

## 结论：本轮审计不通过，不发布

E 盘恢复后，按 talocode-code-review 技能对两个独立轴并行审查，主任务另做测试、
构建、安装、公开文件检查和缺陷复现。基线为
`909fa2fca9f651c77176008341fd64abd34b38dc`；审查范围为相对该 HEAD 的工作区改动及
非忽略新增文件，不是仅审查已提交 diff。基线之后没有新提交。

未修改生产代码、没有提交/推送、没有重写 Git 历史、没有运行 Abaqus 或模型训练。
新增内容仅为审计说明，以及忽略上传的诊断脚本、合成复现目录和证据报告。

## 实际验证

- `python -m pytest -q`：**176 passed, 2 skipped**。
- `python -m build`：wheel 和 sdist 成功。
- 设置 `EXP2CPFE_WHEEL_DIR=dist` 后单独运行
  `tests/integration/test_installed_wheel.py`：**1 passed**。
- `git diff --check`：通过。
- 在新增合成目录运行 `runs/public-audit-20260906/reproduce_exports.py`：两项缺陷均复现。
  第一项使用重复晶粒 ID，确认 validation.passed=False 但 HDF5 导出 completed；第二项
  使用明确的合成提取阶段记录，将其测试目录移到同一审计目录内的保留位置，确认
  导出 completed 且没有 simulation_records。没有删除原件，也未伪装为真实求解。

上述 Python 均使用项目 `.venv` 解释器。测试通过仅说明当前测试覆盖通过，不能消除
已被额外复现证明的缺陷，也不能证明完整 CPFE 数据闭环已实现。

## 公共文件边界

初次扫描包含 99 个已跟踪或非忽略新增候选文件，总计 364284 字节；本审计说明加入后
再扫描的最终清单保存在本地 candidate_audit.json。范围没有排除设计/计划文档。

- 未发现候选原始 ODB/CAE、Fortran 源、检查点、HDF5/NPZ 数据产物或大于 2 MiB 的文件。
  这只是类型/大小检查，不能代替所有文件的语义或许可审查。
- 对候选文本和 2 个可达提交执行了 GitHub/AWS/OpenAI 令牌及私钥头模式扫描，未命中。
  不输出潜在凭据原文；模式扫描不是穷尽的 secret detection。
- 计划文档第 1098 行有绝对安装路径示例。它不是凭据泄漏，但不符合用户严格的
  “公共代码/文档不含本机绝对路径”边界，应改为通用命令名或配置占位形式。
- 同文档第 1059、1133 行是禁止路径规则/审计表达式；测试第 63 行是故意拒绝绝对路径
  的负例。不能把这些一律当成真实数据泄漏，也不应删除负例而削弱测试。
- 旧计划的审计命令排除了 docs/superpowers；后续应移除此排除，避免漏审文档。
- 项目级根 LICENSE 尚未见于候选文件，许可证选择仍应明确，不能由助手伪造授权。
  公开来源清单的 MIT 声明不等同于整个项目已采用 MIT。

下面保留两个审查轴的报告，不合并或跨轴排序。

## Standards

未发现独立 CODING_STANDARDS、CONTRIBUTING、EditorConfig 或 linter 规范。参考实现计划的 typed contracts、模块边界要求及 Fowler 基线；以下均为维护性判断，不是已证实的硬性违规。

1. **[P2，Duplicated Code] 默认校验策略出现双份来源。**
   `src/experiment_to_cpfe/_resources/validation_policy.yaml:1` 完整复制 `configs/validation_policy.yaml`；`pipeline.py:137` 已改为仅加载前者。后续修改配置目录中的 `require_finite: true` 等规则不会影响运行，且没有一致性测试。建议确立唯一权威文件，删除或明确标注另一份为示例；若保留镜像，由构建生成并测试一致性。

2. **[P2，Mysterious Name / Data Clumps] 编译结果命名与实际含义相反。**
   `solvers/abaqus/runner.py:118–121`：`compiler_status = link_status = compile_status`；其中 `compile_status` 实际表示编译与链接的汇总结果，而 `compiler_status` 最终写入结果对象的 `compile_status`。多个退出分支又以位置参数传递这三个字符串（例如 `:245`）。建议将汇总变量改为 `compile_link_status`，实际编译变量改为 `compile_status`，并采用关键字构造结果对象，降低记录错误状态的风险。

3. **[P2，Shotgun Surgery / Primitive Obsession] 新增字段契约散落在三个独立字段清单。**
   `_resources/abaqus_extract_odb.py:48` 定义 CSV 列，`solvers/abaqus/extraction.py:83` 决定数值转换列，`schema/validation.py:201` 决定唯一位置键。增加一种位置标签需要同步修改三处，遗漏可能让不同位置被误判为重复。建议在可供独立 Abaqus 脚本使用的纯标准库模块中定义版本化字段契约，并让主环境加载、校验复用。

Standards：3 项判断性发现，0 项确认的硬性违规；最重要的是默认校验策略双份来源导致修改可能静默失效。

## Spec

1. **[wrong，新 guard 缺口]** `src/experiment_to_cpfe/pipeline.py:395` 按提取目录是否存在决定前置要求。完成提取后目录丢失或改名，会跳过 simulated 数据，仍导出 `completed` HDF5。违反“每个阶段都有明确输入、输出、证据”。应依据 manifest 阶段记录要求提取产物并核验哈希。

2. **[wrong，遗留缺陷]** `src/experiment_to_cpfe/pipeline.py:394` 的 HDF5 导出没有数据校验门槛；`validation.passed=false` 的重复晶粒 ID 等样本也可导出成功。违反“缺少关键字段时，流水线必须失败并报告原因”。应区分实验样本仅 solver-not-ready 与真正的数据校验失败，后者阻止正式导出。

3. **[missing，遗留未完成]** `src/experiment_to_cpfe/schema/validation.py:244` 仍通过 truthy 字典检查映射、材料与边界；声明存在不代表实际数据完整，不能核对配置与生成 INP 是否一致。未满足“ID 唯一性与引用完整性”“晶粒—网格映射”。应增加结构化材料/映射契约及内容检查。

4. **[missing，新增能力尚未接线]** `src/experiment_to_cpfe/solvers/abaqus/runner.py:166` 仍只复制主 INP；新增 `stage_input_bundle` 未接入 CLI，输入锁也不捕获 INCLUDE 依赖。尚未实现“将输入包放入 ASCII-only 临时目录”“输入文件哈希”。应统一接入依赖快照、暂存及分阶段哈希核验。

Spec 轴共 **4 项**；最严重的是已登记提取产物丢失后仍可静默导出成功。未发现明确范围扩张。

## 交付与下一步

本地 `runs/public-audit-20260906/` 保存候选清单、复现脚本、合成案例、四类报告、
run_manifest.json 及校验和。复现产物只是审计测试，没有新增 measured/inferred/simulated
科学证据；本机真实 ODB、公开 NTNU 原件、私有实验资料均未用于本轮复现。

后续修复顺序：先把两个已复现的导出缺陷写为失败回归测试并修复；再完成结构化
Readiness 与 INCLUDE 接线；分别处理 Standards 建议和文档路径。修复后重新进行
双轴审查及公共文件检查，不能以本轮绿色测试替代发布门槛。
公共数据真实 CPFE→HDF5 闭环、NTNU 完整物理单位和部分适配器语义仍未最终验收。

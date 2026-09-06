# 输入绑定与阶段隔离：2026-09-05

## 完成范围

本轮将输入内容绑定与执行顺序检查接入现有 pipeline 高层 API/CLI。
未确认单位的 NTNU 原生样本仍不求解，没有扩展材料假设或提交 GitHub。

使用的 skills：brainstorming 用于核对已批准的有界改动范围；
test-driven-development 用于先复现问题再实现；verification-before-completion
用于全量测试、独立 smoke、构建及产物哈希复核。本轮无需创建子任务。

## 修改文件

- `src/experiment_to_cpfe/provenance/binding.py`：输入绑定的捕获、比对和已登记产物验证。
- `src/experiment_to_cpfe/pipeline.py`：阶段入口检查、规范化样本复用、独立求解目录、
  旧 manifest 哈希保留、提取/导出前置条件、求解后输入复核。
- `tests/unit/test_stage_integrity.py`：17 项跨阶段完整性测试。
- `tests/unit/test_pipeline.py`：导出正向测试改为经过合成求解及提取阶段，不再直接
  注入未登记的提取目录。
- 本文；忽略上传的本轮运行配置和运行证据。

之前各轮未提交修改全部保留。

## 行为与兼容性

1. validate 捕获配置、所有配置声明的 sources/assets、验证策略、可选模板和
   Fortran 文件的 SHA-256，写入 `input/input_lock.json`。组装前后比对原件。
2. 规范化样本、input lock 及初始四类报告的哈希进入 manifest。后续 build、run、
   extract、export 均检查绑定，并读取已验证的 normalized_sample.json，不重新导入原件。
3. 配置或原件变化、规范化文件变化、绑定丢失均阻止继续；旧 run 缺少绑定不能自动补签。
   应新建 run 重新验证，不修改旧基线使它“通过”。
4. build-inp 要求成功 validate；datacheck 要求成功 build-inp；analysis 要求成功
   build-inp 和 datacheck，且前置阶段产物哈希仍匹配。
5. datacheck 使用 `solver/datacheck/`，analysis 使用 `solver/analysis/`。提取只读取
   analysis 的 ODB，不能借用 datacheck 或旧根目录的 ODB。
6. 任何已记录阶段都不允许重复执行，包括 blocked/failed。需要重试时创建新 run；
   已有阶段目录、提取目录也不能复用。此规则避免覆盖既有证据。
7. 追加阶段保留既有 `config_sha256` 和历史产物哈希，不对旧文件重新计算并覆盖基线。
   完整性失败会写独立 blocked 报告，不调用求解进程。
8. 求解后再次检查输入绑定和已生成 INP；发现执行期间变化则记录 failed，保留日志。
9. 提取结果必须报告与登记 ODB 匹配的哈希，且 missing_fields 为空才能 completed。
   存在提取目录时，export 要求该提取阶段成功且登记文件哈希不变。
   NPZ/PyG 导出还要求已登记的 HDF5 阶段成功、产物哈希匹配。

## 实际命令与测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_stage_integrity.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
git diff --check
```

TDD 记录：首轮 11 failed / 1 passed；完成输入绑定与隔离后通过。
随后新增 4 项失败测试，分别暴露未登记提取绕过、运行时输入变化、提取 ODB 哈希
不匹配和缺失字段；修复后通过。最后复现“失败 validate 仍能 build INP”并修复。
最终全量 **124 passed, 1 skipped**。跳过项是显式 opt-in 的真实 Abaqus 集成测试。

独立 CLI smoke 使用 `runs/toolchain/isolated-offline-20260905.json`，其 solver command
明确指向测试夹具，不是本机 Abaqus。只在命令进程内清空 Abaqus 环境覆盖，没有修改
持久环境变量。实际执行：

```powershell
python -m experiment_to_cpfe.cli validate --config runs/toolchain/isolated-offline-20260905.json --run-dir runs/isolated-offline-20260905
python -m experiment_to_cpfe.cli build-inp --config runs/toolchain/isolated-offline-20260905.json --run-dir runs/isolated-offline-20260905
python -m experiment_to_cpfe.cli run-abaqus --config runs/toolchain/isolated-offline-20260905.json --run-dir runs/isolated-offline-20260905 --stage datacheck
python -m experiment_to_cpfe.cli run-abaqus --config runs/toolchain/isolated-offline-20260905.json --run-dir runs/isolated-offline-20260905 --stage analysis
```

上述 python 为项目 `.venv` 解释器。四阶段均返回 0；独立目录和产物哈希验证通过。

## 产物、证据与假设

smoke 保存四类阶段报告、input_lock.json、规范化样本、生成 INP、两个独立目录和
stdout/stderr。主 manifest 记录这些文件的 SHA-256；evidence_manifest.json
另记录本轮实现、测试和说明文件哈希，manifest.sha256 独立保存两份 manifest 的校验和。

本轮未使用本机私有实验案例，也未重新运行公开 NTNU 样本。输入全为合成测试数据；
原有夹具中的 measured/simulated 标签仅用于验证分类，不构成真实测量或真实仿真证据。
夹具写出的 `.odb` 文件是显式假产物，不能用 Abaqus 打开或用于科学结论。
没有新真实 ODB、材料校准、推断单位或有损转换，没有上传 GitHub。

## 限制与下一步

- 绑定检查检测意外修改，不提供数字签名或恶意同时篡改 manifest 的防护。
- 当前支持单写入者执行，不提供并发阶段事务、进程崩溃后的自动恢复或文件系统锁。
- 检查配置声明的文件；尚未绑定完整求解器安装、环境变量、编译工具链和间接 Fortran
  include 依赖。NTNU 原生 INCLUDE 包仍需进一步接入 CLI，此处未自动生成它的契约。
- 低层 `run_abaqus` 是独立执行工具；本轮顺序和绑定约束位于 pipeline 高层入口。
- 运行前后哈希复核不能排除文件在两次检查间被修改又恢复的恶意竞争条件。
- ODB 逐帧缺失字段、字段位置/组件、单位映射以及安装后脚本资源可用性尚需专门完善；
  本次接通目录与来源检查不等于完整 ODB→HDF5 语义闭环验证。
- 任意单位维度分析和完整材料语义 Gate 仍未完成。NTNU 完整物理单位体系仍未确认。

下一步优先修复安装包内的配置/提取脚本资源定位，并验证 ODB 提取的逐字段语义；
保持公开样本 blocked，直到其所需元数据有明确依据。

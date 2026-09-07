# 通用训练数据层 Implementation Plan

> **For agentic workers:** 按本计划在当前任务逐项执行并自检。用户已要求完成实现，无需再次选择执行方式；环境未提供 executing-plans，采用当前会话的 TDD 检查点。完成复核后，用户已确认提交并推送到 origin/main，随后检查远端 CI。

**Goal:** 用配置把多个规范化样本转成带身份、单位和来源的标量回归训练包，接入现有 MLP。

**Architecture:** 独立数据构建器复用 canonical HDF5 读取和资产契约。字段选择、身份对齐和分组验证与 CPU 优化分离，训练器共享分组约束并识别新包元数据。

**Tech Stack:** Python >=3.12、NumPy、h5py、Pydantic 2、PyYAML、pytest；可选 CPU PyTorch。

**Spec:** `docs/superpowers/specs/2026-09-07-training-dataset-design.md`

## Global Constraints

- Python >=3.12，使用项目 .venv；构建数据只依赖基础包，CPU 优化使用 training extra。
- 不修改冻结的 tensile 案例、原始资产、运行结果、版本或许可范围。
- 实施前运行失败测试；所有输入检查在创建输出之前完成，已有路径拒绝覆盖。
- 配置显式声明科学含义，单一标量目标，不推断插值、聚合、配准或单位换算。

### Task 1: 配置、提取与内存训练集

**Files:** 创建 `src/experiment_to_cpfe/datasets/training_config.py`、`training_columns.py`、`training.py`、`src/experiment_to_cpfe/learning/data_contract.py`；创建 `tests/unit/test_training_dataset.py` 和合成 fixture。

**Interfaces:** `TrainingDatasetConfig.model_validate(payload)`；`build_training_dataset(config, *, base_dir: Path) -> TrainingDataset`。结果提供 features/targets/groups/splits/sample_ids/row_ids/metadata。

- [x] 添加合成表与数组包，手工检查列顺序、Pa/kPa 换算、重排行身份以及来源。
  ```python
  data = build_training_dataset(config, base_dir=tmp_path)
  assert data.features[:2].tolist() == [[0.0, 1.0], [0.25, 1.0]]
  assert data.targets[:2].tolist() == [0.0, 0.25]
  ```
- [x] `.venv/Scripts/python -m pytest -q tests/unit/test_training_dataset.py`，确认缺失入口导致失败。
- [x] 实现严格模型、表/数组标量提取、单位一致性、显式转换、键对齐与选行。
  ```python
  order = [column.ids.index(key) for key in anchor.ids]
  aligned = column.values[order]
  transformed = aligned * factor + offset
  ```
- [x] 添加并运行失败测试：重复样本、组跨划分、目标根来源跨划分、已有 split 冲突、缺列/单位/身份、无效类型、空选区。
- [x] 实现全局注册表，复用 `validate_group_splits(groups, splits)`；重新运行本文件及 HDF5/派生导出相关测试。

### Task 2: 持久化、CLI 和训练兼容

**Files:** 更新 `datasets/training.py`、`learning/data_contract.py`、`learning/surrogate.py`、`cli.py`；新增 `tests/integration/test_training_dataset_pipeline.py`，补充 `tests/unit/test_surrogate_training.py`。

**Interfaces:** `run_dataset_build(config_path: Path, output_dir: Path) -> dict`；保留 `run_training(config_path, output_dir)` 和 `train_mlp(...)` 既有签名。

- [x] 测试 `build-training-dataset` 创建非 pickle NPZ、JSON 记录和可用训练配置；断言存在输出时原文件保持。
  ```python
  assert main(['build-training-dataset', '--config', str(config), '--run-dir', str(out)]) == 0
  assert main(['train-surrogate', '--config', str(out/'training-config.json'), '--run-dir', str(model)]) == 0
  ```
- [x] 运行上述新测试确认命令不存在；实现命令路由和输出记录。
- [x] 添加语义错配/载荷变化拒绝测试，运行确认旧训练器不检测新包；实现新格式检查与训练数据收据。旧四数组 NPZ 保持兼容。
- [x] 两个布局各完成 800 epoch 上限的小型 CPU 优化；检查 loss 下降、优于均值基线、test NRMSE < 0.05、模型读回与已存预测一致，train-only 归一化。

### Task 3: 示例、说明与交付验证

**Files:** 创建 `examples/synthetic_training/prepare.py` 和 README；创建 `docs/training-datasets.md`；更新根 README、schema、limitations、native-adapters、runbook、CI；创建本次 verification 记录。

- [x] 合成示例生成两套独立 HDF5/config；集成测试执行同一示例入口，避免示例漂移。
- [x] CPU CI 在 Ubuntu 安装 CPU torch 和 training extra，显式 import torch 后执行训练单元与两布局集成测试。
- [x] 文档给出配置、构建/训练命令、身份与单位规则，解释 canonical package NPZ 与训练 NPZ 的区别。
- [x] 运行一次全量 `.venv/Scripts/python -m pytest -q -rs`，记录准确数量和跳过原因。
- [x] `.venv/Scripts/python -m build --outdir runs/training-data-20260907/dist`；`twine check --strict`；用候选 wheel 在源码目录外执行新入口，并从 sdist 检查打包文件。
- [x] `git diff --check`，核对修改范围、需求覆盖及机器记录；保留未提交改动交付。

自检：三个任务覆盖设计全部接口与验收；组检查只有一个共享实现，旧 API 不增加必填参数；训练 CI 的实际远端状态须与本地验证分开报告。

### 复核修复记录

- [x] 摘要与 URI 的目标来源索引覆盖摘要缺失的两种输入顺序，跨划分时拒绝构建。
- [x] 旧完整 SamplePackage NPZ 保持训练兼容，新训练包缺少格式标记时拒绝按旧包读取。
- [x] 更名表列可通过 unit_key 显式关联已有单位键，保留既有列单位及 ODB field 的一致性检查。
- [x] 新增 7 个回归用例完成红绿验证；针对性测试 73 passed，完整回归 535 passed、2 skipped。
- [x] 重新构建 wheel/sdist，源码目录外安装 1 passed。当前候选及审查记录保存在 `runs/training-data-20260907/review-1/`。

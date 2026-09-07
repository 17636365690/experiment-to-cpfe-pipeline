# 两种规范化布局的标量回归

示例生成两套独立训练输入，每套四个样本、每个样本 31 行。数值来自 `y = x * gain`，来源标为 `input`，并记录为合成生成器。

表数据使用 extension、stiffness 和 force，演示 kN 转 N。数组数据使用 `[channel, row]` 布局，目标数组倒序保存，通过整数身份恢复对应关系。两套配置共用核心构建器。

在仓库根目录运行：

```text
python -m pip install -e ".[training]"
python examples/synthetic_training/prepare.py --output-dir runs/training-inputs
pipeline build-training-dataset --config runs/training-inputs/table/build.yaml --run-dir runs/table-dataset
pipeline train-surrogate --config runs/table-dataset/training-config.json --run-dir runs/table-model
pipeline build-training-dataset --config runs/training-inputs/array/build.yaml --run-dir runs/array-dataset
pipeline train-surrogate --config runs/array-dataset/training-config.json --run-dir runs/array-model
```

训练前可在生成的 `training-config.json` 中加入 `epochs: 800`、`patience: 300`、`seed: 17`，这组设置用于小型 CPU 验收。默认设置与既有 MLP 一致。查看模型目录下的 `training.json` 和 `predictions.npz`，可以比较测试误差、均值基线和训练损失。

输入生成器和两个命令均使用新目录。更改生成配置后重新构建，以便每次训练保留对应的数据记录。选取与分组规则见[训练数据指南](../../docs/training-datasets.md)。
